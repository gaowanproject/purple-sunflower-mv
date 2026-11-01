# -*- coding: utf-8 -*-
"""timeline.py — single source of truth for time, shots and transitions.

Public surface
--------------
Timeline()
    .shots / .lyrics            raw story data
    .shot_index_at_frame(f)     index into .shots
    .shot_at_frame(f)           dict
    .local_frame(shot, f)       1..nframes (clamped)
    .plan(f)                    composition plan for frame f
    .global_exposure(f)         intro / outro master fade
    .shot_fx(shot, t_local)     per-shot exposure / glow curves
    .motion(shot)               procedural camera move (placeholder plates)
    .pulse(t) / .energy(t)      music envelope helpers
"""
from __future__ import annotations

import math
import os

from common import (DURATION, FPS, ROOT, STORY_DIR, clamp, ease_in_out,
                    frame_to_time, load_json, smoothstep, smoothstep_range,
                    time_to_frame, vnoise, audio)

EDIT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "edit.json")
SHOTS_PATH = os.path.join(STORY_DIR, "shots.json")
LYRICS_PATH = os.path.join(STORY_DIR, "lyrics.json")

# --------------------------------------------------------------------- edit.json
# Transition table. `at` is the time of the first frame of shot B (B.t0).
# Window = [b0 - pre, b0 + post - 1] frames, mix m goes 0 -> 1 across it.
DEFAULT_EDIT = {
    "version": 2,
    "fps": FPS,
    "total_frames": 6551,
    "global": {
        "fade_in": {"start": 0.0, "end": 1.6},
        "fade_out": {"start": 270.9, "end": 272.95},
    },
    "transitions": [
        {"a": "S03", "b": "S04", "at": 18.029, "type": "light_bleed", "pre": 12, "post": 12},
        {"a": "S19", "b": "S20", "at": 87.516, "type": "ripple", "pre": 10, "post": 10},
        {"a": "S22", "b": "S23", "at": 104.261, "type": "dissolve", "pre": 8, "post": 8},
        {"a": "S30", "b": "S31", "at": 138.789, "type": "white_flash", "pre": 5, "post": 7},
        {"a": "S42", "b": "S43", "at": 190.785, "type": "from_black", "pre": 16, "post": 26},
        {"a": "S54", "b": "S55", "at": 248.0, "type": "dissolve", "pre": 22, "post": 22},
        {"a": "S56", "b": "S57", "at": 263.5, "type": "to_black", "pre": 24, "post": 30},
    ],
}

# camera keyword -> procedural move for dummy plates
_MOVE_RULES = [
    ("push-in", dict(zoom=(1.0, 1.085), pan=(0.0, 0.0))),
    ("push in", dict(zoom=(1.0, 1.085), pan=(0.0, 0.0))),
    ("push-in on dried", dict(zoom=(1.02, 1.10), pan=(0.0, 0.0))),
    ("crane up", dict(zoom=(1.06, 1.0), pan=(0.0, 0.05))),
    ("tilt down", dict(zoom=(1.04, 1.0), pan=(0.0, 0.05))),
    ("tilt up", dict(zoom=(1.0, 1.02), pan=(0.0, -0.04))),
    ("rises fast", dict(zoom=(1.10, 1.0), pan=(0.0, -0.06))),
    ("drift r", dict(zoom=(1.0, 1.03), pan=(0.05, 0.0))),
    ("drift", dict(zoom=(1.0, 1.03), pan=(0.03, 0.0))),
    ("orbit", dict(zoom=(1.04, 1.02), pan=(0.04, 0.01))),
    ("slow zoom", dict(zoom=(1.0, 1.12), pan=(0.0, 0.0))),
    ("tracking", dict(zoom=(1.02, 1.04), pan=(-0.05, 0.0), shake=0.6)),
    ("wide", dict(zoom=(1.0, 1.04), pan=(0.02, 0.0))),
    ("macro", dict(zoom=(1.03, 1.08), pan=(0.01, 0.0))),
]
_SHAKE_RULES = ("shake", "tracking", "running")


class Timeline:
    def __init__(self, shots_path=SHOTS_PATH, lyrics_path=LYRICS_PATH, edit_path=EDIT_PATH):
        data = load_json(shots_path, None)
        if not data:
            raise SystemExit("timeline: cannot read %s" % shots_path)
        self.fps = data.get("fps", FPS)
        self.total_frames = data.get("total_frames", 6551)
        self.duration = data.get("duration", DURATION)
        self.resolution = tuple(data.get("resolution", (1920, 1080)))
        self.shots = data["shots"]
        self.lyrics = load_json(lyrics_path, []) or []
        self.edit = load_json(edit_path, None) or DEFAULT_EDIT
        self.transitions = [dict(t) for t in self.edit.get("transitions", [])]
        self.global_cfg = self.edit.get("global", DEFAULT_EDIT["global"])
        self._by_id = {s["id"]: s for s in self.shots}
        self._idx_by_id = {s["id"]: i for i, s in enumerate(self.shots)}
        self._ends = [s["f1"] for s in self.shots]
        # resolve transition frame windows
        for tr in self.transitions:
            b = self._by_id[tr["b"]]
            tr["b0"] = b["f0"]
            tr["a0"] = self._by_id[tr["a"]]["f0"]
            tr["start"] = b["f0"] - int(tr.get("pre", 8))
            tr["end"] = b["f0"] + int(tr.get("post", 8)) - 1
        self._audio = audio()

    # ------------------------------------------------------------------ shots
    def shot_index_at_frame(self, f: int) -> int:
        f = int(min(max(f, 1), self.total_frames))
        lo, hi = 0, len(self.shots) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if f > self.shots[mid]["f1"]:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def shot_at_frame(self, f: int):
        return self.shots[self.shot_index_at_frame(f)]

    def local_frame(self, shot, f: int) -> int:
        return int(min(max(f - shot["f0"] + 1, 1), shot["nframes"]))

    def shot_progress(self, shot, f: int) -> float:
        n = max(1, shot["nframes"] - 1)
        return clamp((f - shot["f0"]) / n)

    def shot_by_id(self, sid: str):
        return self._by_id[sid]

    def shot_index(self, shot) -> int:
        return self._idx_by_id[shot["id"]]

    # ------------------------------------------------------------- transitions
    def transition_at(self, f: int):
        """Return dict(type, a, b, m, a_local, b_local) or None."""
        for tr in self.transitions:
            if tr["start"] <= f <= tr["end"]:
                span = max(1, tr["end"] - tr["start"] + 1)
                m = (f - tr["start"] + 0.5) / span
                a = self._by_id[tr["a"]]
                b = self._by_id[tr["b"]]
                return {
                    "type": tr["type"],
                    "a": a,
                    "b": b,
                    "m": clamp(m),
                    "a_local": self.local_frame(a, f),
                    "b_local": self.local_frame(b, f),
                    "pre": tr.get("pre", 8),
                    "post": tr.get("post", 8),
                    "start": tr["start"],
                    "end": tr["end"],
                }
        return None

    def transition_frames(self) -> int:
        n = 0
        for tr in self.transitions:
            n += tr["end"] - tr["start"] + 1
        return n

    # ------------------------------------------------------------- global fade
    def global_exposure(self, f: int) -> float:
        t = frame_to_time(f)
        g = self.global_cfg
        fi = g.get("fade_in", {})
        fo = g.get("fade_out", {})
        e = 1.0
        if fi:
            e *= smoothstep_range(t, fi["start"], fi["end"])
        if fo:
            e *= 1.0 - smoothstep_range(t, fo["start"], fo["end"])
        return clamp(e)

    # -------------------------------------------------------------- shot fx
    def shot_fx(self, shot, f: int) -> dict:
        """Per-shot exposure / additive glow curves (beyond grading)."""
        p = self.shot_progress(shot, f)
        t = frame_to_time(f)
        sid = shot["id"]
        out = {"exposure": 1.0, "glow": None, "glow_amt": 0.0,
               "bloom_boost": 1.0, "sat_boost": 1.0}
        if sid == "S03":                       # light leak grows to white-gold
            g = smoothstep_range(p, 0.45, 1.0)
            out["glow"] = (255, 214, 150)
            out["glow_amt"] = 0.42 * g
            out["exposure"] = 1.0 + 0.16 * g
            out["bloom_boost"] = 1.0 + 0.9 * g
        elif sid == "S30":                     # accelerating cut montage
            out["bloom_boost"] = 1.0 + 0.18 * self._audio.pulse(t, 0.10) * smoothstep_range(p, 0.2, 1.0)
        elif sid == "S42":                     # slow zoom into black
            g = smoothstep_range(p, 0.30, 1.0)
            out["exposure"] = 1.0 - 0.985 * g
            out["glow"] = (120, 90, 170)
            out["glow_amt"] = 0.10 * g
        elif sid == "S47":                     # light engulfs
            g = smoothstep_range(p, 0.55, 1.0)
            out["exposure"] = 1.0 + 0.30 * g
            out["glow"] = (255, 236, 205)
            out["glow_amt"] = 0.65 * g
            out["bloom_boost"] = 1.0 + 1.3 * g
        elif sid == "S49":                     # pulses with the beat
            pulse = self._audio.pulse(t, 0.16)
            out["bloom_boost"] = 1.0 + 0.30 * pulse
            out["exposure"] = 1.0 + 0.025 * pulse
        elif sid == "S52" or sid == "S53":
            out["bloom_boost"] = 1.0 + 0.10 * self._audio.pulse(t, 0.20)
        elif sid == "S55":
            out["exposure"] = 1.0 - 0.06 * smoothstep_range(p, 0.6, 1.0)
        elif sid == "S56":                     # title card
            out["exposure"] = 0.94
            out["bloom_boost"] = 1.05
        elif sid == "S57":                     # credits / fade to black
            out["exposure"] = 1.0 - 0.30 * smoothstep_range(p, 0.05, 0.85)
        return out

    # -------------------------------------------------------------- motion
    def motion(self, shot) -> dict:
        """Procedural camera move used by the dummy plate provider."""
        cam = shot.get("camera", "").lower()
        mv = dict(zoom=(1.0, 1.04), pan=(0.0, 0.0), shake=0.0)
        best = -1
        for key, val in _MOVE_RULES:
            if key in cam and len(key) > best:
                best = len(key)
                mv = dict(zoom=val["zoom"], pan=val.get("pan", (0.0, 0.0)),
                          shake=val.get("shake", 0.0))
        if any(k in cam for k in _SHAKE_RULES):
            mv["shake"] = max(mv.get("shake", 0.0), 0.5)
        if "high-speed" in cam or "120fps" in cam:
            mv["zoom"] = (mv["zoom"][0], mv["zoom"][0] + (mv["zoom"][1] - mv["zoom"][0]) * 0.5)
        return mv

    def weave_offset(self, f: int, amp: float = 0.55) -> tuple:
        """Sub-pixel gate weave (no text layer is affected)."""
        t = f / self.fps
        dx = amp * (0.55 * vnoise(t * 2.1, 11.0) + 0.45 * math.sin(t * 5.1 + 0.7))
        dy = amp * (0.55 * vnoise(t * 1.7, 23.0) + 0.45 * math.sin(t * 4.3 + 2.1))
        return dx, dy

    # ------------------------------------------------------------ music helpers
    @property
    def audio(self):
        return self._audio

    def pulse(self, t: float, decay: float = 0.14) -> float:
        return self._audio.pulse(t, decay)

    def energy(self, t: float) -> float:
        return self._audio.rms_at(t)

    def section_intensity(self, f: int) -> float:
        """0..1 rough intensity of the current section (rms smoothed)."""
        t = frame_to_time(f)
        e = self._audio.rms_at(t)
        return clamp(e * 1.6)

    # ------------------------------------------------------------------ plan
    def plan(self, f: int) -> dict:
        """Everything the compositor needs for frame ``f`` (1-based)."""
        f = int(min(max(f, 1), self.total_frames))
        shot = self.shot_at_frame(f)
        tr = self.transition_at(f)
        exposure = self.global_exposure(f)
        if tr is not None:
            a_fx = self.shot_fx(tr["a"], f)
            b_fx = self.shot_fx(tr["b"], f)
            tr["a_fx"] = a_fx
            tr["b_fx"] = b_fx
        return {"frame": f, "t": frame_to_time(f), "shot": shot,
                "local": self.local_frame(shot, f), "transition": tr,
                "exposure": exposure,
                "fx": self.shot_fx(shot, f)}


if __name__ == "__main__":
    tl = Timeline()
    print("shots:", len(tl.shots), "lyrics:", len(tl.lyrics))
    print("transition frames:", tl.transition_frames())
    for tr in tl.transitions:
        print("  %s->%s %-12s frames %d..%d" % (tr["a"], tr["b"], tr["type"], tr["start"], tr["end"]))
    # smoke test plan mapping
    for f in (1, 149, 150, 279, 434, 2101, 3332, 4580, 6157, 6551):
        p = tl.plan(f)
        print("f%-5d %s local %-3d trans %s exp %.2f" % (
            f, p["shot"]["id"], p["local"],
            p["transition"]["type"] if p["transition"] else "-", p["exposure"]))
