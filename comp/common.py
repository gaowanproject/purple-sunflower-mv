# -*- coding: utf-8 -*-
"""common.py — shared constants, paths, math, image + font helpers.

This module is the foundation of the compositing pipeline. Everything is
expressed in *output pixels* (full render = 1920x1080); a global `scale`
factor S shrinks all geometry so previews can be rendered at 640x360 etc.
"""
from __future__ import annotations

import hashlib
import json
import math
import os

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# --------------------------------------------------------------------------- paths
FPS = 24
FULL_W, FULL_H = 1920, 1080
TOTAL_FRAMES = 6551          # 6551 / 24 = 272.9583 s  (audio 272.966 s)
DURATION = 272.966

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STORY_DIR = os.path.join(ROOT, "story")
COMP_DIR = os.path.join(ROOT, "comp")
OUT_DIR = os.path.join(ROOT, "out")
FINAL_DIR = os.path.join(OUT_DIR, "final")
PLATES_DIR = os.path.join(ROOT, "plates")
ASSETS_DIR = os.path.join(ROOT, "assets")
AUDIO_DIR = os.path.join(ASSETS_DIR, "audio")
FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
CACHE_DIR = os.path.join(COMP_DIR, "cache")
DUMMY_DIR = os.path.join(CACHE_DIR, "dummy_plates")
SHEET_DIR = os.path.join(OUT_DIR, "preview_sheets")
FFMPEG = os.path.join(ROOT, "tools", "ffmpeg.exe")
SONG_WAV = os.path.join(AUDIO_DIR, "song_ff.wav")
WIN_FONTS = "C:/Windows/Fonts"


def ensure_dirs() -> None:
    for d in (CACHE_DIR, DUMMY_DIR, FINAL_DIR, SHEET_DIR, os.path.join(OUT_DIR, "logs")):
        os.makedirs(d, exist_ok=True)


# --------------------------------------------------------------------------- json
def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


# --------------------------------------------------------------------------- math
def clamp(x, a=0.0, b=1.0):
    return a if x < a else (b if x > b else x)


def lerp(a, b, t):
    return a + (b - a) * t


def smoothstep(x):
    x = clamp(x)
    return x * x * (3.0 - 2.0 * x)


def smoothstep_range(x, a, b):
    if b == a:
        return 1.0 if x >= b else 0.0
    return smoothstep((x - a) / (b - a))


def ease_out_cubic(x):
    x = clamp(x)
    return 1.0 - (1.0 - x) ** 3


def ease_in_out(x):
    x = clamp(x)
    return x * x * (3.0 - 2.0 * x)


def ease_out_quint(x):
    x = clamp(x)
    return 1.0 - (1.0 - x) ** 5


def hash01(*args) -> float:
    """Deterministic pseudo random in [0,1) from any arguments."""
    h = hashlib.blake2b(repr(args).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(h, "little") / 18446744073709551616.0


def hash_signed(*args) -> float:
    return hash01(*args) * 2.0 - 1.0


def _smooth(t):
    return t * t * (3.0 - 2.0 * t)


def vnoise(t: float, seed: float = 0.0) -> float:
    """Smooth 1-D value noise in [-1, 1]."""
    i = math.floor(t)
    f = t - i
    a = hash_signed(seed, i)
    b = hash_signed(seed, i + 1)
    return a + (b - a) * _smooth(f)


def vnoise_looped(t: float, seed: float = 0.0) -> float:
    """Smooth 1D noise that loops at 1.0 (t in [0,1))."""
    z = t * 6.283185307179586
    return (math.sin(z + seed) * 0.55
            + math.sin(2 * z + seed * 2.3) * 0.3
            + math.sin(3 * z + seed * 4.1) * 0.15)


def frame_to_time(f: int) -> float:
    return (f - 1.0) / FPS


def time_to_frame(t: float) -> int:
    return int(round(t * FPS)) + 1


# --------------------------------------------------------------------------- images
def to_rgb(im: Image.Image) -> Image.Image:
    return im if im.mode == "RGB" else im.convert("RGB")


def resize(im: Image.Image, size, resample=Image.BICUBIC) -> Image.Image:
    if im.size == tuple(size):
        return im
    return im.resize(tuple(size), resample)


def blur(im: Image.Image, radius: float) -> Image.Image:
    if radius <= 0.01:
        return im
    return im.filter(ImageFilter.GaussianBlur(radius))


def down(im: Image.Image, factor: float, resample=Image.BILINEAR) -> Image.Image:
    w, h = im.size
    return im.resize((max(1, int(round(w * factor))), max(1, int(round(h * factor)))), resample)


def screen(a: Image.Image, b: Image.Image) -> Image.Image:
    return ImageChops.screen(a, b)


def multiply(a: Image.Image, b: Image.Image) -> Image.Image:
    return ImageChops.multiply(a, b)


def blend(a: Image.Image, b: Image.Image, m: float) -> Image.Image:
    m = clamp(m)
    if m <= 0.0:
        return a
    if m >= 1.0:
        return b
    return Image.blend(a, b, m)


def solid_rgb(im: Image.Image, color) -> Image.Image:
    """Return a solid color image with the same size/mode as ``im``."""
    return Image.new("RGB", im.size, tuple(int(c) for c in color))


def luma(im: Image.Image) -> Image.Image:
    return im.convert("L")


def alpha_scale(alpha: Image.Image, k: float) -> Image.Image:
    """Scale an L-mode alpha band by k (0..1) using a cached 256 LUT."""
    kq = int(round(clamp(k) * 255))
    if kq >= 255:
        return alpha
    if kq <= 0:
        return Image.new("L", alpha.size, 0)
    lut = _alpha_luts.get(kq)
    if lut is None:
        lut = [int(round(v * kq / 255.0)) for v in range(256)]
        _alpha_luts[kq] = lut
    return alpha.point(lut)

_alpha_luts: dict = {}


def paste_rgba(base: Image.Image, layer: Image.Image, pos=(0, 0)) -> Image.Image:
    """Alpha-composite an RGBA layer onto an RGB base (in place)."""
    if layer.mode != "RGBA":
        layer = layer.convert("RGBA")
    rgb = layer.convert("RGB") if layer.mode != "RGB" else layer
    a = layer.getchannel("A")
    base.paste(rgb, pos, a)
    return base


def tint_layer(mask_l: Image.Image, color, opacity: float) -> Image.Image:
    """Build an RGBA layer from an L mask, a solid color and an opacity."""
    a = alpha_scale(mask_l, opacity)
    layer = Image.new("RGBA", mask_l.size, tuple(int(c) for c in color) + (255,))
    layer.putalpha(a)
    return layer


def radial_sprite(size: int, color, hardness: float = 0.35, falloff: float = 1.6) -> Image.Image:
    """RGBA radial gradient sprite of ``size`` px (cached)."""
    key = (int(size), tuple(int(c) for c in color), round(hardness, 2), round(falloff, 2))
    hit = _radial_cache.get(key)
    if hit is not None:
        return hit
    s = max(2, int(size) | 1)
    y, x = np.mgrid[0:s, 0:s]
    c = (s - 1) / 2.0
    r = np.sqrt((x - c) ** 2 + (y - c) ** 2) / (s / 2.0)
    inner = clamp(hardness)
    v = np.clip((1.0 - r) / max(1e-3, 1.0 - inner), 0, 1) ** falloff
    a = (v * 255).astype(np.uint8)
    rgba = np.zeros((s, s, 4), np.uint8)
    rgba[..., 0] = int(color[0])
    rgba[..., 1] = int(color[1])
    rgba[..., 2] = int(color[2])
    rgba[..., 3] = a
    im = Image.fromarray(rgba, "RGBA")
    _radial_cache[key] = im
    if len(_radial_cache) > 200:
        _radial_cache.pop(next(iter(_radial_cache)))
    return im

_radial_cache: dict = {}


def gauss_sprite(size: int, color, sigma: float) -> Image.Image:
    return radial_sprite(size, color, hardness=0.0, falloff=sigma)


def box_blur_np(a: np.ndarray, r: int, axis: int) -> np.ndarray:
    """Fast box blur along one axis for float arrays (cumsum based)."""
    if r <= 0:
        return a
    a = np.moveaxis(a, axis, 0)
    n = a.shape[0]
    cs = np.cumsum(a, axis=0, dtype=np.float32)
    cs = np.concatenate([np.zeros((1,) + a.shape[1:], np.float32), cs], 0)
    idx_hi = np.clip(np.arange(n) + r + 1, 0, n)
    idx_lo = np.clip(np.arange(n) - r, 0, n)
    span = (idx_hi - idx_lo).astype(np.float32)
    span = span.reshape((-1,) + (1,) * (a.ndim - 1))
    out = (cs[idx_hi] - cs[idx_lo]) / span
    return np.moveaxis(out, 0, axis)


def gauss_blur_np(a: np.ndarray, sigma: float, passes: int = 3) -> np.ndarray:
    """Approximate gaussian with several box passes (float, array-agnostic)."""
    if sigma <= 0.3:
        return a
    r = max(1, int(round((sigma * 1.6) / passes)))
    out = a
    for _ in range(passes):
        out = box_blur_np(out, r, 0)
        out = box_blur_np(out, r, 1)
    return out


def np_to_pil(a: np.ndarray) -> Image.Image:
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def pil_to_np(im: Image.Image) -> np.ndarray:
    return np.asarray(im)


# --------------------------------------------------------------------------- fonts
FONT_PATHS = {
    "jp300": os.path.join(FONT_DIR, "NotoSerifJP-300.ttf"),
    "jp400": os.path.join(FONT_DIR, "ShipporiMincho-400.ttf"),
    "jp500": os.path.join(FONT_DIR, "ShipporiMincho-500.ttf"),
    "jp600": os.path.join(FONT_DIR, "ShipporiMincho-600.ttf"),
    "jp700": os.path.join(FONT_DIR, "ShipporiMincho-700.ttf"),
    "noto_jp200": os.path.join(FONT_DIR, "NotoSerifJP-200.ttf"),
    "noto_jp300": os.path.join(FONT_DIR, "NotoSerifJP-300.ttf"),
    "noto_jp400": os.path.join(FONT_DIR, "NotoSerifJP-400.ttf"),
    "zen_old400": os.path.join(FONT_DIR, "ZenOldMincho-400.ttf"),
    "zen_old500": os.path.join(FONT_DIR, "ZenOldMincho-500.ttf"),
    "zen_old600": os.path.join(FONT_DIR, "ZenOldMincho-600.ttf"),
    "zen_old700": os.path.join(FONT_DIR, "ZenOldMincho-700.ttf"),
    "kaku300": os.path.join(FONT_DIR, "ZenKakuGothicNew-300.ttf"),
    "kaku400": os.path.join(FONT_DIR, "ZenKakuGothicNew-400.ttf"),
    "kaku500": os.path.join(FONT_DIR, "ZenKakuGothicNew-500.ttf"),
    "kaku700": os.path.join(FONT_DIR, "ZenKakuGothicNew-700.ttf"),
    "kaisei400": os.path.join(FONT_DIR, "KaiseiDecol-400.ttf"),
    "kaisei700": os.path.join(FONT_DIR, "KaiseiDecol-700.ttf"),
    # Chinese (simplified) — variable fonts, weight set through variation axes
    "sc_serif": os.path.join(WIN_FONTS, "NotoSerifSC-VF.ttf"),
    "sc_sans": os.path.join(WIN_FONTS, "NotoSansSC-VF.ttf"),
    "sc_han": os.path.join(WIN_FONTS, "Source Han Serif SC Heavy (TrueType).ttf"),
}

_FONT_CACHE: dict = {}


def load_font(key: str, px: int, weight: int | None = None) -> ImageFont.FreeTypeFont:
    """Load a font by key at pixel size ``px`` (cached).

    For variable fonts pass ``weight`` (e.g. 300) to pick an instance; the
    cache key includes it so mutation is safe.
    """
    px = max(4, int(round(px)))
    ck = (key, px, weight)
    f = _FONT_CACHE.get(ck)
    if f is not None:
        return f
    path = FONT_PATHS[key]
    f = ImageFont.truetype(path, px)
    if weight is not None:
        try:
            f.set_variation_by_axes([weight])
        except (OSError, ValueError, AttributeError):
            pass
    _FONT_CACHE[ck] = f
    return f


def font_key_for(lang: str, emphasis: bool = False) -> tuple:
    """Return (font_key, weight) for a language/style combination."""
    if lang == "jp":
        return ("jp600" if emphasis else "jp500", None)
    return ("sc_sans", 400 if not emphasis else 500)


def glyph_bbox(font: ImageFont.FreeTypeFont, ch: str):
    return font.getbbox(ch, anchor="ls")


def draw_text_layer(size, font: ImageFont.FreeTypeFont, text: str, fill=(255, 255, 255, 255)):
    """Utility: render text into a tight RGBA layer (used for tiny labels)."""
    w, h = size
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((0, 0), text, font=font, fill=fill, anchor="lt")
    return im


# --------------------------------------------------------------------------- audio
class AudioEnergy:
    """Tiny wrapper over the pre-computed RMS envelope / onset list."""

    def __init__(self):
        self.rms = None
        self.hop = 0.01
        self.onsets = np.array([])
        try:
            self.rms = np.load(os.path.join(AUDIO_DIR, "rms.npy")).astype(np.float32)
            meta = load_json(os.path.join(AUDIO_DIR, "audio_meta.json"), {}) or {}
            self.onsets = np.asarray(meta.get("onsets", []), dtype=np.float32)
        except OSError:
            pass
        if self.rms is not None and self.rms.size:
            self._rms_norm = self.rms / (np.percentile(self.rms, 97) + 1e-6)
        else:
            self._rms_norm = None

    def rms_at(self, t: float) -> float:
        if self._rms_norm is None:
            return 0.35
        i = int(t / self.hop)
        if i < 0 or i >= len(self._rms_norm):
            return 0.0
        return float(min(1.0, self._rms_norm[i]))

    def pulse(self, t: float, decay: float = 0.14) -> float:
        """0..1 envelope: 1 right on an onset, decaying smoothly."""
        if self.onsets.size == 0:
            return 0.0
        i = int(np.searchsorted(self.onsets, t, side="right")) - 1
        if i < 0:
            return 0.0
        dt = t - float(self.onsets[i])
        if dt < 0:
            return 0.0
        if dt > 0.5:
            return 0.0
        return float(math.exp(-dt / decay))


_audio = None


def audio() -> AudioEnergy:
    global _audio
    if _audio is None:
        _audio = AudioEnergy()
    return _audio
