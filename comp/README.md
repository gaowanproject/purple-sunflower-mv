# comp/ — Python 合成管线

本目录把 `plates/`（Blender 渲出的 PNG 序列）变成最终成片。全部纯 Python（numpy + Pillow），
最后一步交给 FFmpeg 编码。**不依赖 Blender。**

## 流程

```
plates/<shot>/<shot>_<frame>.png
        │
        ├─ timeline.py      读 story/shots.json，给出 frame → shot 映射、转场窗口
        ├─ plates.py        读 plate，缺帧时回退到最近可用帧
        ├─ grade.py         每个 variant 的调色 + 逐镜自动曝光匹配
        ├─ fx.py            bloom / halation / 色散 / 暗角 / 颗粒 / 雨 / 花瓣 / 尘埃 / 热浪
        ├─ typography.py    歌词排版与逐字动画、标题卡、片尾字卡（输出 comp/lyrics_layout.json）
        └─ composite.py     逐帧合成
                 │
        render_segments.py  按镜头渲染 segment（可多 worker）→ out/segments/<shot>.mp4
                 │
        assemble.py         无损 concat + 音频（AAC 320k）→ out/final/*.mp4
                 │
        finalize.py         全片 QC、海报、低码预览
```

## 常用命令

```bash
# 全片逐镜头合成（4 个 worker，CRF18）
python comp/render_segments.py --workers 4 --crf 18

# 只重做某几个镜头（比如改了某个 plate）
python comp/render_segments.py --shots S12 S19 --workers 2

# 拼接成片（音频来自 assets/audio/song_ff.wav）
python comp/assemble.py

# 质检 + 生成 poster.png / preview.mp4
python comp/finalize.py
```

## 直接跑单帧（不编码，调试布局/调色最快）

```bash
python comp/still.py --frame 1260        # → out/review/…
python comp/preview.py --scale 0.5       # 低分辨率全片预览
```

## 设计要点

- **调色**：`grade.py` 为 15 个 variant 定义色彩世界（`gold_noon` / `gold_dusk` /
  `violet_dusk` / `violet_night` / `noon_hot` / `rain_night` / `night_lamp` …），
  并对每个镜头做自动曝光匹配（基于平均亮度，带高光保护）。
- **光学**：3 级 bloom + 暖色 halation + anamorphic streak、半分辨率径向色散、
  暗角、gate weave、4 组 bank 的时域连续胶片颗粒——文字层不参与色散/抖动。
- **2.5D 氛围**：雨丝、镜头水珠、涟漪、细长花瓣（旋转+运动模糊、只在中后景）、
  尘埃、bokeh、星星、热浪；室外镜头底部 ~48% 屏高的暖雾 + 渐进虚化用来盖住 3D 的
  "黑色花茎"。
- **排版**：每行歌词有三种版式（左下横排 / 竖排 / 居中大字），逐字错峰淡入；
  标题卡有字距"呼吸"动画；中文字幕与日文主行保持固定主次关系。
- **转场**：`edit.json` 定义 7 处特殊转场（光溢出溶解、雨滴涟漪、白闪、从黑浮现、
  长叠化、fade in/out），其余为硬切；逐帧渲染前会校验转场窗口不超界。
- **缺 plate**：`plates.py` 会回退最近帧，`placeholder.py` 用于 720p 预览阶段的占位；
  `assemble.py` 默认拒绝缺 segment 的拼装（`--allow-missing` 可放宽），保证成片零占位。
