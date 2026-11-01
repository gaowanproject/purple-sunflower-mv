# -*- coding: utf-8 -*-
"""
character.py — stylised anime-proportion silhouette figures for the MV.

The MV never shows faces: humans appear only as clean silhouettes / rim-lit shapes.
All figures stand on Z=0 and face +Y in local space; rotate the returned object.
Each figure is ONE mesh object with 2 materials (body, hair).

    import lib, character
    g = character.figure("Girl", variant="girl", pose="stand", height=1.58)
    g.location = (0, 3, 0); g.rotation_euler = (0, 0, math.pi)
    character.idle(g, amp=0.01, keys=(1, 72))
"""
import bpy, bmesh, math, random
from mathutils import Vector, Matrix
import lib


# --------------------------------------------------------------------------- primitives
def _cone(bm, p0, p1, r0, r1, segments=10, mat=0):
    p0, p1 = Vector(p0), Vector(p1)
    d = p1 - p0
    L = d.length
    if L < 1e-6:
        return
    q = d.to_track_quat("Z", "Y")
    M = Matrix.Translation((p0 + p1) * 0.5) @ q.to_matrix().to_4x4()
    n0 = len(bm.faces)
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments,
                          radius1=r0, radius2=r1, depth=L, matrix=M)
    for f in bm.faces[n0:]:
        f.material_index = mat
        f.smooth = True


def _sphere(bm, center, radius, scale=(1, 1, 1), segments=16, rings=10, mat=0, rot=None):
    M = Matrix.Translation(center)
    if rot:
        M = M @ (Matrix.Rotation(rot[2], 4, "Z") @ Matrix.Rotation(rot[1], 4, "Y") @
                 Matrix.Rotation(rot[0], 4, "X"))
    M = M @ Matrix.Diagonal((*scale, 1.0))
    n0 = len(bm.faces)
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings,
                              radius=radius, matrix=M)
    for f in bm.faces[n0:]:
        f.material_index = mat
        f.smooth = True


def _box(bm, center, size, rot=(0, 0, 0), mat=0):
    M = Matrix.Translation(center) @ Matrix.Rotation(rot[2], 4, "Z") @ \
        Matrix.Rotation(rot[1], 4, "Y") @ Matrix.Rotation(rot[0], 4, "X") @ \
        Matrix.Diagonal((size[0] / 2, size[1] / 2, size[2] / 2, 1))
    n0 = len(bm.faces)
    bmesh.ops.create_cube(bm, size=2.0, matrix=M)
    for f in bm.faces[n0:]:
        f.material_index = mat


def _sheet(bm, rings, mat=0):
    vs = [[bm.verts.new(p) for p in ring] for ring in rings]
    for i in range(len(vs) - 1):
        a, b = vs[i], vs[i + 1]
        for j in range(len(a) - 1):
            f = bm.faces.new((a[j], b[j], b[j + 1], a[j + 1]))
            f.material_index = mat
            f.smooth = True


def _mats():
    body = bpy.data.materials.get("CHAR_body")
    if body is None:
        body = lib.principled("CHAR_body", (0.010, 0.010, 0.014), roughness=0.60,
                              specular=0.45, sheen=0.20)
    hair = bpy.data.materials.get("CHAR_hair")
    if hair is None:
        hair = lib.principled("CHAR_hair", (0.016, 0.011, 0.024), roughness=0.34,
                              specular=0.75, sheen=0.55)
    return body, hair


# --------------------------------------------------------------------------- figure
def figure(name="Girl", variant="girl", pose="stand", height=1.58,
           dress_len=0.40, hair_len=0.62, seed=0, facing=0.0, hand_reach=0.17):
    """Build one silhouette figure.  Feet on z=0, faces +Y.  Returns the object."""
    rng = random.Random(seed)
    girl = variant == "girl"
    H = height
    body_m, hair_m = _mats()
    bm = bmesh.new()

    # ---- proportions (stylised anime silhouette, ~7 heads)
    head_h = H * 0.135
    head_w = head_h * 0.74
    head_d = head_h * 0.86
    head_z = H - head_h * 0.52
    chin_z = head_z - head_h * 0.48
    sh_z = H * 0.800
    bust_z = H * 0.705
    waist_z = H * 0.610
    hip_z = H * 0.520
    knee_z = H * 0.285
    ankle_z = H * 0.035
    sh_x = H * 0.081 if girl else H * 0.095
    hip_x = H * 0.046 if girl else H * 0.052
    lean = {"stand": 0.0, "walk": 0.02, "run": 0.11, "reach_up": 0.0,
            "sit": 0.0}.get(pose, 0.0)

    # ---- head (slightly oval, tapering chin)
    _sphere(bm, (0, 0, head_z), head_h * 0.5,
            scale=(head_w / head_h, head_d / head_h, 1.0), segments=20, rings=14, mat=0)
    _sphere(bm, (0, head_w * 0.20, head_z - head_h * 0.28), head_h * 0.36,
            scale=(0.86, 0.96, 1.06), segments=14, rings=9, mat=0)
    # ears
    for sd in (-1, 1):
        _sphere(bm, (sd * head_w * 0.48, -head_d * 0.02, head_z - head_h * 0.04),
                head_h * 0.09, scale=(0.5, 0.95, 1.05), segments=8, rings=6, mat=0)

    # ---- hair
    if girl:
        # skull cap, sits slightly back and higher
        _sphere(bm, (0, -head_d * 0.07, head_z + head_h * 0.075), head_h * 0.545,
                scale=(head_w / head_h * 1.10, head_d / head_h * 1.06, 1.03),
                segments=20, rings=14, mat=1)
        # long hair sheet down the back (the strongest silhouette cue)
        rings = []
        nz = 12
        top = head_z + head_h * 0.46
        for i in range(nz + 1):
            t = i / nz
            z = top - t * (H * hair_len)
            spread = 1.0 + 0.30 * math.sin(math.pi * min(1.0, t * 1.15))
            w = head_w * (0.66 - 0.20 * t) * spread
            y = -head_d * (0.26 + 0.62 * t)
            wob = 0.014 * math.sin(t * 6.0)
            rings.append([(-w + wob, y, z), (-w * 0.36, y - 0.03, z),
                          (w * 0.36, y - 0.03, z), (w + wob, y, z)])
        _sheet(bm, rings, mat=1)
        # fringe: soft bangs across the forehead + two face-framing locks
        for sd in (-1, 1):
            rings = []
            for i in range(7):
                t = i / 6
                z = head_z + head_h * 0.34 - t * head_h * 1.15
                x = sd * head_w * (0.24 + 0.30 * t)
                y = head_d * (0.30 - 0.05 * t)
                rings.append([(x - head_w * 0.16, y, z), (x, y + head_w * 0.05, z),
                              (x + head_w * 0.04, y, z)])
            _sheet(bm, rings, mat=1)
        # side locks in front of the shoulders
        for sd in (-1, 1):
            rings = []
            for i in range(5):
                t = i / 4
                z = head_z - t * H * 0.20
                x = sd * head_w * (0.54 - 0.02 * t)
                y = -head_d * 0.06 + head_d * 0.10 * t
                rings.append([(x - head_w * 0.09, y - head_w * 0.05, z),
                              (x, y, z), (x + head_w * 0.05, y - head_w * 0.05, z)])
            _sheet(bm, rings, mat=1)
    else:
        _sphere(bm, (0, -head_d * 0.03, head_z + head_h * 0.088), head_h * 0.535,
                scale=(head_w / head_h * 1.05, head_d / head_h * 1.00, 1.00),
                segments=18, rings=12, mat=1)
        # short fringe
        for sd in (-1, 1):
            rings = []
            for i in range(5):
                t = i / 4
                z = head_z + head_h * 0.30 - t * head_h * 0.62
                x = sd * head_w * (0.20 + 0.22 * t)
                y = head_d * 0.33
                rings.append([(x - head_w * 0.16, y, z), (x, y + head_w * 0.04, z),
                              (x + head_w * 0.04, y, z)])
            _sheet(bm, rings, mat=1)
        for sd in (-1, 1):
            _sphere(bm, (sd * head_w * 0.36, -head_d * 0.10, head_z + head_h * 0.01),
                    head_h * 0.22, scale=(0.7, 1.0, 0.95), segments=10, rings=8, mat=1)

    # ---- neck & shoulders
    _cone(bm, (0, 0, chin_z - H * 0.004), (0, 0, sh_z + H * 0.020),
          H * 0.0165, H * 0.021, 10, 0)
    # trapezius / shoulder slope
    _sphere(bm, (0, lean, sh_z - H * 0.008), H * 0.050,
            scale=(sh_x / (H * 0.050) * 0.95, 0.60, 0.40), segments=16, rings=9, mat=0)

    if pose == "sit":
        hip_z_s = H * 0.30
        _cone(bm, (0, 0.02, hip_z_s), (0, lean, sh_z), H * 0.075, H * 0.052, 14, 0)
        _sphere(bm, (0, 0.02, hip_z_s), H * 0.062, scale=(1.15, 0.95, 0.55),
                segments=14, rings=8, mat=0)
        for sd in (-1, 1):
            hx = sd * hip_x
            _cone(bm, (hx, 0.03, hip_z_s + 0.01), (hx, H * 0.235, hip_z_s + 0.02),
                  H * 0.040, H * 0.032, 10, 0)
            _cone(bm, (hx, H * 0.235, hip_z_s + 0.02), (hx, H * 0.25, ankle_z),
                  H * 0.030, H * 0.023, 10, 0)
            _box(bm, (hx, H * 0.275, ankle_z * 0.6), (H * 0.048, H * 0.10, H * 0.032), mat=0)
            shoulder = Vector((sd * sh_x, lean, sh_z - H * 0.008))
            hand = Vector((sd * (sh_x + H * 0.035), -H * 0.10, hip_z_s + H * 0.03))
            elbow = (shoulder + hand) * 0.5 + Vector((0, H * 0.02, -H * 0.02))
            _cone(bm, shoulder, elbow, H * 0.024, H * 0.019, 9, 0)
            _cone(bm, elbow, hand, H * 0.018, H * 0.013, 9, 0)
            _sphere(bm, hand, H * 0.023, scale=(0.9, 1.25, 0.8), segments=9, rings=6, mat=0)
        if girl:
            _cone(bm, (0, 0.02, hip_z_s + H * 0.03), (0, 0.02, hip_z_s - H * 0.055),
                  H * 0.058, H * 0.105, 16, 0)
    else:
        # torso
        _cone(bm, (0, lean * 0.5, waist_z), (0, lean, sh_z - H * 0.02),
              H * 0.062, H * 0.082, 16, 0)
        _sphere(bm, (0, lean, bust_z), H * 0.048, scale=(1.18, 0.86, 0.75),
                segments=14, rings=8, mat=0)
        _sphere(bm, (0, lean * 0.35, hip_z), H * 0.058, scale=(1.18, 0.90, 0.62),
                segments=14, rings=8, mat=0)
        # legs
        leg_off = [(0.0, 0.0), (0.0, 0.0)]
        if pose == "walk":
            leg_off = [(0.0, 0.13), (0.0, -0.12)]
        elif pose == "run":
            leg_off = [(0.10, 0.26), (-0.08, -0.22)]
        for sd, (dx, dy) in zip((-1, 1), leg_off):
            hx = sd * hip_x
            knee = Vector((hx + dx * 0.45, lean * 0.3 + dy * 0.55, knee_z))
            ankle = Vector((hx + dx, dy, ankle_z))
            _cone(bm, (hx, lean * 0.3, hip_z - H * 0.015), knee,
                  H * 0.040, H * 0.029, 10, 0)
            _cone(bm, knee, ankle, H * 0.029, H * 0.019, 10, 0)
            _box(bm, (hx + dx, dy + H * 0.030, ankle_z * 0.55),
                 (H * 0.046, H * 0.098, H * 0.036), mat=0)
        if girl:
            _cone(bm, (0, lean * 0.35, hip_z + H * 0.035),
                  (0, lean * 0.35, hip_z - H * dress_len),
                  H * 0.058, H * 0.108, 20, 0)
        # arms
        arm_off = [(0.0, 0.0), (0.0, 0.0)]
        if pose == "walk":
            arm_off = [(0.0, -0.12), (0.0, 0.12)]
        elif pose == "run":
            arm_off = [(-0.05, -0.24), (0.05, 0.22)]
        for sd, (dx, dy) in zip((-1, 1), arm_off):
            sx = sd * sh_x * 0.92
            shoulder = Vector((sx, lean, sh_z - H * 0.006))
            if pose == "hold":
                hand = Vector((sd * hand_reach, 0.045, H * 0.615))
                elbow = (shoulder + hand) * 0.5 + Vector((0, 0.012, -H * 0.048))
            elif pose == "reach_up":
                hand = Vector((sx * 1.15, H * 0.02, sh_z + H * 0.13))
                elbow = (shoulder + hand) * 0.5 + Vector((0, -H * 0.015, -H * 0.015))
            elif pose == "reach_out":
                hand = Vector((sd * (sh_x + H * 0.14), H * 0.045, sh_z - H * 0.02))
                elbow = (shoulder + hand) * 0.5 + Vector((0, 0.01, -H * 0.035))
            else:
                elbow = Vector((sx + sd * H * 0.020 + dx, lean + dy * 0.5, waist_z + H * 0.005))
                hand = Vector((sx + sd * H * 0.030 + dx * 1.6, lean + dy,
                               hip_z + H * 0.055))
            _cone(bm, shoulder, elbow, H * 0.025, H * 0.019, 9, 0)
            _cone(bm, elbow, hand, H * 0.018, H * 0.0125, 9, 0)
            _sphere(bm, hand, H * 0.021, scale=(0.85, 1.3, 0.75), segments=9, rings=6, mat=0)

    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    lib.scene().collection.objects.link(ob)
    me.materials.append(body_m)
    me.materials.append(hair_m)
    ob.rotation_euler = (0, 0, facing)
    return ob


# --------------------------------------------------------------------------- animation
def idle(ob, amp=0.011, phase=0.0, keys=None, period=3.6):
    keys = keys or (1, 48, 96)
    rz = ob.rotation_euler[2]
    lib._set_interp("BEZIER")
    for f in keys:
        t = (f - keys[0]) / 24.0
        a = amp * math.sin(phase + 2 * math.pi * t / period)
        ob.rotation_euler = (a * 0.5, a, rz)
        ob.keyframe_insert("rotation_euler", frame=f)
    return ob


def walk_path(ob, keys, interp="LINEAR"):
    lib._set_interp(interp)
    for f, loc, rz in keys:
        ob.location = loc
        ob.rotation_euler = (0, 0, math.radians(rz))
        ob.keyframe_insert("location", frame=f)
        ob.keyframe_insert("rotation_euler", frame=f)
    return ob


def two_people(name="Couple", variant_a="girl", variant_b="boy", gap=None,
               pose_a="stand", pose_b="stand", height_a=1.57, height_b=1.72, facing=0.0):
    """Two figures side by side.  pose="hold" makes their inner hands meet."""
    if pose_a == "hold" or pose_b == "hold":
        gap = gap if gap else 0.34
        a = figure(name + "_A", variant=variant_a, pose="hold", height=height_a,
                   hand_reach=gap / 2)
        b = figure(name + "_B", variant=variant_b, pose="hold", height=height_b,
                   hand_reach=gap / 2)
    else:
        gap = gap if gap else 0.62
        a = figure(name + "_A", variant=variant_a, pose=pose_a, height=height_a)
        b = figure(name + "_B", variant=variant_b, pose=pose_b, height=height_b)
    a.location = (-gap / 2, 0, 0)
    b.location = (gap / 2, 0, 0)
    a.rotation_euler = (0, 0, facing)
    b.rotation_euler = (0, 0, facing)
    return a, b
