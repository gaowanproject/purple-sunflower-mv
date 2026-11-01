# STATUS_A — Team A (scenery-nature) / set = road + void

**状态：12 镜全部渲完，1358 帧，帧号连续性校验通过（无缺帧、无多余帧）。**
产出：`plates/<shot>/<shot>_<绝对帧4位>.png`，1920x1080 PNG RGB，共 7.1 GB。
脚本：`blender/sets_road.py`（road 四世界）、`blender/sets_void.py`（void 两镜）
校验：`test/check_plates_A.py`
共享库：`lib.py`（22:22 版）+ `character.py`（21:59 版，含 reach_out）

## 渲染参数
单进程串行 / `samples=12–14` / `use_raytracing=False` → 实测 **0.51–0.83 s/帧** @1080p。

## 关键工程发现（**建议全组参考**）
1. **不要用 `lib.fog(density>0)` 的 world volume**。EEVEE 下 world volume 会把物体直接
   光照几乎吃光：实测同场景仅开/关 world volume，路面亮度 **178 → 19**（9 倍），且与
   density 大小、`use_volumetric_shadows`、采样数、光追开关全无关。这就是"地面死黑/
   整体发灰/以为 ambient 没给"的真正原因。
   → 改为 **mesh volume 盒子 + 高度衰减**（`haze_box`）：地面浓、高空淡、无硬边；
     `volumetric_end` 提到 3000–4200，长焦也看不到雾边界。
2. Lead 的亮度数值（sun 12 / ambient 3.0）是在"world volume 压暗"前提下调的，换成正确
   雾层会过曝。road 世界重新平衡为 **sun 9 / ambient 1.45 / exposure −0.45**（金色），
   天空仍沿用 Lead 的 sky 渐变参数。
3. `lib.sky_dome` 渐变方向正确，但天空主体必须**压低亮度（strength≈0.9）**，否则 AgX 会
   把蓝天/橙地平线去饱和成灰白。
4. `lib.sky_dome` 的 `Generated` 坐标在 bmesh sphere 上不是完整 0..1；自定义渐变请用
   `Geometry.Position / radius`（`VectorMath.SCALE`，**不要用 NORMALIZE**，会失效）。

## 镜头清单（最终）
| shot | set/variant | 帧范围 | 帧数 | 自评 |
|---|---|---|---|---|
| S03 | void/petals_dark | 279-433 | 155 | ✅ 干花瓣→白金光溢出（Lead 已确认可用） |
| S04 | road/noon_hot | 434-535 | 102 | ✅ 太阳过曝+花头剪影→摇到路面 |
| S05 | road/noon_hot | 536-636 | 101 | ✅ 已返工 v2：暗底高光水花 |
| S06 | road/noon_hot | 637-740 | 104 | ✅ 公路+电线杆列+远处剪影+地平线融霾 |
| S07 | road/noon_side | 741-846 | 106 | ○ 两人剪影在路上，长影朝镜头（透视压缩） |
| S08 | road/noon_hot | 847-984 | 138 | ✅ 已返工 v2：暗底高光高速水滴 |
| S09 | road/noon_side | 985-1051 | 67 | ○ 逆光侧脸特写（手抬到脸用 hold pose 近似） |
| S10 | road/noon_side | 1052-1152 | 101 | ✅ 两人坐路缘+尘埃+热霾 |
| S22 | road/dusk_afterglow | 2308-2502 | 195 | ✅ 200mm 黄昏，电线杆剪影列+小剪影 |
| S32 | road/violet_dusk | 3450-3542 | 93 | ✅ 紫风暴公路+剪影+风 |
| S42 | void/petals_dark | 4501-4579 | 79 | ✅ 黑水+紫光渐暗+浮花瓣 |
| S50 | road/dusk_afterglow | 5188-5304 | 117 | ✅ 低角夕阳+逆光剪影+光晕 |

## S05/S08 返工方案（v2，已应用）
按 Lead 要求做成"暗底高光"微距：
- **暗沥青**：两镜单独把路面材质换成 near-black（albedo 0.01–0.03），并用
  `dim_ambient(0.22)` 把 world 环境光压到 22%，背景亮度落 ~30–45（画面约 80% 暗）。
- **水**：`splash_spray()` = 20–26 个主水滴(0.5–1.4cm) + 90–150 个细雾滴(0.15–0.45cm)
  + 12–20 个**拉长水柱**（椭球 z 轴 ×3.2–6.5，模拟高速快门凝固）。
- **材质**：alpha 0.30 半透 + roughness 0.045 + IOR 1.333（逆光下暗背景透出才有水感）。
- **水膜**：48 边圆滑薄片，深蓝灰 (0.035,0.048,0.085)、roughness 0.035，只留镜面反射。
- **相机**：85mm/f5.6（S05, focus 1.25m）、100mm/f5.6（S08, focus 0.90m）——不用浅景深。
- **光**：太阳逆光 + 两盏小 area 正面补光（ShotFill 2.4 / Kick 1.4）让高光成型；
  exposure −0.75。

## 剩余小问题（后期可救）
1. 向日葵花瓣在强光下偏白（AgX 高光去饱和）→ 后期加饱和。
2. 金色世界整体偏清淡（不够"过曝暖金"）→ 后期调色加暖。
3. S22/S50 地平线附近仍有一条极淡的雾层边界线 → 后期加渐变遮罩。
4. S07 长影朝镜头方向被透视压缩（太阳方位与全景统一导致的），视觉上不算"长影"。
5. 人物为 character.py 剪影，S06 30m 远景看起来偏细（造型问题）。

## 复用入口
```python
import sets_road
W = sets_road.build_road("noon_hot")   # 或 noon_side / dusk_afterglow / violet_dusk
# 返回 dict: preset, sun, fill, road, curb, poles, wires, flowers, grass, ...
# 相机请用 sets_road.cam_() 包装（clip_end 需够到 2800m 天空球）
```
