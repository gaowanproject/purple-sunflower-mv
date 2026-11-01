# -*- coding: utf-8 -*-
"""
sets_road.py — Team A (scenery-nature), the road world.

One procedural road, four light worlds (shared geometry, different exposure/colour):
    noon_hot        S04 S05 S06 S08   white-hot noon, heat haze, cold water on asphalt
    noon_side       S07 S09 S10       same road, side-backlight: long shadows, silhouettes
    dusk_afterglow  S22 S50           200mm dusk, sun on the horizon, afterglow
    violet_dusk     S32               storm-violet road, wind, low clouds

Blender 5.2 headless.  Imports lib + character only (never copies them).

usage:
    blender -b -P blender/sets_road.py -- look noon_hot
    blender -b -P blender/sets_road.py -- still S04 470
    blender -b -P blender/sets_road.py -- shot S04

For other teams:  build_road(variant) -> dict of scene objects (camera-free).
"""
import bpy, bmesh, math, random, os, sys, json, time
from mathutils import Vector, Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.append(HERE)
import lib
import character

ROOT = lib.ROOT
PLATES = os.path.join(ROOT, "plates")
TESTS = os.path.join(PLATES, "_tests")
SHOTS = json.load(open(os.path.join(ROOT, "story", "shots.json"), encoding="utf-8"))["shots"]
BY_ID = {s["id"]: s for s in SHOTS}
D2R = math.pi / 180.0

# =========================================================================== materials
def mat_noise(name, c_a, c_b, scale=6.0, detail=6.0, rough=0.72, spec=0.4,
              bump=0.0, bump_scale=60.0, metallic=0.0, coord="Object",
              emis=None, emis_strength=0.0, alpha=1.0):
    """Procedural noise-blend Principled material. coord: Object|Generated|UV."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial"); out.location = (760, 0)
    bsdf = N.new("ShaderNodeBsdfPrincipled"); bsdf.location = (420, 0)
    L.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    tc = N.new("ShaderNodeTexCoord"); tc.location = (-1000, 0)
    n1 = N.new("ShaderNodeTexNoise"); n1.location = (-780, 180)
    n1.inputs["Scale"].default_value = scale
    n1.inputs["Detail"].default_value = detail
    L.new(tc.outputs[coord], n1.inputs["Vector"])
    ramp = N.new("ShaderNodeValToRGB"); ramp.location = (-540, 180)
    ramp.color_ramp.elements[0].color = (*c_a, 1.0)
    ramp.color_ramp.elements[1].color = (*c_b, 1.0)
    L.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    L.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = spec
    if bump > 0.0:
        n2 = N.new("ShaderNodeTexNoise"); n2.location = (-780, -260)
        n2.inputs["Scale"].default_value = bump_scale
        n2.inputs["Detail"].default_value = 8.0
        L.new(tc.outputs[coord], n2.inputs["Vector"])
        bmp = N.new("ShaderNodeBump"); bmp.location = (140, -240)
        bmp.inputs["Strength"].default_value = bump
        bmp.inputs["Distance"].default_value = 0.012
        L.new(n2.outputs["Fac"], bmp.inputs["Height"])
        L.new(bmp.outputs["Normal"], bsdf.inputs["Normal"])
    if emis is not None and "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = (*emis, 1.0)
        bsdf.inputs["Emission Strength"].default_value = emis_strength
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        try:
            m.surface_render_method = "DITHERED"
        except Exception:
            pass
    return m


def mat_plain(name, color, rough=0.6, spec=0.4, metallic=0.0):
    return lib.principled(name, color, roughness=rough, metallic=metallic, specular=spec)


def mat_water(name="Water", color=(0.72, 0.82, 0.92), rough=0.03, alpha=1.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial"); out.location = (500, 0)
    bsdf = N.new("ShaderNodeBsdfPrincipled"); bsdf.location = (200, 0)
    L.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    if "IOR" in bsdf.inputs:
        bsdf.inputs["IOR"].default_value = 1.333
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 1.0
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        try:
            m.surface_render_method = "DITHERED"
        except Exception:
            pass
    return m


# =========================================================================== bmesh helpers
def bm_obj(name, bm, mats=None, smooth=True):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    lib.scene().collection.objects.link(ob)
    for mm in (mats or []):
        me.materials.append(mm)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return ob


def mat4(loc=(0, 0, 0), rotz=0.0, scale=(1, 1, 1)):
    return (Matrix.Translation(Vector(loc)) @ Matrix.Rotation(rotz, 4, "Z") @
            Matrix.Diagonal((scale[0], scale[1], scale[2], 1.0)))


def _tag(bm, n0, mi=0, smooth=True):
    for f in bm.faces[n0:]:
        f.material_index = mi
        f.smooth = smooth


def add_cyl(bm, r1, r2, depth, matrix, segs=8, mi=0, caps=True, smooth=True):
    n0 = len(bm.faces)
    bmesh.ops.create_cone(bm, cap_ends=caps, cap_tris=False, segments=segs,
                          radius1=r1, radius2=r2, depth=depth, matrix=matrix)
    _tag(bm, n0, mi, smooth)
    return n0


def add_box(bm, size, matrix, mi=0, smooth=False):
    n0 = len(bm.faces)
    bmesh.ops.create_cube(bm, size=1.0,
                          matrix=matrix @ Matrix.Diagonal((size[0], size[1], size[2], 1.0)))
    _tag(bm, n0, mi, smooth)
    return n0


def add_sphere(bm, r, matrix, u=12, v=8, mi=0, smooth=True):
    n0 = len(bm.faces)
    bmesh.ops.create_uvsphere(bm, u_segments=u, v_segments=v, radius=r, matrix=matrix)
    _tag(bm, n0, mi, smooth)
    return n0


# =========================================================================== sky
def sky_road(name, radius=900.0, c0=(1.0, 0.88, 0.66), c1=(0.84, 0.80, 0.79),
             c2=(0.34, 0.56, 0.96), c3=(0.055, 0.13, 0.40), strength=1.35,
             sun_dir=(0.06, 0.80, 0.34), sun_color=(1.0, 0.90, 0.74),
             halo_pow=6.0, halo_amt=1.9, disc_pow=4000.0, disc_power=350.0,
             glow_only=False):
    """Own sky dome: gradient keyed on world Position (not Incoming, whose sign
    flips the ramp), plus one wide golden halo and a small hot disc.
    Deliberately under-exposed sky body so AgX keeps the colour gradient."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=radius)
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    lib.scene().collection.objects.link(obj)
    obj.visible_shadow = False
    obj.visible_diffuse = False
    obj.visible_glossy = False

    m = bpy.data.materials.new(name + "_mat")
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial"); out.location = (1200, 0)
    geo = N.new("ShaderNodeNewGeometry"); geo.location = (-1700, 0)
    # unit direction from the dome centre: world Position / radius (Generated is
    # not a full 0..1 bbox sweep on a bmesh sphere, so do not use it here)
    nrm = N.new("ShaderNodeVectorMath"); nrm.location = (-1500, -60)
    nrm.operation = "SCALE"
    nrm.inputs["Scale"].default_value = 1.0 / radius
    L.new(geo.outputs["Position"], nrm.inputs[0])
    sep = N.new("ShaderNodeSeparateXYZ"); sep.location = (-1320, 120)
    L.new(nrm.outputs["Vector"], sep.inputs[0])
    mr = N.new("ShaderNodeMapRange"); mr.location = (-1320, -60)
    mr.inputs["From Min"].default_value = -0.05
    mr.inputs["From Max"].default_value = 0.85
    mr.clamp = True
    L.new(sep.outputs["Z"], mr.inputs["Value"])
    ramp = N.new("ShaderNodeValToRGB"); ramp.location = (-1080, -60)
    cr = ramp.color_ramp
    cr.interpolation = "EASE"
    cr.elements[0].position = 0.0; cr.elements[0].color = (*c0, 1.0)
    cr.elements[1].position = 1.0; cr.elements[1].color = (*c3, 1.0)
    e = cr.elements.new(0.17); e.color = (*c1, 1.0)
    e = cr.elements.new(0.46); e.color = (*c2, 1.0)
    L.new(mr.outputs["Result"], ramp.inputs["Fac"])
    mul = N.new("ShaderNodeMixRGB"); mul.location = (-840, 120)
    mul.blend_type = "MULTIPLY"; mul.inputs["Fac"].default_value = 1.0
    L.new(ramp.outputs["Color"], mul.inputs["Color1"])
    mul.inputs["Color2"].default_value = (strength, strength, strength, 1.0)

    # sun: wide halo + tight disc
    sd = N.new("ShaderNodeCombineXYZ"); sd.location = (-1300, -420)
    v = Vector(sun_dir).normalized()
    sd.inputs[0].default_value = v.x
    sd.inputs[1].default_value = v.y
    sd.inputs[2].default_value = v.z
    dot = N.new("ShaderNodeVectorMath"); dot.location = (-1120, -420)
    dot.operation = "DOT_PRODUCT"
    L.new(nrm.outputs["Vector"], dot.inputs[0])
    L.new(sd.outputs["Vector"], dot.inputs[1])
    cl = N.new("ShaderNodeMath"); cl.location = (-960, -420)
    cl.operation = "MAXIMUM"; cl.inputs[1].default_value = 0.0
    L.new(dot.outputs["Value"], cl.inputs[0])
    hp = N.new("ShaderNodeMath"); hp.location = (-800, -360)
    hp.operation = "POWER"; hp.inputs[1].default_value = halo_pow
    L.new(cl.outputs["Value"], hp.inputs[0])
    hm = N.new("ShaderNodeMath"); hm.location = (-640, -360)
    hm.operation = "MULTIPLY"; hm.inputs[1].default_value = halo_amt
    L.new(hp.outputs["Value"], hm.inputs[0])
    dp = N.new("ShaderNodeMath"); dp.location = (-800, -540)
    dp.operation = "POWER"; dp.inputs[1].default_value = disc_pow
    L.new(cl.outputs["Value"], dp.inputs[0])
    dm = N.new("ShaderNodeMath"); dm.location = (-640, -540)
    dm.operation = "MULTIPLY"; dm.inputs[1].default_value = disc_power
    L.new(dp.outputs["Value"], dm.inputs[0])
    ad = N.new("ShaderNodeMath"); ad.location = (-480, -440)
    ad.operation = "ADD"
    if glow_only:
        L.new(hm.outputs["Value"], ad.inputs[0])
    else:
        L.new(hm.outputs["Value"], ad.inputs[0])
        L.new(dm.outputs["Value"], ad.inputs[1])
    gray = N.new("ShaderNodeCombineXYZ"); gray.location = (-320, -440)
    L.new(ad.outputs["Value"], gray.inputs[0])
    L.new(ad.outputs["Value"], gray.inputs[1])
    L.new(ad.outputs["Value"], gray.inputs[2])
    scol = N.new("ShaderNodeMixRGB"); scol.location = (-140, -440)
    scol.blend_type = "MULTIPLY"; scol.inputs["Fac"].default_value = 1.0
    scol.inputs["Color1"].default_value = (*sun_color, 1.0)
    L.new(gray.outputs["Vector"], scol.inputs["Color2"])
    addc = N.new("ShaderNodeMixRGB"); addc.location = (300, 0)
    addc.blend_type = "ADD"; addc.inputs["Fac"].default_value = 1.0
    L.new(mul.outputs["Color"], addc.inputs["Color1"])
    L.new(scol.outputs["Color"], addc.inputs["Color2"])
    em = N.new("ShaderNodeEmission"); em.location = (600, 0)
    em.inputs["Strength"].default_value = 1.0
    L.new(addc.outputs["Color"], em.inputs["Color"])
    L.new(em.outputs["Emission"], out.inputs["Surface"])
    obj.data.materials.append(m)
    return obj


# =========================================================================== road geometry
def ground_plane(name, size, z, preset):
    verts = [(-size, -size, z), (size, -size, z), (size, size, z), (-size, size, z)]
    c_a, c_b = preset["ground"]
    m = mat_noise(name + "_mat", c_a, c_b, scale=0.22, detail=8.0, rough=0.92,
                  bump=0.25, bump_scale=3.5, coord="Object")
    return lib.mesh_object(name, verts, [(0, 1, 2, 3)], mat=m)


def road_ribbon(name, width, y0, y1, z, preset):
    verts = [(-width / 2, y0, z), (width / 2, y0, z), (width / 2, y1, z), (-width / 2, y1, z)]
    c_a, c_b = preset["road"]
    m = mat_noise(name + "_mat", c_a, c_b, scale=1.6, detail=8.0, rough=0.62,
                  bump=0.30, bump_scale=5.0, coord="Object")
    return lib.mesh_object(name, verts, [(0, 1, 2, 3)], mat=m)


def road_markings(name, width, y0, y1, z, paint=(0.80, 0.78, 0.72)):
    bm = bmesh.new()
    hw = width / 2.0 - 0.30
    for sx in (-1, 1):
        add_box(bm, (0.14, y1 - y0, 0.008), mat4((sx * hw, (y0 + y1) / 2.0, z + 0.006)))
    step, dash = 8.0, 4.0
    y = y0
    while y < y1:
        add_box(bm, (0.14, dash, 0.008), mat4((0.0, y + dash / 2.0, z + 0.006)))
        y += step
    m = mat_plain(name + "_mat", paint, rough=0.55, spec=0.35)
    return bm_obj(name, bm, [m], smooth=False)


def shoulder_pair(name, width, y0, y1, z, preset):
    bm = bmesh.new()
    for sx in (-1, 1):
        x0, x1 = sx * (width / 2.0), sx * (width / 2.0 + 1.6)
        vs = [bm.verts.new(p) for p in
              ((min(x0, x1), y0, z + 0.002), (max(x0, x1), y0, z + 0.002),
               (max(x0, x1), y1, z + 0.002), (min(x0, x1), y1, z + 0.002))]
        bm.faces.new(vs)
    m = mat_noise(name + "_mat", (0.38, 0.35, 0.29), (0.19, 0.17, 0.13),
                  scale=8.0, detail=8.0, rough=0.9, bump=0.5, bump_scale=140.0)
    return bm_obj(name, bm, [m], smooth=False)


def curb_pair(name, width, y0, y1, z):
    bm = bmesh.new()
    for sx in (-1, 1):
        add_box(bm, (0.24, y1 - y0, 0.17), mat4((sx * (width / 2.0 + 0.16),
                                                 (y0 + y1) / 2.0, z + 0.045)))
    m = mat_noise(name + "_mat", (0.44, 0.43, 0.40), (0.27, 0.26, 0.24),
                  scale=2.2, rough=0.8, bump=0.3, bump_scale=22.0)
    return bm_obj(name, bm, [m], smooth=False)


def power_line(name, x, ys, h=11.2, sag=0.95, pole_color=(0.44, 0.43, 0.41)):
    bm = bmesh.new()
    for i, y in enumerate(ys):
        add_cyl(bm, 0.19, 0.115, h, mat4((x, y, h / 2.0)), segs=10, mi=0)
        for dz, armw in ((0.35, 1.55), (1.30, 1.30)):
            zc = h - dz
            add_box(bm, (armw, 0.09, 0.09), mat4((x, y, zc)), mi=0)
            for sx in (-1, 0, 1):
                add_cyl(bm, 0.055, 0.045, 0.17,
                        mat4((x + sx * armw * 0.38, y, zc + 0.13)), segs=6, mi=1)
        if i % 2 == 1:
            add_cyl(bm, 0.30, 0.30, 0.82, mat4((x + 0.42, y, h - 2.35)), segs=10, mi=2)
        add_cyl(bm, 0.115, 0.075, 0.35, mat4((x, y, h + 0.14)), segs=8, mi=0)
    pole_mat = mat_noise(name + "_mat", pole_color, tuple(c * 0.62 for c in pole_color),
                         scale=3.0, detail=6.0, rough=0.85, bump=0.25, bump_scale=40.0)
    poles = bm_obj(name + "_poles", bm,
                   [pole_mat,
                    mat_plain(name + "_ins", (0.55, 0.55, 0.52), rough=0.4),
                    mat_plain(name + "_trafo", (0.40, 0.40, 0.38), rough=0.5)],
                   smooth=True)
    cu = bpy.data.curves.new(name + "_wires", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = 0.030
    cu.bevel_resolution = 1
    cu.use_fill_caps = False
    offsets = [(-0.58, h - 0.22), (0.0, h - 0.22), (0.58, h - 0.22),
               (0.0, h - 1.17), (0.0, h - 2.55)]
    sags = [sag, sag, sag, sag * 1.15, sag * 1.6]
    for (dx, zc), sg in zip(offsets, sags):
        for i in range(len(ys) - 1):
            sp = cu.splines.new("POLY")
            n = 7
            sp.points.add(n - 1)
            for k in range(n):
                t = k / (n - 1.0)
                sp.points[k].co = (x + dx, ys[i] + (ys[i + 1] - ys[i]) * t,
                                   zc - sg * math.sin(math.pi * t), 1.0)
    wob = bpy.data.objects.new(name + "_wires", cu)
    lib.scene().collection.objects.link(wob)
    cu.materials.append(mat_plain(name + "_wire", (0.016, 0.016, 0.020), rough=0.85, spec=0.2))
    return poles, wob


def treeline(name, y, x0=-170.0, x1=170.0, n=30, z=0.0, hmin=2.2, hmax=4.8,
             color=(0.055, 0.070, 0.052), seed=5):
    rng = random.Random(seed)
    bm = bmesh.new()
    for i in range(n):
        x = x0 + (x1 - x0) * (i + rng.uniform(-0.4, 0.4)) / n
        h = rng.uniform(hmin, hmax)
        w = h * rng.uniform(0.55, 0.95)
        add_sphere(bm, 1.0, mat4((x, y + rng.uniform(-3, 3), z + h * 0.55), 0.0,
                                 (w, w * rng.uniform(0.6, 0.9), h * 0.55)), u=8, v=6)
    return bm_obj(name, bm, [mat_plain(name + "_mat", color, rough=0.95, spec=0.1)], smooth=True)


def ridge(name, y, spans, color, seed=3):
    """Low far hill silhouette (never tall: the world is flat paddy country)."""
    rng = random.Random(seed)
    bm = bmesh.new()
    for (xc, hw, h) in spans:
        add_sphere(bm, 1.0, mat4((xc, y, h * 0.05), 0.0, (hw, hw * 0.16, h * 0.5)),
                   u=10, v=6)
    return bm_obj(name, bm, [mat_plain(name + "_mat", color, rough=1.0, spec=0.0)], smooth=True)


# =========================================================================== props
def plastic_bottle(name, loc, rz=0.0, tilt=86.0):
    bm = bmesh.new()
    add_cyl(bm, 0.034, 0.034, 0.17, mat4((0, 0, 0.085)), segs=16, mi=0)
    add_cyl(bm, 0.034, 0.020, 0.045, mat4((0, 0, 0.1925)), segs=16, mi=0)
    add_cyl(bm, 0.019, 0.019, 0.035, mat4((0, 0, 0.2325)), segs=12, mi=0)
    add_cyl(bm, 0.021, 0.021, 0.022, mat4((0, 0, 0.261)), segs=12, mi=1)
    m_body = lib.principled(name + "_pet", (0.82, 0.88, 0.90), roughness=0.10,
                            specular=0.6, alpha=0.34)
    m_cap = mat_plain(name + "_cap", (0.16, 0.34, 0.62), rough=0.35, spec=0.5)
    ob = bm_obj(name, bm, [m_body, m_cap], smooth=True)
    ob.location = loc
    ob.rotation_euler = (tilt * D2R, 0.0, rz)
    return ob


def water_puddle(name, loc, r=1.1, ry=1.6, seed=4):
    rng = random.Random(seed)
    bm = bmesh.new()
    n = 22
    ring = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = 1.0 + 0.16 * math.sin(a * 3.0 + 1.2) + 0.10 * math.sin(a * 7.0)
        ring.append((math.cos(a) * r * rr, math.sin(a) * ry * rr))
    c = bm.verts.new((0, 0, 0))
    vs = [bm.verts.new((x, y, 0)) for (x, y) in ring]
    for i in range(n):
        bm.faces.new((c, vs[i], vs[(i + 1) % n]))
    ob = bm_obj(name, bm, [mat_water(name + "_mat", (0.42, 0.55, 0.74), rough=0.012)],
                smooth=True)
    ob.location = (loc[0], loc[1], 0.005)
    return ob


def wet_road(name, center=(0.0, 1.4), seed=4):
    """Overlapping water sheets on the asphalt (the dumped-water shot)."""
    obs = [water_puddle(name + "_a", center, r=2.5, ry=3.2, seed=seed)]
    obs.append(water_puddle(name + "_b", (center[0] - 1.55, center[1] + 2.1),
                            r=1.5, ry=2.0, seed=seed + 1))
    obs.append(water_puddle(name + "_c", (center[0] + 1.7, center[1] - 1.6),
                            r=1.2, ry=1.6, seed=seed + 2))
    for o in obs[1:]:
        o.location.z += 0.0018
    return obs


def bokeh_drops(name, cam_loc, cam_dir, dists=(0.16, 0.24, 0.33), seed=5):
    """A few out-of-focus water beads right in front of the lens -> gold bokeh."""
    rng = random.Random(seed)
    bm = bmesh.new()
    d = Vector(cam_dir).normalized()
    up = Vector((0, 0, 1))
    right = d.cross(up).normalized()
    for i, dist in enumerate(dists):
        for k in range(2):
            p = Vector(cam_loc) + d * dist + right * rng.uniform(-0.035, 0.035) \
                + up * rng.uniform(-0.03, 0.03)
            add_sphere(bm, rng.uniform(0.007, 0.016), mat4(tuple(p)), u=7, v=5)
    ob = bm_obj(name, bm, [mat_water(name + "_mat", (0.88, 0.94, 1.0), rough=0.01, alpha=0.55)],
                smooth=True)
    return ob



def splash_burst(name, loc, seed=7, n=46, spread=0.42, zmax=0.34):
    rng = random.Random(seed)
    bm = bmesh.new()
    for i in range(n):
        a = rng.uniform(0, 2 * math.pi)
        rr = abs(rng.gauss(0, spread * 0.55))
        z = rng.uniform(0.0, zmax) * (1.0 - min(1.0, rr / spread) * 0.55)
        r = rng.uniform(0.006, 0.026)
        add_sphere(bm, r, mat4((math.cos(a) * rr, math.sin(a) * rr, z)), u=7, v=5)
    ob = bm_obj(name, bm, [mat_water(name + "_mat", (0.84, 0.91, 1.0), rough=0.02, alpha=0.52)],
                smooth=True)
    ob.location = loc
    return ob


def ripple_rings(name, loc, n=3):
    objs = []
    m = mat_water(name + "_mat", (0.82, 0.90, 0.98), rough=0.03)
    for i in range(n):
        bm = bmesh.new()
        bmesh.ops.create_circle(bm, cap_ends=False, segments=40, radius=1.0)
        ob = bm_obj("%s_%d" % (name, i), bm, [m], smooth=True)
        ob.location = (loc[0], loc[1], 0.006 + i * 0.001)
        ob.scale = (0.08, 0.08, 0.08)
        objs.append(ob)
    return objs


def dust_motes(name, area=(16.0, 34.0, 0.15, 3.2), n=140, seed=11,
               color=(1.0, 0.95, 0.85)):
    rng = random.Random(seed)
    bm = bmesh.new()
    for i in range(n):
        add_sphere(bm, rng.uniform(0.004, 0.013),
                   mat4((rng.uniform(-area[0] / 2, area[0] / 2),
                         rng.uniform(-area[1] / 2, area[1] / 2),
                         rng.uniform(area[2], area[3]))), u=5, v=4)
    return bm_obj(name, bm, [lib.emission(name + "_mat", color, strength=0.55)], smooth=True)


def sway(objs, amp=0.020, f0=1, f1=100, period=52.0, step=8, seed=0.0, axis=(0.6, 1.0)):
    for i, ob in enumerate(objs):
        ph = (i * 0.61 + seed) % (2 * math.pi)
        rz = ob.rotation_euler[2]
        f = float(f0)
        while f <= f1:
            t = (f - f0) / 24.0
            a = amp * math.sin(ph + 2 * math.pi * t / (period / 24.0)) * math.sin(ph * 7.3 + 1.0)
            ob.rotation_euler = (a * axis[0], a * axis[1], rz)
            ob.keyframe_insert("rotation_euler", frame=f)
            f += step
    return objs


def mat_grass(name, c_root=(0.10, 0.095, 0.032), c_tip=(0.58, 0.44, 0.13), glow=0.30):
    """Backlit dry grass: UV gradient + a little emission so it reads translucent."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    N, L = nt.nodes, nt.links
    N.clear()
    out = N.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
    bsdf = N.new("ShaderNodeBsdfPrincipled"); bsdf.location = (300, 0)
    bsdf.inputs["Roughness"].default_value = 0.72
    L.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    uvn = N.new("ShaderNodeUVMap"); uvn.location = (-800, 60); uvn.uv_map = "UVMap"
    sep = N.new("ShaderNodeSeparateXYZ"); sep.location = (-620, 60)
    L.new(uvn.outputs["UV"], sep.inputs[0])
    ramp = N.new("ShaderNodeValToRGB"); ramp.location = (-420, 60)
    ramp.color_ramp.elements[0].color = (*c_root, 1.0)
    ramp.color_ramp.elements[1].color = (*c_tip, 1.0)
    L.new(sep.outputs["Y"], ramp.inputs["Fac"])
    L.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    if glow > 0 and "Emission Color" in bsdf.inputs:
        L.new(ramp.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = glow
    return m


def grass_blocks(prefix, blocks, color_set="gold", seed=3, mat=None):
    """lib.grass_patch chopped into a few objects so wind sway reads."""
    objs = []
    for i, (xc, yc, area, count) in enumerate(blocks):
        g = lib.grass_patch("%s_%02d" % (prefix, i), count=count, area=area,
                            seed=seed + i * 7, color_set=color_set,
                            height=(0.14, 0.46), mat=mat)
        g.location = (xc, yc, 0.0)
        objs.append(g)
    return objs



# --------------------------------------------------------------- water macro kit
def dark_asphalt(name="RoadDark"):
    """Backlit wet asphalt: nearly black so only the water carries highlights."""
    return mat_noise(name, (0.028, 0.028, 0.033), (0.010, 0.010, 0.014),
                     scale=3.4, detail=8.0, rough=0.42, bump=0.40, bump_scale=9.0,
                     coord="Object", spec=0.62)


def use_dark_road():
    ob = bpy.data.objects.get("Road")
    if ob is not None:
        ob.data.materials.clear()
        ob.data.materials.append(dark_asphalt())


def splash_spray(name, loc, seed=3, n_main=20, n_fine=90, n_streak=12,
                 spread=0.075, zmax=0.16):
    """Tiny droplets + stretched streaks (frozen high-speed shutter look)."""
    rng = random.Random(seed)
    bm = bmesh.new()
    for i in range(n_main):
        a = rng.uniform(0, math.tau)
        rr = abs(rng.gauss(0, spread * 0.6))
        z = rng.uniform(0.0, zmax) * (1.0 - min(1.0, rr / (spread * 1.6)) * 0.45)
        add_sphere(bm, rng.uniform(0.005, 0.014),
                   mat4((math.cos(a) * rr, math.sin(a) * rr, z)), u=8, v=6)
    for i in range(n_fine):
        a = rng.uniform(0, math.tau)
        rr = abs(rng.gauss(0, spread * 1.15))
        z = rng.uniform(0.0, zmax * 1.6)
        add_sphere(bm, rng.uniform(0.0015, 0.0045),
                   mat4((math.cos(a) * rr, math.sin(a) * rr, z)), u=5, v=4)
    for i in range(n_streak):
        a = rng.uniform(0, math.tau)
        rr = abs(rng.gauss(0, spread * 0.85))
        z = rng.uniform(0.02, zmax * 1.15)
        r = rng.uniform(0.0028, 0.0065)
        L = rng.uniform(3.2, 6.5)
        rot = (Matrix.Rotation(rng.uniform(-0.5, 0.5), 4, "X") @
               Matrix.Rotation(rng.uniform(-0.5, 0.5), 4, "Y"))
        m = (Matrix.Translation((math.cos(a) * rr, math.sin(a) * rr, z)) @ rot @
             Matrix.Diagonal((1.0, 1.0, L, 1.0)))
        n0 = len(bm.faces)
        bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=6, radius=r, matrix=m)
        _tag(bm, n0, 0, True)
    m = mat_water(name + "_mat", (0.88, 0.93, 1.0), rough=0.045, alpha=0.30)
    ob = bm_obj(name, bm, [m], smooth=True)
    ob.location = loc
    return ob


def water_sheet(name, loc, r=0.16, ry=0.20, seed=5):
    """Small, smooth, dark sheet: mirror highlight without a bright polygon."""
    bm = bmesh.new()
    n = 48
    ring = []
    for i in range(n):
        a = 2 * math.pi * i / n
        rr = 1.0 + 0.10 * math.sin(a * 3 + 1.2) + 0.06 * math.sin(a * 7 + 0.4)
        ring.append((math.cos(a) * r * rr, math.sin(a) * ry * rr))
    c = bm.verts.new((0, 0, 0))
    vs = [bm.verts.new((x, y, 0)) for (x, y) in ring]
    for i in range(n):
        bm.faces.new((c, vs[i], vs[(i + 1) % n]))
    ob = bm_obj(name, bm, [mat_water(name + "_mat", (0.035, 0.048, 0.085),
                                     rough=0.035)], smooth=True)
    ob.location = (loc[0], loc[1], 0.005)
    return ob


def dim_ambient(strength=0.30):
    """Macro shots: kill the ambient so the asphalt reads near-black and only
    the water catches the sun."""
    w = lib.scene().world
    if not w or not w.node_tree:
        return
    for n in w.node_tree.nodes:
        if n.type == "BACKGROUND":
            n.inputs[1].default_value = strength


def cam_(loc, target, **kw):
    """lib.camera + a far clip that actually reaches the 2800 m sky dome."""
    c = lib.camera(loc, target, **kw)
    c.data.clip_end = 4200.0
    return c



def haze_box(name, center=(0.0, 170.0), size=(900.0, 1200.0), height=46.0,
             density=0.00060, color=(1.0, 0.86, 0.64), anisotropy=0.45):
    """EEVEE quirk: a *world-volume* scatters away almost all direct light on
    surfaces (road 178 -> 19).  A mesh volume object behaves correctly, so haze
    is a couple of big ground-hugging boxes instead."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(center[0], center[1], height * 0.42))
    ob = bpy.context.object
    ob.name = name
    ob.scale = (size[0], size[1], height)
    m = bpy.data.materials.new(name + "_mat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    pv = nt.nodes.new("ShaderNodeVolumePrincipled")
    pv.inputs["Color"].default_value = (*color, 1.0)
    pv.inputs["Anisotropy"].default_value = anisotropy
    # height falloff: thick at the ground, gone before the box top -> no hard edge
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    mr = nt.nodes.new("ShaderNodeMapRange")
    mr.inputs["From Min"].default_value = -0.5
    mr.inputs["From Max"].default_value = 0.5
    mr.clamp = True
    nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
    inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"
    inv.inputs[0].default_value = 1.0
    nt.links.new(mr.outputs["Result"], inv.inputs[1])
    pw = nt.nodes.new("ShaderNodeMath"); pw.operation = "POWER"
    pw.inputs[1].default_value = 2.2
    nt.links.new(inv.outputs["Value"], pw.inputs[0])
    dm = nt.nodes.new("ShaderNodeMath"); dm.operation = "MULTIPLY"
    dm.inputs[1].default_value = density
    nt.links.new(pw.outputs["Value"], dm.inputs[0])
    nt.links.new(dm.outputs["Value"], pv.inputs["Density"])
    nt.links.new(pv.outputs["Volume"], out.inputs["Volume"])
    ob.data.materials.append(m)
    return ob


def haze_layer(preset):
    F = preset["fog"]
    d = F["density"]
    c = F.get("haze_color", F["color"])
    a = F.get("anisotropy", 0.45)
    c = F.get("haze_color", tuple(x * y for x, y in zip(F["color"], (0.52, 0.40, 0.26))))
    return [haze_box("HazeMain", (0.0, 4200.0), (3200.0, 9000.0),
                     F.get("haze_h", 320.0), d, c, a)]


# =========================================================================== world presets
# gold world sun (agreed with Lead / field team): unit vector scene -> sun
GOLD_SUN = (0.06, 0.80, 0.34)
DUSK_SUN = (0.035, 0.9982, 0.030)     # ~1.7 deg above the horizon
VIOLET_SUN = (0.06, 0.80, 0.34)       # same bearing, sun buried in storm cloud

PRESETS = {
    # gold world — numbers taken from the Lead's field look-dev so the road and
    # the sunflower field are literally the same sky.
    "noon_hot": dict(
        sun_dir=(0.06, 0.84, 0.40),
        sun_color=(1.0, 0.95, 0.82), sun_energy=9.0, sun_angle=0.6,
        sky=dict(c_horizon=(1.0, 0.52, 0.12), c_mid=(0.05, 0.34, 1.0),
                 c_zenith=(0.01, 0.055, 0.34), sun_power=70.0, glow=0.18,
                 strength=0.95, sun_exp=2600.0, glow_exp=16.0),
        fog=dict(density=0.00060, color=(1.0, 0.86, 0.64), anisotropy=0.45,
                 ambient=(1.0, 0.95, 0.90), ambient_strength=1.45),
        fill=dict(energy=1500.0, color=(1.0, 0.95, 0.90), size=170.0, height=22.0),
        sky_fill=dict(energy=2.6, direction=(0.15, -0.35, 0.92),
                      color=(0.92, 0.95, 1.0), angle=12.0),
        ground=((0.215, 0.182, 0.104), (0.092, 0.082, 0.048)),
        road=((0.118, 0.119, 0.129), (0.066, 0.067, 0.076)),
        treeline=(0.105, 0.110, 0.095), ridge=(0.50, 0.43, 0.40), pole=(0.44, 0.43, 0.41),
        vol_end=3000.0, exposure=-0.45, ground_size=1200.0, sky_radius=2800.0,
    ),
    "noon_side": dict(
        sun_dir=(0.06, 0.84, 0.40),
        sun_color=(1.0, 0.94, 0.80), sun_energy=9.5, sun_angle=0.5,
        sky=dict(c_horizon=(1.0, 0.50, 0.11), c_mid=(0.05, 0.33, 0.99),
                 c_zenith=(0.01, 0.054, 0.33), sun_power=70.0, glow=0.18,
                 strength=0.93, sun_exp=2600.0, glow_exp=16.0),
        fog=dict(density=0.00070, color=(1.0, 0.85, 0.62), anisotropy=0.42,
                 ambient=(1.0, 0.95, 0.90), ambient_strength=1.35),
        fill=dict(energy=1400.0, color=(1.0, 0.95, 0.90), size=170.0, height=21.0),
        sky_fill=dict(energy=2.4, direction=(0.15, -0.35, 0.92),
                      color=(0.92, 0.95, 1.0), angle=12.0),
        ground=((0.210, 0.178, 0.101), (0.090, 0.080, 0.046)),
        road=((0.115, 0.116, 0.126), (0.064, 0.065, 0.074)),
        treeline=(0.100, 0.105, 0.092), ridge=(0.48, 0.42, 0.40), pole=(0.44, 0.43, 0.41),
        vol_end=3000.0, exposure=-0.40, ground_size=1200.0, sky_radius=2800.0,
    ),
    # dusk — same bearing, sun on the horizon, afterglow
    "dusk_afterglow": dict(
        sun_dir=(0.035, 0.9982, 0.030),
        sun_color=(1.0, 0.60, 0.28), sun_energy=9.0, sun_angle=0.8,
        sky=dict(c_horizon=(1.0, 0.42, 0.10), c_mid=(0.42, 0.20, 0.42),
                 c_zenith=(0.055, 0.075, 0.26), sun_power=90.0, glow=0.30,
                 strength=0.92, sun_exp=2200.0, glow_exp=12.0),
        fog=dict(density=0.00085, color=(1.0, 0.62, 0.38), anisotropy=0.50,
                 ambient=(0.90, 0.72, 0.66), ambient_strength=1.8),
        fill=dict(energy=1500.0, color=(1.0, 0.80, 0.65), size=170.0, height=20.0),
        sky_fill=dict(energy=1.4, direction=(0.12, -0.30, 0.94),
                      color=(0.72, 0.70, 0.95), angle=14.0),
        ground=((0.200, 0.150, 0.095), (0.082, 0.062, 0.046)),
        road=((0.120, 0.115, 0.125), (0.062, 0.060, 0.070)),
        treeline=(0.62, 0.40, 0.26), ridge=(0.34, 0.27, 0.33),
        pole=(0.20, 0.165, 0.155), treeline_amt=0.0,
        vol_end=4200.0, exposure=-0.28, ground_size=1200.0, sky_radius=2800.0,
    ),
    # violet — same bearing, sun buried in storm cloud
    "violet_dusk": dict(
        sun_dir=(0.06, 0.84, 0.40),
        sun_color=(0.72, 0.62, 0.95), sun_energy=2.6, sun_angle=4.0,
        sky=dict(c_horizon=(0.42, 0.28, 0.50), c_mid=(0.15, 0.155, 0.36),
                 c_zenith=(0.035, 0.035, 0.115), sun_power=8.0, glow=0.35,
                 strength=1.00, sun_exp=900.0, glow_exp=6.0),
        fog=dict(density=0.00210, color=(0.44, 0.37, 0.58), anisotropy=0.34,
                 ambient=(0.46, 0.50, 0.70), ambient_strength=1.2),
        fill=dict(energy=700.0, color=(0.64, 0.68, 0.92), size=170.0, height=22.0),
        sky_fill=dict(energy=0.8, direction=(0.15, -0.30, 0.94),
                      color=(0.55, 0.60, 0.90), angle=16.0),
        ground=((0.115, 0.115, 0.102), (0.042, 0.044, 0.046)),
        road=((0.078, 0.076, 0.090), (0.042, 0.042, 0.052)),
        treeline=(0.050, 0.045, 0.070), ridge=(0.17, 0.15, 0.21),
        pole=(0.14, 0.13, 0.17), treeline_amt=0.0,
        vol_end=2200.0, exposure=-0.15, ground_size=1200.0, sky_radius=2800.0,
    ),
}

ROAD_W = 6.4
ROAD_Y0, ROAD_Y1 = -300.0, 460.0
POLE_X = 5.15
POLE_YS = [y for y in range(-224, 460, 38)]


def build_road(variant="noon_hot", q=1.0, res=(1920, 1080), samples=24, exposure=0.0):
    return build_road_world(variant, q=q, res=res, samples=samples, exposure=exposure)


def build_road_world(preset="noon_hot", q=1.0, res=(1920, 1080), samples=24, exposure=0.0):
    """Build the complete road world (no camera). Returns dict of key objects."""
    P = PRESETS[preset]
    lib.reset()
    lib.setup_render(samples=samples, resolution=res, exposure=exposure or P.get("exposure", 0.0))
    sc = lib.scene()
    try:
        sc.eevee.use_raytracing = False      # Lead: off, it is the big cost
    except Exception:
        pass
    try:
        sc.eevee.volumetric_end = P["vol_end"]
        sc.eevee.volumetric_tile_size = "8"
        sc.eevee.volumetric_samples = 48
    except Exception:
        pass

    sd = Vector(P["sun_dir"]).normalized()
    lib.sky_dome(name="Sky_" + preset, radius=P.get("sky_radius", 2800.0),
                 sun_dir=tuple(sd), sun_color=P["sun_color"], **P["sky"])
    # world background = ambient light only; the haze is a mesh volume box
    lib.fog(density=0.0, color=P["fog"]["color"],
            anisotropy=P["fog"]["anisotropy"], ambient=P["fog"]["ambient"],
            ambient_strength=P["fog"]["ambient_strength"])
    haze_layer(P)
    sun = lib.sun_light(energy=P["sun_energy"], direction=tuple(-sd),
                        color=P["sun_color"], angle_deg=P["sun_angle"])
    if P.get("sky_fill"):
        sf = P["sky_fill"]
        lib.sun_light(energy=sf["energy"], direction=sf["direction"],
                      color=sf["color"], angle_deg=sf["angle"])
    fl = lib.fill_light(energy=P["fill"]["energy"], color=P["fill"]["color"],
                        size=P["fill"]["size"], height=P["fill"]["height"],
                        target=(0.0, 6.0, 1.0))

    g = ground_plane("Ground", P.get("ground_size", 1200.0), -0.03, P)
    road = road_ribbon("Road", ROAD_W, ROAD_Y0, ROAD_Y1, 0.0, P)
    marks = road_markings("Markings", ROAD_W, ROAD_Y0, ROAD_Y1, 0.0)
    sh = shoulder_pair("Shoulder", ROAD_W, ROAD_Y0, ROAD_Y1, -0.004, P)
    curb = curb_pair("Curb", ROAD_W, ROAD_Y0, ROAD_Y1, 0.0)

    tl = None
    if P.get("treeline_amt", 1.0) > 0:
        tl = treeline("TreeLine", 700.0, -420, 420, n=int(26 * q) + 6,
                      color=P["treeline"], hmin=2.0, hmax=4.2)
    rdg = ridge("Ridge", 660.0, [(-300, 380, 26), (80, 300, 34), (420, 260, 22)],
                P["ridge"])
    poles, wires = power_line("Poles", POLE_X, POLE_YS, h=11.2,
                              pole_color=P.get("pole", (0.44, 0.43, 0.41)))

    world = dict(preset=P, sun=sun, fill=fl, ground=g, road=road, marks=marks,
                 curb=curb, poles=poles, wires=wires, treeline=tl, ridge=rdg,
                 flowers=[], grass=[], extras=[])

    if preset in ("noon_hot", "noon_side"):
        fl_objs = lib.sunflower_field(count=int(54 * q), area=(9.0, 30.0), seed=31,
                                      color_set="gold", center=(9.2, -6.0),
                                      scale_range=(0.85, 1.25), stem_random=(0.95, 1.45),
                                      face_dir=(0.30, 0.95), face_jitter=0.55)
        fl_objs += lib.sunflower_field(count=max(4, int(9 * q)), area=(2.2, 5.0), seed=32,
                                       color_set="gold", center=(5.55, -8.0),
                                       scale_range=(0.95, 1.30), stem_random=(1.0, 1.4),
                                       face_dir=(0.30, 0.95), face_jitter=0.7)
        fl_objs += lib.sunflower_field(count=int(16 * q), area=(7.0, 26.0), seed=33,
                                       color_set="gold", center=(-9.6, 14.0),
                                       scale_range=(0.85, 1.2), face_dir=(-0.2, 1.0))
        sway(fl_objs, amp=0.014, f0=1, f1=200, period=62.0)
        world["flowers"] = fl_objs
        world["grass"] = grass_blocks("Grass", [
            (6.8, 6.0, (3.4, 44.0), 380), (-7.0, 2.0, (3.4, 44.0), 300),
            (9.6, -22.0, (6.0, 20.0), 200)], color_set="gold", seed=9)
        sway(world["grass"], amp=0.02, f0=1, f1=200, period=54.0)
    elif preset == "violet_dusk":
        fl_objs = lib.sunflower_field(count=int(24 * q), area=(8.0, 26.0), seed=77,
                                      color_set="violet", center=(8.8, 6.0),
                                      scale_range=(0.85, 1.2), stem_random=(0.95, 1.4),
                                      face_dir=(0.30, 0.95), face_jitter=0.6)
        sway(fl_objs, amp=0.045, f0=1, f1=200, period=34.0)
        world["flowers"] = fl_objs
        world["grass"] = grass_blocks("Grass", [
            (6.4, 2.0, (4.0, 46.0), 170), (-6.6, 8.0, (4.0, 46.0), 130)],
            color_set="violet", seed=11)
        sway(world["grass"], amp=0.075, f0=1, f1=200, period=28.0, step=6)
    elif preset == "dusk_afterglow":
        world["grass"] = grass_blocks("Grass", [
            (6.6, 4.0, (3.4, 60.0), 150), (-6.8, 0.0, (3.4, 60.0), 130)],
            color_set="gold", seed=13)
        sway(world["grass"], amp=0.018, f0=1, f1=200, period=64.0)
    return world


# =========================================================================== still helpers
def render_still(name, cam, frame, res=(1280, 720), samples=16):
    sc = lib.scene()
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.frame_set(int(frame))
    try:
        sc.eevee.taa_render_samples = samples
    except Exception:
        pass
    os.makedirs(TESTS, exist_ok=True)
    sc.render.filepath = os.path.join(TESTS, name)
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print("[still] %s  %.2fs" % (name, time.time() - t), flush=True)


# =========================================================================== look-dev
def _look_noon_hot(res, samples):
    W = build_road_world("noon_hot", q=1.0, res=res, samples=samples)
    sd = Vector(W["preset"]["sun_dir"]).normalized()
    f0 = int(BY_ID["S04"]["f0"])
    lib.sunflower_field(count=5, area=(2.6, 4.0), seed=41, color_set="gold",
                        center=(5.25, -12.4), scale_range=(1.20, 1.45),
                        stem_random=(1.05, 1.25), face_dir=(0.30, 0.95))

    # A: S04 head — low at the edge of the sunflowers, up into the blown-out sun
    loc = Vector((4.45, -14.4, 0.98))
    cam = cam_(tuple(loc), tuple(loc + sd * 16.0), lens=35.0, fstop=8.0,
               focus_distance=2.2, name="Cam04a")
    render_still("A_noon_04a", cam, f0, res=res, samples=samples)

    # B: S04 tail — asphalt lead-in with poles on the right
    cam = cam_((1.30, -8.6, 1.06), (0.30, 15.0, 0.55), lens=32.0, fstop=2.8,
               focus_distance=10.0, name="Cam04b")
    render_still("A_noon_04b", cam, f0 + 101, res=res, samples=samples)

    # C: S06 wide road, girl silhouette far, sun behind, poles, shimmer
    plastic_bottle("Bottle", (-1.45, -18.6, 0.042), rz=0.9, tilt=86.0)
    girl = character.figure("Girl06", variant="girl", pose="stand", height=1.56,
                            dress_len=0.40, facing=0.0)
    girl.location = (0.35, 9.0, 0.0)
    cam = cam_((1.25, -20.5, 0.78), (-0.7, 26.0, 1.55), lens=42.0, fstop=4.0,
               focus_distance=27.0, name="Cam06")
    render_still("A_noon_06", cam, int(BY_ID["S06"]["f0"]), res=res, samples=samples)

    # D: S05 macro — dark asphalt, backlit droplets, water sheet
    water_puddle("Puddle", (0.0, 0.44), r=0.30, ry=0.36, seed=5)
    splash_burst("Splash", (0.0, 0.40, 0.008), n=44, spread=0.13, zmax=0.15)
    ripple_rings("Ripple", (0.0, 0.38), n=2)
    bokeh_drops("Bokeh", (0.0, -0.26, 0.135), (0.02, 1.0, -0.35))
    cam = cam_((0.0, -0.32, 0.20), (0.0, 0.95, -0.12), lens=60.0, fstop=4.0,
               focus_distance=0.79, name="Cam05")
    render_still("A_noon_05", cam, int(BY_ID["S05"]["f0"]), res=res, samples=samples)
    print("[look] noon_hot OK", flush=True)


def _look_noon_side(res, samples):
    W = build_road_world("noon_side", q=1.0, res=res, samples=samples)
    # S07 two silhouettes, one walking away, long shadows
    a = character.figure("A07", variant="girl", pose="stand", height=1.66,
                         dress_len=0.40, facing=math.radians(14.0))
    a.location = (0.55, -2.0, 0.0)
    b = character.figure("B07", variant="boy", pose="walk", height=1.74, facing=0.0)
    b.location = (0.95, 3.6, 0.0)
    cam = cam_((0.15, -32.0, 1.16), (0.30, 8.0, 1.06), lens=135.0, fstop=4.0,
               focus_distance=30.0, name="Cam07")
    render_still("A_side_07", cam, int(BY_ID["S07"]["f0"]), res=res, samples=samples)

    # S09 back-lit profile close (hand near face = "hold" pose reads as hand raised)
    c = character.figure("A09", variant="girl", pose="hold", height=1.66,
                         dress_len=0.42, facing=math.pi * 0.5, hand_reach=0.13)
    c.location = (0.0, 0.0, 0.0)
    cam = cam_((-2.35, 0.55, 1.42), (0.0, 0.18, 1.31), lens=85.0, fstop=1.6,
                     focus_distance=2.55, name="Cam09")
    render_still("A_side_09", cam, int(BY_ID["S09"]["f0"]), res=res, samples=samples)

    # S10 two people sitting on the curb, dust, poles
    d = character.figure("A10", variant="girl", pose="sit", height=1.64,
                         dress_len=0.42, facing=math.radians(250.0))
    d.location = (2.62, 2.2, 0.16)
    e = character.figure("B10", variant="boy", pose="sit", height=1.74,
                         facing=math.radians(288.0))
    e.location = (3.42, 2.9, 0.16)
    dust_motes("Dust", area=(14.0, 26.0, 0.2, 3.4), n=120)
    cam = cam_((0.4, -10.5, 1.10), (1.9, 3.2, 0.98), lens=38.0, fstop=2.6,
                     focus_distance=12.5, name="Cam10")
    render_still("A_side_10", cam, int(BY_ID["S10"]["f0"]), res=res, samples=samples)
    print("[look] noon_side OK", flush=True)


def _look_dusk(res, samples):
    W = build_road_world("dusk_afterglow", q=1.0, res=res, samples=samples)
    g = character.figure("G22", variant="girl", pose="walk", height=1.60, facing=0.0)
    g.location = (0.35, 42.0, 0.0)
    cam = cam_((0.0, -84.0, 1.30), (0.35, 60.0, 2.05), lens=200.0, fstop=5.6,
                     focus_distance=126.0, name="Cam22")
    render_still("A_dusk_22", cam, int(BY_ID["S22"]["f0"]), res=res, samples=samples)
    a = character.figure("A50", variant="girl", pose="stand", height=1.66,
                         dress_len=0.42, facing=math.radians(182.0))
    a.location = (0.0, 2.2, 0.0)
    cam = cam_((0.0, -6.2, 0.45), (0.0, 12.0, 3.6), lens=58.0, fstop=2.2,
                     focus_distance=8.0, name="Cam50")
    render_still("A_dusk_50", cam, int(BY_ID["S50"]["f0"]), res=res, samples=samples)
    print("[look] dusk OK", flush=True)


def _look_violet(res, samples):
    W = build_road_world("violet_dusk", q=1.0, res=res, samples=samples)
    a = character.figure("A32", variant="girl", pose="stand", height=1.66,
                         dress_len=0.42, facing=math.radians(104.0))
    a.location = (3.05, 3.2, 0.0)
    cam = cam_((0.85, -6.2, 0.88), (2.5, 5.0, 1.10), lens=36.0, fstop=2.8,
                     focus_distance=7.2, name="Cam32")
    render_still("A_violet_32", cam, int(BY_ID["S32"]["f0"]), res=res, samples=samples)
    print("[look] violet OK", flush=True)


LOOK = dict(noon_hot=_look_noon_hot, noon_side=_look_noon_side,
            dusk_afterglow=_look_dusk, violet_dusk=_look_violet)


# =========================================================================== shot builders
def setup_S04():
    W = build_road_world("noon_hot", q=1.0, res=(1920, 1080), samples=24)
    sd = Vector(W["preset"]["sun_dir"]).normalized()
    f0, f1 = 434, 535
    lib.sunflower_field(count=5, area=(2.6, 4.0), seed=41, color_set="gold",
                        center=(5.25, -12.4), scale_range=(1.20, 1.45),
                        stem_random=(1.05, 1.25), face_dir=(0.30, 0.95))
    loc0 = Vector((4.45, -14.4, 0.98))
    cam = cam_(tuple(loc0), tuple(loc0 + sd * 16.0), lens=35.0, fstop=8.0,
               focus_distance=2.2, name="Cam")
    lib.anim_camera(cam, [
        (f0, tuple(loc0), tuple(loc0 + sd * 16.0), 2.2),
        (f0 + 32, (4.42, -14.2, 0.97), (5.6, 3.0, 4.6), 2.9),
        (f0 + 64, (4.38, -13.9, 0.95), (2.6, 9.0, 1.2), 5.0),
        (f1, (4.30, -13.5, 0.92), (0.30, 16.0, 0.50), 10.0),
    ], lens_keys=[(f0, 35.0), (f1, 38.0)])
    return W


def setup_S05():
    W = build_road_world("noon_hot", q=1.0, res=(1920, 1080), samples=12)
    use_dark_road()
    dim_ambient(0.22)
    water_sheet("Sheet", (0.0, 0.50), r=0.11, ry=0.14, seed=5)
    spray = splash_spray("Spray", (0.0, 0.52, 0.010), seed=5, n_main=22, n_fine=110,
                         n_streak=14, spread=0.070, zmax=0.15)
    lib.area_light("ShotFill", (0.40, -0.34, 0.62), (0.0, 0.52, 0.07), energy=2.4,
                   size=0.30, color=(1.0, 0.96, 0.90))
    lib.area_light("Kick", (-0.30, 0.10, 0.30), (0.0, 0.52, 0.05), energy=1.4,
                   size=0.20, color=(1.0, 0.88, 0.72))
    f0, f1 = 536, 636
    cam = cam_((0.0, -0.74, 0.30), (0.0, 0.55, 0.02), lens=85.0, fstop=5.6,
               focus_distance=1.25, name="Cam")
    lib.anim_camera(cam, [(f0, (0.0, -0.74, 0.30), (0.0, 0.55, 0.02), 1.25),
                          (f1, (0.0, -0.70, 0.29), (0.0, 0.55, 0.02), 1.20)])
    lib.anim_obj(spray, [(f0, (0.0, 0.52, 0.010)), (f0 + 40, (0.0, 0.53, 0.026)),
                         (f0 + 80, (0.0, 0.54, 0.016)), (f1, (0.0, 0.55, 0.007))])
    lib.scene().view_settings.exposure = -0.75
    return W


def setup_S06():
    W = build_road_world("noon_hot", q=1.0, res=(1920, 1080), samples=24)
    plastic_bottle("Bottle", (-1.45, -18.6, 0.042), rz=0.9, tilt=86.0)
    girl = character.figure("Girl", variant="girl", pose="walk", height=1.60, facing=0.0)
    girl.location = (0.35, 9.0, 0.0)
    f0, f1 = 637, 740
    cam = cam_((1.25, -20.5, 0.78), (-0.7, 26.0, 1.55), lens=42.0, fstop=4.0,
                     focus_distance=27.0, name="Cam")
    lib.anim_camera(cam, [(f0, (1.25, -20.5, 0.78), (-0.7, 26.0, 1.55)),
                          (f1, (1.05, -17.0, 0.76), (-0.6, 26.0, 1.50))])
    character.walk_path(girl, [(f0, (0.35, 9.0, 0.0), 0.0), (f1, (0.40, 15.0, 0.0), 0.0)])
    return W


def setup_S08():
    W = build_road_world("noon_hot", q=1.0, res=(1920, 1080), samples=12)
    use_dark_road()
    dim_ambient(0.22)
    water_sheet("Sheet", (0.0, 0.36), r=0.085, ry=0.11, seed=7)
    spray = splash_spray("Spray", (0.0, 0.38, 0.008), seed=9, n_main=26, n_fine=150,
                         n_streak=20, spread=0.050, zmax=0.115)
    lib.area_light("ShotFill", (0.30, -0.24, 0.50), (0.0, 0.38, 0.05), energy=2.0,
                   size=0.25, color=(1.0, 0.96, 0.90))
    lib.area_light("Kick", (-0.22, 0.06, 0.24), (0.0, 0.38, 0.04), energy=1.1,
                   size=0.16, color=(1.0, 0.86, 0.70))
    f0, f1 = 847, 984
    cam = cam_((0.0, -0.52, 0.235), (0.0, 0.40, 0.015), lens=100.0, fstop=5.6,
               focus_distance=0.90, name="Cam")
    lib.anim_camera(cam, [(f0, (0.0, -0.52, 0.235), (0.0, 0.40, 0.015), 0.90),
                          (f1, (0.0, -0.48, 0.230), (0.0, 0.40, 0.015), 0.86)])
    lib.anim_obj(spray, [(f0, (0.0, 0.38, 0.008)), (f0 + 46, (0.0, 0.39, 0.020)),
                         (f0 + 100, (0.0, 0.40, 0.013)), (f1, (0.0, 0.41, 0.006))])
    lib.scene().view_settings.exposure = -0.75
    return W


def setup_S07():
    W = build_road_world("noon_side", q=1.0, res=(1920, 1080), samples=24)
    a = character.figure("A", variant="girl", pose="stand", height=1.66,
                         dress_len=0.40, facing=math.radians(14.0))
    a.location = (0.55, -2.0, 0.0)
    b = character.figure("B", variant="boy", pose="walk", height=1.74, facing=0.0)
    b.location = (0.95, 3.6, 0.0)
    f0, f1 = 741, 846
    cam = cam_((0.15, -32.0, 1.16), (0.30, 8.0, 1.06), lens=135.0, fstop=4.0,
               focus_distance=30.0, name="Cam")
    lib.anim_camera(cam, [(f0, (0.15, -32.0, 1.16), (0.30, 8.0, 1.06)),
                          (f1, (0.20, -31.2, 1.15), (0.30, 8.2, 1.05))])
    character.walk_path(b, [(f0, (0.95, 3.6, 0.0), 0.0), (f1, (1.15, 11.2, 0.0), 0.0)])
    character.idle(a, amp=0.008, keys=(f0, f0 + 52, f1))
    return W


def setup_S09():
    W = build_road_world("noon_side", q=1.0, res=(1920, 1080), samples=24)
    c = character.figure("A", variant="girl", pose="hold", height=1.66,
                         dress_len=0.42, facing=math.pi * 0.5, hand_reach=0.13)
    c.location = (0.0, 0.0, 0.0)
    cam = cam_((-2.35, 0.55, 1.42), (0.0, 0.18, 1.31), lens=85.0, fstop=1.6,
                     focus_distance=2.55, name="Cam")
    lib.anim_camera(cam, [(985, (-2.35, 0.55, 1.42), (0.0, 0.18, 1.31), 2.55),
                          (1051, (-2.16, 0.42, 1.40), (0.0, 0.16, 1.30), 2.35)])
    character.idle(c, amp=0.006, keys=(985, 1018, 1051))
    return W


def setup_S10():
    W = build_road_world("noon_side", q=1.0, res=(1920, 1080), samples=24)
    a = character.figure("A", variant="girl", pose="sit", height=1.64,
                         dress_len=0.42, facing=math.radians(250.0))
    a.location = (2.62, 2.2, 0.16)
    b = character.figure("B", variant="boy", pose="sit", height=1.74,
                         facing=math.radians(288.0))
    b.location = (3.42, 2.9, 0.16)
    dust_motes("Dust", area=(14.0, 26.0, 0.2, 3.4), n=120)
    f0, f1 = 1052, 1152
    cam = cam_((0.4, -10.5, 1.10), (1.9, 3.2, 0.98), lens=38.0, fstop=2.6,
                     focus_distance=12.5, name="Cam")
    lib.anim_camera(cam, [(f0, (0.4, -10.5, 1.10), (1.9, 3.2, 0.98)),
                          (f1, (0.62, -9.0, 1.07), (1.9, 3.4, 0.96))])
    character.idle(a, amp=0.007, keys=(f0, f0 + 50, f1))
    character.idle(b, amp=0.009, phase=1.7, keys=(f0, f0 + 50, f1))
    return W


def setup_S22():
    W = build_road_world("dusk_afterglow", q=1.0, res=(1920, 1080), samples=24)
    g = character.figure("Girl", variant="girl", pose="walk", height=1.60, facing=0.0)
    g.location = (0.35, 42.0, 0.0)
    f0, f1 = 2308, 2502
    cam = cam_((0.0, -84.0, 1.30), (0.35, 60.0, 2.05), lens=200.0, fstop=5.6,
                     focus_distance=126.0, name="Cam")
    lib.anim_camera(cam, [(f0, (0.0, -84.0, 1.30), (0.35, 60.0, 2.05), 126.0),
                          (f1, (0.06, -80.0, 1.29), (0.35, 60.0, 2.02), 122.0)])
    character.walk_path(g, [(f0, (0.35, 42.0, 0.0), 0.0), (f1, (0.55, 56.0, 0.0), 0.0)])
    return W


def setup_S50():
    W = build_road_world("dusk_afterglow", q=1.0, res=(1920, 1080), samples=24)
    a = character.figure("A", variant="girl", pose="stand", height=1.66,
                         dress_len=0.42, facing=math.radians(182.0))
    a.location = (0.16, 3.0, 0.0)
    f0, f1 = 5188, 5304
    cam = cam_((0.30, -9.6, 0.46), (0.20, 12.0, 2.4), lens=38.0, fstop=2.4,
               focus_distance=13.0, name="Cam")
    lib.anim_camera(cam, [(f0, (0.30, -9.6, 0.46), (0.20, 12.0, 2.4), 13.0),
                          (f1, (0.24, -8.0, 0.48), (0.20, 12.0, 2.2), 11.4)])
    character.idle(a, amp=0.010, keys=(f0, f0 + 58, f1))
    return W


def setup_S32():
    W = build_road_world("violet_dusk", q=1.0, res=(1920, 1080), samples=20)
    a = character.figure("A", variant="girl", pose="stand", height=1.66,
                         dress_len=0.42, facing=math.radians(104.0))
    a.location = (3.05, 3.2, 0.0)
    f0, f1 = 3450, 3542
    cam = cam_((0.85, -6.2, 0.88), (2.5, 5.0, 1.10), lens=36.0, fstop=2.8,
                     focus_distance=7.2, name="Cam")
    lib.anim_camera(cam, [(f0, (0.85, -6.2, 0.88), (2.5, 5.0, 1.10), 7.2),
                          (f1, (0.95, -5.1, 0.86), (2.55, 5.1, 1.06), 6.2)])
    character.idle(a, amp=0.012, keys=(f0, f0 + 46, f1))
    return W


SHOT_SETUP = dict(S04=setup_S04, S05=setup_S05, S06=setup_S06, S08=setup_S08,
                  S07=setup_S07, S09=setup_S09, S10=setup_S10,
                  S22=setup_S22, S50=setup_S50, S32=setup_S32)


def render_shot(shot_id, samples=None):
    shot = BY_ID[shot_id]
    t0 = time.time()
    SHOT_SETUP[shot_id]()
    lib.render(shot, os.path.join(PLATES, shot_id), samples=samples or 14)
    dt = time.time() - t0
    print("[shot] %s %d frames in %.1fs (%.2fs/frame)" %
          (shot_id, shot["nframes"], dt, dt / shot["nframes"]), flush=True)


def still_shot(shot_id, frame, res=(1280, 720), samples=16):
    SHOT_SETUP[shot_id]()
    render_still("A_%s_f%04d" % (shot_id, int(frame)), lib.scene().camera,
                 int(frame), res=res, samples=samples)


# =========================================================================== main
def main():
    argv = sys.argv
    args = argv[argv.index("--") + 1:] if "--" in argv else []
    if not args:
        print("usage: -- look <variant> | shot <SID> [samples] | still <SID> <frame>")
        return
    cmd = args[0]
    if cmd == "look":
        name = args[1] if len(args) > 1 else "noon_hot"
        LOOK[name](res=(1280, 720), samples=16)
    elif cmd == "shot":
        render_shot(args[1], samples=int(args[2]) if len(args) > 2 else None)
    elif cmd == "still":
        still_shot(args[1], int(args[2]))
    else:
        print("unknown cmd", cmd)


if __name__ == "__main__":
    main()
