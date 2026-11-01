"""Board integrity check: list broken references and repair them on confirmation."""

import bpy

from .kanvas_context import KanvasTreeOnly
from ..utils.board_check import find_problems, fix_problems
from ..utils.kanvas_data import get_settings


class KANVAS_OT_CheckBoard(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.check_board'
    bl_label = 'Check Board'
    bl_description = ('Look for broken references (links to deleted checklists, arrows attached to '
                      'missing items, damaged frames) and offer to repair them. Nothing is deleted')
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        self._problems = find_problems(get_settings(context))
        if not self._problems:
            self.report({'INFO'}, 'The board has no broken references')
            return {'CANCELLED'}
        try:
            return context.window_manager.invoke_props_dialog(
                self, title='Board problems', confirm_text='Repair')
        except TypeError:   # older Blender without title and confirm text
            return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        column = self.layout.column(align=True)
        for problem in getattr(self, '_problems', ()):
            column.label(text=problem.message, icon='ERROR' if not problem.fixable else 'DOT')
        if any(problem.fixable for problem in getattr(self, '_problems', ())):
            column.separator()
            column.label(text='Repair clears the broken references only.')
        if any(not problem.fixable for problem in getattr(self, '_problems', ())):
            column.label(text='Items without an image need Replace Image.')

    def execute(self, context):
        changed = fix_problems(get_settings(context))
        if changed:
            self.report({'INFO'}, f'Repaired {changed} reference(s)')
        else:
            self.report({'INFO'}, 'Nothing could be repaired automatically')
        context.area.tag_redraw()
        return {'FINISHED'} if changed else {'CANCELLED'}
