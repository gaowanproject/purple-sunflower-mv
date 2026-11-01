# assets/

## audio/ — 音频（不入库）

本仓库**不包含**歌曲音频（版权归 香椎モイミ / 羽累）。

复现时请自备正版音源，放到：

```
assets/audio/song.mp3
```

并转换成管线使用的 wav（44.1kHz / 立体声 / 16bit）：

```bash
ffmpeg -i assets/audio/song.mp3 -ac 2 -ar 44100 -c:a pcm_s16le assets/audio/song_ff.wav
```

管线里 `comp/common.py` 的 `SONG_WAV = assets/audio/song_ff.wav`，最终成片的音频来自它。

## fonts/ — 字体（用脚本下载）

字体文件较大（约 20MB）且各有自己的开源许可，不入库。运行：

```bash
python assets/fonts/dl_fonts.py
```

会从 Google Fonts 下载（均为 OFL 许可）：

| 文件 | 用途 |
|---|---|
| `ShipporiMincho-400/500/600/700.ttf` | 日文歌词主体 |
| `NotoSerifJP-200/300/400/600.ttf` | 日文辅助（细体） |
| `ZenOldMincho-400/500/600/700.ttf` | 标题卡 |
| `KaiseiDecol-400/700.ttf` | 装饰字 |
| `ZenKakuGothicNew-300/400/500/700.ttf` | 小字/字幕 |

中文翻译字幕使用系统中文字体（脚本里回退到 Windows 的 Noto Serif SC / Source Han Serif；
Linux/macOS 可自行改 `comp/common.py` 的 `FONT_FILES` 指向本机字体）。
