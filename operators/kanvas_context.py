"""Context guard shared by operators that edit a Kanvas tree."""


class KanvasTreeOnly:
    @classmethod
    def poll(cls, context):
        space = getattr(context, 'space_data', None)
        if not space or space.type != 'NODE_EDITOR':
            return False
        tree = getattr(space, 'edit_tree', None)
        return tree is not None and tree.bl_idname == 'KanvasNodeTree'


class KanvasDrawingTool(KanvasTreeOnly):
    """Pencil and eraser actions: never in Move mode, where the canvas is only panned."""
    @classmethod
    def poll(cls, context):
        if not super().poll(context):
            return False
        return context.space_data.edit_tree.kanvas_settings.canvas_mode != 'MOVE'
