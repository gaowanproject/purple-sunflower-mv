# -*- coding: utf-8 -*-
"""Build contact sheets from rendered plate folders for quick QC.
usage: python tools/sheet.py S12 S19 ...   (writes out/preview_sheets/sheet_<id>.png)
"""
import sys, os, glob
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out", "preview_sheets")
os.makedirs(OUT, exist_ok=True)


def sheet(sid, cols=4, thumb_w=480):
    files = sorted(glob.glob(os.path.join(ROOT, "plates", sid, "*.png")))
    if not files:
        print("no plates for", sid)
        return None
    picks = [files[int(round(i))] for i in
             [0, (len(files) - 1) * 0.25, (len(files) - 1) * 0.5,
              (len(files) - 1) * 0.75, len(files) - 1]]
    picks = [files[min(len(files) - 1, max(0, int(p)))] for p in
             [0, len(files) * 0.25, len(files) * 0.5, len(files) * 0.75, len(files) - 1]]
    ims = []
    for p in picks:
        im = Image.open(p).convert("RGB")
        w, h = im.size
        im = im.resize((thumb_w, int(h * thumb_w / w)))
        d = ImageDraw.Draw(im)
        d.text((8, 6), os.path.basename(p), fill=(255, 255, 0))
        ims.append(im)
    w, h = ims[0].size
    cols = min(cols, len(ims))
    rows = (len(ims) + cols - 1) // cols
    out = Image.new("RGB", (w * cols, h * rows), (0, 0, 0))
    for i, im in enumerate(ims):
        out.paste(im, ((i % cols) * w, (i // cols) * h))
    path = os.path.join(OUT, f"sheet_{sid}.png")
    out.save(path)
    print("wrote", path)
    return path


if __name__ == "__main__":
    for sid in sys.argv[1:]:
        sheet(sid)
