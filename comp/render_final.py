# -*- coding: utf-8 -*-
"""render_final.py — composite every frame and pipe raw RGB straight into ffmpeg.

Single process:
  python render_final.py --out ../out/final/purple_sunflower_MV_v1.mp4
Parallel (4 workers, each encodes a segment, then lossless concat + audio mux):
  python render_final.py --workers 4
Preview:
  python render_final.py --scale 0.5 --fps-div 2 --draft --preset veryfast
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from common import (FINAL_DIR, FPS, FULL_H, FULL_W, OUT_DIR, SONG_WAV, ensure_dirs)
from composite import Compositor

TOTAL_FRAMES = 6551


# --------------------------------------------------------------------- ffmpeg
def _video_args(args):
    return ["-c:v", args.vcodec, "-preset", args.preset, "-crf", str(args.crf),
            "-pix_fmt", "yuv420p", "-profile:v", "high", "-level", "4.1",
            "-x264-params", "keyint=48:min-keyint=24:scenecut=40"]


def build_encode_cmd(args, W, H, out_path, with_audio):
    cmd = [args.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", "%dx%d" % (W, H), "-r", str(FPS / args.fps_div), "-i", "-"]
    if with_audio:
        cmd += ["-i", args.audio]
    cmd += ["-map", "0:v:0"] + _video_args(args)
    if with_audio:
        cmd += ["-map", "1:a:0", "-c:a", "aac", "-b:a", args.abitrate,
                "-ar", "44100", "-ac", "2", "-shortest"]
    cmd += ["-movflags", "+faststart", out_path]
    return cmd


# ---------------------------------------------------------------------- worker
def _render_frames(comp, frames, args, W, H, out_path, with_audio, log, tag=""):
    cmd = build_encode_cmd(args, W, H, out_path, with_audio)
    log("%sffmpeg: %s" % (tag, " ".join(cmd)))
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    t0 = time.time()
    done = 0
    try:
        for f in frames:
            img = comp.render(f)
            proc.stdin.write(img.tobytes())
            done += 1
            if done % 100 == 0 or done == len(frames):
                el = time.time() - t0
                rate = el / done
                log("%s  %5d/%5d frame %5d  %.3fs/frame  eta %5.1fs" % (
                    tag, done, len(frames), f, rate, rate * (len(frames) - done)))
    except BrokenPipeError:
        log("%sERROR: ffmpeg closed the pipe" % tag)
        proc.kill()
        return False, done
    except Exception:
        log("%sERROR while compositing frame %d\n%s" % (tag, f, traceback.format_exc()))
        proc.kill()
        return False, done
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
    proc.wait()
    if proc.returncode != 0:
        err = proc.stderr.read().decode("utf-8", "replace")[-3000:]
        log("%sffmpeg failed (%d):\n%s" % (tag, proc.returncode, err))
        return False, done
    return True, done


def _worker_main(idx, frames, args, W, H, out_path, log_path):
    """Process entry point for --workers mode."""
    logf = open(log_path, "w", encoding="utf-8")

    def log(msg):
        logf.write(msg + "\n")
        logf.flush()

    tag = "[w%d] " % idx
    try:
        comp = Compositor(W, H, allow_dummy=args.allow_dummy, draft=args.draft)
        ok, done = _render_frames(comp, frames, args, W, H, out_path, False, log, tag)
        log("%sDONE %d frames" % (tag, done))
        return 0 if ok else 1
    except Exception:
        log("%sFATAL\n%s" % (tag, traceback.format_exc()))
        return 1
    finally:
        logf.close()


# ------------------------------------------------------------------- concat/mux
def _concat_and_mux(args, seg_paths, out_path, with_audio, log):
    tmpdir = os.path.dirname(seg_paths[0])
    listfile = os.path.join(tmpdir, "segments.txt")
    with open(listfile, "w", encoding="utf-8") as f:
        for p in seg_paths:
            f.write("file '%s'\n" % p.replace("\\", "/"))
    silent = os.path.join(tmpdir, "video_silent.mp4")
    cmd = [args.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
           "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", silent]
    log("concat: " + " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        log("concat failed: " + r.stderr.decode("utf-8", "replace")[-2000:])
        return False
    if with_audio:
        cmd = [args.ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
               "-i", silent, "-i", args.audio,
               "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
               "-c:a", "aac", "-b:a", args.abitrate, "-ar", "44100", "-ac", "2",
               "-shortest", "-movflags", "+faststart", out_path]
        log("mux: " + " ".join(cmd))
        r = subprocess.run(cmd, capture_output=True)
        if r.returncode != 0:
            log("mux failed: " + r.stderr.decode("utf-8", "replace")[-2000:])
            return False
    else:
        shutil.copyfile(silent, out_path)
    return True


# ------------------------------------------------------------------------ main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(FINAL_DIR, "purple_sunflower_MV_v1.mp4"))
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--start", type=int, default=1)
    ap.add_argument("--end", type=int, default=0)
    ap.add_argument("--fps-div", type=int, default=1)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--preset", default="slow")
    ap.add_argument("--vcodec", default="libx264")
    ap.add_argument("--abitrate", default="320k")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--allow-dummy", dest="allow_dummy", action="store_true", default=True)
    ap.add_argument("--require-real", dest="allow_dummy", action="store_false")
    ap.add_argument("--ffmpeg", default=os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "tools", "ffmpeg.exe"))
    ap.add_argument("--audio", default=SONG_WAV)
    ap.add_argument("--log", default="")
    args = ap.parse_args(argv)

    ensure_dirs()
    W = int(round(FULL_W * args.scale)) // 2 * 2
    H = int(round(FULL_H * args.scale)) // 2 * 2
    end = args.end or TOTAL_FRAMES
    step = max(1, args.fps_div)
    frames = list(range(max(1, args.start), min(end, TOTAL_FRAMES) + 1, step))
    if not frames:
        print("nothing to render")
        return 1
    covers_all = args.start <= 1 and end >= TOTAL_FRAMES
    with_audio = (not args.no_audio) and covers_all

    log_path = args.log or os.path.join(OUT_DIR, "logs",
                                        "render_%s.log" % time.strftime("%H%M%S"))
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    logf = open(log_path, "w", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    t_start = time.time()
    log("=" * 78)
    log("render: %d frames  %dx%d  fps=%d  step=%d  workers=%d  audio=%s  draft=%s" % (
        len(frames), W, H, FPS // step, step, args.workers, with_audio, args.draft))
    log("output: %s" % args.out)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    if args.workers <= 1:
        comp = Compositor(W, H, allow_dummy=args.allow_dummy, draft=args.draft)
        log("plates: %s" % comp.plates.coverage())
        ok, done = _render_frames(comp, frames, args, W, H, args.out, with_audio, log)
        if not ok:
            log("render failed")
            return 1
        wall = time.time() - t_start
        log("DONE  %s" % args.out)
        log("  frames: %d  wall %.1fs (%.2f min)  avg %.3fs/frame" % (
            done, wall, wall / 60.0, wall / max(1, done)))
        log("  plates: %s  stats: %s" % (comp.plates.coverage(), comp.plates.stats))
        logf.close()
        return 0

    # ---------------- parallel workers ----------------
    n = max(1, min(args.workers, len(frames)))
    chunks = []
    base = len(frames) // n
    rem = len(frames) % n
    pos = 0
    for i in range(n):
        cnt = base + (1 if i < rem else 0)
        chunks.append(frames[pos:pos + cnt])
        pos += cnt
    tmpdir = os.path.join(OUT_DIR, "tmp", time.strftime("render_%H%M%S"))
    os.makedirs(tmpdir, exist_ok=True)
    seg_paths = [os.path.join(tmpdir, "seg_%02d.mp4" % i) for i in range(n)]
    shard_logs = [os.path.join(tmpdir, "seg_%02d.log" % i) for i in range(n)]
    log("parallel: %d workers, segments in %s" % (n, tmpdir))
    for i in range(n):
        log("  w%d: frames %d..%d (%d)" % (i, chunks[i][0], chunks[i][-1], len(chunks[i])))

    procs = []
    for i in range(n):
        import multiprocessing as mp
        p = mp.get_context("spawn").Process(
            target=_worker_main,
            args=(i, chunks[i], args, W, H, seg_paths[i], shard_logs[i]))
        p.start()
        procs.append(p)
    last_report = 0.0
    while any(p.is_alive() for p in procs):
        time.sleep(20)
        if time.time() - last_report > 20:
            last_report = time.time()
            for i, p in enumerate(procs):
                try:
                    with open(shard_logs[i], "r", encoding="utf-8") as f:
                        lines = [ln.strip() for ln in f.readlines() if ln.strip()]
                    if lines:
                        log("  " + lines[-1])
                except OSError:
                    pass
    codes = [p.exitcode for p in procs]
    for i, p in enumerate(procs):
        p.join()
    if any(c != 0 for c in codes):
        log("worker failures: %s" % codes)
        return 1
    ok = _concat_and_mux(args, seg_paths, args.out, with_audio, log)
    if not ok:
        return 1
    wall = time.time() - t_start
    log("DONE  %s" % args.out)
    log("  frames: %d  wall %.1fs (%.2f min)  avg %.3fs/frame" % (
        len(frames), wall, wall / 60.0, wall / max(1, len(frames))))
    logf.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
