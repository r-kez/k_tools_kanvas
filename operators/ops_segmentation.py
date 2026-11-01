"""Explicit user actions for Auto Select: install, download, remove, analyze.

Every action is a normal (non-modal) operator that starts a worker thread. While
a job runs, a short timer redraws the UI and removes itself when the job ends.
"""

import bpy

from .kanvas_context import KanvasTreeOnly
from .ops_mask import _active_image
from ..utils import sam_engine

_REDRAW_INTERVAL = 0.3


def _redraw_everything():
    manager = bpy.context.window_manager
    for window in manager.windows:
        for area in window.screen.areas:
            if area.type in {'PREFERENCES', 'NODE_EDITOR'}:
                area.tag_redraw()


def _redraw_tick():
    _redraw_everything()
    return _REDRAW_INTERVAL if sam_engine.busy() else None


def _watch_jobs():
    if not bpy.app.timers.is_registered(_redraw_tick):
        bpy.app.timers.register(_redraw_tick, first_interval=_REDRAW_INTERVAL)


def _confirm(operator, context, event, title, message, confirm_text):
    try:
        return context.window_manager.invoke_confirm(
            operator, event, title=title, message=message, confirm_text=confirm_text)
    except TypeError:   # older Blender without the keyword arguments
        return context.window_manager.invoke_confirm(operator, event)


class KANVAS_OT_SamInstallEngine(bpy.types.Operator):
    bl_idname = 'kanvas.sam_install_engine'
    bl_label = 'Install Segmentation Engine'
    bl_description = ('Download ONNX Runtime (about 50 MB) with pip into the add-on data '
                     'folder. Nothing is installed into Blender itself')
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        return _confirm(self, context, event, 'Install ONNX Runtime?',
                        'This downloads about 50 MB from PyPI into the add-on data folder.',
                        'Install')

    def execute(self, context):
        if sam_engine.start_install_engine():
            _watch_jobs()
        return {'FINISHED'}


class KANVAS_OT_SamDownloadModel(bpy.types.Operator):
    bl_idname = 'kanvas.sam_download_model'
    bl_label = 'Download Segmentation Model'
    bl_description = ('Download the MobileSAM model (about 45 MB, Apache-2.0) from '
                     'huggingface.co into the add-on data folder')
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        return _confirm(self, context, event, 'Download the segmentation model?',
                        'This downloads about 45 MB from huggingface.co.', 'Download')

    def execute(self, context):
        if sam_engine.start_download_models():
            _watch_jobs()
        return {'FINISHED'}


class KANVAS_OT_SamRemoveFiles(bpy.types.Operator):
    bl_idname = 'kanvas.sam_remove_files'
    bl_label = 'Remove Segmentation Files'
    bl_description = 'Delete the downloaded engine and model from the add-on data folder'
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        return _confirm(self, context, event, 'Remove segmentation files?',
                        'The engine and model will be deleted. Existing masks and colors are kept.',
                        'Remove')

    def execute(self, context):
        sam_engine.remove_files()
        _redraw_everything()
        return {'FINISHED'}


class KANVAS_OT_SamAnalyzeImage(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.sam_analyze_image'
    bl_label = 'Analyze Image'
    bl_description = ('Prepare this image for Auto Select. Runs once per image; '
                     'afterwards each click is nearly instant')
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        item = _active_image(context)
        return (item is not None and sam_engine.snapshot('analyze')['state'] != 'working'
                and sam_engine.ready())

    def execute(self, context):
        item = _active_image(context)
        if item is None:
            return {'CANCELLED'}
        if not sam_engine.start_analyze(item.image_data):
            self.report({'WARNING'}, sam_engine.snapshot('analyze')['message']
                        or 'Analysis is already running')
            return {'CANCELLED'}
        _watch_jobs()
        return {'FINISHED'}
