# tools/

`comp/` 与 `assemble.py` 默认调用 `tools/ffmpeg.exe`（Windows 静态构建）。

## 安装

1. 下载任意带 libx264 + AAC 的 FFmpeg 静态构建（推荐 https://www.gyan.dev/ffmpeg/builds/ 的 essentials 版）；
2. 解压后把 `ffmpeg.exe` 放到本目录：

```
tools/ffmpeg.exe
```

Linux/macOS 上直接 `apt install ffmpeg` / `brew install ffmpeg`，然后把
`comp/common.py` 里的 `FFMPEG` 改成 `"ffmpeg"` 即可。

## 校验

```bash
./tools/ffmpeg.exe -hide_banner -encoders | grep -E "libx264|aac"
```

应能看到 `libx264`（视频）与 `aac`（音频）。成片参数：
`libx264 -crf 18 -preset slow -pix_fmt yuv420p -movflags +faststart` + `aac 320k`。
