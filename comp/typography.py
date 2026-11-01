# -*- coding: utf-8 -*-
"""typography.py — lyric typesetting, per-glyph animation, title & credits.

Design notes
------------
* JP lyric body   : Shippori Mincho 500 (600 for emphasis lines), white with a
  soft drop shadow and a very subtle warm/violet halo so it survives both the
  golden and the violet worlds.
* CN translation   : Noto Sans SC (light), ~0.62 opacity, small caps-sized,
  tucked under the Japanese line (or set as a second vertical column).
* Ghost lyrics     : same line at 2.6-3.6x size, 4-7% opacity, heavily blurred.
* Layouts          : bottom-left (default), right/left vertical (縦書き),
  centre-large for hooks.  Every line's layout is written to lyrics_layout.json.
* Animation        : per-glyph staggered ease-out fade-in with a 9px rise and a
  soft blur dissolve; 340ms line fade-out before the next line.
"""
from __future__ import annotations

import math
import os

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

from common import (COMP_DIR, FULL_H, FULL_W, FONT_PATHS, alpha_scale, clamp,
                    ease_out_cubic, font_key_for, hash01, load_font, load_json,
                    save_json, smoothstep, smoothstep_range)

LAYOUT_PATH = os.path.join(COMP_DIR, "lyrics_layout.json")
LAYOUT_VERSION = 12

SAFE_L, SAFE_R = 130, 1150
SAFE_T, SAFE_B = 150, 1000

# ------------------------------------------------------------------ styles
# i -> style.  bl = bottom-left, bl_emph = bigger/600, vr/vl = vertical,
# center_big = centred chorus hook, center_key = the two key screams.
STYLES = {
    0: "bl", 1: "bl", 2: "bl", 3: "bl", 4: "vr", 5: "bl", 6: "bl", 7: "bl",
    8: "bl_emph", 9: "vl", 10: "center_big", 11: "bl", 12: "vr", 13: "bl",
    14: "bl_emph", 15: "bl", 16: "vl", 17: "bl_emph", 18: "center_big",
    19: "bl", 20: "vr", 21: "bl", 22: "bl", 23: "bl", 24: "bl", 25: "vl",
    26: "bl", 27: "bl", 28: "bl", 29: "bl", 30: "bl_emph", 31: "bl", 32: "bl",
    33: "vr", 34: "bl_emph", 35: "center_big", 36: "bl", 37: "bl",
    38: "center_big", 39: "bl", 40: "vl", 41: "bl_emph", 42: "center_big",
    43: "bl", 44: "bl", 45: "center_big", 46: "vr", 47: "bl", 48: "vl",
    49: "center_big", 50: "bl", 51: "vr", 52: "bl_emph", 53: "center_big",
    54: "bl", 55: "vl", 56: "bl_emph", 57: "center_big", 58: "center_key",
    59: "center_key",
}

STYLE_SPEC = {
    # style: (font, sizes, tracking, jp_align, vertical, first_scale)
    "bl": dict(font=("jp", False), sizes=(50, 48, 46, 44, 42), tracking=0.026,
               kind="bl", first=1.12),
    "bl_emph": dict(font=("jp", True), sizes=(54, 52, 50, 48, 46), tracking=0.026,
                    kind="bl", first=1.14),
    "center_big": dict(font=("jp", True), sizes=(82, 76, 70, 64, 58), tracking=0.055,
                       kind="center", first=1.10),
    "center_key": dict(font=("jp", True), sizes=(112, 104, 96, 88), tracking=0.085,
                       kind="center", first=1.08),
    "vr": dict(font=("jp", False), sizes=(54, 50, 46), tracking=14, kind="vr", first=1.10),
    "vl": dict(font=("jp", False), sizes=(54, 50, 46), tracking=14, kind="vl", first=1.10),
}

# colour groups per shot variant
GOLD_VARIANTS = {"noon_hot", "noon_side", "gold_noon", "gold_dusk", "dusk_afterglow", "macro_warm"}
VIOLET_VARIANTS = {"violet_dusk", "violet_night", "petals_dark"}
COLD_VARIANTS = {"night_rain", "rain_night", "night_dark", "city_bridge", "macro_cold"}

TEXT_STYLE = {
    "gold": dict(color=(255, 251, 242), glow=(255, 213, 150), glow_a=0.30),
    "violet": dict(color=(247, 245, 255), glow=(178, 150, 255), glow_a=0.32),
    "cold": dict(color=(240, 245, 255), glow=(150, 190, 255), glow_a=0.28),
    "neutral": dict(color=(252, 250, 246), glow=(220, 214, 230), glow_a=0.26),
}


def variant_group(variant: str) -> str:
    if variant in GOLD_VARIANTS:
        return "gold"
    if variant in VIOLET_VARIANTS:
        return "violet"
    if variant in COLD_VARIANTS:
        return "cold"
    return "neutral"


# ------------------------------------------------------------------ row helpers
def _font_spec(font_spec):
    lang, emph = font_spec
    return font_key_for(lang, emph)


def _row_width(glyphs):
    if not glyphs:
        return 0.0
    x0 = min(g["bbox"][0] for g in glyphs)
    x1 = max(g["bbox"][2] for g in glyphs)
    return x1 - x0


def build_h_row(text: str, font_key, weight, size: float, tracking: float,
                x: float, baseline: float, align: str = "left",
                first_scale: float = 1.0, pad: float = 34.0) -> dict:
    """Build a horizontal row: glyph positions + bbox (full-res design space)."""
    glyphs = []
    pen = 0.0
    size_i = int(round(size))
    for idx, ch in enumerate(text):
        if ch == " ":
            pen += size * 0.35
            continue
        sc = first_scale if idx == 0 else 1.0
        px = size * sc
        f = load_font(font_key, px, weight)
        bbox = f.getbbox(ch, anchor="ls")
        adv = f.getlength(ch)
        glyphs.append(dict(ch=ch, font_key=font_key, weight=weight, px=int(round(px)),
                           pen=pen, bbox=bbox, size=sc))
        pen += adv + tracking
    width = pen - tracking if glyphs else 0.0
    if align == "center":
        x0 = x - width / 2.0
    elif align == "right":
        x0 = x - width
    else:
        x0 = x
    for g in glyphs:
        g["draw_x"] = x0 + g["pen"]
        g["draw_y"] = baseline
    bx0 = min(g["draw_x"] + g["bbox"][0] for g in glyphs) - pad
    by0 = min(g["draw_y"] + g["bbox"][1] for g in glyphs) - pad
    bx1 = max(g["draw_x"] + g["bbox"][2] for g in glyphs) + pad
    by1 = max(g["draw_y"] + g["bbox"][3] for g in glyphs) + pad
    return dict(kind="h", glyphs=glyphs, bbox=(bx0, by0, bx1, by1), size=size,
                tracking=tracking, text=text)


def build_v_row(text: str, font_key, weight, size: float, gap: float,
                cx: float, top: float, first_scale: float = 1.0,
                pad: float = 30.0) -> dict:
    glyphs = []
    cy = top
    for idx, ch in enumerate(text):
        if ch == " ":
            cy += size + gap
            continue
        sc = first_scale if idx == 0 else 1.0
        px = size * sc
        f = load_font(font_key, px, weight)
        bbox = f.getbbox(ch, anchor="ls")
        cell = size * 1.02 + gap
        cy_c = cy + cell / 2.0
        draw_x = cx - (bbox[0] + bbox[2]) / 2.0
        draw_y = cy_c - (bbox[1] + bbox[3]) / 2.0
        glyphs.append(dict(ch=ch, font_key=font_key, weight=weight, px=int(round(px)),
                           cell_cx=cx, cell_cy=cy_c, bbox=bbox, size=sc,
                           draw_x=draw_x, draw_y=draw_y))
        cy += cell
    bx0 = min(g["draw_x"] + g["bbox"][0] for g in glyphs) - pad
    by0 = min(g["draw_y"] + g["bbox"][1] for g in glyphs) - pad
    bx1 = max(g["draw_x"] + g["bbox"][2] for g in glyphs) + pad
    by1 = max(g["draw_y"] + g["bbox"][3] for g in glyphs) + pad
    return dict(kind="v", glyphs=glyphs, bbox=(bx0, by0, bx1, by1), size=size,
                tracking=gap, text=text)


# ------------------------------------------------------------------ layout
def _fit_h_sizes(text, font_key, weight, sizes, tracking, max_w, first=1.12):
    for size in sizes:
        r = build_h_row(text, font_key, weight, size, size * tracking if tracking < 1 else tracking,
                        0.0, 0.0, "left", first)
        w = r["bbox"][2] - r["bbox"][0] - 68.0
        if w <= max_w:
            return size, r
    return None, None


CN_SHADOW = dict(alpha=0.38, blur=4.2, dx=0.0, dy=1.6, halo=0.0, halo_blur=0.0)
JP_SHADOW = dict(alpha=0.88, blur=8.0, dx=0.0, dy=2.4, halo=0.34, halo_blur=24.0)


def _cn_baseline(jp_font_key, jp_weight, jp_px, jp_baseline, cn_px, gap=10.0):
    """Exact baseline so the CN subtitle sits 8-14px under the JP line."""
    jf = load_font(jp_font_key, int(round(jp_px)), jp_weight)
    _ja, jdesc = jf.getmetrics()
    cf = load_font("sc_sans", int(round(cn_px)), 400)
    casc, _cdesc = cf.getmetrics()
    return jp_baseline + jdesc * 0.82 + gap + casc


def _split_two(text):
    """Split a long JP line into two balanced visual rows."""
    if "　" in text:
        a, b = text.split("　", 1)
        return [a, b]
    n = len(text)
    # avoid splitting inside the most common bracket pairs
    mid = n // 2
    best = None
    for d in range(0, n // 2):
        for k in (mid - d, mid + d):
            if 2 <= k <= n - 2:
                left, right = text[:k], text[k:]
                if left.count("「") == left.count("」") and right.count("「") == right.count("」"):
                    best = (left, right)
                    break
        if best:
            break
    if not best:
        best = (text[:mid], text[mid:])
    return list(best)


def build_line_layout(i, lyric, style, variant, tl):
    spec = STYLE_SPEC.get(style, STYLE_SPEC["bl"])
    font_key, weight = _font_spec(spec["font"])
    sizes = spec["sizes"]
    tracking = spec["tracking"]
    first = spec["first"]
    t = lyric["t"]
    t_end = lyric["t_end"]
    jp = lyric["jp"]
    cn = lyric["cn"]
    kind = spec["kind"]
    rows = []

    if kind == "bl":
        # fit one or two rows into the bottom-left safe box
        size, row = _fit_h_sizes(jp, font_key, weight, sizes, tracking,
                                 SAFE_R - SAFE_L, first)
        single = size is not None
        if single:
            size_i = int(round(size))
            base = 850.0
            row = build_h_row(jp, font_key, weight, size, max(0.6, size * tracking),
                              SAFE_L, base, "left", first)
            rows.append(dict(row=row, start=t, stagger=0.024, dur=0.29))
            cn_size = 32
            cn_track = cn_size * 0.03
            cn_base = _cn_baseline(font_key, weight, size, base, cn_size, gap=11.0)
            cn_row = build_h_row(cn, "sc_sans", 400, cn_size, cn_track,
                                 SAFE_L, cn_base, "left", 1.0, pad=24)
            cn_row["shadow"] = CN_SHADOW
            rows.append(dict(row=cn_row, start=t + 0.16, stagger=0.0, dur=0.32,
                             alpha=0.88))
        else:
            parts = _split_two(jp)
            size2, _ = _fit_h_sizes(max(parts, key=len), font_key, weight,
                                    (46, 44, 42, 40), tracking, SAFE_R - SAFE_L, 1.0)
            size2 = size2 or 40
            base1, base2 = 806.0, 806.0 + size2 * 1.26
            for ri, part in enumerate(parts):
                row = build_h_row(part, font_key, weight, size2, max(0.6, size2 * tracking),
                                  SAFE_L, base1 if ri == 0 else base2, "left", 1.0)
                rows.append(dict(row=row, start=t, stagger=0.022, dur=0.29))
            cn_size = 32
            cn_base = _cn_baseline(font_key, weight, size2, base2, cn_size, gap=11.0)
            cn_row = build_h_row(cn, "sc_sans", 400, cn_size, cn_size * 0.03,
                                 SAFE_L, cn_base, "left", 1.0, pad=24)
            cn_row["shadow"] = CN_SHADOW
            rows.append(dict(row=cn_row, start=t + 0.18, stagger=0.0, dur=0.32, alpha=0.88))
    elif kind == "center":
        size, _ = _fit_h_sizes(jp, font_key, weight, sizes, tracking, FULL_W - 300, first)
        size = size or sizes[-1]
        base = 500.0
        row = build_h_row(jp, font_key, weight, size, max(1.0, size * tracking),
                          FULL_W / 2.0, base, "center", first)
        rows.append(dict(row=row, start=t, stagger=0.030, dur=0.30))
        cn_size = 33
        cn_base = _cn_baseline(font_key, weight, size, base, cn_size, gap=13.0)
        cn_row = build_h_row(cn, "sc_sans", 400, cn_size, cn_size * 0.04,
                             FULL_W / 2.0, cn_base, "center", 1.0, pad=24)
        cn_row["shadow"] = CN_SHADOW
        rows.append(dict(row=cn_row, start=t + 0.20, stagger=0.0, dur=0.32, alpha=0.88))
    else:  # vertical
        right = kind == "vr"
        col_x = 1712.0 if right else 198.0
        top = 178.0
        avail = 900.0
        size = sizes[0]
        for s in sizes:
            total = len(jp) * (s * 1.02 + spec["tracking"]) - spec["tracking"]
            if total <= avail:
                size = s
                break
        row = build_v_row(jp, font_key, weight, size, spec["tracking"], col_x, top, first)
        rows.append(dict(row=row, start=t, stagger=0.034, dur=0.30))
        cn_size = 27
        cn_gap = 8
        cn_x = col_x - (size * 0.5 + 22 + cn_size * 0.5) if right else col_x + (size * 0.5 + 22 + cn_size * 0.5)
        jp_total = len(jp) * (size * 1.02 + spec["tracking"]) - spec["tracking"]
        cn_total = len(cn) * (cn_size * 1.02 + cn_gap) - cn_gap
        cn_top = top + max(0.0, (jp_total - cn_total) / 2.0)
        cn_row = build_v_row(cn, "sc_sans", 400, cn_size, cn_gap, cn_x,
                             cn_top, 1.0, pad=20)
        cn_row["shadow"] = CN_SHADOW
        rows.append(dict(row=cn_row, start=t + 0.22, stagger=0.0, dur=0.34, alpha=0.88))

    dur = max(0.4, t_end - t)
    fo_dur = clamp(dur * 0.34, 0.24, 0.40)
    fo_start = t_end - fo_dur
    return dict(
        i=i, style=style, t=t, t_end=t_end,
        fade_out_start=fo_start, fade_out_dur=fo_dur,
        group=variant_group(variant),
        rows=rows,
        ghost=_ghost_spec(i, jp, style, rows, t, t_end, size=rows[0]["row"]["size"] if rows else 48),
        jp=jp, cn=cn,
    )


def _ghost_spec(i, jp, style, rows, t, t_end, size):
    rnd = hash01("ghost", i)
    kind = STYLE_SPEC.get(style, STYLE_SPEC["bl"])["kind"]
    if kind == "bl":
        gsize = clamp(size * 3.3, 150, 260)
        x = FULL_W * (0.30 + 0.45 * rnd)
        y = 180 + 230 * hash01("gy", i)
        align = "left"
        vertical = False
    elif kind == "center":
        gsize = clamp(size * 2.5, 170, 300)
        x = FULL_W * (0.42 + 0.16 * rnd)
        y = 150 + 200 * hash01("gy", i)
        align = "center"
        vertical = False
    else:
        gsize = clamp(size * 2.45, 120, 190)
        x = FULL_W * (0.20 if kind == "vr" else 0.78)
        y = 120.0
        align = "center"
        vertical = True
    return dict(text=jp, size=gsize, tracking=0.10 if not vertical else 16,
                x=x, y=y, align=align, vertical=vertical,
                alpha=0.042 + 0.024 * hash01("ga", i),
                blur=15.0 + 9.0 * hash01("gb", i),
                tint=(255, 250, 245) if rnd < 0.6 else (235, 230, 255),
                start=t + 0.10, end=max(t + 0.4, t_end - 0.05))


# ---------------------------------------------------------------- title/credits
def build_title(tl):
    """Title card over S56 (starts exactly at f6157 = 256.5 s).

    * first 20 frames fade in from 0
    * letter tracking breathes from +0.16em down to +0.10em
    * big soft warm outer glow + faint warm-gold radial halo behind the type
    """
    t0 = 256.5
    TITLE_FRAMES = 20
    px = 128.0
    trk0, trk1 = px * 0.16, px * 0.10
    nvar = 11
    variants = []
    for k in range(nvar):
        u = k / float(nvar - 1)
        trk = trk0 + (trk1 - trk0) * (u * u * (3 - 2 * u))
        variants.append(build_h_row("紫色の向日葵", "zen_old600", None, px, trk,
                                    FULL_W / 2.0, 438.0, "center", 1.0, pad=64))
    rows = []
    rows.append(dict(row=variants[-1], variants=variants,
                     start=t0, track_start=t0, track_dur=TITLE_FRAMES / 24.0,
                     stagger=0.055, dur=0.42, alpha=1.0, glow=2.2,
                     glow_blur=2.4))
    rows.append(dict(row=build_h_row("Purple Sunflower", "kaku300", None, 31, 3.0,
                                     FULL_W / 2.0, 548.0, "center", 1.0, pad=28),
                     start=t0 + 0.62, stagger=0.0, dur=0.55, alpha=0.78,
                     color=(232, 230, 227)))
    rows.append(dict(row=build_h_row("香椎モイミ feat. 羽累", "jp500", None, 28, 4.0,
                                     FULL_W / 2.0, 608.0, "center", 1.0, pad=28),
                     start=t0 + 0.92, stagger=0.0, dur=0.55, alpha=0.85,
                     color=(242, 238, 233)))
    return dict(t0=t0, t1=263.5, rows=rows,
                fade_out_start=262.94, fade_out_dur=0.50,
                halo=dict(cx=FULL_W * 0.5, cy=FULL_H * 0.42, rx=FULL_W * 0.52,
                          ry=FULL_H * 0.30, alpha=0.30, color=(255, 224, 182)),
                shade=dict(cx=FULL_W * 0.5, cy=FULL_H * 0.47, rx=FULL_W * 0.50,
                           ry=FULL_H * 0.34, alpha=0.34))


def build_credits(tl):
    """End credits over S57, fading out with the picture (last ~3s)."""
    rows = []
    sc = (232, 229, 224)
    lines = [
        ("音乐：香椎モイミ「紫色の向日葵」feat. 羽累", "sc_sans", 25, 0.0),
        ("作曲・编曲：香椎モイミ", "sc_sans", 24, 0.55),
    ]
    y = 402.0
    for k, (txt, fk, sz, extra) in enumerate(lines):
        rows.append(dict(row=build_h_row(txt, fk, 400, sz, 2.0,
                                         FULL_W / 2.0, y + k * 42, "center", 1.0, pad=24),
                         start=265.30 + k * 0.30, stagger=0.0, dur=0.7, alpha=0.70,
                         color=sc, glow=0.6))
    # second block
    blk = [
        ("MV 制作：DeepSeek Harness", "sc_sans", 23),
        ("3D / 合成：Blender 5.2 · Python · FFmpeg", "sc_sans", 23),
    ]
    y2 = 540.0
    for k, (txt, fk, sz) in enumerate(blk):
        rows.append(dict(row=build_h_row(txt, fk, 400, sz, 2.0,
                                         FULL_W / 2.0, y2 + k * 40, "center", 1.0, pad=24),
                         start=266.15 + k * 0.28, stagger=0.0, dur=0.7, alpha=0.68,
                         color=sc, glow=0.6))
    rows.append(dict(row=build_h_row("ご視聴ありがとうございました", "jp500", None, 25, 6.0,
                                     FULL_W / 2.0, 668.0, "center", 1.0, pad=28),
                     start=266.95, stagger=0.0, dur=0.8, alpha=0.78,
                     color=(248, 244, 238), glow=0.9))
    return dict(t0=263.5, t1=272.966, rows=rows,
                fade_out_start=269.95, fade_out_dur=2.55,
                shade=dict(cx=FULL_W * 0.5, cy=FULL_H * 0.52, rx=FULL_W * 0.48,
                           ry=FULL_H * 0.40, alpha=0.40))


# ------------------------------------------------------------------ renderer
class Typography:
    def __init__(self, timeline, W: int, H: int, scale: float = 1.0):
        self.tl = timeline
        self.W, self.H, self.S = W, H, scale
        self.layout = self._build_layout()
        self.lines = self.layout["lines"]
        self.title = self.layout["title"]
        self.credits = self.layout["credits"]
        self._static = {}
        self._ghost = {}
        self._shade = {}
        self._font_cache = {}
        self._line_index = self._index_lines()

    # ---------------------------------------------------------------- build
    def _build_layout(self):
        lines = []
        for ly in self.tl.lyrics:
            i = ly["i"]
            style = STYLES.get(i, "bl")
            f = self.tl.shot_at_frame(max(1, int(round(ly["t"] * self.tl.fps)) + 1))
            lines.append(build_line_layout(i, ly, style, f["variant"], self.tl))
        return dict(version=LAYOUT_VERSION, lines=lines,
                    title=build_title(self.tl), credits=build_credits(self.tl))

    def _index_lines(self):
        idx = []
        for ln in self.lines:
            idx.append((ln["t"] - 0.05, ln["t_end"] + 0.05, ln))
        return idx

    def write_layout(self, path=LAYOUT_PATH):
        def clean(o):
            if isinstance(o, dict):
                return {k: clean(v) for k, v in o.items() if k != "glyphs"}
            if isinstance(o, (list, tuple)):
                return [clean(v) for v in o]
            return o
        doc = dict(version=LAYOUT_VERSION,
                   note=("Auto-generated by comp/typography.py. Style per line: bl=bottom-left, "
                         "bl_emph=emphasis, vr/vl=vertical right/left, center_big=chorus hook, "
                         "center_key=key scream. Coordinates are 1920x1080 design space."),
                   styles={str(k): v for k, v in STYLES.items()},
                   lines=clean(self.lines),
                   title=clean(self.title), credits=clean(self.credits))
        save_json(path, doc)

    # ------------------------------------------------------------- helpers
    def _scaled_bbox(self, row):
        x0, y0, x1, y1 = row["bbox"]
        S = self.S
        return (int(math.floor(x0 * S)), int(math.floor(y0 * S)),
                int(math.ceil(x1 * S)), int(math.ceil(y1 * S)))

    def _row_scale_key(self):
        return round(self.S, 2)

    def _ensure_font(self, g):
        px = max(4, int(round(g["px"] * self.S)))
        key = (g["font_key"], px, g["weight"])
        f = self._font_cache.get(key)
        if f is None:
            f = load_font(g["font_key"], px, g["weight"])
            self._font_cache[key] = f
        return f

    def _draw_glyphs(self, row, t, mask=None, S=None):
        """Draw glyphs into an L mask (scaled). Returns mask."""
        S = self.S if S is None else S
        x0, y0, x1, y1 = self._scaled_bbox(row)
        w, h = max(1, x1 - x0), max(1, y1 - y0)
        if mask is None:
            mask = Image.new("L", (w, h), 0)
        d = ImageDraw.Draw(mask)
        glyphs = row["glyphs"]
        n = len(glyphs)
        a0 = row.get("start", 0.0)
        stagger = row.get("stagger", 0.0)
        dur = max(0.05, row.get("dur", 0.3))
        total_stag = stagger * max(0, n - 1)
        if total_stag > 0.5:
            stagger = 0.5 / max(1, n - 1)
        for k, g in enumerate(glyphs):
            if t is None:
                a = 1.0
                rise = 0.0
            else:
                st = a0 + k * stagger
                a = ease_out_cubic((t - st) / dur)
                if a <= 0.004:
                    continue
                rise = (1.0 - a) * 9.0 * S
            f = self._ensure_font(g)
            px = g["draw_x"] * S - x0
            py = g["draw_y"] * S - y0 + rise
            fill = 255 if t is None else int(255 * a)
            if row.get("kind", "h") == "v":
                # vertical: draw_x already positions bbox centre (baseline origin)
                d.text((px, py), g["ch"], font=f, fill=fill, anchor="ls")
            else:
                d.text((px, py), g["ch"], font=f, fill=fill, anchor="ls")
        return mask

    def _colorize(self, mask, w, h, group, glow_boost=1.0, shadow=True,
                  shadow_spec=None, color=None, glow_blur=1.0):
        st = TEXT_STYLE[group]
        text_color = tuple(color) if color else tuple(st["color"])
        S = self.S
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        if shadow:
            spec = shadow_spec or JP_SHADOW
            m = mask
            dx = int(round(spec.get("dx", 0.0) * S))
            dy = int(round(spec.get("dy", 2.0) * S))
            if dx or dy:
                m = ImageChops.offset(m, dx, dy)
            halo = spec.get("halo", 0.0)
            if halo > 0.005:
                hm = m.filter(ImageFilter.GaussianBlur(max(0.6, spec["halo_blur"] * S)))
                hm = hm.point(lambda v: int(v * halo))
                hl = Image.new("RGBA", (w, h), (4, 3, 10, 255))
                hl.putalpha(hm)
                layer.alpha_composite(hl)
            sh = m.filter(ImageFilter.GaussianBlur(max(0.4, spec["blur"] * S)))
            sh = sh.point(lambda v: int(v * spec["alpha"]))
            shl = Image.new("RGBA", (w, h), (0, 0, 0, 255))
            shl.putalpha(sh)
            layer.alpha_composite(shl)
        glow = mask.filter(ImageFilter.GaussianBlur(max(0.6, 13.0 * S * glow_blur)))
        ga = st["glow_a"] * glow_boost
        glow = glow.point(lambda v: int(v * ga))
        gl = Image.new("RGBA", (w, h), tuple(st["glow"]) + (255,))
        gl.putalpha(glow)
        layer.alpha_composite(gl)
        tx = Image.new("RGBA", (w, h), text_color + (255,))
        tx.putalpha(mask)
        layer.alpha_composite(tx)
        return layer

    def _static_row(self, rid, row, group, glow_boost, glow_blur=1.0):
        key = (rid, self._row_scale_key(), group, round(glow_blur, 2))
        hit = self._static.get(key)
        if hit is not None:
            return hit
        x0, y0, x1, y1 = self._scaled_bbox(row)
        w, h = max(1, x1 - x0), max(1, y1 - y0)
        mask = self._draw_glyphs(row, None)
        layer = self._colorize(mask, w, h, group, glow_boost,
                               shadow_spec=row.get("shadow"), color=row.get("color"),
                               glow_blur=glow_blur)
        rgb = layer.convert("RGB")
        alpha = layer.getchannel("A")
        hit = (rgb, alpha, (x0, y0))
        self._static[key] = hit
        return hit

    def _dynamic_row(self, rid, row, t, group, glow_boost, glow_blur=1.0):
        x0, y0, x1, y1 = self._scaled_bbox(row)
        w, h = max(1, x1 - x0), max(1, y1 - y0)
        mask = self._draw_glyphs(row, t)
        # soft blur dissolve on entry
        S = self.S
        a0 = row.get("start", 0.0)
        stag = row.get("stagger", 0.0) * max(0, len(row["glyphs"]) - 1)
        dur = max(0.05, row.get("dur", 0.3))
        prog = clamp((t - a0) / max(0.05, dur + stag))
        bw = (1.0 - prog) ** 1.6
        if bw > 0.02:
            mask = mask.filter(ImageFilter.GaussianBlur(max(0.4, 2.6 * S * bw)))
        layer = self._colorize(mask, w, h, group, glow_boost,
                               shadow_spec=row.get("shadow"), color=row.get("color"),
                               glow_blur=glow_blur)
        return layer.convert("RGB"), layer.getchannel("A"), (x0, y0)

    # ------------------------------------------------------------ row render
    def _render_row(self, rid, row_spec, t, group, line_alpha=1.0, glow_boost=1.0):
        row = row_spec["row"]
        a0 = row_spec.get("start", 0.0)
        if t < a0 - 0.02:
            return None
        variants = row_spec.get("variants")
        track_start = row_spec.get("track_start")
        track_dur = row_spec.get("track_dur", 0.0)
        entry = 1.0
        if variants:
            u = clamp((t - track_start) / max(1e-4, track_dur))
            row = variants[int(round(u * (len(variants) - 1)))]
            entry = ease_out_cubic(u) if u < 1.0 else 1.0
            a0 = track_start
        n = len(row["glyphs"])
        stagger = row_spec.get("stagger", 0.0)
        total_stag = stagger * max(0, n - 1)
        dur = max(0.05, row_spec.get("dur", 0.3))
        row_alpha = row_spec.get("alpha", 1.0) * line_alpha * entry
        gb = row_spec.get("glow", glow_boost)
        gblur = row_spec.get("glow_blur", 1.0)
        if (not variants) and t >= a0 + total_stag + dur + 0.02:
            rgb, alpha, pos = self._static_row(rid, row, group, gb, gblur)
        else:
            rgb, alpha, pos = self._dynamic_row(rid, row, t, group, gb, gblur)
        k = clamp(row_alpha)
        if k <= 0.002:
            return None
        return (rgb, alpha_scale(alpha, k), pos)

    def _render_rule(self, rid, spec, t, line_alpha=1.0):
        a0 = spec.get("start", 0.0)
        dur = max(0.05, spec.get("dur", 0.4))
        r = spec["rule"]
        a = ease_out_cubic((t - a0) / dur) * r.get("alpha", 1.0) * line_alpha
        if a <= 0.01:
            return None
        S = self.S
        w = max(2, int((r["x1"] - r["x0"]) * S))
        h = max(2, int(6 * S))
        layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        th = max(1, int(round(r["thickness"] * S)))
        col = (255, 252, 246, int(255 * clamp(a)))
        d.rectangle([0, (h - th) // 2, w - 1, (h - th) // 2 + th], fill=col)
        return (layer.convert("RGB"), layer.getchannel("A"),
                (int(r["x0"] * S), int(r["y"] * S) - h // 2))

    # ------------------------------------------------------------ shade layer
    def shade_op(self, spec):
        key = (round(spec["cx"]), round(spec["cy"]), round(spec["rx"]),
               round(spec["ry"]), round(spec["alpha"], 2))
        hit = self._shade.get(key)
        if hit is None:
            S = self.S
            W, H = self.W, self.H
            lw, lh = max(16, W // 6), max(16, H // 6)
            import numpy as np
            yy, xx = np.mgrid[0:lh, 0:lw].astype("float32")
            cx = spec["cx"] / FULL_W * lw
            cy = spec["cy"] / FULL_H * lh
            rx = spec["rx"] / FULL_W * lw
            ry = spec["ry"] / FULL_H * lh
            r = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
            v = np.clip(1.0 - r, 0, 1) ** 1.8 * spec["alpha"]
            a = (np.clip(v, 0, 1) * 255).astype("uint8")
            a = Image.fromarray(a).resize((W, H), Image.BILINEAR)
            rgb = Image.new("RGB", (W, H), (8, 6, 14))
            hit = (rgb, a, (0, 0))
            self._shade[key] = hit
        return hit

    # ------------------------------------------------------------ title halo
    def _halo_op(self, spec):
        key = (round(spec["cx"]), round(spec["cy"]), round(spec["rx"]),
               round(spec["ry"]), round(spec["alpha"], 2), tuple(spec["color"]))
        hit = self._shade.get(key)
        if hit is not None:
            return hit
        S = self.S
        W, H = self.W, self.H
        lw, lh = max(16, W // 6), max(16, H // 6)
        yy, xx = np.mgrid[0:lh, 0:lw].astype("float32")
        cx = spec["cx"] / FULL_W * lw
        cy = spec["cy"] / FULL_H * lh
        rx = spec["rx"] / FULL_W * lw
        ry = spec["ry"] / FULL_H * lh
        r = np.sqrt(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2)
        v = np.clip(1.0 - r, 0, 1) ** 2.0 * spec["alpha"]
        # extra warm core behind the title
        r2 = np.sqrt(((xx - cx) / (rx * 0.55)) ** 2 + ((yy - cy) / (ry * 0.45)) ** 2)
        v += np.clip(1.0 - r2, 0, 1) ** 2.4 * spec["alpha"] * 0.45
        a = (np.clip(v, 0, 1) * 255).astype("uint8")
        a = Image.fromarray(a).resize((W, H), Image.BILINEAR)
        rgb = Image.new("RGB", (W, H), tuple(spec["color"]))
        hit = (rgb, a, (0, 0))
        self._shade[key] = hit
        return hit

    # ------------------------------------------------------------ ghost build
    def _ghost_build(self, ln):
        g = ln["ghost"]
        key = (ln["i"], self._row_scale_key())
        hit = self._ghost.get(key)
        if hit is not None:
            return hit
        f = 3  # low-res build factor
        size = g["size"] * self.S
        if g["vertical"]:
            row = build_v_row(g["text"], "jp600", None, size, g["tracking"] * self.S,
                              g["x"] * self.S, g["y"] * self.S, 1.0, pad=20)
        else:
            row = build_h_row(g["text"], "jp600", None, size,
                              max(0.8, size * g["tracking"]), g["x"] * self.S,
                              g["y"] * self.S, g["align"], 1.0, pad=40)
        bx0, by0, bx1, by1 = row["bbox"]
        lw = max(8, int((bx1 - bx0) / f) + 2)
        lh = max(8, int((by1 - by0) / f) + 2)
        mask = Image.new("L", (lw, lh), 0)
        d = ImageDraw.Draw(mask)
        for gl in row["glyphs"]:
            ft = load_font(gl["font_key"], max(6, gl["px"] // f), gl["weight"])
            px = gl["draw_x"] / f - bx0 / f
            py = gl["draw_y"] / f - by0 / f
            d.text((px, py), gl["ch"], font=ft, fill=255, anchor="ls")
        mask = mask.filter(ImageFilter.GaussianBlur(max(0.4, g["blur"] * self.S / f)))
        mask = mask.point(lambda v: int(v * g["alpha"]))
        layer = Image.new("RGBA", (lw, lh), tuple(g["tint"]) + (255,))
        layer.putalpha(mask)
        hit = (layer, (bx0, by0, bx1, by1), f)
        self._ghost[key] = hit
        return hit

    def _ghost_op(self, ln, t, line_alpha):
        g = ln["ghost"]
        if t < g["start"] or t > g["end"]:
            return None
        env = smoothstep_range(t, g["start"], g["start"] + 0.55) * \
              (1.0 - smoothstep_range(t, g["end"] - 0.5, g["end"]))
        if env <= 0.01:
            return None
        layer, bbox, f = self._ghost_build(ln)
        drift_x = 4.0 * math.sin(t * 0.25 + hash01("gdx", ln["i"]) * 6.28) * self.S
        drift_y = 2.5 * math.sin(t * 0.19 + hash01("gdy", ln["i"]) * 6.28) * self.S
        x0 = int(round(bbox[0] + drift_x))
        y0 = int(round(bbox[1] + drift_y))
        # clip against the frame
        cx0 = max(0, -x0)
        cy0 = max(0, -y0)
        cx1 = min(layer.width, self.W - x0)
        cy1 = min(layer.height, self.H - y0)
        if cx1 <= cx0 or cy1 <= cy0:
            return None
        rgb = layer.convert("RGB").crop((cx0, cy0, cx1, cy1))
        alpha = layer.getchannel("A").crop((cx0, cy0, cx1, cy1))
        tw, th = (cx1 - cx0) * f, (cy1 - cy0) * f
        rgb = rgb.resize((tw, th), Image.BILINEAR)
        alpha = alpha.resize((tw, th), Image.BILINEAR)
        k = clamp(env * line_alpha)
        alpha = alpha.point(lambda v: int(v * k))
        return (rgb, alpha, (x0 + cx0 * f, y0 + cy0 * f))

    # ---------------------------------------------------------------- public
    def render(self, f: int, t: float):
        """Return a list of (rgb, alpha, pos) paste ops, back-to-front."""
        ops = []
        # 1. active lyric line(s)
        for ln in self.lines:
            ts = ln["t"]
            te = ln["t_end"]
            if t < ts - 0.05 or t > te + 0.10:
                continue
            group = ln["group"]
            line_alpha = 1.0 - smoothstep_range(t, ln["fade_out_start"],
                                                ln["fade_out_start"] + ln["fade_out_dur"])
            if line_alpha <= 0.005:
                continue
            gop = self._ghost_op(ln, t, line_alpha)
            if gop is not None:
                ops.append(gop)
            for ri, rs in enumerate(ln["rows"]):
                op = self._render_row("L%d_%d" % (ln["i"], ri), rs, t, group,
                                      line_alpha, glow_boost=1.0)
                if op is not None:
                    ops.append(op)
        # 2. title card
        if self.title["t0"] - 0.02 <= t <= self.title["t1"] + 0.1:
            line_alpha = 1.0 - smoothstep_range(t, self.title["fade_out_start"],
                                                self.title["fade_out_start"] + self.title["fade_out_dur"])
            if line_alpha > 0.005:
                m = clamp((t - self.title["t0"]) / 0.55)
                shade_k = clamp(line_alpha * ease_out_cubic(m))
                sh = self.shade_op(self.title["shade"])
                if sh is not None and shade_k > 0.01:
                    ops.append((sh[0], alpha_scale(sh[1], shade_k), sh[2]))
                halo = self._halo_op(self.title["halo"])
                if halo is not None:
                    ops.append((halo[0], alpha_scale(halo[1], clamp(shade_k * 0.9)), halo[2]))
                for ri, rs in enumerate(self.title["rows"]):
                    if "rule" in rs:
                        op = self._render_rule("T%d" % ri, rs, t, line_alpha)
                    else:
                        op = self._render_row("T%d" % ri, rs, t, "gold", line_alpha,
                                              glow_boost=1.25)
                    if op is not None:
                        ops.append(op)
        # 3. credits
        if self.credits["t0"] - 0.02 <= t <= 272.97:
            line_alpha = 1.0 - smoothstep_range(t, self.credits["fade_out_start"],
                                                self.credits["fade_out_start"] + self.credits["fade_out_dur"])
            if line_alpha > 0.005:
                m = clamp((t - self.credits["t0"]) / 0.9)
                shade_k = clamp(line_alpha * ease_out_cubic(m))
                sh = self.shade_op(self.credits["shade"])
                if sh is not None and shade_k > 0.01:
                    ops.append((sh[0], alpha_scale(sh[1], shade_k), sh[2]))
                for ri, rs in enumerate(self.credits["rows"]):
                    if "rule" in rs:
                        op = self._render_rule("C%d" % ri, rs, t, line_alpha)
                    else:
                        op = self._render_row("C%d" % ri, rs, t, "cold", line_alpha,
                                              glow_boost=0.9)
                    if op is not None:
                        ops.append(op)
        return ops



if __name__ == "__main__":
    import sys
    from timeline import Timeline
    tl = Timeline()
    typo = Typography(tl, 1920, 1080, 1.0)
    typo.write_layout()
    print("wrote", LAYOUT_PATH)
    print("lines:", len(typo.lines))
    for i in (0, 4, 10, 18, 58):
        ln = typo.lines[i]
        print(i, ln["style"], "rows:", len(ln["rows"]),
              "bbox:", tuple(round(v) for v in ln["rows"][0]["row"]["bbox"]))
