# -*- coding: utf-8 -*-
"""preview.py — quick review render (640x360, every 2nd frame) with audio.

Output name:
  out/final/preview.mp4        when every shot has real plates
  out/final/preview_dummy.mp4  when some shots still use procedural plates
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import FINAL_DIR, ensure_dirs
from composite import Compositor
import render_final


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--scale", type=float, default=1.0 / 3.0)
    ap.add_argument("--fps-div", type=int, default=2)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=0)
    ap.add_argument("--crf", type=int, default=23)
    ap.add_argument("--preset", default="veryfast")
    ap.add_argument("--out", default="")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args(argv)

    ensure_dirs()
    # decide dummy vs real
    comp = Compositor(192, 108, draft=True)
    cov = comp.plates.coverage()
    dummy = cov["shots_with_plates"] < cov["shots_total"]
    out = args.out or os.path.join(FINAL_DIR, "preview_dummy.mp4" if dummy else "preview.mp4")
    print("preview: %d/%d shots have real plates -> %s" % (
        cov["shots_with_plates"], cov["shots_total"], "dummy" if dummy else "real"))
    argv2 = ["--out", out,
             "--scale", str(args.scale),
             "--fps-div", str(args.fps_div),
             "--crf", str(args.crf),
             "--preset", args.preset,
             "--draft",
             "--start", str(args.start),
             "--end", str(args.end),
             "--workers", str(args.workers)]
    if args.no_audio:
        argv2.append("--no-audio")
    return render_final.main(argv2)


if __name__ == "__main__":
    sys.exit(main())
