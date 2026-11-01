"""Resolve the Kanvas board owned by the active Node Tree."""

import re


def unique_item_name(settings, requested):
    """Return a board-wide Blender-style label without changing existing names."""
    existing = {item.name for item in settings.images}
    existing.update(arrow.name for arrow in settings.arrows)
    if requested not in existing:
        return requested
    match = re.fullmatch(r'(.*)\.(\d{3,})', requested)
    base = match.group(1) if match else requested
    number = int(match.group(2)) + 1 if match else 1
    while f'{base}.{number:03d}' in existing:
        number += 1
    return f'{base}.{number:03d}'


def get_settings(context):
    space = getattr(context, 'space_data', None)
    tree = getattr(space, 'edit_tree', None) if space else None
    if tree is None:
        tree = getattr(context, 'kanvas_tree', None)
    if tree is not None and tree.bl_idname == 'KanvasNodeTree':
        ensure_unique_tree_annotation(tree)
        return tree.kanvas_settings
    # Used only by legacy file migration and headless harnesses without an
    # active Node Editor. Interactive operators poll for a Kanvas tree.
    scene = getattr(context, 'scene', None)
    return getattr(scene, 'kanvas_settings', None)


def ensure_unique_tree_annotation(tree):
    """Blender duplicates a NodeTree while retaining its annotation datablock."""
    import bpy

    annotation = tree.annotation
    if annotation is None:
        return
    if any(other != tree and other.bl_idname == 'KanvasNodeTree'
           and other.annotation == annotation for other in bpy.data.node_groups):
        tree.annotation = annotation.copy()


def ensure_unique_tree_annotations():
    import bpy

    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'KanvasNodeTree':
            ensure_unique_tree_annotation(tree)


def _copy_properties(source, target, excluded=()):
    for prop in source.bl_rna.properties:
        name = prop.identifier
        if name in excluded or name in {'rna_type', 'text_body'}:
            continue
        if prop.type == 'COLLECTION':
            source_items = getattr(source, name)
            target_items = getattr(target, name)
            for source_item in source_items:
                _copy_properties(source_item, target_items.add())
        else:
            if prop.is_readonly:
                continue
            value = getattr(source, name)
            setattr(target, name, tuple(value)
                    if getattr(prop, 'array_length', 0) else value)


def migrate_legacy_scenes():
    """Copy old scene boards once, retaining source data for rollback."""
    import bpy
    from ..properties import suspend_frame_geometry_updates, suspend_selection_updates

    trees = sorted((tree for tree in bpy.data.node_groups
                    if tree.bl_idname == 'KanvasNodeTree'), key=lambda tree: tree.name)
    claimed = set()
    for scene in bpy.data.scenes:
        if scene.kanvas_tree_migrated:
            continue
        legacy = scene.kanvas_settings
        if not legacy.images and not legacy.arrows:
            continue
        visible = []
        for window in bpy.context.window_manager.windows:
            if window.scene != scene:
                continue
            for area in window.screen.areas:
                if area.type == 'NODE_EDITOR':
                    tree = getattr(area.spaces.active, 'edit_tree', None)
                    if tree and tree.bl_idname == 'KanvasNodeTree':
                        visible.append(tree)
        candidates = visible + trees
        target = next((tree for tree in candidates
                       if tree.name not in claimed
                       and not tree.kanvas_settings.images
                       and not tree.kanvas_settings.arrows), None)
        if target is None:
            target = bpy.data.node_groups.new(f'{scene.name} Kanvas', 'KanvasNodeTree')
            trees.append(target)
        with suspend_frame_geometry_updates(), suspend_selection_updates():
            _copy_properties(legacy, target.kanvas_settings)
        target.kanvas_settings.is_modal_running = False
        target.kanvas_settings.show_box_sel = False
        target.kanvas_settings.batch_loading = False
        target.use_fake_user = True
        for window in bpy.context.window_manager.windows:
            if window.scene != scene:
                continue
            for area in window.screen.areas:
                if (area.type == 'NODE_EDITOR'
                        and area.ui_type == 'KanvasNodeTree'
                        and getattr(area.spaces.active, 'edit_tree', None) is None):
                    area.spaces.active.node_tree = target
        claimed.add(target.name)
        scene.kanvas_tree_migrated = True
