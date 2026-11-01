# -*- coding: utf-8 -*-
"""render_segments.py — incremental per-shot rendering for the final assembly.

Every shot is rendered to its own silent H.264 segment (out/segments/<SID>.mp4)
plus a small JSON sidecar.  When all 57 segments exist, assemble.py concatenates
them (lossless) and muxes the audio.  This allows re-rendering only the shots
whose plates changed / arrived later.

  python render_segments.py                     # all shots whose plates are complete
  python render_segments.py --shots S12 S19     # specific shots
  python render_segments.py --workers 4 --force # re-render everything
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (FINAL_DIR, FPS, FULL_H, FULL_W, OUT_DIR, PLATES_DIR, ensure_dirs,
                    load_json, save_json)
from composite import Compositor
from timeline import Timeline

SEG_DIR = os.path.join(OUT_DIR, "segments")


def video_args(args):
    return ["-c:v", "libx264", "-preset", args.preset, "-crf", str(args.crf),
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
            "-x264-params", "keyint=48:min-keyint=24:scenecut=40"]


def plate_signature(tl):
    """(file count, max mtime) per shot — used to detect changed/updated plates."""
    sig = {}
    for shot in tl.shots:
        d = os.path.join(PLATES_DIR, shot["id"])
        n = 0
        mx = 0.0
        if os.path.isdir(d):
            try:
                for name in os.listdir(d):
                    if name.lower().endswith((".png", ".jpg", ".jpeg")):
                        n += 1
                        try:
                            mx = max(mx, os.path.getmtime(os.path.join(d, name)))
                        except OSError:
                            pass
            except OSError:
                pass
        sig[shot["id"]] = "%d:%.0f" % (n, mx)
    return sig


def segment_complete(shot, seg_dir, sig_map=None):
    path = os.path.join(seg_dir, shot["id"] + ".mp4")
    side = os.path.join(seg_dir, shot["id"] + ".json")
    if not (os.path.exists(path) and os.path.exists(side)):
        return False
    try:
        with open(side, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError):
        return False
    if meta.get("frames") != shot["nframes"] or meta.get("f0") != shot["f0"]:
        return False
    if sig_map is not None and meta.get("sig") != sig_map.get(shot["id"]):
        return False
    return True


def render_shot(comp, shot, args, W, H, seg_dir, log, tag="", sig_map=None):
    f0, f1 = shot["f0"], shot["f1"]
    frames = list(range(f0, f1 + 1))
    out = os.path.join(seg_dir, shot["id"] + ".mp4")
    tmp = out + ".tmp.mp4"
    cmd = [args.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
           "-r", str(FPS), "-i", "-"] + video_args(args) + ["-movflags", "+faststart", tmp]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    t0 = time.time()
    done = 0
    try:
        for f in frames:
            img = comp.render(f)
            proc.stdin.write(img.tobytes())
            done += 1
            if done % 100 == 0:
                log("%s%s %4d/%4d  %.3fs/frame" % (tag, shot["id"], done, len(frames),
                                                   (time.time() - t0) / done))
    except BrokenPipeError:
        log("%s%s ffmpeg closed pipe" % (tag, shot["id"]))
        proc.kill()
        return False
    except Exception:
        log("%s%s ERROR\n%s" % (tag, shot["id"], traceback.format_exc()))
        proc.kill()
        return False
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
    proc.wait()
    if proc.returncode != 0:
        log("%s%s ffmpeg failed: %s" % (tag, shot["id"],
                                        proc.stderr.read().decode("utf-8", "replace")[-800:]))
        return False
    os.replace(tmp, out)
    save_json(os.path.join(seg_dir, shot["id"] + ".json"),
              dict(shot=shot["id"], f0=f0, f1=f1, frames=len(frames), w=W, h=H,
                   preset=args.preset, crf=args.crf,
                   sig=(sig_map or {}).get(shot["id"]),
                   rendered_at=time.strftime("%Y-%m-%d %H:%M:%S")))
    log("%s%s DONE %d frames in %.1fs" % (tag, shot["id"], len(frames),
                                          time.time() - t0))
    return True


def _worker(idx, shots, args, W, H, seg_dir, log_path, sig_map=None):
    logf = open(log_path, "w", encoding="utf-8")

    def log(msg):
        logf.write(msg + "\n")
        logf.flush()

    tag = "[w%d] " % idx
    try:
        comp = Compositor(W, H, allow_dummy=False, draft=args.draft)
        ok = True
        for shot in shots:
            if not render_shot(comp, shot, args, W, H, seg_dir, log, tag, sig_map):
                ok = False
                break
        log("%sFINISHED %s" % (tag, "ok" if ok else "with errors"))
        return 0 if ok else 1
    except Exception:
        log("%sFATAL\n%s" % (tag, traceback.format_exc()))
        return 1
    finally:
        logf.close()


def shots_with_complete_plates(tl, args):
    """Shots whose every frame resolves to a real plate file."""
    from plates import PlateProvider
    prov = PlateProvider(tl, 64, 36, allow_dummy=False)
    out = []
    for shot in tl.shots:
        if shot["id"] not in prov.real:
            continue
        missing = 0
        for local in range(1, shot["nframes"] + 1):
            if prov._resolve_number(shot, local) is None:
                missing += 1
                if missing > 0:
                    break
        if missing == 0:
            out.append(shot)
        elif args.report:
            print("  partial %s: %d/%d frames" % (shot["id"],
                  len(prov.real[shot["id"]]), shot["nframes"]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", nargs="*", default=None)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="slow")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-render existing segments")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--segdir", default=SEG_DIR)
    ap.add_argument("--ffmpeg", default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", "ffmpeg.exe"))
    args = ap.parse_args(argv)

    ensure_dirs()
    os.makedirs(args.segdir, exist_ok=True)
    W = int(round(FULL_W * args.scale)) // 2 * 2
    H = int(round(FULL_H * args.scale)) // 2 * 2
    tl = Timeline()
    sig_map = plate_signature(tl)

    if args.shots:
        by_id = {s["id"]: s for s in tl.shots}
        shots = [by_id[s] for s in args.shots if s in by_id]
    else:
        print("scanning plates for complete shots ...")
        shots = shots_with_complete_plates(tl, args)
    if not args.force:
        todo = [s for s in shots if not segment_complete(s, args.segdir, sig_map)]
        skipped = [s for s in shots if segment_complete(s, args.segdir, sig_map)]
    else:
        todo, skipped = shots, []
    print("shots to render: %d   already done: %d" % (len(todo), len(skipped)))
    if not todo:
        print("nothing to do")
        return 0
    total = sum(s["nframes"] for s in todo)
    print("frames: %d  (%.1f min at 0.3s/frame single process)" % (total, total * 0.3 / 60))

    log_path = os.path.join(OUT_DIR, "logs",
                            "segments_%s.log" % time.strftime("%H%M%S"))
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logf = open(log_path, "w", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    log("=" * 78)
    log("segments: %d shots, %d frames, %dx%d, workers=%d, crf=%d preset=%s" % (
        len(todo), total, W, H, args.workers, args.crf, args.preset))
    log("segdir: %s" % args.segdir)
    t_start = time.time()

    if args.workers <= 1:
        comp = Compositor(W, H, allow_dummy=False, draft=args.draft)
        for i, shot in enumerate(todo):
            log("[%d/%d] %s" % (i + 1, len(todo), shot["id"]))
            if not render_shot(comp, shot, args, W, H, args.segdir, log, "", sig_map):
                log("render failed on %s" % shot["id"])
                return 1
    else:
        import multiprocessing as mp
        n = max(1, min(args.workers, len(todo)))
        chunks = [[] for _ in range(n)]
        for i, s in enumerate(todo):
            chunks[i % n].append(s)
        tmpdir = os.path.join(OUT_DIR, "tmp", time.strftime("seg_%H%M%S"))
        os.makedirs(tmpdir, exist_ok=True)
        procs = []
        for i in range(n):
            p = mp.get_context("spawn").Process(
                target=_worker,
                args=(i, chunks[i], args, W, H, args.segdir,
                      os.path.join(tmpdir, "w%d.log" % i), sig_map))
            p.start()
            procs.append(p)
        while any(p.is_alive() for p in procs):
            time.sleep(20)
            for i in range(n):
                try:
                    with open(os.path.join(tmpdir, "w%d.log" % i), "r", encoding="utf-8") as f:
                        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
                    if lines:
                        log("  " + lines[-1])
                except OSError:
                    pass
        codes = [p.exitcode for p in procs]
        for p in procs:
            p.join()
        if any(c != 0 for c in codes):
            log("worker failures: %s" % codes)
            return 1
    wall = time.time() - t_start
    done = [s for s in todo if segment_complete(s, args.segdir, sig_map)]
    log("DONE: %d/%d segments in %.1fs (%.1f min)" % (len(done), len(todo), wall, wall / 60))
    logf.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
