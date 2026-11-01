# -*- coding: utf-8 -*-
"""assemble.py — concatenate per-shot segments into the final MV (with audio).

  python assemble.py --out ../out/final/purple_sunflower_MV_v1.mp4
  python assemble.py --dry-run        # only report which segments are missing

Requires render_segments.py to have produced out/segments/<SID>.mp4 for every
shot.  Refuses to assemble unless all 57 shots are present (no placeholder
frames in the final film).
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import FINAL_DIR, FPS, SONG_WAV, ensure_dirs, save_json
from timeline import Timeline
from render_segments import plate_signature

SEG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "out", "segments")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--segdir", default=SEG_DIR)
    ap.add_argument("--out", default=os.path.join(FINAL_DIR, "purple_sunflower_MV_v1.mp4"))
    ap.add_argument("--audio", default=SONG_WAV)
    ap.add_argument("--abitrate", default="320k")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-missing", action="store_true",
                    help="assemble even with missing shots (preview only!)")
    ap.add_argument("--ffmpeg", default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", "ffmpeg.exe"))
    args = ap.parse_args(argv)

    ensure_dirs()
    tl = Timeline()
    sig_map = plate_signature(tl)
    segs = []
    missing = []
    stale = []
    total_frames = 0
    for shot in tl.shots:
        path = os.path.abspath(os.path.join(args.segdir, shot["id"] + ".mp4"))
        side = os.path.abspath(os.path.join(args.segdir, shot["id"] + ".json"))
        if os.path.exists(path):
            try:
                with open(side, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except (OSError, ValueError):
                meta = {}
            if meta.get("sig") != sig_map.get(shot["id"]):
                stale.append(shot["id"])
            segs.append((shot, path))
            total_frames += shot["nframes"]
        else:
            missing.append(shot["id"])
    # verify each segment duration matches its shot length
    corrupt = []
    for shot, path in segs:
        try:
            r = subprocess.run([args.ffmpeg, "-hide_banner", "-i", path],
                               capture_output=True)
            txt = r.stderr.decode("utf-8", "replace")
            dur = None
            for line in txt.splitlines():
                if line.strip().startswith("Duration:"):
                    hh, mm, ss = line.split("Duration:")[1].split(",")[0].strip().split(":")
                    dur = int(hh) * 3600 + int(mm) * 60 + float(ss)
                    break
            exp = shot["nframes"] / float(FPS)
            if dur is None or abs(dur - exp) > 0.12:
                corrupt.append("%s(%.2fs vs %.2fs)" % (shot["id"], dur or -1, exp))
        except Exception as exc:
            corrupt.append("%s(%s)" % (shot["id"], exc))
    if corrupt:
        print("corrupt/truncated segments:", " ".join(corrupt))
        if not args.allow_missing:
            print("refusing to assemble: re-render those segments")
            return 1
    print("segments: %d/%d   frames %d/%d (%.3fs)" % (
        len(segs), len(tl.shots), total_frames, tl.total_frames,
        total_frames / FPS))
    if stale:
        print("stale (plates changed since render):", " ".join(stale))
        if not args.allow_missing:
            print("refusing to assemble: re-render stale segments first (render_segments.py)")
            return 1
    if missing:
        print("missing:", " ".join(missing))
        if not args.allow_missing:
            print("refusing to assemble: %d shots missing (final must have no placeholders)"
                  % len(missing))
            return 1
    if args.dry_run:
        return 0

    tmpdir = os.path.join(os.path.dirname(os.path.abspath(args.out)), "_assemble")
    os.makedirs(tmpdir, exist_ok=True)
    listfile = os.path.join(tmpdir, "segments.txt")
    with open(listfile, "w", encoding="utf-8") as f:
        for shot, path in segs:
            f.write("file '%s'\n" % path.replace("\\", "/"))
    silent = os.path.join(tmpdir, "video_silent.mp4")
    cmd = [args.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", silent]
    print("concat:", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        print(r.stderr.decode("utf-8", "replace")[-3000:])
        return 1
    cmd = [args.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-i", silent, "-i", args.audio,
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
           "-c:a", "aac", "-b:a", args.abitrate, "-ar", "44100", "-ac", "2",
           "-shortest", "-movflags", "+faststart", args.out]
    print("mux:", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        print(r.stderr.decode("utf-8", "replace")[-3000:])
        return 1
    # verify
    probe = subprocess.run([args.ffmpeg, "-hide_banner", "-i", args.out],
                           capture_output=True)
    txt = probe.stderr.decode("utf-8", "replace")
    for line in txt.splitlines():
        if "Duration" in line or "Stream #" in line:
            print(line.strip())
    print("WROTE", args.out)
    save_json(os.path.join(tmpdir, "assemble.json"),
              dict(out=args.out, segments=[s["id"] for s, _ in segs],
                   missing=missing, frames=total_frames))
    return 0


if __name__ == "__main__":
    sys.exit(main())
