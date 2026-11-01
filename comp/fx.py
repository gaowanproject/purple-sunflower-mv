# -*- coding: utf-8 -*-
"""fx.py — optical / camera / 2.5D atmosphere effects.

All effects are procedural: bloom, halation, anamorphic streak, light leaks,
rain, lens droplets, ripples, petals, dust, bokeh, stars, heat haze, vignette,
temporally coherent grain and (subtle) chromatic aberration.
"""
from __future__ import annotations

import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from common import (alpha_scale, blur, box_blur_np, clamp, hash01, lerp,
                    load_json, radial_sprite, resize, smoothstep, vnoise)

# --------------------------------------------------------------------- config
# bloom  : additive glow strength (0..1)
# hal    : halation strength + tint
# streak : anamorphic horizontal streak strength + tint
# leak   : corner light-leak strength + tint
# flare  : sun flare ghosts (placeholders only, needs sun position)
# grain  : grain strength
# ca     : chromatic aberration at the frame edge, in full-res px
# vig    : vignette strength
OPTICS = {
    "noon_hot": dict(bloom=0.66, hal=0.46, hal_tint=(255, 144, 66), streak=0.12,
                     streak_tint=(210, 228, 255), leak=0.22, leak_tint=(255, 190, 112),
                     flare=0.65, grain=0.048, ca=0.55, vig=0.13),
    "noon_side": dict(bloom=0.56, hal=0.40, hal_tint=(255, 150, 78), streak=0.10,
                      streak_tint=(205, 225, 255), leak=0.18, leak_tint=(255, 198, 126),
                      flare=0.5, grain=0.046, ca=0.50, vig=0.12),
    "gold_noon": dict(bloom=0.64, hal=0.44, hal_tint=(255, 156, 78), streak=0.13,
                      streak_tint=(212, 228, 255), leak=0.22, leak_tint=(255, 202, 132),
                      flare=0.6, grain=0.044, ca=0.52, vig=0.12),
    "gold_dusk": dict(bloom=0.62, hal=0.44, hal_tint=(255, 134, 62), streak=0.12,
                      streak_tint=(208, 220, 255), leak=0.26, leak_tint=(255, 166, 96),
                      flare=0.6, grain=0.048, ca=0.55, vig=0.14),
    "violet_dusk": dict(bloom=0.42, hal=0.32, hal_tint=(206, 126, 255), streak=0.10,
                        streak_tint=(190, 200, 255), leak=0.22, leak_tint=(196, 136, 255),
                        flare=0.4, grain=0.072, ca=0.58, vig=0.15),
    "violet_night": dict(bloom=0.46, hal=0.28, hal_tint=(168, 116, 255), streak=0.09,
                         streak_tint=(180, 196, 255), leak=0.20, leak_tint=(168, 118, 255),
                         flare=0.35, grain=0.078, ca=0.58, vig=0.16),
    "dusk_afterglow": dict(bloom=0.58, hal=0.42, hal_tint=(255, 142, 78), streak=0.11,
                           streak_tint=(208, 220, 255), leak=0.24, leak_tint=(255, 174, 112),
                           flare=0.5, grain=0.050, ca=0.52, vig=0.14),
    "rain_night": dict(bloom=0.38, hal=0.24, hal_tint=(146, 136, 255), streak=0.07,
                       streak_tint=(168, 200, 255), leak=0.14, leak_tint=(146, 126, 250),
                       flare=0.2, grain=0.082, ca=0.50, vig=0.17),
    "night_rain": dict(bloom=0.36, hal=0.22, hal_tint=(146, 138, 255), streak=0.07,
                       streak_tint=(168, 200, 255), leak=0.12, leak_tint=(136, 118, 240),
                       flare=0.15, grain=0.080, ca=0.48, vig=0.17),
    "night_dark": dict(bloom=0.28, hal=0.16, hal_tint=(120, 120, 220), streak=0.05,
                       streak_tint=(160, 190, 255), leak=0.09, leak_tint=(108, 108, 210),
                       flare=0.1, grain=0.092, ca=0.42, vig=0.19),
    "night_lamp": dict(bloom=0.40, hal=0.28, hal_tint=(255, 146, 76), streak=0.06,
                       streak_tint=(190, 210, 255), leak=0.20, leak_tint=(255, 166, 96),
                       flare=0.25, grain=0.072, ca=0.48, vig=0.17),
    "macro_cold": dict(bloom=0.38, hal=0.20, hal_tint=(148, 188, 255), streak=0.06,
                       streak_tint=(180, 210, 255), leak=0.14, leak_tint=(118, 168, 255),
                       flare=0.2, grain=0.070, ca=0.55, vig=0.16),
    "macro_warm": dict(bloom=0.46, hal=0.32, hal_tint=(255, 154, 84), streak=0.07,
                       streak_tint=(200, 220, 255), leak=0.18, leak_tint=(255, 186, 116),
                       flare=0.25, grain=0.062, ca=0.55, vig=0.16),
    "city_bridge": dict(bloom=0.32, hal=0.20, hal_tint=(255, 166, 104), streak=0.08,
                        streak_tint=(190, 205, 240), leak=0.10, leak_tint=(118, 138, 190),
                        flare=0.1, grain=0.092, ca=0.45, vig=0.18),
    "petals_dark": dict(bloom=0.38, hal=0.24, hal_tint=(170, 110, 255), streak=0.05,
                        streak_tint=(170, 190, 255), leak=0.12, leak_tint=(148, 98, 240),
                        flare=0.1, grain=0.086, ca=0.50, vig=0.19),
}

# atmosphere mix per variant (0..1)
ATMOS = {
    "noon_hot": dict(heat=0.85, dust=0.35, petals=0.10, rain=0.0, drops=0.0, bokeh=0.18,
                     stars=0.0, ripples=0.0, leak=0.55, sun_glow=0.55, rising=False),
    "noon_side": dict(heat=0.55, dust=0.30, petals=0.10, rain=0.0, drops=0.0, bokeh=0.15,
                      stars=0.0, ripples=0.0, leak=0.40, sun_glow=0.35, rising=False),
    "gold_noon": dict(heat=0.22, dust=0.45, petals=0.70, rain=0.0, drops=0.0, bokeh=0.30,
                      stars=0.0, ripples=0.0, leak=0.45, sun_glow=0.45, rising=False),
    "gold_dusk": dict(heat=0.15, dust=0.45, petals=0.60, rain=0.0, drops=0.0, bokeh=0.30,
                      stars=0.0, ripples=0.0, leak=0.50, sun_glow=0.55, rising=False),
    "violet_dusk": dict(heat=0.10, dust=0.35, petals=0.65, rain=0.0, drops=0.0, bokeh=0.30,
                        stars=0.0, ripples=0.0, leak=0.42, sun_glow=0.28, rising=True),
    "violet_night": dict(heat=0.0, dust=0.32, petals=0.60, rain=0.0, drops=0.0, bokeh=0.32,
                         stars=0.75, ripples=0.0, leak=0.30, sun_glow=0.18, rising=True),
    "dusk_afterglow": dict(heat=0.20, dust=0.35, petals=0.35, rain=0.0, drops=0.0, bokeh=0.22,
                           stars=0.0, ripples=0.0, leak=0.55, rising=False),
    "rain_night": dict(heat=0.0, dust=0.15, petals=0.0, rain=0.95, drops=0.45, bokeh=0.60,
                       stars=0.0, ripples=0.55, leak=0.30, rising=False),
    "night_rain": dict(heat=0.0, dust=0.22, petals=0.0, rain=0.55, drops=0.35, bokeh=0.45,
                       stars=0.0, ripples=0.15, leak=0.24, rising=False),
    "night_dark": dict(heat=0.0, dust=0.18, petals=0.0, rain=0.20, drops=0.10, bokeh=0.18,
                       stars=0.15, ripples=0.0, leak=0.12, rising=False),
    "night_lamp": dict(heat=0.0, dust=0.40, petals=0.0, rain=0.18, drops=0.10, bokeh=0.30,
                       stars=0.0, ripples=0.0, leak=0.30, rising=False),
    "macro_cold": dict(heat=0.0, dust=0.20, petals=0.0, rain=0.0, drops=0.50, bokeh=0.35,
                       stars=0.0, ripples=0.10, leak=0.20, rising=False),
    "macro_warm": dict(heat=0.0, dust=0.30, petals=0.0, rain=0.0, drops=0.35, bokeh=0.40,
                       stars=0.0, ripples=0.0, leak=0.30, rising=False),
    "city_bridge": dict(heat=0.0, dust=0.20, petals=0.0, rain=0.35, drops=0.20, bokeh=0.40,
                        stars=0.0, ripples=0.0, leak=0.15, rising=False),
    "petals_dark": dict(heat=0.0, dust=0.15, petals=0.55, rain=0.0, drops=0.0, bokeh=0.25,
                        stars=0.10, ripples=0.30, leak=0.18, rising=True),
}

PETAL_COLORS = {
    "gold": (255, 196, 112), "gold2": (255, 222, 150),
    "violet": (212, 176, 255), "violet2": (246, 232, 255),
    "white": (255, 244, 232),
}
STREAK_COLORS = {"gold": (255, 214, 150), "violet": (190, 150, 255), "cool": (170, 200, 255)}


def optics_params(variant: str) -> dict:
    return OPTICS.get(variant, OPTICS["gold_dusk"])


def atmos_params(variant: str) -> dict:
    return ATMOS.get(variant, ATMOS["gold_dusk"])


# ------------------------------------------------------------------ helpers
def _to_u8(arr) -> Image.Image:
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _small(im: Image.Image, f: int):
    w, h = im.size
    return im.resize((max(8, w // f), max(8, h // f)), Image.BILINEAR)


# ------------------------------------------------------------------ light layer
def light_layer(im: Image.Image, shot, t: float, S: float, meta: dict | None = None,
                pulse: float = 0.0, boost: float = 1.0) -> Image.Image:
    """Bloom + halation + anamorphic streak + light leak, as an additive RGB layer.

    Everything is built in normalised [0,1] space and upscaled once; the caller
    screen-blends it over the graded frame.
    """
    W, H = im.size
    variant = shot["variant"]
    P = optics_params(variant)
    A = atmos_params(variant)
    f = 7 if S >= 0.8 else 6
    sw, sh = max(8, W // f), max(8, H // f)
    small = im.resize((sw, sh), Image.BILINEAR)
    a = np.asarray(small).astype(np.float32) / 255.0
    lum = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
    # adaptive thresholds: bright sunny plates should only bloom on the hottest
    # highlights, dark night plates should glow generously
    p82 = float(np.percentile(lum, 82))
    thr = clamp(p82 * 0.84, 0.26, 0.88)
    hot = np.clip((lum - thr) / max(0.07, 0.99 - thr), 0.0, 1.0) ** 1.40
    bright = a * hot[..., None]
    # --- bloom: two blur scales combined
    bloom_amt = P["bloom"] * boost * (1.0 + 0.06 * pulse)
    bimg = _to_u8(bright * 255.0)
    b1 = bimg.filter(ImageFilter.GaussianBlur(2.6))
    b2 = bimg.filter(ImageFilter.GaussianBlur(10.0))
    b3 = bimg.filter(ImageFilter.GaussianBlur(24.0))
    glow = (np.asarray(b1).astype(np.float32) * 0.26
            + np.asarray(b2).astype(np.float32) * 0.36
            + np.asarray(b3).astype(np.float32) * 0.38) / 255.0 * bloom_amt * 1.18
    # --- halation: warm / violet bleed around the very hot cores
    p95 = float(np.percentile(lum, 95))
    hal_thr = clamp(p95 * 0.96, 0.55, 0.97)
    hal_mask = np.clip((lum - hal_thr) / max(0.03, 0.995 - hal_thr), 0.0, 1.0) ** 1.05
    hal = (hal_mask[..., None] * np.array(P["hal_tint"], np.float32)[None, None, :] / 255.0
           * P["hal"] * 0.55 * boost)
    hal = np.asarray(_to_u8(hal * 255.0).filter(ImageFilter.GaussianBlur(6.0))).astype(np.float32) / 255.0
    # --- anamorphic streak (very wide horizontal blur of the highlights)
    st = np.asarray(_to_u8(bright * 255.0)).astype(np.float32) / 255.0
    st = box_blur_np(box_blur_np(st, 12, 1), 12, 1)
    streak = st * (P["streak"] * 0.85) * (np.array(P["streak_tint"], np.float32) / 255.0)[None, None, :]
    # --- light leak: soft moving warm / violet glow from one side
    leak_amt = A["leak"] * (0.68 + 0.32 * math.sin(t * 0.9 + hash01(shot["id"]) * 6.28))
    if meta and meta.get("sun"):
        lx, ly = meta["sun"]
    else:
        lx, ly = 0.30, 0.24
    lx += 0.05 * math.sin(t * 0.31)
    ly += 0.04 * math.cos(t * 0.23)
    yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
    dx = xx / sw - lx
    dy = yy / sh - ly
    lr = np.sqrt((dx * 0.70) ** 2 + dy ** 2)
    leak = np.clip(1.0 - lr / 0.90, 0.0, 1.0) ** 2.8 * leak_amt * 0.24
    base = glow + hal + streak
    base += leak[..., None] * (np.array(P["leak_tint"], np.float32) / 255.0)[None, None, :]
    # sun / horizon glow: a soft light source bloom that sells the sunlight
    sg = A.get("sun_glow", 0.0)
    if sg > 0.01 and meta and meta.get("sun"):
        sx0, sy0 = meta["sun"]
        r = np.sqrt(((xx / sw) - sx0) ** 2 * 0.65 + ((yy / sh) - sy0) ** 2)
        sun = np.clip(1.0 - r / 0.42, 0.0, 1.0) ** 2.0 * sg * 0.26
        base += sun[..., None] * (np.array(P["leak_tint"], np.float32) / 255.0)[None, None, :]
    base = np.clip(base, 0.0, 1.0) * 255.0
    # --- sun flare ghosts (placeholder plates only, they know where the sun is)
    if P["flare"] > 0.01 and meta and meta.get("sun"):
        sunx, suny = meta["sun"][0] * sw, meta["sun"][1] * sh
        cx, cy = sw * 0.5, sh * 0.5
        ghosts = [(0.55, 0.10, (255, 210, 160)), (0.85, 0.05, (255, 180, 220)),
                  (1.25, 0.16, (190, 210, 255)), (-0.35, 0.07, (255, 230, 190))]
        for gx, gr, gc in ghosts:
            px = sunx + (cx - sunx) * (1 + gx)
            py = suny + (cy - suny) * (1 + gx)
            rr = max(2, int(gr * sw))
            if 0 <= px < sw and 0 <= py < sh:
                spr = radial_sprite(rr * 2, gc, hardness=0.15, falloff=2.4)
                arr = np.asarray(spr).astype(np.float32)
                x0 = int(clamp(px - rr, 0, sw - 1))
                y0 = int(clamp(py - rr, 0, sh - 1))
                x1 = min(sw, x0 + arr.shape[1])
                y1 = min(sh, y0 + arr.shape[0])
                sub = arr[:y1 - y0, :x1 - x0]
                alpha = sub[..., 3:4] / 255.0 * P["flare"] * 0.10
                region = base[y0:y1, x0:x1]
                region += alpha * sub[..., :3]
    out = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
    return out.resize((W, H), Image.BILINEAR)


def screen_light(im: Image.Image, light: Image.Image) -> Image.Image:
    return ImageChops.screen(im, light)


# --------------------------------------------------------------- local contrast
def clarity(im: Image.Image, amount: float, S: float, radius: float = 9.0) -> Image.Image:
    """Cheap dehaze / local contrast: unsharp mask at half resolution.

    The 3D plates are rendered flat and hazy; a touch of clarity restores the
    micro-contrast that makes the frame feel photographed.
    """
    if amount <= 0.01:
        return im
    W, H = im.size
    f = 4
    hw, hh = max(8, W // f), max(8, H // f)
    small = im.resize((hw, hh), Image.BILINEAR)
    blur_small = small.filter(ImageFilter.GaussianBlur(max(1.0, radius * 0.34 * max(0.6, S))))
    a = np.asarray(small).astype(np.float32)
    b = np.asarray(blur_small).astype(np.float32)
    out = a + (a - b) * amount
    sharp = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8))
    return sharp.resize((W, H), Image.BILINEAR)


CLARITY = {
    "noon_hot": 0.34, "noon_side": 0.32, "gold_noon": 0.34, "gold_dusk": 0.32,
    "dusk_afterglow": 0.30, "macro_warm": 0.22,
    "violet_dusk": 0.26, "violet_night": 0.22, "petals_dark": 0.18,
    "rain_night": 0.20, "night_rain": 0.18, "night_dark": 0.14,
    "night_lamp": 0.20, "macro_cold": 0.20, "city_bridge": 0.18,
}


# --------------------------------------------------------- glass reflections
def glass_reflection(im: Image.Image, amount: float = 0.20, blur_px: float = 2.6,
                     tint=None) -> Image.Image:
    """Blend a vertically mirrored, slightly blurred copy back over the frame.

    Used for the window-glass reflection shots (S37/S38): the ghosted double
    sells "two figures, one of them only a reflection".
    """
    if amount <= 0.005:
        return im
    flipped = im.transpose(Image.FLIP_TOP_BOTTOM)
    if blur_px > 0.3:
        flipped = flipped.filter(ImageFilter.GaussianBlur(blur_px))
    if tint is not None:
        flipped = ImageChops.multiply(flipped, Image.new("RGB", im.size, tuple(tint)))
    return Image.blend(im, flipped, clamp(amount))


# ------------------------------------------------------------------ heat haze
def heat_haze(im: Image.Image, t: float, strength: float, S: float, seed: float = 0.0):
    if strength <= 0.02:
        return im
    W, H = im.size
    f = 4
    sw, sh = max(16, W // f), max(16, H // f)
    small = im.resize((sw, sh), Image.BILINEAR)
    a = np.asarray(small).astype(np.float32)
    yy = np.arange(sh, dtype=np.float32)
    xx = np.arange(sw, dtype=np.float32)
    amp = (0.9 + 1.5 * strength) * max(0.6, S) * 1.2
    wobble = (np.sin(xx * 0.055 + t * 3.1 + seed) * 0.6
              + np.sin(xx * 0.017 - t * 2.0 + seed * 2.0) * 0.4)
    dy = wobble * amp                     # per column
    sy = yy[:, None] + dy[None, :]
    sy = np.clip(sy, 0, sh - 1.001)
    y0 = sy.astype(np.int32)
    fy = sy - y0
    y1 = np.minimum(y0 + 1, sh - 1)
    out = (a[y0, np.arange(sw)[None, :], :] * (1 - fy[..., None])
           + a[y1, np.arange(sw)[None, :], :] * fy[..., None])
    # haze stronger near the bottom half
    wgt = np.clip((np.linspace(0, 1, sh, dtype=np.float32) - 0.25) / 0.75, 0, 1)[:, None, None]
    src = a * (1 - 0.55 * wgt * strength) + out * (0.55 * wgt * strength + 0.45 * strength)
    warped = Image.fromarray(np.clip(src, 0, 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
    return Image.blend(im, warped, 0.50)


# ------------------------------------------------------- outdoor ground finish
_FOG_CACHE: dict = {}


def _bottom_gradient(W: int, H: int, height_frac: float, max_alpha: float,
                     power: float = 1.6) -> Image.Image:
    key = (W, H, round(height_frac, 3), round(max_alpha, 3), power)
    m = _FOG_CACHE.get(key)
    if m is not None:
        return m
    lw, lh = max(8, (W + 7) // 8), max(8, (H + 7) // 8)
    yy = np.linspace(0.0, 1.0, lh, dtype=np.float32)
    y0 = 1.0 - height_frac
    v = np.clip((yy - y0) / max(1e-4, height_frac), 0, 1) ** power * max_alpha
    col = (v * 255).astype(np.uint8)
    small = Image.fromarray(np.repeat(np.repeat(col[:, None], lw, axis=1), 8, axis=0)[:H, :W])
    m = small.resize((W, H), Image.BILINEAR)
    _FOG_CACHE[key] = m
    return m


def ground_treatment(im: Image.Image, shot, S: float, meta: dict | None = None,
                     group: str = "gold", bottom_std: float | None = None) -> Image.Image:
    """Bottom fog + progressive blur for outdoor field / road shots.

    * field (low-angle flower sea): taller warm fog (0.48 screen) + soft bottom blur
      so the dark stem "forest" melts into haze instead of reading as tree trunks
    * road: lighter 0.30 screen fog, mainly to hide noisy dark asphalt / grass
    * if the foreground is already a clean black bokeh, fog is kept light
    """
    set_name = shot.get("set")
    if set_name not in ("field", "road"):
        return im
    W, H = im.size
    textured = True if bottom_std is None else (bottom_std > 0.030)
    if set_name == "field":
        hfrac = 0.48 if textured else 0.42
        alpha = 0.35 if textured else 0.20
        blur_h, blur_mask_h, blur_max = 0.22, 0.18, 0.78
    else:
        hfrac = 0.30 if textured else 0.34
        alpha = 0.27 if textured else 0.12
        blur_h, blur_mask_h, blur_max = 0.26, 0.21, 0.86
    if group == "violet":
        fog_col = (132, 120, 172)
    elif group == "cold":
        fog_col = (110, 128, 166)
    else:
        fog_col = (198, 158, 112)
    # 1) progressive blur of the bottom
    bh = int(H * blur_h) + 2
    y0 = max(0, H - bh)
    region = im.crop((0, y0, W, H))
    blurred = region.filter(ImageFilter.GaussianBlur(max(2.0, 6.0 * S)))
    mask_b = _bottom_gradient(W, H, blur_mask_h, blur_max, power=1.3).crop((0, y0, W, H))
    im.paste(blurred, (0, y0), mask_b)
    # 2) soft fog rising from the bottom edge
    fh = int(H * hfrac)
    fog = Image.new("RGB", (W, fh), fog_col)
    mask_f = _bottom_gradient(W, H, hfrac, alpha, power=1.10).crop((0, H - fh, W, H))
    im.paste(fog, (0, H - fh), mask_f)
    return im


# ------------------------------------------------------------------ atmosphere
class Atmosphere:
    """Procedural 2.5D overlays, cached per (shot, output size)."""

    def __init__(self):
        self._cfg = {}
        self._petal_sprites = {}
        self._droplet = {}
        self._bokeh = {}
        self._stars = {}

    # -- petal sprites: pre-rendered rounded petals at 12 angles / 4 sizes
    def _petal_sprite(self, r: int, ang_deg: int, col):
        key = (r, ang_deg, col)
        spr = self._petal_sprites.get(key)
        if spr is not None:
            return spr
        s = max(6, int(r * 2.6))
        im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        ang = math.radians(ang_deg)
        dx, dy = math.cos(ang), math.sin(ang)
        px, py = -dy, dx
        cx, cy = s / 2.0, s / 2.0
        L = r
        pts_l, pts_r = [], []
        for i in range(9):
            u = i / 8.0
            prof = math.sin(math.pi * (0.14 + 0.86 * u)) ** 0.55
            w = r * 0.17 * prof          # slender: length/width > 3:1
            x = cx + dx * L * (0.18 + 0.82 * u)
            y = cy + dy * L * (0.18 + 0.82 * u)
            pts_l.append((x + px * w, y + py * w))
            pts_r.append((x - px * w, y - py * w))
        # small notch at the tip (sunflower petal)
        tipx = cx + dx * L * 0.98
        tipy = cy + dy * L * 0.98
        notch = (tipx - dx * L * 0.08, tipy - dy * L * 0.08)
        d.polygon(pts_l + [notch] + pts_r[::-1], fill=tuple(col) + (255,))
        im = im.filter(ImageFilter.GaussianBlur(max(0.4, r * 0.03)))
        if len(self._petal_sprites) > 400:
            self._petal_sprites.clear()
        self._petal_sprites[key] = im
        return im

    def _droplet_sprite(self, s: int):
        spr = self._droplet.get(s)
        if spr is not None:
            return spr
        s = max(8, int(s))
        yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
        c = (s - 1) / 2.0
        dx = (xx - c) / (s * 0.5)
        dy = (yy - c) / (s * 0.5)
        r = np.sqrt(dx * dx + dy * dy)
        rim = np.exp(-((r - 0.76) / 0.10) ** 2) * 0.55
        spec = np.exp(-(((dx + 0.32) / 0.13) ** 2 + ((dy + 0.36) / 0.13) ** 2)) * 0.9
        inner = np.clip(1.0 - r / 0.70, 0, 1) ** 1.6
        rgba = np.zeros((s, s, 4), np.float32)
        rgba[..., 0] = 200
        rgba[..., 1] = 220
        rgba[..., 2] = 255
        rgba[..., 3] = np.clip((rim + spec) * 255.0, 0, 255)
        im = Image.fromarray(rgba.astype(np.uint8), "RGBA")
        # dark body: separate RGBA pass, composited under the bright rim
        da = np.clip(inner * 0.17 * 255.0, 0, 255).astype(np.uint8)
        darr = np.zeros((s, s, 4), np.uint8)
        darr[..., 3] = da
        dark_im = Image.fromarray(darr, "RGBA")
        self._droplet[s] = (im, dark_im)
        return self._droplet[s]

    def _bokeh_sprite(self, r: int, col):
        key = (r, col)
        spr = self._bokeh.get(key)
        if spr is not None:
            return spr
        spr = radial_sprite(max(4, int(r * 2.6)), col, hardness=0.32, falloff=1.8)
        self._bokeh[key] = spr
        return spr

    # -- per shot particle config
    def cfg(self, shot):
        sid = shot["id"]
        c = self._cfg.get(sid)
        if c is not None:
            return c
        P = atmos_params(shot["variant"])
        O = optics_params(shot["variant"])
        rnd = random.Random(int(hash01("atmos", sid) * 1e9))
        cfg = dict(params=P, rain=[], petals=[], dust=[], bokeh=[], stars=[],
                   drops=[], ripples=[])
        # rain: 3 layers
        n_rain = int(170 * P["rain"])
        for i in range(n_rain):
            layer = i % 3
            cfg["rain"].append(dict(
                x=rnd.uniform(-0.15, 1.15), y=rnd.uniform(-0.1, 1.1),
                spd=rnd.uniform(1.0, 2.0) * (0.55 + 0.35 * layer),
                ln=rnd.uniform(0.012, 0.05) * (0.7 + 0.45 * layer),
                slant=rnd.uniform(0.05, 0.22),
                a=rnd.uniform(0.05, 0.20) * (0.6 + 0.4 * (2 - layer) / 2),
                w=1 + (layer == 2)))
        # petals: slender, mid/background only (never big blobs in the foreground)
        n_pet = int(54 * P["petals"])
        violet_world = "violet" in shot["variant"] or shot["variant"] == "petals_dark" or shot["variant"] == "rain_night"
        cols = ("violet", "violet2") if violet_world else ("gold", "gold2", "white")
        for i in range(n_pet):
            # depth: far petals are smaller, nearer ones slightly larger but still small
            depth = rnd.random()
            y0 = rnd.uniform(-0.06, 0.78) if depth < 0.75 else rnd.uniform(-0.06, 0.55)
            size_i = 0 if depth < 0.35 else (1 if depth < 0.68 else (2 if depth < 0.9 else 3))
            a = rnd.uniform(0.35, 0.70) * (0.75 + 0.25 * (1 - depth))
            cfg["petals"].append(dict(
                x=rnd.uniform(-0.08, 1.08), y=y0,
                vx=rnd.uniform(-0.010, 0.018), vy=rnd.uniform(0.010, 0.038) * (-1 if P["rising"] else 1),
                sway=rnd.uniform(0.008, 0.035), w=rnd.uniform(0.4, 1.2),
                ph=rnd.uniform(0, 6.28), size=size_i, depth=depth,
                rot=rnd.uniform(0, 360), spin=rnd.uniform(-26, 26),
                col=cols[rnd.randrange(len(cols))], a=a))
        # dust motes
        n_dust = int(90 * P["dust"])
        for i in range(n_dust):
            cfg["dust"].append(dict(
                x=rnd.uniform(0, 1), y=rnd.uniform(0, 1), r=rnd.uniform(0.6, 2.4),
                ph=rnd.uniform(0, 6.28), spd=rnd.uniform(0.2, 0.7),
                a=rnd.uniform(0.10, 0.5)))
        # bokeh
        n_bok = int(18 * P["bokeh"])
        for i in range(n_bok):
            cfg["bokeh"].append(dict(
                x=rnd.uniform(0, 1), y=rnd.uniform(0.05, 0.95),
                r=rnd.uniform(4, 26), a=rnd.uniform(0.05, 0.22),
                ph=rnd.uniform(0, 6.28), drift=rnd.uniform(0.002, 0.01),
                col=(O["leak_tint"] if rnd.random() < 0.6 else (190, 210, 255))))
        # stars
        n_st = int(110 * P["stars"])
        for i in range(n_st):
            cfg["stars"].append(dict(x=rnd.uniform(0, 1), y=rnd.uniform(0, 0.75),
                                     r=rnd.uniform(0.5, 1.8), a=rnd.uniform(0.15, 0.7),
                                     ph=rnd.uniform(0, 6.28)))
        # drops
        n_dr = int(13 * P["drops"])
        for i in range(n_dr):
            cfg["drops"].append(dict(x=rnd.uniform(0.03, 0.97), y=rnd.uniform(0.03, 0.97),
                                     r=rnd.uniform(4, 19), ph=rnd.uniform(0, 6.28),
                                     slide=rnd.uniform(0.0008, 0.004), a=rnd.uniform(0.25, 0.7)))
        # ripples (puddle positions)
        n_rip = int(7 * P["ripples"])
        for i in range(n_rip):
            cfg["ripples"].append(dict(x=rnd.uniform(0.15, 0.85), y=rnd.uniform(0.66, 0.96),
                                       ph=rnd.uniform(0, 6.28), spd=rnd.uniform(0.18, 0.42),
                                       rx=rnd.uniform(0.04, 0.15), a=rnd.uniform(0.10, 0.28)))
        self._cfg[sid] = cfg
        return cfg

    def layer(self, shot, t: float, W: int, H: int, S: float, meta: dict | None = None):
        """Return an RGBA overlay at (W, H) or None."""
        cfg = self.cfg(shot)
        P = cfg["params"]
        if not any((P["rain"], P["petals"], P["dust"], P["bokeh"], P["stars"], P["drops"], P["ripples"])):
            return None
        dw = min(W, 1216)
        dh = int(round(H * dw / float(W)))
        f = W / float(dw)
        Sd = S / f
        w, h = dw, dh
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        seed = hash01(shot["id"]) * 100.0
        # ---- rain
        if P["rain"] > 0.02:
            for r in cfg["rain"]:
                y = (r["y"] + r["spd"] * t * 0.55) % 1.20 - 0.10
                x = (r["x"] + (y - r["y"]) * r["slant"] + 0.02 * math.sin(t * 0.7 + seed)) % 1.20 - 0.10
                ln = r["ln"]
                a = int(255 * r["a"])
                d.line([(x * w, y * h), (x * w + r["slant"] * ln * w, (y + ln) * h)],
                       fill=(200, 214, 245, a), width=r["w"])
        # ---- ripples (puddle rings)
        for rp in cfg["ripples"]:
            phase = (t * rp["spd"] + rp["ph"] / 6.28) % 1.0
            rr = phase * rp["rx"] * W
            a = int(255 * rp["a"] * (1.0 - phase) ** 1.4)
            if rr > 1 and a > 2:
                cx, cy = rp["x"] * w, rp["y"] * h
                d.ellipse([cx - rr, cy - rr * 0.18, cx + rr, cy + rr * 0.18],
                          outline=(210, 225, 255, a), width=max(1, int(S * 1.2)))
        # ---- petals: slender, mid/background, rotated, motion-blurred 3-6px
        if P["petals"] > 0.02:
            sizes = [int(v * max(0.50, Sd)) for v in (8, 11, 15, 21)]
            for pt in cfg["petals"]:
                yy = (pt["y"] + pt["vy"] * t) % 1.15 - 0.075
                xx = (pt["x"] + pt["vx"] * t + pt["sway"] * math.sin(t * pt["w"] + pt["ph"])) % 1.15 - 0.075
                ang = (pt["rot"] + pt["spin"] * t) % 360
                spr = self._petal_sprite(sizes[pt["size"]], int(ang / 15) * 15,
                                         PETAL_COLORS[pt["col"]])
                a = pt["a"] * (0.72 + 0.28 * math.sin(t * 1.3 + pt["ph"]))
                px, py = xx * w, yy * h
                if -50 < px < w + 50 and -50 < py < h + 50 and a > 0.01:
                    alpha0 = spr.getchannel("A")
                    # motion blur along the velocity vector (3-6 px at 1080p)
                    vx_px = pt["vx"] * w + 0.002 * math.cos(t * pt["w"] + pt["ph"])
                    vy_px = pt["vy"] * h
                    vn = math.hypot(vx_px, vy_px) + 1e-6
                    trail = (3.0 + 3.0 * pt["depth"]) * max(0.55, Sd)
                    ux, uy = vx_px / vn, vy_px / vn
                    for k, aa in ((2, 0.16), (1, 0.36), (0, 1.0)):
                        ox = -ux * trail * k / 2.0
                        oy = -uy * trail * k / 2.0
                        a_scaled = alpha_scale(alpha0, clamp(a * aa, 0.0, 0.74))
                        layer.paste(spr, (int(px - spr.width / 2 + ox),
                                          int(py - spr.height / 2 + oy)),
                                    a_scaled)
        # ---- dust motes
        for du in cfg["dust"]:
            yy = (du["y"] + du["spd"] * t * 0.012) % 1.0
            xx = (du["x"] + 0.008 * math.sin(t * 0.4 * du["spd"] + du["ph"])) % 1.0
            r = du["r"] * max(0.6, Sd)
            a = int(255 * du["a"] * (0.6 + 0.4 * math.sin(t * 2.0 + du["ph"])))
            if r < 1.2:
                d.point((xx * w, yy * h), fill=(255, 246, 226, a))
            else:
                d.ellipse([xx * w - r, yy * h - r, xx * w + r, yy * h + r],
                          fill=(255, 244, 224, a))
        # ---- lens droplets
        if P["drops"] > 0.02:
            for dr in cfg["drops"]:
                yy = (dr["y"] + dr["slide"] * t * 10) % 1.0
                xx = dr["x"] + 0.004 * math.sin(t * 0.5 + dr["ph"])
                s = int(dr["r"] * max(0.6, Sd))
                if s < 4:
                    continue
                bright, dark = self._droplet_sprite(s)
                px, py = int(xx * w - s / 2), int(yy * h - s / 2)
                if -s < px < w and -s < py < h:
                    layer.paste(dark, (px, py), dark)
                    layer.paste(bright, (px, py), bright)
        # ---- bokeh
        for bk in cfg["bokeh"]:
            xx = bk["x"] + bk["drift"] * math.sin(t * 0.15 + bk["ph"])
            yy = bk["y"] + 0.004 * math.cos(t * 0.11 + bk["ph"])
            r = int(bk["r"] * max(0.6, Sd))
            a = int(255 * bk["a"] * (0.75 + 0.25 * math.sin(t * 0.9 + bk["ph"])))
            spr = self._bokeh_sprite(r, tuple(int(c) for c in bk["col"]))
            spr = spr.copy()
            spr.putalpha(spr.getchannel("A").point(lambda v, a=a: v * a // 255))
            layer.paste(spr, (int(xx * w - spr.width / 2), int(yy * h - spr.height / 2)), spr)
        # ---- stars
        for st in cfg["stars"]:
            a = int(255 * st["a"] * (0.55 + 0.45 * math.sin(t * 1.7 + st["ph"])))
            r = st["r"] * max(0.55, Sd)
            d.ellipse([st["x"] * w - r, st["y"] * h - r, st["x"] * w + r, st["y"] * h + r],
                      fill=(225, 232, 255, a))
        layer = layer.filter(ImageFilter.GaussianBlur(max(0.35, 0.40 * Sd)))
        if (w, h) != (W, H):
            layer = layer.resize((W, H), Image.BILINEAR)
        return layer


# ------------------------------------------------------------------ lens / grain
_VIG_CACHE: dict = {}

# sky tinting: multiplied per channel at <=1.0 so it can only push colours, and
# the exposure match in the compositor compensates for the slight darkening.
SKY_TINT = {
    "gold":   dict(top=(0.965, 1.030, 1.075), hor=(1.000, 0.930, 0.790)),
    "violet": dict(top=(1.010, 0.955, 1.100), hor=(1.030, 0.930, 0.960)),
    "cold":   dict(top=(0.960, 1.000, 1.090), hor=(1.000, 0.975, 1.020)),
    "neutral": dict(top=(0.985, 1.000, 1.045), hor=(1.000, 0.975, 0.970)),
}


def apply_vignette(im: Image.Image, variant: str, S: float, set_name: str = "",
                   group: str = "") -> Image.Image:
    P = optics_params(variant)
    W, H = im.size
    if not group:
        group = "gold"
    sky = set_name in ("field", "road")
    key = (W, H, variant, round(P["vig"], 3), set_name, group)
    mask = _VIG_CACHE.get(key)
    if mask is None:
        sw, sh = max(32, (W + 7) // 8), max(32, (H + 7) // 8)
        yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
        nx = (xx / (sw - 1) - 0.5) * 2.0
        ny = (yy / (sh - 1) - 0.5) * 2.0
        r = np.sqrt(nx * nx + ny * ny) / math.sqrt(2.0)
        v = 1.0 - P["vig"] * (r ** 2.2)
        m = np.repeat(np.clip(v, 0, 1)[..., None], 3, axis=2)
        if sky:
            t = SKY_TINT.get(group, SKY_TINT["gold"])
            yyf = (np.arange(sh, dtype=np.float32) / max(1, sh - 1))[:, None]
            horizon = 0.56
            # 1 at top, 0 at horizon (smooth), sky tint fades out under horizon
            w = np.clip(1.0 - (yyf - 0.08) / max(0.05, horizon - 0.08), 0, 1) ** 1.4
            top = np.array(t["top"], np.float32)
            hor = np.array(t["hor"], np.float32)
            u = np.clip((yyf - 0.10) / max(0.05, horizon - 0.10), 0, 1)
            grad = top[None, None, :] * (1 - u[..., None]) + hor[None, None, :] * u[..., None]
            grad = grad * np.ones((1, sw, 1), np.float32)
            m = m * (1.0 + w[..., None] * (grad - 1.0))
        mm = np.clip(m * 255.0, 0, 255).astype(np.uint8)
        mm = np.repeat(np.repeat(mm, 8, axis=0), 8, axis=1)[:H, :W]
        mask = Image.fromarray(mm, "RGB")
        _VIG_CACHE[key] = mask
    return ImageChops.multiply(im, mask)


class Grain:
    """Temporally coherent grain: cross-faded banks of fine noise.

    Banks are generated at half resolution (so grain reads as soft 2px film
    grain rather than digital pixel noise) and kept at output size for speed.
    """

    NBANKS = 4

    def __init__(self):
        self._banks = {}

    def _bank(self, W, H, k):
        key = (W, H, k)
        b = self._banks.get(key)
        if b is not None:
            return b
        hw, hh = max(8, W // 2), max(8, H // 2)
        rng = np.random.default_rng(1000 + k * 77 + W * 3 + H)
        base = rng.normal(0.0, 1.0, (hh, hw)).astype(np.float32)
        chroma = rng.normal(0.0, 0.32, (hh, hw, 3)).astype(np.float32)
        n = base[..., None] * 0.86 + chroma
        n = np.clip(128.0 + n * 30.0, 0, 255).astype(np.uint8)
        arr = np.repeat(n, 3, axis=2) if n.shape[2] == 1 else n
        small = Image.fromarray(arr, "RGB")
        b = small.resize((W, H), Image.BILINEAR)
        if len(self._banks) > 12:
            self._banks.clear()
        self._banks[key] = b
        return b

    def prewarm(self, W: int, H: int) -> None:
        for k in range(self.NBANKS):
            self._bank(W, H, k)

    def apply(self, im: Image.Image, t: float, strength: float, S: float) -> Image.Image:
        W, H = im.size
        if strength <= 0.001:
            return im
        nb = self.NBANKS
        ph = t * 2.4
        k = int(ph) % nb
        w = smoothstep(ph - int(ph))
        a = self._bank(W, H, k)
        b = self._bank(W, H, (k + 1) % nb)
        g = Image.blend(a, b, w)
        # grain slightly coarser in the shadows: keep simple, uniform blend
        return Image.blend(im, g, clamp(strength * (1.0 + 0.30 * (1.0 / max(0.4, S) - 1.0)), 0.0, 0.22))


class Chromatic:
    """Very light radial chromatic aberration (edge 1-2 px).

    Applied to the chroma channels only, at half resolution; green (sharpness)
    is untouched, which is invisible after 4:2:0 encoding but ~2x faster.
    """

    def apply(self, im: Image.Image, amount_px: float, S: float) -> Image.Image:
        a = amount_px * max(0.35, S)
        if a < 0.25:
            return im
        W, H = im.size
        r, g, b = im.split()
        hw, hh = max(8, W // 2), max(8, H // 2)
        e = a / (W * 0.5) * 2.0 * 1.6
        r_small = r.resize((hw, hh), Image.BILINEAR)
        b_small = b.resize((hw, hh), Image.BILINEAR)

        def scale_channel(ch, s):
            bw = hw / s
            bh = hh / s
            x0 = (hw - bw) / 2.0
            y0 = (hh - bh) / 2.0
            sc = ch.resize((hw, hh), Image.BICUBIC, box=(x0, y0, x0 + bw, y0 + bh))
            return sc.resize((W, H), Image.BILINEAR)

        r2 = scale_channel(r_small, 1.0 + e * 0.35)
        b2 = scale_channel(b_small, 1.0 + e * 1.15)
        return Image.merge("RGB", (r2, g, b2))


# ------------------------------------------------------------------ warps
_GRID_CACHE: dict = {}


def radial_warp(im: Image.Image, cx: float, cy: float, t: float, strength: float,
                S: float, W: int = None, H: int = None) -> Image.Image:
    """Raindrop ripple warp (used by the S19->S20 transition)."""
    W = W or im.size[0]
    H = H or im.size[1]
    f = 2
    sw, sh = W // f, H // f
    small = im.resize((sw, sh), Image.BILINEAR)
    a = np.asarray(small).astype(np.float32)
    gx, gy = _GRID_CACHE.get((sw, sh), (None, None))
    if gx is None:
        gx, gy = np.meshgrid(np.arange(sw, dtype=np.float32), np.arange(sh, dtype=np.float32))
        _GRID_CACHE[(sw, sh)] = (gx, gy)
    dx = gx - cx * sw
    dy = gy - cy * sh
    r = np.sqrt(dx * dx + dy * dy) + 1e-3
    # expanding rings + vortex-ish wobble
    amp = strength * 14.0 * max(0.5, S)
    wave = np.sin(r * 0.16 - t * 9.0) * np.exp(-r / (sw * 0.55))
    sx = gx + (dx / r) * wave * amp
    sy = gy + (dy / r) * wave * amp
    sx = np.clip(sx, 0, sw - 1.001)
    sy = np.clip(sy, 0, sh - 1.001)
    ix = sx.astype(np.int32)
    iy = sy.astype(np.int32)
    fx = (sx - ix)[..., None]
    fy = (sy - iy)[..., None]
    ix1 = np.minimum(ix + 1, sw - 1)
    iy1 = np.minimum(iy + 1, sh - 1)
    c00 = a[iy, ix]
    c10 = a[iy, ix1]
    c01 = a[iy1, ix]
    c11 = a[iy1, ix1]
    out = (c00 * (1 - fx) * (1 - fy) + c10 * fx * (1 - fy)
           + c01 * (1 - fx) * fy + c11 * fx * fy)
    warped = Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
    return warped


def flash_glow(im: Image.Image, amount: float, color=(255, 228, 190), S: float = 1.0) -> Image.Image:
    """Soft additive bloom flash used by light-bleed / white-flash transitions."""
    if amount <= 0.001:
        return im
    W, H = im.size
    sw, sh = max(8, W // 8), max(8, H // 8)
    small = im.resize((sw, sh), Image.BILINEAR)
    a = np.asarray(small).astype(np.float32) / 255.0
    lum = a[..., 0] * 0.299 + a[..., 1] * 0.587 + a[..., 2] * 0.114
    hot = np.clip((lum - 0.35) / 0.65, 0, 1)[..., None] ** 1.2
    glow = np.asarray(_to_u8(a * hot * 255.0).filter(ImageFilter.GaussianBlur(6))).astype(np.float32)
    tint = np.array(color, np.float32)
    glow = glow * (np.array([tint[0] / 255.0, tint[1] / 255.0, tint[2] / 255.0])[None, None, :])
    glow_img = Image.fromarray(np.clip(glow, 0, 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
    white = Image.new("RGB", (W, H), tuple(int(c * amount) for c in color))
    out = ImageChops.screen(im, glow_img)
    return Image.blend(out, white, clamp(amount * 0.55))


def petals_dark_overlay(im: Image.Image, t: float, W: int, H: int, S: float) -> Image.Image:
    return im
