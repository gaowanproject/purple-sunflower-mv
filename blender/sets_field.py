# -*- coding: utf-8 -*-
"""
sets_field.py — the sunflower-field set (26 shots, team L).

Worlds
  gold_noon    : bleached summer noon, cyan sky, high sun, heat
  gold_dusk    : low golden sun, long shadows, backlight
  violet_dusk  : storm violet, low light, wind
  violet_night : indigo night, stars, faintly glowing violet flowers

Usage (absolute frames come from story/shots.json):
  blender -b --factory-startup -P blender/sets_field.py -- --shot S12
  blender -b --factory-startup -P blender/sets_field.py -- --shot S12 --test
"""
import bpy, sys, os, math, json, random, copy
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.append(HERE)
import lib, character

SHOTS = json.load(open(os.path.join(ROOT, "story", "shots.json"), encoding="utf-8"))["shots"]
SHOT = {s["id"]: s for s in SHOTS}

# --------------------------------------------------------------------------- worlds
VARIANTS = {
    "gold_noon": dict(
        sky=dict(c_horizon=(1.0, 0.52, 0.12), c_mid=(0.05, 0.34, 1.00),
                 c_zenith=(0.01, 0.055, 0.34), sun_dir=(0.06, 0.84, 0.40),
                 sun_color=(1.0, 0.95, 0.82), sun_power=70.0, glow=0.18, strength=0.82,
                 cloud=((1.0, 0.97, 0.93), 0.10, 1.20, 0.55), sun_exp=2600.0, glow_exp=16.0),
        bounce=dict(loc=(0.0, 5.0, 2.1), target=(0.0, 5.0, 0.0), energy=150.0,
                    size=26.0, color=(1.0, 0.80, 0.55)),
        mist=dict(height=1.15, density=0.075, color=(1.0, 0.90, 0.72), size=170.0),
        fog=dict(density=0.0011, color=(1.0, 0.86, 0.64), vol_end=900.0,
                 ambient=(1.0, 0.95, 0.90), ambient_strength=0.50),
        skyfill=dict(energy=1.1, dir=(0.15, -0.35, 0.92), color=(0.92, 0.95, 1.0),
                     angle=12.0),
        sun=dict(energy=5.5, color=(1.0, 0.94, 0.82), angle_deg=1.6),
        fill=dict(energy=190.0, color=(1.0, 0.93, 0.82), size=170.0, height=22.0),
        ground=dict(color_a=(0.58, 0.46, 0.20), color_b=(0.24, 0.22, 0.10), noise_scale=2.4),
        hills=None, field_color="gold", exposure=-2.15, look="Medium High Contrast", samples=10,
        field=dict(count=1050, area=(36, 46), scale_range=(0.92, 1.20)),
        grass=dict(count=2400, area=(30, 34)),
    ),
    "gold_dusk": dict(
        sky=dict(c_horizon=(1.0, 0.36, 0.06), c_mid=(0.72, 0.20, 0.28),
                 c_zenith=(0.07, 0.06, 0.24), sun_dir=(0.03, 0.92, 0.14),
                 sun_color=(1.0, 0.55, 0.22), sun_power=72.0, glow=0.16, strength=0.85,
                 cloud=((1.0, 0.55, 0.42), 0.18, 1.30, 0.34), sun_exp=2000.0, glow_exp=12.0),
        bounce=dict(loc=(0.0, 5.0, 1.9), target=(0.0, 5.0, 0.0), energy=110.0,
                    size=24.0, color=(1.0, 0.55, 0.40)),
        mist=dict(height=1.10, density=0.080, color=(1.0, 0.62, 0.42), size=170.0),
        fog=dict(density=0.0016, color=(1.0, 0.58, 0.36), vol_end=800.0,
                 ambient=(1.0, 0.72, 0.58), ambient_strength=0.45),
        skyfill=dict(energy=0.8, dir=(-0.1, -0.25, 0.95), color=(1.0, 0.80, 0.75),
                     angle=14.0),
        sun=dict(energy=4.2, color=(1.0, 0.55, 0.32), angle_deg=1.8),
        fill=dict(energy=140.0, color=(1.0, 0.66, 0.50), size=130.0, height=16.0),
        ground=dict(color_a=(0.44, 0.26, 0.12), color_b=(0.13, 0.10, 0.06), noise_scale=2.4),
        hills=None, field_color="gold", exposure=-2.05, look="Medium High Contrast", samples=10,
        field=dict(count=1000, area=(36, 46), scale_range=(0.92, 1.20)),
        grass=dict(count=2300, area=(30, 34)),
    ),
    "violet_dusk": dict(
        sky=dict(c_horizon=(0.62, 0.16, 0.32), c_mid=(0.13, 0.06, 0.28),
                 c_zenith=(0.012, 0.010, 0.05), sun_dir=(0.02, 0.94, 0.10),
                 sun_color=(1.0, 0.35, 0.35), sun_power=55.0, glow=0.14, strength=0.85,
                 cloud=((0.45, 0.28, 0.60), 0.25, 1.50, 0.26), sun_exp=1500.0, glow_exp=14.0),
        bounce=dict(loc=(0.0, 5.0, 1.9), target=(0.0, 5.0, 0.0), energy=260.0,
                    size=22.0, color=(0.62, 0.45, 0.95)),
        mist=dict(height=1.05, density=0.085, color=(0.58, 0.44, 0.82), size=160.0),
        fog=dict(density=0.0020, color=(0.55, 0.40, 0.80), vol_end=700.0,
                 ambient=(0.64, 0.52, 1.0), ambient_strength=0.40),
        skyfill=dict(energy=1.2, dir=(-0.2, -0.3, 0.9), color=(0.70, 0.72, 1.0),
                     angle=16.0),
        sun=dict(energy=4.0, color=(1.0, 0.45, 0.42), angle_deg=2.0),
        fill=dict(energy=300.0, color=(0.66, 0.50, 1.0), size=110.0, height=15.0),
        ground=dict(color_a=(0.21, 0.12, 0.23), color_b=(0.055, 0.045, 0.09), noise_scale=2.4),
        hills=None, field_color="violet", exposure=-1.85, look="Medium High Contrast", samples=10,
        field=dict(count=950, area=(34, 42), scale_range=(0.92, 1.16)),
        grass=dict(count=2100, area=(30, 34)),
    ),
    "violet_night": dict(
        sky=dict(c_horizon=(0.10, 0.07, 0.22), c_mid=(0.035, 0.030, 0.13),
                 c_zenith=(0.004, 0.004, 0.020), sun_dir=(-0.10, 0.80, 0.22),
                 sun_color=(0.85, 0.82, 1.0), sun_power=30.0, glow=0.12, strength=0.95,
                 cloud=((0.26, 0.20, 0.42), 0.26, 1.5, 0.24),
                 star=(2.2, 130.0, 0.9986, 1.0),
                 sun_exp=1600.0, glow_exp=26.0),
        bounce=dict(loc=(0.0, 5.0, 1.9), target=(0.0, 5.0, 0.0), energy=180.0,
                    size=22.0, color=(0.45, 0.42, 0.90)),
        mist=dict(height=1.05, density=0.080, color=(0.28, 0.22, 0.52), size=160.0),
        fog=dict(density=0.0016, color=(0.26, 0.20, 0.50), vol_end=800.0,
                 ambient=(0.36, 0.36, 0.74), ambient_strength=0.45),
        skyfill=dict(energy=1.0, dir=(-0.15, -0.3, 0.9), color=(0.55, 0.60, 1.0),
                     angle=18.0),
        sun=dict(energy=2.2, color=(0.78, 0.78, 1.0), angle_deg=1.4),
        fill=dict(energy=340.0, color=(0.50, 0.42, 0.95), size=120.0, height=14.0),
        ground=dict(color_a=(0.13, 0.08, 0.17), color_b=(0.03, 0.025, 0.055), noise_scale=2.2),
        hills=None, field_color="violet", exposure=-1.15, look="Medium High Contrast", samples=10,
        field=dict(count=1050, area=(36, 46), scale_range=(0.92, 1.16)),
        grass=dict(count=2200, area=(30, 34)),
    ),
}


def build_world(V):
    s = V["sky"]
    lib.sky_dome(c_horizon=s["c_horizon"], c_mid=s["c_mid"], c_zenith=s["c_zenith"],
                 sun_dir=s["sun_dir"], sun_color=s["sun_color"], sun_power=s["sun_power"],
                 glow=s["glow"], strength=s["strength"], cloud=s.get("cloud"),
                 star=s.get("star"), sun_exp=s.get("sun_exp", 900.0),
                 glow_exp=s.get("glow_exp", 8.0))
    f = V["fog"]
    lib.fog(density=f["density"], color=f["color"], ambient=f["ambient"],
            ambient_strength=f["ambient_strength"], world_volume=False)
    try:
        lib.scene().eevee.volumetric_end = f.get("vol_end", 120.0)
        lib.scene().eevee.volumetric_start = 0.4
        lib.scene().eevee.volumetric_samples = 48
    except Exception:
        pass
    su = V["sun"]
    lib.sun_light(energy=su["energy"], direction=s["sun_dir"], color=su["color"],
                  angle_deg=su["angle_deg"])
    fl = V["fill"]
    _fl = lib.fill_light(energy=fl["energy"], color=fl["color"], size=fl["size"], height=fl["height"])
    _fl.data.use_shadow = False
    # second "sky bounce" sun from above so backlit shadow sides are not dead black
    sf = V.get("skyfill")
    if sf:
        lib.sun_light(energy=sf["energy"], direction=sf["dir"], color=sf["color"],
                      angle_deg=sf.get("angle", 8.0))
    g = V["ground"]
    lib.ground(color_a=g["color_a"], color_b=g["color_b"], noise_scale=g["noise_scale"],
               size=2400.0)
    h = V.get("hills")
    if h:
        lib.hills(distance=h["distance"], height=h["height"], color=h["color"],
                  emission=h.get("emission", 0.5), seed=7)
    bounce = V.get("bounce")
    if bounce:
        _bo = lib.area_light("Bounce", loc=bounce["loc"], target=bounce["target"],
                             energy=bounce["energy"], size=bounce["size"],
                             color=bounce["color"])
        _bo.data.use_shadow = False
    # NOTE: no volume scatter in field shots — EEVEE volumes attenuate direct light,
    # which killed the scene contrast.  Haze is added in post (comp).


def build_field(V, count=None):
    f = V["field"]
    fd = Vector(V["sky"]["sun_dir"])
    face = (fd.x, fd.y) if (fd.x * fd.x + fd.y * fd.y) > 1e-4 else (0.0, 1.0)
    n = count or f["count"]
    objs = lib.sunflower_field(count=n, area=f["area"], seed=11,
                               color_set=V["field_color"], scale_range=f["scale_range"],
                               stem_random=(1.25, 1.62), face_dir=face, face_jitter=0.5,
                               exclude_radius=0.55, leaf=False)
    # dense near cluster so the foreground reads as a real field
    if count is None:
        objs += lib.sunflower_field(count=int(n * 0.55), area=(15.0, 15.0),
                                    center=(0.0, 3.0), seed=29,
                                    color_set=V["field_color"],
                                    scale_range=(0.96, 1.24),
                                    stem_random=(1.30, 1.70),
                                    face_dir=face, face_jitter=0.55,
                                    exclude_radius=0.7, leaf=False)
    g = V["grass"]
    lib.grass_patch(count=int(g["count"] * 0.22), area=(20, 20), seed=5, color_set=
                    ("violet" if V["field_color"] == "violet" else "gold"))
    # tall leafy understory: occludes the bare stems so the field reads as a crop
    lib.grass_patch(name="Understory", count=int(g["count"] * 0.75), area=(36, 40), seed=8,
                    height=(0.30, 0.80), color_set=
                    ("violet" if V["field_color"] == "violet" else "gold"))
    return objs


# --------------------------------------------------------------------------- helpers
def girl(name="Girl", loc=(0, 0, 0), facing_deg=180.0, pose="stand", height=1.57,
         dress_len=0.40, hair_len=0.62, seed=0):
    g = character.figure(name, variant="girl", pose=pose, height=height,
                         dress_len=dress_len, hair_len=hair_len, seed=seed)
    g.location = loc
    g.rotation_euler = (0, 0, math.radians(facing_deg))
    character.idle(g, amp=0.009, phase=seed * 1.7, keys=(1, 90))
    return g


def boy(name="Boy", loc=(0, 0, 0), facing_deg=180.0, pose="stand", height=1.73, seed=1):
    b = character.figure(name, variant="boy", pose=pose, height=height, seed=seed)
    b.location = loc
    b.rotation_euler = (0, 0, math.radians(facing_deg))
    character.idle(b, amp=0.008, phase=seed * 2.3, keys=(1, 90))
    return b


def couple(loc=(0, 0, 0), facing_deg=180.0, hold=True, gap=0.36, ha=1.57, hb=1.73):
    a = character.figure("Girl", variant="girl", pose="hold", height=ha, hand_reach=gap / 2)
    b = character.figure("Boy", variant="boy", pose="hold", height=hb, hand_reach=gap / 2)
    root = Vector(loc)
    ca = math.cos(math.radians(facing_deg)) * gap / 2
    sa = math.sin(math.radians(facing_deg)) * gap / 2
    a.location = root + Vector((-ca, sa, 0))
    b.location = root + Vector((ca, -sa, 0))
    a.rotation_euler = (0, 0, math.radians(facing_deg))
    b.rotation_euler = (0, 0, math.radians(facing_deg))
    character.idle(a, amp=0.007, keys=(1, 90))
    character.idle(b, amp=0.006, keys=(1, 90))
    return a, b


def hero_flower(loc, size=1.0, color_set="violet", seed=3, tilt=24.0, stem=1.35, petals=26):
    pals = lib._petal_set(color_set)
    ob = lib.sunflower("Hero", size=size, n_petals=petals, petal_len=0.235,
                       stem_len=stem, head_tilt=tilt, mats=pals[2], pose_seed=seed,
                       head_azim=math.pi)
    ob.location = loc
    return ob


def float_petals(count=90, area=(14, 16), z0=0.2, z1=2.4, speed=0.45, seed=2,
                 color_set="violet", center=(0, 0)):
    """Individual petal cards slowly rising (for S52/S53)."""
    rng = random.Random(seed)
    pals = lib._petal_set(color_set)
    objs = []
    fr = SHOT_CURRENT["f0"]
    for i in range(count):
        x = center[0] + rng.uniform(-area[0] / 2, area[0] / 2)
        y = center[1] + rng.uniform(-area[1] / 2, area[1] / 2)
        ob = lib.sunflower(f"petal{i:03d}", size=rng.uniform(0.16, 0.34),
                           n_petals=1, petal_len=0.20, stem_len=0.001, head_tilt=0,
                           mats=pals[0], pose_seed=rng.randint(0, 9999), leaf=False)
        # keep only the petals: hide stem/disc by scaling them away is overkill; instead
        # use a tiny stem and let comp/fog hide it — acceptable at these sizes.
        ob.location = (x, y, z0 + rng.uniform(0, z1))
        ob.rotation_euler = (rng.uniform(-1.2, 1.2), rng.uniform(-1.2, 1.2),
                             rng.uniform(0, 6.28))
        dz = rng.uniform(0.6, 1.4) * speed
        lib.anim_obj(ob, [(fr, ob.location.copy()),
                          (fr + 200, (x + rng.uniform(-0.6, 0.6),
                                      y + rng.uniform(-0.4, 0.4),
                                      ob.location.z + dz * 200 / 24.0))],
                     interp="LINEAR", path="location")
        objs.append(ob)
    return objs


def sparkles(count=60, area=(8, 6), center=(0, 3), z=(0.8, 2.2), seed=4,
             color=(1.0, 0.85, 1.0)):
    """Tiny emissive dots = floating pollen / magic dust (bloomed in comp)."""
    mat = bpy.data.materials.get("sparkle_mat")
    if mat is None:
        mat = lib.emission("sparkle_mat", color, strength=6.0)
    rng = random.Random(seed)
    for i in range(count):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=8, ring_count=6, radius=0.006)
        ob = bpy.context.object
        ob.name = f"spark{i:03d}"
        ob.data.materials.append(mat)
        ob.location = (center[0] + rng.uniform(-area[0] / 2, area[0] / 2),
                       center[1] + rng.uniform(-area[1] / 2, area[1] / 2),
                       rng.uniform(*z))
        drift = rng.uniform(0.15, 0.5)
        fr = SHOT_CURRENT["f0"]
        lib.anim_obj(ob, [(fr, ob.location.copy()),
                          (fr + 260, (ob.location.x + rng.uniform(-0.3, 0.3),
                                      ob.location.y + rng.uniform(-0.2, 0.4),
                                      ob.location.z + drift))],
                     interp="LINEAR", path="location")


SHOT_CURRENT = {"f0": 1}

# shots where the camera should not be blocked by flowers growing through it
NO_CLEAR = {"S11", "S13", "S14", "S15", "S17", "S33", "S44", "S49", "S52", "S30", "S48"}
# shots lit from behind the camera (sun behind the lens -> sunflower faces visible)
SUNFLIP = {"S12": True}


def clear_camera_path(shot, radius=1.05, step=4, max_z=3.4):
    """Delete field flowers that the camera flies through."""
    sc = bpy.context.scene
    cam = sc.camera
    if cam is None:
        return
    pts = []
    for f in range(shot["f0"], shot["f1"] + 1, step):
        sc.frame_set(f)
        p = cam.matrix_world.translation
        if p.z < max_z:
            pts.append(p.copy())
    sc.frame_set(shot["f0"])
    removed = 0
    for ob in list(bpy.data.objects):
        n = ob.name
        if not (n.startswith("SF") or n.startswith("Hero") or n.startswith("petal")):
            continue
        p = ob.matrix_world.translation
        for q in pts:
            dx = p.x - q.x
            dy = p.y - q.y
            if dx * dx + dy * dy < radius * radius:
                bpy.data.objects.remove(ob, do_unlink=True)
                removed += 1
                break
    print(f"[clear] {shot['id']}: removed {removed} flowers from camera path")


# --------------------------------------------------------------------------- per-shot staging
def s11(shot, V):
    """macro: sunflower head turning to the sun (pre-chorus)."""
    hero_flower((0.10, 2.45, 0.0), size=1.10, color_set="gold", seed=21, tilt=28,
                stem=1.34, petals=29)
    lib.camera((0.16, 0.28, 1.40), (0.06, 2.45, 1.30), lens=85, fstop=2.2,
               focus_distance=2.25)
    cam = bpy.context.scene.camera
    lib.anim_camera(cam, [(shot["f0"], (0.20, 0.32, 1.41), (0.05, 2.45, 1.29), 2.3),
                          (shot["f1"], (0.02, 0.14, 1.36), (0.08, 2.45, 1.33), 2.45)])


def s12(shot, V):
    """low dolly through golden field toward the sun, girl ahead."""
    girl(loc=(0.55, 5.6, 0), facing_deg=6, pose="stand", height=1.56, seed=3)
    cam = lib.camera((0.35, -1.9, 1.38), (0.5, 6.0, 1.46), lens=35, fstop=2.2,
                     focus_distance=7.4)
    lib.anim_camera(cam, [(shot["f0"], (0.35, -1.9, 1.36), (0.5, 6.0, 1.40), 7.5),
                          (shot["f1"], (0.30, 0.35, 1.78), (0.55, 6.0, 1.52), 6.2)])


def s13(shot, V):
    """violet sunflower in foreground focus, gold field behind."""
    hero_flower((-0.55, 3.6, 0), size=1.08, color_set="violet", seed=7, tilt=22, stem=1.55)
    lib.sunflower_field(count=420, area=(26, 20), seed=31, color_set="gold",
                        scale_range=(0.95, 1.2), face_dir=(0.0, 1.0), face_jitter=0.6)
    cam = lib.camera((0.05, 1.45, 1.42), (-0.5, 3.55, 1.34), lens=85, fstop=1.8,
                     focus_distance=2.15)
    lib.anim_camera(cam, [(shot["f0"], (0.10, 1.55, 1.43), (-0.5, 3.55, 1.35), 2.2),
                          (shot["f1"], (0.0, 1.32, 1.39), (-0.5, 3.55, 1.31), 2.0)])


def s14(shot, V):
    """slow orbit around violet hero flower, sparkles, flare."""
    hero_flower((0.0, 3.2, 0), size=1.12, color_set="violet", seed=13, tilt=26, stem=1.5)
    lib.sunflower_field(count=380, area=(24, 18), seed=41, color_set="gold",
                        scale_range=(0.95, 1.2), face_dir=(0.0, 1.0))
    sparkles(count=46, area=(5, 4), center=(0.0, 3.2), z=(0.9, 2.0), seed=8)
    f0, f1 = shot["f0"], shot["f1"]
    lib.camera((1.05, 1.35, 1.44), (0.0, 3.2, 1.30), lens=85, fstop=1.9, focus_distance=2.2)
    cam = bpy.context.scene.camera
    lib.anim_camera(cam, [(f0, (0.95, 1.30, 1.40), (0.0, 3.2, 1.30), 2.2),
                          ((f0 + f1) // 2, (0.0, 1.05, 1.46), (0.0, 3.2, 1.28), 2.2),
                          (f1, (-0.85, 1.35, 1.42), (0.0, 3.2, 1.32), 2.2)])


def s15(shot, V):
    """macro translucent petals fill frame, drift up into light."""
    hero_flower((0.35, 2.35, 0), size=1.15, color_set="gold", seed=17, tilt=34, stem=1.45)
    cam = lib.camera((0.30, 0.95, 1.50), (0.35, 2.35, 1.36), lens=100, fstop=2.2,
                     focus_distance=1.45)
    lib.anim_camera(cam, [(shot["f0"], (0.32, 0.98, 1.46), (0.35, 2.35, 1.38), 1.4),
                          (shot["f1"], (0.40, 0.90, 1.68), (0.36, 2.35, 1.62), 1.5)])


def s16(shot, V):
    """low wide: two silhouettes sitting in long shadows, seen from behind."""
    g = girl(loc=(-0.55, 7.6, 0), facing_deg=10, pose="sit", height=1.55, seed=4)
    b = boy(loc=(0.50, 7.75, 0), facing_deg=10, pose="sit", height=1.70, seed=6)
    cam = lib.camera((-2.2, 2.6, 1.25), (0.0, 7.65, 1.30), lens=40, fstop=2.2,
                     focus_distance=6.2)
    lib.anim_camera(cam, [(shot["f0"], (-2.35, 2.45, 1.20), (0.0, 7.65, 1.26), 6.4),
                          (shot["f1"], (-1.75, 2.95, 1.32), (0.0, 7.65, 1.34), 5.8)])


def s17(shot, V):
    """macro dappled light in grass, long shadow sweeping across."""
    g = girl(loc=(0.9, 2.6, 0), facing_deg=200, pose="walk", height=1.55, seed=9)
    cam = lib.camera((-0.75, 1.55, 0.26), (0.75, 3.1, 0.46), lens=55, fstop=1.7,
                     focus_distance=1.35)
    lib.anim_camera(cam, [(shot["f0"], (-0.78, 1.58, 0.24), (0.7, 3.05, 0.46), 1.3),
                          (shot["f1"], (-0.62, 1.42, 0.30), (0.8, 3.15, 0.44), 1.45)])


def s18(shot, V):
    """low angle backlit silhouette, halo, sun through petals."""
    g = girl(loc=(0.2, 3.5, 0), facing_deg=2, pose="stand", height=1.58, seed=11)
    cam = lib.camera((0.55, 0.9, 0.55), (0.2, 3.6, 1.15), lens=40, fstop=1.9,
                     focus_distance=2.85)
    lib.anim_camera(cam, [(shot["f0"], (0.58, 0.95, 0.52), (0.2, 3.6, 1.05), 2.8),
                          (shot["f1"], (0.30, 0.65, 0.80), (0.2, 3.6, 1.35), 3.0)])


def s19(shot, V):
    """foreground sunflower sway, two silhouettes holding hands behind."""
    couple(loc=(0.1, 6.6, 0), facing_deg=0, gap=0.40)
    hero_flower((-0.95, 1.95, 0), size=1.22, color_set="gold", seed=23, tilt=16, stem=1.55)
    cam = lib.camera((0.05, 0.05, 1.30), (0.1, 6.6, 1.42), lens=58, fstop=1.8,
                     focus_distance=1.95)
    lib.anim_camera(cam, [(shot["f0"], (0.0, 0.22, 1.28), (0.1, 6.6, 1.46), 2.0),
                          (shot["f1"], (0.05, -0.02, 1.36), (0.1, 6.6, 1.42), 5.6)])


def s27(shot, V):
    """wide sunset field, wind waves, petals drifting."""
    girl(loc=(-1.1, 7.5, 0), facing_deg=6, pose="stand", height=1.55, seed=14)
    cam = lib.camera((0.5, -2.5, 1.34), (0.0, 8.0, 1.40), lens=32, fstop=2.6, focus_distance=9.0)
    lib.anim_camera(cam, [(shot["f0"], (0.6, -2.6, 1.32), (-0.2, 8.0, 1.36), 9.0),
                          (shot["f1"], (0.2, -1.4, 1.62), (0.1, 8.0, 1.44), 8.0)])


def s29(shot, V):
    """cloud time-lapse over field; sun sinks."""
    girl(loc=(0.9, 8.4, 0), facing_deg=4, pose="stand", height=1.54, seed=15)
    cam = lib.camera((-0.8, -3.2, 1.32), (0.7, 9.2, 1.48), lens=30, fstop=2.8, focus_distance=10.0)
    lib.anim_camera(cam, [(shot["f0"], (-0.9, -3.3, 1.28), (0.6, 9.2, 1.44), 10.0),
                          (shot["f1"], (-0.5, -2.6, 1.56), (0.8, 9.2, 1.60), 9.5)])


def s30(shot, V):
    """rapid beats: petal / couple / running figure / sun — hard jumps."""
    hero_flower((0.0, 1.55, 0), size=0.95, color_set="gold", seed=31, tilt=20, stem=1.35)
    couple(loc=(0.4, 5.2, 0), facing_deg=180, gap=0.38)
    girl(loc=(-1.2, 7.2, 0), facing_deg=210, pose="run", height=1.55, seed=19)
    f0, f1 = shot["f0"], shot["f1"]
    q = (f1 - f0) // 4
    b = [f0, f0 + q, f0 + 2 * q, f0 + 3 * q, f1]
    cam = lib.camera((0.0, 0.35, 1.45), (0.0, 1.55, 1.30), lens=100, fstop=1.8,
                     focus_distance=1.2)
    keys = [
        (b[0], (0.0, 0.30, 1.46), (0.0, 1.55, 1.32), 1.25),
        (b[1] - 1, (0.0, 0.30, 1.46), (0.0, 1.55, 1.32), 1.25),
        (b[1], (0.35, 3.0, 1.22), (0.4, 5.2, 1.35), 2.3),
        (b[2] - 1, (0.38, 3.05, 1.24), (0.4, 5.2, 1.35), 2.3),
        (b[2], (-2.4, 3.6, 1.05), (-1.2, 7.2, 1.1), 4.0),
        (b[3] - 1, (-2.35, 3.65, 1.06), (-1.2, 7.2, 1.1), 4.0),
        (b[3], (0.1, 0.6, 1.5), (0.2, 6.0, 1.9), 6.0),
        (b[4], (0.12, 0.5, 1.52), (0.2, 6.0, 1.95), 6.0),
    ]
    lib.anim_camera(cam, keys, interp="CONSTANT")


def s31(shot, V):
    """camera rises through violet sunflowers, storm sky, girl ahead."""
    girl(loc=(0.3, 6.8, 0), facing_deg=4, pose="stand", height=1.56, seed=21)
    cam = lib.camera((0.9, -1.6, 0.95), (0.3, 6.8, 1.55), lens=38, fstop=2.2, focus_distance=8.5)
    lib.anim_camera(cam, [(shot["f0"], (0.95, -1.7, 0.90), (0.4, 6.8, 1.35), 8.6),
                          (shot["f1"], (0.55, -0.5, 2.55), (0.3, 6.8, 1.75), 7.4)])


def s33(shot, V):
    """close rim-lit hands: one pulls the other pull-the-wrist moment."""
    a, b = couple(loc=(0.0, 4.6, 0), facing_deg=196, gap=0.34, ha=1.56, hb=1.72)
    b.location += Vector((0.12, -0.18, 0))
    cam = lib.camera((0.15, 2.05, 1.02), (-0.02, 4.45, 0.92), lens=100, fstop=2.0,
                     focus_distance=2.1)
    lib.anim_camera(cam, [(shot["f0"], (0.18, 2.10, 1.04), (-0.05, 4.45, 0.90), 2.15),
                          (shot["f1"], (0.08, 1.92, 0.98), (0.05, 4.45, 0.95), 2.0)])


def s34(shot, V):
    """tracking two silhouettes running through violet field."""
    a, b = couple(loc=(0.0, 6.5, 0), facing_deg=180, gap=0.42, ha=1.56, hb=1.72)
    # running pose for both
    for o, side in ((a, -1), (b, 1)):
        o.rotation_euler = (0, 0, math.radians(180))
    cam = lib.camera((1.5, 2.2, 1.1), (-0.3, 6.6, 1.3), lens=42, fstop=2.0, focus_distance=4.5)
    lib.anim_camera(cam, [(shot["f0"], (1.65, 2.4, 1.06), (-0.4, 6.6, 1.26), 4.6),
                          (shot["f1"], (0.75, 2.0, 1.22), (-0.1, 6.6, 1.36), 4.2)])


def s43(shot, V):
    """wide crane up: night violet field glowing, girl center."""
    girl(loc=(0.05, 6.4, 0), facing_deg=2, pose="stand", height=1.56, seed=27)
    cam = lib.camera((1.35, -2.6, 1.55), (0.05, 6.4, 1.4), lens=34, fstop=2.4, focus_distance=9.0)
    lib.anim_camera(cam, [(shot["f0"], (1.4, -2.7, 1.5), (0.1, 6.4, 1.35), 9.0),
                          (shot["f1"], (0.9, -1.5, 3.9), (0.05, 6.4, 1.55), 8.0)])


def s44(shot, V):
    """hero violet sunflower, dew, moonlight, sparkle."""
    hero_flower((0.0, 2.9, 0), size=1.06, color_set="violet", seed=33, tilt=24, stem=1.42)
    sparkles(count=40, area=(2.6, 2.4), center=(0.0, 3.0), z=(1.0, 1.9), seed=12,
             color=(0.86, 0.78, 1.0))
    cam = lib.camera((0.42, 0.75, 1.38), (0.0, 2.9, 1.28), lens=100, fstop=1.8,
                     focus_distance=2.1)
    lib.anim_camera(cam, [(shot["f0"], (0.45, 0.80, 1.40), (-0.02, 2.9, 1.26), 2.05),
                          (shot["f1"], (0.22, 0.62, 1.33), (0.02, 2.9, 1.32), 2.2)])


def s45(shot, V):
    """sunset horizon, two silhouettes hand in hand, back view."""
    couple(loc=(0.0, 9.4, 0), facing_deg=0, gap=0.36)
    cam = lib.camera((0.7, 1.2, 1.42), (0.0, 9.4, 1.52), lens=38, fstop=2.2, focus_distance=8.4)
    lib.anim_camera(cam, [(shot["f0"], (0.75, 1.15, 1.38), (0.0, 9.4, 1.48), 8.4),
                          (shot["f1"], (0.50, 1.75, 1.52), (0.0, 9.4, 1.58), 7.8)])


def s46(shot, V):
    """close two silhouettes back view, one leans, flare."""
    couple(loc=(-0.05, 7.2, 0), facing_deg=6, gap=0.34)
    cam = lib.camera((0.55, 2.2, 1.34), (-0.05, 6.9, 1.28), lens=58, fstop=2.0,
                     focus_distance=5.3)
    lib.anim_camera(cam, [(shot["f0"], (0.58, 2.25, 1.32), (-0.05, 6.9, 1.24), 5.3),
                          (shot["f1"], (0.40, 2.55, 1.40), (-0.02, 6.9, 1.32), 5.0)])


def s47(shot, V):
    """wide girl alone, flare, push in."""
    girl(loc=(0.0, 6.2, 0), facing_deg=0, pose="stand", height=1.56, seed=35)
    cam = lib.camera((0.6, -0.9, 1.28), (0.0, 6.2, 1.36), lens=40, fstop=2.2, focus_distance=7.2)
    lib.anim_camera(cam, [(shot["f0"], (0.65, -1.0, 1.26), (0.0, 6.2, 1.34), 7.3),
                          (shot["f1"], (0.45, 1.9, 1.50), (0.0, 6.2, 1.40), 4.8)])


def s48(shot, V):
    """memory flashes: gold field / petals / couple — hard cuts."""
    f0, f1 = shot["f0"], shot["f1"]
    q = (f1 - f0) // 3
    b = [f0, f0 + q, f0 + 2 * q, f1]
    couple(loc=(0.6, 5.6, 0), facing_deg=180, gap=0.38)
    hero_flower((-0.5, 2.4, 0), size=1.1, color_set="gold", seed=41, tilt=22, stem=1.45)
    girl(loc=(-1.0, 6.6, 0), facing_deg=196, pose="stand", height=1.56, seed=37)
    cam = lib.camera((0.0, 0.3, 1.45), (-0.5, 2.4, 1.32), lens=100, fstop=1.8, focus_distance=2.1)
    keys = [
        (b[0], (0.0, 0.25, 1.46), (-0.5, 2.4, 1.34), 2.1),
        (b[1] - 1, (0.0, 0.25, 1.46), (-0.5, 2.4, 1.34), 2.1),
        (b[1], (0.1, 2.4, 1.35), (0.6, 5.6, 1.3), 3.3),
        (b[2] - 1, (0.12, 2.42, 1.36), (0.6, 5.6, 1.3), 3.3),
        (b[2], (1.5, 2.0, 1.15), (-1.0, 6.6, 1.25), 4.8),
        (b[3], (1.55, 1.8, 1.2), (-1.0, 6.6, 1.28), 4.9),
    ]
    lib.anim_camera(cam, keys, interp="CONSTANT")


def s49(shot, V):
    """violet sunflower macro, petals trembling, light pulses."""
    hero_flower((0.0, 2.55, 0), size=1.0, color_set="violet", seed=43, tilt=20, stem=1.45)
    sun = bpy.data.objects.get("Sun")
    f0, f1 = shot["f0"], shot["f1"]
    if sun:
        lib._set_interp("LINEAR")
        for i, f in enumerate(range(f0, f1 + 1, 12)):
            sun.data.energy = 1.0 + (0.55 if i % 2 == 0 else 0.0)
            sun.data.keyframe_insert("energy", frame=f)
    cam = lib.camera((0.28, 0.55, 1.36), (0.0, 2.55, 1.30), lens=100, fstop=1.7,
                     focus_distance=2.0)
    lib.anim_camera(cam, [(f0, (0.30, 0.58, 1.37), (-0.01, 2.55, 1.28), 2.0),
                          (f1, (0.16, 0.42, 1.33), (0.01, 2.55, 1.33), 2.15)])


def s51(shot, V):
    """sunflower sway, two silhouettes hold hands (back view), slow motion."""
    couple(loc=(0.1, 7.4, 0), facing_deg=2, gap=0.36)
    hero_flower((-0.95, 2.1, 0), size=1.18, color_set="gold", seed=47, tilt=16, stem=1.52)
    cam = lib.camera((0.05, 0.1, 1.30), (0.1, 7.4, 1.42), lens=62, fstop=1.9,
                     focus_distance=2.0)
    lib.anim_camera(cam, [(shot["f0"], (0.05, 0.18, 1.30), (0.1, 7.4, 1.42), 2.0),
                          (shot["f1"], (0.0, -0.08, 1.26), (0.1, 7.4, 1.38), 6.6)])


def s52(shot, V):
    """close violet sunflower, petals begin to rise."""
    hero_flower((0.0, 3.0, 0), size=1.15, color_set="violet", seed=53, tilt=18, stem=1.45)
    float_petals(count=70, area=(6, 7), z0=0.4, z1=3.2, speed=0.55, seed=21,
                 color_set="violet", center=(0.0, 3.4))
    cam = lib.camera((0.30, 1.1, 1.42), (0.0, 3.0, 1.28), lens=85, fstop=1.9,
                     focus_distance=1.95)
    lib.anim_camera(cam, [(shot["f0"], (0.32, 1.16, 1.42), (-0.01, 3.0, 1.26), 1.95),
                          (shot["f1"], (0.12, 0.95, 1.46), (0.02, 3.0, 1.34), 2.1)])


def s53(shot, V):
    """wide night field, petals rising into the sky, tilt up."""
    girl(loc=(0.2, 7.6, 0), facing_deg=2, pose="stand", height=1.55, seed=41)
    float_petals(count=110, area=(20, 24), z0=0.3, z1=4.0, speed=0.7, seed=23,
                 color_set="violet", center=(0.0, 7.0))
    cam = lib.camera((0.4, -2.2, 1.30), (0.1, 8.0, 1.72), lens=30, fstop=2.6, focus_distance=9.5)
    lib.anim_camera(cam, [(shot["f0"], (0.42, -2.3, 1.28), (0.1, 8.0, 1.58), 9.5),
                          (shot["f1"], (0.25, -2.1, 1.52), (0.1, 8.0, 3.95), 8.0)])


def s54(shot, V):
    """panorama crane high above glowing field under stars."""
    girl(loc=(0.2, 8.2, 0), facing_deg=2, pose="stand", height=1.55, seed=43)
    cam = lib.camera((1.1, -0.6, 3.2), (0.15, 9.0, 1.2), lens=26, fstop=3.2, focus_distance=11.0)
    lib.anim_camera(cam, [(shot["f0"], (1.15, -0.7, 3.1), (0.15, 9.0, 1.0), 11.0),
                          (shot["f1"], (0.2, 3.2, 9.5), (0.15, 12.0, 0.5), 9.0)])


SETUP = {
    "S11": s11, "S12": s12, "S13": s13, "S14": s14, "S15": s15,
    "S16": s16, "S17": s17, "S18": s18, "S19": s19,
    "S27": s27, "S29": s29, "S30": s30,
    "S31": s31, "S33": s33, "S34": s34,
    "S43": s43, "S44": s44, "S45": s45, "S46": s46, "S47": s47,
    "S48": s48, "S49": s49, "S51": s51, "S52": s52, "S53": s53, "S54": s54,
}


# --------------------------------------------------------------------------- main
def render_shot(sid, test=False):
    shot = SHOT[sid]
    V = VARIANTS[shot["variant"]]
    if SUNFLIP.get(sid):
        V = copy.deepcopy(V)
        sx, sy, sz = V["sky"]["sun_dir"]
        V["sky"]["sun_dir"] = (-sx, -sy, sz)
    SHOT_CURRENT["f0"] = shot["f0"]
    lib.reset()
    res = (1280, 720) if test else (1920, 1080)
    lib.setup_render(samples=12 if test else V["samples"], resolution=res,
                     exposure=V["exposure"], look=V["look"])
    build_world(V)
    build_field(V, count=None)
    SETUP[sid](shot, V)
    if sid not in NO_CLEAR:
        clear_camera_path(shot)
    sc = lib.scene()
    sc.frame_start, sc.frame_end = shot["f0"], shot["f1"]
    if test:
        sc.frame_set((shot["f0"] + shot["f1"]) // 2)
        os.makedirs(os.path.join(ROOT, "plates", "_tests"), exist_ok=True)
        sc.render.filepath = os.path.join(ROOT, "plates", "_tests", f"L_{sid}_{shot['variant']}.png")
        bpy.ops.render.render(write_still=True)
        print("TEST STILL", sc.render.filepath)
    else:
        out = os.path.join(ROOT, "plates", sid)
        lib.render(shot, out)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    sid = None
    test = "--test" in argv
    for i, a in enumerate(argv):
        if a == "--shot":
            sid = argv[i + 1]
    if sid is None:
        print("SHOTS:", " ".join(sorted(SETUP)))
    else:
        render_shot(sid, test=test)
