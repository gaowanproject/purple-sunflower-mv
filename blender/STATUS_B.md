# STATUS_B — Team B（室内 / 街道）镜头交付状态

> 负责：`blender/sets_room.py`、`blender/sets_street.py`（我拥有）
> 依赖：`blender/lib.py`（只读）、`blender/character.py`（只读）
> 输出：`plates/<shot_id>/<shot_id>_<绝对帧:04d>.png` — 1920x1080 / PNG RGB / EEVEE
> **交付状态：19/19 镜头、2343/2343 帧完整、帧号连续、无缺帧**（校验脚本 `test/verify_B.py`）

## 镜头清单

| 镜头 | 帧范围 | 帧数 | set | 内容 | 状态 |
|---|---|---|---|---|---|
| S01 | 1–149 | 149 | room/night_rain | 85mm 窗玻璃雨滴，焦点从水滴拉到城市散景 | ✅ |
| S02 | 150–278 | 129 | room/night_rain | 书桌 + A4 纸 + 干枯紫向日葵逆光剪影 + 城市 bokeh + 尘埃 | ✅ |
| S20 | 2101–2203 | 103 | street/rain_night | 雨夜街道 + 地上碗状红伞 + 霓虹倒影条 + 三层雨丝 | ✅ |
| S21 | 2204–2307 | 104 | street/rain_night | 低机位红伞伞骨 + 霓虹 bokeh + 湿地光斑 | ✅ |
| S23 | 2503–2605 | 103 | room/macro_cold | 玻璃杯融冰微距 + 杯壁冷凝水珠 + 冷蓝背光 | ✅ |
| S24 | 2606–2710 | 105 | room/macro_cold | 杯壁水珠特写（浅景深，慢移） | ✅ |
| S25 | 2711–2811 | 101 | room/night_rain | 窗玻璃雨滴 + 城市/路灯 bokeh + 心跳式慢推近 | ✅ |
| S26 | 2812–2919 | 108 | room/night_dark | 窗边女性剪影缓慢转身（月光轮廓） | ✅ |
| S28 | 3022–3123 | 102 | room/macro_warm | 同融冰杯，暖光版 + 落下的水滴 + 暖 bokeh | ✅ |
| S35 | 3761–3865 | 105 | room/night_lamp | 2AM：冰淇淋在杯中融化 + 暖台灯 + 时钟指针 2:00 | ✅ |
| S36 | 3866–3941 | 76 | room/night_lamp | 夜窗 + 城市 bokeh + 两侧窗帘（风动褶皱下摆）+ 窗台盆栽 + 左下书桌干花 | ✅ 返工完成 |
| S37 | 3942–4059 | 118 | room/night_lamp | 窗玻璃两人倒影（窗外镜像 ghost，alpha 0.30/0.20） | ✅ |
| S38 | 4060–4182 | 123 | room/night_lamp | 窗台紫向日葵摇动（前景虚化）+ 背景两人 ghost 倒影 | ✅ |
| S39 | 4183–4291 | 109 | street/city_bridge | 天桥栏杆前景俯拍湿街 + 车流倒影光轨 + 右侧孤独剪影 | ✅ |
| S40 | 4292–4407 | 116 | 3 拍 | 空床(4292–4329) / 空街(4330–4368) / 空场枯向日葵田(4369–4407) | ✅ |
| S41 | 4408–4500 | 93 | room/night_dark | 暗床蜷缩剪影 + 窗侧冷色轮廓光（暗部见形，背景近黑） | ✅ 返工完成 |
| S55 | 5953–6156 | 204 | room/night_rain | 回到当下：干花 + 纸 + 窗，一片花瓣飘起 | ✅ |
| S56 | 6157–6324 | 168 | room/night_rain | 雨窗底（左上/右下暗部留负空间给标题） | ✅ |
| S57 | 6325–6551 | 227 | room/night_rain | 灯光/城市自发光自然衰减至几乎全暗（最终 fade 后期加） | ✅ |

## 关键技术决定（对后期 / 其他组有用）

1. **EEVEE 采样噪点**：raytracing + 体积雾在低 samples 下会在暗部产生斜向"编织纹"。室内与街道场景全部 `scene.eevee.use_raytracing=False`，`fog(density=0)` 只用 world `ambient` 提供冷色环境光（这是唯一能照亮暗部的方式；自发光天空球不照亮场景）。
2. **台灯罩** `visible_shadow=False` 模拟布艺透光；点光在罩内 + 上方补光，暖光才能爬到墙面形成"孤岛"。
3. **窗外城市** = 远景楼体剪影 + 大量小自发光窗灯/霓虹条 + 近处 (5–16m) bokeh 光点。85mm 大光圈下自动成为大散景。
4. **湿地面反射**：street 场景用「贴地彩色光条 + 镜像发光体复制」近似霓虹倒影（EEVEE 无 SSR 时的稳妥做法）。
5. **雨**：street 是 7 层 × 42 条长条 mesh 循环下移；窗玻璃雨滴是 430 个压扁球合并 mesh。
6. **人物**：`character.py` 的 `figure()` / `two_people()`。S37/S38 倒影 = 窗外镜像位置 ghost 剪影（`hide_render` 关键帧只在 S37 起始帧显示，避免穿帮进 S36）。
7. **S40 三拍**由 3 个不同场景分别渲染后写入同一目录同一连续帧段。

## ⚠️ 已知短板（Lead 决定用调色解决，本轮不返工）

1. **S21 水洼倒影弱**：低机位红伞成立，但"水洼镜面倒影"未体现，目前靠贴地光条。
2. **S37/S38 倒影**：窗外镜像 ghost 方案；后期会在 plate 上叠 15–25% 垂直翻转镜像 + 轻微模糊强化反射感。
3. **S02/S55 右侧桌面留白偏多**、**S20/S40b 红伞偏暗红**：调色解决。

## ✅ 已完成的返工

- **S41**：加窗侧 cold rim（area 34W + 12W 斜向），勾出肩/背/头发轮廓，背景保持近黑。重渲 93 帧。
- **S36**：相机左移 + 加宽（lens 22，x −1.78），两侧窗帘入画；窗帘褶皱幅度 ×1.6、Blow shape-key 幅度 0.24、emission 0.10（半透薄纱透冷光），下摆随帧起伏。重渲 76 帧。

## 复现 / 重渲命令

```bash
BL="blender.exe"
# 全部剩余（串行，samples 12）
bash test/render_final.sh
# 单组
"$BL" -b -P blender/sets_room.py -- render_lamp_rest 12     # S37/S38
"$BL" -b -P blender/sets_room.py -- render_dark 12          # S26/S40a/S41
"$BL" -b -P blender/sets_room.py -- render_macro_cold 12    # S23/S24
"$BL" -b -P blender/sets_room.py -- render_macro_warm 12    # S28
"$BL" -b -P blender/sets_street.py -- render_street 12      # S20/S21/S40b
"$BL" -b -P blender/sets_street.py -- render_bridge 12      # S39
# 缺帧检测 + 自动补渲
"$BL" -b -P blender/sets_room.py -- render_missing
```

## 渲染参数

- EEVEE，1920×1080，samples 12（S01/S02/S25/S55/S56/S57 首轮为 20/16，后统一 12），AgX view transform，无 bloom/颗粒/暗角（后期负责）。
- 单帧 0.9 s（独占 GPU）～ 2 s（多 teammate 并行时，GPU 争用）。
