import bpy
from . import auto_load

auto_load.init()


# ---------------------------------------------------------------------------
# Idle maintenance only. Input is dispatched by the addon keymap, so this
# timer must never start a modal operator.
# ---------------------------------------------------------------------------

def _kanvas_maintenance():
    """
    Release idle textures and synchronize visible Kanvas frames.
    """
    try:
        # This timer also runs when the editor is idle, so hidden or offscreen
        # references can release their shared Blender GPU textures.
        from .utils.gpu.gpu_image import prune_texture_cache
        prune_texture_cache()
        from .utils.hidden_datablocks import sweep_throttled
        sweep_throttled()
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type != 'NODE_EDITOR':
                    continue
                space = area.spaces.active
                if not space or not space.edit_tree:
                    continue
                if space.edit_tree.bl_idname != 'KanvasNodeTree':
                    continue

                settings = space.edit_tree.kanvas_settings
                if settings.is_modal_running:
                    continue

                # Sincroniza frames se necessário (seguro no timer thread)
                try:
                    from .utils.gpu import is_sync_needed, sync_kanvas_frames
                    if is_sync_needed(space.edit_tree, settings):
                        sync_kanvas_frames(space.edit_tree, settings)
                except Exception:
                    pass

                settings.use_interactivity = True

    except Exception:
        pass

    return 0.5


@bpy.app.handlers.persistent
def ensure_kanvas_protection(dummy):
    """Ensure all Kanvas trees are protected from Purge on file load."""
    from .operators.ops_modal import clear_modal_areas
    from .utils.hidden_datablocks import sweep as hide_kanvas_datablocks
    from .utils.kanvas_data import migrate_legacy_scenes, ensure_unique_tree_annotations
    from .utils.gpu.gpu_mask import clear_mask_cache
    from .utils.gpu.gpu_markup import clear_markup_cache

    clear_modal_areas()
    clear_mask_cache()
    hide_kanvas_datablocks()
    from . import keymap
    keymap.sync_hand_cursor()
    clear_markup_cache()
    migrate_legacy_scenes()
    ensure_unique_tree_annotations()
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'KanvasNodeTree':
            tree.use_fake_user = True
            settings = tree.kanvas_settings
            settings.is_modal_running = False
            settings.show_box_sel = False
            settings.arrow_quick_active = False
            settings.arrow_dragging = False
            settings.arrow_hover_valid = False
            for item in settings.images:
                item.mask_editing = False
                item.markup_editing = False
            _migrate_text_card_titles(settings)
            _migrate_stack_order(settings)
            _restore_image_frame_auto_fit(settings)


@bpy.app.handlers.persistent
def protect_kanvas_trees_before_save(dummy):
    from .utils.kanvas_data import ensure_unique_tree_annotations

    ensure_unique_tree_annotations()
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'KanvasNodeTree':
            tree.use_fake_user = True


@bpy.app.handlers.persistent
def refresh_kanvas_after_undo(dummy):
    """Undo can restore mask data with an earlier revision and cache signature."""
    from .utils.gpu.gpu_mask import clear_mask_cache
    from .utils.gpu.gpu_markup import clear_markup_cache

    clear_mask_cache()
    clear_markup_cache()
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'NODE_EDITOR':
                area.tag_redraw()


def _restore_image_frame_auto_fit(settings):
    """Upgrade frames saved with manual bounds while they contain images."""
    from .utils.gpu import frame_ancestors, frame_has_content, update_frame_bounds

    frames = [item for item in settings.images if item.item_type == 'FRAME']
    frames.sort(key=lambda frame: len(frame_ancestors(settings, frame)), reverse=True)
    for frame in frames:
        if frame_has_content(settings, frame.frame_node_name):
            if not frame.auto_resize:
                frame.auto_resize = True
            update_frame_bounds(None, settings, frame.frame_node_name)


def _migrate_stack_order(settings):
    """Boards saved before the list became the stacking order: frames and groups had
    no layer of their own (0), so they would all sink to the back with their content.
    Give each one the layer of its front member, innermost first."""
    if settings.stack_version >= 1:
        return
    from .utils.gpu import frame_ancestors
    frames = [item for item in settings.images if item.item_type == 'FRAME']
    frames.sort(key=lambda frame: len(frame_ancestors(settings, frame)), reverse=True)
    for frame in frames:
        layers = [item.z_index for item in settings.images
                  if item.parent_frame == frame.frame_node_name]
        if layers and max(layers) > frame.z_index:
            frame.z_index = max(layers)
    settings.stack_version = 1


def _migrate_text_card_titles(settings):
    """Preserve the visible title (or its absence) from older saved cards."""
    for item in settings.images:
        if item.item_type != 'TEXT' or item.is_property_set('text_show_header'):
            continue
        old_header = item.text_header.strip()
        if old_header:
            item.name = old_header
            item.text_show_header = True
            item.text_header = ''
        else:
            item.text_show_header = False


def _restore_loaded_frames():
    """Run after registration, when Blender has released restricted bpy.data."""
    try:
        scenes = tuple(bpy.data.scenes)
    except AttributeError:
        return 0.5
    from .utils.kanvas_data import migrate_legacy_scenes
    from .operators.ops_mask import clear_stale_paint_state
    migrate_legacy_scenes()
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'KanvasNodeTree':
            tree.use_fake_user = True
            clear_stale_paint_state(tree)
            _migrate_text_card_titles(tree.kanvas_settings)
            _migrate_stack_order(tree.kanvas_settings)
            _restore_image_frame_auto_fit(tree.kanvas_settings)
    return None





def register():
    auto_load.register()

    # Hot reload can preserve SKIP_SAVE flags after the old paint modal is gone.
    # Clear them now when bpy.data is available; the deferred restore retries.
    try:
        from .operators.ops_mask import clear_stale_paint_state
        for tree in bpy.data.node_groups:
            if tree.bl_idname == 'KanvasNodeTree':
                clear_stale_paint_state(tree)
                tree.kanvas_settings.is_modal_running = False
    except AttributeError:
        pass

    # Manual fallback for Scene properties
    if not hasattr(bpy.types.Scene, "kanvas_settings"):
        from . import properties
        properties.register()

    bpy.app.handlers.load_post.append(ensure_kanvas_protection)
    bpy.app.handlers.save_pre.append(protect_kanvas_trees_before_save)
    bpy.app.handlers.undo_post.append(refresh_kanvas_after_undo)
    bpy.app.handlers.redo_post.append(refresh_kanvas_after_undo)
    bpy.types.NODE_HT_header.append(_draw_mode_header)

    if not bpy.app.timers.is_registered(_restore_loaded_frames):
        bpy.app.timers.register(_restore_loaded_frames, first_interval=0.5)

    if not bpy.app.timers.is_registered(_kanvas_maintenance):
        bpy.app.timers.register(_kanvas_maintenance, first_interval=1.0, persistent=True)


def _draw_mode_header(self, context):
    tree = getattr(context.space_data, 'edit_tree', None)
    if tree is not None and tree.bl_idname == 'KanvasNodeTree':
        self.layout.prop(tree.kanvas_settings, 'canvas_mode', expand=True)


def unregister():
    try:
        bpy.types.NODE_HT_header.remove(_draw_mode_header)
    except (ValueError, RuntimeError):
        pass
    if bpy.app.timers.is_registered(_restore_loaded_frames):
        bpy.app.timers.unregister(_restore_loaded_frames)
    if bpy.app.timers.is_registered(_kanvas_maintenance):
        bpy.app.timers.unregister(_kanvas_maintenance)

    if ensure_kanvas_protection in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(ensure_kanvas_protection)
    if protect_kanvas_trees_before_save in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(protect_kanvas_trees_before_save)
    if refresh_kanvas_after_undo in bpy.app.handlers.undo_post:
        bpy.app.handlers.undo_post.remove(refresh_kanvas_after_undo)
    if refresh_kanvas_after_undo in bpy.app.handlers.redo_post:
        bpy.app.handlers.redo_post.remove(refresh_kanvas_after_undo)

    from .operators.ops_modal import clear_modal_areas
    clear_modal_areas()
    from .utils import sam_engine
    sam_engine.shutdown()
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'KanvasNodeTree':
            tree.kanvas_settings.is_modal_running = False
            tree.kanvas_settings.arrow_quick_active = False
            tree.kanvas_settings.arrow_dragging = False

    from . import keymap
    keymap.unregister()
    auto_load.unregister()

    if hasattr(bpy.types.Scene, "kanvas_settings"):
        from . import properties
        properties.unregister()
