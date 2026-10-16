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
SAMPLES = {'KNURL': 8, 'RIBS': 8, 'CARBON': 10, 'WOOD': 12, 'HAMMER': 12, 'BRICK': 14, 'HEX': 14,
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


def _load_image(path):
    if not path:
        raise common.AddonError('Elige la imagen para el relieve (PNG o JPG en grises: blanco alto, negro bajo).')
    try:
        img = bpy.data.images.load(bpy.path.abspath(path), check_existing=True)
    except RuntimeError:
        raise common.AddonError('No pude abrir esa imagen.')
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(-1, 4)
    gray = (0.299 * px[:, 0] + 0.587 * px[:, 1] + 0.114 * px[:, 2]) * px[:, 3] + (1 - px[:, 3])
    return patterns.ImagePattern(gray.astype(np.float64), w, h)


def apply(context, obj, pattern='KNURL', depth_mm=0.6, scale_mm=4.0, direction='IN', projection='BOX',
          zone='ALL', keep_base=True, image_path='', detail=1.0, unit='AUTO'):
    """Crea «<pieza>_textura». Devuelve el mensaje para el usuario."""
    if obj is None or obj.type != 'MESH':
        raise common.AddonError('Selecciona la pieza (una malla) a la que quieres dar textura.')
    t0 = time.time()
    code, f = common.resolve_unit(context.scene, unit, obj)
    image = _load_image(image_path) if pattern == 'IMAGE' else None
    # tamaño del vóxel: unas 8 divisiones por celda del dibujo, sin pasar de MAX_FACES
    bm = common.world_bmesh(context, obj)
    try:
        area_mm2 = sum(face.calc_area() for face in bm.faces) * f * f
    finally:
        bm.free()
    if area_mm2 <= 0:
        raise common.AddonError('La pieza no tiene caras.')
    want = scale_mm / (SAMPLES.get(pattern, 10) * detail)   # muestras por celda según lo fino del dibujo
    floor = math.sqrt(area_mm2 / MAX_FACES)
    voxel = max(want, floor, 0.05)
    coarse = voxel > scale_mm / 2.5
    out = _remeshed_copy(context, obj, voxel / f, f'{obj.name}_textura')
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
    d = depth_mm * h if direction == 'OUT' else -depth_mm * (1.0 - h)
    P = P + N * (d * mask)[:, None]
    me.vertices.foreach_set('co', (P / f).astype(np.float32).ravel())
    me.update()
    out[common.UNIT_PROP] = code
    out['taller_origen'] = obj.name
    out['textura'] = pattern
    obj.hide_set(True); obj.hide_render = True
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
