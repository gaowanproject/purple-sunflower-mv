# -*- coding: utf-8 -*-
"""plates.py — resolve every frame to real 3D plates when available, else the
procedural dummy plates.  Handles camera moves, gate weave and LRU caching.
"""
from __future__ import annotations

import bisect
import os
from collections import OrderedDict

import numpy as np
from PIL import Image, ImageFilter, ImageFile

from common import (CACHE_DIR, DUMMY_DIR, PLATES_DIR, clamp, lerp, load_json,
                    smoothstep)
from placeholder import CANVAS_SCALE, build_canvas, ensure_dummy_plates

META_PATH = os.path.join(DUMMY_DIR, "meta.json")

# Shot-matching auto exposure: the raw 3D plates are neutral and dark, so each
# shot is lifted (or pulled) so its median luma lands on the look target of its
# world.  Computed once per shot and held stable for the whole shot.
TARGET_MEAN = {
    # finished-look mean luma: clean plates get pulled down ~0.2-0.4 EV in the
    # gold world, night worlds stay deep and contrasty.
    "noon_hot": 0.280, "noon_side": 0.250, "gold_noon": 0.265, "gold_dusk": 0.235,
    "dusk_afterglow": 0.235, "macro_warm": 0.265,
    "violet_dusk": 0.165, "violet_night": 0.135, "petals_dark": 0.090,
    "rain_night": 0.135, "night_rain": 0.140, "night_dark": 0.070,
    "night_lamp": 0.155, "macro_cold": 0.140, "city_bridge": 0.100,
}


class PlateProvider:
    def __init__(self, timeline, out_w: int, out_h: int, allow_dummy: bool = True):
        self.tl = timeline
        self.W, self.H = out_w, out_h
        self.S = out_w / 1920.0
        self.allow_dummy = allow_dummy
        self.real = {}
        self.meta = load_json(META_PATH, {}) or {}
        self.stats = {"real": 0, "dummy": 0, "missing_fallback": 0}
        self._canvas = OrderedDict()
        self._frames = OrderedDict()
        self._calib = {}
        self._stats = {}
        self._hint = {}
        self._bad = set()
        self._scan()
        self._dummy_ready = False

    # ------------------------------------------------------------------ scan
    def _scan(self):
        for shot in self.tl.shots:
            sid = shot["id"]
            d = os.path.join(PLATES_DIR, sid)
            frames = {}
            if os.path.isdir(d):
                try:
                    for name in os.listdir(d):
                        if not name.lower().endswith((".png", ".jpg", ".jpeg")):
                            continue
                        stem = os.path.splitext(name)[0]
                        # plates are written as "S12_1258.png" (global frame) or
                        # "0001.png" (local frame) — take the trailing number
                        digits = ""
                        for ch in reversed(stem):
                            if ch.isdigit():
                                digits = ch + digits
                            else:
                                break
                        if not digits:
                            continue
                        frames[int(digits)] = os.path.join(d, name)
                except OSError:
                    frames = {}
            if frames:
                self.real[sid] = frames
        self._n_real_shots = len(self.real)

    def refresh(self):
        self.real = {}
        self._scan()
        return self.real

    def coverage(self) -> dict:
        total = len(self.tl.shots)
        return {"shots_with_plates": len(self.real), "shots_total": total,
                "real_frames": sum(len(v) for v in self.real.values()),
                "expected_frames": sum(s["nframes"] for s in self.tl.shots)}

    def has_real(self, shot) -> bool:
        return shot["id"] in self.real

    # ------------------------------------------------------- auto exposure
    @staticmethod
    def _luma_stats(im: Image.Image):
        g = im.convert("L").resize((160, 90), Image.BILINEAR)
        arr = np.asarray(g, dtype=np.float32) / 255.0
        rgb = np.asarray(im.resize((160, 90), Image.BILINEAR), dtype=np.float32) / 255.0
        chroma_map = rgb.max(axis=2) - rgb.min(axis=2)
        bright = arr > 0.12
        if bright.sum() > 40:
            chroma = float(chroma_map[bright].mean())
        else:
            chroma = float(chroma_map.mean())
        # bottom-of-frame texture tells us whether the foreground ground needs
        # fog/blur (noisy grass) or is already a clean black bokeh
        hh = arr.shape[0]
        bot = arr[int(hh * 0.72):]
        return dict(mean=float(arr.mean()), std=float(arr.std()),
                    chroma=chroma, p995=float(np.percentile(arr, 99.5)),
                    bottom_std=float(bot.std()))

    def _sample_image(self, shot):
        sid = shot["id"]
        if sid in self.real:
            frames = self.real[sid]
            if frames:
                num = sorted(frames.keys())[0]
                try:
                    return Image.open(frames[num]).convert("RGB")
                except (OSError, ValueError):
                    return None
        return self._load_canvas(shot).convert("RGB")

    def shot_stats(self, shot) -> dict:
        sid = shot["id"]
        hit = self._stats.get(sid)
        if hit is not None:
            return hit
        im = self._sample_image(shot)
        st = self._luma_stats(im) if im is not None else dict(mean=0.3, std=0.1, chroma=0.12, p995=0.8)
        self._stats[sid] = st
        return st

    def exposure_mul(self, shot) -> float:
        """Stable per-shot exposure matching so plates land on the look target."""
        sid = shot["id"]
        hit = self._calib.get(sid)
        if hit is not None:
            return hit
        st = self.shot_stats(shot)
        target = TARGET_MEAN.get(shot["variant"], 0.30)
        mul = target / max(0.02, st["mean"])
        # highlight protection: never push the top 0.5% past ~0.93
        if st["p995"]:
            mul = min(mul, 0.93 / max(0.10, st["p995"]))
        mul = clamp(mul, 0.45, 1.95)
        self._calib[sid] = round(mul, 4)
        return self._calib[sid]

    def sat_mul(self, shot) -> float:
        """Lift saturation on flat/hazy plates, leave already-saturated ones alone."""
        st = self.shot_stats(shot)
        variant = shot["variant"]
        if variant in ("night_rain", "rain_night", "night_dark", "city_bridge", "macro_cold"):
            return 1.0
        return clamp((0.185 / max(0.03, st["chroma"])) ** 0.45, 0.94, 1.30)

    def clarity_mul(self, shot) -> float:
        st = self.shot_stats(shot)
        base = clamp(1.0 + (0.12 - st["std"]) * 2.6, 1.0, 1.45)
        if shot.get("set") in ("field", "road"):
            base *= 1.25
        return base

    def light_hint(self, shot):
        """Estimated light source position (for leak / flare placement)."""
        sid = shot["id"]
        hit = self._hint.get(sid)
        if hit is not None:
            return hit
        im = self._sample_image(shot)
        if im is None:
            self._hint[sid] = None
            return None
        small = im.convert("L").resize((96, 54), Image.BILINEAR)
        small = small.filter(ImageFilter.GaussianBlur(4.0))
        arr = np.asarray(small, dtype=np.float32)
        region = arr[: int(54 * 0.74)]
        y, x = np.unravel_index(int(np.argmax(region)), region.shape)
        hint = {"sun": [round(float(x) / 96.0, 3), round(float(y) / 54.0, 3)]}
        self._hint[sid] = hint
        return hint

    def _ensure_dummy(self):
        if not self._dummy_ready:
            ensure_dummy_plates(self.tl.shots)
            self.meta = load_json(META_PATH, {}) or {}
            self._dummy_ready = True

    # ----------------------------------------------------------------- access
    def get_meta(self, shot):
        return self.meta.get(shot["id"])

    def _load_canvas(self, shot):
        self._ensure_dummy()
        sid = shot["id"]
        cav = self._canvas.get(sid)
        if cav is not None:
            self._canvas.move_to_end(sid)
            return cav
        path = os.path.join(DUMMY_DIR, sid + ".png")
        if not os.path.exists(path):
            img, sun, hz = build_canvas(shot)
            img.save(path, "PNG", compress_level=3)
        else:
            img = Image.open(path).convert("RGB")
        self._canvas[sid] = img
        if len(self._canvas) > 9:
            self._canvas.popitem(last=False)
        return img

    def _load_real_frame(self, shot, num: int):
        sid = shot["id"]
        key = (sid, num)
        if key in self._bad:
            return None
        fr = self._frames.get(key)
        if fr is not None:
            self._frames.move_to_end(key)
            return fr
        path = self.real.get(sid, {}).get(num)
        if path is None:
            return None
        fr = None
        try:
            with Image.open(path) as im:
                fr = im.convert("RGB")
                fr.load()
        except (OSError, ValueError):
            self._bad.add(key)
            return None
        self._frames[key] = fr
        if len(self._frames) > 6:
            self._frames.popitem(last=False)
        return fr

    def _resolve_number(self, shot, local: int):
        """Plates may be numbered by local shot frame or by global frame."""
        frames = self.real.get(shot["id"], {})
        for cand in (local, shot["f0"] + local - 1):
            if cand in frames:
                return cand
        return None

    def _nearest_real(self, shot, local: int):
        frames = sorted(self.real[shot["id"]].keys())
        targets = [local, shot["f0"] + local - 1]
        best = None
        for target in targets:
            i = bisect.bisect_left(frames, target)
            cand = []
            if i < len(frames):
                cand.append(frames[i])
            if i > 0:
                cand.append(frames[i - 1])
            cand.sort(key=lambda n: abs(n - target))
            if cand and (best is None or abs(cand[0] - target) < best[1]):
                best = (cand[0], abs(cand[0] - target))
        return best[0] if best else None

    def _nearest_loadable(self, shot, local: int, max_try: int = 16):
        """Nearest frame whose PNG actually decodes (skips truncated writes)."""
        frames = sorted(self.real[shot["id"]].keys())
        candidates = []
        targets = [local, shot["f0"] + local - 1]
        for target in targets:
            i = bisect.bisect_left(frames, target)
            for d in range(0, max_try):
                for j in (i - d, i + d):
                    if 0 <= j < len(frames):
                        candidates.append((abs(frames[j] - target), frames[j]))
        candidates.sort()
        tried = set()
        for _dist, num in candidates:
            if num in tried:
                continue
            tried.add(num)
            fr = self._load_real_frame(shot, num)
            if fr is not None:
                return fr
        # last resort: partially-decodable frame (accept artifacts rather than a hole)
        for _dist, num in candidates[:6]:
            path = self.real[shot["id"]].get(num)
            if not path:
                continue
            try:
                old = ImageFile.LOAD_TRUNCATED_IMAGES
                ImageFile.LOAD_TRUNCATED_IMAGES = True
                with Image.open(path) as im:
                    fr = im.convert("RGB")
                    fr.load()
                ImageFile.LOAD_TRUNCATED_IMAGES = old
                self.stats["truncated"] = self.stats.get("truncated", 0) + 1
                return fr
            except (OSError, ValueError):
                continue
        return None

    # -------------------------------------------------------------- camera box
    def _camera_box_placeholder(self, shot, local, weave):
        canvas = self._load_canvas(shot)
        cw, ch = canvas.size
        p = (local - 1) / max(1, shot["nframes"] - 1)
        pe = smoothstep(clamp((p - 0.01) / 0.98))
        mv = self.tl.motion(shot)
        z = lerp(mv["zoom"][0], mv["zoom"][1], pe)
        px, py = mv["pan"]
        # box in canvas pixels: at zoom 1 the full 1920-wide frame is shown
        bw = cw * self.S / z
        bh = ch * self.S / z
        pan_w = (canvas.width * self.S - bw) / 2.0
        pan_h = (canvas.height * self.S - bh) / 2.0
        cx = canvas.width * self.S / 2.0 + px * pan_w * (2 * pe - 1)
        cy = canvas.height * self.S / 2.0 + py * pan_h * (2 * pe - 1)
        if mv.get("shake"):
            amp = 1.4 * mv["shake"] * self.S
            cx += amp * self.tl.weave_offset(local * 1.7, 1.0)[0]
            cy += amp * self.tl.weave_offset(local * 1.3, 2.0)[1]
        scale_canvas = canvas.width / 1920.0   # 1.2
        cx += weave[0] * scale_canvas * self.S
        cy += weave[1] * scale_canvas * self.S
        x0 = cx - bw / 2.0
        y0 = cy - bh / 2.0
        x0 = clamp(x0, 0.0, max(0.0, cw - bw))
        y0 = clamp(y0, 0.0, max(0.0, ch - bh))
        return canvas, (x0, y0, x0 + bw, y0 + bh)

    def _camera_box_real(self, shot, src, weave):
        W, H = src.size
        z = 1.010
        bw, bh = W / z, H / z
        cx = W / 2.0 + weave[0] * (W / 1920.0)
        cy = H / 2.0 + weave[1] * (H / 1080.0)
        x0 = clamp(cx - bw / 2.0, 0.0, W - bw)
        y0 = clamp(cy - bh / 2.0, 0.0, H - bh)
        return src, (x0, y0, x0 + bw, y0 + bh)

    # ------------------------------------------------------------------ get
    def get(self, shot, local: int, weave=(0.0, 0.0)) -> Image.Image:
        sid = shot["id"]
        if sid in self.real:
            num = self._resolve_number(shot, local)
            fr = self._load_real_frame(shot, num) if num is not None else None
            if fr is None:
                fr = self._nearest_loadable(shot, local)
                if fr is not None:
                    self.stats["missing_fallback"] += 1
            if fr is not None:
                src, box = self._camera_box_real(shot, fr, weave)
                self.stats["real"] += 1
                return src.resize((self.W, self.H), Image.BICUBIC, box=box)
        else:
            self.stats["dummy"] += 1
        if not self.allow_dummy:
            raise RuntimeError("missing plates for %s frame %d" % (sid, local))
        canvas, box = self._camera_box_placeholder(shot, local, weave)
        return canvas.resize((self.W, self.H), Image.BICUBIC, box=box)
