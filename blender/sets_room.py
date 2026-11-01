# -*- coding: utf-8 -*-
"""
sets_room.py — Team B interior sets for "紫色の向日葵".
Blender 5.2.3 LTS / BLENDER_EEVEE, renders via command line.

Owned by teammate scenery-interior.  Import only lib.py (do not fork it).

Room layout (metres, interior)
------------------------------
  X: -2.8 .. 2.8      Y: -2.2 .. 2.2 (window wall at +Y)      Z: 0 .. 2.7
  window   : x -1.2..1.2, z 0.95..2.30, wall plane y=2.2
  desk     : x -2.45..-0.72, y 1.50..2.14, top z 0.74   (paper + dried sunflower)
  bed      : x 1.12..2.72,  y -2.15..0.50, mattress top z 0.52
  night bx : x 0.54..1.06,  y -2.12..-1.55, top z 0.52  (lamp + clock + ice cream)
  clock    : on -Y wall (x 1.6, z 1.62)
  curtain  : both window sides, y 2.04
  plant    : windowsill x 0.98

Entry points
------------
  blender.exe -b -P blender/sets_room.py -- --lookdev night_lamp|rain_night|macro_cold|all
  blender.exe -b -P blender/sets_room.py -- --shots S35,S36 --samples 24
"""
import bpy, bmesh, math, random, sys, os, time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import lib
from mathutils import Vector, Matrix

ROOT = lib.ROOT
PLATES = os.path.join(ROOT, "plates")
TESTS = os.path.join(PLATES, "_tests")

# ---------------------------------------------------------------- room constants
RX0, RX1 = -2.8, 2.8
RY0, RY1 = -2.2, 2.2
RZ1 = 2.7
WIN_X0, WIN_X1 = -1.20, 1.20
WIN_Z0, WIN_Z1 = 0.95, 2.30
DESK_X0, DESK_X1 = -2.45, -0.72
DESK_Y0, DESK_Y1 = 1.50, 2.14
DESK_Z = 0.74
BED_X0, BED_X1 = 1.12, 2.72
BED_Y0, BED_Y1 = -2.15, 0.50
BED_TOP = 0.52
NB_X0, NB_X1 = 0.54, 1.06
NB_Y0, NB_Y1 = -2.12, -1.55
NB_TOP = 0.52


# ================================================================ mesh helpers
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


def box(name, center, size, mat, bevel=0.004, segs=2):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size[0]
        v.co.y *= size[1]
        v.co.z *= size[2]
    if bevel > 0:
        try:
            bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, offset_type='OFFSET',
                            segments=segs, profile=0.5, affect='EDGES', clamp_overlap=True)
        except Exception:
            pass
    bmesh.ops.translate(bm, vec=Vector(center), verts=bm.verts)
    return bm_to_obj(name, bm, mat, smooth=(bevel > 0))


def cyl(name, loc, r, h, mat, rot=(0, 0, 0), segs=24, r2=None, cap=True, smooth=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=cap, cap_tris=False, segments=segs,
                          radius1=r, radius2=(r if r2 is None else r2), depth=h)
    rm = Matrix.Rotation(rot[2], 3, 'Z') @ Matrix.Rotation(rot[1], 3, 'Y') @ Matrix.Rotation(rot[0], 3, 'X')
    bmesh.ops.transform(bm, matrix=rm.to_4x4(), verts=bm.verts)
    bmesh.ops.translate(bm, vec=Vector(loc), verts=bm.verts)
    return bm_to_obj(name, bm, mat, smooth=smooth)


def sphere(name, loc, r, mat, scale=(1, 1, 1), segs=28, rings=18):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segs, v_segments=rings, radius=r)
    for v in bm.verts:
        v.co.x *= scale[0]
        v.co.y *= scale[1]
        v.co.z *= scale[2]
    bmesh.ops.translate(bm, vec=Vector(loc), verts=bm.verts)
    return bm_to_obj(name, bm, mat, smooth=True)


def tube(name, pts, radius, mat, segs=8, smooth=True, cap=True):
    """Polyline tube with parallel-transport frames."""
    pts = [Vector(p) for p in pts]
    n = len(pts)
    bm = bmesh.new()
    up = Vector((0, 0, 1))
    prev_n = None
    rings = []
    for i, p in enumerate(pts):
        if i == 0:
            t = (pts[1] - pts[0]).normalized()
        elif i == n - 1:
            t = (pts[-1] - pts[-2]).normalized()
        else:
            t = (pts[i + 1] - pts[i - 1]).normalized()
        ref = up if abs(t.dot(up)) < 0.95 else Vector((1, 0, 0))
        nrm = (ref - t * ref.dot(t)).normalized()
        if prev_n is not None:
            nrm = (prev_n - t * prev_n.dot(t)).normalized()
        prev_n = nrm
        binorm = t.cross(nrm)
        ring = []
        for k in range(segs):
            a = 2 * math.pi * k / segs
            ring.append(bm.verts.new(p + nrm * (math.cos(a) * radius) + binorm * (math.sin(a) * radius)))
        rings.append(ring)
    for i in range(n - 1):
        a, b = rings[i], rings[i + 1]
        for k in range(segs):
            k2 = (k + 1) % segs
            try:
                bm.faces.new((a[k], a[k2], b[k2], b[k]))
            except ValueError:
                pass
    if cap:
        try:
            bm.faces.new(rings[0][::-1])
            bm.faces.new(rings[-1])
        except ValueError:
            pass
    return bm_to_obj(name, bm, mat, smooth=smooth)


# ================================================================ materials
def _nt(m):
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    return nt


def _out(nt):
    o = nt.nodes.new("ShaderNodeOutputMaterial")
    o.location = (700, 0)
    return o


def _bsdf(nt, loc=(300, 0)):
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.location = loc
    return b


def _set(b, key, val):
    if key in b.inputs:
        b.inputs[key].default_value = val


def mat_wall(name="B_wall", base=(0.105, 0.100, 0.135), stain=(0.078, 0.074, 0.100),
             rough=0.94, bump=0.09):
    m = lib._mat(name)
    nt = _nt(m)
    out = _out(nt)
    b = _bsdf(nt)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-1100, 0)
    # large scale damp stains / discolouration
    n1 = nt.nodes.new("ShaderNodeTexNoise"); n1.location = (-900, 200)
    n1.inputs["Scale"].default_value = 1.6
    n1.inputs["Detail"].default_value = 6.0
    n1.inputs["Roughness"].default_value = 0.58
    nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
    r1 = nt.nodes.new("ShaderNodeValToRGB"); r1.location = (-680, 200)
    r1.color_ramp.elements[0].position = 0.28
    r1.color_ramp.elements[0].color = (*stain, 1.0)
    r1.color_ramp.elements[1].position = 0.78
    r1.color_ramp.elements[1].color = (*base, 1.0)
    nt.links.new(n1.outputs["Fac"], r1.inputs["Fac"])
    nt.links.new(r1.outputs["Color"], b.inputs["Base Color"])
    # fine plaster grain bump + mid undulation (kept subtle: no moire tiling)
    # plaster relief: only LOW frequency, high-frequency noise causes moire on walls
    n2 = nt.nodes.new("ShaderNodeTexNoise"); n2.location = (-900, -220)
    n2.inputs["Scale"].default_value = 14.0
    n2.inputs["Detail"].default_value = 2.0
    n2.inputs["Roughness"].default_value = 0.5
    nt.links.new(tc.outputs["Object"], n2.inputs["Vector"])
    bp = nt.nodes.new("ShaderNodeBump"); bp.location = (-420, -260)
    bp.inputs["Strength"].default_value = bump * 0.55
    bp.inputs["Distance"].default_value = 0.035
    nt.links.new(n2.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    # roughness breakup
    rr = nt.nodes.new("ShaderNodeMapRange"); rr.location = (-420, -520)
    rr.inputs["From Min"].default_value = 0.0
    rr.inputs["From Max"].default_value = 1.0
    rr.inputs["To Min"].default_value = rough - 0.06
    rr.inputs["To Max"].default_value = min(1.0, rough + 0.05)
    nt.links.new(n1.outputs["Fac"], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
    return m


def mat_floor(name="B_floor", c1=(0.105, 0.082, 0.066), c2=(0.055, 0.042, 0.038),
              rough=0.55):
    m = lib._mat(name)
    nt = _nt(m)
    out = _out(nt)
    b = _bsdf(nt)
    b.location = (300, 0)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-1300, 0)
    mp = nt.nodes.new("ShaderNodeMapping"); mp.location = (-1120, 0)
    mp.inputs["Rotation"].default_value = (0, 0, math.radians(90))
    mp.inputs["Scale"].default_value = (1.0, 1.0, 1.0)
    nt.links.new(tc.outputs["Object"], mp.inputs["Vector"])
    brick = nt.nodes.new("ShaderNodeTexBrick"); brick.location = (-900, 120)
    brick.inputs["Scale"].default_value = 2.2
    brick.inputs["Mortar Size"].default_value = 0.004
    brick.inputs["Mortar Smooth"].default_value = 0.35
    brick.inputs["Bias"].default_value = 0.0
    brick.inputs["Brick Width"].default_value = 0.62
    brick.inputs["Row Height"].default_value = 0.085
    brick.inputs["Color1"].default_value = (*c1, 1.0)
    brick.inputs["Color2"].default_value = (*c2, 1.0)
    brick.inputs["Mortar"].default_value = (0.020, 0.016, 0.015, 1.0)
    nt.links.new(mp.outputs["Vector"], brick.inputs["Vector"])
    # dirt overlay
    n = nt.nodes.new("ShaderNodeTexNoise"); n.location = (-900, -240)
    n.inputs["Scale"].default_value = 9.0
    n.inputs["Detail"].default_value = 8.0
    nt.links.new(mp.outputs["Vector"], n.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMixRGB"); mix.location = (-600, 40)
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 0.45
    nt.links.new(brick.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(n.outputs["Color"], mix.inputs["Color2"])
    nt.links.new(mix.outputs["Color"], b.inputs["Base Color"])
    bp = nt.nodes.new("ShaderNodeBump"); bp.location = (-600, -240)
    bp.inputs["Strength"].default_value = 0.35
    bp.inputs["Distance"].default_value = 0.004
    nt.links.new(brick.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    rr = nt.nodes.new("ShaderNodeMapRange"); rr.location = (-600, -430)
    rr.inputs["To Min"].default_value = 0.30
    rr.inputs["To Max"].default_value = 0.72
    nt.links.new(n.outputs["Fac"], rr.inputs["Value"])
    nt.links.new(rr.outputs["Result"], b.inputs["Roughness"])
    _set(b, "Specular IOR Level", 0.45)
    return m


def mat_wood(name="B_wood", color=(0.070, 0.053, 0.040), rough=0.58, grain=11.0):
    m = lib._mat(name)
    nt = _nt(m)
    out = _out(nt)
    b = _bsdf(nt)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-900, 0)
    wave = nt.nodes.new("ShaderNodeTexWave"); wave.location = (-700, 100)
    wave.wave_type = 'BANDS'
    wave.bands_direction = 'Y'
    wave.inputs["Scale"].default_value = grain
    wave.inputs["Distortion"].default_value = 5.0
    wave.inputs["Detail"].default_value = 3.0
    wave.inputs["Detail Scale"].default_value = 2.0
    nt.links.new(tc.outputs["Object"], wave.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB"); ramp.location = (-480, 100)
    ramp.color_ramp.elements[0].color = (color[0] * 0.82, color[1] * 0.82, color[2] * 0.82, 1.0)
    ramp.color_ramp.elements[1].color = (color[0] * 1.18, color[1] * 1.16, color[2] * 1.14, 1.0)
    nt.links.new(wave.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", rough)
    bp = nt.nodes.new("ShaderNodeBump"); bp.location = (-230, -200)
    bp.inputs["Strength"].default_value = 0.05
    nt.links.new(wave.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_paint(name="B_paint_white", color=(0.30, 0.29, 0.27), rough=0.72):
    m = lib._mat(name)
    nt = _nt(m)
    out = _out(nt)
    b = _bsdf(nt)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    _set(b, "Base Color", (*color, 1.0))
    _set(b, "Roughness", rough)
    tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-800, 0)
    n = nt.nodes.new("ShaderNodeTexNoise"); n.location = (-620, -160)
    n.inputs["Scale"].default_value = 24.0
    n.inputs["Detail"].default_value = 8.0
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    bp = nt.nodes.new("ShaderNodeBump"); bp.location = (-400, -200)
    bp.inputs["Strength"].default_value = 0.12
    nt.links.new(n.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_fabric(name="B_fabric", color=(0.56, 0.58, 0.66), rough=0.88, sheen=0.5):
    m = lib._mat(name)
    nt = _nt(m)
    out = _out(nt)
    b = _bsdf(nt)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    _set(b, "Base Color", (*color, 1.0))
    _set(b, "Roughness", rough)
    _set(b, "Sheen Weight", sheen)
    _set(b, "Sheen Roughness", 0.5)
    tc = nt.nodes.new("ShaderNodeTexCoord"); tc.location = (-800, 0)
    n = nt.nodes.new("ShaderNodeTexNoise"); n.location = (-620, 160)
    n.inputs["Scale"].default_value = 240.0
    n.inputs["Detail"].default_value = 3.0
    nt.links.new(tc.outputs["Object"], n.inputs["Vector"])
    bp = nt.nodes.new("ShaderNodeBump"); bp.location = (-400, -120)
    bp.inputs["Strength"].default_value = 0.10
    nt.links.new(n.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


def mat_metal(name="B_metal", color=(0.30, 0.30, 0.33), rough=0.38):
    m = lib._mat(name)
    nt = _nt(m)
    out = _out(nt)
    b = _bsdf(nt)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    _set(b, "Base Color", (*color, 1.0))
    _set(b, "Roughness", rough)
    _set(b, "Metallic", 1.0)
    return m


def mat_glass(name="B_glass", tint=(0.85, 0.90, 1.0), alpha=0.10, rough=0.04,
              transmission=0.0, ior=1.45, refraction=False):
    m = lib._mat(name)
    nt = _nt(m)
    out = _out(nt)
    b = _bsdf(nt)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    _set(b, "Base Color", (*tint, 1.0))
    _set(b, "Roughness", rough)
    _set(b, "IOR", ior)
    _set(b, "Transmission Weight", transmission)
    _set(b, "Alpha", alpha)
    _set(b, "Specular IOR Level", 0.6)
    try:
        m.surface_render_method = 'DITHERED'
    except Exception:
        pass
    if refraction:
        try:
            m.use_raytrace_refraction = True
        except Exception:
            pass
    return m


def mat_water(name="B_water", tint=(0.90, 0.95, 1.0), rough=0.03, alpha=0.85):
    m = lib._mat(name)
    nt = _nt(m)
    out = _out(nt)
    b = _bsdf(nt)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    _set(b, "Base Color", (*tint, 1.0))
    _set(b, "Roughness", rough)
    _set(b, "IOR", 1.33)
    _set(b, "Transmission Weight", 0.85)
    _set(b, "Alpha", alpha)
    try:
        m.surface_render_method = 'DITHERED'
        m.use_raytrace_refraction = True
    except Exception:
        pass
    return m


def mat_emissive(name, color, strength=1.0):
    return lib.emission(name, color, strength)


# ================================================================ room shell

def center_object(ob, name=None):
    """Move the mesh centroid to the origin and store it in ob.location."""
    me = ob.data
    if not me.vertices:
        return ob
    c = Vector((0, 0, 0))
    for v in me.vertices:
        c += v.co
    c /= len(me.vertices)
    for v in me.vertices:
        v.co -= c
    ob.location = ob.location + c
    return ob


def build_shell(M):
    """Floor, ceiling and the four walls with a window opening at +Y."""
    quad("floor", [(RX0, RY0, 0), (RX1, RY0, 0), (RX1, RY1, 0), (RX0, RY1, 0)], M["floor"])
    quad("ceil", [(RX0, RY0, RZ1), (RX0, RY1, RZ1), (RX1, RY1, RZ1), (RX1, RY0, RZ1)], M["wall"])
    # +Y wall (window): four panels around the opening, normals toward -Y
    def yq(name, x0, x1, z0, z1):
        quad(name, [(x0, RY1, z0), (x1, RY1, z0), (x1, RY1, z1), (x0, RY1, z1)], M["wall"])
    yq("wall_win_below", RX0, RX1, 0.0, WIN_Z0)
    yq("wall_win_above", RX0, RX1, WIN_Z1, RZ1)
    yq("wall_win_left", RX0, WIN_X0, WIN_Z0, WIN_Z1)
    yq("wall_win_right", WIN_X1, RX1, WIN_Z0, WIN_Z1)
    # -Y wall (head of bed / clock), normals +Y
    quad("wall_south", [(RX0, RY0, 0), (RX0, RY0, RZ1), (RX1, RY0, RZ1), (RX1, RY0, 0)], M["wall"])
    # -X wall, normals +X
    quad("wall_west", [(RX0, RY0, 0), (RX0, RY1, 0), (RX0, RY1, RZ1), (RX0, RY0, RZ1)], M["wall"])
    # +X wall, normals -X
    quad("wall_east", [(RX1, RY0, 0), (RX1, RY0, RZ1), (RX1, RY1, RZ1), (RX1, RY1, 0)], M["wall"])
    # skirting boards
    for nm, c, s in (
        ("skirt_s", (0.0, RY0 + 0.02, 0.06), (5.6, 0.04, 0.12)),
        ("skirt_e", (RX1 - 0.02, 0.0, 0.06), (0.04, 4.4, 0.12)),
        ("skirt_w", (RX0 + 0.02, 0.0, 0.06), (0.04, 4.4, 0.12)),
        ("skirt_n1", (-2.0, RY1 - 0.02, 0.06), (1.6, 0.04, 0.12)),
        ("skirt_n2", (2.0, RY1 - 0.02, 0.06), (1.6, 0.04, 0.12)),
    ):
        box(nm, c, s, M["wood"], bevel=0.003)
    # simple cornice line
    for nm, c, s in (
        ("corn_n", (0.0, RY1 - 0.03, RZ1 - 0.045), (5.6, 0.06, 0.09)),
        ("corn_s", (0.0, RY0 + 0.03, RZ1 - 0.045), (5.6, 0.06, 0.09)),
    ):
        box(nm, c, s, M["paint"], bevel=0.002)


def build_window(M):
    """Frame, mullions, sill, glass and rain droplets on the inner face."""
    fy = RY1 - 0.035
    # outer frame
    box("win_frame_b", (0.0, fy, WIN_Z0 - 0.035), (2.56, 0.10, 0.08), M["paint"], bevel=0.006)
    box("win_frame_t", (0.0, fy, WIN_Z1 + 0.035), (2.56, 0.10, 0.08), M["paint"], bevel=0.006)
    box("win_frame_l", (WIN_X0 - 0.035, fy, (WIN_Z0 + WIN_Z1) / 2), (0.08, 0.10, WIN_Z1 - WIN_Z0 + 0.16), M["paint"], bevel=0.006)
    box("win_frame_r", (WIN_X1 + 0.035, fy, (WIN_Z0 + WIN_Z1) / 2), (0.08, 0.10, WIN_Z1 - WIN_Z0 + 0.16), M["paint"], bevel=0.006)
    # mullions: one vertical in the middle, two horizontal
    box("win_mull_v", (0.0, fy, (WIN_Z0 + WIN_Z1) / 2), (0.045, 0.055, WIN_Z1 - WIN_Z0), M["paint"], bevel=0.004)
    box("win_mull_h1", (0.0, fy, WIN_Z0 + (WIN_Z1 - WIN_Z0) * 0.42), (WIN_X1 - WIN_X0, 0.055, 0.04), M["paint"], bevel=0.004)
    box("win_mull_h2", (0.0, fy, WIN_Z0 + (WIN_Z1 - WIN_Z0) * 0.74), (WIN_X1 - WIN_X0, 0.055, 0.035), M["paint"], bevel=0.004)
    # sill
    box("win_sill", (0.0, RY1 - 0.10, WIN_Z0 - 0.022), (2.62, 0.26, 0.045), M["paint"], bevel=0.004)
    # glass plane
    g = quad("win_glass", [(WIN_X0, RY1 - 0.055, WIN_Z0), (WIN_X1, RY1 - 0.055, WIN_Z0),
                           (WIN_X1, RY1 - 0.055, WIN_Z1), (WIN_X0, RY1 - 0.055, WIN_Z1)],
             M["glass"], smooth=True)
    return g


def build_rain_on_glass(M, count=210, seed=5, y=RY1 - 0.062, drop_scale=1.0):
    """All droplets merged into one mesh: flattened spheres on the glass."""
    rng = random.Random(seed)
    bm = bmesh.new()
    for i in range(count):
        x = rng.uniform(WIN_X0 + 0.03, WIN_X1 - 0.03)
        z = rng.uniform(WIN_Z0 + 0.03, WIN_Z1 - 0.03)
        r = rng.uniform(0.0022, 0.0095) * drop_scale
        if rng.random() < 0.12:
            r *= 1.9
        sz = rng.uniform(0.25, 0.5)
        tilt = rng.uniform(-0.25, 0.25)
        sx = rng.uniform(0.8, 1.25)
        mat4 = (Matrix.Translation((x, y - 0.002 - rng.uniform(0, 0.0015), z)) @
                Matrix.Rotation(tilt, 4, 'X') @
                Matrix.Diagonal((1.0, sz, sx, 1.0)))
        bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=r, matrix=mat4)
    ob = bm_to_obj("rain_drops_glass", bm, M["drop"], smooth=True)
    return ob


def build_curtain(M, side="L"):
    """Vertically hung cloth with sine folds; gets a shape key for the wind."""
    if side == "L":
        x0, x1 = WIN_X0 - 0.40, WIN_X0 + 0.02
    else:
        x0, x1 = WIN_X1 - 0.02, WIN_X1 + 0.40
    z0, z1 = 0.03, RZ1 - 0.10
    y0 = RY1 - 0.16
    nx, nz = 10, 22
    verts, faces = [], []
    rng = random.Random(3 if side == "L" else 4)
    ph = rng.uniform(0, 6)
    for j in range(nz + 1):
        tz = j / nz
        for i in range(nx + 1):
            tx = i / nx
            xx = x0 + (x1 - x0) * tx
            zz = z0 + (z1 - z0) * tz
            fold = (0.105 * math.sin(tx * math.pi * 3.2 + ph) * (0.35 + 0.65 * tz)
                    + 0.030 * math.sin(tx * math.pi * 7.0 - ph * 0.7) * (0.25 + 0.75 * tz)
                    + 0.018 * math.sin(tz * 9.0 + tx * 4.0 + ph))
            yy = y0 + fold + 0.02 * math.sin(ph + tz * 3.0)
            verts.append((xx, yy, zz))
    for j in range(nz):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    me = bpy.data.meshes.new("curtain_" + side)
    me.from_pydata(verts, [], faces)
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new("curtain_" + side, me)
    _link(ob, M["curtain"])
    # shape key for the night wind
    ob.shape_key_add(name="Basis", from_mix=False)
    sk = ob.shape_key_add(name="Blow", from_mix=False)
    for j in range(nz + 1):
        tz = j / nz
        for i in range(nx + 1):
            tx = i / nx
            idx = j * (nx + 1) + i
            base = Vector(verts[idx])
            amp = 0.24 * (tz ** 0.8) * (0.4 + 0.6 * math.sin(tx * math.pi * 1.2 + ph))
            drift = 0.055 * math.sin(tx * math.pi * 2.2 + tz * 2.0 + ph) * tz
            sk.data[idx].co = (base.x + 0.03 * tz, base.y + amp * 0.9, base.z)
    return ob


def build_curtain_rod(M):
    cyl("curtain_rod", (0.0, RY1 - 0.16, RZ1 - 0.075), 0.016, 3.3, M["metal"],
        rot=(0, math.pi / 2, 0), segs=14)
    for x in (-1.63, 1.63):
        cyl("rod_end_%s" % ("l" if x < 0 else "r"), (x, RY1 - 0.16, RZ1 - 0.075), 0.026, 0.03,
            M["metal"], rot=(0, math.pi / 2, 0), segs=14)


# ================================================================ furniture
def build_desk(M):
    # top
    box("desk_top", ((DESK_X0 + DESK_X1) / 2, (DESK_Y0 + DESK_Y1) / 2, DESK_Z - 0.02),
        (DESK_X1 - DESK_X0, DESK_Y1 - DESK_Y0, 0.04), M["wood_desk"], bevel=0.006)
    # aprons
    for nm, c, s in (
        ("desk_apron_f", ((DESK_X0 + DESK_X1) / 2, DESK_Y0 + 0.03, DESK_Z - 0.075), (DESK_X1 - DESK_X0, 0.035, 0.07)),
        ("desk_apron_b", ((DESK_X0 + DESK_X1) / 2, DESK_Y1 - 0.03, DESK_Z - 0.075), (DESK_X1 - DESK_X0, 0.035, 0.07)),
    ):
        box(nm, c, s, M["wood"], bevel=0.003)
    # legs
    for x in (DESK_X0 + 0.06, DESK_X1 - 0.06):
        for y in (DESK_Y0 + 0.06, DESK_Y1 - 0.06):
            box("desk_leg", (x, y, (DESK_Z - 0.04) / 2), (0.055, 0.055, DESK_Z - 0.04),
                M["wood"], bevel=0.004)
    # small drawer block on the right
    box("desk_drawer", (DESK_X1 - 0.22, DESK_Y1 - 0.35, 0.50), (0.40, 0.55, 0.42), M["wood"], bevel=0.006)
    box("desk_handle", (DESK_X1 - 0.22, DESK_Y1 - 0.35 + 0.28, 0.58), (0.10, 0.02, 0.015), M["metal"], bevel=0.003)


def build_paper_and_flower(M, seed=11):
    """Sheet of paper on the desk + dried purple sunflower lying on it."""
    rng = random.Random(seed)
    # paper: subdivided plane with slight curl
    nx, ny = 14, 10
    w, h = 0.30, 0.42
    cx, cy = -1.62, 1.86
    verts, faces = [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            tx, ty = i / nx, j / ny
            x = cx - w / 2 + w * tx
            y = cy - h / 2 + h * ty
            edge = min(tx, 1 - tx, ty, 1 - ty)
            curl = 0.012 * (1.0 - min(1.0, edge * 5.0)) + 0.004 * math.sin(tx * 6 + ty * 4)
            z = DESK_Z + 0.001 + curl
            verts.append((x, y, z))
            if i and j:
                a = (j - 1) * (nx + 1) + (i - 1)
                faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    me = bpy.data.meshes.new("paper")
    me.from_pydata(verts, [], faces)
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new("paper", me)
    _link(ob, M["paper"])
    return ob


def build_dried_sunflower(M, loc=(-1.55, 1.86, DESK_Z + 0.006), seed=5):
    """Wilted violet sunflower lying on the paper (lib sunflower, dead palette)."""
    sf = lib.sunflower("dried_sunflower", size=0.62, n_petals=21, petal_len=0.062,
                       stem_len=0.105, head_tilt=34, pose_seed=seed, stem_thickness=0.005,
                       leaf=False,
                       mats=(M["petal_dry"], M["disc_dry"], M["stem_dry"]),
                       head_azim=-0.4)
    sf.location = (loc[0], loc[1], loc[2] + 0.004)
    sf.rotation_euler = (math.radians(22), math.radians(-4), math.radians(26))
    # bent stem trailing across the paper
    pts = [Vector((loc[0] - 0.01, loc[1] + 0.02, loc[2] + 0.035)),
           Vector((loc[0] + 0.06, loc[1] - 0.06, loc[2] + 0.020)),
           Vector((loc[0] + 0.13, loc[1] - 0.16, loc[2] + 0.010)),
           Vector((loc[0] + 0.18, loc[1] - 0.26, loc[2] + 0.006))]
    tube("dried_stem", pts, 0.0038, M["stem_dry"], segs=7)
    # two fallen petals on the paper
    for k, (px, py, ang) in enumerate(((-1.30, 1.74, 40), (-1.70, 1.62, -25))):
        bm = bmesh.new()
        uv_layer = bm.loops.layers.uv.new("UVMap")
        rot = (Matrix.Rotation(math.radians(ang), 3, 'Z') @
               Matrix.Rotation(math.radians(88), 3, 'X'))
        lib._add_petal(bm, rot, 0.062, 0.021, 0.05, 4, 0, uv_layer)
        bmesh.ops.translate(bm, vec=Vector((px, py, DESK_Z + 0.004)), verts=bm.verts)
        bm_to_obj("fallen_petal_%d" % k, bm, M["petal_dry"], smooth=True)
    return sf


def build_chair(M):
    cx, cy = -2.52, 1.62
    box("chair_seat", (cx, cy, 0.45), (0.42, 0.42, 0.035), M["wood"], bevel=0.008)
    for x in (cx - 0.17, cx + 0.17):
        for y in (cy - 0.17, cy + 0.17):
            box("chair_leg", (x, y, 0.22), (0.032, 0.032, 0.44), M["wood"], bevel=0.003)
    box("chair_back", (cx, cy - 0.19, 0.72), (0.42, 0.03, 0.42), M["wood"], bevel=0.008)
    # cloth thrown over the back
    box("chair_cloth", (cx + 0.02, cy - 0.21, 0.66), (0.34, 0.04, 0.26), M["fabric"], bevel=0.02)


def build_bed(M):
    # frame
    box("bed_frame", ((BED_X0 + BED_X1) / 2, (BED_Y0 + BED_Y1) / 2, 0.16),
        (BED_X1 - BED_X0, BED_Y1 - BED_Y0, 0.32), M["wood_dark"], bevel=0.01)
    # mattress
    box("mattress", ((BED_X0 + BED_X1) / 2, (BED_Y0 + BED_Y1) / 2, 0.42),
        (BED_X1 - BED_X0 - 0.10, BED_Y1 - BED_Y0 - 0.10, 0.20), M["sheet"], bevel=0.03)
    # headboard at -Y
    box("headboard", ((BED_X0 + BED_X1) / 2, BED_Y0 + 0.02, 0.62),
        (BED_X1 - BED_X0, 0.06, 0.62), M["wood_dark"], bevel=0.012)
    # duvet: dense displaced grid, draped over the sides, hollow where a body lay
    nx, ny = 56, 50
    x0, x1 = BED_X0 - 0.05, BED_X1 + 0.05
    y0, y1 = BED_Y0 + 0.30, BED_Y1 + 0.04
    verts, faces = [], []
    for j in range(ny + 1):
        ty = j / ny
        for i in range(nx + 1):
            tx = i / nx
            x = x0 + (x1 - x0) * tx
            y = y0 + (y1 - y0) * ty
            # drape: horizontal overhang past the mattress edge pulls z down
            ex = max(0.0, (BED_X0 + 0.07) - x, x - (BED_X1 - 0.07))
            ey = max(0.0, y - (BED_Y1 - 0.07))
            dsx = min(1.0, ex / 0.12)
            dsy = min(1.0, ey / 0.12)
            drap = 0.30 * (dsx * dsx * (3 - 2 * dsx)) + 0.22 * (dsy * dsy * (3 - 2 * dsy))
            z = 0.575 - drap
            # multi-scale cloth wrinkles
            fold = (math.sin(tx * 26.0 + ty * 4.0 + 0.6) * 0.014 +
                    math.sin(ty * 33.0 + tx * 2.0 + 2.1) * 0.010 +
                    math.sin((tx + ty) * 47.0 + 1.3) * 0.005 +
                    math.sin(tx * 9.0 - ty * 15.0) * 0.008)
            # body hollow (someone just left)
            dx = (tx - 0.44) * 1.55
            dy = (ty - 0.42) * 1.05
            hollow = -0.045 * math.exp(-(dx * dx + dy * dy) * 4.0)
            # secondary dip (legs)
            dx2 = (tx - 0.55) * 2.4
            dy2 = (ty - 0.62) * 2.0
            hollow += -0.020 * math.exp(-(dx2 * dx2 + dy2 * dy2) * 5.0)
            verts.append((x, y, z + fold + hollow))
            if i and j:
                a = (j - 1) * (nx + 1) + (i - 1)
                faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    me = bpy.data.meshes.new("duvet")
    me.from_pydata(verts, [], faces)
    me.update()
    for p in me.polygons:
        p.use_smooth = True
    ob = bpy.data.objects.new("duvet", me)
    _link(ob, M["duvet"])
    # two pillows: soft boxes with wrinkled surface
    for k, (px, py) in enumerate(((BED_X0 + 0.40, BED_Y0 + 0.26),
                                  (BED_X1 - 0.40, BED_Y0 + 0.27))):
        rngp = random.Random(30 + k)
        pnx, pny = 18, 14
        pw, pd, ph = 0.46, 0.32, 0.125
        pv, pf = [], []
        for jj in range(pny + 1):
            v = jj / pny
            for ii in range(pnx + 1):
                u = ii / pnx
                sx = (u - 0.5) * 2.0
                sy = (v - 0.5) * 2.0
                dome = 0.5 * (1 - sx * sx) * (1 - sy * sy)
                zz = ph * dome * 0.75
                wr = 0.008 * math.sin(u * 21 + v * 9) + 0.005 * math.sin(v * 27 + u * 5)
                pv.append((px + sx * pw / 2, py + sy * pd / 2, BED_TOP + 0.09 + zz + wr +
                           0.004 * math.sin(u * 60 + v * 40)))
                if ii and jj:
                    a = (jj - 1) * (pnx + 1) + (ii - 1)
                    pf.append((a, a + 1, a + pnx + 2, a + pnx + 1))
        # skirt down to the mattress
        me = bpy.data.meshes.new("pillow_%d" % k)
        me.from_pydata(pv, [], pf)
        me.update()
        for p in me.polygons:
            p.use_smooth = True
        ob = bpy.data.objects.new("pillow_%d" % k, me)
        _link(ob, M["duvet"])
    return ob


def build_nightstand(M):
    box("nb_body", ((NB_X0 + NB_X1) / 2, (NB_Y0 + NB_Y1) / 2, NB_TOP / 2),
        (NB_X1 - NB_X0, NB_Y1 - NB_Y0, NB_TOP), M["wood_dark"], bevel=0.006)
    box("nb_top", ((NB_X0 + NB_X1) / 2, (NB_Y0 + NB_Y1) / 2, NB_TOP + 0.012),
        (NB_X1 - NB_X0 + 0.04, NB_Y1 - NB_Y0 + 0.04, 0.025), M["wood"], bevel=0.004)
    box("nb_drawer", ((NB_X0 + NB_X1) / 2, NB_Y1 + 0.002, 0.36),
        (NB_X1 - NB_X0 - 0.08, 0.02, 0.14), M["wood"], bevel=0.003)
    box("nb_handle", ((NB_X0 + NB_X1) / 2, NB_Y1 + 0.016, 0.36), (0.07, 0.015, 0.012), M["metal"], bevel=0.002)


def build_lamp(M):
    """Warm bedside lamp: base, stem, fabric shade (emissive inside)."""
    bx, by = 0.80, -1.84
    z0 = NB_TOP + 0.028
    cyl("lamp_base", (bx, by, z0 + 0.012), 0.085, 0.024, M["metal"], segs=32)
    cyl("lamp_stem", (bx, by, z0 + 0.20), 0.011, 0.36, M["metal"], segs=12)
    # shade: cone shell, wide at the bottom
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, cap_tris=False, segments=32,
                          radius1=0.160, radius2=0.085, depth=0.21)
    bmesh.ops.translate(bm, vec=Vector((bx, by, z0 + 0.44)), verts=bm.verts)
    shade = bm_to_obj("lamp_shade", bm, M["shade"], smooth=True)
    shade.visible_shadow = False          # fabric shade lets light through
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=32,
                          radius1=0.157, radius2=0.082, depth=0.208)
    bmesh.ops.translate(bm, vec=Vector((bx, by, z0 + 0.44)), verts=bm.verts)
    shade_in = bm_to_obj("lamp_shade_in", bm, M["shade_glow"], smooth=True)
    shade_in.visible_shadow = False
    # inner bulb glow
    sphere("lamp_bulb", (bx, by, z0 + 0.42), 0.032, M["bulb"], segs=16, rings=10)
    # switch on the base
    box("lamp_switch", (bx + 0.10, by + 0.05, z0 + 0.02), (0.02, 0.02, 0.015), M["metal"], bevel=0.002)
    return shade


def build_clock(M):
    """Wall clock on the -Y wall above the nightstand: 2 AM."""
    cx, cz = 1.72, 1.62
    cy = RY0 + 0.045
    cyl("clock_rim", (cx, cy, cz), 0.165, 0.035, M["wood"], rot=(math.pi / 2, 0, 0), segs=40)
    cyl("clock_face", (cx, cy + 0.018, cz), 0.148, 0.004, M["clockface"], rot=(math.pi / 2, 0, 0), segs=40)
    # hour marks
    for i in range(12):
        a = 2 * math.pi * i / 12
        r = 0.128
        box("clock_tick", (cx + math.sin(a) * r, cy + 0.023, cz + math.cos(a) * r),
            (0.008, 0.003, 0.020 if i % 3 == 0 else 0.012), M["metal"], bevel=0.001)
    # hands: 2:00
    import math as _m
    hx = cx + 0.0
    # hour hand pointing to 2 o'clock (60 deg from 12)
    hb = bmesh.new()
    bmesh.ops.create_cube(hb, size=1.0)
    for v in hb.verts:
        v.co.x *= 0.012
        v.co.y *= 0.008
        v.co.z *= 0.078
    bmesh.ops.translate(hb, vec=Vector((0, 0, 0.039)), verts=hb.verts)
    bmesh.ops.rotate(hb, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(60), 3, 'Y'), verts=hb.verts)
    bmesh.ops.translate(hb, vec=Vector((hx, cy + 0.03, cz)), verts=hb.verts)
    bm_to_obj("clock_hour", hb, M["metal"], smooth=False)
    mb = bmesh.new()
    bmesh.ops.create_cube(mb, size=1.0)
    for v in mb.verts:
        v.co.x *= 0.008
        v.co.y *= 0.007
        v.co.z *= 0.112
    bmesh.ops.translate(mb, vec=Vector((0, 0, 0.056)), verts=mb.verts)
    bmesh.ops.rotate(mb, cent=(0, 0, 0), matrix=Matrix.Rotation(0.0, 3, 'Y'), verts=mb.verts)
    bmesh.ops.translate(mb, vec=Vector((hx, cy + 0.034, cz)), verts=mb.verts)
    bm_to_obj("clock_min", mb, M["metal"], smooth=False)
    cyl("clock_pin", (cx, cy + 0.04, cz), 0.008, 0.01, M["metal"], rot=(math.pi / 2, 0, 0), segs=12)


def build_glass_ice(M, loc=(0.80, -1.62, NB_TOP + 0.04), scale=1.0, water_level=0.55, ices=3, seed=3):
    """Tumbler glass with ice cubes + water. Returns dict of objects for animation."""
    rng = random.Random(seed)
    r, h = 0.043 * scale, 0.115 * scale
    x, y, z = loc
    # outer wall
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, cap_tris=False, segments=32, radius1=r, radius2=r * 1.03, depth=h)
    bmesh.ops.translate(bm, vec=Vector((x, y, z + h / 2)), verts=bm.verts)
    glass_out = bm_to_obj("glass_out", bm, M["glass_cup"], smooth=True)
    # bottom
    cyl("glass_bottom", (x, y, z + 0.006 * scale), r * 1.01, 0.012 * scale, M["glass_cup"], segs=32)
    # water body
    wh = h * water_level
    water = cyl("water", (x, y, z + wh / 2), r * 0.955, wh, M["water"], segs=32)
    # ice cubes
    cubes = []
    for i in range(ices):
        s = rng.uniform(0.30, 0.42) * scale * r * 2.0 / 2.0
        cx = x + rng.uniform(-r * 0.35, r * 0.35)
        cy = y + rng.uniform(-r * 0.35, r * 0.35)
        cz = z + rng.uniform(0.35, 0.85) * h
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= s
            v.co.y *= s
            v.co.z *= s * 0.85
            v.co.x += rng.uniform(-s * 0.10, s * 0.10)
            v.co.y += rng.uniform(-s * 0.10, s * 0.10)
        try:
            bmesh.ops.bevel(bm, geom=list(bm.edges), offset=s * 0.10, offset_type='OFFSET',
                            segments=2, profile=0.6, affect='EDGES', clamp_overlap=True)
        except Exception:
            pass
        rot = (rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), rng.uniform(0, 6.28))
        rm = Matrix.Rotation(rot[2], 4, 'Z') @ Matrix.Rotation(rot[1], 4, 'Y') @ Matrix.Rotation(rot[0], 4, 'X')
        bmesh.ops.transform(bm, matrix=rm, verts=bm.verts)
        bmesh.ops.translate(bm, vec=Vector((cx, cy, cz)), verts=bm.verts)
        cubes.append(center_object(bm_to_obj("ice_%d" % i, bm, M["ice"], smooth=True)))
    return dict(glass=glass_out, water=water, ice=cubes, top=z + h, r=r)


def build_icecream_cup(M, loc=(0.80, -1.62, NB_TOP + 0.03), seed=7):
    """Glass cup with melting ice cream + spoon (S35)."""
    rng = random.Random(seed)
    x, y, z = loc
    r, h = 0.052, 0.085
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=False, cap_tris=False, segments=32, radius1=r, radius2=r * 1.12, depth=h)
    bmesh.ops.translate(bm, vec=Vector((x, y, z + h / 2)), verts=bm.verts)
    bm_to_obj("icecup", bm, M["glass_cup"], smooth=True)
    cyl("icecup_bottom", (x, y, z + 0.006), r * 1.01, 0.012, M["glass_cup"], segs=32)
    # ice cream: two blobs, the upper one sliding down
    blob1 = center_object(sphere("cream_1", (x, y, z + h + 0.008), 0.046, M["cream"], scale=(1.0, 1.0, 0.72), segs=28, rings=18))
    blob2 = center_object(sphere("cream_2", (x + 0.012, y - 0.014, z + h + 0.030), 0.030, M["cream"], scale=(1.0, 1.0, 0.78), segs=24, rings=16))
    # melted pool ring on the saucer
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=28, radius1=0.058, radius2=0.052, depth=0.006)
    bmesh.ops.translate(bm, vec=Vector((x, y, z + 0.003)), verts=bm.verts)
    bm_to_obj("cream_pool", bm, M["cream_liquid"], smooth=True)
    # saucer
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=32, radius1=0.105, radius2=0.088, depth=0.012)
    bmesh.ops.translate(bm, vec=Vector((x, y, z - 0.008)), verts=bm.verts)
    bm_to_obj("saucer", bm, M["paint"], smooth=True)
    # spoon leaning in the cup
    pts = [Vector((x + 0.028, y + 0.004, z + h + 0.045)),
           Vector((x + 0.075, y + 0.02, z + h - 0.01)),
           Vector((x + 0.115, y + 0.05, z + 0.012))]
    tube("spoon_handle", pts, 0.0045, M["metal"], segs=8)
    sphere("spoon_bowl", (x + 0.028, y + 0.004, z + h + 0.045), 0.011, M["metal"], scale=(1.0, 1.6, 0.5), segs=16, rings=10)
    return dict(cream1=blob1, cream2=blob2)


def build_wall_art(M):
    # a small faded print above the bed
    box("art_frame", (0.52, RY0 + 0.03, 1.68), (0.48, 0.03, 0.36), M["wood_dark"], bevel=0.004)
    box("art_paper", (0.52, RY0 + 0.048, 1.68), (0.40, 0.004, 0.28), M["art_print"], bevel=0.001)
    # a second, smaller frame on the +X wall
    box("art2_frame", (RX1 - 0.03, 0.85, 1.48), (0.03, 0.34, 0.44), M["wood_dark"], bevel=0.004)
    box("art2_paper", (RX1 - 0.048, 0.85, 1.48), (0.004, 0.28, 0.38), M["art_print"], bevel=0.001)


def build_potted_sunflower(M, loc=(0.98, 2.06, 0.955), seed=13, size=0.34):
    """Small violet sunflower in a terracotta pot on the windowsill (S38)."""
    x, y, z = loc
    # pot
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=24, radius1=0.062, radius2=0.082, depth=0.13)
    bmesh.ops.translate(bm, vec=Vector((x, y, z + 0.065)), verts=bm.verts)
    bm_to_obj("pot", bm, M["terracotta"], smooth=True)
    cyl("pot_soil", (x, y, z + 0.128), 0.074, 0.012, M["soil"], segs=24)
    # sunflower
    sf = lib.sunflower("window_sunflower", size=size, n_petals=20, petal_len=0.10,
                       stem_len=0.78, head_tilt=26, pose_seed=seed, leaf=True,
                       mats=(M["petal_violet"], M["disc_dark"], M["stem"]), head_azim=0.15)
    sf.location = (x, y, z + 0.13)
    sf.rotation_euler = (0, 0, math.radians(-24))
    return sf


def build_dust(M, region=(-2.1, -0.2, 1.25, 2.18, 0.82, 1.70), count=34, seed=17):
    """Slow drifting dust motes in the window light (S02)."""
    rng = random.Random(seed)
    x0, x1, y0, y1, z0, z1 = region
    obs = []
    for i in range(count):
        p = (rng.uniform(x0, x1), rng.uniform(y0, y1), rng.uniform(z0, z1))
        r = rng.uniform(0.0018, 0.0045)
        ob = sphere("dust_%02d" % i, p, r, M["dust"], segs=8, rings=6)
        obs.append(ob)
    return obs


def build_city(M, dist=30.0, seed=8):
    """Night city outside the window: dark towers, lit windows, neon and a street light."""
    rng = random.Random(seed)
    objs = []
    # towers
    for i in range(26):
        w = rng.uniform(4.0, 11.0)
        h = rng.uniform(5.0, 19.0)
        x = rng.uniform(-55, 55)
        yy = dist + rng.uniform(0, 45)
        box("city_tower_%02d" % i, (x, yy, h / 2), (w, w * rng.uniform(0.7, 1.4), h),
            M["tower"], bevel=0.02)
    # lit windows: merged quads with 3 emissive materials
    bm = bmesh.new()
    emats = [M["win_warm"], M["win_cool"], M["win_violet"]]
    for i in range(560):
        x = rng.uniform(-50, 50)
        yy = dist + rng.uniform(0, 42)
        z = rng.uniform(1.2, 17.0)
        w = rng.uniform(0.18, 0.5)
        h = rng.uniform(0.16, 0.36)
        vs = [bm.verts.new((x - w / 2, yy - 0.01, z + h / 2)),
              bm.verts.new((x + w / 2, yy - 0.01, z + h / 2)),
              bm.verts.new((x + w / 2, yy - 0.01, z - h / 2)),
              bm.verts.new((x - w / 2, yy - 0.01, z - h / 2))]
        f = bm.faces.new(vs)
        f.material_index = rng.choices([0, 1, 2], weights=[0.55, 0.32, 0.13])[0]
    bm_to_obj("city_windows", bm, emats, smooth=False)
    # neon signs (abstract bars / tubes, no text)
    for i in range(14):
        x = rng.uniform(-26, 26)
        yy = dist + rng.uniform(-8, 12)
        z = rng.uniform(2.5, 16.0)
        col = rng.choice([(1.0, 0.25, 0.55), (0.55, 0.45, 1.0), (0.25, 0.85, 1.0),
                          (1.0, 0.55, 0.2), (0.9, 0.9, 1.0)])
        w = rng.uniform(0.6, 2.4)
        h = rng.uniform(0.10, 0.22)
        box("neon_%02d" % i, (x, yy, z), (w, 0.05, h),
            lib.emission("neon_%d" % i, col, rng.uniform(2.5, 6.0)), bevel=0.01)
        # vertical companion tube
        box("neonv_%02d" % i, (x - w / 2 - 0.12, yy, z), (0.05, 0.05, rng.uniform(0.8, 2.2)),
            lib.emission("neonv_%d" % i, col, rng.uniform(2.0, 5.0)), bevel=0.008)
    # bokeh points close outside the window (read as big city bokeh blobs)
    bm = bmesh.new()
    emats = [M["win_warm"], M["win_cool"], M["win_violet"]]
    for i in range(90):
        x = rng.uniform(-9.0, 9.0)
        yy = rng.uniform(5.5, 16.0)
        z = rng.uniform(0.6, 9.0)
        w = rng.uniform(0.10, 0.42)
        h = rng.uniform(0.10, 0.42)
        vs = [bm.verts.new((x - w / 2, yy, z + h / 2)),
              bm.verts.new((x + w / 2, yy, z + h / 2)),
              bm.verts.new((x + w / 2, yy, z - h / 2)),
              bm.verts.new((x - w / 2, yy, z - h / 2))]
        f = bm.faces.new(vs)
        f.material_index = rng.choices([0, 1, 2], weights=[0.42, 0.36, 0.22])[0]
    bm_to_obj("city_bokeh", bm, emats, smooth=False)
    # street light near the window (for bokeh in S01/S25)
    for i, (x, yy) in enumerate(((-3.2, 9.0), (2.6, 8.0), (5.5, 11.0))):
        cyl("street_pole_%d" % i, (x, yy, 2.4), 0.055, 4.8, M["tower"], segs=10)
        cyl("street_arm_%d" % i, (x + 0.6, yy, 4.75), 0.035, 1.2, M["tower"],
            rot=(0, math.pi / 2, 0), segs=10)
        sphere("street_bulb_%d" % i, (x + 1.15, yy, 4.7), 0.10,
               lib.emission("street_glow_%d" % i, (1.0, 0.72, 0.38), 9.0), segs=14, rings=10)
        # light pool
        lib.point_light("street_light_%d" % i, (x + 1.15, yy, 4.6), energy=90, radius=0.5,
                        color=(1.0, 0.70, 0.38))
    return objs


def build_sky_night(M):
    rng = random.Random(12)
    # horizon light pollution band
    quad("sky_city_glow", [(-120, 90, 0), (120, 90, 0), (120, 90, 6), (-120, 90, 6)],
         lib.gradient_mat("B_city_glow", (0.030, 0.022, 0.052), (0.0, 0.0, 0.0), strength=0.35))
    # near city blocks below the horizon so the window is not an empty gradient
    for i in range(14):
        bx = -46 + i * 7.0 + rng.uniform(-2, 2)
        by = 24.0 + rng.uniform(-4, 8)
        bh = rng.uniform(2.0, 8.0)
        box("cityblock_%02d" % i, (bx, by, bh / 2 - 3.0), (rng.uniform(4, 8), rng.uniform(4, 9), bh),
            M["tower"], bevel=0.02)
    lib.sky_dome(c_horizon=(0.026, 0.021, 0.045), c_mid=(0.010, 0.011, 0.024),
                 c_zenith=(0.0030, 0.0034, 0.008), sun_dir=(0.35, 0.86, 0.36),
                 sun_color=(0.90, 0.94, 1.0), sun_power=9.0, glow=0.55, strength=1.0,
                 cloud=((0.10, 0.09, 0.16), 0.18, 3.0, 0.14))


# ================================================================ material registry
def make_materials():
    M = {}
    M["wall"] = mat_wall()
    M["floor"] = mat_floor()
    M["wood"] = mat_wood()
    M["wood_dark"] = mat_wood("B_wood_dark", (0.036, 0.028, 0.024), rough=0.62, grain=9.0)
    M["wood_desk"] = mat_wood("B_wood_desk", (0.185, 0.145, 0.112), rough=0.66, grain=10.0)
    M["paint"] = mat_paint()
    M["metal"] = mat_metal()
    M["fabric"] = mat_fabric("B_fabric_warm", (0.42, 0.38, 0.33), sheen=0.4)
    M["sheet"] = mat_fabric("B_sheet", (0.44, 0.45, 0.53), sheen=0.55)
    M["duvet"] = mat_fabric("B_duvet", (0.395, 0.405, 0.475), sheen=0.6)
    M["curtain"] = mat_fabric("B_curtain", (0.38, 0.365, 0.435), rough=0.92, sheen=0.55)
    M["curtain"].node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (0.42, 0.46, 0.72, 1.0)
    M["curtain"].node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 0.10
    M["paper"] = mat_fabric("B_paper", (0.56, 0.57, 0.62), rough=0.95, sheen=0.1)
    M["paper_dim"] = lib.principled("B_paper_dim", (0.34, 0.33, 0.36), roughness=0.95)
    M["art_print"] = lib.principled("B_art_print", (0.085, 0.080, 0.105), roughness=0.9)
    M["bg_dark"] = mat_black()
    M["glass"] = mat_glass("B_pane", alpha=0.055, rough=0.05, ior=1.5)
    M["glass_cup"] = mat_glass("B_cup", tint=(0.88, 0.94, 1.0), alpha=0.30, rough=0.05,
                               transmission=0.0, ior=1.45)
    M["drop"] = lib.principled("B_drop", (0.82, 0.90, 1.0), roughness=0.05, alpha=0.38,
                                 emission=(0.30, 0.40, 0.75), emission_strength=0.02)
    M["water"] = mat_water("B_water_body", alpha=0.9)
    M["ice"] = lib.principled("B_ice", (0.90, 0.95, 1.0), roughness=0.05, alpha=0.55)
    try:
        M["ice"].surface_render_method = 'DITHERED'
    except Exception:
        pass
    M["cream"] = lib.principled("B_cream", (0.88, 0.80, 0.62), roughness=0.46, subsurface=0.30)
    M["cream_liquid"] = lib.principled("B_cream_liq", (0.80, 0.73, 0.58), roughness=0.14)
    M["shade"] = lib.principled("B_shade_outer", (0.36, 0.27, 0.19), roughness=0.85, sheen=0.4,
                                emission=(1.0, 0.52, 0.22), emission_strength=0.45)
    M["shade_glow"] = lib.principled("B_shade_inner", (0.9, 0.5, 0.24), roughness=0.6,
                                     emission=(1.0, 0.50, 0.20), emission_strength=1.6)
    M["bulb"] = lib.emission("B_bulb", (1.0, 0.62, 0.30), 12.0)
    M["clockface"] = lib.principled("B_clockface", (0.62, 0.60, 0.55), roughness=0.55)
    M["terracotta"] = lib.principled("B_terracotta", (0.32, 0.16, 0.10), roughness=0.82)
    M["soil"] = lib.principled("B_soil", (0.045, 0.032, 0.024), roughness=0.95)
    M["stem"] = lib.principled("B_stem_dry", (0.16, 0.17, 0.10), roughness=0.75)
    M["stem_dry"] = lib.principled("B_stem_brown", (0.115, 0.085, 0.055), roughness=0.82)
    M["petal_violet"] = lib._sunflower_petal_mat("B_petal_violet", (0.30, 0.10, 0.48), (0.72, 0.46, 0.98), 0.16)
    M["disc_dark"] = lib.principled("B_disc_dark", (0.075, 0.045, 0.075), roughness=0.8)
    M["petal_dry"] = lib._sunflower_petal_mat("B_petal_dry", (0.24, 0.145, 0.30), (0.52, 0.35, 0.58), 0.09)
    M["disc_dry"] = lib.principled("B_disc_dry", (0.10, 0.06, 0.075), roughness=0.88)
    M["tower"] = lib.principled("B_tower", (0.012, 0.013, 0.020), roughness=0.95)
    M["win_warm"] = lib.emission("B_win_warm", (1.0, 0.58, 0.26), 1.9)
    M["win_cool"] = lib.emission("B_win_cool", (0.48, 0.68, 1.0), 1.6)
    M["win_violet"] = lib.emission("B_win_violet", (0.72, 0.42, 1.0), 2.2)
    M["dust"] = lib.principled("B_dust", (0.72, 0.72, 0.78), roughness=0.6,
                               emission=(0.7, 0.75, 1.0), emission_strength=1.5, alpha=0.85)
    try:
        M["dust"].surface_render_method = 'DITHERED'
    except Exception:
        pass
    M["skin"] = lib.principled("B_skin", (0.22, 0.14, 0.13), roughness=0.7)
    M["hair"] = lib.principled("B_hair", (0.030, 0.026, 0.032), roughness=0.55)
    M["cloth_dark"] = lib.principled("B_cloth_dark", (0.055, 0.050, 0.070), roughness=0.85)
    return M


# ================================================================ room assembly
def build_room_base():
    M = make_materials()
    build_shell(M)
    build_window(M)
    build_curtain_rod(M)
    build_curtain(M, "L")
    build_curtain(M, "R")
    build_desk(M)
    build_paper_and_flower(M)
    build_dried_sunflower(M)
    build_chair(M)
    build_bed(M)
    build_nightstand(M)
    build_lamp(M)
    build_clock(M)
    build_wall_art(M)
    return M


def add_window_glass_rain(M):
    return build_rain_on_glass(M, count=430, drop_scale=0.42)


def add_city(M):
    build_city(M)
    build_sky_night(M)


# ================================================================ lights
def lights_night_lamp(M):
    """Warm bedside lamp island vs cold window light."""
    # moon: directional so the window frame throws a crisp pool of light inside
    lib.sun_light(energy=2.6, direction=(0.16, -0.94, -0.30), color=(0.42, 0.54, 1.0),
                  angle_deg=0.55)
    lib.area_light("win_city_glow", (-1.4, 5.2, 1.25), target=(0.5, -0.3, 1.0),
                   energy=190.0, size=2.6, color=(0.58, 0.36, 0.95))
    lib.point_light("lamp_warm", (0.80, -1.84, NB_TOP + 0.31), energy=52.0, radius=0.05,
                    color=(1.0, 0.52, 0.20))
    # warm spill above/around the shade (fabric shade transmits)
    lib.point_light("lamp_above", (0.80, -1.84, NB_TOP + 0.56), energy=9.0, radius=0.10,
                    color=(1.0, 0.56, 0.26))
    lib.area_light("ceiling_fill", (0.0, -0.2, RZ1 - 0.10), target=(0.4, -0.8, 0.0),
                   energy=9.0, size=3.0, color=(0.30, 0.38, 0.80))
    lib.scene().eevee.use_raytracing = False
    lib.fog(density=0.0, color=(0.52, 0.55, 0.82), anisotropy=0.42,
            ambient=(0.100, 0.094, 0.195), ambient_strength=0.62)


def lights_night_rain(M):
    """Very cold, almost no interior light; city leaks in."""
    # window key light: soft, comes through the panes onto the desk
    lib.area_light("win_cold", (0.2, 4.4, 1.75), target=(-1.5, 1.6, 0.80),
                   energy=340.0, size=2.2, color=(0.55, 0.65, 1.0))
    lib.area_light("win_city_glow", (-1.9, 4.8, 1.10), target=(-1.2, 1.2, 0.85),
                   energy=150.0, size=3.0, color=(0.58, 0.38, 0.98))
    lib.area_light("win_city_glow2", (2.2, 4.6, 1.45), target=(1.4, 1.4, 0.9),
                   energy=70.0, size=2.2, color=(0.30, 0.55, 1.0))
    # cool bounce from the ceiling so the dark side keeps detail
    lib.area_light("room_fill", (-0.6, 0.2, RZ1 - 0.12), target=(-1.5, 1.5, 0.7),
                   energy=13.0, size=2.6, color=(0.32, 0.40, 0.85))
    lib.scene().eevee.use_raytracing = False
    lib.fog(density=0.0, color=(0.45, 0.50, 0.85), anisotropy=0.4,
            ambient=(0.070, 0.078, 0.160), ambient_strength=0.68)


# ================================================================ camera helpers
def make_cam(loc, target, lens=50.0, fstop=2.0, focus=None, name="Cam"):
    c = lib.camera(loc, target, lens=lens, fstop=fstop,
                   focus_distance=(focus if focus is not None else (Vector(target) - Vector(loc)).length),
                   name=name)
    return c


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
    print("[room] %-24s %.2fs" % (name, time.time() - t))


# ================================================================ macro set (S23/S24/S28)
def mat_black(name="B_bg_dark", color=(0.012, 0.012, 0.018)):
    return lib.principled(name, color, roughness=0.9)


def build_condensation(M, cx=0.0, cy=0.0, z0=0.0, r=0.044, h=0.115, count=110, seed=3):
    """Tiny droplets clinging to the outside of the glass, some running down."""
    rng = random.Random(seed)
    bm = bmesh.new()
    for i in range(count):
        a = rng.uniform(0, 2 * math.pi)
        zz = z0 + rng.uniform(0.008, h * 0.95)
        rad = r * (1.005 + rng.uniform(0, 0.004))
        px, py = cx + math.cos(a) * rad, cy + math.sin(a) * rad
        sz = rng.uniform(0.0007, 0.0032)
        if rng.random() < 0.10:
            sz *= 2.1
        # droplet sits on the wall: thick along the radial normal, flattened tangentially
        spin = Matrix.Rotation(a, 4, 'Z')
        flat = Matrix.Diagonal((1.0, 0.38, rng.uniform(0.9, 1.9), 1.0))
        mat4 = (Matrix.Translation((px, py, zz)) @ spin @ flat @
                Matrix.Rotation(math.pi / 2, 4, 'Y'))
        bmesh.ops.create_uvsphere(bm, u_segments=8, v_segments=5, radius=sz, matrix=mat4)
    return bm_to_obj("condensation", bm, M["drop"], smooth=True)


def build_macro_set(M, ices=3, water_level=0.60, seed=4):
    """A small dark tabletop set for the ice-glass macro shots."""
    quad("macro_table", [(-3, -3, 0), (3, -3, 0), (3, 3, 0), (-3, 3, 0)], M["wood_desk"])
    # backdrop boards (dark, will fall out of focus)
    quad("macro_bg", [(-2.5, 1.7, 0), (2.5, 1.7, 0), (2.5, 1.7, 2.2), (-2.5, 1.7, 2.2)], M["bg_dark"])
    quad("macro_bg_l", [(-1.6, 1.35, 0), (-1.6, 1.7, 0), (-1.6, 1.7, 2.2), (-1.6, 1.35, 2.2)], M["bg_dark"])
    iced = build_glass_ice(M, loc=(0.0, 0.0, 0.0), scale=1.0, water_level=water_level,
                           ices=ices, seed=seed)
    build_condensation(M, count=120, seed=seed + 1)
    # a couple of loose ice chips on the table
    rng = random.Random(seed + 7)
    for i in range(3):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= rng.uniform(0.012, 0.022)
            v.co.y *= rng.uniform(0.012, 0.022)
            v.co.z *= rng.uniform(0.008, 0.014)
        bmesh.ops.translate(bm, vec=Vector((rng.uniform(-0.16, 0.16), rng.uniform(-0.14, 0.12),
                                            0.006)), verts=bm.verts)
        bm_to_obj("ice_chip_%d" % i, bm, M["ice"], smooth=True)
    return iced


def lights_macro_cold():
    lib.area_light("back_key", (0.00, 0.34, 0.26), target=(0.0, 0.0, 0.07),
                   energy=55.0, size=0.22, color=(0.58, 0.72, 1.0))
    lib.area_light("side_cold", (-0.40, 0.02, 0.24), target=(0.0, 0.0, 0.08),
                   energy=14.0, size=0.55, color=(0.42, 0.52, 1.0))
    lib.area_light("rim_top", (0.08, -0.18, 0.42), target=(0.0, 0.0, 0.07),
                   energy=6.0, size=0.30, color=(0.55, 0.65, 1.0))
    lib.scene().eevee.use_raytracing = False
    lib.fog(density=0.0, color=(0.30, 0.35, 0.60), anisotropy=0.4,
            ambient=(0.020, 0.024, 0.055), ambient_strength=1.0)


def lights_macro_warm():
    lib.area_light("back_key", (0.10, 0.34, 0.24), target=(0.0, 0.0, 0.07),
                   energy=42.0, size=0.26, color=(1.0, 0.66, 0.36))
    lib.area_light("side_warm", (-0.42, 0.02, 0.22), target=(0.0, 0.0, 0.08),
                   energy=18.0, size=0.45, color=(1.0, 0.55, 0.26))
    lib.point_light("bokeh_warm", (-0.55, 1.15, 0.36), energy=6.0, radius=0.10,
                    color=(1.0, 0.58, 0.24))
    lib.scene().eevee.use_raytracing = False
    lib.fog(density=0.0, color=(0.55, 0.36, 0.20), anisotropy=0.4,
            ambient=(0.055, 0.035, 0.022), ambient_strength=1.0)


def lookdev_macro():
    for mode in ("cold", "warm"):
        lib.reset()
        lib.setup_render(samples=20, resolution=(1280, 720))
        M = make_materials()
        if mode == "cold":
            build_macro_set(M, ices=3, water_level=0.60, seed=4)
            lights_macro_cold()
        else:
            build_macro_set(M, ices=3, water_level=0.52, seed=9)
            lights_macro_warm()
        # debug: wide view of the whole macro set
        cam = make_cam((0.30, -0.62, 0.34), (0.0, 0.0, 0.055), lens=50, fstop=4.0, focus=0.70)
        render_still("B_macro_%s_dbg" % mode)
        # S23 wide-ish macro on the glass
        cam = make_cam((0.015, -0.315, 0.088), (0.0, 0.0, 0.070), lens=85, fstop=2.8, focus=0.315)
        render_still("B_macro_%s_01" % mode)
        # S24 tight on the condensation on the glass wall
        cam = make_cam((0.0, -0.175, 0.072), (0.0, 0.0, 0.062), lens=85, fstop=2.2, focus=0.178)
        render_still("B_macro_%s_02" % mode)
        # S28 alt: lower angle, ice cubes and water line
        cam = make_cam((-0.115, -0.235, 0.045), (0.0, 0.0, 0.085), lens=85, fstop=2.0, focus=0.25)
        render_still("B_macro_%s_03" % mode)


# ================================================================ look-dev: night_lamp
def lookdev_night_lamp():
    lib.reset()
    lib.setup_render(samples=20, resolution=(1280, 720))
    M = build_room_base()
    add_window_glass_rain(M)
    add_city(M)
    build_icecream_cup(M)
    build_potted_sunflower(M)
    lights_night_lamp(M)
    # 1) bedside: lamp shade + ice cream foreground + clock background
    cam = make_cam((0.02, -0.46, 0.86), (0.90, -1.82, 0.96), lens=31, fstop=2.2, focus=1.45)
    render_still("B_lamp_01")
    # 2) window + curtains + moon, low angle, asymmetric with a warm edge on the right
    cam = make_cam((-1.38, -0.72, 0.86), (0.52, 2.20, 1.30), lens=25, fstop=2.4, focus=3.1)
    render_still("B_lamp_02")
    # 3) bed + lamp + window, wide enough to read the room
    cam = make_cam((0.05, 1.05, 1.32), (1.85, -1.25, 0.72), lens=24, fstop=4.0, focus=2.6)
    render_still("B_lamp_03")
    # 4) empty bed from above (S40 beat 1)
    cam = make_cam((2.35, 0.78, 1.52), (1.45, -1.42, 0.50), lens=34, fstop=2.8, focus=2.4)
    render_still("B_lamp_04")


# ================================================================ look-dev: night_rain
def lookdev_night_rain():
    lib.reset()
    lib.setup_render(samples=16, resolution=(1280, 720))
    M = build_room_base()
    add_window_glass_rain(M)
    add_city(M)
    build_dust(M)
    lights_night_rain(M)
    # 1) S01: 85mm close on the glass, focus pull target = glass
    cam = make_cam((0.30, 0.22, 1.44), (0.18, 4.2, 1.30), lens=85, fstop=2.0, focus=1.95)
    render_still("B_rain_01")
    # 2) S02: diagonal over the desk, window light behind, flower silhouette
    cam = make_cam((-2.28, 0.52, 1.08), (-1.10, 1.92, 0.86), lens=46, fstop=2.0, focus=1.75)
    cam.rotation_euler.z += math.radians(-2.0)
    render_still("B_rain_02")
    # 3) S02 alt: closer on the flower, heavy bokeh
    cam = make_cam((-1.95, 0.55, 0.95), (-1.55, 1.88, 0.82), lens=70, fstop=1.8, focus=1.35)
    cam.rotation_euler.z += math.radians(-3.0)
    render_still("B_rain_03")
    # 4) dried flower diagnostic close-up
    cam = make_cam((-1.20, 0.72, 0.93), (-1.55, 1.86, 0.84), lens=85, fstop=2.8, focus=1.0)
    render_still("B_rain_04")



def render_missing(shots_arg, samples=12):
    """Render the missing frames of the given shots: shots_arg = 'S01:12,30-44;S02:...'."""
    S = load_shots()
    builders = {
        "S01": build_room_night_rain, "S02": build_room_night_rain,
        "S25": build_room_night_rain, "S55": build_room_night_rain,
        "S56": build_room_night_rain, "S57": build_room_night_rain,
        "S35": build_room_night_lamp, "S36": build_room_night_lamp,
        "S37": build_room_night_lamp, "S38": build_room_night_lamp,
        "S26": build_room_night_dark, "S41": build_room_night_dark,
        "S40a": lambda: build_room_night_dark(beats=("S40",)),
        "S23": build_macro_cold, "S24": build_macro_cold,
        "S28": build_macro_warm,
        "S40c": build_empty_field,
    }
    todo = {}
    for part in shots_arg.split(";"):
        if not part.strip():
            continue
        sid, spec = part.split(":")
        frames = []
        for chunk in spec.split(","):
            if "-" in chunk:
                a, b = chunk.split("-")
                frames.extend(range(int(a), int(b) + 1))
            else:
                frames.append(int(chunk))
        todo[sid] = frames
    # build each needed set once
    built = {}
    for sid, frames in todo.items():
        key = sid.rstrip("abc")
        bf = builders.get(sid) or builders.get(key)
        if key not in built:
            built[key] = bf()
        cams = built[key]
        cam_key = sid if sid in cams else key
        sc = lib.scene()
        sc.camera = cams[cam_key]
        outdir = os.path.join(PLATES, "S40" if sid.startswith("S40") else sid)
        os.makedirs(outdir, exist_ok=True)
        for f in frames:
            sc.frame_set(f)
            sc.render.filepath = os.path.join(outdir, "%s_%04d.png" % (sid if not sid.startswith("S40") else "S40", f))
            bpy.ops.render.render(write_still=True)
            print("[missing] %s %d" % (sid, f))


def find_missing():
    S = load_shots()
    B = [x for x in S.values() if x.get("team") == "B"]
    out = []
    for sh in B:
        sid, f0, f1 = sh["id"], sh["f0"], sh["f1"]
        d = os.path.join(PLATES, sid)
        have = set()
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.startswith(sid + "_") and f.endswith(".png"):
                    try:
                        have.add(int(f[len(sid) + 1:-4]))
                    except ValueError:
                        pass
        miss = [n for n in range(f0, f1 + 1) if n not in have]
        if miss:
            out.append("%s:%s" % (sid, ",".join("%d-%d" % (n, n) for n in miss)))
    return ";".join(out)


# ================================================================ night_lamp group (S35-S38)
def build_room_night_lamp(anim=True):
    lib.reset()
    lib.setup_render(samples=20, resolution=(1920, 1080))
    M = build_room_base()
    add_window_glass_rain(M)
    add_city(M)
    cream = build_icecream_cup(M)
    plant = build_potted_sunflower(M)
    lights_night_lamp(M)
    lib.area_light("warm_anchor", (-0.55, -0.35, 1.35), target=(0.6, 1.6, 1.2),
                   energy=10.0, size=0.9, color=(1.0, 0.55, 0.24))
    S = load_shots()
    cams = {}

    try:
        ga, gb = character_mod.two_people("Refl", variant_a="girl", variant_b="boy",
                                          pose_a="hold", pose_b="hold",
                                          height_a=1.58, height_b=1.72, facing=math.pi)
        gy = 2 * 2.145 - 1.18
        ga.location = (0.42, gy, 0.0)
        gb.location = (0.76, gy, 0.0)
        ga.rotation_euler = (0, 0, math.pi)
        gb.rotation_euler = (0, 0, math.pi)
        ghostify(ga, alpha=0.30)
        ghostify(gb, alpha=0.20)
        for g in (ga, gb):
            g.hide_render = True
            g.keyframe_insert("hide_render", frame=S["S35"]["f0"] - 10)
            g.hide_render = True
            g.keyframe_insert("hide_render", frame=S["S37"]["f0"] - 1)
            g.hide_render = False
            g.keyframe_insert("hide_render", frame=S["S37"]["f0"])
    except Exception as exc:
        print("[warn] character reflection failed:", exc)

    sh = S["S35"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((0.02, -0.46, 0.86), (0.90, -1.82, 0.96), lens=31, fstop=2.2, focus=1.45)
    lib.anim_camera(cam, [
        (f0, (0.02, -0.46, 0.86), (0.90, -1.82, 0.96), 1.45),
        (f1, (0.02, -0.36, 0.84), (0.88, -1.82, 0.94), 1.30),
    ])
    cams["S35"] = cam
    c1, c2 = cream["cream1"], cream["cream2"]
    p1 = c1.location.copy()
    p2 = c2.location.copy()
    for f, sc1, dz1, sc2, dz2 in ((f0, 1.0, 0.0, 1.0, 0.0),
                                  (f0 + int((f1 - f0) * 0.55), 0.955, -0.004, 0.99, -0.002),
                                  (f1, 0.90, -0.012, 0.96, -0.006)):
        c1.scale = (sc1, sc1, sc1 * 0.92)
        c1.location = (p1.x, p1.y, p1.z + dz1)
        c1.keyframe_insert("scale", frame=f)
        c1.keyframe_insert("location", frame=f)
        c2.scale = (sc2, sc2, sc2 * 0.78)
        c2.location = (p2.x, p2.y, p2.z + dz2)
        c2.keyframe_insert("scale", frame=f)
        c2.keyframe_insert("location", frame=f)

    sh = S["S36"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((-1.78, -0.62, 0.88), (0.28, 2.20, 1.34), lens=22, fstop=2.4, focus=2.9)
    lib.anim_camera(cam, [
        (f0, (-1.78, -0.62, 0.88), (0.28, 2.20, 1.34), 2.9),
        (f1, (-1.66, -0.42, 0.90), (0.24, 2.20, 1.32), 2.6),
    ])
    cams["S36"] = cam
    for side in ("L", "R"):
        ob = bpy.data.objects.get("curtain_" + side)
        if ob and ob.data.shape_keys:
            kb = ob.data.shape_keys.key_blocks.get("Blow")
            if kb:
                for f, v in ((f0, 0.10), (f0 + 18, 0.85), (f0 + 40, 0.25),
                             (f0 + 58, 0.65), (f1, 0.30)):
                    kb.value = v
                    kb.keyframe_insert("value", frame=f)

    sh = S["S37"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((1.12, 0.42, 1.28), (0.18, 2.20, 1.32), lens=36, fstop=2.0, focus=1.85)
    lib.anim_camera(cam, [
        (f0, (1.12, 0.42, 1.28), (0.18, 2.20, 1.32), 1.85),
        (f1, (1.02, 0.30, 1.26), (0.24, 2.20, 1.31), 1.72),
    ], interp="BEZIER")
    cams["S37"] = cam

    sh = S["S38"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((0.30, 1.00, 1.02), (0.98, 2.12, 1.18), lens=50, fstop=1.9, focus=1.10)
    lib.anim_camera(cam, [
        (f0, (0.30, 1.00, 1.02), (0.98, 2.12, 1.18), 1.08),
        (f1, (0.26, 0.92, 1.03), (0.96, 2.12, 1.16), 1.03),
    ])
    cams["S38"] = cam
    if plant:
        rz = plant.rotation_euler[2]
        for f, a in ((f0, 0.0), (f0 + 34, 0.045), (f0 + 70, -0.030), (f1, 0.020)):
            plant.rotation_euler = (a * 0.4, a, rz)
            plant.keyframe_insert("rotation_euler", frame=f)
    return cams


# ================================================================ night_dark group (S26/S40a/S41)
def lights_night_dark():
    lib.sun_light(energy=2.2, direction=(0.10, -0.90, -0.34), color=(0.44, 0.56, 1.0),
                  angle_deg=0.5)
    lib.area_light("city_leak", (1.6, 4.6, 1.3), target=(0.4, 0.6, 0.9),
                   energy=90.0, size=2.0, color=(0.52, 0.36, 0.92))
    lib.point_light("floor_bounce", (0.4, -0.6, 0.16), energy=2.0, radius=0.6,
                    color=(0.35, 0.42, 0.9))
    lib.scene().eevee.use_raytracing = False
    lib.fog(density=0.0, color=(0.30, 0.34, 0.60), anisotropy=0.4,
            ambient=(0.028, 0.032, 0.075), ambient_strength=0.70)


def build_room_night_dark(anim=True, beats=("S26", "S40", "S41")):
    lib.reset()
    lib.setup_render(samples=20, resolution=(1920, 1080))
    M = build_room_base()
    add_window_glass_rain(M)
    add_city(M)
    lights_night_dark()
    S = load_shots()
    cams = {}

    if "S26" in beats:
        girl = character_mod.figure("Girl26", variant="girl", pose="stand", height=1.58,
                                    facing=math.pi)
        girl.location = (1.30, 1.10, 0.0)
        girl.rotation_euler = (0, 0, math.pi * 0.06)
        sh = S["S26"]; f0, f1 = sh["f0"], sh["f1"]
        for f, rz in ((f0, math.pi * 0.06), (f0 + 40, math.pi * 0.06),
                      (f0 + 78, math.pi * 0.52), (f1, math.pi * 0.60)):
            girl.rotation_euler = (0, 0, rz)
            girl.keyframe_insert("rotation_euler", frame=f)
        cam = make_cam((-0.55, 0.25, 1.20), (1.25, 2.12, 1.32), lens=40, fstop=1.8, focus=1.85)
        lib.anim_camera(cam, [
            (f0, (-0.55, 0.25, 1.20), (1.25, 2.12, 1.32), 1.85),
            (f1, (-0.42, 0.38, 1.19), (1.28, 2.12, 1.31), 1.72),
        ])
        cams["S26"] = cam

    if "S40" in beats:
        cam = make_cam((2.30, 0.70, 1.48), (1.48, -1.52, 0.50), lens=33, fstop=2.4, focus=2.2)
        lib.anim_camera(cam, [
            (4292, (2.30, 0.70, 1.48), (1.48, -1.52, 0.50), 2.20),
            (4329, (2.22, 0.58, 1.44), (1.46, -1.55, 0.50), 2.10),
        ])
        cams["S40"] = cam

    if "S41" in beats:
        # cold rim from the window side: only enough to outline shoulder/back/hair
        lib.area_light("bed_rim", (1.55, 1.75, 1.30), target=(1.72, -0.55, 0.62),
                       energy=34.0, size=1.1, color=(0.48, 0.60, 1.0))
        lib.area_light("bed_rim2", (0.35, 0.95, 1.05), target=(1.72, -0.40, 0.55),
                       energy=12.0, size=0.9, color=(0.42, 0.55, 1.0))
        girl = character_mod.figure("Girl41", variant="girl", pose="sit", height=1.56,
                                    dress_len=0.55, hair_len=0.7, facing=math.pi * 0.5)
        girl.location = (1.72, -0.55, BED_TOP + 0.01)
        girl.rotation_euler = (math.radians(-72), 0, math.pi * 0.5)
        sh = S["S41"]; f0, f1 = sh["f0"], sh["f1"]
        cam = make_cam((0.28, -1.55, 0.72), (1.72, -0.45, 0.66), lens=42, fstop=1.8, focus=1.6)
        lib.anim_camera(cam, [
            (f0, (0.28, -1.55, 0.72), (1.72, -0.45, 0.66), 1.60),
            (f1, (0.34, -1.42, 0.70), (1.70, -0.48, 0.65), 1.52),
        ])
        cams["S41"] = cam
    return cams


# ================================================================ macro group (S23/S24/S28)
def build_macro_cold(anim=True):
    lib.reset()
    lib.setup_render(samples=20, resolution=(1920, 1080))
    M = make_materials()
    iced = build_macro_set(M, ices=3, water_level=0.60, seed=4)
    lights_macro_cold()
    lib.point_light("far_bokeh", (0.42, 1.30, 0.30), energy=7.0, radius=0.10,
                    color=(1.0, 0.55, 0.28))
    lib.point_light("far_bokeh2", (-0.46, 1.25, 0.45), energy=5.0, radius=0.08,
                    color=(0.55, 0.45, 1.0))
    S = load_shots()
    cams = {}
    sh = S["S23"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((0.015, -0.315, 0.088), (0.0, 0.0, 0.070), lens=85, fstop=2.8, focus=0.315)
    lib.anim_camera(cam, [
        (f0, (0.020, -0.330, 0.090), (0.0, 0.0, 0.068), 0.330),
        (f1, (0.012, -0.285, 0.086), (0.0, 0.0, 0.072), 0.286),
    ])
    cams["S23"] = cam
    sh = S["S24"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((0.0, -0.175, 0.072), (0.0, 0.0, 0.062), lens=85, fstop=2.2, focus=0.178)
    lib.anim_camera(cam, [
        (f0, (0.012, -0.180, 0.074), (-0.004, 0.0, 0.060), 0.182),
        (f1, (-0.008, -0.152, 0.070), (0.006, 0.0, 0.064), 0.155),
    ], interp="LINEAR")
    cams["S24"] = cam
    for i, cube in enumerate(iced["ice"]):
        base = cube.location.copy()
        s0 = cube.scale.copy()
        for f, k in ((2503, 1.0), (2710, 0.90)):
            cube.scale = (s0.x * k, s0.y * k, s0.z * k)
            cube.keyframe_insert("scale", frame=f)
            cube.location = (base.x, base.y, base.z - 0.002 * (1 - k))
            cube.keyframe_insert("location", frame=f)
    return cams


def build_macro_warm(anim=True):
    lib.reset()
    lib.setup_render(samples=20, resolution=(1920, 1080))
    M = make_materials()
    iced = build_macro_set(M, ices=3, water_level=0.50, seed=9)
    lights_macro_warm()
    S = load_shots()
    cams = {}
    sh = S["S28"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((-0.115, -0.235, 0.045), (0.0, 0.0, 0.085), lens=85, fstop=2.0, focus=0.25)
    lib.anim_camera(cam, [
        (f0, (-0.130, -0.245, 0.044), (0.0, 0.0, 0.086), 0.255),
        (f1, (-0.098, -0.205, 0.048), (0.0, 0.0, 0.082), 0.215),
    ])
    cams["S28"] = cam
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.004)
    drop = bm_to_obj("falling_drop", bm, M["drop"], smooth=True)
    drop.location = (0.012, 0.052, 0.30)
    for f, z in ((f0, 0.30), (f0 + 40, 0.16), (f0 + 52, 0.115), (f1, 0.112)):
        drop.location = (0.012, 0.052, z)
        drop.keyframe_insert("location", frame=f)
    lib.point_light("bokeh_warm", (-0.55, 1.15, 0.36), energy=8.0, radius=0.10,
                    color=(1.0, 0.58, 0.24))
    return cams


# ================================================================ empty field beat (S40c)
def build_empty_field(anim=True):
    lib.reset()
    lib.setup_render(samples=20, resolution=(1920, 1080))
    lib.sky_dome(c_horizon=(0.030, 0.026, 0.048), c_mid=(0.012, 0.012, 0.026),
                 c_zenith=(0.0035, 0.0036, 0.009), sun_dir=(0.35, 0.80, 0.48),
                 sun_color=(0.85, 0.90, 1.0), sun_power=5.0, glow=0.4, strength=1.0,
                 cloud=((0.05, 0.045, 0.085), 0.30, 2.2, 0.25))
    lib.fog(density=0.0, color=(0.28, 0.30, 0.50), anisotropy=0.4,
            ambient=(0.032, 0.034, 0.070), ambient_strength=1.0)
    lib.ground(size=200, color_a=(0.045, 0.040, 0.036), color_b=(0.018, 0.017, 0.016),
               roughness=0.95, noise_scale=3.0, noise_amt=0.6)
    # dead sunflower field: all heads hang
    rng = random.Random(23)
    pals = lib._petal_set("dead")
    field = []
    for i in range(130):
        x = rng.uniform(-16, 16)
        y = rng.uniform(-14, 16)
        if abs(x) < 1.2 and -3.5 < y < 9.0:
            continue
        if (x * x + (y - 2) * (y - 2)) ** 0.5 < 1.6:
            continue
        ob = lib.sunflower(name="dead_%03d" % i, size=rng.uniform(0.85, 1.3),
                           n_petals=rng.choice([17, 19, 21]), petal_len=0.20,
                           stem_len=rng.uniform(0.95, 1.45), head_tilt=rng.uniform(62, 108),
                           pose_seed=rng.randint(0, 999999), leaf=True,
                           mats=rng.choice(pals), head_azim=rng.uniform(-0.6, 0.6))
        ob.location = (x, y, 0)
        ob.rotation_euler = (0, 0, rng.uniform(0, math.pi * 2))
        field.append(ob)
    lib.wind_sway(field, amp=0.010, keys=(4369, 4388, 4407))
    lib.sun_light(energy=1.5, direction=(0.16, -0.86, -0.40), color=(0.48, 0.58, 1.0),
                  angle_deg=0.6)
    lib.area_light("horizon_glow", (0.0, 60.0, 3.0), target=(0.0, 0.0, 2.0),
                   energy=420.0, size=30.0, color=(0.45, 0.36, 0.80))
    lib.point_light("fill", (0.0, -4.0, 2.0), energy=3.0, radius=2.0,
                    color=(0.40, 0.46, 0.85))
    lib.scene().eevee.use_raytracing = False
    S = load_shots()
    sh = S["S40"]
    cam = make_cam((0.0, -4.6, 0.62), (0.15, 10.0, 1.15), lens=34, fstop=3.2, focus=7.0)
    lib.anim_camera(cam, [
        (4369, (0.0, -4.6, 0.62), (0.15, 10.0, 1.15), 7.0),
        (4407, (0.06, -4.2, 0.64), (0.15, 10.0, 1.15), 6.4),
    ])
    return {"S40c": cam}


def render_empty_field(samples=20):
    S = load_shots()
    cams = build_empty_field()
    sc = lib.scene()
    sc.camera = cams["S40c"]
    fake = {"id": "S40", "f0": 4369, "f1": 4407}
    t = time.time()
    lib.render(fake, os.path.join(PLATES, "S40"), samples=samples)
    print("[render] S40c 39 frames in %.1fs" % (time.time() - t))


# ================================================================ shot groups + animation
import json as _json
import character as character_mod


def load_shots():
    with open(os.path.join(ROOT, "story", "shots.json"), encoding="utf-8") as f:
        return {x["id"]: x for x in _json.load(f)["shots"]}


def ghostify(ob, alpha=0.38, tint=(0.55, 0.62, 0.95)):
    """Make a copy of a figure's materials so it reads as a glass reflection."""
    for slot in ob.material_slots:
        if slot.material is None:
            continue
        m = slot.material.copy()
        m.name = slot.material.name + "_ghost"
        nt = m.node_tree
        for n in nt.nodes:
            if n.type == "BSDF_PRINCIPLED":
                n.inputs["Alpha"].default_value = alpha
                if "Emission Color" in n.inputs:
                    n.inputs["Emission Color"].default_value = (*tint, 1.0)
                    n.inputs["Emission Strength"].default_value = 0.10
        try:
            m.surface_render_method = "DITHERED"
            m.use_transparent_shadow = True
        except Exception:
            pass
        slot.material = m
    ob.visible_shadow = False


def build_room_night_rain(anim=True):
    lib.reset()
    lib.setup_render(samples=20, resolution=(1920, 1080))
    M = build_room_base()
    add_window_glass_rain(M)
    add_city(M)
    dust = build_dust(M)
    lights_night_rain(M)
    cams = {}
    S = load_shots()

    # ---- S01: 85mm close on the glass; focus pulls from droplets to city bokeh
    sh = S["S01"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((0.30, 0.36, 1.46), (0.06, 4.2, 1.30), lens=85, fstop=2.0, focus=1.85)
    lib.anim_camera(cam, [
        (f0, (0.30, 0.36, 1.46), (0.06, 4.2, 1.30), 1.82),
        (f0 + int((f1 - f0) * 0.45), (0.30, 0.40, 1.455), (0.08, 4.2, 1.295), 3.6),
        (f1, (0.30, 0.46, 1.45), (0.10, 4.2, 1.29), 26.0),
    ], interp="BEZIER")
    cams["S01"] = cam

    # ---- S02: desk + dried flower, slow drift right
    sh = S["S02"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((-2.28, 0.52, 1.08), (-1.10, 1.92, 0.86), lens=46, fstop=2.0, focus=1.75)
    cam.rotation_euler.z += math.radians(-2.0)
    lib.anim_camera(cam, [
        (f0, (-2.30, 0.54, 1.085), (-1.06, 1.92, 0.86), 1.78),
        (f1, (-2.16, 0.50, 1.075), (-1.18, 1.92, 0.855), 1.72),
    ])
    cams["S02"] = cam

    # ---- S25: rain on glass + streetlight bokeh, heartbeat push-in
    sh = S["S25"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((0.24, 0.80, 1.36), (0.16, 4.2, 1.24), lens=60, fstop=2.0, focus=1.34)
    lib.anim_camera(cam, [
        (f0, (0.24, 0.80, 1.36), (0.16, 4.2, 1.24), 1.34),
        (f1, (0.22, 1.02, 1.35), (0.16, 4.2, 1.23), 1.13),
    ], interp="BEZIER")
    cd = cam.data
    pulse = []
    t = f0
    k = 0
    while t <= f1:
        pulse.append((t, 60.0 + (1.1 if k % 2 == 0 else 0.0)))
        t += 12
        k += 1
    for f, l in pulse:
        cd.lens = l
        cd.keyframe_insert("lens", frame=f)
    cams["S25"] = cam

    # ---- S55: back to the present, one petal lifts
    sh = S["S55"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((-2.26, 0.46, 1.10), (-1.20, 1.92, 0.92), lens=52, fstop=2.0, focus=1.62)
    lib.anim_camera(cam, [
        (f0, (-2.26, 0.46, 1.10), (-1.20, 1.92, 0.92), 1.62),
        (f1, (-2.10, 0.40, 1.06), (-1.30, 1.92, 0.90), 1.55),
    ])
    cams["S55"] = cam
    petal = bpy.data.objects.get("fallen_petal_0")
    if petal:
        petal.location = (-1.30, 1.74, 0.746)
        petal.rotation_euler = (0, 0, math.radians(40))
        for k in range(4):
            f = f0 + int((f1 - f0) * k / 3.0)
            zt = 0.746 + 0.52 * (k / 3.0) ** 1.6
            petal.location = (-1.30 + 0.10 * k / 3.0, 1.74 + 0.16 * k / 3.0, zt)
            petal.rotation_euler = (math.radians(18 * k), math.radians(35 * k), math.radians(40 + 120 * k))
            petal.keyframe_insert("location", frame=f)
            petal.keyframe_insert("rotation_euler", frame=f)

    # ---- S56: rain window base for the title card, slow drift
    sh = S["S56"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((0.35, 0.62, 1.50), (0.05, 4.2, 1.42), lens=55, fstop=2.2, focus=1.62)
    lib.anim_camera(cam, [
        (f0, (0.35, 0.62, 1.50), (0.05, 4.2, 1.42), 1.62),
        (f1, (0.30, 0.50, 1.48), (0.02, 4.2, 1.40), 1.55),
    ])
    cams["S56"] = cam

    # ---- S57: fade out -- light decays naturally, last petal glow
    sh = S["S57"]; f0, f1 = sh["f0"], sh["f1"]
    cam = make_cam((-2.20, 0.42, 1.08), (-1.34, 1.92, 0.90), lens=62, fstop=1.9, focus=1.45)
    lib.anim_camera(cam, [
        (f0, (-2.20, 0.42, 1.08), (-1.34, 1.92, 0.90), 1.45),
        (f1, (-2.10, 0.36, 1.05), (-1.42, 1.92, 0.88), 1.40),
    ])
    cams["S57"] = cam
    for o in [o for o in bpy.data.objects if o.type == "LIGHT"]:
        e0 = o.data.energy
        o.data.energy = e0
        o.data.keyframe_insert("energy", frame=f0)
        o.data.energy = e0 * 0.04
        o.data.keyframe_insert("energy", frame=f1)
    for m in bpy.data.materials:
        if not m.name.startswith(("B_win_", "B_city", "B_street")):
            continue
        nt = m.node_tree
        if nt is None:
            continue
        for n in nt.nodes:
            if n.type == "EMISSION":
                s0 = n.inputs["Strength"].default_value
                n.inputs["Strength"].default_value = s0
                n.inputs["Strength"].keyframe_insert("default_value", frame=f0)
                n.inputs["Strength"].default_value = s0 * 0.04
                n.inputs["Strength"].keyframe_insert("default_value", frame=f1)
    return cams


def render_group(build_fn, samples=20):
    S = load_shots()
    cams = build_fn()
    for sid in cams.keys():
        sh = S[sid]
        sc = lib.scene()
        sc.camera = cams[sid]
        outdir = os.path.join(PLATES, sid)
        t = time.time()
        lib.render(sh, outdir, samples=samples)
        print("[render] %s %d frames in %.1fs" % (sid, sh["f1"] - sh["f0"] + 1, time.time() - t))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    what = argv[0] if argv else "all"
    if what == "night_lamp":
        lookdev_night_lamp()
    elif what == "night_rain":
        lookdev_night_rain()
    elif what == "macro":
        lookdev_macro()
    elif what == "all":
        lookdev_night_lamp()
        lookdev_night_rain()
        lookdev_macro()
    elif what == "render_rain":
        render_group(build_room_night_rain, samples=int(argv[1]) if len(argv) > 1 else 20)
    elif what == "render_s25":
        S = load_shots()
        cams = build_room_night_rain()
        sc = lib.scene()
        sc.camera = cams["S25"]
        lib.render(S["S25"], os.path.join(PLATES, "S25"), samples=20)
    elif what == "render_rain_rest":
        S = load_shots()
        cams = build_room_night_rain()
        sc = lib.scene()
        for sid in ("S55", "S56", "S57"):
            sc.camera = cams[sid]
            lib.render(S[sid], os.path.join(PLATES, sid), samples=20)
            print("[render] %s done" % sid)
    elif what == "render_s57_rest":
        S = load_shots()
        cams = build_room_night_rain()
        sc = lib.scene()
        sc.camera = cams["S57"]
        fake = {"id": "S57", "f0": 6412, "f1": 6551}
        lib.render(fake, os.path.join(PLATES, "S57"), samples=int(argv[1]) if len(argv) > 1 else 16)
        print("[render] S57 rest done")
    elif what == "render_lamp_rest":
        S = load_shots()
        cams = build_room_night_lamp()
        sc = lib.scene()
        for sid in ("S37", "S38"):
            sc.camera = cams[sid]
            lib.render(S[sid], os.path.join(PLATES, sid), samples=int(argv[1]) if len(argv) > 1 else 12)
            print("[render] %s done" % sid)
    elif what == "render_s38_rest":
        S = load_shots()
        cams = build_room_night_lamp()
        sc = lib.scene()
        sc.camera = cams["S38"]
        fake = {"id": "S38", "f0": 4097, "f1": 4182}
        lib.render(fake, os.path.join(PLATES, "S38"), samples=int(argv[1]) if len(argv) > 1 else 12)
        print("[render] S38 rest done")
    elif what == "render_missing":
        spec = argv[1] if len(argv) > 1 else find_missing()
        print("[missing] spec:", spec[:300])
        if spec:
            render_missing(spec, samples=int(argv[2]) if len(argv) > 2 else 12)
    elif what == "render_s41":
        S = load_shots()
        cams = build_room_night_dark(beats=("S41",))
        sc = lib.scene()
        sc.camera = cams["S41"]
        lib.render(S["S41"], os.path.join(PLATES, "S41"), samples=int(argv[1]) if len(argv) > 1 else 12)
        print("[render] S41 done")
    elif what == "render_s36":
        S = load_shots()
        cams = build_room_night_lamp()
        sc = lib.scene()
        sc.camera = cams["S36"]
        lib.render(S["S36"], os.path.join(PLATES, "S36"), samples=int(argv[1]) if len(argv) > 1 else 12)
        print("[render] S36 done")
    elif what == "render_lamp":
        render_group(build_room_night_lamp, samples=int(argv[1]) if len(argv) > 1 else 20)
    elif what == "render_dark":
        render_group(build_room_night_dark, samples=int(argv[1]) if len(argv) > 1 else 20)
    elif what == "render_dark_bedonly":
        render_group(lambda: build_room_night_dark(beats=("S40",)), samples=int(argv[1]) if len(argv) > 1 else 20)
    elif what == "render_macro_cold":
        render_group(build_macro_cold, samples=int(argv[1]) if len(argv) > 1 else 20)
    elif what == "render_macro_warm":
        render_group(build_macro_warm, samples=int(argv[1]) if len(argv) > 1 else 20)
    elif what == "render_empty_field":
        render_empty_field(samples=int(argv[1]) if len(argv) > 1 else 20)


if __name__ == "__main__":
    main()
