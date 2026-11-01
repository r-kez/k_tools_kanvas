import bpy

class KANVAS_UL_image_list(bpy.types.UIList):
    def filter_items(self, context, data, propname):
        from ..utils.gpu import get_frame
        items = getattr(data, propname)
        query = data.list_search.strip().casefold()
        if query:
            frame_indices = {item.frame_node_name: index
                             for index, item in enumerate(items)
                             if item.item_type == 'FRAME'}
            ancestors = []
            for item in items:
                chain, seen, name = [], set(), item.parent_frame
                while name and name not in seen:
                    seen.add(name)
                    chain.append(name)
                    parent_index = frame_indices.get(name)
                    name = items[parent_index].parent_frame if parent_index is not None else ''
                ancestors.append(chain)
            from ..utils.item_search import item_matches
            matched = {index for index, item in enumerate(items)
                       if item_matches(item, query)}
            visible = set(matched)
            for index in matched:
                visible.update(frame_indices[name] for name in ancestors[index]
                               if name in frame_indices)
                item = items[index]
                if item.item_type == 'FRAME':
                    visible.update(child_index for child_index, chain in enumerate(ancestors)
                                   if item.frame_node_name in chain)
            return [self.bitflag_filter_item if index in visible else 0
                    for index in range(len(items))], []
        collapsed = {item.frame_node_name for item in items
                     if item.item_type == 'FRAME' and item.list_collapsed}
        def visible(item):
            seen, name = set(), item.parent_frame
            while name and name not in seen:
                if name in collapsed:
                    return False
                seen.add(name)
                parent = get_frame(data, name)
                name = parent.parent_frame if parent else ''
            return True
        flags = [self.bitflag_filter_item if visible(item) else 0 for item in items]
        return flags, []

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        is_frame = (getattr(item, "item_type", 'IMAGE') == 'FRAME')
        is_text = (getattr(item, "item_type", 'IMAGE') == 'TEXT')
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            from ..utils.gpu import get_frame, frame_ancestors, frame_descendants
            parent = get_frame(data, item.parent_frame) if item.parent_frame else None
            depth = 1 + len(frame_ancestors(data, parent)) if parent else 0
            descendants = frame_descendants(data, item.frame_node_name) if is_frame else []
            active_index = data.active_image_index
            active_child = (data.images[active_index]
                            if 0 <= active_index < len(data.images) else None)
            hidden_active = (is_frame and item.list_collapsed and active_child
                             and any(child.item_id == active_child.item_id
                                     for child in descendants))

            # Indent the whole hierarchy row; reserve the right edge for
            # status, descendant count, and visibility controls.
            columns = layout.split(factor=0.72, align=True)
            main = columns.row(align=True)
            trailing = columns.row(align=True)

            for level in range(min(depth, 5)):
                indent = main.row(align=True)
                indent.ui_units_x = 0.65
                indent.label(text="└" if level == min(depth, 5) - 1 else "")

            collapse = main.row(align=True)
            collapse.ui_units_x = 1.0
            if is_frame:
                collapse.prop(item, "list_collapsed", text="",
                              icon='TRIA_RIGHT' if item.list_collapsed else 'TRIA_DOWN',
                              emboss=False)
            else:
                collapse.label(text="", icon='BLANK1')

            kind = main.row(align=True)
            kind.ui_units_x = 1.0
            kind.label(text="", icon='FULLSCREEN_ENTER' if is_frame else
                       'TEXT' if is_text else 'IMAGE_DATA')

            name = main.row(align=True)
            name.prop(item, "name", text="", emboss=False)

            active_mark = trailing.row(align=True)
            active_mark.ui_units_x = 0.8
            active_mark.label(text="", icon='RADIOBUT_ON' if hidden_active else 'BLANK1')
            count = trailing.row(align=True)
            count.alignment = 'RIGHT'
            count.label(text=str(len(descendants)) if is_frame else " ")
            lock = trailing.row(align=True)
            lock.ui_units_x = 1.0
            lock.prop(item, "is_locked", text="",
                      icon='LOCKED' if item.is_locked else 'UNLOCKED',
                      emboss=False)
            visibility = trailing.row(align=True)
            visibility.ui_units_x = 1.0
            visibility.prop(item, "show_in_editor", text="",
                            icon='HIDE_OFF' if item.show_in_editor else 'HIDE_ON',
                            emboss=False)
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            icon_type = 'FULLSCREEN_ENTER' if is_frame else ('TEXT' if is_text else 'IMAGE_DATA')
            layout.label(text="", icon=icon_type)

