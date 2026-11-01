# -*- coding: utf-8 -*-
"""
lib.py — shared look-dev library for the MV "紫色の向日葵 / Purple Sunflower".
Blender 5.2.3 LTS, EEVEE.  Every set module imports this; do not fork it.

Conventions
-----------
* Everything animates on ABSOLUTE frames (24 fps).  shot['f0']..shot['f1'].
* Render output: PNG RGB 8bit, 1920x1080, AgX view transform, look "None".
* No bloom / no grain / no vignette in 3D.  The compositor adds those.
* Colour worlds are named "gold", "violet", "night", "cold".
"""
import bpy, bmesh, math, random, os
from mathutils import Vector, Euler, Matrix

FPS = 24
RES_X, RES_Y = 1920, 1080
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --------------------------------------------------------------------------- scene
def reset():
    """Wipe the file down to an empty scene."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    sc.render.fps = FPS
    sc.render.fps_base = 1.0
    sc.frame_start = 1
    sc.frame_end = 6551
    return sc


def scene():
    return bpy.context.scene


def setup_render(samples=24, resolution=(RES_X, RES_Y), exposure=0.0, look="None",
                 view="AgX", motion_blur=False, transparent=False):
    sc = scene()
    r = sc.render
    r.engine = "BLENDER_EEVEE"
    r.resolution_x, r.resolution_y = resolution
    r.resolution_percentage = 100
    r.fps = FPS
    r.film_transparent = transparent
    r.use_persistent_data = True
    r.use_motion_blur = motion_blur
    r.filter_size = 1.30
    try:
        sc.eevee.taa_render_samples = samples
    except Exception:
        pass
    for attr, val in (("use_raytracing", True), ("use_shadows", True)):
        try:
            setattr(sc.eevee, attr, val)
        except Exception:
            pass
    try:
        sc.eevee.use_volumetric_shadows = True
    except Exception:
        pass
    try:
        sc.eevee.volumetric_tile_size = "4"
        sc.eevee.volumetric_samples = 64
        sc.eevee.volumetric_start = 0.5
        sc.eevee.volumetric_end = 220.0
    except Exception:
        pass
    try:
        sc.eevee.bokeh_max_size = 120.0
    except Exception:
        pass
    # colour management (names differ between builds -> be defensive)
    try:
        sc.view_settings.view_transform = view
    except Exception:
        pass
    try:
        sc.view_settings.look = look
    except Exception:
        try:
            sc.view_settings.look = "None"
        except Exception:
            pass
    sc.view_settings.exposure = exposure
    sc.view_settings.gamma = 1.0
    im = r.image_settings
    im.file_format = "PNG"
    im.color_mode = "RGB"
    im.color_depth = "8"
    im.compression = 12
    return sc


# --------------------------------------------------------------------------- materials
def _mat(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    return m


def principled(name, color, roughness=0.55, metallic=0.0, emission=None,
               emission_strength=0.0, specular=0.4, subsurface=0.0,
               sheen=0.0, alpha=1.0):
    m = _mat(name)
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    def setin(key, val):
        if key in bsdf.inputs:
            bsdf.inputs[key].default_value = val
    setin("Base Color", (*color, 1.0))
    setin("Roughness", roughness)
    setin("Metallic", metallic)
    setin("Specular IOR Level", specular)
    setin("Sheen Weight", sheen)
    setin("Subsurface Weight", subsurface)
    if emission is not None:
        setin("Emission Color", (*emission, 1.0))
        setin("Emission Strength", emission_strength)
    if alpha < 1.0:
        setin("Alpha", alpha)
        try:
            m.surface_render_method = "DITHERED"
        except Exception:
            pass
    return m


def emission(name, color, strength=1.0):
    m = _mat(name)
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    em.location = (-100, 0)
    em.inputs["Color"].default_value = (*color, 1.0)
    em.inputs["Strength"].default_value = strength
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    return m


def gradient_mat(name, c_bottom, c_top, strength=1.0, axis="Z", noise_scale=0.0,
                 noise_amt=0.0, c_noise=None):
    """Vertical (world Z) gradient emission/BSDF mix — used for sky domes, suns, haze."""
    m = _mat(name)
    nt = m.node_tree
    nt.nodes.clear()
    N = nt.nodes
    out = N.new("ShaderNodeOutputMaterial"); out.location = (700, 0)
    tex = N.new("ShaderNodeTexCoord"); tex.location = (-1100, 0)
    sep = N.new("ShaderNodeSeparateXYZ"); sep.location = (-900, 0)
    nt.links.new(tex.outputs["Generated"], sep.inputs[0])
    mapr = N.new("ShaderNodeMapRange"); mapr.location = (-700, 0)
    mapr.inputs["From Min"].default_value = 0.0
    mapr.inputs["From Max"].default_value = 1.0
    nt.links.new(sep.outputs["Z" if axis == "Z" else ("Y" if axis == "Y" else "X")], mapr.inputs["Value"])
    ramp = N.new("ShaderNodeValToRGB"); ramp.location = (-480, 0)
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (*c_bottom, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (*c_top, 1.0)
    nt.links.new(mapr.outputs["Result"], ramp.inputs["Fac"])
    em = N.new("ShaderNodeEmission"); em.location = (450, 0)
    em.inputs["Strength"].default_value = strength
    src = ramp.outputs["Color"]
    if noise_scale > 0:
        noise = N.new("ShaderNodeTexNoise"); noise.location = (-700, -300)
        noise.inputs["Scale"].default_value = noise_scale
        noise.inputs["Detail"].default_value = 6.0
        nt.links.new(tex.outputs["Generated"], noise.inputs["Vector"])
        mix = N.new("ShaderNodeMixRGB"); mix.location = (-250, 0)
        mix.blend_type = "MIX"
        mix.inputs["Fac"].default_value = noise_amt
        nt.links.new(ramp.outputs["Color"], mix.inputs["Color1"])
        mix.inputs["Color2"].default_value = (*(c_noise or c_top), 1.0)
        src = mix.outputs["Color"]
    nt.links.new(src, em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    m.use_backface_culling = False
    return m


# --------------------------------------------------------------------------- sky / world
def sky_dome(name="SkyDome", radius=420.0, c_horizon=(1.0, 0.62, 0.30),
             c_mid=(0.55, 0.55, 0.85), c_zenith=(0.10, 0.14, 0.42),
             sun_dir=(0.0, -0.9, 0.25), sun_color=(1.0, 0.85, 0.6),
             sun_power=260.0, sun_size=0.999, glow=1.0, strength=1.0,
             cloud=None, star=None, horizon_boost=0.0,
             sun_exp=900.0, glow_exp=8.0):
    """sun_dir = unit vector pointing FROM the scene TOWARD the sun (world space)."""
    """Stylised sky dome with baked sun disc + halo.  Normals point inward."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=64, v_segments=32, radius=radius)
    bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    scene().collection.objects.link(obj)
    obj.visible_shadow = False
    obj.visible_diffuse = False
    obj.visible_glossy = False

    m = bpy.data.materials.new(name + "_mat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N = nt.nodes
    out = N.new("ShaderNodeOutputMaterial"); out.location = (900, 0)
    geo = N.new("ShaderNodeNewGeometry"); geo.location = (-1650, 0)
    # Incoming points from the surface towards the camera -> negate to get the
    # viewing direction (needed for both gradient and sun dot).
    negdir = N.new("ShaderNodeVectorMath"); negdir.location = (-1450, 150)
    negdir.operation = "SCALE"; negdir.inputs["Scale"].default_value = -1.0
    nt.links.new(geo.outputs["Incoming"], negdir.inputs[0])
    sep = N.new("ShaderNodeSeparateXYZ"); sep.location = (-1250, 0)
    nt.links.new(negdir.outputs["Vector"], sep.inputs[0])
    mapr = N.new("ShaderNodeMapRange"); mapr.location = (-1000, 100)
    mapr.inputs["From Min"].default_value = -0.35
    mapr.inputs["From Max"].default_value = 0.95
    mapr.clamp = True
    nt.links.new(sep.outputs["Z"], mapr.inputs["Value"])
    ramp = N.new("ShaderNodeValToRGB"); ramp.location = (-780, 100)
    cr = ramp.color_ramp
    cr.interpolation = "EASE"
    cr.elements[0].position = 0.0; cr.elements[0].color = (*c_horizon, 1.0)
    cr.elements[1].position = 1.0; cr.elements[1].color = (*c_zenith, 1.0)
    e = cr.elements.new(0.42); e.color = (*c_mid, 1.0)
    nt.links.new(mapr.outputs["Result"], ramp.inputs["Fac"])

    # sun disc + halo from dot(incoming, sun_dir)
    sdir = N.new("ShaderNodeCombineXYZ"); sdir.location = (-1200, -300)
    v = Vector(sun_dir).normalized()
    sdir.inputs[0].default_value = v.x
    sdir.inputs[1].default_value = v.y
    sdir.inputs[2].default_value = v.z
    dot = N.new("ShaderNodeVectorMath"); dot.location = (-1000, -300)
    dot.operation = "DOT_PRODUCT"
    nt.links.new(negdir.outputs["Vector"], dot.inputs[0])
    nt.links.new(sdir.outputs["Vector"], dot.inputs[1])
    # halo: pow(clamp(dot), n)
    powr = N.new("ShaderNodeMath"); powr.location = (-800, -300)
    powr.operation = "POWER"; powr.inputs[1].default_value = glow_exp
    clamp = N.new("ShaderNodeMath"); clamp.location = (-950, -450)
    clamp.operation = "MAXIMUM"; clamp.inputs[1].default_value = 0.0
    nt.links.new(dot.outputs["Value"], clamp.inputs[0])
    nt.links.new(clamp.outputs["Value"], powr.inputs[0])
    mul = N.new("ShaderNodeMath"); mul.location = (-620, -300)
    mul.operation = "MULTIPLY"; mul.inputs[1].default_value = glow
    nt.links.new(powr.outputs["Value"], mul.inputs[0])
    # sharp disc
    sharp = N.new("ShaderNodeMath"); sharp.location = (-800, -520)
    sharp.operation = "POWER"; sharp.inputs[1].default_value = sun_exp
    nt.links.new(clamp.outputs["Value"], sharp.inputs[0])
    disc = N.new("ShaderNodeMath"); disc.location = (-620, -520)
    disc.operation = "MULTIPLY"; disc.inputs[1].default_value = sun_power
    nt.links.new(sharp.outputs["Value"], disc.inputs[0])
    add = N.new("ShaderNodeMath"); add.location = (-440, -400)
    add.operation = "ADD"
    nt.links.new(mul.outputs["Value"], add.inputs[0])
    nt.links.new(disc.outputs["Value"], add.inputs[1])
    sun_col = N.new("ShaderNodeMixRGB"); sun_col.location = (-250, -400)
    sun_col.blend_type = "MULTIPLY"
    sun_col.inputs["Fac"].default_value = 1.0
    sun_col.inputs["Color1"].default_value = (*sun_color, 1.0)
    nt.links.new(add.outputs["Value"], sun_col.inputs["Color2"])

    # optional clouds band
    base = ramp.outputs["Color"]
    if cloud is not None:
        ccol, camt, cscale, cheight = cloud
        noise = N.new("ShaderNodeTexNoise"); noise.location = (-1000, 400)
        noise.inputs["Scale"].default_value = cscale
        noise.inputs["Detail"].default_value = 8.0
        noise.inputs["Roughness"].default_value = 0.62
        coord = N.new("ShaderNodeTexCoord"); coord.location = (-1250, 400)
        nt.links.new(coord.outputs["Generated"], noise.inputs["Vector"])
        cband = N.new("ShaderNodeMath"); cband.location = (-800, 400)
        cband.operation = "POWER"
        cband.inputs[1].default_value = 2.4
        t = N.new("ShaderNodeMath"); t.location = (-950, 600)
        t.operation = "MULTIPLY"; t.inputs[1].default_value = 3.2
        nt.links.new(mapr.outputs["Result"], t.inputs[0])
        zz = N.new("ShaderNodeMath"); zz.location = (-800, 600)
        zz.operation = "SUBTRACT"; zz.inputs[0].default_value = cheight
        nt.links.new(t.outputs["Value"], zz.inputs[1])
        zz2 = N.new("ShaderNodeMath"); zz2.location = (-650, 600)
        zz2.operation = "MULTIPLY"; zz2.inputs[1].default_value = -1.0
        nt.links.new(zz.outputs["Value"], zz2.inputs[0])
        sr = N.new("ShaderNodeMapRange"); sr.location = (-500, 600)
        sr.inputs["From Min"].default_value = 0.0; sr.inputs["From Max"].default_value = 1.0
        sr.clamp = True
        nt.links.new(zz2.outputs["Value"], sr.inputs["Value"])
        nt.links.new(noise.outputs["Fac"], cband.inputs[0])
        cm = N.new("ShaderNodeMixRGB"); cm.location = (-650, 300)
        cm.blend_type = "SCREEN"; cm.inputs["Fac"].default_value = 0.6
        nt.links.new(ramp.outputs["Color"], cm.inputs["Color1"])
        cm.inputs["Color2"].default_value = (*ccol, 1.0)
        fac = N.new("ShaderNodeMath"); fac.location = (-320, 300)
        fac.operation = "MULTIPLY"; fac.inputs[1].default_value = camt
        nt.links.new(cband.outputs["Value"], fac.inputs[0])
        cm2 = N.new("ShaderNodeMixRGB"); cm2.location = (-150, 200)
        cm2.blend_type = "MIX"
        nt.links.new(fac.outputs["Value"], cm2.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], cm2.inputs["Color1"])
        nt.links.new(cm.outputs["Color"], cm2.inputs["Color2"])
        base = cm2.outputs["Color"]

    if star:
        # star field from 3D white noise on the incoming direction
        sc_ = N.new("ShaderNodeVectorMath"); sc_.location = (-1250, -900)
        sc_.operation = "SCALE"; sc_.inputs["Scale"].default_value = star[1]
        nt.links.new(negdir.outputs["Vector"], sc_.inputs[0])
        wn = N.new("ShaderNodeTexWhiteNoise"); wn.location = (-1050, -900)
        wn.noise_dimensions = "3D"
        nt.links.new(sc_.outputs["Vector"], wn.inputs["Vector"])
        thr = N.new("ShaderNodeMapRange"); thr.location = (-850, -900)
        thr.inputs["From Min"].default_value = star[2]
        thr.inputs["From Max"].default_value = 1.0
        thr.clamp = True
        nt.links.new(wn.outputs["Value"], thr.inputs["Value"])
        smul = N.new("ShaderNodeMath"); smul.location = (-650, -900)
        smul.operation = "MULTIPLY"; smul.inputs[1].default_value = star[0]
        nt.links.new(thr.outputs["Result"], smul.inputs[0])
        sstar = N.new("ShaderNodeMixRGB"); sstar.location = (-450, -900)
        sstar.blend_type = "ADD"; sstar.inputs["Fac"].default_value = 1.0
        sstar.inputs["Color1"].default_value = (0, 0, 0, 1)
        sstar.inputs["Color2"].default_value = (star[3], star[3], star[3], 1)
        nt.links.new(smul.outputs["Value"], sstar.inputs["Fac"])
        sbase = N.new("ShaderNodeMixRGB"); sbase.location = (-250, -820)
        sbase.blend_type = "ADD"; sbase.inputs["Fac"].default_value = 1.0
        nt.links.new(ramp.outputs["Color"], sbase.inputs["Color1"])
        nt.links.new(sstar.outputs["Color"], sbase.inputs["Color2"])
        base = sbase.outputs["Color"]

    addc = N.new("ShaderNodeMixRGB"); addc.location = (300, 0)
    addc.blend_type = "ADD"; addc.inputs["Fac"].default_value = 1.0
    nt.links.new(base, addc.inputs["Color1"])
    nt.links.new(sun_col.outputs["Color"], addc.inputs["Color2"])
    em = N.new("ShaderNodeEmission"); em.location = (600, 0)
    em.inputs["Strength"].default_value = strength
    nt.links.new(addc.outputs["Color"], em.inputs["Color"])
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    obj.data.materials.append(m)
    return obj


def fog(density=0.0012, color=(1.0, 0.85, 0.65), anisotropy=0.3):
    """World volume haze (EEVEE volumetrics)."""
    w = bpy.data.worlds.new("FogWorld")
    scene().world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    vol = nt.nodes.new("ShaderNodeVolumeScatter")
    vol.inputs["Color"].default_value = (*color, 1.0)
    vol.inputs["Density"].default_value = density
    vol.inputs["Anisotropy"].default_value = anisotropy
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Color"].default_value = (*color, 1.0)
    bg.inputs["Strength"].default_value = 0.06
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return w


# --------------------------------------------------------------------------- lights
def fog(density=0.0012, color=(1.0, 0.85, 0.65), anisotropy=0.3,
        ambient=None, ambient_strength=0.55, world_volume=True):
    """World haze + ambient fill.  `ambient` colours the world background that
    EEVEE uses as ambient light (important: emissive sky domes do NOT light)."""
    w = bpy.data.worlds.new("World")
    scene().world = w
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    ac = ambient if ambient is not None else color
    bg.inputs["Color"].default_value = (*ac, 1.0)
    bg.inputs["Strength"].default_value = ambient_strength
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    if world_volume and density > 0:
        vol = nt.nodes.new("ShaderNodeVolumeScatter")
        vol.inputs["Color"].default_value = (*color, 1.0)
        vol.inputs["Density"].default_value = density
        vol.inputs["Anisotropy"].default_value = anisotropy
        nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    return w


def fill_light(energy=300.0, color=(1.0, 0.95, 0.9), size=60.0, height=14.0,
               target=(0, 0, 1.0), name="Fill"):
    """Big soft overhead card used to lift silhouettes / shadow sides."""
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.color = color
    ld.size = size
    ld.shape = "SQUARE"
    ob = bpy.data.objects.new(name, ld)
    scene().collection.objects.link(ob)
    ob.location = (0.0, 0.0, height)
    try:
        ld.volume_factor = 0.03
    except Exception:
        pass
    look_at(ob, target)
    return ob


def sun_light(energy=4.0, direction=(0.2, -0.6, -0.5), color=(1.0, 0.86, 0.66), angle_deg=2.0):
    ld = bpy.data.lights.new("Sun", "SUN")
    ld.energy = energy
    ld.color = color
    ld.angle = math.radians(angle_deg)
    try:
        ld.use_shadow = True
    except Exception:
        pass
    ob = bpy.data.objects.new("Sun", ld)
    scene().collection.objects.link(ob)
    v = Vector(direction).normalized()
    ob.rotation_euler = v.to_track_quat("Z", "Y").to_euler()
    ob.location = (0, 0, 30)
    return ob


def area_light(name, loc, target=(0, 0, 0), energy=200.0, size=4.0,
               color=(1.0, 0.95, 0.9), shape="SQUARE"):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy = energy
    ld.color = color
    ld.size = size
    ld.shape = shape
    ob = bpy.data.objects.new(name, ld)
    scene().collection.objects.link(ob)
    ob.location = loc
    look_at(ob, target)
    return ob


def point_light(name, loc, energy=40.0, radius=0.4, color=(1.0, 0.9, 0.8)):
    ld = bpy.data.lights.new(name, "POINT")
    ld.energy = energy
    ld.color = color
    ld.shadow_soft_size = radius
    ob = bpy.data.objects.new(name, ld)
    scene().collection.objects.link(ob)
    ob.location = loc
    return ob


# --------------------------------------------------------------------------- helpers
def look_at(obj, target, roll=0.0):
    d = Vector(target) - obj.location
    q = d.to_track_quat("-Z", "Y")
    e = q.to_euler()
    if roll:
        e.z += roll
    obj.rotation_euler = e
    return obj


def ground(name="Ground", size=900.0, color_a=(0.25, 0.20, 0.10),
           color_b=(0.12, 0.10, 0.06), roughness=0.9, z=0.0,
           noise_scale=6.0, noise_amt=0.5):
    bpy.ops.mesh.primitive_plane_add(size=size, location=(0, 0, z))
    ob = bpy.context.object
    ob.name = name
    m = bpy.data.materials.new(name + "_mat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N = nt.nodes
    out = N.new("ShaderNodeOutputMaterial"); out.location = (600, 0)
    bsdf = N.new("ShaderNodeBsdfPrincipled"); bsdf.location = (300, 0)
    bsdf.inputs["Roughness"].default_value = roughness
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    tex = N.new("ShaderNodeTexCoord"); tex.location = (-700, 0)
    noise = N.new("ShaderNodeTexNoise"); noise.location = (-500, 0)
    noise.inputs["Scale"].default_value = noise_scale
    noise.inputs["Detail"].default_value = 8.0
    nt.links.new(tex.outputs["Generated"], noise.inputs["Vector"])
    ramp = N.new("ShaderNodeValToRGB"); ramp.location = (-280, 0)
    ramp.color_ramp.elements[0].color = (*color_b, 1.0)
    ramp.color_ramp.elements[1].color = (*color_a, 1.0)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    mix = N.new("ShaderNodeMixRGB"); mix.location = (0, 0)
    mix.blend_type = "MIX"; mix.inputs["Fac"].default_value = noise_amt
    nt.links.new(ramp.outputs["Color"], mix.inputs["Color1"])
    mix.inputs["Color2"].default_value = (*color_a, 1.0)
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    ob.data.materials.append(m)
    return ob


def camera(loc, target, lens=35.0, fstop=2.8, focus_target=None, focus_distance=None,
           sensor=36.0, shift=(0.0, 0.0), name="Cam"):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_width = sensor
    cd.shift_x, cd.shift_y = shift
    cd.clip_start = 0.05
    cd.clip_end = 2000.0
    ob = bpy.data.objects.new(name, cd)
    scene().collection.objects.link(ob)
    ob.location = loc
    look_at(ob, target)
    if fstop:
        cd.dof.use_dof = True
        cd.dof.aperture_fstop = fstop
        cd.dof.aperture_blades = 6
        if focus_target is not None:
            if hasattr(focus_target, "name"):
                cd.dof.focus_object = focus_target
            else:
                cd.dof.focus_distance = (Vector(focus_target) - Vector(loc)).length
        elif focus_distance is not None:
            cd.dof.focus_distance = focus_distance
    scene().camera = ob
    return ob


def _set_interp(interp):
    try:
        bpy.context.preferences.edit.keyframe_new_interpolation_type = interp
    except Exception:
        pass


def anim_camera(cam, keys, interp="BEZIER", lens_keys=None, focus=None):
    """keys: [(frame, loc, target)] or [(frame, loc, target, focus_dist)]"""
    _set_interp(interp)
    cd = cam.data
    for k in keys:
        f, loc, target = k[0], k[1], k[2]
        cam.location = loc
        look_at(cam, target)
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)
        if len(k) > 3 and k[3] is not None:
            cd.dof.focus_distance = k[3]
            cd.dof.keyframe_insert("focus_distance", frame=f)
    if lens_keys:
        for f, l in lens_keys:
            cd.lens = l
            cd.keyframe_insert("lens", frame=f)
    return cam


def anim_obj(ob, keys, interp="BEZIER", path="location"):
    """keys: [(frame, value)] for a single transform channel or (frame, (x,y,z))."""
    _set_interp(interp)
    for f, val in keys:
        setattr(ob, path, val)
        ob.keyframe_insert(path, frame=f)
    return ob


def empty(name, loc=(0, 0, 0)):
    ob = bpy.data.objects.new(name, None)
    scene().collection.objects.link(ob)
    ob.location = loc
    return ob


def mesh_object(name, verts, faces, mat=None, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    ob = bpy.data.objects.new(name, me)
    scene().collection.objects.link(ob)
    if mat:
        me.materials.append(mat)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return ob


# --------------------------------------------------------------------------- sunflower
def ground_mist(name="Mist", height=1.15, density=0.06, color=(1.0, 0.88, 0.70),
               size=140.0, z0=-0.2, anisotropy=0.25):
    """A flattened volume box near the ground: hides stems and adds atmosphere."""
    bbox = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x *= size
        v.co.y *= size
        v.co.z = z0 + (v.co.z + 0.5) * height
    bm.to_mesh(bbox)
    bm.free()
    ob = bpy.data.objects.new(name, bbox)
    scene().collection.objects.link(ob)
    ob.visible_shadow = False
    m = bpy.data.materials.new(name + "_mat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    vol = nt.nodes.new("ShaderNodeVolumeScatter")
    vol.inputs["Color"].default_value = (*color, 1.0)
    vol.inputs["Density"].default_value = density
    vol.inputs["Anisotropy"].default_value = anisotropy
    nt.links.new(vol.outputs["Volume"], out.inputs["Volume"])
    bbox.materials.append(m)
    return ob


def hills(name="Hills", distance=165.0, height=7.0, color=(0.35, 0.26, 0.14),
          seed=2, segments=160, emission=0.15, thickness=0.0, z_offset=-2.0):
    """A soft distant ridge ring used to close the horizon (fog does the blending)."""
    import bpy as _bpy
    rng = random.Random(seed)
    bm = bmesh.new()
    rings = []
    phase = [rng.uniform(0, 6.28) for _ in range(4)]
    for i in range(segments + 1):
        a = 2 * math.pi * i / segments
        # layered sine ridge
        hh = (0.55 * math.sin(a * 2 + phase[0]) + 0.30 * math.sin(a * 5 + phase[1]) +
              0.18 * math.sin(a * 11 + phase[2]) + 0.10 * math.sin(a * 23 + phase[3]))
        hh = max(0.06, 0.55 + 0.45 * hh) * height
        r = distance * (1.0 + 0.06 * math.sin(a * 3 + phase[1]))
        x, y = math.cos(a) * r, math.sin(a) * r
        v0 = bm.verts.new((x, y, z_offset))
        v1 = bm.verts.new((x, y, z_offset + hh))
        rings.append((v0, v1))
    for i in range(segments):
        a0, a1 = rings[i], rings[i + 1]
        f = bm.faces.new((a0[0], a1[0], a1[1], a0[1]))
        f.smooth = True
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    scene().collection.objects.link(ob)
    ob.visible_shadow = False
    m = bpy.data.materials.new(name + "_mat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N = nt.nodes
    out = N.new("ShaderNodeOutputMaterial"); out.location = (400, 0)
    em = N.new("ShaderNodeEmission"); em.location = (200, 0)
    em.inputs["Color"].default_value = (*color, 1.0)
    em.inputs["Strength"].default_value = max(0.35, emission)
    nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
    me.materials.append(m)
    return ob


def _sunflower_petal_mat(name="SF_petal", c_base=(0.9, 0.35, 0.02), c_tip=(1.0, 0.82, 0.22),
                         emission_amt=0.14):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N = nt.nodes
    out = N.new("ShaderNodeOutputMaterial"); out.location = (700, 0)
    bsdf = N.new("ShaderNodeBsdfPrincipled"); bsdf.location = (380, 0)
    bsdf.inputs["Roughness"].default_value = 0.38
    if "Sheen Weight" in bsdf.inputs:
        bsdf.inputs["Sheen Weight"].default_value = 0.55
    if "Sheen Roughness" in bsdf.inputs:
        bsdf.inputs["Sheen Roughness"].default_value = 0.45
    if "Subsurface Weight" in bsdf.inputs:
        bsdf.inputs["Subsurface Weight"].default_value = 0.32
        if "Subsurface Radius" in bsdf.inputs:
            bsdf.inputs["Subsurface Radius"].default_value = (0.06, 0.035, 0.012)
        if "Subsurface Scale" in bsdf.inputs:
            bsdf.inputs["Subsurface Scale"].default_value = 0.08
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    uvn = N.new("ShaderNodeUVMap"); uvn.location = (-900, 0)
    uvn.uv_map = "UVMap"
    sep = N.new("ShaderNodeSeparateXYZ"); sep.location = (-700, 0)
    nt.links.new(uvn.outputs["UV"], sep.inputs[0])
    ramp = N.new("ShaderNodeValToRGB"); ramp.location = (-480, 0)
    cr = ramp.color_ramp
    cr.interpolation = "EASE"
    cr.elements[0].position = 0.0; cr.elements[0].color = (*c_base, 1.0)
    cr.elements[1].position = 1.0; cr.elements[1].color = (*c_tip, 1.0)
    e = cr.elements.new(0.55); e.color = tuple((a * 0.5 + b * 0.5) for a, b in zip(c_base, c_tip)) + (1.0,)
    nt.links.new(sep.outputs["Y"], ramp.inputs["Fac"])
    # subtle veining / mottling
    noise = N.new("ShaderNodeTexNoise"); noise.location = (-900, -320)
    noise.inputs["Scale"].default_value = 42.0
    noise.inputs["Detail"].default_value = 4.0
    comb = N.new("ShaderNodeCombineXYZ"); comb.location = (-700, -320)
    nt.links.new(sep.outputs["X"], comb.inputs["X"])
    nt.links.new(sep.outputs["Y"], comb.inputs["Y"])
    comb.inputs["Z"].default_value = 0.0
    nt.links.new(comb.outputs["Vector"], noise.inputs["Vector"])
    mix = N.new("ShaderNodeMixRGB"); mix.location = (-220, 60)
    mix.blend_type = "OVERLAY"; mix.inputs["Fac"].default_value = 0.22
    nt.links.new(ramp.outputs["Color"], mix.inputs["Color1"])
    nt.links.new(noise.outputs["Color"], mix.inputs["Color2"])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    # translucent glow: strongest mid/tip
    emcol = N.new("ShaderNodeMixRGB"); emcol.location = (100, -260)
    emcol.blend_type = "MIX"; emcol.inputs["Fac"].default_value = 0.85
    emcol.inputs["Color1"].default_value = (*c_base, 1.0)
    nt.links.new(ramp.outputs["Color"], emcol.inputs["Color2"])
    if "Emission Color" in bsdf.inputs:
        nt.links.new(emcol.outputs["Color"], bsdf.inputs["Emission Color"])
        bsdf.inputs["Emission Strength"].default_value = emission_amt
    return m


def _add_petal(bm, rot3, length, width, bend, segs, mat_index, uv_layer, twist=0.0):
    """Curved, cupped petal with a rounded tip and a rippled edge."""
    prof = [(-1.0, 0.50), (-0.72, 0.78), (-0.36, 0.95), (0.0, 1.0),
            (0.36, 0.95), (0.72, 0.78), (1.0, 0.50)]
    grid_v, grid_uv = [], []
    for i in range(segs + 1):
        t = i / segs
        y = t * length
        # profile: narrow at base, widest ~45%, softly tapered rounded tip
        taper = math.sin(math.pi * (0.055 + 0.90 * t)) ** 0.55
        taper *= (1.0 - 0.30 * max(0.0, t - 0.55) / 0.45)
        w = width * taper
        zc = bend * (t ** 2) * length * 1.9
        # gentle waviness along the edge
        rip = 0.045 * width * math.sin(t * 9.0 + 1.7)
        row, uvs = [], []
        for xx, cup in prof:
            cup_amt = (1.0 - cup) * 0.45          # centreline slightly raised
            local = Vector((xx * (w + rip * abs(xx)),
                            y + twist * (xx * abs(xx)) * 0.06,
                            zc - cup_amt * w * 0.55))
            row.append(bm.verts.new(rot3 @ local))
            uvs.append(((xx + 1.0) * 0.5, t))
        grid_v.append(row)
        grid_uv.append(uvs)
    for i in range(segs):
        a, b = grid_v[i], grid_v[i + 1]
        au, bu = grid_uv[i], grid_uv[i + 1]
        for j in range(len(a) - 1):
            f = bm.faces.new((a[j], b[j], b[j + 1], a[j + 1]))
            f.material_index = mat_index
            f.smooth = True
            for loop, uv in zip(f.loops, (au[j], bu[j], bu[j + 1], au[j + 1])):
                loop[uv_layer].uv = uv


def _disc_mat(name="SF_disc"):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N = nt.nodes
    out = N.new("ShaderNodeOutputMaterial"); out.location = (700, 0)
    bsdf = N.new("ShaderNodeBsdfPrincipled"); bsdf.location = (380, 0)
    bsdf.inputs["Roughness"].default_value = 0.72
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    tc = N.new("ShaderNodeTexCoord"); tc.location = (-900, 0)
    n1 = N.new("ShaderNodeTexNoise"); n1.location = (-700, 0)
    n1.inputs["Scale"].default_value = 180.0
    n1.inputs["Detail"].default_value = 6.0
    nt.links.new(tc.outputs["Object"], n1.inputs["Vector"])
    ramp = N.new("ShaderNodeValToRGB"); ramp.location = (-480, 0)
    ramp.color_ramp.elements[0].color = (0.105, 0.045, 0.020, 1.0)
    ramp.color_ramp.elements[1].color = (0.330, 0.150, 0.055, 1.0)
    e = ramp.color_ramp.elements.new(0.55)
    e.color = (0.200, 0.085, 0.032, 1.0)
    nt.links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bump = N.new("ShaderNodeBump"); bump.location = (150, -260)
    bump.inputs["Strength"].default_value = 0.55
    bump.inputs["Distance"].default_value = 0.006
    nt.links.new(n1.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def grass_patch(name="Grass", count=1400, area=(30, 30), seed=3, height=(0.05, 0.16),
                color_set="gold", mat=None):
    """One merged mesh of crossed grass tufts (cheap ground detail)."""
    import bpy as _bpy
    rng = random.Random(seed)
    if mat is None:
        mat = bpy.data.materials.new(name + "_mat")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        N = nt.nodes
        out = N.new("ShaderNodeOutputMaterial"); out.location = (500, 0)
        bsdf = N.new("ShaderNodeBsdfPrincipled"); bsdf.location = (250, 0)
        bsdf.inputs["Roughness"].default_value = 0.62
        if "Subsurface Weight" in bsdf.inputs:
            bsdf.inputs["Subsurface Weight"].default_value = 0.25
            if "Subsurface Scale" in bsdf.inputs:
                bsdf.inputs["Subsurface Scale"].default_value = 0.03
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        uvn = N.new("ShaderNodeUVMap"); uvn.location = (-700, 0)
        uvn.uv_map = "UVMap"
        sep = N.new("ShaderNodeSeparateXYZ"); sep.location = (-520, 0)
        nt.links.new(uvn.outputs["UV"], sep.inputs[0])
        ramp = N.new("ShaderNodeValToRGB"); ramp.location = (-320, 0)
        if color_set == "gold":
            ramp.color_ramp.elements[0].color = (0.055, 0.080, 0.020, 1.0)
            ramp.color_ramp.elements[1].color = (0.34, 0.30, 0.09, 1.0)
        elif color_set == "violet":
            ramp.color_ramp.elements[0].color = (0.035, 0.022, 0.050, 1.0)
            ramp.color_ramp.elements[1].color = (0.17, 0.09, 0.21, 1.0)
        else:
            ramp.color_ramp.elements[0].color = (0.07, 0.07, 0.06, 1.0)
            ramp.color_ramp.elements[1].color = (0.26, 0.24, 0.19, 1.0)
        nt.links.new(sep.outputs["Y"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    wx, wy = area
    for i in range(count):
        x = rng.uniform(-wx / 2, wx / 2)
        y = rng.uniform(-wy / 2, wy / 2)
        h = rng.uniform(*height)
        w = h * rng.uniform(0.10, 0.20)
        ang = rng.uniform(0, math.pi)
        for k in range(3):
            a = ang + k * math.pi / 3.0
            dx, dy = math.cos(a), math.sin(a)
            lean = rng.uniform(-0.12, 0.12)
            p0 = Vector((x - dx * w, y - dy * w, 0))
            p1 = Vector((x + dx * w, y + dy * w, 0))
            p2 = Vector((x + dx * w * 0.55 + lean * h, y + dy * w * 0.55, h))
            p3 = Vector((x - dx * w * 0.55 + lean * h, y - dy * w * 0.55, h * rng.uniform(0.85, 1.0)))
            vs = [bm.verts.new(p0), bm.verts.new(p1), bm.verts.new(p2), bm.verts.new(p3)]
            f = bm.faces.new(vs)
            for loop, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
                loop[uv_layer].uv = uv
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    scene().collection.objects.link(ob)
    me.materials.append(mat)
    return ob


def _petal_set(color_set="gold"):
    """Returns list of (petal_mat, disc_mat, stem_mat) palettes."""
    if color_set == "gold":
        pairs = [((0.72, 0.20, 0.005), (0.95, 0.62, 0.06)),
                 ((0.66, 0.16, 0.004), (0.92, 0.55, 0.03)),
                 ((0.80, 0.26, 0.008), (1.00, 0.70, 0.10)),
                 ((0.70, 0.21, 0.005), (0.96, 0.64, 0.12))]
    elif color_set == "violet":
        pairs = [((0.30, 0.06, 0.45), (0.86, 0.52, 1.00)),
                 ((0.20, 0.04, 0.36), (0.66, 0.34, 0.96)),
                 ((0.42, 0.12, 0.58), (0.95, 0.66, 1.00)),
                 ((0.26, 0.05, 0.40), (0.76, 0.42, 0.98))]
    elif color_set == "dead":       # dried, desaturated flower (intro / void)
        pairs = [((0.16, 0.10, 0.10), (0.42, 0.30, 0.34)),
                 ((0.20, 0.13, 0.12), (0.50, 0.36, 0.40))]
    else:
        pairs = [((0.85, 0.78, 0.62), (1.00, 0.96, 0.86))]
    mats = []
    for i, (c, t) in enumerate(pairs):
        emis = 0.05 if color_set == "gold" else (0.16 if color_set == "violet" else 0.04)
        mats.append((_sunflower_petal_mat(f"SF_petal_{color_set}_{i}", c, t, emis),
                     _disc_mat("SF_disc"),
                     principled(f"SF_stem_{color_set}", (0.018, 0.028, 0.014), roughness=0.85)))
    return mats


def sunflower(name="Sunflower", size=1.0, n_petals=21, petal_len=0.215, stem_len=1.42,
              head_tilt=32.0, pose_seed=0, stem_thickness=0.018, leaf=True,
              mats=None, head_azim=0.0, inner_ring=True):
    """Single-object procedural sunflower.  Materials: 0 petal, 1 disc, 2 stem."""
    import bpy as _bpy
    rng = random.Random(pose_seed)
    if mats is None:
        mats = _petal_set("gold")[0]
    m_petal, m_center, m_stem = mats
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    L = petal_len * size
    tilt = math.radians(head_tilt)
    nrm = Vector((math.sin(tilt) * math.sin(head_azim),
                  -math.sin(tilt) * math.cos(head_azim), math.cos(tilt)))
    head_rot = Vector((0, 0, 1)).rotation_difference(nrm).to_matrix()
    head_off = Vector((0, 0, stem_len * size))
    r0 = L * 0.34
    rings = [(n_petals, 1.0, 0.0, r0)]
    if inner_ring:
        rings.append((max(9, int(n_petals * 0.72)), 0.62, 0.10, r0 * 0.75))
    for (np_, lscale, ringz, rr) in rings:
        for i in range(np_):
            ang = 2 * math.pi * i / np_ + rng.uniform(-0.07, 0.07)
            rot = head_rot @ Matrix.Rotation(ang, 3, "Z")
            base = rot @ Vector((0.0, rr, ringz * L))
            nv0 = len(bm.verts)
            _add_petal(bm, rot, L * lscale * rng.uniform(0.92, 1.08), 0.078 * size,
                       rng.uniform(0.05, 0.11), 5, 0, uv_layer,
                       twist=rng.uniform(-0.5, 0.5))
            for v in bm.verts[nv0:]:
                v.co += base + head_off
    # seed disc (domed)
    n0 = len(bm.faces)
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=True, segments=28,
                          radius1=L * 0.56, radius2=L * 0.30, depth=0.075 * size,
                          matrix=Matrix.Translation(head_off) @ head_rot.to_4x4())
    for f in bm.faces[n0:]:
        f.material_index = 1
        f.smooth = True
    for l in bm.faces[n0:]:
        for loop in l.loops:
            loop[uv_layer].uv = (0.5, 0.5)
    # stem
    n0 = len(bm.faces)
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=8,
                          radius1=stem_thickness * size, radius2=stem_thickness * size * 0.7,
                          depth=stem_len * size,
                          matrix=Matrix.Translation((0, 0, stem_len * size / 2)))
    for f in bm.faces[n0:]:
        f.material_index = 2
        f.smooth = True
    if leaf:
        for k in range(3):
            w = 0.20 * size
            l = 0.52 * size
            zc = stem_len * size * (0.22 + 0.21 * k)
            ang = math.radians(rng.uniform(55, 125)) * (1 if k else -1)
            rot = (Matrix.Rotation(ang, 3, "Z") @
                   Matrix.Rotation(math.radians(rng.uniform(-40, 15)), 3, "Y"))
            base = Vector((0, 0, zc))
            quad = [(-w, 0, 0), (w, 0, 0), (w * 0.55, l, 0.07 * size), (-w * 0.55, l, 0.07 * size)]
            vs = [bm.verts.new(base + rot @ Vector(p)) for p in quad]
            f = bm.faces.new(vs)
            f.material_index = 2
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    scene().collection.objects.link(ob)
    me.materials.append(m_petal)
    me.materials.append(m_center)
    me.materials.append(m_stem)
    return ob


def sunflower_field(count=260, area=(26.0, 26.0), seed=7, scale_range=(0.85, 1.35),
                    color_set="gold", center=(0, 0), exclude_radius=0.0,
                    stem_random=(0.95, 1.45), dead_ratio=0.0, face_dir=(0.0, 1.0),
                    face_jitter=0.55, leaf=True):
    """face_dir: horizontal direction (world XY) the heads turn toward."""
    rng = random.Random(seed)
    fdx, fdy = face_dir
    base_az = math.atan2(fdy, -fdx)
    pals = _petal_set(color_set)
    dead = _petal_set("dead") if dead_ratio > 0 else None
    objs = []
    wx, wy = area
    for i in range(count):
        x = center[0] + rng.uniform(-wx / 2, wx / 2)
        y = center[1] + rng.uniform(-wy / 2, wy / 2)
        if exclude_radius and (x * x + y * y) ** 0.5 < exclude_radius:
            continue
        s = rng.uniform(*scale_range)
        mats = dead[0] if (dead and rng.random() < dead_ratio) else rng.choice(pals)
        ob = sunflower(name=f"SF{i:05d}", size=s,
                       n_petals=rng.choice([25, 27, 29, 31]),
                       stem_len=rng.uniform(*stem_random),
                       head_tilt=rng.uniform(20, 55),
                       pose_seed=rng.randint(0, 10 ** 6),
                       mats=mats, leaf=leaf,
                       head_azim=base_az + rng.uniform(-face_jitter, face_jitter))
        ob.location = (x, y, 0)
        ob.rotation_euler = (0, 0, rng.uniform(0, math.pi * 2))
        objs.append(ob)
    return objs


def wind_sway(objs, amp=0.022, keys=(1, 36, 72)):
    for i, ob in enumerate(objs):
        ph = (i * 0.61) % (math.pi * 2)
        rz = ob.rotation_euler[2]
        for f in keys:
            t = (f - keys[0]) / 24.0
            a = amp * math.sin(ph + 2 * math.pi * t / 3.2) * math.sin(ph * 7.3 + 1.0)
            ob.rotation_euler = (a * 0.6, a, rz)
            ob.keyframe_insert("rotation_euler", frame=f)
    return objs


# --------------------------------------------------------------------------- render
def render(shot, outdir, samples=None, label=""):
    sc = scene()
    if samples:
        try:
            sc.eevee.taa_render_samples = samples
        except Exception:
            pass
    os.makedirs(outdir, exist_ok=True)
    sc.frame_start = int(shot["f0"])
    sc.frame_end = int(shot["f1"])
    sc.render.filepath = os.path.join(outdir, shot["id"] + "_")
    bpy.ops.render.render(animation=True)
    print(f"[lib] rendered {shot['id']} -> {outdir} ({shot['f0']}-{shot['f1']}) {label}")


def save(path):
    bpy.ops.wm.save_as_mainfile(filepath=path)
