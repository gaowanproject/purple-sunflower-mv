import re, subprocess, os, urllib.request
UA = "Mozilla/5.0 (Windows NT 6.1; WOW64)"
fams = {
 "NotoSerifJP": "Noto+Serif+JP:wght@200;300;400;600",
 "ShipporiMincho": "Shippori+Mincho:wght@400;500;600;700",
 "ZenOldMincho": "Zen+Old+Mincho:wght@400;500;600;700",
 "KaiseiDecol": "Kaisei+Decol:wght@400;700",
 "ZenKakuGothicNew": "Zen+Kaku+Gothic+New:wght@300;400;500;700",
}
os.makedirs(".", exist_ok=True)
for name, q in fams.items():
    url = f"https://fonts.googleapis.com/css2?family={q}&display=swap"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    css = urllib.request.urlopen(req, timeout=30).read().decode()
    blocks = css.split("@font-face")
    n = 0
    for b in blocks:
        w = re.search(r"font-weight:\s*(\d+)", b)
        u = re.search(r"url\((https://[^)]+\.ttf)\)", b)
        if w and u:
            wght = w.group(1)
            out = f"{name}-{wght}.ttf"
            if os.path.exists(out): continue
            urllib.request.urlretrieve(u.group(1), out)
            n += 1
    print(name, "downloaded", n)
