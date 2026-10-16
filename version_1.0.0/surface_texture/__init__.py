# SPDX-FileCopyrightText: 2026 Ricardo Lugaresi
# SPDX-License-Identifier: GPL-3.0-or-later

bl_info = {'name': 'Surface Texture', 'author': 'Ricardo Lugaresi', 'version': (1, 0, 0),
           'blender': (4, 2, 0), 'location': 'Vista 3D > N > Surface Texture',
           'description': 'Relieve real e imprimible en cualquier pieza: moleteado, carbono, hexágonos, cuero, '
                          'madera, piedra, martillado o tu propia imagen. Todo en modo Objeto',
           'category': 'Object'}

import bpy

from . import common, texture

PATTERN_ITEMS = [
    ('KNURL', 'Moleteado', 'Rombos para agarre: pomos, mandos, tapones'),
    ('CARBON', 'Fibra de carbono', 'Trenzado de sarga'),
    ('HEX', 'Hexágonos', 'Panal'),
    ('LEATHER', 'Cuero', 'Piel con grietas y poro'),
    ('HAMMER', 'Martillado', 'Metal martillado: hoyuelos'),
    ('WOOD', 'Madera', 'Vetas y anillos'),
    ('STONE', 'Piedra', 'Roca o yeso rugoso'),
    ('BRICK', 'Ladrillo', 'Pared de ladrillos'),
    ('RIBS', 'Estrías', 'Rayas paralelas'),
    ('IMAGE', 'Mi imagen', 'Un PNG o JPG en grises: blanco alto, negro bajo (logos, texturas)'),
]
DIR_ITEMS = [('IN', 'Grabada', 'Hacia dentro: la pieza no crece (respeta medidas y encajes)'),
             ('OUT', 'En relieve', 'Hacia fuera: más marcada al tacto')]
PROJ_ITEMS = [('BOX', 'Cualquier forma', 'Se proyecta desde los tres ejes y se mezcla sin costuras'),
              ('CYLINDER', 'Redonda (eje Z)', 'Envuelve la pieza alrededor del eje vertical: pomos y mandos')]
ZONE_ITEMS = [('ALL', 'Todo', ''), ('SIDES', 'Laterales', 'Solo lo que mira hacia los lados'),
              ('TOP', 'Arriba', 'Solo lo que mira hacia arriba')]
NEEDS_PROJECTION = {'KNURL', 'CARBON', 'HEX', 'BRICK', 'RIBS', 'IMAGE'}


class TextureProps(bpy.types.PropertyGroup):
    model_unit: bpy.props.EnumProperty(name='Unidades', items=common.UNIT_ITEMS, default='AUTO')
    pattern: bpy.props.EnumProperty(name='Textura', items=PATTERN_ITEMS, default='KNURL')
    depth: bpy.props.FloatProperty(name='Profundidad (mm)', default=0.6, min=0.1, max=5, precision=2)
    scale: bpy.props.FloatProperty(name='Tamaño del dibujo (mm)', default=4.0, min=0.5, max=100, precision=1)
    direction: bpy.props.EnumProperty(name='Dirección', items=DIR_ITEMS, default='IN')
    projection: bpy.props.EnumProperty(name='Forma', items=PROJ_ITEMS, default='BOX')
    zone: bpy.props.EnumProperty(name='Dónde', items=ZONE_ITEMS, default='ALL')
    keep_base: bpy.props.BoolProperty(name='No tocar la base', default=True,
                                      description='Lo que apoya en la cama queda liso y plano')
    image: bpy.props.StringProperty(name='Imagen', subtype='FILE_PATH')
    detail: bpy.props.FloatProperty(name='Detalle', default=1.0, min=0.5, max=2.0, precision=1,
                                    description='Más detalle = más nítido y más pesado')
    show_fine: bpy.props.BoolProperty(name='Ajustes', default=False)
    done: bpy.props.StringProperty(default='')
    export_folder: bpy.props.StringProperty(name='Carpeta', default='//Texturas', subtype='DIR_PATH')
    scope: bpy.props.EnumProperty(name='Exportar', items=common.SCOPE_ITEMS, default='SELECTED')


def _model(context):
    for obj in [context.active_object] + list(context.selected_objects):
        if obj is not None and obj.type == 'MESH' and not common.is_helper(obj):
            return obj
    return None


class OBJECT_OT_texture_apply(bpy.types.Operator):
    """Pone la textura en una copia de la pieza (la original no se toca)"""
    bl_idname = 'object.texture_apply'; bl_label = 'Poner textura'; bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return common.poll_object_mode(cls, context)

    def execute(self, context):
        p = context.scene.texture_props
        try:
            msg = texture.apply(context, _model(context), p.pattern, p.depth, p.scale, p.direction, p.projection,
                                p.zone, p.keep_base, p.image, p.detail, p.model_unit)
        except common.AddonError as exc:
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        p.done = msg
        self.report({'INFO'}, msg + ' Ctrl+Z para probar otra.')
        return {'FINISHED'}


class OBJECT_OT_texture_export(bpy.types.Operator):
    """Exporta a STL en milímetros"""
    bl_idname = 'object.texture_export'; bl_label = 'Exportar STL'

    @classmethod
    def poll(cls, context):
        return common.poll_object_mode(cls, context)

    def execute(self, context):
        p = context.scene.texture_props
        try:
            files = common.export_meshes(context, p.export_folder, p.scope, p.model_unit)
        except (common.AddonError, OSError) as exc:
            self.report({'ERROR'}, str(exc)); return {'CANCELLED'}
        where = files[0].parent if files else common.export_folder(p.export_folder)
        self.report({'INFO'}, f'{len(files)} STL exportados en mm en {where}'); return {'FINISHED'}


def _wrap(layout, text, width=38):
    col = layout.column(align=True); col.scale_y = .8
    line = ''
    for word in text.split():
        if len(line) + len(word) + 1 > width:
            col.label(text=line); line = word
        else:
            line = (line + ' ' + word).strip()
    if line:
        col.label(text=line)


class VIEW3D_PT_texture(bpy.types.Panel):
    bl_label = 'Surface Texture'; bl_idname = 'VIEW3D_PT_texture'; bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'; bl_category = 'Surface Texture'

    def draw(self, context):
        layout = self.layout; p = context.scene.texture_props
        layout.use_property_split = True; layout.use_property_decorate = False
        if common.draw_mode_warning(layout, context):
            return
        box = layout.box()
        box.label(text='1 · Pieza', icon='MESH_DATA')
        model = _model(context)
        if model is None:
            row = box.row(); row.alert = True
            row.label(text='Selecciona la pieza', icon='ERROR')
        else:
            mm = common.factor(context.scene, p.model_unit, model)
            d = [x * mm for x in model.dimensions]
            box.label(text=model.name, icon='OBJECT_DATA')
            box.label(text=f'{d[0]:.0f} × {d[1]:.0f} × {d[2]:.0f} mm')
        box = layout.box()
        box.label(text='2 · Textura', icon='TEXTURE')
        box.prop(p, 'pattern')
        if p.pattern == 'IMAGE':
            box.prop(p, 'image')
        box.prop(p, 'depth')
        box.prop(p, 'scale')
        row = box.row(); row.use_property_split = False
        row.prop(p, 'direction', expand=True)
        if p.pattern in NEEDS_PROJECTION:
            row = box.row(); row.use_property_split = False
            row.prop(p, 'projection', expand=True)
        box.prop(p, 'keep_base')
        fine = box.column()
        fine.prop(p, 'show_fine', icon='TRIA_DOWN' if p.show_fine else 'TRIA_RIGHT', emboss=False)
        if p.show_fine:
            fine.prop(p, 'zone')
            fine.prop(p, 'detail')
            fine.prop(p, 'model_unit')
        col = layout.column(); col.scale_y = 1.6
        col.operator('object.texture_apply', icon='MOD_DISPLACE')
        if p.done:
            _wrap(layout, p.done)
        box = layout.box()
        box.label(text='3 · Exportar STL', icon='EXPORT')
        row = box.row(); row.use_property_split = False
        row.prop(p, 'scope', expand=True)
        box.prop(p, 'export_folder')
        box.operator('object.texture_export', icon='EXPORT')


classes = (TextureProps, OBJECT_OT_texture_apply, OBJECT_OT_texture_export, VIEW3D_PT_texture)


def register():
    common.register_classes(classes, 'texture_props', TextureProps)


def unregister():
    common.unregister_classes(classes, 'texture_props')
