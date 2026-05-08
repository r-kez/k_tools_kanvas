import bpy

class KanvasNodeTree(bpy.types.NodeTree):
    """Custom Node Tree for Kanvas References"""
    bl_idname = 'KanvasNodeTree'
    bl_label = 'Kanvas'
    bl_icon = 'IMAGE_DATA'

class KanvasNode(bpy.types.Node):
    """Base Node for Kanvas"""
    bl_idname = 'KanvasNode'
    bl_label = 'Kanvas Node'
    bl_icon = 'IMAGE_DATA'

    @classmethod
    def poll(cls, ntree):
        return ntree.bl_idname == 'KanvasNodeTree'
