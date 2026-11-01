# -*- coding: utf-8 -*-
"""
sets_void.py — Team A (scenery-nature), the void world.

    S03  void/petals_dark  f279-433   100mm macro push-in on dried petals,
                                       a light leak growing to white-gold
    S42  void/petals_dark  f4501-4579 black water, violet light fading out

Pure black void, no sky, no ground.  Blender 5.2 headless, imports lib only.

usage:
    blender -b -P blender/sets_void.py -- look S03
    blender -b -P blender/sets_void.py -- shot S03
    blender -b -P blender/sets_void.py -- still S03 300
"""
import bpy, bmesh, math, random, os, sys, json, time
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
import lib

ROOT = lib.ROOT
PLATES = os.path.join(ROOT, "plates")
TESTS = os.path.join(PLATES, "_tests")
SHOTS = json.load(open(os.path.join(ROOT, "story", "shots.json"), encoding="utf-8"))["shots"]
BY_ID = {s["id"]: s for s in SHOTS}


# ---------------------------------------------------------------- geometry
def petal(name, length=0.075, width=0.026, bend=0.55, cup=0.35, mat=None, seed=0):
    """One curved, cupped dried petal (a strip of quads)."""
    rng = random.Random(seed)
    bm = bmesh.new()
    segs, rows = 5, 5
    grid = []
    for i in range(segs + 1):
        t = i / segs
        y = t * length
        w = width * math.sin(math.pi * (0.10 + 0.88 * t)) ** 0.55
        z = bend * (t ** 1.6) * length
        row = []
        for j in range(rows + 1):
            u = (j / rows) * 2.0 - 1.0
            row.append(bm.verts.new((u * w, y,
                                     z - cup * (1.0 - abs(u)) * w * 0.9
                                     + 0.06 * w * math.sin(t * 7.0 + u * 3.0))))
        grid.append(row)
    for i in range(segs):
        a, b = grid[i], grid[i + 1]
        for j in range(rows):
            bm.faces.new((a[j], b[j], b[j + 1], a[j + 1]))
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    lib.scene().collection.objects.link(ob)
    for p in me.polygons:
        p.use_smooth = True
    if mat:
        me.materials.append(mat)
    return ob


def dried_petal_mat(name):
    """Desaturated violet-brown dried petal, slight translucency."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = lib.principled(name, (0.105, 0.062, 0.075), roughness=0.62, subsurface=0.25,
                       sheen=0.35)
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    bsdf = next(n for n in N if n.type == "BSDF_PRINCIPLED")
    out = next(n for n in N if n.type == "OUTPUT_MATERIAL")
    tc = N.new("ShaderNodeTexCoord"); tc.location = (-900, 0)
    noise = N.new("ShaderNodeTexNoise"); noise.location = (-700, 0)
    noise.inputs["Scale"].default_value = 90.0
    noise.inputs["Detail"].default_value = 8.0
    L.new(tc.outputs["Object"], noise.inputs["Vector"])
    ramp = N.new("ShaderNodeValToRGB"); ramp.location = (-450, 0)
    ramp.color_ramp.elements[0].color = (0.055, 0.030, 0.042, 1.0)
    ramp.color_ramp.elements[1].color = (0.185, 0.105, 0.115, 1.0)
    e = ramp.color_ramp.elements.new(0.5)
    e.color = (0.115, 0.060, 0.078, 1.0)
    L.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    L.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (0.30, 0.115, 0.26, 1.0)
        bsdf.inputs["Emission Strength"].default_value = 0.06
    return m


def black_world(ambient=(0.012, 0.010, 0.018), strength=0.06):
    lib.fog(density=0.0, color=(0.02, 0.02, 0.03), ambient=ambient,
            ambient_strength=strength)


# =========================================================================== S03
def setup_S03():
    lib.reset()
    lib.setup_render(samples=14, resolution=(1920, 1080), exposure=0.0)
    try:
        lib.scene().eevee.use_raytracing = False
    except Exception:
        pass
    sc = lib.scene()
    try:
        sc.eevee.volumetric_end = 60.0
    except Exception:
        pass
    black_world()

    mat = dried_petal_mat("PetalDried")
    mat2 = dried_petal_mat("PetalDried2")
    mat2.name = "PetalDried2"
    # a fan of petals of different sizes: the macro subject sits ~0.35 m from the
    # lens, others drift through the dark at other depths
    rng = random.Random(7)
    petals = []
    # hero cluster
    for i in range(7):
        a = rng.uniform(0, math.tau)
        p = petal("PetalHero%02d" % i, length=rng.uniform(0.055, 0.085),
                  width=rng.uniform(0.020, 0.030), bend=rng.uniform(0.35, 0.8),
                  cup=rng.uniform(0.2, 0.5), mat=mat, seed=i)
        p.location = (rng.uniform(-0.05, 0.05), rng.uniform(-0.04, 0.05),
                      rng.uniform(-0.05, 0.04))
        p.rotation_euler = (rng.uniform(-0.9, 0.9), rng.uniform(-1.2, 1.2),
                            rng.uniform(0, math.tau))
        petals.append(p)
    # drifting background petals
    for i in range(16):
        p = petal("PetalBG%02d" % i, length=rng.uniform(0.03, 0.06), width=0.02,
                  bend=rng.uniform(0.2, 0.7), mat=mat, seed=100 + i)
        p.location = (rng.uniform(-0.9, 0.9), rng.uniform(-0.2, 1.1),
                      rng.uniform(-0.7, 0.5))
        p.rotation_euler = (rng.uniform(-math.pi, math.pi),
                            rng.uniform(-math.pi, math.pi),
                            rng.uniform(0, math.tau))
        petals.append(p)

    # the light leak: an emissive card behind the petals, violet -> white-gold
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=7.0)
    me = bpy.data.meshes.new("LeakCard")
    bm.to_mesh(me)
    bm.free()
    card = bpy.data.objects.new("LeakCard", me)
    sc.collection.objects.link(card)
    card.location = (0.0, 4.0, 0.55)
    card.rotation_euler = (math.radians(-76.0), 0, 0)
    m = bpy.data.materials.new("LeakMat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = (0.42, 0.20, 0.55, 1.0)
    em.inputs["Strength"].default_value = 0.05
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    me.materials.append(m)
    # soft radial falloff so the card has no hard edge
    tex = nt.nodes.new("ShaderNodeTexCoord")
    grad = nt.nodes.new("ShaderNodeTexGradient"); grad.gradient_type = "RADIAL"
    mapr = nt.nodes.new("ShaderNodeMapRange")
    mapr.inputs["From Min"].default_value = 0.04
    mapr.inputs["From Max"].default_value = 0.62
    mapr.inputs["To Min"].default_value = 1.0
    mapr.inputs["To Max"].default_value = 0.0
    nt.links.new(tex.outputs["Generated"], grad.inputs["Vector"])
    nt.links.new(grad.outputs["Fac"], mapr.inputs["Value"])
    gain = nt.nodes.new("ShaderNodeMath"); gain.operation = "MULTIPLY"
    gain.name = "LeakGain"
    nt.links.new(mapr.outputs["Result"], gain.inputs[0])
    gain.inputs[1].default_value = 0.05
    nt.links.new(gain.outputs["Value"], em.inputs["Strength"])

    # fill from the front-left so the near petals keep a silhouette edge
    lib.area_light("Rim", (-1.2, -1.0, 0.9), (0.0, 0.15, 0.05), energy=26.0, size=1.2,
                   color=(0.66, 0.60, 0.98))
    key = lib.area_light("Key", (0.0, 1.4, 0.55), (0.0, 0.12, 0.0), energy=3.0,
                         size=0.5, color=(1.0, 0.90, 0.75))

    f0, f1 = 279, 433
    cam = lib.camera((0.0, -0.34, 0.055), (0.004, 0.03, 0.005), lens=100.0, fstop=4.5,
                     focus_distance=0.35, name="Cam")
    cam.data.clip_start = 0.01
    lib.anim_camera(cam, [(f0, (0.0, -0.34, 0.055), (0.004, 0.03, 0.005), 0.35),
                          (f1, (0.0, -0.235, 0.050), (0.002, 0.026, 0.004), 0.25)],
                    lens_keys=[(f0, 100.0), (f1, 108.0)])

    # the leak grows: dark violet -> hot white-gold, and the key comes with it
    _anim_area_energy("Rim", [(f0, 12.0), (f1, 26.0)])
    _anim_area_energy("Key", [(f0, 3.0), (int(f0 + (f1 - f0) * 0.55), 8.0), (f1, 140.0)])
    _anim_emission_color(m, [(f0, (0.42, 0.20, 0.55), 0.06),
                             (f0 + 60, (0.62, 0.34, 0.52), 0.9),
                             (int(f0 + (f1 - f0) * 0.72), (1.0, 0.78, 0.52), 7.0),
                             (f1, (1.0, 0.95, 0.86), 34.0)])
    # petals breathe very slightly (slow drift, no perf cost)
    for i, p in enumerate(petals[:7]):
        r0 = p.rotation_euler.copy()
        for f, amp in ((f0, 0.0), (f1, 0.10)):
            p.rotation_euler = (r0.x + amp * 0.4, r0.y + amp, r0.z)
            p.keyframe_insert("rotation_euler", frame=f)
    return sc


def _anim_area_energy(name, keys):
    ob = bpy.data.objects.get(name)
    if not ob:
        return
    lib._set_interp("BEZIER")
    for f, e in keys:
        ob.data.energy = e
        ob.data.keyframe_insert("energy", frame=f)


def _anim_emission_color(mat, keys):
    """keys: [(frame, rgb, strength)] on the Emission node."""
    nt = mat.node_tree
    em = next(n for n in nt.nodes if n.type == "EMISSION")
    lib._set_interp("BEZIER")
    gain = nt.nodes.get("LeakGain")
    for f, rgb, strength in keys:
        em.inputs["Color"].default_value = (*rgb, 1.0)
        em.inputs["Color"].keyframe_insert("default_value", frame=f)
        if gain:
            gain.inputs[1].default_value = strength
            gain.inputs[1].keyframe_insert("default_value", frame=f)


# =========================================================================== S42
def setup_S42():
    lib.reset()
    lib.setup_render(samples=14, resolution=(1920, 1080), exposure=-0.55)
    try:
        lib.scene().eevee.use_raytracing = False
    except Exception:
        pass
    sc = lib.scene()
    black_world((0.010, 0.008, 0.016), 0.05)

    # black water: a dense rippled grid with a near-mirror surface
    n = 90
    size = 6.0
    bm = bmesh.new()
    verts = []
    rng = random.Random(3)
    for j in range(n + 1):
        row = []
        for i in range(n + 1):
            x = (i / n - 0.5) * size
            y = (j / n - 0.5) * size
            z = (0.010 * math.sin(x * 5.1 + y * 1.7) +
                 0.006 * math.sin(y * 7.3 - x * 2.2) +
                 0.004 * math.sin(x * 13.0 + y * 9.0))
            row.append(bm.verts.new((x, y, z)))
        verts.append(row)
    for j in range(n):
        for i in range(n):
            bm.faces.new((verts[j][i], verts[j][i + 1],
                          verts[j + 1][i + 1], verts[j + 1][i]))
    me = bpy.data.meshes.new("Water")
    bm.to_mesh(me)
    bm.free()
    water = bpy.data.objects.new("Water", me)
    sc.collection.objects.link(water)
    for p in me.polygons:
        p.use_smooth = True
    wm = lib.principled("VoidWater", (0.009, 0.007, 0.016), roughness=0.16,
                        specular=0.75)
    me.materials.append(wm)

    # a few dried petals floating on the water
    mat = dried_petal_mat("PetalDried")
    for i in range(5):
        p = petal("FloatPetal%d" % i, length=rng.uniform(0.05, 0.085),
                  width=rng.uniform(0.018, 0.028), bend=rng.uniform(0.05, 0.25),
                  cup=rng.uniform(0.1, 0.3), mat=mat, seed=50 + i)
        p.location = (rng.uniform(-0.30, 0.30), rng.uniform(-0.25, 0.25), 0.012)
        p.rotation_euler = (0.0, 0.0, rng.uniform(0, math.tau))

    # violet key light that fades out
    key = lib.area_light("Violet", (0.30, 0.62, 1.05), (0.0, 0.10, 0.0),
                         energy=26.0, size=2.6, color=(0.62, 0.34, 0.95))
    lib.area_light("Fill", (-0.9, -0.7, 0.6), (0.0, 0.0, 0.0), energy=2.2, size=1.6,
                   color=(0.35, 0.32, 0.62))
    # faint sparkle highlight to catch the ripples
    lib.point_light("Spark", (0.18, 0.32, 0.40), energy=2.6, radius=0.10,
                    color=(0.85, 0.72, 1.0))

    f0, f1 = 4501, 4579
    cam = lib.camera((0.0, -0.72, 0.30), (0.0, 0.05, -0.02), lens=55.0, fstop=1.8,
                     focus_distance=0.82, name="Cam")
    lib.anim_camera(cam, [(f0, (0.0, -0.72, 0.30), (0.0, 0.05, -0.02), 0.82),
                          (f1, (0.0, -0.80, 0.27), (0.0, 0.03, -0.02), 0.88)],
                    lens_keys=[(f0, 55.0), (f1, 78.0)])
    _anim_area_energy("Violet", [(f0, 26.0), (f0 + 34, 9.0), (f1, 0.5)])
    _anim_area_energy("Fill", [(f0, 2.2), (f1, 0.3)])
    _anim_area_energy("Spark", [(f0, 2.6), (f1, 0.2)])
    return sc


# =========================================================================== render
def render_still(name, frame, res=(1280, 720), samples=16):
    sc = lib.scene()
    sc.frame_set(int(frame))
    sc.render.resolution_x, sc.render.resolution_y = res
    os.makedirs(TESTS, exist_ok=True)
    sc.render.filepath = os.path.join(TESTS, name)
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print("[still] %s  %.2fs" % (name, time.time() - t), flush=True)


SETUP = dict(S03=setup_S03, S42=setup_S42)


def look(shot_id):
    SETUP[shot_id]()
    shot = BY_ID[shot_id]
    n = shot["nframes"]
    for i, frac in enumerate((0.05, 0.45, 0.85)):
        fr = int(shot["f0"] + frac * (n - 1))
        render_still("A_%s_look%d" % (shot_id, i), fr)


def render_shot(shot_id, samples=None):
    shot = BY_ID[shot_id]
    t0 = time.time()
    SETUP[shot_id]()
    lib.render(shot, os.path.join(PLATES, shot_id), samples=samples or 14)
    dt = time.time() - t0
    print("[shot] %s %d frames in %.1fs (%.2fs/frame)" %
          (shot_id, shot["nframes"], dt, dt / shot["nframes"]), flush=True)


def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    if not args:
        print("usage: -- look S03 | shot S03 | still S03 300")
        return
    if args[0] == "look":
        look(args[1])
    elif args[0] == "shot":
        render_shot(args[1], samples=int(args[2]) if len(args) > 2 else None)
    elif args[0] == "still":
        SETUP[args[1]]()
        render_still("A_%s_f%04d" % (args[1], int(args[2])), int(args[2]))


if __name__ == "__main__":
    main()
