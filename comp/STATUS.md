# STATUS — Compositor (MV《紫色の向日葵》)

**最后更新：2026-11-01 23:25（第 1 天）· 最终成片已交付**
负责人：compositor（后期合成师）
目录约定：只能写 `comp/` 与 `out/`；`story/`、`plates/`、`tools/`、`blender/` 只读。

---

## 0. TL;DR

- 整套管线 **已跑通**：plates → 调色 → 光学 → 2.5D 氛围 → 底部雾/虚化 → 暗角/色散/颗粒 → 歌词排版 → 转场 → ffmpeg 编码。
- 真实 plates **已自动接入**（按 `plates/<shot_id>/<shot_id>_<globalframe>.png` 或 `0001.png` 两种命名都支持，缺帧回退最近帧，无 plate 用程序化占位板）。
- **调色方向已通过 Lead 审核**（S12 静帧 `out/review/review2_01270.png`；新 S12 plate 版 `out/review/newS12_01260.png`）。
- **720p 全片预览已出并获 Lead 通过**：`out/final/preview_720p_dummy.mp4`（1280x720/24fps/4:32.96，含音频；缺 plate 镜头为占位）。
- **Lead 第二轮修改已完成**：标题卡提亮（暖金径向 halo + 大半径暖外发光 + 前 20 帧 0→1 淡入 + 字距 0.16em→0.10em 呼吸动画）；field 底部暖雾提到 0.48 屏高/alpha 0.35 + 底部柔化；竖排中文字幕列垂直居中。
- **1080p 最终渲染方案已切换为"逐镜头 segment"**：`render_segments.py`（每镜独立 mp4 + plate 签名）+ `assemble.py`（无损 concat + AAC 320k）。正在渲染已完成的 25 个镜头（3025 帧）；剩余镜头 plate 到齐后增量补渲，保证成片无占位画面。
- 转场/黑帧 QA：用 ffmpeg 解码 720p 预览逐帧 luma 分析，**除设计内的 4 段黑（片头淡入 / S42→S43 from_black / S56→S57 to_black / 片尾 fade）外无黑帧**。

---

## 1. 代码结构（全部在 comp/）

| 文件 | 作用 |
|---|---|
| `common.py` | 路径/常量/缓动/噪声/字体/图像工具（PIL 加速优先） |
| `timeline.py` | 时间轴：帧→镜头映射、转场窗口、全局淡入淡出、每镜头特效曲线、weave、音乐脉冲 |
| `edit.json` | **剪辑决策表**：7 个特殊转场 + 片头/片尾淡入淡出（Lead 已确认） |
| `grade.py` | 15 个 variant 的电影调色（LUT：曝光/白平衡/gain-offset/gamma/S 曲线/肩部/高光染色 + 饱和） |
| `placeholder.py` | 程序化占位板（按 set/variant 生成 2304x1296 画布：field/road/room/street/void） |
| `plates.py` | plate 解析（真实/占位）、镜头运动裁切、weave、**逐镜头自动曝光匹配 + 饱和度/clarity 自适应 + 光源位置估计** |
| `fx.py` | bloom/halation/anamorphic streak/light leak/sun glow/rain/droplet/ripple/petal/dust/bokeh/star/heat haze/vignette+sky tint/chromatic/grain/clarity/底部雾/渐变模糊/径向 warp/白闪 glow |
| `typography.py` | 歌词排版 + 逐字动画 + 幽灵歌词 + 标题卡 + 片尾字卡；`lyrics_layout.json` 自动生成 |
| `composite.py` | 逐帧合成器（含全部转场实现） |
| `render_final.py` | 批量合成 → ffmpeg 管道 / 多进程分段渲染 + concat + 音频 |
| `preview.py` | 640x360 / 每 2 帧 / 带音频的快速预览 |
| `still.py` | 指定帧出 1080p 静帧（审片用） |
| `looktest.py` | 单张 plate 的快速调色 look-dev 工具 |

运行方式（工作目录 `E:\大肥鱼代工区\work\MV\comp`）：
```
python still.py --frames 1270 --scale 1.0
python render_final.py --workers 4 --out ../out/final/purple_sunflower_MV_v1.mp4
python preview.py                       # 640x360, 每2帧, 自动命名 preview(_dummy).mp4
python render_final.py --start 1258 --end 1310 --out ../out/review/seg.mp4 --no-audio
```

---

## 2. 已实现的设计/技术点

### 调色（按 Lead 最新指示）
- 15 个 variant 分 4 个色彩世界：gold（noon_hot / noon_side / gold_noon / gold_dusk / dusk_afterglow / macro_warm）、violet（violet_dusk / violet_night / petals_dark）、cold/night（night_rain / rain_night / night_dark / night_lamp / macro_cold / city_bridge）。
- gold 世界：高光琥珀金、中间调蜜黄、暗部青绿/橄榄；对比 0.24-0.28、饱和 1.10-1.18；天空用 multiply 遮罩做"top 青蓝 → 地平线 琥珀"竖向渐变；整体按"逐镜头自动曝光匹配"压到目标平均亮度（每镜恒定，不闪烁），并做高光保护（p99.5 上限）。
- violet / night：暗部蓝紫、高光粉紫，对比更高、暗部更沉、颗粒更明显。
- 每个镜头先做 **shot matching**：mean luma 目标 + 饱和度补偿（低饱和 plate 自动 +sat）+ clarity 补偿（平坦/hazy plate 自动加局部对比）+ 从 plate 估计光源位置（用于 sun glow/flare/leak 定位）。

### 光学/镜头感
- 3 级 bloom（半径 2.6/10/24 @1/7 分辨率，大半径低强度）+ 暖色 halation + anamorphic 水平 streak + 逐镜头 sun glow。
- CA：半分辨率色度径向色散（边缘 0.5-1.5px，绿通道保持锐利）。
- 暗角 10-19%（按 variant），gate weave 0.3-0.6px（文字层不参与）。
- 胶片颗粒：4 组 noise bank 交叉淡化，时域连续；暗部/夜景更明显。
- 镜头几何：占位板走程序化运镜（push-in/tilt/crane/orbit/drift/shake）；真实 plate 保留原运镜，只做 1% 裁切冗余 + weave。

### 2.5D 氛围（按 variant/set 配置）
- 雨丝（3 层速度/长度）、镜头水珠（亮边+暗体）、地面水波纹、花瓣（细长 3:1、旋转、沿速度 3-6px 运动模糊、中后景）、尘埃、bokeh、星星、热浪（1/4 分辨率位移）。
- 底部处理：field/road 全部加暖雾（自适应强度）+ 底部 28% 渐进虚化，专门盖住 3D plate 的黑茎/草点；若底边本来就是干净黑位则自动减雾。

### 排版（Lead 已确认过风格，并已按第二轮反馈修改）
- 日文主歌词：Shippori Mincho 500（强调 600），50-54px（center 58-82，key 96-112）；白色偏暖 + 深色投影 + 大半径暗晕 + 暖/紫辉光。
- 中文副标题：Noto Sans SC 400，32px，透明度 0.88，深色投影（4px/0.38），紧贴日文下方 11px。
- 版式：60 行 = 37 行左下 / 12 行竖排（右 6、左 6）/ 11 行居中大字；关键句「（歌词行略）」「（歌词行略）」「（歌词行略）」等用居中大字。
- 动画：逐字 20-35ms 错峰淡入（ease-out）、升起 9px、模糊消散；行尾前 0.24-0.40s 淡出。
- 幽灵歌词：同句 2.5-3.6 倍大、透明度 0.042-0.066、大范围模糊、缓慢漂移。
- 标题卡 S56：Zen Old Mincho 600 128px + 字距 0.17em + "Purple Sunflower" + "香椎モイミ feat. 羽累"（带柔光/暗底）。
- 片尾字卡 S57：按 Lead 给定文案（音乐/作曲・编曲/MV 制作/3D・合成/ご視聴ありがとうございました），22-25px、alpha 0.68-0.78、最后 ~2.5s 淡出到全黑。

### 转场（edit.json，Lead 已确认）
| 边界 | 类型 | 实现 |
|---|---|---|
| 片头 | fade in | 0-1.6s 全局曝光 |
| S03→S04 | light_bleed | 溶解 + 暖金光溢（峰值白闪） |
| S19→S20 | ripple | 溶解 + 径向雨滴涟漪 warp + 冷光 |
| S22→S23 | dissolve | 叠化 |
| S30→S31 | white_flash | 白闪 + 强 glow |
| S42→S43 | from_black | A 压黑→B 从黑浮现 + 紫光 |
| S54→S55 | dissolve | 长叠化（22+22 帧） |
| S56→S57 | to_black | A 压黑 → B 从黑缓慢浮现（30 帧） |
| 片尾 | fade out | 270.9-272.95s 全局 |

---

## 3. 进度 / plates

- 2026-11-01 22:2x：17/57 镜已有真实序列（约 1724 帧）。已接：S01 S02 S03 S04 S05 S06 S22 S25 S32 S50 S55 S56 S57（部分/完整）。
- S12 试拍：107/118 帧，已用于审片静帧/片段。
- S19：32 帧（旧版，可能待重渲）。
- 缺失镜头自动用占位板，**不阻塞**渲染；plate 到位后重跑对应帧段即可（`--start/--end`）。
- S19 32 帧可能是旧版（体积雾版本），若 3D 重渲会自动用新帧。

## 4. 已知问题 / 待办

- [x] 调色方向确认（Lead 通过，要求三点微调：绿茎→3D 已修；新 plate 更暗→自动曝光已 +0.19EV；花瓣更金）。
- [x] 720p 全片预览 `out/final/preview_720p_dummy.mp4`。
- [x] 逐镜头 segment：53/57 已完成（含 S36/S41 覆盖后的 stale 重渲、S05/S08 返工版、S37/S38 玻璃倒影版）。
- [ ] 等最后 4 镜（S48/S49/S51/S53）plate 到齐 → `render_segments.py --workers 4` 收尾 → `assemble.py` → `finalize.py`（QC/poster/preview）→ 报 Lead。
- [x] S37/S38 玻璃倒影：垂直镜像 17% + 3.4px 模糊 + 轻微冷色压暗（`fx.glass_reflection`）。
- [x] plate 鲁棒性：3D 写坏的截断 PNG（如 S57_6411）跳过并用最近可用帧，保证渲染不断。
- [ ] 真实 plates 到齐后重跑缺 plate 的镜头段；最终输出 `out/final/purple_sunflower_MV_v1.mp4`。
- [ ] 片尾 S57 目前 plates 只有 52/227 帧，其余先用占位（房间雨窗），到位后重渲。
- [ ] S19/S22 等旧版 plate（有体积雾）在重渲后需要重新确认调色。
- [ ] 花瓣/雨丝/水珠的密度与透明度可能还需按最终画面再微调。
- [ ] 若 Lead 需要中文竖排/英文副标题等其它版式，可调 `typography.py` 的 STYLES/STYLE_SPEC。

## 5. 性能

| 模式 | 分辨率 | 速度 |
|---|---|---|
| 单进程 1080p（真实 plate，重特效） | 1920x1080 | ~0.35-0.45 s/帧 |
| 单进程 1080p（占位 plate，重特效） | 1920x1080 | ~0.23-0.28 s/帧 |
| 4 进程 1080p | 1920x1080 | 预计 ~10-14 min 全片 |
| 640x360 / 2 帧取 1 | 640x360 | ~0.06-0.09 s/帧 → 全片约 4-5 min |

主要耗时：PNG 解码（真实 plate 65ms/帧，占大头）、atmosphere 绘制、bloom 上采样+screen、CA、clarity。


---

## 6. 最终交付记录（2026-11-01 23:25）

| 交付物 | 路径 | 规格 |
|---|---|---|
| 主成片 | `out/final/purple_sunflower_MV_v1.mp4` | 1920x1080 / 24fps / H.264 High CRF18 / AAC 320k 44.1k / 6551 帧 / 272.958s / 188.51 MB / 5525 kb/s / faststart |
| 海报帧 | `out/final/poster.png` | 1920x1080，S43 f4640 紫向日葵花田，无字幕 |
| 低码预览 | `out/final/preview.mp4` | 640x360 / 12fps / 272.97s / 13.56 MB（含音频） |
| 审片版 720p | `out/final/preview_720p_dummy.mp4` | 早前含占位镜头的节奏预览（历史版本，非最终） |

**最终 QC 结果**
- ffmpeg 全解码帧数 = **6551 / 6551** ✓
- 时长 = **272.96s**（音频 272.966s，`-shortest` 对齐）✓
- A/V 同步校验：与 song_ff.wav 做互相关，**lag = 0 样本，corr 0.9992** ✓
- 逐帧亮度扫描：黑场仅出现在 4 个设计位置（片头淡入 0–0.46s、S42→S43 from_black 190.4–191.1s、S56→S57 to_black 263.3–264.0s、片尾 fade 272.1–272.9s），无意外黑帧 ✓
- faststart：moov 位于文件头（偏移 36 bytes）✓
- 57/57 镜全部真实 plates，逐镜头 segment 渲染（allow_dummy=False），**成片无占位画面** ✓
- 已知瑕疵：`plates/S57/S57_6411.png` 为 3D 写坏的截断 PNG，合成时用最近可用帧替代（片尾暗部 1 帧，肉眼不可辨）；如需绝对干净，3D 补渲该帧后重渲 S57 segment（~2 min）即可。

**渲染性能**：1080p 单进程约 0.35-0.45s/帧；4 路并行 segment 渲染 + 无损 concat，全片约 12-15 分钟。
