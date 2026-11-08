from contextlib import contextmanager
import math

import bpy
from .utils.kanvas_data import get_settings


_frame_geometry_updates_suspended = 0
_selection_updates_suspended = 0

_MARKDOWN_TOOLTIP = """Format text in this card with Markdown:
# Heading, ## Subheading, ### Small heading
- Item, * Item, or + Item for bullet lists
**Bold text** and `inline code` (backtick / grave accent)
On ABNT2, type ` with the grave accent key followed by Space
[Link label](https://example.com) for web links
Ctrl+click a link on the card to open it"""


def _settings_for_item(item, context):
    owner = getattr(item, 'id_data', None)
    if getattr(owner, 'bl_idname', None) == 'KanvasNodeTree':
        return owner.kanvas_settings
    return get_settings(context)


@contextmanager
def suspend_frame_geometry_updates():
    """Avoid intermediate fits while moving a frame and all of its children."""
    global _frame_geometry_updates_suspended
    _frame_geometry_updates_suspended += 1
    try:
        yield
    finally:
        _frame_geometry_updates_suspended -= 1


@contextmanager
def suspend_selection_updates():
    """Keep a multi-selection intact while the UI list changes order."""
    global _selection_updates_suspended
    _selection_updates_suspended += 1
    try:
        yield
    finally:
        _selection_updates_suspended -= 1

def update_kanvas_item_name(self, context):
    """Keep the default image label in sync with its datablock."""
    if getattr(self, "item_type", 'IMAGE') == 'IMAGE':
        if self.image_data and self.name == "Image":
            self.name = self.image_data.name
    elif getattr(self, "item_type", 'IMAGE') in {'TEXT', 'SHAPE'} and getattr(context, 'area', None):
        context.area.tag_redraw()

def update_show_in_editor(self, context):
    """Quando visibilidade muda. Se for frame, propaga para todas as imagens filhas."""
    if getattr(self, "item_type", 'IMAGE') == 'FRAME' and self.frame_node_name:
        try:
            settings = _settings_for_item(self, context)
            from .utils.gpu import frame_descendants
            for img in frame_descendants(settings, self.frame_node_name):
                img.show_in_editor = self.show_in_editor
        except Exception:
            pass

def update_frame_auto_resize(self, context):
    """Quando auto_resize for reativado no frame, ajusta o tamanho para conter os filhos."""
    if _frame_geometry_updates_suspended:
        return
    settings = _settings_for_item(self, context)
    if (settings and getattr(self, "item_type", 'IMAGE') == 'FRAME'
            and self.frame_node_name and not self.auto_resize):
        from .utils.gpu import frame_has_content
        if frame_has_content(settings, self.frame_node_name):
            self.auto_resize = True
            return
    if getattr(self, "item_type", 'IMAGE') == 'FRAME' and getattr(self, "auto_resize", False) and self.frame_node_name:
        try:
            settings = _settings_for_item(self, context)
            space = getattr(context, 'space_data', None)
            tree = getattr(space, 'edit_tree', None) if space else None
            from .utils.gpu import update_frame_bounds
            update_frame_bounds(tree, settings, self.frame_node_name)
            if hasattr(context, "area") and context.area:
                context.area.tag_redraw()
        except Exception:
            pass


def update_frame_geometry(self, context):
    """Refresh an attached frame when image geometry changes in the UI or canvas."""
    if self.parent_frame:
        self.released_parent_frame = ''
    if _frame_geometry_updates_suspended:
        return
    if getattr(self, "item_type", 'IMAGE') in {'IMAGE', 'TEXT', 'SHAPE', 'FRAME'} and self.parent_frame:
        from .utils.gpu import update_frame_bounds
        update_frame_bounds(None, _settings_for_item(self, context), self.parent_frame)
    update_kanvas_item_name(self, context)
    if getattr(context, 'area', None):
        context.area.tag_redraw()


def update_frame_header_font(self, context):
    if getattr(self, "item_type", 'IMAGE') == 'FRAME' and self.frame_node_name:
        from .utils.gpu import update_frame_bounds
        from .utils.gpu.gpu_frame import frame_header_height
        update_frame_bounds(None, _settings_for_item(self, context), self.frame_node_name)
        self.frame_height = max(self.frame_height, frame_header_height(self) + 24.0)
    if getattr(context, 'area', None):
        context.area.tag_redraw()

def update_text_appearance(self, context):
    if hasattr(self, 'line_id') and self.line_id:
        owner = getattr(self, 'id_data', None)
        if getattr(owner, 'bl_idname', None) == 'KanvasNodeTree':
            settings = owner.kanvas_settings
            card = next((item for item in settings.images
                         if item.item_type == 'TEXT' and item.text_checklist
                         and any(line.as_pointer() == self.as_pointer()
                                 for line in item.text_lines)), None)
            if card is not None:
                for image in settings.images:
                    if image.item_type == 'IMAGE':
                        for region in image.markup_regions:
                            if (region.checklist_card_id == card.item_id
                                    and region.checklist_line_id == self.line_id):
                                region.name = self.value
    if (not _frame_geometry_updates_suspended
            and getattr(self, "item_type", 'IMAGE') == 'TEXT' and self.parent_frame):
        from .utils.gpu import update_frame_bounds
        update_frame_bounds(None, _settings_for_item(self, context), self.parent_frame)
    if getattr(context, 'area', None):
        context.area.tag_redraw()


def get_text_body(self):
    return '\n'.join(line.value for line in self.text_lines)


def set_text_body(self, value):
    parts = value.split('\n')
    lines = self.text_lines
    while len(lines) < len(parts):
        lines.add()
    while len(lines) > len(parts):
        lines.remove(len(lines) - 1)
    for line, part in zip(lines, parts):
        if line.value != part:
            line.value = part


def get_rotation_ui(self):
    """Present clockwise-positive degrees without changing saved rotations."""
    return math.radians(-self.rotation)


def set_rotation_ui(self, value):
    self.rotation = -math.degrees(value)


def update_checklist_line_color(self, context):
    owner = getattr(self, 'id_data', None)
    if getattr(owner, 'bl_idname', None) != 'KanvasNodeTree':
        return
    settings = owner.kanvas_settings
    line_id = self.line_id
    if not line_id:
        return
    card = next((item for item in settings.images
                 if item.item_type == 'TEXT' and item.text_checklist
                 and any(line.as_pointer() == self.as_pointer()
                         for line in item.text_lines)), None)
    if card is None:
        return
    for image in settings.images:
        if image.item_type != 'IMAGE':
            continue
        for region in image.markup_regions:
            if (region.checklist_card_id == card.item_id
                    and region.checklist_line_id == line_id):
                region.color = tuple(self.color)
                image.markup_revision += 1
    if getattr(context, 'area', None):
        context.area.tag_redraw()


class KanvasTextLine(bpy.types.PropertyGroup):  # type: ignore
    line_id: bpy.props.StringProperty(default='')  # type: ignore
    done: bpy.props.BoolProperty(  # type: ignore
        name='Done', description='Mark this checklist task as complete',
        default=False, update=update_text_appearance,
    )
    show_color_links: bpy.props.BoolProperty(  # type: ignore
        name='Show Paint Links',
        description='Show arrows in this task color to its paint on linked images',
        default=False, update=update_text_appearance,
    )
    value: bpy.props.StringProperty(  # type: ignore
        name='Line',
        description='Text of this card line or checklist task',
        default='',
        update=update_text_appearance,
    )
    color: bpy.props.FloatVectorProperty(  # type: ignore
        name='Task Color', description='Shared paint color for this checklist task',
        subtype='COLOR', size=3, default=(0.95, 0.34, 0.18),
        min=0.0, max=1.0, update=update_checklist_line_color,
    )


def update_selection_order(self, context):
    """Number items in the order they are selected (see `selection_order`)."""
    if not self.is_selected:
        if self.selection_order:
            self.selection_order = 0
        return
    if self.selection_order:
        return
    settings = getattr(self.id_data, 'kanvas_settings', None)
    if settings is None:
        return
    settings.selection_counter += 1
    self.selection_order = settings.selection_counter


def set_shape_vertices(item, vertices):
    """Replace a shape's vertices with unit-box positions (-0.5..0.5)."""
    collection = item.shape_vertices
    collection.clear()
    for x, y in vertices:
        collection.add().co = (x, y)


def vertex_records(item):
    """Everything about a shape's vertices except the selection, to copy or restore."""
    return [(tuple(v.co), v.handle_type, tuple(v.handle_left), tuple(v.handle_right),
             v.contour) for v in item.shape_vertices]


def set_vertex_records(item, records):
    """Replace a shape's vertices with records from `vertex_records`.

    Four-item records (without the contour number) all go to contour 0.
    """
    collection = item.shape_vertices
    collection.clear()
    for record in records:
        vertex = collection.add()
        vertex.co = record[0]
        vertex.handle_type = record[1]
        vertex.handle_left = record[2]
        vertex.handle_right = record[3]
        vertex.contour = record[4] if len(record) > 4 else 0


def update_shape_kind(self, context):
    """Changing the kind rebuilds the vertices; Polygon keeps the current ones."""
    if getattr(self, 'item_type', '') != 'SHAPE':
        return
    from .utils.shape_geometry import preset_records
    records = preset_records(self.shape_kind)
    if records is not None:
        set_vertex_records(self, records)
    update_frame_geometry(self, context)


def update_shape_appearance(self, context):
    if getattr(context, 'area', None):
        context.area.tag_redraw()


def update_shape_edit_vertices(self, context):
    """Leaving Edit Vertices forgets the vertex selection, so it never comes back stale."""
    if not self.shape_edit_vertices:
        for vertex in self.shape_vertices:
            if vertex.select:
                vertex.select = False
    update_shape_appearance(self, context)


def update_shape_curve_resolution(self, context):
    update_shape_appearance(self, context)


def _selected_vertices_get(self):
    if getattr(self, 'item_type', '') != 'SHAPE':
        return (0.0, 0.0)
    from .operators.ops_shape import selected_vertex_indices, selection_center
    indices = selected_vertex_indices(self)
    return selection_center(self, indices) if indices else tuple(self.location)


def _selected_vertices_set(self, value):
    if getattr(self, 'item_type', '') != 'SHAPE':
        return
    from .operators.ops_shape import (move_vertices, normalize_shape, selected_vertex_indices,
                                      selection_center)
    indices = selected_vertex_indices(self)
    if not indices:
        return
    current = selection_center(self, indices)
    delta = (value[0] - current[0], value[1] - current[1])
    if abs(delta[0]) < 1e-9 and abs(delta[1]) < 1e-9:
        return
    if self.shape_kind != 'POLYGON':
        self.shape_kind = 'POLYGON'  # keeps the current vertices
    move_vertices(self, indices, delta)
    normalize_shape(self)


def update_shape_closed(self, context):
    """An open path starts without fill (the fill would close it); closing it again
    brings the fill back, since a closed outline with neither would only be a line."""
    if getattr(self, 'item_type', '') != 'SHAPE':
        return
    if not self.shape_closed:
        if self.shape_kind != 'POLYGON':
            self.shape_kind = 'POLYGON'  # keeps the current vertices
        if self.shape_show_fill:
            self.shape_show_outline = True
            self.shape_show_fill = False
    update_frame_geometry(self, context)


def update_shape_fill(self, context):
    """A shape with neither fill nor outline would be invisible: keep the outline."""
    if not self.shape_show_fill and not self.shape_show_outline:
        self.shape_show_outline = True
    update_shape_appearance(self, context)


def update_shape_outline(self, context):
    if not self.shape_show_outline and not self.shape_show_fill:
        self.shape_show_outline = True
    update_shape_appearance(self, context)


class KanvasShapeVertex(bpy.types.PropertyGroup):
    co: bpy.props.FloatVectorProperty(  # type: ignore
        name='Vertex',
        description='Vertex position inside the shape box, from -0.5 to 0.5 on each axis',
        size=2,
    )
    select: bpy.props.BoolProperty(  # type: ignore
        name='Selected',
        description='Selected in Edit Vertices: moved together and removed with X or Delete',
        default=False,
    )
    # Bezier handles. A Sharp vertex has none (straight edges, as before handles existed)
    # and an Auto vertex works them out from its neighbours, so only Aligned and Free
    # vertices read the stored positions. Same unit-box coordinates as `co`.
    handle_type: bpy.props.EnumProperty(  # type: ignore
        name='Vertex Type',
        description='How the outline passes through this vertex',
        items=[
            ('SHARP', 'Sharp', 'A corner with straight edges'),
            ('AUTO', 'Auto', 'A smooth curve worked out from the neighbouring vertices'),
            ('ALIGNED', 'Aligned', 'A smooth curve: the two handles stay in line'),
            ('FREE', 'Free', 'Each handle moves on its own, for a curved corner'),
            # Added last: enum values are saved by position, so the earlier ones keep theirs.
            ('MIRRORED', 'Mirrored', 'A smooth curve: the two handles mirror each other, '
             'same angle and same length'),
        ],
        default='SHARP',
    )
    handle_left: bpy.props.FloatVectorProperty(  # type: ignore
        name='Handle In', description='Handle towards the previous vertex, in the shape box',
        size=2,
    )
    handle_right: bpy.props.FloatVectorProperty(  # type: ignore
        name='Handle Out', description='Handle towards the next vertex, in the shape box',
        size=2,
    )
    # Which closed contour of the shape this vertex belongs to. The vertices of one
    # contour are consecutive; a contour inside another one is a hole (even-odd fill).
    contour: bpy.props.IntProperty(  # type: ignore
        name='Contour', description='Closed contour of the shape this vertex belongs to',
        default=0, min=0,
    )


class KanvasMaskDab(bpy.types.PropertyGroup):
    uv: bpy.props.FloatVectorProperty(size=2)  # type: ignore
    radius_uv: bpy.props.FloatVectorProperty(size=2)  # type: ignore
    uv_axis_x: bpy.props.FloatVectorProperty(size=2)  # type: ignore
    uv_axis_y: bpy.props.FloatVectorProperty(size=2)  # type: ignore
    erase: bpy.props.BoolProperty(default=False)  # type: ignore
    sequence: bpy.props.IntProperty(default=0)  # type: ignore


class KanvasMaskVertex(bpy.types.PropertyGroup):
    uv: bpy.props.FloatVectorProperty(size=2)  # type: ignore


class KanvasMaskPolygon(bpy.types.PropertyGroup):
    vertices: bpy.props.CollectionProperty(type=KanvasMaskVertex)  # type: ignore
    erase: bpy.props.BoolProperty(default=False)  # type: ignore
    sequence: bpy.props.IntProperty(default=0)  # type: ignore


class KanvasMarkupRegion(bpy.types.PropertyGroup):
    region_id: bpy.props.StringProperty(default='')  # type: ignore
    checklist_card_id: bpy.props.StringProperty(default='')  # type: ignore
    checklist_line_id: bpy.props.StringProperty(default='')  # type: ignore
    checklist_origin_card_id: bpy.props.StringProperty(default='')  # type: ignore
    checklist_origin_line_id: bpy.props.StringProperty(default='')  # type: ignore
    name: bpy.props.StringProperty(  # type: ignore
        name='Region', description='Object or task represented by this color',
        default='New Region',
    )
    color: bpy.props.FloatVectorProperty(  # type: ignore
        name='Color', description='Color painted over this image',
        subtype='COLOR', size=3, default=(0.95, 0.35, 0.18),
        min=0.0, max=1.0,
    )
    opacity: bpy.props.FloatProperty(  # type: ignore
        name='Opacity', description='Opacity of this color region',
        default=0.45, min=0.0, max=1.0,
    )
    visible: bpy.props.BoolProperty(  # type: ignore
        name='Visible', description='Show this color region on the image',
        default=True,
    )
    inverse: bpy.props.BoolProperty(  # type: ignore
        name='Inverse',
        description='Color everything on the image except the painted area',
        default=False,
        update=lambda self, context: _tag_markup_changed(self, context),
    )
    dabs: bpy.props.CollectionProperty(type=KanvasMaskDab)  # type: ignore
    polygons: bpy.props.CollectionProperty(type=KanvasMaskPolygon)  # type: ignore
    next_sequence: bpy.props.IntProperty(default=1)  # type: ignore
    revision: bpy.props.IntProperty(default=0, options={'SKIP_SAVE'})  # type: ignore


class KanvasChecklistAssociation(bpy.types.PropertyGroup):
    card_id: bpy.props.StringProperty(  # type: ignore
        name='Checklist', description='Checklist linked to this image', default='',
    )


def _tag_markup_changed(region, context):
    if getattr(context, 'area', None):
        context.area.tag_redraw()


def _follow_isolation(item, context):
    """While isolating, choosing a region in the list isolates that region."""
    if item.markup_isolate_id and 0 <= item.markup_active_index < len(item.markup_regions):
        item.markup_isolate_id = item.markup_regions[item.markup_active_index].region_id
    _tag_markup_changed(item, context)


def update_canvas_mode(self, context):
    from . import keymap
    keymap.sync_hand_cursor()
    if getattr(context, 'area', None):
        context.area.tag_redraw()


def update_item_lock(self, context):
    if self.is_locked:
        self.is_selected = False
    if getattr(self, 'item_type', '') == 'FRAME' and self.id_data is not None:
        # Locking a frame locks its whole group, including nested frames.
        settings = getattr(self.id_data, 'kanvas_settings', None)
        if settings is not None:
            from .utils.gpu import frame_descendants
            for child in frame_descendants(settings, self.frame_node_name):
                if child.is_locked != self.is_locked:
                    child.is_locked = self.is_locked
    if getattr(context, 'area', None):
        context.area.tag_redraw()


def update_arrow_lock(self, context):
    if self.is_locked:
        self.is_selected = False
    if getattr(context, 'area', None):
        context.area.tag_redraw()


class KanvasImageItem(bpy.types.PropertyGroup): # type: ignore
    item_id: bpy.props.StringProperty(  # type: ignore
        name='Item ID',
        description='Persistent Kanvas item identity',
        default='',
    )
    name: bpy.props.StringProperty(  # type: ignore
        name='Name',
        description='Name shown on the canvas and in the item list',
        default='Image',
        update=update_kanvas_item_name,
    )
    item_type: bpy.props.EnumProperty(  # type: ignore
        name='Type',
        description='Kind of Kanvas item',
        items=[
            ('IMAGE', 'Image', 'Image Item'),
            ('FRAME', 'Frame', 'Frame Container Item'),
            ('TEXT', 'Text', 'Multiline text card'),
            ('SHAPE', 'Shape', 'Rectangle, triangle, diamond or free polygon'),
        ],
        default='IMAGE',
    )
    frame_node_name: bpy.props.StringProperty(  # type: ignore
        name='Frame ID',
        description='Persistent identifier for this Kanvas frame',
        default='',
    )

    frame_width: bpy.props.FloatProperty(  # type: ignore
        name='Width',
        description='Width of the frame on the canvas',
        default=320.0,
        min=60.0,
        update=update_frame_geometry,
    )

    frame_height: bpy.props.FloatProperty(  # type: ignore
        name='Height',
        description='Height of the frame on the canvas',
        default=240.0,
        min=60.0,
        update=update_frame_geometry,
    )

    frame_color: bpy.props.FloatVectorProperty(  # type: ignore
        name='Frame Color',
        description='Color of the frame body and header',
        subtype='COLOR',
        size=3,
        default=(0.22, 0.28, 0.38),
        min=0.0,
        max=1.0,
    )

    frame_opacity: bpy.props.FloatProperty(  # type: ignore
        name='Frame Opacity',
        description='Transparency of the frame background',
        default=0.3,
        min=0.0,
        max=1.0,
    )

    frame_is_group: bpy.props.BoolProperty(  # type: ignore
        name='Group',
        description=('This frame item is a group: it keeps its members together without '
                     'drawing a frame. Groups do not nest'),
        default=False,
    )

    list_collapsed: bpy.props.BoolProperty(  # type: ignore
        name='Collapse in List',
        description="Hide this frame's children in the item list only",
        default=False,
    )

    frame_font_size: bpy.props.IntProperty(  # type: ignore
        name='Header Font Size',
        description='Size of the frame header label',
        default=14,
        min=8,
        soft_max=128,
        update=update_frame_header_font,
    )

    text_lines: bpy.props.CollectionProperty(  # type: ignore
        type=KanvasTextLine,
    )
    text_layout_expanded: bpy.props.BoolProperty(  # type: ignore
        name='Layout', description='Expand text card layout controls', default=False,
    )
    text_appearance_expanded: bpy.props.BoolProperty(  # type: ignore
        name='Appearance', description='Expand text card appearance controls', default=False,
    )
    text_checklist: bpy.props.BoolProperty(  # type: ignore
        name='Checklist', description='Show each line as a task with a checkbox',
        default=False, update=update_text_appearance,
    )
    text_compare: bpy.props.BoolProperty(  # type: ignore
        name='Comparison',
        description='This card compares two images (A and B) instead of showing text',
        default=False, update=update_text_appearance,
    )
    compare_a_id: bpy.props.StringProperty(  # type: ignore
        name='Image A', description='Item shown as A in this comparison card', default='',
    )
    compare_b_id: bpy.props.StringProperty(  # type: ignore
        name='Image B', description='Item shown as B in this comparison card', default='',
    )
    compare_mode: bpy.props.EnumProperty(  # type: ignore
        name='Mode',
        description='How A and B are compared',
        items=(
            ('SPLIT', 'Split', 'A on one side of a divider and B on the other. Drag the divider on the card'),
            ('FADE', 'Fade', 'B drawn over A with adjustable opacity'),
            ('DIFF', 'Difference', 'Shows where A and B differ: black where they match, brighter where they do not'),
        ),
        default='SPLIT', update=update_text_appearance,
    )
    compare_blend: bpy.props.FloatProperty(  # type: ignore
        name='B Opacity', description='How much of B shows over A in Fade mode',
        default=0.5, min=0.0, max=1.0, subtype='FACTOR', update=update_text_appearance,
    )
    compare_gain: bpy.props.FloatProperty(  # type: ignore
        name='Amplify', description='Brighten small differences in Difference mode',
        default=1.0, min=1.0, max=10.0, update=update_text_appearance,
    )
    compare_split: bpy.props.FloatProperty(  # type: ignore
        name='Divider',
        description='Where the divider sits: A is shown to its left and B to its right',
        default=0.5, min=0.0, max=1.0, subtype='FACTOR', update=update_text_appearance,
    )
    text_show_progress: bpy.props.BoolProperty(  # type: ignore
        name='Show Progress', description='Show completed checklist percentage on the card',
        default=True, update=update_text_appearance,
    )
    text_markdown: bpy.props.BoolProperty(  # type: ignore
        name='Markdown', description=_MARKDOWN_TOOLTIP,
        default=False, update=update_text_appearance,
    )
    text_scroll: bpy.props.FloatProperty(  # type: ignore
        name='Text Scroll',
        description='Vertical scroll position inside this text card',
        default=0.0, min=0.0,
    )
    text_header: bpy.props.StringProperty(  # type: ignore
        name='Legacy Header', description='Saved header used only to migrate older cards',
        default='', update=update_text_appearance,
    )
    text_show_header: bpy.props.BoolProperty(  # type: ignore
        name='Show Title', description='Draw the card name at the top of the card',
        default=True, update=update_text_appearance,
    )

    text_body: bpy.props.StringProperty(  # type: ignore
        name='Text',
        get=get_text_body,
        set=set_text_body,
        update=update_text_appearance,
        description='Edit the text card; press Shift + Enter to insert a new line',
    )

    text_scale: bpy.props.FloatProperty(  # type: ignore
        name='Overall Scale',
        description='Scale the card and its text together',
        default=1.0,
        min=0.25,
        max=8.0,
        update=update_text_appearance,
    )

    text_width: bpy.props.FloatProperty(  # type: ignore
        name='Width',
        description='Card width and text wrapping, without changing font size',
        default=320.0,
        min=100.0,
        update=update_text_appearance,
    )

    text_height: bpy.props.FloatProperty(  # type: ignore
        name='Height',
        description='Card height without changing font size',
        default=180.0,
        min=60.0,
        update=update_text_appearance,
    )

    text_font_size: bpy.props.IntProperty(  # type: ignore
        name='Font Size',
        description='Base font size of text on this card',
        default=18,
        min=8,
        max=72,
        update=update_text_appearance,
    )

    text_color: bpy.props.FloatVectorProperty(  # type: ignore
        name='Text Color',
        description='Color of text on this card',
        subtype='COLOR',
        size=3,
        default=(1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
        update=update_text_appearance,
    )

    text_background: bpy.props.FloatVectorProperty(  # type: ignore
        name='Background',
        description='Background color of this text card',
        subtype='COLOR',
        size=3,
        default=(0.12, 0.14, 0.18),
        min=0.0,
        max=1.0,
        update=update_text_appearance,
    )

    text_opacity: bpy.props.FloatProperty(  # type: ignore
        name='Background Opacity',
        description='Transparency of the text card background',
        default=0.92,
        min=0.0,
        max=1.0,
        update=update_text_appearance,
    )

    shape_kind: bpy.props.EnumProperty(  # type: ignore
        name='Shape',
        description='Kind of shape. Changing it rebuilds the vertices inside the same box',
        items=[
            ('RECTANGLE', 'Rectangle', 'Four straight sides', 'MESH_PLANE', 0),
            ('TRIANGLE', 'Triangle', 'Three straight sides', 'MESH_CONE', 1),
            ('DIAMOND', 'Diamond', 'Four corners on the middle of each side', 'MESH_CUBE', 2),
            ('ELLIPSE', 'Ellipse', 'Round shape that fills its box', 'MESH_CIRCLE', 3),
            ('PENTAGON', 'Pentagon', 'Five equal sides', 'MESH_ICOSPHERE', 4),
            ('HEXAGON', 'Hexagon', 'Six equal sides', 'MESH_ICOSPHERE', 5),
            ('STAR', 'Star', 'Five pointed star', 'SOLO_OFF', 6),
            ('POLYGON', 'Polygon', 'Free vertices; edit them with Edit Vertices', 'EDITMODE_HLT', 7),
        ],
        default='RECTANGLE',
        update=update_shape_kind,
    )
    shape_width: bpy.props.FloatProperty(  # type: ignore
        name='Width',
        description='Width of the shape box before the overall scale',
        default=160.0, min=4.0,
        update=update_frame_geometry,
    )
    shape_height: bpy.props.FloatProperty(  # type: ignore
        name='Height',
        description='Height of the shape box before the overall scale',
        default=120.0, min=4.0,
        update=update_frame_geometry,
    )
    shape_vertices: bpy.props.CollectionProperty(type=KanvasShapeVertex)  # type: ignore
    shape_edit_vertices: bpy.props.BoolProperty(  # type: ignore
        name='Edit Vertices',
        description=('Show the vertices of this shape. Click, Shift+click or drag a box to select '
                     'vertices, drag them to move, click an edge to add a vertex, X or Delete '
                     'removes the selected ones'),
        default=False, options={'SKIP_SAVE'},
        update=update_shape_edit_vertices,
    )
    shape_curve_resolution: bpy.props.IntProperty(  # type: ignore
        name='Curve Resolution',
        description=('Straight segments used to draw each curved edge of this shape. Lower is '
                     'lighter and more angular, higher is smoother'),
        default=16, min=2, max=64,
        update=update_shape_curve_resolution,
    )
    shape_vertex_location: bpy.props.FloatVectorProperty(  # type: ignore
        name='Vertex Position',
        description=('Canvas position of the selected vertices (the middle of their bounds). '
                     'Type a value to move them there'),
        size=2, get=_selected_vertices_get, set=_selected_vertices_set,
        options={'SKIP_SAVE'},
    )
    shape_closed: bpy.props.BoolProperty(  # type: ignore
        name='Closed',
        description=('Join the last vertex of each outline back to the first. Off, the shape '
                     'is an open path: a line or a curve with two ends, drawn without fill'),
        default=True, update=update_shape_closed,
    )
    shape_show_fill: bpy.props.BoolProperty(  # type: ignore
        name='Fill', description='Fill the inside of the shape. Without a fill, only the outline picks the shape (the outline stays on)',
        default=True, update=update_shape_fill,
    )
    shape_fill_color: bpy.props.FloatVectorProperty(  # type: ignore
        name='Fill Color', description='Color inside the shape',
        subtype='COLOR', size=3, default=(0.95, 0.62, 0.15), min=0.0, max=1.0,
        update=update_shape_appearance,
    )
    shape_fill_opacity: bpy.props.FloatProperty(  # type: ignore
        name='Fill Opacity', description='Opacity of the fill',
        default=0.25, min=0.0, max=1.0, subtype='FACTOR',
        update=update_shape_appearance,
    )
    shape_show_outline: bpy.props.BoolProperty(  # type: ignore
        name='Outline', description='Draw a line around the shape. It stays on while the fill is off, so the shape never disappears',
        default=True, update=update_shape_outline,
    )
    shape_line_color: bpy.props.FloatVectorProperty(  # type: ignore
        name='Line Color', description='Color of the outline',
        subtype='COLOR', size=3, default=(0.95, 0.62, 0.15), min=0.0, max=1.0,
        update=update_shape_appearance,
    )
    shape_line_width: bpy.props.FloatProperty(  # type: ignore
        name='Line Width', description='Width of the outline on the canvas',
        default=3.0, min=1.0, max=40.0, update=update_shape_appearance,
    )
    shape_line_style: bpy.props.EnumProperty(  # type: ignore
        name='Line',
        description='How the outline is drawn',
        items=(
            ('SOLID', 'Solid', 'Continuous line'),
            ('DASHED', 'Dashed', 'Line made of dashes'),
            ('DOTTED', 'Dotted', 'Line made of dots'),
        ),
        default='SOLID', update=update_shape_appearance,
    )
    shape_corner_radius: bpy.props.FloatProperty(  # type: ignore
        name='Corner Radius',
        description=('Round every sharp corner between two straight edges with this radius, in '
                     'canvas units. 0 keeps sharp corners. A corner never uses more than half '
                     'of each edge'),
        default=0.0, min=0.0, soft_max=200.0, update=update_shape_appearance,
    )
    shape_line_join: bpy.props.EnumProperty(  # type: ignore
        name='Join', description='How the line turns at the corners of the outline',
        items=[(identifier, label, description, number) for number, (identifier, label, description)
               in enumerate((('ROUND', 'Round', 'Rounded corners'),
                             ('MITER', 'Miter', 'Sharp corners; very sharp ones are cut off'),
                             ('BEVEL', 'Bevel', 'Corners cut off straight')))],
        default='ROUND', update=update_shape_appearance,
    )
    shape_line_cap: bpy.props.EnumProperty(  # type: ignore
        name='Ends', description='How the ends of an open path and of each dash look',
        items=[(identifier, label, description, number) for number, (identifier, label, description)
               in enumerate((('ROUND', 'Round', 'Rounded ends'),
                             ('FLAT', 'Flat', 'Cut off square at the end point'),
                             ('SQUARE', 'Square', 'Cut off square, half the line width past '
                              'the end point')))],
        default='ROUND', update=update_shape_appearance,
    )
    shape_line_align: bpy.props.EnumProperty(  # type: ignore
        name='Align', description='Where the line lies on a closed outline',
        items=[(identifier, label, description, number) for number, (identifier, label, description)
               in enumerate((('CENTER', 'Center', 'Centered on the outline'),
                             ('INSIDE', 'Inside', 'Inside the outline: the shape keeps its size'),
                             ('OUTSIDE', 'Outside', 'Outside the outline')))],
        default='CENTER', update=update_shape_appearance,
    )
    shape_show_text: bpy.props.BoolProperty(  # type: ignore
        name='Text', description='Show the text of this shape, centered inside it',
        default=True, update=update_shape_appearance,
    )

    auto_resize: bpy.props.BoolProperty(  # type: ignore
        name='Auto Resize',
        description='Automatically resize frame to fit contained images',
        default=True,
        update=update_frame_auto_resize,
    )

    image_data: bpy.props.PointerProperty(  # type: ignore
        name='Image',
        description='Blender image displayed by this reference',
        type=bpy.types.Image,
        update=update_frame_geometry,
    )
    mask_enabled: bpy.props.BoolProperty(  # type: ignore
        name='Mask', description='Show only the painted parts of this image instance',
        default=False,
    )
    mask_dabs: bpy.props.CollectionProperty(type=KanvasMaskDab)  # type: ignore
    mask_polygons: bpy.props.CollectionProperty(type=KanvasMaskPolygon)  # type: ignore
    mask_next_sequence: bpy.props.IntProperty(default=1)  # type: ignore
    mask_revision: bpy.props.IntProperty(default=0, options={'SKIP_SAVE'})  # type: ignore
    mask_editing: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})  # type: ignore
    mask_tool: bpy.props.EnumProperty(  # type: ignore
        name='Mask Tool',
        description='Choose Brush, Polygon, or Rectangle while editing the mask',
        items=[
            ('BRUSH', 'Brush', 'Paint or erase freehand mask strokes'),
            ('POLYGON', 'Polygon', 'Click vertices to reveal or erase a straight-edged area'),
            ('RECTANGLE', 'Rectangle', 'Drag a rectangle; Shift makes it square and Ctrl draws from the center'),
            ('AUTO', 'Auto Select', 'Click a subject to select it (analyze the image first)'),
        ],
        default='BRUSH',
    )
    mask_brush_size: bpy.props.FloatProperty(  # type: ignore
        name='Brush Size', description='Round brush radius, measured in equivalent source image pixels',
        default=32.0, min=1.0, max=512.0,
    )
    mask_erase: bpy.props.BoolProperty(  # type: ignore
        name='Erase', description='Erase mask coverage instead of revealing it',
        default=False,
    )
    markup_visible: bpy.props.BoolProperty(  # type: ignore
        name='Color Markup', description='Show colored regions over this image',
        default=False,
    )
    markup_show_names: bpy.props.BoolProperty(  # type: ignore
        name='Names',
        description='Show each painted area\'s name at the center of every island',
        default=False,
        update=lambda self, context: _tag_markup_changed(self, context),
    )
    markup_show_done_lines: bpy.props.BoolProperty(  # type: ignore
        name='Done Lines',
        description='Draw diagonal lines over areas whose linked checklist task is done',
        default=True,
        update=lambda self, context: _tag_markup_changed(self, context),
    )
    markup_arrows_all_islands: bpy.props.BoolProperty(  # type: ignore
        name='Point All Islands',
        description=('Draw one checklist arrow to every painted island of a task, '
                     'instead of only to the nearest one'),
        default=False,
        update=lambda self, context: _tag_markup_changed(self, context),
    )
    markup_done_line_opacity: bpy.props.FloatProperty(  # type: ignore
        name='Line Opacity', description='Opacity of the diagonal done lines',
        default=0.5, min=0.0, max=1.0,
        update=lambda self, context: _tag_markup_changed(self, context),
    )
    markup_regions: bpy.props.CollectionProperty(type=KanvasMarkupRegion)  # type: ignore
    checklist_associations: bpy.props.CollectionProperty(  # type: ignore
        type=KanvasChecklistAssociation,
    )
    markup_isolate_id: bpy.props.StringProperty(  # type: ignore
        name='Isolated Region',
        description='Only this color region is shown while set (empty = show all)',
        default='',
        update=lambda self, context: _tag_markup_changed(self, context),
    )
    markup_active_index: bpy.props.IntProperty(  # type: ignore
        default=0, min=0,
        update=lambda self, context: _follow_isolation(self, context),
    )
    markup_revision: bpy.props.IntProperty(default=0, options={'SKIP_SAVE'})  # type: ignore
    markup_editing: bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'})  # type: ignore
    markup_tool: bpy.props.EnumProperty(  # type: ignore
        name='Color Tool',
        description='Brush, polygon, or rectangle tool for the active color region',
        items=[
            ('BRUSH', 'Brush', 'Paint the active color region'),
            ('POLYGON', 'Polygon', 'Fill a polygon with the active color'),
            ('RECTANGLE', 'Rectangle', 'Drag a rectangle; Shift makes it square and Ctrl draws from the center'),
            ('AUTO', 'Auto Select', 'Click a subject to color it (analyze the image first)'),
        ],
        default='BRUSH',
    )
    markup_brush_size: bpy.props.FloatProperty(  # type: ignore
        name='Brush Size', description='Color brush radius in source image pixels',
        default=32.0, min=1.0, max=512.0,
    )
    markup_erase: bpy.props.BoolProperty(  # type: ignore
        name='Erase Color', description='Erase paint from the active color region',
        default=False,
    )

    location: bpy.props.FloatVectorProperty(  # type: ignore
        name='Location',
        description='Center position of this item on the Kanvas canvas',
        size=2,
        default=(0.0, 0.0),
        update=update_frame_geometry,
    )

    scale_xy: bpy.props.FloatVectorProperty(  # type: ignore
        name='Stretch',
        description='Scale along each image axis before the overall scale',
        size=2,
        default=(1.0, 1.0),
        update=update_frame_geometry,
    )

    scale_master: bpy.props.FloatProperty(  # type: ignore
        name='Scale',
        description='Overall size multiplier for this reference',
        default=1.0,
        min=0.001,
        update=update_frame_geometry,
    )

    shear_xy: bpy.props.FloatVectorProperty(  # type: ignore
        name='Shear',
        description='Skew this image along its local X or Y axis',
        size=2,
        default=(0.0, 0.0),
        update=update_frame_geometry,
    )

    # Kanvas geometry and existing .blend files store this value in degrees.
    rotation: bpy.props.FloatProperty(  # type: ignore
        name='Rotation',
        description='Stored rotation in degrees',
        default=0.0,
        update=update_frame_geometry,
    )
    rotation_ui: bpy.props.FloatProperty(  # type: ignore
        name='Rotation',
        description='Positive values rotate clockwise',
        subtype='ANGLE',
        unit='ROTATION',
        get=get_rotation_ui,
        set=set_rotation_ui,
        options={'SKIP_SAVE'},
    )

    opacity: bpy.props.FloatProperty(  # type: ignore
        name='Opacity',
        description='Transparency of this image',
        default=1.0,
        min=0.0,
        max=1.0,
    )

    color_tint: bpy.props.FloatVectorProperty(  # type: ignore
        name='Color Tint',
        description='Multiply this image by a tint color',
        subtype='COLOR',
        size=3,
        default=(1.0, 1.0, 1.0),
        min=0.0,
        max=1.0,
    )

    show_in_editor: bpy.props.BoolProperty(  # type: ignore
        name='Show',
        description='Show this item on the Kanvas canvas',
        default=True,
        update=update_show_in_editor,
    )
    z_index: bpy.props.IntProperty(  # type: ignore
        name='Z-Index',
        description='Drawing order of this item relative to other items',
        default=0,
    )
    use_color_correction: bpy.props.BoolProperty(  # type: ignore
        name='Color Correction',
        description='Convert sRGB to Linear for correct viewport colors',
        default=True,
    )
    is_selected: bpy.props.BoolProperty(  # type: ignore
        name='Is Selected',
        description='Include this item in the current canvas selection',
        default=False, update=update_selection_order,
    )
    # When the item was selected, counted per board: tools that care about the order of
    # selection (a boolean Difference) read it. 0 while the item is not selected.
    selection_order: bpy.props.IntProperty(default=0)  # type: ignore
    is_locked: bpy.props.BoolProperty(  # type: ignore
        name='Locked',
        description='Prevent selection and direct canvas transformations; unlock from the item list',
        default=False,
        update=update_item_lock,
    )

    # Frame parenting — persistent ID of the Kanvas frame (empty = no parent).
    parent_frame: bpy.props.StringProperty(  # type: ignore
        name='Parent Frame',
        description='ID of the Kanvas frame containing this item',
        default='',
        update=update_frame_geometry,
    )
    released_parent_frame: bpy.props.StringProperty(  # type: ignore
        default='', options={'SKIP_SAVE'},
    )


    # Image Adjustments
    flip_h: bpy.props.BoolProperty(  # type: ignore
        name='Flip Horizontal',
        description='Mirror this image from left to right',
        default=False,
    )
    flip_v: bpy.props.BoolProperty(  # type: ignore
        name='Flip Vertical',
        description='Mirror this image from top to bottom',
        default=False,
    )
    value_gray: bpy.props.BoolProperty(  # type: ignore
        name='Grayscale',
        description='Show this image in grayscale to check its values (light and dark)',
        default=False,
        update=lambda self, context: _tag_markup_changed(self, context),
    )
    value_levels: bpy.props.IntProperty(  # type: ignore
        name='Posterize',
        description='Reduce this image to a few gray tones to check its values (0 is off, 2 to 12 tones)',
        default=0, min=0, max=12,
        update=lambda self, context: _tag_markup_changed(self, context),
    )
    brightness: bpy.props.FloatProperty(  # type: ignore
        name='Brightness',
        description='Adjust the displayed brightness of this image',
        default=1.0,
        min=0.0,
        max=5.0,
    )
    contrast: bpy.props.FloatProperty(  # type: ignore
        name='Contrast',
        description='Adjust the displayed contrast of this image',
        default=1.0,
        min=0.0,
        max=5.0,
    )
    saturation: bpy.props.FloatProperty(  # type: ignore
        name='Saturation',
        description='Adjust the displayed color saturation of this image',
        default=1.0,
        min=0.0,
        max=5.0,
    )

def update_active_image(self, context):
    if _selection_updates_suspended:
        return
    settings = _settings_for_item(self, context)

    if getattr(settings, "show_box_sel", False):
        return

    if 0 <= settings.active_image_index < len(settings.images):
        for arrow in settings.arrows:
            arrow.is_selected = False

    new_idx = settings.active_image_index
    if new_idx >= 0 and settings.active_arrow_index >= 0:
        settings.active_arrow_index = -1
    if 0 <= new_idx < len(settings.images):
        new_img = settings.images[new_idx]
        if new_img.is_locked:
            new_img.is_selected = False
            return
        selected_count = sum(1 for img in settings.images if img.is_selected)

        # Se a imagem clicada já faz parte de uma multi-seleção,
        # apenas atualiza o índice ativo sem destruir as outras seleções.
        # Isso permite que o drag de multi-seleção funcione corretamente.
        if new_img.is_selected and selected_count > 1:
            return

    if not settings.shift_is_held:
        for idx, img in enumerate(settings.images):
            img.is_selected = (idx == settings.active_image_index)
    else:
        if 0 <= settings.active_image_index < len(settings.images):
            settings.images[settings.active_image_index].is_selected = True

def _adjustment_source(settings):
    index = settings.active_image_index
    if 0 <= index < len(settings.images):
        active = settings.images[index]
        if active.item_type == 'IMAGE' and active.is_selected:
            return active
    return next((item for item in settings.images
                 if item.item_type == 'IMAGE' and item.is_selected), None)


def _batch_adjustment_get(name, default):
    def get(settings):
        source = _adjustment_source(settings)
        value = getattr(source, name) if source else default
        return tuple(value) if name == 'color_tint' else value
    return get


def _batch_adjustment_set(name):
    def set(settings, value):
        for item in settings.images:
            if item.item_type == 'IMAGE' and item.is_selected:
                setattr(item, name, value)
    return set


def update_active_arrow(self, context):
    if _selection_updates_suspended:
        return
    if not 0 <= self.active_arrow_index < len(self.arrows):
        return
    if self.arrows[self.active_arrow_index].is_locked:
        self.arrows[self.active_arrow_index].is_selected = False
        return
    for index, arrow in enumerate(self.arrows):
        arrow.is_selected = index == self.active_arrow_index
    for item in self.images:
        item.is_selected = False
    if self.active_image_index != -1:
        self.active_image_index = -1


class KanvasArrow(bpy.types.PropertyGroup):  # type: ignore
    is_selected: bpy.props.BoolProperty(  # type: ignore
        name='Is Selected',
        description='Include this arrow in the current canvas selection',
        default=False,
    )
    is_locked: bpy.props.BoolProperty(  # type: ignore
        name='Locked',
        description='Prevent canvas selection and movement of this arrow',
        default=False,
        update=update_arrow_lock,
    )
    arrow_id: bpy.props.StringProperty(  # type: ignore
        name='Arrow ID',
        description='Persistent identity of this Kanvas arrow',
        default='',
    )
    name: bpy.props.StringProperty(  # type: ignore
        name='Name',
        description='Name of this arrow in the item list',
        default='Arrow',
    )
    label: bpy.props.StringProperty(  # type: ignore
        name='Label',
        description='Text shown at the midpoint of the arrow',
        default='',
    )
    start: bpy.props.FloatVectorProperty(  # type: ignore
        name='Start',
        description='Canvas position of the arrow start when unattached',
        size=2,
    )
    end: bpy.props.FloatVectorProperty(  # type: ignore
        name='End',
        description='Canvas position of the arrow end when unattached',
        size=2,
    )
    curve_offset: bpy.props.FloatVectorProperty(  # type: ignore
        name='Curve Offset',
        description='Offset of the arrow midpoint from the straight line',
        size=2,
        default=(0.0, 0.0),
    )
    start_item_id: bpy.props.StringProperty(  # type: ignore
        name='Start Anchor',
        description='Item attached to the start of this arrow',
        default='',
    )
    end_item_id: bpy.props.StringProperty(  # type: ignore
        name='End Anchor',
        description='Item attached to the end of this arrow',
        default='',
    )
    start_line_id: bpy.props.StringProperty(default='')  # type: ignore
    end_line_id: bpy.props.StringProperty(default='')  # type: ignore
    start_uv: bpy.props.FloatVectorProperty(  # type: ignore
        name='Start Anchor Position',
        description='Position of the start anchor within its attached item',
        size=2,
        default=(0.5, 0.5),
    )
    end_uv: bpy.props.FloatVectorProperty(  # type: ignore
        name='End Anchor Position',
        description='Position of the end anchor within its attached item',
        size=2,
        default=(0.5, 0.5),
    )
    color: bpy.props.FloatVectorProperty(  # type: ignore
        name='Color',
        description='Color of the arrow and its label accent',
        subtype='COLOR',
        size=4,
        default=(1.0, 0.72, 0.18, 1.0),
        min=0.0,
        max=1.0,
    )
    thickness: bpy.props.FloatProperty(  # type: ignore
        name='Thickness',
        description='Width of the arrow stroke on the canvas',
        default=2.5,
        min=1.0,
        max=20.0,
    )
    line_style: bpy.props.EnumProperty(  # type: ignore
        name='Line',
        description='How the arrow line is drawn',
        items=(
            ('SOLID', 'Solid', 'Continuous line'),
            ('DASHED', 'Dashed', 'Line made of dashes'),
            ('DOTTED', 'Dotted', 'Line made of dots'),
        ),
        default='SOLID',
    )
    head_style: bpy.props.EnumProperty(  # type: ignore
        name='Heads',
        description='Where the arrow has a head',
        items=(
            ('END', 'End', 'Arrowhead at the end'),
            ('BOTH', 'Both', 'Arrowheads at both ends'),
            ('NONE', 'None', 'Plain line without arrowheads'),
        ),
        default='END',
    )


class KanvasSettings(bpy.types.PropertyGroup):
    images: bpy.props.CollectionProperty(  # type: ignore
        type=KanvasImageItem,
    )
    list_search: bpy.props.StringProperty(  # type: ignore
        name='Search Items or Frames',
        description='Filter the item list by name, card text, or color region name without hiding canvas content',
        default='',
        options={'SKIP_SAVE'},
    )
    arrows: bpy.props.CollectionProperty(  # type: ignore
        type=KanvasArrow,
    )
    active_arrow_index: bpy.props.IntProperty(  # type: ignore
        name='Active Arrow',
        description='Index of the active arrow in the Kanvas list',
        default=-1,
        update=update_active_arrow,
    )
    arrow_dragging: bpy.props.BoolProperty(  # type: ignore
        options={'SKIP_SAVE'},
    )
    arrow_quick_active: bpy.props.BoolProperty(  # type: ignore
        options={'SKIP_SAVE'},
    )
    arrow_hover: bpy.props.FloatVectorProperty(  # type: ignore
        size=2,
        options={'SKIP_SAVE'},
    )
    arrow_hover_valid: bpy.props.BoolProperty(  # type: ignore
        options={'SKIP_SAVE'},
    )
    arrow_hover_item_id: bpy.props.StringProperty(  # type: ignore
        options={'SKIP_SAVE'},
    )
    drop_target_frame: bpy.props.StringProperty(  # type: ignore
        default='',
        options={'SKIP_SAVE'},
    )
    active_image_index: bpy.props.IntProperty(  # type: ignore
        name='Active Image Index',
        description='Index of the active item in the Kanvas list',
        default=0,
        update=update_active_image,
    )

    show_debug_grid: bpy.props.BoolProperty(  # type: ignore
        name='Show Debug Grid',
        description='Show the canvas origin axes',
        default=True,
    )
    # Older draw callbacks may remain alive until Blender restarts after addon reload.
    show_all: bpy.props.BoolProperty(  # type: ignore
        name='Legacy Canvas Visibility',
        description='Saved visibility setting from older Kanvas versions',
        default=True,
        options={'HIDDEN'},
    )

    batch_flip_h: bpy.props.BoolProperty(  # type: ignore
        name='Flip Horizontal',
        description='Mirror all selected images from left to right',
        get=_batch_adjustment_get('flip_h', False),
        set=_batch_adjustment_set('flip_h'),
        options={'SKIP_SAVE'},
    )

    batch_flip_v: bpy.props.BoolProperty(  # type: ignore
        name='Flip Vertical',
        description='Mirror all selected images from top to bottom',
        get=_batch_adjustment_get('flip_v', False),
        set=_batch_adjustment_set('flip_v'),
        options={'SKIP_SAVE'},
    )

    batch_value_gray: bpy.props.BoolProperty(  # type: ignore
        name='Grayscale',
        description='Show all selected images in grayscale',
        get=_batch_adjustment_get('value_gray', False),
        set=_batch_adjustment_set('value_gray'),
        options={'SKIP_SAVE'},
    )
    batch_value_levels: bpy.props.IntProperty(  # type: ignore
        name='Posterize',
        description='Reduce all selected images to a few gray tones (0 is off, 2 to 12 tones)',
        default=0, min=0, max=12,
        get=_batch_adjustment_get('value_levels', 0),
        set=_batch_adjustment_set('value_levels'),
        options={'SKIP_SAVE'},
    )

    batch_brightness: bpy.props.FloatProperty(  # type: ignore
        name='Brightness',
        description='Set the brightness of all selected images',
        default=1.0,
        min=0.0,
        max=5.0,
        get=_batch_adjustment_get('brightness', 1.0),
        set=_batch_adjustment_set('brightness'),
        options={'SKIP_SAVE'},
    )
    batch_contrast: bpy.props.FloatProperty(  # type: ignore
        name='Contrast',
        description='Set the contrast of all selected images',
        default=1.0,
        min=0.0,
        max=5.0,
        get=_batch_adjustment_get('contrast', 1.0),
        set=_batch_adjustment_set('contrast'),
        options={'SKIP_SAVE'},
    )

    batch_saturation: bpy.props.FloatProperty(  # type: ignore
        name='Saturation',
        description='Set the color saturation of all selected images',
        default=1.0,
        min=0.0,
        max=5.0,
        get=_batch_adjustment_get('saturation', 1.0),
        set=_batch_adjustment_set('saturation'),
        options={'SKIP_SAVE'},
    )

    batch_opacity: bpy.props.FloatProperty(  # type: ignore
        name='Opacity',
        description='Set the opacity of all selected images',
        default=1.0,
        min=0.0,
        max=1.0,
        get=_batch_adjustment_get('opacity', 1.0),
        set=_batch_adjustment_set('opacity'),
        options={'SKIP_SAVE'},
    )

    batch_color_tint: bpy.props.FloatVectorProperty(  # type: ignore
        name='Color Tint',
        description='Set the tint color of all selected images',
        subtype='COLOR',
        default=(1.0, 1.0, 1.0),
        size=3,
        min=0.0,
        max=1.0,
        get=_batch_adjustment_get('color_tint', (1.0, 1.0, 1.0)),
        set=_batch_adjustment_set('color_tint'),
        options={'SKIP_SAVE'},
    )

    batch_use_color_correction: bpy.props.BoolProperty(  # type: ignore
        name='Color Correction',
        description='Apply sRGB to Linear conversion to all selected images',
        get=_batch_adjustment_get('use_color_correction', True),
        set=_batch_adjustment_set('use_color_correction'),
        options={'SKIP_SAVE'},
    )

    is_modal_running: bpy.props.BoolProperty(  # type: ignore
        name='Is Modal Running',
        description='Whether a Kanvas canvas gesture is active',
        default=False,
    )

    batch_loading: bpy.props.BoolProperty(  # type: ignore
        default=False,
        options={'SKIP_SAVE'},
    )

    use_interactivity: bpy.props.BoolProperty(  # type: ignore
        name='Interactivity',
        description='Allow moving and scaling images in the viewport',
        default=True,
    )

    canvas_mode: bpy.props.EnumProperty(  # type: ignore
        name='Mode',
        description='Edit: full editing. Move: left click only pans the canvas',
        items=[
            ('EDIT', 'Edit', 'Select and edit images, cards and frames', 'RESTRICT_SELECT_OFF', 0),
            ('MOVE', 'Move', 'Left click drag pans the canvas without changing anything', 'VIEW_PAN', 1),
        ],
        default='EDIT',
        update=update_canvas_mode,
    )

    # Gizmo Settings
    show_gizmos: bpy.props.BoolProperty(  # type: ignore
        name='Show Gizmos',
        description='Show transform handles on selected images',
        default=True,
    )
    gizmo_size: bpy.props.FloatProperty(  # type: ignore
        name='Gizmo Size',
        description='Size of image transform handles in screen pixels',
        default=25.0,
        min=10.0,
        max=100.0,
    )
    show_scale_handles: bpy.props.BoolProperty(  # type: ignore
        name='Scale Handles',
        description='Show corner and edge handles for scaling selected images',
        default=True,
    )
    show_rotate_handles: bpy.props.BoolProperty(  # type: ignore
        name='Rotate Handles',
        description='Show the circular rotation handle on selected images',
        default=True,
    )
    show_hitbox_debug: bpy.props.BoolProperty(  # type: ignore
        name='Show Hitbox Debug',
        description='Draw hit areas used to detect canvas clicks',
        default=False,
    )

    # Snapping Settings
    snap_grid: bpy.props.BoolProperty(  # type: ignore
        name='Grid Snap',
        description='Snap item movements and transforms to the Kanvas grid',
        default=True,
    )
    selection_counter: bpy.props.IntProperty(default=0)  # type: ignore
    # 1: the item list is the stacking order (frames carry the layer of their content).
    stack_version: bpy.props.IntProperty(default=0)  # type: ignore
    snap_shape_vertices: bpy.props.BoolProperty(  # type: ignore
        name='Vertex Snap',
        description='In Edit Vertices, snap a dragged vertex to the vertices of other shapes',
        default=False,
    )
    snap_images: bpy.props.BoolProperty(  # type: ignore
        name='Image Snap',
        description='Snap item edges and centers to other visible images',
        default=True,
    )
    grid_size: bpy.props.IntProperty(  # type: ignore
        name='Grid Size',
        description='Spacing between grid snap positions in canvas units',
        default=20,
        min=1,
    )
    snap_threshold: bpy.props.FloatProperty(  # type: ignore
        name='Threshold',
        description='Maximum screen distance before a snap target is ignored',
        default=10.0,
        min=1.0,
    )

    # Transient Snap Visualization (Not saved)
    snap_viz_x: bpy.props.FloatProperty(  # type: ignore
        options={'SKIP_SAVE'},
    )
    snap_viz_y: bpy.props.FloatProperty(  # type: ignore
        options={'SKIP_SAVE'},
    )
    show_snap_viz_x: bpy.props.BoolProperty(  # type: ignore
        options={'SKIP_SAVE'},
    )
    show_snap_viz_y: bpy.props.BoolProperty(  # type: ignore
        options={'SKIP_SAVE'},
    )

    # UI State
    shift_is_held: bpy.props.BoolProperty(  # type: ignore
        options={'SKIP_SAVE'},
    )
    alt_is_held: bpy.props.BoolProperty(  # type: ignore
        options={'SKIP_SAVE'},
    )
    ctrl_is_held: bpy.props.BoolProperty(  # type: ignore
        options={'SKIP_SAVE'},
    )
    f_is_held: bpy.props.BoolProperty(  # type: ignore
        options={'SKIP_SAVE'},
    )

    # Box Selection (Transient)
    box_sel_start: bpy.props.FloatVectorProperty(  # type: ignore
        size=2,
        options={'SKIP_SAVE'},
    )
    box_sel_end: bpy.props.FloatVectorProperty(  # type: ignore
        size=2,
        options={'SKIP_SAVE'},
    )
    show_box_sel: bpy.props.BoolProperty(  # type: ignore
        default=False,
        options={'SKIP_SAVE'},
    )

class KanvasNodeTree(bpy.types.NodeTree): # type: ignore
    """A custom node tree for managing Kanvas references."""
    bl_idname = 'KanvasNodeTree'
    bl_label = 'Kanvas Tree'
    bl_icon = 'IMAGE'

def register():
    KanvasNodeTree.kanvas_settings = bpy.props.PointerProperty(
        type=KanvasSettings,
    )
    bpy.types.Scene.kanvas_settings = bpy.props.PointerProperty(
        type=KanvasSettings,
    )
    bpy.types.Scene.kanvas_tree_migrated = bpy.props.BoolProperty(default=False)

def unregister():
    del bpy.types.Scene.kanvas_tree_migrated
    del bpy.types.Scene.kanvas_settings
    del KanvasNodeTree.kanvas_settings
