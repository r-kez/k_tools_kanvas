"""Shape tab: kind, vertices and outline tools, place and size, opacity, export."""

from .common import gap, pair_row, vector_row


def draw(layout, context, settings, item):
    layout.prop(item, 'shape_kind', text='Kind')
    gap(layout)
    _draw_vertices(layout, item)
    gap(layout)
    row = layout.row(align=True)
    row.prop(item, 'shape_closed', text='Closed', toggle=True,
             icon='MESH_CIRCLE' if item.shape_closed else 'IPO_LINEAR')
    from ...utils.shape_geometry import item_contour_ranges, uses_curve_resolution
    contours = len(item_contour_ranges(item))
    if contours > 1:
        row = layout.row(align=True)
        row.label(text=f'{contours} contours (inner ones are holes)', icon='SELECT_DIFFERENCE')
        row.operator('kanvas.separate_contours', text='Separate', icon='MOD_EXPLODE')
    gap(layout)
    column = layout.column(align=True)
    column.prop(item, 'shape_corner_radius', text='Corner Radius')
    row = column.row(align=True)
    # Curved edges and rounded corners use it; a shape with neither has nothing to smooth.
    row.enabled = uses_curve_resolution(item)
    row.prop(item, 'shape_curve_resolution', text='Curve Resolution')

    gap(layout)
    geometry = layout.column(align=True)
    vector_row(geometry, 'Position', item, 'location')
    pair_row(geometry, 'Size', item, ('shape_width', 'shape_height'))
    row = geometry.row(align=True)
    row.prop(item, 'rotation_ui', text='Rotation')
    row.prop(item, 'scale_master', text='Scale')
    gap(layout)
    layout.prop(item, 'opacity', text='Opacity', slider=True)
    layout.operator('kanvas.export_shapes_svg', text='Export SVG...', icon='EXPORT')


def _draw_vertices(layout, item):
    box = layout.box()
    row = box.row(align=True)
    row.prop(item, 'shape_edit_vertices', text='Edit Vertices (E)', toggle=True,
             icon='EDITMODE_HLT')
    if not item.shape_edit_vertices:
        row = box.row(align=True)
        row.label(text=f'{len(item.shape_vertices)} vertices')
        row.operator('kanvas.flip_shape', text='Flip H', icon='MOD_MIRROR').axis = 'X'
        row.operator('kanvas.flip_shape', text='Flip V', icon='MOD_MIRROR').axis = 'Y'
        return
    selected = sum(1 for vertex in item.shape_vertices if vertex.select)
    row = box.row(align=True)
    row.label(text=f'{len(item.shape_vertices)} vertices, {selected} selected')
    delete = row.row(align=True)
    delete.enabled = selected > 0
    delete.operator('kanvas.delete_shape_vertices', text='Delete', icon='X')
    tools = box.column(align=True)
    tools.enabled = selected > 0
    tools.prop(item, 'shape_vertex_location', text='Position')
    row = tools.row(align=True)
    row.operator('kanvas.select_contour', text='Contour (L)', icon='SELECT_EXTEND')
    row.operator('kanvas.reverse_contour', text='Reverse', icon='ARROW_LEFTRIGHT')
    row = tools.row(align=True)
    row.operator('kanvas.flip_shape', text='Flip H', icon='MOD_MIRROR').axis = 'X'
    row.operator('kanvas.flip_shape', text='Flip V', icon='MOD_MIRROR').axis = 'Y'
    from ...utils.shape_geometry import HANDLE_TYPES
    types = {vertex.handle_type for vertex in item.shape_vertices if vertex.select}
    column = box.column(align=True)
    column.enabled = selected > 0
    column.label(text='Vertex Type (V)')
    grid = column.grid_flow(row_major=True, columns=3, even_columns=True, align=True)
    for identifier, label, _, icon in HANDLE_TYPES:
        grid.operator('kanvas.set_vertex_type', text=label, icon=icon,
                      depress=types == {identifier}).kind = identifier
