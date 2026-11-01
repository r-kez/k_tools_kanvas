"""Context guard shared by operators that edit a Kanvas tree."""


class KanvasTreeOnly:
    @classmethod
    def poll(cls, context):
        space = getattr(context, 'space_data', None)
        if not space or space.type != 'NODE_EDITOR':
            return False
        tree = getattr(space, 'edit_tree', None)
        return tree is not None and tree.bl_idname == 'KanvasNodeTree'
