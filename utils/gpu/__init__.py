import bpy
from .grid import draw_axes
from .guides import draw_snap_guides
from .frame import draw_kanvas_frame
from .image import get_kanvas_texture, invalidate_texture_cache, clear_texture_cache
from .selection import draw_selection_box

def draw_callback_px(*args):
    """SpaceNodeEditor POST_VIEW draw callback."""
    context = bpy.context

    if not hasattr(context, "scene") or context.scene is None:
        return

    if (not hasattr(context, "space_data")
            or not hasattr(context.space_data, "edit_tree")
            or context.space_data.edit_tree is None
            or context.space_data.edit_tree.bl_idname != 'KanvasNodeTree'):
        return

    try:
        settings = context.scene.kanvas_settings
    except AttributeError:
        return

    # Calculate view_pixel_size
    try:
        region = context.region
        v2d = region.view2d
        p0 = v2d.region_to_view(0, 0)
        p1 = v2d.region_to_view(1, 1)
        view_pixel_size = abs(p1[0] - p0[0])
    except Exception:
        return

    # 1. Draw Frames
    if context.space_data.edit_tree:
        for node in context.space_data.edit_tree.nodes:
            if node.type == 'FRAME':
                try:
                    draw_kanvas_frame(node, view_pixel_size)
                except:
                    pass

    if settings.show_debug_grid:
        try: draw_axes()
        except: pass

    if settings.use_snapping:
        try: draw_snap_guides(settings)
        except: pass

    if not settings.show_all:
        return

    # Draw Selection Box
    try: draw_selection_box(settings)
    except: pass

    selected_images = [img for img in settings.images if img.is_selected and img.show_in_editor and img.image_data]
    multi_select = len(selected_images) > 1
    
    if multi_select:
        from .common import get_collective_bounding_box, get_prefs
        data_list = []
        for img in selected_images:
            tex = get_kanvas_texture(img.image_data)
            if tex.texture:
                data_list.append((img.location, img.scale_xy, img.scale_master, img.shear_xy, img.rotation, tex.texture.width, tex.texture.height))
        collective_bbox = get_collective_bounding_box(data_list)
        
        if collective_bbox:
            from .image import draw_collective_outline, draw_collective_gizmos
            prefs = get_prefs()
            if prefs:
                try:
                    draw_collective_outline(collective_bbox, prefs.color_selection, prefs.selection_thickness)
                    if settings.show_gizmos:
                        draw_collective_gizmos(collective_bbox, settings.gizmo_size * view_pixel_size)
                except:
                    pass

    invalidate_texture_cache()

    for img_item in settings.images:
        if not img_item.show_in_editor or not img_item.image_data:
            continue
        
        try:
            tex = get_kanvas_texture(img_item.image_data)
            final_scale = (img_item.scale_xy[0] * img_item.scale_master, img_item.scale_xy[1] * img_item.scale_master)
            
            tex.draw(
                img_item.location,
                final_scale,
                img_item.shear_xy,
                img_item.rotation,
                img_item.opacity,
                img_item.color_tint,
                brightness=img_item.brightness,
                contrast=img_item.contrast,
                saturation=img_item.saturation,
                flip_h=img_item.flip_h,
                flip_v=img_item.flip_v,
                use_color_correction=img_item.use_color_correction,
            )

            if img_item.is_selected and not multi_select:
                tex.draw_outline(img_item.location, final_scale, img_item.shear_xy, img_item.rotation)
                if settings.show_gizmos:
                    tex.draw_gizmos(
                        img_item.location,
                        final_scale,
                        img_item.shear_xy,
                        img_item.rotation,
                        settings.gizmo_size * view_pixel_size,
                    )
        except Exception as e:
            # Silently fail individual image drawing to prevent whole-UI crash
            pass

class KanvasDrawHandler:
    _handler = None

    @classmethod
    def add_handler(cls):
        if cls._handler is None:
            cls._handler = bpy.types.SpaceNodeEditor.draw_handler_add(
                draw_callback_px, (), 'WINDOW', 'POST_VIEW'
            )

    @classmethod
    def remove_handler(cls):
        if cls._handler is not None:
            bpy.types.SpaceNodeEditor.draw_handler_remove(cls._handler, 'WINDOW')
            cls._handler = None

def register():
    KanvasDrawHandler.add_handler()

def unregister():
    KanvasDrawHandler.remove_handler()
    clear_texture_cache()
