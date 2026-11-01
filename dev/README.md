# dev/ — 辅助脚本

| 脚本 | 用途 |
|---|---|
| `qc_frames.py` | 检查 `plates/<shot>/` 每个镜头的帧号是否连续、缺多少帧 |
| `sheet.py` | 从某个镜头的 plate 序列抽 5 帧拼成 contact sheet（快速质检） |
| `analyze_audio.py` | 分析音频的 RMS / 起音点，辅助剪辑节奏（需要 `assets/audio/song.wav`） |

用法：

```bash
python dev/qc_frames.py                 # 全部镜头覆盖情况
python dev/qc_frames.py --missing-only  # 只看缺帧镜头
python dev/sheet.py S12 S22 S43         # → out/preview_sheets/sheet_S12.png …
```

这些脚本只依赖 numpy / Pillow，不需要 Blender。
