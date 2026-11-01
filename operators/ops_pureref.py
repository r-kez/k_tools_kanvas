"""Experimental PureRef scene import into the active Kanvas tree."""

from pathlib import Path
from html.parser import HTMLParser
import tempfile
import uuid

import bpy
from bpy_extras.io_utils import ImportHelper

from .kanvas_context import KanvasTreeOnly
from ..properties import suspend_selection_updates
from ..utils.kanvas_data import get_settings, unique_item_name
from ..utils.pureref import PureRefText, read_pureref


class _PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {'br', 'p', 'div'} and self.parts:
            self.parts.append('\n')

    def handle_data(self, data):
        self.parts.append(data)


def _plain_text(content):
    if '<' not in content or '>' not in content:
        return content.strip()
    parser = _PlainText()
    parser.feed(content)
    return '\n'.join(line.strip() for line in ''.join(parser.parts).splitlines()
                     if line.strip())


class KANVAS_OT_ImportPureRef(KanvasTreeOnly, bpy.types.Operator, ImportHelper):
    bl_idname = 'kanvas.import_pureref'
    bl_label = 'Import PureRef Scene'
    bl_description = 'Import embedded images and simple notes from compatible PureRef 1.10/1.11 and 2.x scenes'
    bl_options = {'REGISTER', 'UNDO'}

    filename_ext = '.pur'
    filter_glob: bpy.props.StringProperty(default='*.pur', options={'HIDDEN'})

    def execute(self, context):
        try:
            scene = read_pureref(self.filepath)
        except Exception as exc:
            self.report({'ERROR'}, f'Could not read PureRef scene: {exc}')
            return {'CANCELLED'}
        if not scene.images and not scene.texts:
            self.report({'WARNING'}, 'No supported images or notes found in the PureRef scene')
            return {'CANCELLED'}

        from ..utils.gpu.gpu_common import get_prefs
        from .ops_image import _convert_float_image_to_byte

        settings = get_settings(context)
        tree = context.space_data.edit_tree
        prefs = get_prefs()
        optimize = bool(getattr(prefs, 'use_optimization', True))
        resolution = int(getattr(prefs, 'max_image_resolution', '1080'))
        force_8bit = bool(getattr(prefs, 'force_8bit', True))
        first_index = len(settings.images)
        base_z = max((item.z_index for item in settings.images), default=-1) + 1
        old_active = settings.active_image_index
        old_selection = tuple(item.is_selected for item in settings.images)
        old_batch = settings.batch_loading
        created_images = []
        image_cache = {}
        source_path = str(Path(self.filepath).resolve())

        try:
            settings.batch_loading = True
            with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / 'scratch') as temp_dir:
                with suspend_selection_updates():
                    records = sorted((*scene.images, *scene.texts),
                                     key=lambda record: record.z_index)
                    for record in records:
                        if isinstance(record, PureRefText):
                            content = _plain_text(record.content)
                            if not content:
                                continue
                            title = next(iter(content.splitlines()), 'PureRef Note')[:80]
                            item_name = unique_item_name(settings, title)
                            item = settings.images.add()
                            item.item_id = uuid.uuid4().hex
                            item.item_type = 'TEXT'
                            item.name = item_name
                            item.text_body = content
                            item.text_show_header = False
                            item.text_color = record.color
                            item.text_background = record.background
                            item.text_opacity = record.opacity
                            item.location = record.center
                            item.z_index = base_z + record.z_index
                            continue
                        image = image_cache.get(record.image_id)
                        if image is None:
                            temp_path = Path(temp_dir) / f'{record.image_id}.{record.extension}'
                            temp_path.write_bytes(record.payload)
                            image = bpy.data.images.load(str(temp_path), check_existing=False)
                            created_images.append(image)
                            original_width, original_height = image.size
                            if original_width < 1 or original_height < 1:
                                raise ValueError(f'Image {record.image_id} has no decoded pixels')
                            if optimize and resolution > 0 and max(image.size) > resolution:
                                ratio = resolution / max(image.size)
                                image.scale(max(1, int(image.size[0] * ratio)),
                                            max(1, int(image.size[1] * ratio)))
                            if optimize and force_8bit:
                                image.colorspace_settings.name = 'sRGB'
                                if image.is_float:
                                    created_images.pop()
                                    image = _convert_float_image_to_byte(image)
                                    created_images.append(image)
                            image.name = f'PureRef_{record.image_id}'
                            image.pack()
                            image.filepath = ''
                            image.buffers_free()
                            image['kanvas_pureref_source'] = source_path
                            image['kanvas_pureref_image_id'] = record.image_id
                            image_cache[record.image_id] = image

                        item_name = unique_item_name(settings, record.name)
                        item = settings.images.add()
                        item.item_id = uuid.uuid4().hex
                        item.item_type = 'IMAGE'
                        item.name = item_name
                        item.image_data = image
                        item.location = record.center
                        item.scale_xy = (
                            record.scale[0] * record.source_size[0] / image.size[0],
                            record.scale[1] * record.source_size[1] / image.size[1])
                        item.rotation = record.rotation
                        item.opacity = record.opacity
                        item.z_index = base_z + record.z_index
                        item.is_locked = record.locked
                    for item in settings.images:
                        item.is_selected = False
                    active_index = -1
                    for index in range(first_index, len(settings.images)):
                        item = settings.images[index]
                        if not item.is_locked:
                            item.is_selected = True
                            active_index = index
                    settings.active_image_index = active_index
            tree.use_fake_user = True
        except Exception as exc:
            with suspend_selection_updates():
                while len(settings.images) > first_index:
                    settings.images.remove(len(settings.images) - 1)
                for item, was_selected in zip(settings.images, old_selection):
                    item.is_selected = was_selected
                settings.active_image_index = old_active
            for image in created_images:
                if image.name in bpy.data.images and image.users == 0:
                    bpy.data.images.remove(image)
            self.report({'ERROR'}, f'PureRef import failed: {exc}')
            return {'CANCELLED'}
        finally:
            settings.batch_loading = old_batch

        if context.area:
            context.area.tag_redraw()
        imported_texts = len(settings.images) - first_index - len(scene.images)
        image_word = 'image' if len(scene.images) == 1 else 'images'
        note_word = 'note' if imported_texts == 1 else 'notes'
        if scene.skipped:
            self.report({'WARNING'},
                        f'Imported {len(scene.images)} {image_word} and '
                        f'{imported_texts} {note_word}; '
                        f'{len(scene.skipped)} item(s) or detail(s) could not be converted. '
                        'See the Blender console for details.')
            print('Kanvas PureRef import limitations: ' + '; '.join(scene.skipped))
        else:
            self.report({'INFO'},
                        f'Imported {len(scene.images)} {image_word} and '
                        f'{imported_texts} {note_word} '
                        f'from PureRef {scene.version}')
        return {'FINISHED'}


class KANVAS_FH_PureRef(bpy.types.FileHandler):
    """Route dropped PureRef scenes to the existing Kanvas importer."""

    bl_idname = 'KANVAS_FH_PureRef'
    bl_label = 'Kanvas PureRef Drop Handler'
    bl_file_extensions = '.pur'
    bl_import_operator = 'kanvas.import_pureref'

    @classmethod
    def poll_drop(cls, context):
        space = getattr(context, 'space_data', None)
        region = getattr(context, 'region', None)
        return bool(
            space is not None
            and space.type == 'NODE_EDITOR'
            and region is not None
            and region.type == 'WINDOW'
            and getattr(space, 'edit_tree', None) is not None
            and space.edit_tree.bl_idname == 'KanvasNodeTree'
        )
