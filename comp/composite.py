# -*- coding: utf-8 -*-
"""composite.py — the frame compositor: plate → grade → optics → atmosphere →
lens → grain → typography, plus all transitions from edit.json.
"""
from __future__ import annotations

import math
import time

from PIL import Image, ImageChops, ImageFilter

from common import (FPS, FULL_H, FULL_W, clamp, frame_to_time, lerp, smoothstep,
                    smoothstep_range)
from fx import (Atmosphere, Chromatic, Grain, apply_vignette, clarity,
                flash_glow, glass_reflection, ground_treatment, heat_haze,
                light_layer, optics_params, radial_warp, screen_light,
                atmos_params, CLARITY)
from grade import apply_gain, grade
from plates import PlateProvider
from timeline import Timeline
from typography import Typography, variant_group


class Compositor:
    def __init__(self, W: int = 1920, H: int = 1080, allow_dummy: bool = True,
                 quality: str = "final", draft: bool = False):
        self.W, self.H = int(W), int(H)
        self.S = self.W / 1920.0
        self.tl = Timeline()
        self.plates = PlateProvider(self.tl, self.W, self.H, allow_dummy=allow_dummy)
        self.typo = Typography(self.tl, self.W, self.H, self.S)
        self.atm = Atmosphere()
        self.grain = Grain()
        self.chroma = Chromatic()
        self.quality = "preview" if draft else quality
        self.grain.prewarm(self.W, self.H)
        self._last_timing = {}

    # ------------------------------------------------------------------ shot
    def _render_shot(self, shot, local: int, f: int, fx: dict) -> Image.Image:
        tim = {}
        t0 = time.perf_counter()
        weave = self.tl.weave_offset(f)
        plate = self.plates.get(shot, local, weave)
        meta = self.plates.get_meta(shot) or self.plates.light_hint(shot)
        tim["plate"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        calib = self.plates.exposure_mul(shot)
        expo = clamp(fx.get("exposure", 1.0) * calib, 0.0, 3.0)
        sat = clamp(fx.get("sat_boost", 1.0) * self.plates.sat_mul(shot), 0.3, 1.7)
        im = grade(plate, shot["variant"], exposure=expo, sat_mul=sat)
        tim["grade"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        cmul = self.plates.clarity_mul(shot)
        im = clarity(im, CLARITY.get(shot["variant"], 0.2) * cmul, self.S,
                     radius=18.0 if shot.get("set") in ("field", "road") else 11.0)
        tim["clarity"] = time.perf_counter() - t0

        # window-glass reflection ghosts for the room reflection shots
        if shot["id"] in ("S37", "S38"):
            im = glass_reflection(im, 0.17, 3.4 * self.S, tint=(236, 234, 240))

        A = atmos_params(shot["variant"])
        if A["heat"] > 0.45:
            t0 = time.perf_counter()
            im = heat_haze(im, f / FPS, A["heat"], self.S,
                           seed=self.tl.shot_index(shot) * 1.7)
            tim["heat"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        pulse = self.tl.pulse(f / FPS, 0.16)
        boost = fx.get("bloom_boost", 1.0)
        light = light_layer(im, shot, f / FPS, self.S, meta, pulse=pulse, boost=boost)
        im = screen_light(im, light)
        tim["light"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        at = self.atm.layer(shot, f / FPS, self.W, self.H, self.S, meta)
        if at is not None:
            im.paste(at.convert("RGB"), (0, 0), at.getchannel("A"))
        tim["atmos"] = time.perf_counter() - t0

        # outdoor ground finish (fog + progressive blur) for field / road shots
        if shot.get("set") in ("field", "road"):
            t0 = time.perf_counter()
            bstd = self.plates.shot_stats(shot).get("bottom_std")
            im = ground_treatment(im, shot, self.S, meta,
                                  group=variant_group(shot["variant"]),
                                  bottom_std=bstd)
            tim["ground"] = time.perf_counter() - t0

        # designed additive glow (light leaks / light engulf)
        g_amt = fx.get("glow_amt", 0.0)
        if g_amt > 0.002 and fx.get("glow"):
            t0 = time.perf_counter()
            im = flash_glow(im, g_amt, fx["glow"], self.S)
            tim["glow"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        im = apply_vignette(im, shot["variant"], self.S,
                            set_name=shot.get("set", ""),
                            group=variant_group(shot["variant"]))
        tim["vignette"] = time.perf_counter() - t0

        if self.quality != "preview":
            t0 = time.perf_counter()
            P = optics_params(shot["variant"])
            im = self.chroma.apply(im, P["ca"], self.S)
            tim["ca"] = time.perf_counter() - t0

        t0 = time.perf_counter()
        P = optics_params(shot["variant"])
        im = self.grain.apply(im, f / FPS, P["grain"], self.S)
        tim["grain"] = time.perf_counter() - t0

        self._last_timing = tim
        return im

    # ------------------------------------------------------------ transitions
    def _transition(self, a: Image.Image, b: Image.Image, tr: dict, f: int) -> Image.Image:
        kind = tr["type"]
        m = tr["m"]
        W, H = self.W, self.H
        if kind == "dissolve":
            return Image.blend(a, b, smoothstep(m))
        if kind == "light_bleed":
            out = Image.blend(a, b, smoothstep(m))
            peak = math_sin_peak(m)
            out = flash_glow(out, 0.55 * peak, (255, 226, 186), self.S)
            return out
        if kind == "ripple":
            out = Image.blend(a, b, smoothstep(m))
            strength = math_sin_peak(m) * 1.0
            if strength > 0.02:
                out = radial_warp(out, 0.5, 0.62, f / FPS, strength, self.S, W, H)
            out = flash_glow(out, 0.10 * math_sin_peak(m), (200, 220, 255), self.S)
            return out
        if kind == "white_flash":
            out = Image.blend(a, b, smoothstep(m))
            peak = math_sin_peak(m) ** 1.4
            if peak > 0.01:
                white = Image.new("RGB", (W, H), (255, 252, 246))
                out = Image.blend(out, white, clamp(0.92 * peak))
                out = flash_glow(out, 0.35 * peak, (255, 245, 225), self.S)
            return out
        if kind == "from_black":
            e = clamp(m * 2.0)
            if m < 0.5:
                ea = 1.0 - smoothstep(e)
                out = apply_gain(a, clamp(1.0 - 0.995 * (1.0 - ea), 0.0, 1.0))
            else:
                eb = smoothstep((m - 0.5) * 2.0)
                out = apply_gain(b, clamp(eb ** 0.92, 0.0, 1.0))
            glow = math_sin_peak(m) ** 1.3
            if glow > 0.01:
                out = flash_glow(out, 0.10 * glow, (150, 120, 220), self.S)
            return out
        if kind == "to_black":
            if m < 0.5:
                eb = 1.0 - smoothstep(clamp(m * 2.0))
                out = apply_gain(a, clamp(eb, 0.0, 1.0))
            else:
                eb = smoothstep(clamp((m - 0.5) * 1.55))
                out = apply_gain(b, clamp(eb, 0.0, 1.0))
            return out
        # fallback: hard cut
        return b if m >= 0.5 else a

    # ------------------------------------------------------------------ frame
    def render(self, f: int, with_text: bool = True) -> Image.Image:
        plan = self.tl.plan(f)
        t = plan["t"]
        tr = plan["transition"]
        if tr is None:
            img = self._render_shot(plan["shot"], plan["local"], f, plan["fx"])
        else:
            a = self._render_shot(tr["a"], tr["a_local"], f, tr.get("a_fx", {}))
            b = self._render_shot(tr["b"], tr["b_local"], f, tr.get("b_fx", {}))
            img = self._transition(a, b, tr, f)
        # master fade in / out
        expo = plan["exposure"]
        if expo < 0.999:
            img = apply_gain(img, expo)
        # typography (never affected by weave / grain / CA)
        if with_text:
            for rgb, alpha, pos in self.typo.render(f, t):
                img.paste(rgb, pos, alpha)
        return img

    # ------------------------------------------------------------------ stats
    def stats(self) -> dict:
        return {"plates": self.plates.coverage(),
                "plate_stats": dict(self.plates.stats),
                "typo_lines": len(self.typo.lines)}


def math_sin_peak(m: float) -> float:
    return math.sin(math.pi * clamp(m)) ** 2


if __name__ == "__main__":
    comp = Compositor(1280, 720, draft=True)
    for f in (1, 280, 434, 2101, 2502, 3332, 4579, 5953, 6157, 6325, 6551):
        t0 = time.perf_counter()
        im = comp.render(f)
        dt = time.perf_counter() - t0
        print("frame %5d  %.2fs  timing %s" % (
            f, dt, {k: round(v * 1000, 1) for k, v in comp._last_timing.items()}))
    print(comp.stats())
