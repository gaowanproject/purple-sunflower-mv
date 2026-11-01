# story/ — 时间轴与歌词数据

| 文件 | 说明 | 是否入库 |
|---|---|---|
| `shots.json` | **唯一真源**：57 个镜头的帧范围、场景、相机说明 | ✅ |
| `lyrics.example.json` | 歌词时间轴结构示例（文本留空） | ✅ |
| `build_lyrics.py` | 由你自己的 LRC + 中文翻译生成 `lyrics.json` | ✅ |
| `lyrics.lrc` | 歌词 LRC 时间轴（自备） | ❌ git-ignored |
| `translation.txt` | 逐行中文翻译（自备） | ❌ git-ignored |
| `lyrics.json` | 合成/排版管线真正读取的文件 | ❌ git-ignored |

## 为什么歌词不进仓库

歌曲与歌词版权归 香椎モイミ / 羽累 所有。本仓库是非商业同人二创，**不分发歌词文本与音频**。
想复现 MV 的歌词排版，请自备合法取得的 LRC 与翻译，运行：

```bash
python story/build_lyrics.py
```

`lyrics.json` 的格式：

```json
[
 {"i": 0, "t": 18.029, "t_end": 22.307, "jp": "（第 1 行歌词）", "cn": "（第 1 行翻译）"},
 ...
]
```

`t` / `t_end` 单位为秒，`t` 是行开始时间。`comp/typography.py` 会按 `t` 逐行淡入，
按 `t_end` 之前 300–400ms 淡出；`comp/lyrics_layout.json` 里记录了每一行的版式
（左下横排 `bl` / 左侧竖排 `vl` / 右侧竖排 `vr` / 居中大字 `center_big` 等）。

## shots.json 字段

```json
{"id":"S12","t0":52.388,"t1":57.292,"f0":1258,"f1":1375,"nframes":118,
 "set":"field","variant":"gold_noon","team":"L",
 "camera":"low dolly through golden sunflowers toward the sun, petals fly, girl ahead",
 "section":"chorus1"}
```

- `f0`/`f1`：绝对帧号（24fps），plate 文件名为 `<id>_<4 位帧号>.png`；
- `set`：对应 `blender/sets_<set>.py` 里的场景组；
- `variant`：色彩世界（`gold_noon` / `gold_dusk` / `violet_dusk` / `violet_night` / `noon_hot` / …）；
- `team`：制作分工标记（L = field，A = road/void，B = room/street），仅作历史记录。
