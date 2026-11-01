# -*- coding: utf-8 -*-
"""
sets_street.py — Team B street sets for "紫色の向日葵".
Blender 5.2.3 LTS / BLENDER_EEVEE.

  S20  rain night street, red umbrella lying on wet asphalt, cold violet
  S21  low puddle shot: umbrella reflection, rain rings, neon bokeh
  S39  desaturated city night from a footbridge, car-light streaks, lone silhouette
  S40b empty street beat (frames 4330-4368)

Street runs along +Y.  Road x -5..5, buildings behind the kerbs at |x| > 5.
Camera heights 0.1-4.5 m.  Wet asphalt reflection is faked with a mirrored
copy of the emissive geometry below the ground + a translucent asphalt layer.

Run:
  blender.exe -b -P blender/sets_street.py -- --lookdev
  blender.exe -b -P blender/sets_street.py -- render 20
"""
import bpy, bmesh, math, random, sys, os, time, json
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import lib
import character as character_mod
from mathutils import Vector, Matrix

ROOT = lib.ROOT
PLATES = os.path.join(ROOT, "plates")
TESTS = os.path.join(PLATES, "_tests")

ROAD_HALF = 5.0
Y0, Y1 = -14.0, 42.0


# ================================================================ helpers
def _link(ob, mats=None):
    bpy.context.scene.collection.objects.link(ob)
    if mats is not None:
        if isinstance(mats, (list, tuple)):
            for m in mats:
                ob.data.materials.append(m)
        else:
            ob.data.materials.append(mats)
    return ob


def bm_to_obj(name, bm, mats=None, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    return _link(ob, mats)


def quad(name, cs, mat, smooth=False):
    return lib.mesh_object(name, cs, [(0, 1, 2, 3)], mat, smooth)


def box(name, center, size, mat, bevel=0.004, segs=2, rot=(0, 0, 0)):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    R = (Matrix.Rotation(rot[2], 4, 'Z') @ Matrix.Rotation(rot[1], 4, 'Y') @
         Matrix.Rotation(rot[0], 4, 'X'))
    bmesh.ops.transform(bm, matrix=R, verts=bm.verts)
    if bevel > 0:
        try:
            bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, offset_type='OFFSET',
                            segments=segs, profile=0.5, affect='EDGES', clamp_overlap=True)
        except Exception:
            pass
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return bm_to_obj(name, bm, mat, smooth=(bevel > 0))


def cyl(name, loc, r, h, mat, rot=(0, 0, 0), segs=20, r2=None, cap=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=segs,
                          radius1=r, radius2=(r if r2 is None else r2), depth=h)
    R = (Matrix.Rotation(rot[2], 4, 'Z') @ Matrix.Rotation(rot[1], 4, 'Y') @
         Matrix.Rotation(rot[0], 4, 'X'))
    bmesh.ops.transform(bm, matrix=R, verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(loc), verts=bm.verts)
    return bm_to_obj(name, bm, mat, smooth=True)


def sphere(name, loc, r, mat, scale=(1, 1, 1), segs=20, rings=12):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=r)
    for v in bm.verts:
        v.co.x *= scale[0]
        v.co.y *= scale[1]
        v.co.z *= scale[2]
    bmesh.ops.translate(bm, vec=Vector(loc), verts=bm.verts)
    return bm_to_obj(name, bm, mat, smooth=True)


# ================================================================ materials
def _nt(m):
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    return nt


def _bsdf(nt, loc=(300, 0)):
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.location = loc
    return b


def _set(b, key, val):
    if key in b.inputs:
        b.inputs[key].default_value = val


def mat_asphalt(name="S_asphalt"):
    m = lib._mat(name)
    nt = _nt(m)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (700, 0)
    b = _bsdf(nt)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-1000, 0)
    n1 = nt.nodes.new("ShaderNodeTexNoise"); n1.location = (-820, 140)
    n1.inputs["Scale"].default_value = 2.2
    n1.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.location = (-600, 140)
    ramp.color_ramp.elements[0].color = (0.028, 0.030, 0.042, 1)
    ramp.color_ramp.elements[1].color = (0.075, 0.077, 0.095, 1)
    nt.links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    # wet: low roughness patches
    n2 = nt.nodes.new("ShaderNodeTexNoise"); n2.location = (-820, -180)
    n2.inputs["Scale"].default_value = 0.7
    n2.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
    rr = nt.nodes.new("ShaderNodeMapRange"); rr.location = (-600, -180)
    rr.inputs["To Min"].default_value = 0.06
    rr.inputs["To Max"].default_value = 0.30
    nt.links.new(n2.outputs["Fac"], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
    _set(b, "Specular IOR Level", 0.62)
    bp = nt.nodes.new("ShaderNodeBump"); bp.location = (-360, -360)
    bp.inputs["Strength"].default_value = 0.10
    bp.inputs["Distance"].default_value = 0.005
    nt.links.new(n2.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_brick(name="S_brick", tone=(0.055, 0.050, 0.062)):
    m = lib._mat(name)
    nt = _nt(m)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
    b = _bsdf(nt)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-900, 0)
    brick = nt.nodes.new("ShaderNodeTexBrick"); brick.location = (-700, 100)
    brick.inputs["Scale"].default_value = 2.0
    brick.inputs["Mortar Size"].default_value = 0.006
    brick.inputs["Brick Width"].default_value = 0.8
    brick.inputs["Row Height"].default_value = 0.25
    brick.inputs["Color1"].default_value = (*[c * 1.6 for c in tone], 1)
    brick.inputs["Color2"].default_value = (*[c * 0.7 for c in tone], 1)
    brick.inputs["Mortar"].default_value = (0.012, 0.012, 0.016, 1)
    nt.links.new(tc.outputs["Object"], brick.inputs["Vector"])
    nt.links.new(brick.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", 0.85)
    bp = nt.nodes.new("ShaderNodeBump"); bp.location = (-380, -240)
    bp.inputs["Strength"].default_value = 0.30
    nt.links.new(brick.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_emit(name, color, strength):
    return lib.emission(name, color, strength)


def make_materials():
    M = {}
    M["asphalt"] = mat_asphalt()
    M["brick"] = mat_brick("S_brick_warm", (0.052, 0.045, 0.055))
    M["brick2"] = mat_brick("S_brick_cool", (0.040, 0.045, 0.062))
    M["concrete"] = lib.principled("S_concrete", (0.075, 0.075, 0.085), roughness=0.8)
    M["dark"] = lib.principled("S_dark_metal", (0.020, 0.020, 0.026), roughness=0.55)
    M["metal"] = lib.principled("S_metal", (0.12, 0.12, 0.14), roughness=0.35, metallic=1.0)
    M["paint_line"] = lib.principled("S_paint", (0.42, 0.42, 0.44), roughness=0.65)
    M["umbrella"] = lib.principled("S_umbrella_red", (0.66, 0.045, 0.055), roughness=0.18,
                                   specular=0.8, sheen=0.2)
    M["umbrella_dark"] = lib.principled("S_umbrella_dark", (0.22, 0.012, 0.020),
                                        roughness=0.3)
    M["rain"] = lib.principled("S_rain", (0.65, 0.72, 0.90), roughness=0.08, alpha=0.30,
                               emission=(0.55, 0.62, 0.90), emission_strength=0.20)
    try:
        M["rain"].surface_render_method = 'DITHERED'
        M["rain"].use_transparent_shadow = True
    except Exception:
        pass
    M["puddle"] = lib.principled("S_puddle", (0.010, 0.012, 0.020), roughness=0.04,
                                 specular=0.9)
    M["skin"] = lib.principled("S_skin", (0.22, 0.14, 0.13), roughness=0.7)
    M["windshield"] = lib.principled("S_windshield", (0.06, 0.07, 0.10), roughness=0.2)
    M["car_red"] = mat_emit("S_car_red", (1.0, 0.06, 0.04), 7.0)
    M["car_white"] = mat_emit("S_car_white", (0.85, 0.90, 1.0), 8.0)
    M["lamp"] = mat_emit("S_street_lamp", (1.0, 0.66, 0.32), 14.0)
    M["neon_pink"] = mat_emit("S_neon_pink", (1.0, 0.20, 0.48), 7.0)
    M["neon_cyan"] = mat_emit("S_neon_cyan", (0.20, 0.80, 1.0), 7.0)
    M["neon_violet"] = mat_emit("S_neon_violet", (0.62, 0.32, 1.0), 8.0)
    M["neon_amber"] = mat_emit("S_neon_amber", (1.0, 0.52, 0.16), 6.0)
    M["win_warm"] = mat_emit("S_win_warm", (1.0, 0.60, 0.28), 1.5)
    M["win_cool"] = mat_emit("S_win_cool", (0.45, 0.66, 1.0), 1.2)
    return M


# ================================================================ set build
def build_ground(M):
    quad("road", [(-ROAD_HALF, Y0, 0), (ROAD_HALF, Y0, 0), (ROAD_HALF, Y1, 0),
                  (-ROAD_HALF, Y1, 0)], M["asphalt"], smooth=True)
    for x in (-ROAD_HALF - 1.4, ROAD_HALF + 1.4):
        quad("sidewalk_%.0f" % x, [(x - 1.4, Y0, 0.12), (x + 1.4, Y0, 0.12),
                                   (x + 1.4, Y1, 0.12), (x - 1.4, Y1, 0.12)],
             M["concrete"], smooth=True)
        box("kerb_%.0f" % x, (x - 1.4 if x > 0 else x + 1.4, (Y0 + Y1) / 2, 0.06),
            (0.12, Y1 - Y0, 0.12), M["concrete"], bevel=0.01)
    # lane dashes
    for i in range(24):
        y = Y0 + 2.0 + i * 2.4
        quad("dash_%02d" % i, [(-0.06, y, 0.002), (0.06, y, 0.002),
                               (0.06, y + 1.2, 0.002), (-0.06, y + 1.2, 0.002)],
             M["paint_line"])
    # puddles: slightly dark low-roughness discs
    rng = random.Random(4)
    for i in range(7):
        x = rng.uniform(-3.6, 3.6)
        y = rng.uniform(Y0 + 3, 26)
        rx = rng.uniform(0.3, 1.1)
        ry = rng.uniform(0.5, 2.0)
        bm = bmesh.new()
        bmesh.ops.create_circle(bm, cap_ends=True, cap_tris=False, segments=26,
                                radius=1.0)
        for v in bm.verts:
            v.co.x *= rx
            v.co.y *= ry
        bmesh.ops.translate(bm, vec=Vector((x, y, 0.004)), verts=bm.verts)
        bm_to_obj("puddle_%d" % i, bm, M["puddle"], smooth=True)


def build_buildings(M):
    rng = random.Random(8)
    objs = []
    for side in (-1, 1):
        x = side * (ROAD_HALF + 1.4)
        y = Y0
        while y < Y1:
            w = rng.uniform(4.0, 9.0)
            h = rng.uniform(7.0, 20.0)
            depth = rng.uniform(5.0, 10.0)
            mat = rng.choice([M["brick"], M["brick2"], M["brick"]])
            ob = box("bld_%d_%.0f" % (side, y), (x + side * depth / 2, y + w / 2, h / 2),
                     (depth, w, h), mat, bevel=0.05)
            objs.append(ob)
            # lit windows on the street-facing face
            bm = bmesh.new()
            em = [M["win_warm"], M["win_cool"]]
            rows = int(h / 1.5)
            cols = max(2, int(w / 1.6))
            for r in range(rows):
                for c in range(cols):
                    if rng.random() < 0.42:
                        continue
                    wx = x - side * 0.02
                    wy = y + 0.5 + c * (w - 1.0) / cols
                    wz = 1.0 + r * 1.5
                    vs = [bm.verts.new((wx, wy - 0.28, wz - 0.35)),
                          bm.verts.new((wx, wy + 0.28, wz - 0.35)),
                          bm.verts.new((wx, wy + 0.28, wz + 0.35)),
                          bm.verts.new((wx, wy - 0.28, wz + 0.35))]
                    f = bm.faces.new(vs)
                    f.material_index = rng.choice([0, 1])
            if bm.faces:
                bm_to_obj("bld_win_%d_%.0f" % (side, y), bm, em, smooth=False)
            y += w + rng.uniform(0.4, 2.0)
    return objs


def build_neon(M):
    """Abstract neon bars / tubes on the facades (no text)."""
    rng = random.Random(11)
    objs = []
    cols = [M["neon_pink"], M["neon_cyan"], M["neon_violet"], M["neon_amber"]]
    for i in range(22):
        side = rng.choice([-1, 1])
        x = side * (ROAD_HALF + 1.2)
        y = rng.uniform(Y0 + 6, 26)
        z = rng.uniform(2.0, 9.0)
        col = rng.choice(cols)
        kind = rng.random()
        if kind < 0.45:      # horizontal bar
            w = rng.uniform(0.8, 2.6)
            ob = box("neon_%02d" % i, (x - side * 0.08, y, z), (0.10, w, rng.uniform(0.10, 0.18)),
                     col, bevel=0.01)
        elif kind < 0.75:    # vertical tube
            h = rng.uniform(1.0, 3.2)
            ob = box("neon_%02d" % i, (x - side * 0.08, y, z), (0.10, rng.uniform(0.08, 0.14), h),
                     col, bevel=0.01)
        else:                # square sign
            w = rng.uniform(0.5, 1.2)
            h = rng.uniform(0.5, 1.2)
            ob = box("neon_%02d" % i, (x - side * 0.08, y, z), (0.10, w, h), col, bevel=0.02)
        objs.append(ob)
        # practical light from the sign
        nl = lib.point_light("neon_l_%02d" % i, (x - side * 0.6, y, z), energy=rng.uniform(18, 46),
                             radius=0.4, color=(0.9, 0.35, 0.6) if col is M["neon_pink"] else
                             (0.4, 0.7, 1.0) if col is M["neon_cyan"] else
                             (0.65, 0.45, 1.0) if col is M["neon_violet"] else (1.0, 0.6, 0.3))
        try:
            nl.data.use_shadow = False
        except Exception:
            pass
    return objs


def build_street_lamps(M):
    for i, (x, y) in enumerate(((-4.55, 1.2), (4.55, 6.0),
                                (-4.55, 14.0), (4.55, 22.0))):
        cyl("lamp_pole_%d" % i, (x, y, 2.6), 0.07, 5.2, M["dark"], segs=10)
        cyl("lamp_arm_%d" % i, (x + (0.55 if x > 0 else -0.55), y, 5.15), 0.045, 1.1,
            M["dark"], rot=(0, math.pi / 2, 0), segs=10)
        hx = x + (1.15 if x > 0 else -1.15)
        sphere("lamp_head_%d" % i, (hx, y, 5.05), 0.14, M["lamp"], segs=14, rings=10)
        lp = lib.point_light("lamp_light_%d" % i, (hx, y, 4.95), energy=220, radius=0.5,
                             color=(1.0, 0.64, 0.30))
        try:
            lp.data.use_shadow = (i < 2)
        except Exception:
            pass


def build_rain(M, n_layers=7, per_layer=42, area=(-6, 6, -12, 30, 0.2, 7.0), speed=0.9):
    """Curtains of rain streaks; each layer loops downward."""
    rng = random.Random(21)
    x0, x1, y0, y1, z0, z1 = area
    layers = []
    for L in range(n_layers):
        bm = bmesh.new()
        for i in range(per_layer):
            x = rng.uniform(x0, x1)
            y = rng.uniform(y0, y1)
            z = rng.uniform(z0, z1)
            ln = rng.uniform(0.35, 0.95)
            w = rng.uniform(0.004, 0.010)
            tilt = rng.uniform(0.02, 0.10)
            vs = [bm.verts.new((x - w, y, z)), bm.verts.new((x + w, y, z)),
                  bm.verts.new((x + w + tilt, y, z + ln)),
                  bm.verts.new((x - w + tilt, y, z + ln))]
            bm.faces.new(vs)
        ob = bm_to_obj("rain_layer_%d" % L, bm, M["rain"], smooth=False)
        ob.visible_shadow = False
        layers.append(ob)
    return layers


def animate_rain(layers, f0, f1, span=3.2):
    nkey = 4
    for i, ob in enumerate(layers):
        z0 = ob.location.z
        for k in range(nkey + 1):
            f = f0 + int((f1 - f0) * k / nkey)
            t = (k / nkey) * span
            ob.location = (0, 0, z0 - t)
            ob.keyframe_insert("location", frame=f)


def build_umbrella(M, loc=(0.55, 2.6, 0.02), rot=(0.0, 0.0, 0.35), seed=3, rad=0.78):
    """Red umbrella lying open on the wet street: shallow scalloped bowl facing up."""
    rng = random.Random(seed)
    x, y, z = loc
    bm = bmesh.new()
    nseg = 16
    ring = []
    for i in range(nseg):
        a = 2 * math.pi * i / nseg
        rr = rad * rng.uniform(0.96, 1.04)
        dz = 0.020 if i % 2 == 0 else 0.055     # scalloped rim
        ring.append(bm.verts.new((x + math.cos(a) * rr, y + math.sin(a) * rr, z + dz)))
    c = bm.verts.new((x, y, z + 0.012))
    for i in range(nseg):
        f = bm.faces.new((c, ring[(i + 1) % nseg], ring[i]))
        f.smooth = True
    # ribs along the underside
    for i in range(8):
        a = 2 * math.pi * i / 8
        p0 = Vector((x, y, z + 0.012))
        p1 = Vector((x + math.cos(a) * rad * 0.98, y + math.sin(a) * rad * 0.98, z + 0.038))
        pts = [p0, (p0 + p1) * 0.5 + Vector((0, 0, 0.035)), p1]
        rings = []
        for j, pp in enumerate(pts):
            t = (pts[min(j + 1, 2)] - pts[max(j - 1, 0)]).normalized()
            nr = Vector((0, 0, 1)) - t * Vector((0, 0, 1)).dot(t)
            if nr.length < 1e-4:
                nr = Vector((1, 0, 0))
            nr.normalize()
            b = t.cross(nr)
            rings.append([bm.verts.new(pp + nr * math.cos(2 * math.pi * k / 6) * 0.007 +
                                       b * math.sin(2 * math.pi * k / 6) * 0.007)
                          for k in range(6)])
        for j in range(len(rings) - 1):
            for k in range(6):
                k2 = (k + 1) % 6
                try:
                    bm.faces.new((rings[j][k], rings[j][k2], rings[j + 1][k2], rings[j + 1][k]))
                except ValueError:
                    pass
    # shaft sticking out sideways on the ground
    shaft = cyl("umb_shaft", (x, y, z + 0.09), 0.014, 0.55, M["metal"], segs=8)
    ob = bm_to_obj("umbrella_%d" % seed, bm, M["umbrella"], smooth=True)
    ob.rotation_euler = rot
    ob.location = (0, 0, 0)
    return ob


def build_footbridge(M):
    """Concrete footbridge crossing the street (for S39)."""
    z = 4.35
    box("bridge_deck", (0.0, 6.0, z), (11.0, 3.2, 0.22), M["concrete"], bevel=0.02)
    box("bridge_beam", (0.0, 6.0, z - 0.30), (10.6, 2.2, 0.36), M["concrete"], bevel=0.02)
    for x in (-5.4, 5.4):
        box("bridge_pier_%.0f" % x, (x, 6.0, z / 2), (0.9, 1.6, z), M["concrete"], bevel=0.03)
    # railings
    for side, dy in ((-1, -1.55), (1, 1.55)):
        box("rail_top_%d" % side, (0.0, 6.0 + dy, z + 1.02), (11.0, 0.06, 0.07), M["metal"], bevel=0.01)
        box("rail_mid_%d" % side, (0.0, 6.0 + dy, z + 0.55), (11.0, 0.05, 0.05), M["metal"], bevel=0.01)
        for i in range(14):
            xx = -5.2 + i * 0.8
            box("rail_post_%d_%d" % (side, i), (xx, 6.0 + dy, z + 0.52), (0.045, 0.045, 1.02),
                M["metal"], bevel=0.008)
    # deck lights
    for i in range(5):
        xx = -4.0 + i * 2.0
        box("bridge_light_%d" % i, (xx, 6.0 - 1.5, z + 1.15), (0.30, 0.06, 0.04), M["car_white"],
            bevel=0.005)
        bp = lib.point_light("bridge_pl_%d" % i, (xx, 6.0 - 1.2, z + 1.1), energy=26, radius=0.3,
                             color=(1.0, 0.88, 0.75))
        try:
            bp.data.use_shadow = False
        except Exception:
            pass


def build_car_streaks(M, count=7, seed=5):
    """Car light trails: long emissive bars just above the road, animated sideways."""
    rng = random.Random(seed)
    bars = []
    for i in range(count):
        lane = rng.choice([-2.6, -1.2, 1.2, 2.6])
        y = rng.uniform(-6, 24)
        z = rng.uniform(0.35, 1.15)
        ln = rng.uniform(3.0, 7.0)
        red = lane < 0
        mat = M["car_red"] if red else M["car_white"]
        bm = bmesh.new()
        w = 0.055
        vs = [bm.verts.new((lane - w, y - ln / 2, z)), bm.verts.new((lane + w, y - ln / 2, z)),
              bm.verts.new((lane + w, y + ln / 2, z)), bm.verts.new((lane - w, y + ln / 2, z))]
        bm.faces.new(vs)
        ob = bm_to_obj("car_streak_%d" % i, bm, mat, smooth=False)
        ob.visible_shadow = False
        bars.append((ob, y, rng.uniform(6.0, 14.0)))
    return bars


def animate_streaks(bars, f0, f1):
    for i, (ob, y, speed) in enumerate(bars):
        d = 2 if i % 2 else -2   # some pass each way
        for k in range(3):
            f = f0 + int((f1 - f0) * k / 2)
            t = (f - f0) / 24.0
            ob.location.y = y + d * speed * t
            ob.keyframe_insert("location", frame=f)


def build_sky():
    lib.sky_dome(c_horizon=(0.030, 0.022, 0.048), c_mid=(0.010, 0.011, 0.026),
                 c_zenith=(0.003, 0.0035, 0.009), sun_dir=(0.4, 0.7, 0.5),
                 sun_color=(0.8, 0.85, 1.0), sun_power=0.0, glow=0.0, strength=1.0,
                 cloud=((0.055, 0.045, 0.085), 0.35, 2.0, 0.30))


def build_reflection(M):
    """Mirrored copy of the emissive set below the road + translucent road layer.

    Implemented as: duplicate the road as a semi-transparent dark layer, and
    duplicate the neon/lamp/sign meshes with z mirrored.  Cheap and stable in EEVEE.
    """
    glow = [o for o in bpy.data.objects
            if o.type == "MESH" and o.name.startswith(("neon_", "lamp_head_", "bld_win_",
                                                       "car_streak_", "bridge_light_"))]
    for o in glow:
        c = o.copy()
        c.data = o.data  # linked duplicate
        bpy.context.scene.collection.objects.link(c)
        c.name = "refl_" + o.name
        c.location = (o.location.x, o.location.y, -o.location.z)
        c.scale = (o.scale.x, o.scale.y, -o.scale.z)
        try:
            c.visible_shadow = False
        except Exception:
            pass


def build_wet_reflections(M):
    """Soft coloured light smears on the road: cheap stand-in for neon reflections."""
    rng = random.Random(41)
    cols = [M["neon_pink"], M["neon_cyan"], M["neon_violet"], M["neon_amber"], M["win_warm"]]
    for i in range(16):
        side = rng.choice([-1, 1])
        x = side * rng.uniform(0.6, 4.4)
        y = rng.uniform(-4.0, 30.0)
        ln = rng.uniform(1.2, 5.5)
        w = rng.uniform(0.05, 0.22)
        col = rng.choice(cols)
        bm = bmesh.new()
        vs = [bm.verts.new((x - w / 2, y - ln / 2, 0.006)),
              bm.verts.new((x + w / 2, y - ln / 2, 0.006)),
              bm.verts.new((x + w / 2, y + ln / 2, 0.006)),
              bm.verts.new((x - w / 2, y + ln / 2, 0.006))]
        bm.faces.new(vs)
        ob = bm_to_obj("wet_refl_%d" % i, bm, col, smooth=False)
        ob.visible_shadow = False


def build_people(M):
    """Lone silhouette on the footbridge (S39)."""
    girl = character_mod.figure("StreetGirl", variant="girl", pose="stand", height=1.58,
                                facing=math.pi * 0.15)
    girl.location = (1.15, 7.55, 4.46)
    girl.rotation_euler = (0, 0, math.pi * 0.92)
    return girl


# ================================================================ lighting
def lights_street(intensity=1.0):
    # cold city ambience
    lib.fog(density=0.0, color=(0.30, 0.30, 0.52), anisotropy=0.35,
            ambient=(0.050, 0.052, 0.095), ambient_strength=1.0)
    # fill from above so the wet road and rain keep some shape
    lib.area_light("sky_fill", (0.0, 8.0, 16.0), target=(0.0, 6.0, 0.0),
                   energy=2200.0 * intensity, size=26.0, color=(0.38, 0.42, 0.80))
    # low hazard / sodium glow from down the street
    lib.area_light("street_glow", (0.0, 34.0, 3.0), target=(0.0, 4.0, 1.0),
                   energy=700.0 * intensity, size=10.0, color=(1.0, 0.55, 0.35))


def lights_bridge(intensity=1.0):
    lib.fog(density=0.0, color=(0.28, 0.30, 0.50), anisotropy=0.35,
            ambient=(0.024, 0.028, 0.058), ambient_strength=0.80)
    lib.area_light("sky_fill", (0.0, 10.0, 18.0), target=(0.0, 6.0, 0.0),
                   energy=700.0 * intensity, size=30.0, color=(0.30, 0.34, 0.66))
    lib.area_light("city_glow", (0.0, 40.0, 6.0), target=(0.0, 6.0, 2.0),
                   energy=500.0 * intensity, size=22.0, color=(0.55, 0.40, 0.85))


# ================================================================ cameras
def make_cam(loc, target, lens=35.0, fstop=2.0, focus=None, name="Cam"):
    return lib.camera(loc, target, lens=lens, fstop=fstop,
                      focus_distance=(focus if focus is not None else
                                      (Vector(target) - Vector(loc)).length),
                      name=name)


def render_still(name, res=(1280, 720), samples=16, subdir="_tests"):
    sc = lib.scene()
    sc.render.resolution_x, sc.render.resolution_y = res
    try:
        sc.eevee.taa_render_samples = samples
    except Exception:
        pass
    outdir = os.path.join(PLATES, subdir)
    os.makedirs(outdir, exist_ok=True)
    sc.render.filepath = os.path.join(outdir, name + ".png")
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print("[street] %-24s %.2fs" % (name, time.time() - t))


def load_shots():
    with open(os.path.join(ROOT, "story", "shots.json"), encoding="utf-8") as f:
        return {x["id"]: x for x in json.load(f)["shots"]}


# ================================================================ scenes
def build_street_scene(S, with_bridge=False):
    lib.reset()
    lib.setup_render(samples=20, resolution=(1920, 1080))
    M = make_materials()
    build_sky()
    build_ground(M)
    build_buildings(M)
    build_neon(M)
    build_street_lamps(M)
    rain = build_rain(M)
    build_umbrella(M, loc=(0.42, 2.10, 0.02), rot=(0.0, 0.0, 0.35), seed=3, rad=0.86)
    build_umbrella(M, loc=(-2.4, 9.0, 0.02), rot=(0.0, 0.0, 1.1), seed=6, rad=0.70)
    if with_bridge:
        build_footbridge(M)
        people = build_people(M)
        bars = build_car_streaks(M)
    else:
        people = None
        bars = None
    build_reflection(M)
    build_wet_reflections(M)
    lib.scene().eevee.use_raytracing = False
    cams = {}

    # ---- S20: rain hitting the lens; wet asphalt, red umbrella, cold violet
    sh = S["S20"]; f0, f1 = sh["f0"], sh["f1"]
    lights_street()
    cam = make_cam((-0.55, -1.35, 0.62), (0.75, 5.2, 1.05), lens=32, fstop=2.2, focus=2.4)
    lib.anim_camera(cam, [
        (f0, (-0.55, -1.35, 0.62), (0.75, 5.2, 1.05), 2.4),
        (f1, (-0.48, -1.18, 0.60), (0.78, 5.2, 1.02), 2.3),
    ])
    cams["S20"] = cam
    # lens droplets in the very foreground
    bm = bmesh.new()
    rng = random.Random(31)
    for i in range(9):
        rr = rng.uniform(0.004, 0.016)
        cx = rng.uniform(-0.07, 0.07)
        cz = rng.uniform(-0.04, 0.05)
        mat4 = Matrix.Translation((cx, -3.2 - 0.28, 0.52 + cz)) @ Matrix.Diagonal((1.0, 0.4, 1.2, 1.0))
        bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=7, radius=rr, matrix=mat4)
    lensd = bm_to_obj("lens_drops", bm, M["rain"], smooth=True)
    lensd.parent = cam
    lensd.matrix_parent_inverse = cam.matrix_world.inverted()

    # ---- S21: low puddle shot, umbrella reflection, neon bokeh
    sh = S["S21"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((1.12, 0.05, 0.115), (0.05, 2.55, 0.16), lens=34, fstop=2.2, focus=2.35)
    lib.anim_camera(cam, [
        (f0, (1.12, 0.05, 0.115), (0.05, 2.55, 0.16), 2.35),
        (f1, (1.02, 0.16, 0.105), (0.05, 2.55, 0.155), 2.20),
    ])
    cams["S21"] = cam

    # ---- S40 beat 2: empty street (4330-4368)
    cam = make_cam((0.0, -2.0, 1.05), (0.2, 14.0, 0.9), lens=32, fstop=2.8, focus=8.0)
    lib.anim_camera(cam, [
        (4330, (0.0, -2.0, 1.05), (0.2, 14.0, 0.9), 8.0),
        (4368, (0.06, -1.8, 1.04), (0.2, 14.0, 0.9), 7.4),
    ])
    cams["S40b"] = cam

    if with_bridge:
        # ---- S39: desaturated city night from the bridge
        sh = S["S39"]; f0, f1 = sh["f0"], sh["f1"]
        cam = make_cam((-2.2, 4.0, 6.05), (0.6, 13.5, 2.4), lens=35, fstop=2.0, focus=6.0)
        lib.anim_camera(cam, [
            (f0, (-2.2, 4.0, 6.05), (0.6, 13.5, 2.4), 6.0),
            (f1, (-2.0, 4.2, 6.00), (0.65, 13.5, 2.35), 5.6),
        ])
        cams["S39"] = cam
    return cams, rain, bars


# ================================================================ lookdev
def lookdev():
    S = load_shots()
    # clean street scene, then the bridge scene
    cams, rain, bars = build_street_scene(S, with_bridge=False)
    sc = lib.scene()
    sc.camera = cams["S20"]
    render_still("B_street_20a")
    sc.camera = cams["S21"]
    render_still("B_street_21a")

    cams, rain, bars = build_street_scene(S, with_bridge=True)
    sc = lib.scene()
    sc.camera = cams["S39"]
    render_still("B_street_39a")
    sc.camera = cams["S40b"]
    render_still("B_street_40b")


# ================================================================ render
def render_single(build_fn, sid, samples=20):
    S = load_shots()
    cams = build_fn(S)
    sh = S[sid]
    sc = lib.scene()
    sc.camera = cams[sid]
    outdir = os.path.join(PLATES, sh["id"])
    t = time.time()
    lib.render(sh, outdir, samples=samples)
    print("[render] %s %d frames in %.1fs" % (sid, sh["f1"] - sh["f0"] + 1, time.time() - t))


def render_street(samples=20):
    S = load_shots()
    cams, rain, bars = build_street_scene(S, with_bridge=False)
    sc = lib.scene()
    # animate rain over the whole street use
    animate_rain(rain, 2101, 4368, span=3.2)
    for sid in ("S20", "S21"):
        sh = S[sid]
        sc.camera = cams[sid]
        t = time.time()
        lib.render(sh, os.path.join(PLATES, sid), samples=samples)
        print("[render] %s %d frames in %.1fs" % (sid, sh["f1"] - sh["f0"] + 1, time.time() - t))
    # S40 beat 2: empty street
    fake = {"id": "S40", "f0": 4330, "f1": 4368}
    sc.camera = cams["S40b"]
    t = time.time()
    lib.render(fake, os.path.join(PLATES, "S40"), samples=samples)
    print("[render] S40b 39 frames in %.1fs" % (time.time() - t, ))


def render_bridge(samples=20):
    S = load_shots()
    cams, rain, bars = build_street_scene(S, with_bridge=True)
    sc = lib.scene()
    animate_rain(rain, 4183, 4291, span=3.2)
    if bars:
        animate_streaks(bars, 4183, 4291)
    sh = S["S39"]
    sc.camera = cams["S39"]
    t = time.time()
    lib.render(sh, os.path.join(PLATES, "S39"), samples=samples)
    print("[render] S39 %d frames in %.1fs" % (sh["f1"] - sh["f0"] + 1, time.time() - t))


def render_s40b(samples=12):
    """Only the empty-street beat of S40 (frames 4330-4368)."""
    S = load_shots()
    cams, rain, bars = build_street_scene(S, with_bridge=False)
    sc = lib.scene()
    animate_rain(rain, 2101, 4368, span=3.2)
    sc.camera = cams["S40b"]
    fake = {"id": "S40", "f0": 4330, "f1": 4368}
    lib.render(fake, os.path.join(PLATES, "S40"), samples=samples)
    print("[render] S40b 39 frames done")


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    what = argv[0] if argv else "all"
    if what == "lookdev":
        lookdev()
    elif what == "render_street":
        render_street(samples=int(argv[1]) if len(argv) > 1 else 20)
    elif what == "render_bridge":
        render_bridge(samples=int(argv[1]) if len(argv) > 1 else 20)
    elif what == "render_s40b":
        render_s40b(samples=int(argv[1]) if len(argv) > 1 else 12)


if __name__ == "__main__":
    main()
