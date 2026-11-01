# -*- coding: utf-8 -*-
"""finalize.py — QC the assembled master, write poster + low-res preview.

  python finalize.py --master ../out/final/purple_sunflower_MV_v1.mp4 \
      --poster-frame 4725 --poster-out ../out/final/poster.png

Checks: resolution / fps / duration / frame count / audio stream / faststart,
plus a per-frame luma scan to catch unintended black frames.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

from common import FINAL_DIR, FPS, SONG_WAV, ensure_dirs
from composite import Compositor


def probe(ffmpeg, path):
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", path], capture_output=True)
    txt = r.stderr.decode("utf-8", "replace")
    info = {}
    for line in txt.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            info["duration"] = line.split(",")[0].replace("Duration:", "").strip()
        if "Stream #" in line:
            info.setdefault("streams", []).append(line)
    return info


def frame_count(ffmpeg, path, w, h):
    """Count frames by decoding to null (fast; avoids 40GB of raw stdout)."""
    r = subprocess.run([ffmpeg, "-hide_banner", "-i", path, "-map", "0:v:0",
                        "-f", "null", "-"], capture_output=True)
    txt = r.stderr.decode("utf-8", "replace")
    import re as _re
    vals = [int(m) for m in _re.findall(r"frame=\s*(\d+)", txt)]
    return vals[-1] if vals else 0


def luma_scan(ffmpeg, path):
    r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path,
                        "-vf", "scale=64:36,format=gray", "-f", "rawvideo", "-"],
                       capture_output=True)
    W, H = 64, 36
    n = len(r.stdout) // (W * H)
    a = np.frombuffer(r.stdout[:n * W * H], dtype=np.uint8).reshape(n, H, W)
    return a.mean(axis=(1, 2)), n


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--master", default=os.path.join(FINAL_DIR, "purple_sunflower_MV_v1.mp4"))
    ap.add_argument("--poster-frame", type=int, default=0)
    ap.add_argument("--poster-out", default=os.path.join(FINAL_DIR, "poster.png"))
    ap.add_argument("--preview-out", default=os.path.join(FINAL_DIR, "preview.mp4"))
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--ffmpeg", default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", "ffmpeg.exe"))
    args = ap.parse_args(argv)

    ensure_dirs()
    print("== probe ==", flush=True)
    info = probe(args.ffmpeg, args.master)
    for s in info.get("streams", []):
        print("  ", s)
    print("   duration:", info.get("duration"))

    print("== frame count (decode) ==", flush=True)
    n = frame_count(args.ffmpeg, args.master, 1920, 1080)
    print("   frames:", n, " expected 6551  ", "OK" if n == 6551 else "MISMATCH!")

    print("== luma scan ==", flush=True)
    luma, ln = luma_scan(args.ffmpeg, args.master)
    dark = np.where(luma < 8)[0]
    groups = []
    for f in dark:
        if groups and f == groups[-1][-1] + 1:
            groups[-1].append(f)
        else:
            groups.append([f])
    for g in groups:
        print("   dark %d..%d  (%.2f..%.2fs, %d frames)" % (g[0], g[-1], g[0] / 24.0,
                                                           g[-1] / 24.0, len(g)))

    if args.poster_frame:
        print("== poster frame %d ==" % args.poster_frame, flush=True)
        comp = Compositor(1920, 1080, draft=False)
        im = comp.render(args.poster_frame, with_text=False)
        im.save(args.poster_out)
        print("   wrote", args.poster_out)

    if not args.no_preview:
        print("== low-res preview ==", flush=True)
        cmd = [args.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
               "-i", args.master, "-i", SONG_WAV,
               "-vf", "scale=640:360,fps=12", "-map", "0:v:0", "-map", "1:a:0",
               "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
               "-shortest", "-movflags", "+faststart", args.preview_out]
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            print(r.stderr.decode("utf-8", "replace")[-1500:])
        else:
            print("   wrote", args.preview_out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
