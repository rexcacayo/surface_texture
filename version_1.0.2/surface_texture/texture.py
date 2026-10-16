# SPDX-FileCopyrightText: 2026 Ricardo Lugaresi
# SPDX-License-Identifier: GPL-3.0-or-later

"""Relieve de verdad (geometría) sobre cualquier pieza, listo para imprimir.

1. La malla se rehace con vóxeles finos (Remesh) para tener vértices repartidos por igual:
   el dibujo necesita detalle uniforme y así sale siempre cerrada.
2. Cada vértice se mueve por su normal según el patrón (hacia fuera o grabado hacia dentro).
3. La base (lo que apoya en la cama) no se toca, para que siga plana.
"""
import math
import time

import bpy
import numpy as np

from . import common, patterns

MAX_FACES = 1_500_000
# cuántos vóxeles por celda pide cada dibujo (surcos finos o grano = más)
SAMPLES = {'KNURL': 12, 'RIBS': 8, 'CARBON': 10, 'WOOD': 12, 'HAMMER': 12, 'BRICK': 14, 'HEX': 14,
           'LEATHER': 16, 'STONE': 20, 'IMAGE': 16}


def _mesh_arrays(me):
    V = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', V)
    N = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('normal', N)
    E = np.empty(len(me.edges) * 2, np.int64); me.edges.foreach_get('vertices', E)
    return V.reshape(-1, 3), N.reshape(-1, 3), E.reshape(-1, 2)


def _spread(values, E, rounds=2):
    n = len(values)
    deg = np.bincount(E.ravel(), minlength=n).astype(float) + 1.0
    for _ in range(rounds):
        acc = values.copy()
        np.add.at(acc, E[:, 0], values[E[:, 1]])
        np.add.at(acc, E[:, 1], values[E[:, 0]])
        values = acc / deg
    return values


def _remeshed_copy(context, obj, voxel_bu, name):
    """Copia en mundo con vóxeles uniformes (el original no se toca)."""
    graph = context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(obj.evaluated_get(graph), depsgraph=graph)
    me.transform(obj.matrix_world)
    out = bpy.data.objects.new(name, me)
    col = obj.users_collection[0] if obj.users_collection else context.scene.collection
    col.objects.link(out)
    for slot in obj.material_slots:
        if slot.material and slot.material.name not in [m.name for m in me.materials if m]:
            me.materials.append(slot.material)
    mod = out.modifiers.new('Textura_vóxeles', 'REMESH')
    mod.mode = 'VOXEL'
    mod.voxel_size = voxel_bu
    mod.adaptivity = 0.0
    if hasattr(mod, 'use_smooth_shade'):
        mod.use_smooth_shade = False
    context.view_layer.update()
    graph = context.evaluated_depsgraph_get()
    new = bpy.data.meshes.new_from_object(out.evaluated_get(graph), depsgraph=graph)
    out.modifiers.remove(mod)
    old = out.data
    out.data = new
    new.name = name
    bpy.data.meshes.remove(old)
    return out


def _svg_to_png(path):
    """Un SVG (logo vectorial) se importa como curvas rellenas y se pinta en blanco sobre negro,
    visto desde arriba, para usarlo como mapa de alturas."""
    import os
    import tempfile
    from mathutils import Vector
    before = set(bpy.data.objects)
    curves_before = set(bpy.data.curves)
    try:
        bpy.ops.import_curve.svg(filepath=path)
    except Exception as exc:
        raise common.AddonError(f'No pude leer ese SVG ({exc}). Prueba con un PNG.')
    new = [o for o in bpy.data.objects if o not in before]
    curves = [o for o in new if o.type == 'CURVE']
    scene = bpy.data.scenes.new('_svg_textura')
    cam = None
    try:
        if not curves:
            raise common.AddonError('Ese SVG no tiene formas que se puedan usar.')
        for o in new:
            for c in list(o.users_collection):
                c.objects.unlink(o)
            scene.collection.objects.link(o)
        for o in curves:
            o.data.dimensions = '2D'
            o.data.fill_mode = 'BOTH'
            o.data.materials.clear()
        pts = [o.matrix_world @ Vector(c) for o in curves for c in o.bound_box]
        lo = Vector([min(p[i] for p in pts) for i in range(3)])
        hi = Vector([max(p[i] for p in pts) for i in range(3)])
        size = hi - lo
        span = max(size.x, size.y, 1e-6) * 1.08          # un poco de margen: el logo no se pega al de al lado
        cam = bpy.data.objects.new('_svg_cam', bpy.data.cameras.new('_svg_cam'))
        scene.collection.objects.link(cam)
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = span
        cam.location = ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, hi.z + 1.0)
        scene.camera = cam
        world = bpy.data.worlds.new('_svg_world')
        world.color = (0, 0, 0)
        scene.world = world
        scene.render.engine = 'BLENDER_WORKBENCH'
        sh = scene.display.shading
        sh.light = 'FLAT'; sh.color_type = 'SINGLE'; sh.single_color = (1, 1, 1)
        sh.background_type = 'WORLD' if hasattr(sh, 'background_type') else sh.background_type
        sh.show_cavity = False; sh.show_shadows = False; sh.show_object_outline = False
        scene.view_settings.view_transform = 'Standard'
        scene.render.film_transparent = False
        res = 1024
        scene.render.resolution_x = res
        scene.render.resolution_y = res
        out = os.path.join(tempfile.gettempdir(), '_svg_textura.png')
        scene.render.filepath = out
        bpy.ops.render.render(write_still=True, scene=scene.name)
        return out
    finally:
        for o in new + ([cam] if cam else []):
            if o.name in bpy.data.objects:
                bpy.data.objects.remove(o, do_unlink=True)
        for c in [c for c in bpy.data.curves if c not in curves_before and c.users == 0]:
            bpy.data.curves.remove(c)
        if scene.world and scene.world.name.startswith('_svg_world'):
            bpy.data.worlds.remove(scene.world)
        bpy.data.scenes.remove(scene)


def _load_image(path, repeat=True, invert=False):
    if not path:
        raise common.AddonError('Elige la imagen para el relieve (PNG, JPG o SVG: blanco alto, negro bajo).')
    path = bpy.path.abspath(path)
    if path.lower().endswith('.svg'):
        path = _svg_to_png(path)
    try:
        img = bpy.data.images.load(path, check_existing=False)
    except RuntimeError:
        raise common.AddonError('No pude abrir esa imagen. Usa PNG, JPG o SVG.')
    w, h = img.size
    if not w or not h:
        bpy.data.images.remove(img)
        raise common.AddonError('No pude leer esa imagen (sale vacía). Usa PNG, JPG o SVG.')
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    px = px.reshape(-1, 4)
    gray = (0.299 * px[:, 0] + 0.587 * px[:, 1] + 0.114 * px[:, 2]) * px[:, 3] + (1 - px[:, 3])
    if invert:
        gray = 1.0 - gray
    return patterns.ImagePattern(gray.astype(np.float64), w, h, repeat)


def apply(context, obj, pattern='KNURL', depth_mm=0.6, scale_mm=4.0, direction='IN', projection='BOX',
          zone='ALL', keep_base=True, image_path='', detail=1.0, unit='AUTO', stack=False, image_repeat=False, image_invert=False):
    """Crea «<pieza>_textura». Devuelve el mensaje para el usuario.
    Si lo seleccionado ya es una textura, por defecto se rehace desde la pieza original (se cambia
    de textura, no se apila); con stack=True se pone encima de la anterior."""
    if obj is None or obj.type != 'MESH':
        raise common.AddonError('Selecciona la pieza (una malla) a la que quieres dar textura.')
    previous = None
    if not stack:
        while obj.get('textura') and obj.get('taller_origen') in bpy.data.objects:
            previous = previous or obj
            obj = bpy.data.objects[obj['taller_origen']]
    t0 = time.time()
    code, f = common.resolve_unit(context.scene, unit, obj)
    image = _load_image(image_path, image_repeat, image_invert) if pattern == 'IMAGE' else None
    # tamaño del vóxel: unas 8 divisiones por celda del dibujo, sin pasar de MAX_FACES
    bm = common.world_bmesh(context, obj)
    try:
        area_mm2 = sum(face.calc_area() for face in bm.faces) * f * f
    finally:
        bm.free()
    if area_mm2 <= 0:
        raise common.AddonError('La pieza no tiene caras.')
    want = scale_mm / (SAMPLES.get(pattern, 10) * detail)   # muestras por celda según lo fino del dibujo
    if pattern == 'IMAGE':
        want = max(0.12, scale_mm / (120.0 * detail))          # un logo necesita ~120 puntos de lado para leerse
    floor = math.sqrt(area_mm2 / MAX_FACES)
    voxel = max(want, floor, 0.05)
    coarse = voxel > scale_mm / 2.5
    out = _remeshed_copy(context, obj, voxel / f, f'{obj.name}_textura')
    try:
        return _texture(context, obj, out, previous, pattern, depth_mm, scale_mm, direction, projection, zone,
                        keep_base, image, code, f, voxel, coarse, t0)
    except Exception:
        me = out.data
        bpy.data.objects.remove(out, do_unlink=True)
        bpy.data.meshes.remove(me)
        raise


def _texture(context, obj, out, previous, pattern, depth_mm, scale_mm, direction, projection, zone, keep_base,
             image, code, f, voxel, coarse, t0):
    me = out.data
    V, N, E = _mesh_arrays(me)
    P = V * f
    h = patterns.height(P, N, pattern, scale_mm, projection, image=image)
    # zonas
    mask = np.ones(len(P))
    if zone == 'SIDES':
        mask *= 1.0 - patterns._smooth(0.6, 0.8, np.abs(N[:, 2]))
    elif zone == 'TOP':
        mask *= patterns._smooth(0.3, 0.6, N[:, 2])
    if keep_base:
        zrel = P[:, 2] - P[:, 2].min()
        mask *= patterns._smooth(0.2, 0.2 + max(1.0, depth_mm * 2), zrel)
    mask = _spread(mask, E, 2)
    if pattern == 'IMAGE':
        d = depth_mm * h if direction == 'OUT' else -depth_mm * h     # lo blanco sube (relieve) o se hunde (grabado)
    else:
        d = depth_mm * h if direction == 'OUT' else -depth_mm * (1.0 - h)
    P = P + N * (d * mask)[:, None]
    me.vertices.foreach_set('co', (P / f).astype(np.float32).ravel())
    me.update()
    out[common.UNIT_PROP] = code
    out['taller_origen'] = obj.name
    out['textura'] = pattern
    obj.hide_set(True); obj.hide_render = True
    if previous is not None:
        previous.hide_set(True); previous.hide_render = True
    for o in context.selected_objects:
        o.select_set(False)
    out.select_set(True)
    context.view_layer.objects.active = out
    names = {'KNURL': 'moleteado', 'HEX': 'hexágonos', 'CARBON': 'fibra de carbono', 'BRICK': 'ladrillo',
             'RIBS': 'estrías', 'STONE': 'piedra', 'HAMMER': 'martillado', 'LEATHER': 'cuero', 'WOOD': 'madera',
             'IMAGE': 'imagen'}
    msg = (f'Textura {names.get(pattern, pattern)}: {depth_mm:g} mm '
           f'{"hacia fuera" if direction == "OUT" else "grabada"}, dibujo de {scale_mm:g} mm. '
           f'{len(me.polygons):_} caras ({time.time() - t0:.0f} s).'.replace('_', '.'))
    if coarse:
        msg += (f' Ojo: la pieza es grande para un dibujo tan pequeño (detalle {voxel:.2f} mm): '
                'agranda el dibujo para que se vea nítido.')
    return msg
