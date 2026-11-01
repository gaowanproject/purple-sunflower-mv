# -*- coding: utf-8 -*-
"""QC: check every shot's plate folder for frame continuity and report gaps.
usage: python tools/qc_frames.py [--missing-only]
"""
import json, os, glob, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOTS = json.load(open(os.path.join(ROOT, "story", "shots.json"), encoding="utf-8"))["shots"]

rows = []
for s in SHOTS:
    sid = s["id"]
    d = os.path.join(ROOT, "plates", sid)
    have = set()
    if os.path.isdir(d):
        for p in glob.glob(os.path.join(d, "*.png")):
            b = os.path.basename(p)[len(sid) + 1:-4]
            if b.isdigit():
                have.add(int(b))
    need = set(range(s["f0"], s["f1"] + 1))
    missing = sorted(need - have)
    extra = sorted(have - need)
    rows.append((sid, s["f0"], s["f1"], len(need), len(have & need), len(missing),
                 s["team"], s["set"], s["variant"]))

missing_only = "--missing-only" in sys.argv
print(f"{'shot':6s} {'range':>13s} {'need':>5s} {'have':>5s} {'miss':>5s}  team set/variant")
tot_need = tot_have = 0
for sid, f0, f1, n, h, m, team, st, var in rows:
    tot_need += n
    tot_have += h
    if missing_only and m == 0:
        continue
    print(f"{sid:6s} {f0:>6d}-{f1:<6d} {n:5d} {h:5d} {m:5d}  {team} {st}/{var}")
print(f"\nTOTAL {tot_have}/{tot_need} frames = {100.0*tot_have/tot_need:.1f}%")
