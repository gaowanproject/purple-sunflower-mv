# -*- coding: utf-8 -*-
"""
build_lyrics.py — build story/lyrics.json from YOUR OWN lyric files.

The song's lyrics are copyright their authors; they are NOT shipped in this
repository.  To reproduce the MV you need to supply your own (legally obtained)
LRC timing file and a line-by-line translation:

    story/lyrics.lrc          standard LRC: [mm:ss.xxx]lyric line
    story/translation.txt     one translation line per LRC lyric line (optional)

Then run:

    python story/build_lyrics.py

Output (git-ignored):

    story/lyrics.json         [{"i":0,"t":18.029,"t_end":22.307,"jp":"...","cn":"..."}]

The shot table (story/shots.json) is independent of this file and is shipped.
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LRC = os.path.join(HERE, "lyrics.lrc")
TRANS = os.path.join(HERE, "translation.txt")
OUT = os.path.join(HERE, "lyrics.json")


def parse_lrc(path):
    lines = []
    for raw in open(path, encoding="utf-8-sig"):
        m = re.match(r"\[(\d+):(\d+(?:\.\d+)?)\]\s*(.*)", raw.strip())
        if not m:
            continue
        t = int(m.group(1)) * 60 + float(m.group(2))
        txt = m.group(3).strip()
        if txt:
            lines.append((t, txt))
    return lines


def parse_translation(path):
    out = []
    if not os.path.exists(path):
        return out
    for raw in open(path, encoding="utf-8-sig"):
        s = raw.strip()
        if s:
            out.append(s)
    return out


def main():
    if not os.path.exists(LRC):
        sys.exit("missing %s — supply your own LRC file (see module docstring)" % LRC)
    jp = parse_lrc(LRC)
    cn = parse_translation(TRANS)
    if cn and len(cn) != len(jp):
        print("[warn] %d JP lines vs %d translation lines; extra translation lines are ignored, "
              "missing ones are left empty" % (len(jp), len(cn)))
    rows = []
    for i, (t, txt) in enumerate(jp):
        rows.append({"i": i, "t": round(t, 3), "jp": txt,
                     "cn": cn[i] if i < len(cn) else "",
                     "t_end": round(jp[i + 1][0], 3) if i + 1 < len(jp) else round(t + 5.0, 3)})
    json.dump(rows, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("wrote %s (%d lines)" % (OUT, len(rows)))


if __name__ == "__main__":
    main()
