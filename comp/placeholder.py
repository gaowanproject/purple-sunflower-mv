# -*- coding: utf-8 -*-
"""placeholder.py — procedural "dummy plates" so the whole pipeline can be
built, graded and cut before the 3D renders arrive.

Each shot gets one 1.2x oversized canvas (2266x1272) cached to disk; the
compositor then makes the actual 1920x1080 frame from a moving crop of that
canvas (synthetic camera move).  These images are *not* final art — they
exist to validate typography, grade, optics and edit rhythm.
"""
from __future__ import annotations

import json
import math
import os
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from common import (CACHE_DIR, DUMMY_DIR, FONT_DIR, ROOT, clamp, hash01,
                    load_json, save_json)

CANVAS_SCALE = 1.20
SUN = {}   # shot_id -> (x, y) normalised position of the light source
META_PATH = os.path.join(DUMMY_DIR, "meta.json")

# --------------------------------------------------------------------- palettes
# keys: sky_top, sky_mid, sky_hor, sun, glow, ground_far, ground_near,
#       silhouette, bokeh, accent, haze
PALETTES = {
    "noon_hot": dict(sky_top=(96, 158, 216), sky_mid=(176, 202, 214), sky_hor=(255, 238, 202),
                     sun=(255, 253, 240), glow=(255, 231, 176), ground_far=(226, 190, 112),
                     ground_near=(146, 114, 58), silhouette=(72, 50, 28),
                     bokeh=(255, 214, 148), accent=(255, 186, 86), haze=(255, 238, 208)),
    "noon_side": dict(sky_top=(112, 166, 212), sky_mid=(196, 208, 208), sky_hor=(255, 234, 198),
                      sun=(255, 247, 222), glow=(255, 226, 176), ground_far=(208, 174, 106),
                      ground_near=(124, 96, 56), silhouette=(62, 44, 28),
                      bokeh=(255, 222, 162), accent=(255, 194, 100), haze=(255, 236, 206)),
    "gold_noon": dict(sky_top=(128, 184, 206), sky_mid=(228, 214, 180), sky_hor=(255, 232, 172),
                      sun=(255, 250, 228), glow=(255, 228, 160), ground_far=(234, 194, 106),
                      ground_near=(154, 118, 56), silhouette=(88, 62, 32),
                      bokeh=(255, 220, 150), accent=(255, 190, 88), haze=(255, 238, 196)),
    "gold_dusk": dict(sky_top=(84, 80, 138), sky_mid=(198, 148, 150), sky_hor=(255, 186, 116),
                      sun=(255, 220, 156), glow=(255, 190, 118), ground_far=(180, 134, 66),
                      ground_near=(88, 64, 40), silhouette=(48, 34, 26),
                      bokeh=(255, 196, 138), accent=(255, 160, 80), haze=(255, 204, 160)),
    "violet_dusk": dict(sky_top=(44, 40, 92), sky_mid=(104, 74, 138), sky_hor=(206, 130, 170),
                        sun=(238, 158, 196), glow=(198, 120, 176), ground_far=(92, 66, 110),
                        ground_near=(40, 30, 58), silhouette=(24, 18, 36),
                        bokeh=(220, 150, 230), accent=(190, 120, 220), haze=(150, 110, 170)),
    "violet_night": dict(sky_top=(8, 8, 30), sky_mid=(28, 24, 66), sky_hor=(84, 62, 128),
                         sun=(206, 212, 255), glow=(122, 108, 200), ground_far=(34, 30, 70),
                         ground_near=(14, 12, 32), silhouette=(6, 6, 16),
                         bokeh=(150, 160, 255), accent=(186, 146, 255), haze=(90, 80, 150)),
    "dusk_afterglow": dict(sky_top=(88, 88, 138), sky_mid=(188, 140, 136), sky_hor=(255, 168, 96),
                           sun=(255, 200, 132), glow=(255, 168, 104), ground_far=(172, 128, 72),
                           ground_near=(82, 60, 42), silhouette=(52, 38, 26),
                           bokeh=(255, 190, 140), accent=(255, 150, 90), haze=(240, 190, 160)),
    "night_rain": dict(sky_top=(10, 14, 30), sky_mid=(22, 30, 54), sky_hor=(38, 48, 78),
                       sun=(150, 170, 220), glow=(60, 78, 120), ground_far=(26, 32, 52),
                       ground_near=(12, 15, 28), silhouette=(5, 7, 14),
                       bokeh=(140, 168, 240), accent=(255, 188, 122), haze=(70, 86, 128)),
    "rain_night": dict(sky_top=(8, 11, 26), sky_mid=(18, 24, 46), sky_hor=(30, 38, 64),
                       sun=(255, 120, 160), glow=(120, 60, 110), ground_far=(24, 26, 44),
                       ground_near=(8, 10, 20), silhouette=(4, 5, 12),
                       bokeh=(120, 200, 255), accent=(255, 96, 150), haze=(60, 70, 110)),
    "night_dark": dict(sky_top=(4, 5, 10), sky_mid=(8, 10, 18), sky_hor=(14, 17, 28),
                       sun=(190, 200, 230), glow=(40, 50, 80), ground_far=(12, 14, 22),
                       ground_near=(5, 6, 10), silhouette=(2, 3, 6),
                       bokeh=(90, 110, 160), accent=(150, 140, 120), haze=(40, 48, 70)),
    "night_lamp": dict(sky_top=(16, 13, 15), sky_mid=(26, 21, 22), sky_hor=(34, 28, 28),
                       sun=(255, 186, 108), glow=(190, 120, 60), ground_far=(40, 32, 30),
                       ground_near=(20, 16, 16), silhouette=(8, 7, 8),
                       bokeh=(255, 190, 120), accent=(86, 110, 156), haze=(120, 90, 70)),
    "macro_cold": dict(sky_top=(12, 26, 42), sky_mid=(26, 46, 68), sky_hor=(44, 72, 98),
                       sun=(190, 226, 255), glow=(70, 120, 170), ground_far=(30, 54, 74),
                       ground_near=(14, 26, 40), silhouette=(6, 12, 20),
                       bokeh=(160, 210, 255), accent=(110, 170, 230), haze=(70, 110, 150)),
    "macro_warm": dict(sky_top=(44, 30, 22), sky_mid=(72, 48, 34), sky_hor=(96, 64, 40),
                       sun=(255, 220, 168), glow=(200, 130, 70), ground_far=(88, 60, 40),
                       ground_near=(40, 26, 18), silhouette=(18, 12, 8),
                       bokeh=(255, 210, 160), accent=(255, 170, 100), haze=(150, 110, 80)),
    "city_bridge": dict(sky_top=(6, 9, 14), sky_mid=(12, 18, 26), sky_hor=(22, 30, 40),
                        sun=(255, 226, 180), glow=(90, 100, 120), ground_far=(18, 24, 32),
                        ground_near=(8, 10, 14), silhouette=(3, 4, 7),
                        bokeh=(180, 200, 230), accent=(255, 190, 130), haze=(50, 60, 80)),
    "petals_dark": dict(sky_top=(8, 6, 14), sky_mid=(16, 12, 26), sky_hor=(34, 22, 52),
                        sun=(200, 160, 255), glow=(90, 50, 150), ground_far=(26, 18, 44),
                        ground_near=(9, 7, 16), silhouette=(3, 2, 6),
                        bokeh=(170, 120, 255), accent=(200, 150, 255), haze=(60, 40, 100)),
}


def _pal(variant: str) -> dict:
    return PALETTES.get(variant, PALETTES["gold_noon"])


# ------------------------------------------------------------------- primitives
def _vert_gradient(W, H, stops) -> np.ndarray:
    ys = np.linspace(0.0, 1.0, H, dtype=np.float32)
    cols = np.zeros((H, 3), np.float32)
    for c in range(3):
        cols[:, c] = np.interp(ys, [s[0] for s in stops], [s[1][c] for s in stops])
    return np.repeat(cols[:, None, :], W, axis=1)


def _glow_arr(W, H, cx, cy, rx, ry, color, strength, falloff=2.0, core=0.0):
    """Additive radial glow returned as float array (low-res, then upscaled)."""
    gw, gh = max(8, W // 8), max(8, H // 8)
    y, x = np.mgrid[0:gh, 0:gw].astype(np.float32)
    dx = (x + 0.5) / gw * W - cx
    dy = (y + 0.5) / gh * H - cy
    r = np.sqrt((dx / max(1.0, rx)) ** 2 + (dy / max(1.0, ry)) ** 2)
    v = np.clip(1.0 - r, 0.0, 1.0) ** falloff
    if core > 0.0:
        v = v + core * np.clip(1.0 - r * 1.6, 0.0, 1.0) ** (falloff * 0.5)
    v = np.clip(v, 0, 1) * strength
    small = np.zeros((gh, gw, 3), np.float32)
    for c in range(3):
        small[..., c] = v * color[c]
    im = Image.fromarray(np.clip(small, 0, 255).astype(np.uint8))
    im = im.resize((W, H), Image.BICUBIC)
    return np.asarray(im).astype(np.float32)


def _noise(W, H, cell, octaves=3, seed=0) -> np.ndarray:
    """Smooth 2-D noise field 0..1 (uint8 pyramid upscaled with bicubic)."""
    rng = np.random.default_rng(seed)
    acc = np.zeros((H, W), np.float32)
    amp = 1.0
    tot = 0.0
    for o in range(octaves):
        c = max(2, int(cell / (2 ** o)))
        gw = max(2, W // c)
        gh = max(2, H // c)
        grid = rng.random((gh, gw)).astype(np.float32)
        g = Image.fromarray((grid * 255).astype(np.uint8)).resize((W, H), Image.BICUBIC)
        acc += np.asarray(g).astype(np.float32) / 255.0 * amp
        tot += amp
        amp *= 0.5
    acc /= max(1e-6, tot)
    return acc


def _rgba(W, H):
    return Image.new("RGBA", (W, H), (0, 0, 0, 0))


def _comp(base: Image.Image, layer: Image.Image, blur_r=0.0) -> Image.Image:
    if layer is None:
        return base
    if blur_r > 0:
        layer = layer.filter(ImageFilter.GaussianBlur(blur_r))
    return Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")


def _add_rgb(base: np.ndarray, add: np.ndarray) -> np.ndarray:
    return base + add


def _petal_pts(cx, cy, ang, length, width, npts=11):
    """Rounded petal polygon (teardrop profile, both sides mirrored)."""
    dx, dy = math.cos(ang), math.sin(ang)
    px, py = -dy, dx
    left, right = [], []
    for i in range(npts + 1):
        u = i / float(npts)
        prof = math.sin(math.pi * (0.18 + 0.82 * u)) ** 0.65
        w = width * 0.5 * prof
        x = cx + dx * length * (0.14 + 0.86 * u)
        y = cy + dy * length * (0.14 + 0.86 * u)
        left.append((x + px * w, y + py * w))
        right.append((x - px * w, y - py * w))
    return left + right[::-1]


def _draw_flower(d: ImageDraw.ImageDraw, cx, cy, r, petal_col, center_col,
                 rim_col=None, n=17, rot=0.0, petal_w=0.44, inner=True):
    if rim_col is not None:
        for k in range(n):
            a = rot + 2 * math.pi * k / n
            d.polygon(_petal_pts(cx, cy, a, r * 1.06, r * petal_w * 1.30),
                      fill=rim_col)
    for k in range(n):
        a = rot + 2 * math.pi * k / n
        d.polygon(_petal_pts(cx, cy, a, r, r * petal_w), fill=petal_col)
    if inner:
        for k in range(max(7, n * 2 // 3)):
            a = rot + 0.32 + 2 * math.pi * k / max(7, n * 2 // 3)
            d.polygon(_petal_pts(cx, cy, a, r * 0.66, r * petal_w * 0.85),
                      fill=tuple(max(0, int(c * 0.88)) for c in petal_col[:3]) + ((petal_col[3] if len(petal_col) > 3 else 255),))
    rr = r * 0.30
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=center_col)
    r2 = r * 0.17
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2],
              fill=tuple(min(255, int(c * 1.18)) for c in center_col[:3]) + (255,))


def _draw_person(d, x, foot_y, h, col, lean=0.0, arm_raise=0.0, facing=0):
    """Simple but readable silhouette: head, torso, legs, arms."""
    head_r = h * 0.072
    hip_y = foot_y - h * 0.48
    sho_y = foot_y - h * 0.80
    cx = x
    head_cx = cx + lean * h * 0.10
    head_cy = foot_y - h + head_r
    d.ellipse([head_cx - head_r, head_cy - head_r, head_cx + head_r, head_cy + head_r], fill=col)
    d.line([(head_cx, head_cy + head_r * 0.7), (cx, sho_y)], fill=col, width=max(2, int(h * 0.05)))
    # torso
    d.polygon([(cx - h * 0.075, sho_y), (cx + h * 0.075, sho_y),
               (cx + h * 0.055, hip_y), (cx - h * 0.055, hip_y)], fill=col)
    # legs
    d.line([(cx, hip_y), (cx - h * 0.06, foot_y)], fill=col, width=max(2, int(h * 0.05)))
    d.line([(cx, hip_y), (cx + h * 0.075, foot_y)], fill=col, width=max(2, int(h * 0.05)))
    # arms
    d.line([(cx - h * 0.06, sho_y + h * 0.02), (cx - h * 0.13, sho_y + h * 0.22 + arm_raise * h * 0.2)],
           fill=col, width=max(2, int(h * 0.038)))
    ax = cx + h * 0.06
    d.line([(ax, sho_y + h * 0.02), (ax + h * (0.10 + facing * 0.05), sho_y + h * 0.20 - arm_raise * h * 0.3)],
           fill=col, width=max(2, int(h * 0.038)))


def _draw_sunflower_field(base: Image.Image, W, H, pal, seed, n_layers=3,
                          horizon=0.58, hero_violet=False, figures=0, sun_xy=(0.62, 0.42),
                          macro=False, haze_strength=1.0) -> Image.Image:
    rng = random.Random(seed)
    base_rgb = np.asarray(base).astype(np.float32)
    ys = np.linspace(0, 1, H, dtype=np.float32)
    # --- sun glow + horizon haze + clouds
    sx, sy = sun_xy
    base_rgb += _glow_arr(W, H, sx * W, sy * H, W * 0.34, W * 0.34, pal["glow"], 0.50,
                          falloff=2.2, core=0.85)
    base_rgb += _glow_arr(W, H, sx * W, sy * H, W * 0.055, W * 0.055, pal["sun"], 0.95,
                          falloff=1.4, core=0.7)
    band = np.exp(-((ys - horizon) / 0.05) ** 2)[:, None, None]
    base_rgb += band * np.array(pal["haze"], np.float32)[None, None, :] * 0.32 * haze_strength
    n = _noise(W, H, 90, 3, seed + 11)
    cw = np.clip((n - 0.46) * 2.4, 0, 1) * np.clip(1.0 - np.abs(ys - 0.20) / 0.32, 0, 1)[:, None]
    cloud_col = np.array(pal["glow"], np.float32) * 0.50 + 66
    base_rgb += cw[..., None] * cloud_col[None, None, :] * 0.50
    base = Image.fromarray(np.clip(base_rgb, 0, 255).astype(np.uint8))

    # --- ground plane: gradient + texture
    g0 = np.array(pal["ground_far"], np.float32)
    g1 = np.array(pal["ground_near"], np.float32)
    u = np.clip((ys - horizon) / max(0.01, 1.0 - horizon), 0, 1)[:, None]
    ground_rgb = g0[None, :] * (1 - u) + g1[None, :] * u
    ground_np = np.repeat(ground_rgb[:, None, :], W, axis=1)
    tex = _noise(W, H, 26, 3, seed + 5)
    ground_np *= (0.86 + 0.30 * tex)[..., None]
    ground_img = Image.fromarray(np.clip(ground_np, 0, 255).astype(np.uint8))
    gm = (np.clip((ys - horizon) * 260, 0, 1)[:, None] * np.ones((1, W)) * 255).astype(np.uint8)
    base = Image.composite(ground_img, base, Image.fromarray(gm))
    # --- distant hills
    hills = _rgba(W, H)
    hd = ImageDraw.Draw(hills)
    pts = [(0, H)]
    for i in range(0, 21):
        x = W * i / 20.0
        y = (horizon + 0.004 + 0.011 * math.sin(i * 1.7 + seed)) * H
        pts.append((x, y))
    pts.append((W, H))
    hd.polygon(pts, fill=tuple(int(c * 0.78) for c in pal["ground_far"]) + (255,))
    base = _comp(base, hills, 1.4)

    # --- sunflower layers (far -> near); backlit silhouettes with a warm rim
    if not macro:
        for li in range(n_layers):
            depth = li / max(1, n_layers - 1)          # 0 far .. 1 near
            ly = horizon + (0.010 + 0.26 * (depth ** 1.5)) * (1 - horizon)
            hh0 = lerp_num(0.020, 0.072, depth ** 1.1) * H
            layer = _rgba(W, H)
            ld = ImageDraw.Draw(layer)
            col = blend_col(pal["ground_near"], pal["silhouette"], 0.30 + 0.58 * depth)
            rim = blend_col(pal["sun"], pal["ground_far"], 0.28)
            nflowers = int(16 + 16 * depth)
            for fi in range(nflowers):
                fx = (fi + rng.uniform(-0.4, 0.4)) / nflowers
                if fx < -0.04 or fx > 1.04:
                    continue
                cx = fx * W
                hh = hh0 * rng.uniform(0.72, 1.30)
                ground_y = (ly + rng.uniform(-0.018, 0.045)) * H
                bend = rng.uniform(-0.10, 0.10) * hh
                ld.line([(cx, ground_y), (cx + bend, ground_y - hh)], fill=col + (255,),
                        width=max(2, int(hh * 0.055)))
                for lf in range(2):
                    ly2 = ground_y - hh * (0.30 + 0.22 * lf)
                    s = 1 if lf % 2 == 0 else -1
                    ld.polygon([(cx + bend * 0.5, ly2),
                                (cx + s * hh * 0.26, ly2 - hh * 0.06),
                                (cx + s * hh * 0.30, ly2 + hh * 0.04)],
                               fill=col + (255,))
                _draw_flower(ld, cx + bend, ground_y - hh, hh * 0.40,
                             col + (255,), tuple(int(c * 0.72) for c in col) + (255,),
                             rim_col=rim + (255,), n=17, rot=rng.uniform(0, 1.0),
                             petal_w=0.42)
            base = _comp(base, layer, blur_r=2.4 * (1 - depth) + 0.35)
        # out-of-focus foreground heads at the bottom corners (depth cue)
        for (fx, fy, rr, bl) in ((rng.uniform(-0.02, 0.10), 0.99, 0.16, 9),
                                 (rng.uniform(0.90, 1.02), 1.01, 0.18, 12)):
            layer = _rgba(W, H)
            ld = ImageDraw.Draw(layer)
            col = blend_col(pal["ground_near"], pal["silhouette"], 0.75)
            _draw_flower(ld, fx * W, fy * H, rr * W, col + (255,),
                         tuple(int(c * 0.6) for c in col) + (255,), n=18,
                         rot=rng.uniform(0, 1), petal_w=0.40)
            base = _comp(base, layer, blur_r=bl)
    else:
        # macro: one or two huge flower heads with depth of field
        for li, (fx, fy, rr, bl) in enumerate(((0.50, 0.86, 0.30, 3.0),
                                               (0.16, 1.05, 0.34, 9.0))):
            layer = _rgba(W, H)
            ld = ImageDraw.Draw(layer)
            col = blend_col(pal["ground_near"], pal["silhouette"], 0.55 - 0.1 * li)
            _draw_flower(ld, W * fx, H * fy, W * rr, col + (255,),
                         tuple(int(c * 0.55) for c in col) + (255,),
                         rim_col=blend_col(pal["sun"], pal["accent"], 0.35) + (255,),
                         n=21, rot=rng.uniform(0, 1), petal_w=0.36)
            base = _comp(base, layer, blur_r=bl)

    # violet hero sunflower (foreground focus) for the "violet sunflower" shots
    if hero_violet:
        layer = _rgba(W, H)
        ld = ImageDraw.Draw(layer)
        cx, cy = W * 0.50, H * 0.58
        r = W * 0.235
        petal = (84, 56, 138)
        center = (30, 19, 46)
        rim = (196, 158, 255)
        _draw_flower(ld, cx, cy, r, petal + (255,), center + (255,), rim_col=rim + (255,),
                     n=23, rot=0.2, petal_w=0.36)
        layer = layer.filter(ImageFilter.GaussianBlur(1.0))
        base = _comp(base, layer, 0.0)
        garr = np.asarray(base).astype(np.float32)
        garr += _glow_arr(W, H, cx, cy, r * 0.7, r * 0.7, (110, 80, 190), 0.20, falloff=2.0)
        garr += _glow_arr(W, H, cx - r * 0.1, cy - r * 0.1, r * 0.22, r * 0.22, (220, 200, 255), 0.10)
        base = Image.fromarray(np.clip(garr, 0, 255).astype(np.uint8))

    # --- figures (silhouettes with a rim)
    if figures:
        layer = _rgba(W, H)
        ld = ImageDraw.Draw(layer)
        col = pal["silhouette"]
        rim = blend_col(pal["sun"], pal["accent"], 0.25)
        fh = H * 0.125
        positions = [(0.38, 0.66), (0.45, 0.66)] if figures >= 2 else [(0.45, 0.66)]
        rim_layer = _rgba(W, H)
        rd = ImageDraw.Draw(rim_layer)
        for i, (fx, gy) in enumerate(positions):
            _draw_person(rd, fx * W + 4, gy * H + 3, fh, rim + (255,),
                         facing=(1 if i == 0 else -1))
        base = _comp(base, rim_layer.filter(ImageFilter.GaussianBlur(3.0)), 0.0)
        for i, (fx, gy) in enumerate(positions):
            _draw_person(ld, fx * W, gy * H, fh, col + (255,),
                         lean=(-0.02 if i == 0 else 0.02), facing=(1 if i == 0 else -1))
        base = _comp(base, layer, 0.4)
    return base



def lerp_num(a, b, t):
    return a + (b - a) * t


def blend_col(a, b, t):
    t = clamp(t)
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


# ------------------------------------------------------------------------ road
def _scene_road(shot, W, H, pal, seed) -> Image.Image:
    rng = random.Random(seed)
    horizon = 0.52
    sky = _vert_gradient(W, H, [(0.0, pal["sky_top"]), (0.45, pal["sky_mid"]), (horizon, pal["sky_hor"])])
    base = Image.fromarray(np.clip(sky, 0, 255).astype(np.uint8))
    arr = np.asarray(base).astype(np.float32)
    cam = shot.get("camera", "").lower()
    macro = ("macro" in cam) or ("asphalt" in cam and "wide" not in cam)
    sx, sy = 0.62, 0.40
    if "macro" in cam:
        # close-up asphalt with sky glow at the top
        g = _vert_gradient(W, H, [(0.0, pal["sky_hor"]), (0.35, pal["ground_far"]), (1.0, pal["ground_near"])])
        arr = g
        arr += _glow_arr(W, H, W * 0.5, H * 0.1, W * 0.6, H * 0.5, pal["glow"], 0.75, falloff=2.0)
        n = _noise(W, H, 18, 3, seed + 3)
        arr *= (0.72 + 0.55 * n)[..., None]
        base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        layer = _rgba(W, H)
        d = ImageDraw.Draw(layer)
        # bright water sheet / steam
        for k in range(3):
            cx = rng.uniform(0.2, 0.8) * W
            cy = rng.uniform(0.45, 0.8) * H
            rw = rng.uniform(0.15, 0.4) * W
            d.ellipse([cx - rw, cy - rw * 0.25, cx + rw, cy + rw * 0.25],
                      fill=tuple(int(c) for c in pal["sun"]) + (70,))
        base = _comp(base, layer.filter(ImageFilter.GaussianBlur(10)), 0.0)
        sx, sy = 0.5, 0.12
    else:
        sun_y = 0.36 if "noon" in shot["variant"] else 0.44
        arr += _glow_arr(W, H, W * 0.62, H * sun_y, W * 0.4, W * 0.4, pal["glow"], 0.6,
                         falloff=2.0, core=0.8)
        arr += _glow_arr(W, H, W * 0.62, H * sun_y, W * 0.05, W * 0.05, pal["sun"], 0.9, falloff=1.2)
        base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        # ground on both sides of the road
        gy = np.linspace(0, 1, H, dtype=np.float32)
        gg = np.clip((gy - horizon) / (1 - horizon), 0, 1)[:, None]
        gcol = (np.array(pal["ground_far"], np.float32)[None, :] * (1 - gg)
                + np.array(pal["ground_near"], np.float32)[None, :] * gg)
        gimg = np.repeat(gcol[:, None, :], W, axis=1)
        tn = _noise(W, H, 30, 3, seed + 9)
        gimg *= (0.90 + 0.22 * tn)[..., None]
        gmask = (np.clip((gy - horizon) * 260, 0, 1)[:, None] * np.ones((1, W)) * 255).astype(np.uint8)
        base = Image.composite(Image.fromarray(np.clip(gimg, 0, 255).astype(np.uint8)),
                               base, Image.fromarray(gmask))
        # road wedge
        layer = _rgba(W, H)
        d = ImageDraw.Draw(layer)
        vpx, vpy = W * 0.55, H * horizon
        road_col = tuple(max(4, int(c * 0.62)) for c in pal["ground_near"])
        d.polygon([(vpx - W * 0.012, vpy), (vpx + W * 0.012, vpy),
                   (W * 1.10, H), (-W * 0.10, H)], fill=road_col + (255,))
        base = _comp(base, layer, 1.2)
        arr = np.asarray(base).astype(np.float32)
        # lane dashes: centre line with perspective spacing
        layer = _rgba(W, H)
        d2 = ImageDraw.Draw(layer)
        u = 0.02
        while u < 1.0:
            y = vpy + (H - vpy) * (u ** 2.4)
            x = vpx + (W * 0.5 - vpx) * (u ** 1.6)
            ln = 3 + 26 * (u ** 1.7)
            w = max(1, int(1 + 7 * u))
            d2.rectangle([x - w, y, x + w, y + ln],
                         fill=tuple(min(255, int(c * 1.45)) for c in pal["ground_far"]) + (235,))
            u += 0.052 + 0.10 * u
        base = _comp(base, layer.filter(ImageFilter.GaussianBlur(1.1)), 0.0)
        # poles + wires
        layer = _rgba(W, H)
        d = ImageDraw.Draw(layer)
        pole_col = tuple(int(c * 0.85) for c in pal["silhouette"]) + (255,)
        for side, fx in ((-1, 0.16), (-1, 0.30), (1, 0.86), (1, 0.72)):
            x = W * fx
            ph = H * (0.30 + 0.05 * rng.random())
            top = vpy + H * 0.04 - ph
            d.line([(x, vpy + H * 0.02), (x, top)], fill=pole_col, width=max(3, int(W * 0.004)))
            d.line([(x - W * 0.022, top + ph * 0.18), (x + W * 0.022, top + ph * 0.18)],
                   fill=pole_col, width=max(2, int(W * 0.003)))
        base = _comp(base, layer, 0.6)
        # wires (sagging)
        layer = _rgba(W, H)
        d = ImageDraw.Draw(layer)
        for k in range(3):
            y0 = vpy - H * 0.22 + k * H * 0.035
            pts = []
            for i in range(41):
                u = i / 40.0
                x = W * (0.10 + 0.80 * u)
                y = y0 + H * 0.035 * math.sin(math.pi * u) * (0.8 + 0.2 * k)
                pts.append((x, y))
            d.line(pts, fill=tuple(int(c * 0.6) for c in pal["silhouette"]) + (230,), width=2)
        base = _comp(base, layer, 0.4)
        # tiny figure far away
        if "silhouette" in cam or "figure" in cam or "girl" in cam:
            layer = _rgba(W, H)
            d = ImageDraw.Draw(layer)
            _draw_person(d, W * (0.53 + rng.uniform(-0.06, 0.06)), H * (horizon + 0.075),
                         H * 0.075, pal["silhouette"] + (255,))
            base = _comp(base, layer.filter(ImageFilter.GaussianBlur(1.0)), 0.0)
    # bokeh highlights
    layer = _rgba(W, H)
    d = ImageDraw.Draw(layer)
    for _ in range(14):
        r = rng.uniform(0.004, 0.018) * W
        cx, cy = rng.uniform(0, 1) * W, rng.uniform(0.1, 0.75) * H
        col = pal["bokeh"]
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(col) + (60,))
    base = _comp(base, layer.filter(ImageFilter.GaussianBlur(4)), 0.0)
    # horizon haze
    arr = np.asarray(base).astype(np.float32)
    ys = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    arr += np.exp(-((ys - horizon) / 0.035) ** 2) * np.array(pal["haze"], np.float32) * 0.35
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), (sx, sy), horizon


# ------------------------------------------------------------------------ room
def _scene_room(shot, W, H, pal, seed) -> Image.Image:
    rng = random.Random(seed)
    variant = shot["variant"]
    dark = 0.22 if variant != "night_rain" else 0.30
    top = tuple(int(c * dark) for c in pal["sky_top"])
    arr = _vert_gradient(W, H, [(0.0, top), (0.55, (int(34 * dark + 12), int(30 * dark + 10), int(34 * dark + 14))),
                                (1.0, (10, 9, 12))])
    base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    # window opening
    wx0, wx1 = W * 0.46, W * 0.88
    wy0, wy1 = H * 0.10, H * 0.66
    win = _rgba(W, H)
    wd = ImageDraw.Draw(win)
    win_col_top = tuple(min(255, int(c * 1.55 + 14)) for c in pal["sky_mid"])
    win_col_bot = tuple(min(255, int(c * 1.7 + 20)) for c in pal["sky_hor"])
    wd.rectangle([wx0, wy0, wx1, wy1], fill=tuple(win_col_top) + (255,))
    base = _comp(base, win, 0.0)
    # window content: gradient + city bokeh
    wimg = Image.new("RGB", (int(wx1 - wx0), int(wy1 - wy0)))
    warr = _vert_gradient(int(wx1 - wx0), int(wy1 - wy0),
                          [(0.0, win_col_top), (1.0, win_col_bot)])
    wimg = Image.fromarray(np.clip(warr, 0, 255).astype(np.uint8))
    wl = _rgba(wimg.width, wimg.height)
    wld = ImageDraw.Draw(wl)
    for _ in range(110):
        r = rng.uniform(0.002, 0.014) * W
        cx, cy = rng.uniform(0, 1) * wimg.width, rng.uniform(0.1, 1.0) * wimg.height
        col = pal["bokeh"] if rng.random() < 0.6 else pal["accent"]
        a = int(rng.uniform(60, 210))
        wld.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(col) + (a,))
    wimg = _comp(wimg, wl.filter(ImageFilter.GaussianBlur(2.4)), 0.0)
    # rain on the glass
    wr = _rgba(wimg.width, wimg.height)
    wrd = ImageDraw.Draw(wr)
    for _ in range(220):
        x = rng.uniform(0, 1) * wimg.width
        y = rng.uniform(0, 1) * wimg.height
        ln = rng.uniform(0.01, 0.06) * wimg.height
        wrd.line([(x, y), (x + ln * 0.12, y + ln)], fill=(200, 215, 255, 40),
                 width=max(1, int(W * 0.0009)))
    wimg = _comp(wimg, wr.filter(ImageFilter.GaussianBlur(0.6)), 0.0)
    base.paste(wimg, (int(wx0), int(wy0)))
    # window frame
    layer = _rgba(W, H)
    d = ImageDraw.Draw(layer)
    fc = (14, 13, 16, 255)
    t = max(3, int(W * 0.006))
    d.rectangle([wx0 - t, wy0 - t, wx1 + t, wy1 + t], outline=fc, width=t)
    d.line([(wx0 + (wx1 - wx0) * 0.5, wy0), (wx0 + (wx1 - wx0) * 0.5, wy1)], fill=fc, width=t)
    d.line([(wx0, wy0 + (wy1 - wy0) * 0.42), (wx1, wy0 + (wy1 - wy0) * 0.42)], fill=fc, width=t)
    # sill
    d.rectangle([wx0 - t * 2, wy1 + t, wx1 + t * 2, wy1 + t * 2.2], fill=(24, 22, 24, 255))
    base = _comp(base, layer, 0.3)
    # light shaft from window
    shaft = _rgba(W, H)
    sd = ImageDraw.Draw(shaft)
    sd.polygon([(wx0, wy0 + (wy1 - wy0) * 0.35), (wx0, wy1),
                (W * 0.18, H * 1.0), (W * 0.02, H * 0.62)],
               fill=tuple(min(255, int(c * 0.55 + 30)) for c in pal["haze"]) + (52,))
    base = _comp(base, shaft.filter(ImageFilter.GaussianBlur(28)), 0.0)
    # desk foreground
    layer = _rgba(W, H)
    d = ImageDraw.Draw(layer)
    d.polygon([(0, H * 0.82), (W, H * 0.70), (W, H), (0, H)], fill=(13, 12, 14, 255))
    # dried sunflower on the desk
    fx, fy = W * 0.24, H * 0.80
    d.line([(fx, fy), (fx - W * 0.01, fy - H * 0.22)], fill=(40, 32, 26, 255), width=max(3, int(W * 0.003)))
    for ang in (-0.5, 0.0, 0.5):
        d.line([(fx, fy), (fx + math.sin(ang) * W * 0.035, fy - H * 0.26 - abs(ang) * H * 0.02)],
               fill=(36, 28, 24, 255), width=max(2, int(W * 0.0025)))
    _draw_flower(d, fx - W * 0.005, fy - H * 0.285, W * 0.042, (52, 40, 34, 255),
                 (30, 22, 20, 255), n=13, rot=0.4, petal_w=0.24)
    # vase
    d.polygon([(fx - W * 0.018, fy - H * 0.06), (fx + W * 0.018, fy - H * 0.06),
               (fx + W * 0.026, fy + H * 0.03), (fx - W * 0.026, fy + H * 0.03)],
              fill=(30, 28, 30, 255))
    base = _comp(base, layer, 0.7)
    # warm lamp glow for night_lamp
    if variant == "night_lamp":
        g = _rgba(W, H)
        gd = ImageDraw.Draw(g)
        gd.ellipse([W * 0.02, -H * 0.15, W * 0.34, H * 0.42], fill=tuple(pal["sun"]) + (70,))
        base = _comp(base, g.filter(ImageFilter.GaussianBlur(40)), 0.0)
        arr = np.asarray(base).astype(np.float32)
        arr += _glow_arr(W, H, W * 0.15, H * 0.12, W * 0.3, W * 0.3, pal["glow"], 0.35)
        base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    # cold moon / city glow
    arr = np.asarray(base).astype(np.float32)
    arr += _glow_arr(W, H, W * 0.67, H * 0.30, W * 0.34, W * 0.30, pal["glow"], 0.30)
    base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    # dust motes / bokeh in the room
    layer = _rgba(W, H)
    d = ImageDraw.Draw(layer)
    for _ in range(30):
        r = rng.uniform(0.001, 0.006) * W
        cx, cy = rng.uniform(0, 1) * W, rng.uniform(0, 1) * H
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(pal["bokeh"]) + (int(rng.uniform(20, 80)),))
    base = _comp(base, layer.filter(ImageFilter.GaussianBlur(2.5)), 0.0)
    return base, (0.67, 0.30), 0.66


# ---------------------------------------------------------------------- street
def _scene_street(shot, W, H, pal, seed) -> Image.Image:
    rng = random.Random(seed)
    variant = shot["variant"]
    horizon = 0.55
    arr = _vert_gradient(W, H, [(0.0, pal["sky_top"]), (0.5, pal["sky_mid"]), (horizon, pal["sky_hor"])])
    base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    # buildings
    layer = _rgba(W, H)
    d = ImageDraw.Draw(layer)
    col = (max(2, int(pal["ground_near"][0] * 0.55)), max(2, int(pal["ground_near"][1] * 0.55)),
           max(2, int(pal["ground_near"][2] * 0.60)))
    x = -W * 0.02
    while x < W:
        bw = rng.uniform(0.05, 0.14) * W
        bh = rng.uniform(0.10, 0.34) * H
        top = H * horizon - bh
        d.rectangle([x, top, x + bw, H * horizon + H * 0.02], fill=col + (255,))
        # lit windows
        for _ in range(int(bh / (H * 0.05))):
            wx = x + rng.uniform(0.12, 0.82) * bw
            wy = top + rng.uniform(0.1, 0.85) * bh
            ww = rng.uniform(0.01, 0.018) * W
            wh = ww * 0.7
            wc = pal["accent"] if rng.random() < 0.55 else pal["bokeh"]
            d.rectangle([wx, wy, wx + ww, wy + wh], fill=tuple(wc) + (int(rng.uniform(60, 150)),))
        x += bw + rng.uniform(0.004, 0.012) * W
    base = _comp(base, layer, 0.8)
    # street + wet asphalt
    layer = _rgba(W, H)
    d = ImageDraw.Draw(layer)
    d.rectangle([0, int(horizon * H), W, H], fill=tuple(max(3, int(c * 0.35)) for c in pal["ground_near"]) + (255,))
    base = _comp(base, layer, 0.0)
    arr = np.asarray(base).astype(np.float32)
    # wet reflections: vertical smears of neon
    refl = _rgba(W, H)
    rd = ImageDraw.Draw(refl)
    for _ in range(26):
        cx = rng.uniform(0, 1) * W
        top = H * (horizon + rng.uniform(0.0, 0.08))
        ln = rng.uniform(0.08, 0.30) * H
        w = rng.uniform(0.004, 0.016) * W
        c = pal["accent"] if rng.random() < 0.55 else pal["bokeh"]
        rd.line([(cx, top), (cx + rng.uniform(-0.02, 0.02) * W, top + ln)],
                fill=tuple(c) + (int(rng.uniform(40, 130)),), width=max(1, int(w)))
    base = _comp(base, refl.filter(ImageFilter.GaussianBlur(4.0)), 0.0)
    # puddle
    layer = _rgba(W, H)
    d = ImageDraw.Draw(layer)
    pcx, pcy = W * rng.uniform(0.35, 0.65), H * rng.uniform(0.76, 0.88)
    prx, pry = W * rng.uniform(0.20, 0.34), H * rng.uniform(0.05, 0.09)
    d.ellipse([pcx - prx, pcy - pry, pcx + prx, pcy + pry],
              fill=tuple(min(255, int(c * 1.5 + 20)) for c in pal["sky_hor"]) + (150,))
    base = _comp(base, layer.filter(ImageFilter.GaussianBlur(1.5)), 0.0)
    # ripples in the puddle
    layer = _rgba(W, H)
    d = ImageDraw.Draw(layer)
    for k in range(4):
        rr = prx * (0.15 + 0.22 * k)
        d.ellipse([pcx - rr, pcy - rr * 0.28, pcx + rr, pcy + rr * 0.28],
                  outline=(200, 220, 255, 40), width=2)
    base = _comp(base, layer.filter(ImageFilter.GaussianBlur(1.0)), 0.0)
    # red umbrella lying on the street
    if "傘" in shot.get("note", "") or "umbrella" in shot.get("camera", "").lower():
        layer = _rgba(W, H)
        d = ImageDraw.Draw(layer)
        ux, uy = W * 0.52, H * 0.83
        ur = W * 0.115
        # canopy: half circle
        d.pieslice([ux - ur, uy - ur * 0.55, ux + ur, uy + ur * 1.1], 185, 355,
                   fill=(120, 22, 34, 255))
        for k in range(6):
            a = math.pi + (k + 0.5) / 6 * math.pi
            d.line([(ux, uy + ur * 0.2), (ux + math.cos(a) * ur, uy + math.sin(a) * ur * 0.75)],
                   fill=(80, 12, 22, 255), width=2)
        d.line([(ux, uy + ur * 0.18), (ux, uy + ur * 0.9)], fill=(40, 26, 22, 255), width=4)
        base = _comp(base, layer, 1.4)
    # neon bokeh
    layer = _rgba(W, H)
    d = ImageDraw.Draw(layer)
    for _ in range(22):
        r = rng.uniform(0.003, 0.014) * W
        cx, cy = rng.uniform(0, 1) * W, rng.uniform(0.1, 0.7) * H
        c = pal["accent"] if rng.random() < 0.5 else pal["bokeh"]
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=tuple(c) + (int(rng.uniform(40, 120)),))
    base = _comp(base, layer.filter(ImageFilter.GaussianBlur(3)), 0.0)
    # rain streaks
    layer = _rgba(W, H)
    d = ImageDraw.Draw(layer)
    for _ in range(260):
        x = rng.uniform(0, 1) * W
        y = rng.uniform(0, 1) * H
        ln = rng.uniform(0.015, 0.06) * H
        d.line([(x, y), (x + ln * 0.18, y + ln)], fill=(190, 205, 240, 36), width=1)
    base = _comp(base, layer.filter(ImageFilter.GaussianBlur(0.7)), 0.0)
    # city glow
    arr = np.asarray(base).astype(np.float32)
    arr += _glow_arr(W, H, W * 0.5, H * 0.45, W * 0.55, H * 0.35, pal["glow"], 0.28)
    # car light streaks for city_bridge
    if variant == "city_bridge":
        layer = _rgba(W, H)
        d = ImageDraw.Draw(layer)
        for k in range(5):
            y = H * (0.58 + 0.03 * k) + rng.uniform(-8, 8)
            x0 = rng.uniform(0, 0.3) * W
            x1 = x0 + rng.uniform(0.3, 0.7) * W
            col = (255, 226, 190, 70)
            d.line([(x0, y), (x1, y)], fill=col, width=int(rng.uniform(2, 5)))
        layer = layer.filter(ImageFilter.GaussianBlur(6))
        base = _comp(base, layer, 0.0)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), (0.5, 0.45), horizon


# ------------------------------------------------------------------------ void
def _scene_void(shot, W, H, pal, seed) -> Image.Image:
    rng = random.Random(seed)
    arr = _vert_gradient(W, H, [(0.0, (2, 2, 6)), (0.45, pal["sky_top"]), (1.0, (3, 2, 7))])
    arr += _glow_arr(W, H, W * 0.5, H * 0.58, W * 0.45, H * 0.30, pal["glow"], 0.55,
                     falloff=1.8, core=0.3)
    arr += _glow_arr(W, H, W * 0.5, H * 0.62, W * 0.10, H * 0.06, pal["sun"], 0.45 + 0.0)
    base = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    # water plane
    layer = _rgba(W, H)
    d = ImageDraw.Draw(layer)
    d.rectangle([0, int(H * 0.52), W, H], fill=(6, 5, 12, 255))
    base = _comp(base, layer, 0.0)
    # ripples
    layer = _rgba(W, H)
    d = ImageDraw.Draw(layer)
    for k in range(36):
        cx = rng.uniform(0, 1) * W
        cy = H * rng.uniform(0.56, 1.0)
        rx = rng.uniform(0.02, 0.16) * W
        a = int(rng.uniform(12, 40))
        d.ellipse([cx - rx, cy - rx * 0.20, cx + rx, cy + rx * 0.20],
                  outline=tuple(pal["bokeh"]) + (a,), width=1)
    base = _comp(base, layer.filter(ImageFilter.GaussianBlur(1.4)), 0.0)
    # petals floating
    layer = _rgba(W, H)
    d = ImageDraw.Draw(layer)
    petal = (86, 58, 140) if "violet" in str(pal.get("glow")) or True else (200, 160, 90)
    for _ in range(20):
        cx, cy = rng.uniform(0, 1) * W, rng.uniform(0.2, 1.0) * H
        ln = rng.uniform(0.01, 0.035) * W
        ang = rng.uniform(0, math.pi * 2)
        col = blend_col(petal, pal["accent"], rng.uniform(0.0, 0.6))
        d.polygon(_petal_pts(cx, cy, ang, ln, ln * 0.46), fill=col + (int(rng.uniform(80, 200)),))
    base = _comp(base, layer.filter(ImageFilter.GaussianBlur(0.8)), 0.0)
    # mist noise
    arr = np.asarray(base).astype(np.float32)
    n = _noise(W, H, 60, 3, seed + 7)
    arr += (n[..., None] - 0.5) * np.array(pal["haze"], np.float32) * 0.20
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)), (0.5, 0.6), 0.52


# --------------------------------------------------------------------- builder
def build_canvas(shot, W=None, H=None) -> Image.Image:
    W = W or int(round(1920 * CANVAS_SCALE))
    H = H or int(round(1080 * CANVAS_SCALE))
    variant = shot["variant"]
    pal = _pal(variant)
    seed = int(hash01(shot["id"]) * 1e6)
    rng = random.Random(seed + 1)
    cam = shot.get("camera", "").lower()
    note = shot.get("note", "")
    st = shot.get("set")
    # light position default by set/variant
    if "night" in variant or variant in ("rain_night", "night_dark", "night_lamp", "city_bridge"):
        sun_xy = (0.6, 0.32)
    elif "dusk" in variant:
        sun_xy = (0.58, 0.46)
    else:
        sun_xy = (0.63, 0.34)
    horizon = 0.58
    figures = 0
    if any(k in cam for k in ("two silhouettes", "two figures")):
        figures = 2
    elif any(k in cam for k in ("silhouette", "girl", "figure", "reflections hold hands")):
        figures = 1
    close_cam = any(k in cam for k in ("macro", "close", "foreground focus", "fill frame",
                                       "hero", "translucent petals"))
    hero_violet = ("violet sunflower" in cam or "violet sunflower" in note) and close_cam
    macro = (not hero_violet) and any(k in cam for k in ("macro", "translucent petals fill frame"))
    if st in ("field",):
        base = _vert_gradient(W, H, [(0.0, pal["sky_top"]), (0.42, pal["sky_mid"]), (horizon, pal["sky_hor"])])
        base = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
        img = _draw_sunflower_field(base, W, H, pal, seed, horizon=horizon,
                                    hero_violet=hero_violet, figures=figures,
                                    sun_xy=sun_xy, macro=macro)
        sun = sun_xy
    elif st == "road":
        img, sun, horizon = _scene_road(shot, W, H, pal, seed)
    elif st == "room":
        img, sun, horizon = _scene_room(shot, W, H, pal, seed)
    elif st == "street":
        img, sun, horizon = _scene_street(shot, W, H, pal, seed)
    else:  # void
        img, sun, horizon = _scene_void(shot, W, H, pal, seed)
    # a touch of bloom already in the plate (the compositor adds the real one)
    arr = np.asarray(img).astype(np.float32)
    n = _noise(W, H, 120, 2, seed + 21)
    arr *= (0.96 + 0.08 * n)[..., None]
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    # very light overall softness to avoid a "flat CG" look
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    return img, sun, horizon


def ensure_dummy_plates(shots, force=False, log=print) -> dict:
    """Generate / refresh all dummy plate canvases. Returns metadata dict."""
    os.makedirs(DUMMY_DIR, exist_ok=True)
    meta = load_json(META_PATH, {}) or {}
    made = 0
    for k, shot in enumerate(shots):
        sid = shot["id"]
        path = os.path.join(DUMMY_DIR, sid + ".png")
        if force or not os.path.exists(path) or meta.get(sid, {}).get("v") != 3:
            img, sun, horizon = build_canvas(shot)
            img.save(path, "PNG", compress_level=3)
            meta[sid] = {"v": 3, "sun": [round(sun[0], 4), round(sun[1], 4)],
                         "horizon": round(horizon, 4), "set": shot["set"],
                         "variant": shot["variant"],
                         "size": [img.width, img.height]}
            made += 1
            if made % 8 == 1:
                log("  dummy plate %s (%d/%d)" % (sid, k + 1, len(shots)))
    save_json(META_PATH, meta)
    return meta


if __name__ == "__main__":
    from timeline import Timeline
    tl = Timeline()
    ensure_dummy_plates(tl.shots, force="--force" in os.sys.argv)
    print("dummy plates ready in", DUMMY_DIR)
