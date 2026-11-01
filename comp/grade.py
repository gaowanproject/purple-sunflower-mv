# -*- coding: utf-8 -*-
"""grade.py — per-variant film-look grading (LUT based, numpy/PIL, fast).

Colour world of the MV
----------------------
warm gold  =  memory / the summer that no longer exists
violet-blue =  the present, the hallucination, the love that cannot be let go

Every shot carries a `variant` in shots.json; the grade below builds a
per-channel 3x256 LUT (exposure -> white balance -> gain/offset -> gamma ->
contrast S-curve -> soft shoulder -> highlight tint) plus a saturation step.
"""
from __future__ import annotations

import math

from PIL import Image, ImageEnhance

from common import FPS, clamp, load_json, smoothstep

# ------------------------------------------------------------------ parameters
# exposure : linear exposure multiplier
# wb       : per-channel white balance (R,G,B)
# contrast : S-curve amount  (-1..1)
# sat      : saturation multiplier (1 = neutral)
# offset   : per-channel shadow offset (added, weighted toward blacks)
# gain     : per-channel gain
# gamma    : per-channel exponent (>1 darker mids, <1 brighter mids)
# black    : black-lift amount (0..0.1)
# shoulder : highlight soft-clip amount (0..1)
# tint_hi  : per-channel additive highlight tint (weighted by x^3)
GRADES = {
    # ------- gold world: amber highlights, honey mids, teal/olive shadows -----
    "noon_hot": dict(exposure=1.00, wb=(1.060, 1.0, 0.905), contrast=0.28, sat=1.18,
                     offset=(-0.014, 0.012, 0.022), gain=(1.065, 1.020, 0.880),
                     gamma=(0.940, 0.995, 1.045), black=0.010, shoulder=0.62,
                     tint_hi=(0.072, 0.030, 0.0)),
    "noon_side": dict(exposure=1.00, wb=(1.048, 1.0, 0.918), contrast=0.26, sat=1.14,
                      offset=(-0.012, 0.012, 0.022), gain=(1.055, 1.015, 0.895),
                      gamma=(0.945, 0.997, 1.045), black=0.012, shoulder=0.60,
                      tint_hi=(0.062, 0.026, 0.0)),
    "gold_noon": dict(exposure=1.00, wb=(1.050, 1.0, 0.915), contrast=0.27, sat=1.18,
                      offset=(-0.014, 0.012, 0.026), gain=(1.060, 1.020, 0.885),
                      gamma=(0.940, 0.995, 1.045), black=0.012, shoulder=0.62,
                      tint_hi=(0.070, 0.030, 0.0)),
    "gold_dusk": dict(exposure=1.00, wb=(1.065, 0.992, 0.890), contrast=0.28, sat=1.16,
                      offset=(-0.016, 0.010, 0.028), gain=(1.070, 1.010, 0.875),
                      gamma=(0.950, 0.995, 1.040), black=0.012, shoulder=0.58,
                      tint_hi=(0.078, 0.032, 0.006)),
    "dusk_afterglow": dict(exposure=1.00, wb=(1.055, 0.992, 0.905), contrast=0.27, sat=1.12,
                           offset=(-0.014, 0.011, 0.026), gain=(1.060, 1.010, 0.880),
                           gamma=(0.950, 0.997, 1.042), black=0.012, shoulder=0.58,
                           tint_hi=(0.070, 0.028, 0.008)),
    "macro_warm": dict(exposure=1.00, wb=(1.045, 1.0, 0.918), contrast=0.24, sat=1.12,
                       offset=(-0.012, 0.012, 0.024), gain=(1.055, 1.010, 0.898),
                       gamma=(0.945, 0.997, 1.042), black=0.014, shoulder=0.58,
                       tint_hi=(0.062, 0.026, 0.0)),
    # ---------------- violet world: blue-violet shadows, pink-violet highlights -
    "violet_dusk": dict(exposure=1.00, wb=(0.98, 0.955, 1.05), contrast=0.27, sat=1.00,
                        offset=(0.004, -0.004, 0.040), gain=(1.03, 0.965, 1.05),
                        gamma=(1.025, 1.0, 0.955), black=0.012, shoulder=0.22,
                        tint_hi=(0.055, 0.008, 0.055)),
    "violet_night": dict(exposure=1.00, wb=(0.955, 0.945, 1.07), contrast=0.29, sat=1.02,
                         offset=(0.006, -0.006, 0.046), gain=(1.035, 0.955, 1.06),
                         gamma=(1.03, 1.0, 0.95), black=0.016, shoulder=0.18,
                         tint_hi=(0.045, 0.006, 0.060)),
    "petals_dark": dict(exposure=1.00, wb=(0.96, 0.94, 1.09), contrast=0.30, sat=0.98,
                        offset=(0.004, -0.004, 0.042), gain=(1.02, 0.955, 1.07),
                        gamma=(1.03, 1.0, 0.945), black=0.012, shoulder=0.16,
                        tint_hi=(0.05, 0.005, 0.06)),
    # ---------------- cold / night world --------------------------------------
    "rain_night": dict(exposure=1.00, wb=(0.95, 0.97, 1.07), contrast=0.26, sat=0.80,
                       offset=(0.004, 0.008, 0.034), gain=(0.975, 1.0, 1.045),
                       gamma=(1.0, 1.0, 0.985), black=0.014, shoulder=0.24,
                       tint_hi=(0.014, 0.018, 0.044)),
    "night_rain": dict(exposure=1.00, wb=(0.955, 0.975, 1.065), contrast=0.24, sat=0.84,
                       offset=(0.006, 0.008, 0.032), gain=(0.97, 1.0, 1.045),
                       gamma=(1.0, 1.0, 0.99), black=0.015, shoulder=0.24,
                       tint_hi=(0.012, 0.018, 0.040)),
    "night_dark": dict(exposure=1.00, wb=(0.955, 0.97, 1.05), contrast=0.32, sat=0.62,
                       offset=(0.002, 0.004, 0.024), gain=(0.95, 1.0, 1.055),
                       gamma=(1.03, 1.0, 0.98), black=0.008, shoulder=0.18,
                       tint_hi=(0.010, 0.010, 0.030)),
    "night_lamp": dict(exposure=1.00, wb=(1.02, 1.0, 1.01), contrast=0.22, sat=0.96,
                       offset=(0.012, 0.004, 0.026), gain=(1.05, 1.0, 0.965),
                       gamma=(1.0, 1.0, 0.995), black=0.012, shoulder=0.30,
                       tint_hi=(0.038, 0.014, 0.0)),
    "macro_cold": dict(exposure=1.00, wb=(0.92, 0.98, 1.09), contrast=0.22, sat=0.82,
                       offset=(0.0, 0.010, 0.030), gain=(0.96, 1.0, 1.07),
                       gamma=(1.0, 1.0, 0.99), black=0.014, shoulder=0.22,
                       tint_hi=(0.0, 0.020, 0.044)),
    "city_bridge": dict(exposure=1.00, wb=(0.97, 1.0, 1.03), contrast=0.26, sat=0.50,
                        offset=(0.004, 0.008, 0.022), gain=(0.98, 1.0, 1.02),
                        gamma=(1.02, 1.0, 1.0), black=0.010, shoulder=0.26,
                        tint_hi=(0.020, 0.014, 0.016)),
}

DEFAULT_GRADE = GRADES["gold_noon"]

_LUT_CACHE: dict = {}
_GAIN_CACHE: dict = {}


def _channel_lut(p: dict, exposure: float, c: int) -> list:
    """Build one 256 entry channel LUT (list of ints)."""
    wb = p["wb"][c]
    gain = p["gain"][c]
    offset = p["offset"][c]
    gamma = p["gamma"][c]
    tint = p["tint_hi"][c]
    contrast = p["contrast"]
    black = p["black"]
    shoulder = p["shoulder"]
    out = []
    for i in range(256):
        x = i / 255.0
        # exposure + white balance + gain
        x = x * exposure * wb * gain
        # shadow weighted offset
        x = x + offset * (1.0 - clamp(x))
        if x < 0.0:
            x = 0.0
        elif x > 1.0:
            x = 1.0
        # gamma
        if gamma != 1.0:
            x = x ** gamma
        # black lift
        if black > 0.0:
            x = x * (1.0 - black) + black
        # contrast S-curve (in display space)
        if contrast != 0.0:
            x = x + contrast * (smoothstep(x) - x)
        # highlight tint
        if tint:
            x = x + tint * (x ** 3)
        # soft shoulder
        if shoulder > 0.0 and x > 0.7:
            u = clamp((x - 0.7) / 0.3)
            soft = 0.7 + 0.3 * (1.0 - (1.0 - u) ** 2)
            x = x + shoulder * (soft - x)
        if x < 0.0:
            x = 0.0
        elif x > 1.0:
            x = 1.0
        out.append(int(round(x * 255.0)))
    return out


def get_lut(variant: str, exposure: float = 1.0) -> list:
    """768-entry RGB point LUT for (variant, exposure). Cached."""
    p = GRADES.get(variant, DEFAULT_GRADE)
    # quantise exposure so the cache stays small
    q = int(round(clamp(exposure, 0.0, 3.0) * 512))
    key = (variant, q)
    lut = _LUT_CACHE.get(key)
    if lut is not None:
        return lut
    e = q / 512.0
    lut = _channel_lut(p, e, 0) + _channel_lut(p, e, 1) + _channel_lut(p, e, 2)
    if len(_LUT_CACHE) > 4096:
        _LUT_CACHE.clear()
    _LUT_CACHE[key] = lut
    return lut


def grade(im: Image.Image, variant: str, exposure: float = 1.0,
          sat_mul: float = 1.0) -> Image.Image:
    """Apply the variant grade to an RGB image."""
    p = GRADES.get(variant, DEFAULT_GRADE)
    out = im.point(get_lut(variant, exposure))
    sat = p["sat"] * sat_mul
    if abs(sat - 1.0) > 0.01:
        out = ImageEnhance.Color(out).enhance(sat)
    return out


# ------------------------------------------------------------------ utilities
def gain_lut(exposure: float) -> list:
    """Simple 3x256 multiply LUT, for fades / exposure ramps."""
    q = int(round(clamp(exposure, 0.0, 1.5) * 512))
    lut = _GAIN_CACHE.get(q)
    if lut is not None:
        return lut
    e = q / 512.0
    one = [min(255, max(0, int(round(i * e)))) for i in range(256)]
    lut = one * 3
    _GAIN_CACHE[q] = lut
    return lut


def apply_gain(im: Image.Image, exposure: float) -> Image.Image:
    if abs(exposure - 1.0) < 0.002:
        return im
    return im.point(gain_lut(exposure))


def lerp_color(a, b, t):
    t = clamp(t)
    return tuple(int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3))


if __name__ == "__main__":
    from common import load_json as _lj
    shots = _lj("story/shots.json", {})["shots"]
    variants = sorted({s["variant"] for s in shots})
    print("variants:", variants)
    for v in variants:
        print("  %-15s %s" % (v, GRADES.get(v, "MISSING")))
