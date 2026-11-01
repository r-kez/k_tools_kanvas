import bpy
from ..utils.kanvas_data import get_settings, unique_item_name
import os
import uuid
import hashlib
import tempfile
from array import array
from types import SimpleNamespace
from bpy_extras.io_utils import ImportHelper
from .kanvas_context import KanvasTreeOnly
from ..utils.markdown import safe_link
from ..utils.clipboard_image import read_image_clipboard

def _resolve_assets_folder(prefs):
    rel_folder = getattr(prefs, 'assets_folder', '//assets/kanvas') if prefs else '//assets/kanvas'

    if not bpy.data.filepath:
        return None, "Kanvas: .blend file not saved yet. Save the project before adding images with Auto Copy enabled."

    abs_folder = bpy.path.abspath(rel_folder)
    return abs_folder, None


def image_origin(image):
    """Return a remembered URL or the original local path of an image."""
    if image is None:
        return '', ''
    url = image.get('kanvas_source_url', '')
    if url:
        return 'URL', str(url)
    pure_ref = image.get('kanvas_pureref_source', '')
    if pure_ref:
        return 'PUR', str(pure_ref)
    path = image.get('kanvas_source_path', '') or image.filepath
    if path:
        return 'FILE', os.path.abspath(bpy.path.abspath(path))
    return '', ''


def missing_external_items(settings):
    """References whose displayed image file is missing and is not packed."""
    return [item for item in settings.images
            if item.item_type == 'IMAGE' and item.image_data
            and item.image_data.packed_file is None
            and item.image_data.filepath
            and not os.path.isfile(bpy.path.abspath(item.image_data.filepath))]


def _convert_float_image_to_byte(image):
    """Copy decoded pixels to an 8-bit Blender image before packing."""
    width, height = image.size
    if not image.is_float or width < 1 or height < 1:
        return image
    pixels = array('f', [0.0]) * (width * height * 4)
    image.pixels.foreach_get(pixels)
    converted = bpy.data.images.new(
        image.name + '_8bit', width=width, height=height,
        alpha=True, float_buffer=False)
    try:
        converted.colorspace_settings.name = 'sRGB'
        converted.pixels.foreach_set(pixels)
        converted.update()
    except Exception:
        bpy.data.images.remove(converted)
        raise
    bpy.data.images.remove(image)
    return converted


def _pack_embedded_image(image):
    """Pack the current pixels, including any resize, without a source path."""
    path = None
    try:
        with tempfile.NamedTemporaryFile(
                prefix='kanvas_clipboard_packed_', suffix='.png',
                delete=False) as output:
            path = output.name
        image.filepath_raw = path
        image.file_format = 'PNG'
        image.save()
        with open(path, 'rb') as saved:
            payload = saved.read()
        packed = bpy.data.images.load(path, check_existing=False)
        try:
            packed.name = image.name
            packed.colorspace_settings.name = 'sRGB'
            packed.pack(data=payload, data_len=len(payload))
            packed.filepath_raw = ''
        except Exception:
            bpy.data.images.remove(packed)
            raise
        bpy.data.images.remove(image)
        return packed
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError as exc:
                print(f'Kanvas: could not remove temporary packed image: {exc}')

def _find_or_save_webp(temp_img, source_path, abs_folder, target_w, target_h,
                       convert_srgb=False):
    os.makedirs(abs_folder, exist_ok=True)

    fingerprint = hashlib.blake2b(digest_size=16)
    fingerprint.update(f'kanvas-webp-v3|{target_w}x{target_h}|q90|srgb={int(convert_srgb)}|'.encode())
    resolved_source = os.path.realpath(bpy.path.abspath(source_path))
    fingerprint.update(os.path.normcase(resolved_source).encode('utf-8', 'surrogatepass'))
    fingerprint.update(b'\0')
    with open(resolved_source, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            fingerprint.update(chunk)
    stem = os.path.splitext(os.path.basename(source_path))[0][:160]
    base = f"{stem}_{fingerprint.hexdigest()}"
    counter = 0
    while True:
        suffix = f"_{counter:03d}" if counter else ""
        target_path = os.path.join(abs_folder, f"{base}{suffix}.webp")
        if not os.path.exists(target_path):
            break
        try:
            existing = bpy.data.images.load(target_path, check_existing=False)
            try:
                if tuple(existing.size) == (target_w, target_h):
                    return target_path
            finally:
                bpy.data.images.remove(existing)
        except Exception:
            pass
        counter += 1

    try:
        temp_img.scale(target_w, target_h)
        temp_img.filepath_raw = target_path
        temp_img.file_format = 'WEBP'

        if hasattr(temp_img, 'file_format_quality'):
            temp_img.file_format_quality = 90

        temp_img.save()
    except Exception as e:
        print(f"Kanvas: Error during image save: {e}")
        raise e

    if not os.path.exists(target_path):
        raise RuntimeError(f"Kanvas: Failed to create WebP file at {target_path}")

    return target_path


def add_image_to_kanvas(context, filepath, location=None, *, embedded=False):
    settings = get_settings(context)

    space_data = getattr(context, 'space_data', None)
    if space_data and space_data.type == 'NODE_EDITOR' and getattr(space_data, 'edit_tree', None):
        tree = space_data.edit_tree
        if tree.bl_idname == 'KanvasNodeTree' and not tree.use_fake_user:
            tree.use_fake_user = True

    from ..utils.gpu.gpu_common import get_prefs
    prefs = get_prefs()

    max_res_str = getattr(prefs, 'max_image_resolution', '1080') if prefs else '1080'
    force_8bit  = getattr(prefs, 'force_8bit', True) if prefs else True
    use_opt     = getattr(prefs, 'use_optimization', True) if prefs else True
    auto_copy   = (getattr(prefs, 'auto_copy', False) if prefs else False) and not embedded

    if auto_copy:
        _, blend_error = _resolve_assets_folder(prefs)
        if blend_error:
            print(blend_error)
            try:
                bpy.context.workspace.status_text_set(text=blend_error)
            except Exception:
                pass
            return None

    temp_img = bpy.data.images.load(filepath, check_existing=False)

    width, height = temp_img.size[0], temp_img.size[1]
    new_width, new_height = width, height

    if width > 0 and height > 0:
        if use_opt and max_res_str != '0':
            max_res = int(max_res_str)
            longest_edge = max(width, height)
            
            if longest_edge > max_res:
                scale_factor = max_res / longest_edge
                new_width    = max(1, int(width  * scale_factor))
                new_height   = max(1, int(height * scale_factor))

    if use_opt and force_8bit:
        if hasattr(temp_img, 'colorspace_settings'):
            temp_img.colorspace_settings.name = 'sRGB'

    if auto_copy:
        abs_folder, _ = _resolve_assets_folder(prefs)
        try:
            saved_path = _find_or_save_webp(
                temp_img, filepath, abs_folder, new_width, new_height,
                convert_srgb=bool(use_opt and force_8bit))
        except Exception as e:
            print(f"Kanvas: Failed to save WebP - {e}")
            bpy.data.images.remove(temp_img)
            try:
                bpy.context.workspace.status_text_set(text=f"Kanvas: Error saving image: {e}")
            except Exception:
                pass
            return None

        bpy.data.images.remove(temp_img)

        img = bpy.data.images.load(saved_path, check_existing=True)
        img.name = f"Kanvas_{os.path.basename(saved_path)}"

        img["kanvas_source_path"]   = filepath
        img["kanvas_original_size"] = f"{width}x{height}"

    else:
        # Image.copy() reloads the original file dimensions in Blender 5.2, so
        # keep and pack the scaled image datablock itself.
        if (new_width, new_height) != (width, height):
            temp_img.scale(new_width, new_height)
        if use_opt and force_8bit:
            temp_img = _convert_float_image_to_byte(temp_img)
        img = temp_img
        img.name = ("Kanvas_Clipboard" if embedded else
                    f"Kanvas_{os.path.basename(filepath)}")
        if embedded:
            img = _pack_embedded_image(img)
        else:
            img.pack()

    if embedded:
        img.filepath_raw = ''
        img['kanvas_clipboard'] = True
    else:
        img['kanvas_source_path'] = os.path.abspath(bpy.path.abspath(filepath))

    if location is None:
        region = getattr(context, 'region', None)
        if region and getattr(region, 'view2d', None):
            v2d      = region.view2d
            location = v2d.region_to_view(region.width / 2, region.height / 2)
        else:
            location = (0, 0)

    item_name = unique_item_name(settings, img.name)
    new_item            = settings.images.add()
    new_item.item_id     = uuid.uuid4().hex
    new_item.name       = item_name
    new_item.image_data = img
    new_item.location   = (location[0], location[1])

    max_z           = max([i.z_index for i in settings.images] + [-1])
    new_item.z_index = max_z + 1

    settings.active_image_index = len(settings.images) - 1

    # Check if added inside an existing frame (when not in batch mode)
    if not getattr(settings, 'batch_loading', False):
        from ..utils.gpu import find_frame_at_location, update_frame_bounds, sync_kanvas_frames
        target_frame = find_frame_at_location(settings, location)
        if target_frame:
            new_item.parent_frame = target_frame.frame_node_name
            space_data = getattr(context, 'space_data', None)
            tree = getattr(space_data, 'edit_tree', None) if space_data else None
            update_frame_bounds(tree, settings, target_frame.frame_node_name)
            sync_kanvas_frames(tree, settings)

    return new_item


class _KanvasBatchImport:
    """Import one image per timer event and finish as one undoable operator."""

    def _start_batch(self, context, paths, location):
        from ..utils.gpu.gpu_common import get_prefs
        prefs = get_prefs()
        if getattr(prefs, 'auto_copy', False) and not bpy.data.filepath:
            self.report({'ERROR'}, "Save the .blend file before adding images with Auto Copy enabled.")
            return {'CANCELLED'}

        self._batch_scene = context.scene
        self._batch_tree = context.space_data.edit_tree
        self._batch_settings = get_settings(context)
        self._batch_area = context.area
        self._batch_paths = paths
        self._batch_index = 0
        self._batch_items = []
        self._batch_failures = 0
        self._batch_location = location
        settings = get_settings(context)
        settings.batch_loading = True
        self._batch_previous_selection = [i for i, item in enumerate(settings.images) if item.is_selected]
        self._batch_previous_active = settings.active_image_index
        self._batch_timer = context.window_manager.event_timer_add(0.01, window=context.window)
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def _finish_batch(self, context):
        context.window_manager.event_timer_remove(self._batch_timer)
        self._batch_timer = None
        try:
            bpy.context.workspace.status_text_set(None)
        except Exception:
            pass

        settings = self._batch_settings
        settings.batch_loading = False
        if not self._batch_items:
            settings.active_image_index = self._batch_previous_active
            for i, item in enumerate(settings.images):
                item.is_selected = i in self._batch_previous_selection
            self.report({'ERROR'}, "No images could be loaded")
            return {'CANCELLED'}

        # active_image_index's update callback clears previous selections while
        # importing, so select the completed batch together only at the end.
        for item in settings.images:
            item.is_selected = False
        # CollectionProperty.move() can relocate item RNA pointers while
        # frames are synchronized. Image datablocks retain their identity.
        imported_image_ids = set(self._batch_items)
        imported = [item for item in settings.images
                    if item.image_data and item.image_data.as_pointer() in imported_image_ids]
        if imported:
            for i, item in enumerate(settings.images):
                if item.image_data == imported[-1].image_data:
                    settings.active_image_index = i
                    break
        for item in imported:
            item.is_selected = True
        if len(imported) > 1:
            pack_image_items(imported, gap=40)

        # Auto-parent and auto-resize frames
        space_data = getattr(context, 'space_data', None)
        tree = getattr(space_data, 'edit_tree', None) if space_data else None
        from ..utils.gpu import find_frame_at_location, update_frame_bounds, sync_kanvas_frames, auto_parent_images_to_frames
        target_frame = find_frame_at_location(settings, self._batch_location) if self._batch_location else None
        if target_frame:
            for item in imported:
                item.parent_frame = target_frame.frame_node_name
            update_frame_bounds(tree, settings, target_frame.frame_node_name)
            sync_kanvas_frames(tree, settings)
        else:
            affected = auto_parent_images_to_frames(tree, settings, targets=imported)
            for fname in affected:
                update_frame_bounds(tree, settings, fname)
            if affected:
                sync_kanvas_frames(tree, settings)

        if self._batch_area:
            self._batch_area.tag_redraw()
        self.report({'INFO'}, f"Loaded and packed {len(imported)} image(s)" if len(imported) > 1
                    else f"Loaded {len(imported)} image")
        if self._batch_failures:
            self.report({'WARNING'}, f"Failed to load {self._batch_failures} image(s)")
        return {'FINISHED'}

    def modal(self, context, event):
        if event.type == 'ESC' and event.value == 'PRESS':
            self._batch_index = len(self._batch_paths)
            return self._finish_batch(context)
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}
        # Event.timer não está exposto em todas as versões do Blender (5.3).
        # Quando disponível, ignoramos timers de outros operadores; caso
        # contrário, qualquer TIMER pode avançar um item do lote.
        event_timer = getattr(event, 'timer', None)
        if event_timer is not None and event_timer != self._batch_timer:
            return {'PASS_THROUGH'}
        if self._batch_index >= len(self._batch_paths):
            return self._finish_batch(context)

        path = self._batch_paths[self._batch_index]
        self._batch_index += 1
        try:
            import_context = SimpleNamespace(scene=self._batch_scene, space_data=None,
                                             kanvas_tree=self._batch_tree, region=None)
            item = add_image_to_kanvas(import_context, path, location=self._batch_location)
            if item is None:
                self._batch_failures += 1
            else:
                self._batch_items.append(item.image_data.as_pointer())
        except Exception as exc:
            self._batch_failures += 1
            print(f"Kanvas: Failed to load {path}: {exc}")

        try:
            bpy.context.workspace.status_text_set(
                text=f"Kanvas: Loading {self._batch_index} of {len(self._batch_paths)} images..."
            )
        except Exception:
            pass
        if self._batch_area:
            self._batch_area.tag_redraw()
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        if getattr(self, '_batch_scene', None) is not None:
            self._batch_settings.batch_loading = False
        if getattr(self, '_batch_timer', None) is not None:
            context.window_manager.event_timer_remove(self._batch_timer)
            self._batch_timer = None


class KANVAS_FH_ImageHandler(bpy.types.FileHandler):
    bl_idname        = "KANVAS_FH_ImageHandler"
    bl_label         = "Kanvas Image Drop Handler"
    bl_file_extensions = ".png;.jpg;.jpeg;.tga;.tif;.tiff;.webp;.exr"
    bl_import_operator = "kanvas.add_image"

    @classmethod
    def poll_drop(cls, context):
        space = getattr(context, 'space_data', None)
        return (
            space is not None
            and space.type == 'NODE_EDITOR'
            and getattr(context, 'region', None) is not None
            and context.region.type == 'WINDOW'
            and getattr(space, 'edit_tree', None) is not None
            and space.edit_tree.bl_idname == 'KanvasNodeTree'
        )


# Blender's built-in image-node FileHandler also polls for every Node Editor.
# With both handlers available, a drop opens a choice menu. Keep the native
# handler for other node trees and let Kanvas be the sole handler in its tree.
_native_image_drop_class = None
_native_image_drop_poll = None
_filtered_image_drop_poll = None


def register():
    global _native_image_drop_class, _native_image_drop_poll, _filtered_image_drop_poll
    from bl_operators.node import NODE_FH_image_node

    if _filtered_image_drop_poll is not None:
        return
    current = NODE_FH_image_node.__dict__.get('poll_drop')
    # Recover cleanly if Python reloaded this module before its unregister()
    # ran; do not stack wrappers around the Blender handler.
    original = getattr(getattr(current, '__func__', None), '_kanvas_original', current)
    if not isinstance(original, classmethod):
        return

    def poll_without_kanvas(cls, context):
        if KANVAS_FH_ImageHandler.poll_drop(context):
            return False
        return original.__func__(cls, context)

    poll_without_kanvas._kanvas_original = original
    filtered = classmethod(poll_without_kanvas)
    NODE_FH_image_node.poll_drop = filtered
    _native_image_drop_class = NODE_FH_image_node
    _native_image_drop_poll = original
    _filtered_image_drop_poll = filtered


def unregister():
    global _native_image_drop_class, _native_image_drop_poll, _filtered_image_drop_poll
    if (_native_image_drop_class is not None
            and _native_image_drop_class.__dict__.get('poll_drop') is _filtered_image_drop_poll):
        _native_image_drop_class.poll_drop = _native_image_drop_poll
    _native_image_drop_class = None
    _native_image_drop_poll = None
    _filtered_image_drop_poll = None

class KANVAS_OT_AddImage(KanvasTreeOnly, _KanvasBatchImport, bpy.types.Operator):
    """Import single or multiple files passed by Blender's FileHandler."""
    bl_idname  = "kanvas.add_image"
    bl_label   = "Add Reference"
    bl_description = 'Add dropped image files to the current Kanvas board'
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    # Modo arquivo único (drop de 1 imagem)
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")  # type: ignore

    # Modo multi-arquivo (drop de N imagens — Blender preenche directory+files)
    directory: bpy.props.StringProperty(subtype="DIR_PATH")  # type: ignore
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement)  # type: ignore

    def execute(self, context):
        # Determina lista de caminhos a carregar
        if self.files:
            # Multi-file drop: monta caminhos a partir de directory + files
            paths_to_load = [
                os.path.join(self.directory, f.name)
                for f in self.files if f.name
            ]
            # Fallback: se files existiu mas veio vazio, usa filepath
            if not paths_to_load and self.filepath:
                paths_to_load = [self.filepath]
        else:
            paths_to_load = [self.filepath] if self.filepath else []

        if not paths_to_load:
            return {'CANCELLED'}

        # Calcula posição central para drop
        region = getattr(context, 'region', None)
        location = (0, 0)
        if region and getattr(region, 'view2d', None):
            location = region.view2d.region_to_view(region.width / 2, region.height / 2)

        if len(paths_to_load) == 1:
            # Caminho rápido: carrega direto, sem timer
            result = add_image_to_kanvas(context, paths_to_load[0], location=location)
            if result is None:
                self.report({'ERROR'}, "Save the .blend file before adding images with Auto Copy enabled.")
                return {'CANCELLED'}
            return {'FINISHED'}

        return self._start_batch(context, paths_to_load, location)

class KANVAS_OT_AddImageBrowser(KanvasTreeOnly, bpy.types.Operator, ImportHelper):
    """Import one local image as a Kanvas reference."""
    bl_idname  = "kanvas.add_image_browser"
    bl_label   = "Add Reference"
    bl_description = 'Choose one image file to add to the current Kanvas board'
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty( # type: ignore
        subtype="FILE_PATH", options={'SKIP_SAVE'})
    filter_glob: bpy.props.StringProperty( # type: ignore
        default="*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.webp",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context):
        if not self.filepath:
            return {'CANCELLED'}
        result = add_image_to_kanvas(context, self.filepath)
        if result is None:
            self.report({'ERROR'}, "Save the .blend file before adding images with Auto Copy enabled.")
            return {'CANCELLED'}
        return {'FINISHED'}

class KANVAS_OT_AddMultipleImages(KanvasTreeOnly, _KanvasBatchImport, bpy.types.Operator, ImportHelper):
    """Import several local images and arrange the new references."""
    bl_idname  = "kanvas.add_multiple_images"
    bl_label   = "Add Multiple References"
    bl_description = 'Choose several image files and arrange them on the current board'
    bl_options = {'REGISTER', 'UNDO'}

    directory: bpy.props.StringProperty( # type: ignore
        subtype='DIR_PATH')
    files: bpy.props.CollectionProperty( # type: ignore
        type=bpy.types.OperatorFileListElement)
    filter_glob: bpy.props.StringProperty( # type: ignore
        default="*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.webp",
        options={'HIDDEN'},
        maxlen=255,
    )

    def execute(self, context):
        paths_to_load = [os.path.join(self.directory, f.name) for f in self.files]
        if not paths_to_load:
            return {'CANCELLED'}

        region   = getattr(context, 'region', None)
        location = (0, 0)
        if region and getattr(region, 'view2d', None):
            location = region.view2d.region_to_view(region.width / 2, region.height / 2)

        if len(paths_to_load) == 1:
            result = add_image_to_kanvas(context, paths_to_load[0], location=location)
            return {'FINISHED'} if result else {'CANCELLED'}
        return self._start_batch(context, paths_to_load, location)


class KANVAS_OT_PasteImage(KanvasTreeOnly, _KanvasBatchImport, bpy.types.Operator):
    """Paste copied image files or pixels into the active Kanvas board."""

    bl_idname = 'kanvas.paste_image'
    bl_label = 'Paste Image'
    bl_description = 'Paste local image files or copied image pixels into Kanvas'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        region = getattr(context, 'region', None)
        if region is None or region.type != 'WINDOW':
            return False
        settings = get_settings(context)
        return (settings is not None and not settings.batch_loading
                and not any(item.mask_editing or item.markup_editing
                            for item in settings.images))

    def _paste(self, context, location):
        try:
            contents = read_image_clipboard(context.window_manager.clipboard)
        except (OSError, RuntimeError) as exc:
            self.report({'WARNING'}, f'Could not read clipboard: {exc}')
            return {'CANCELLED'}
        if contents.paths:
            if len(contents.paths) > 1:
                return self._start_batch(context, list(contents.paths), location)
            try:
                item = add_image_to_kanvas(context, contents.paths[0],
                                           location=location)
            except (OSError, RuntimeError, ValueError) as exc:
                self.report({'ERROR'}, f'Could not load image: {exc}')
                return {'CANCELLED'}
            if item is None:
                self.report({'ERROR'}, 'Save the .blend file before importing with Auto Copy enabled')
                return {'CANCELLED'}
            context.area.tag_redraw()
            return {'FINISHED'}
        if contents.pixels:
            path = None
            try:
                with tempfile.NamedTemporaryFile(
                        prefix='kanvas_clipboard_', suffix=contents.extension,
                        delete=False) as output:
                    path = output.name
                    output.write(contents.pixels)
                item = add_image_to_kanvas(context, path, location=location,
                                           embedded=True)
            except (OSError, RuntimeError, ValueError) as exc:
                self.report({'ERROR'}, f'Could not paste image pixels: {exc}')
                return {'CANCELLED'}
            finally:
                if path:
                    try:
                        os.unlink(path)
                    except OSError as exc:
                        print(f'Kanvas: could not remove temporary clipboard file: {exc}')
            if item is None:
                return {'CANCELLED'}
            context.area.tag_redraw()
            return {'FINISHED'}
        self.report({'INFO'}, 'Clipboard has no supported local image')
        return {'CANCELLED'}

    def execute(self, context):
        region = context.region
        location = region.view2d.region_to_view(region.width / 2,
                                                region.height / 2)
        return self._paste(context, location)

    def invoke(self, context, event):
        region = context.region
        x, y = event.mouse_x - region.x, event.mouse_y - region.y
        if not 0 <= x < region.width or not 0 <= y < region.height:
            x, y = region.width / 2, region.height / 2
        location = region.view2d.region_to_view(x, y)
        return self._paste(context, location)


class KANVAS_OT_RemoveImage(KanvasTreeOnly, bpy.types.Operator):
    """Remove the selected unlocked Kanvas items from this board."""
    bl_idname  = "kanvas.remove_image"
    bl_label   = "Remove Kanvas Item?"
    bl_description = 'Remove selected unlocked items from the current board'
    bl_options = {'REGISTER', 'UNDO'}

    index: bpy.props.IntProperty(default=-1) # type: ignore

    def execute(self, context):
        settings = get_settings(context)
        from ..utils.gpu.gpu_image import _texture_cache

        removed_names = []
        arrow_indices = ([i for i, arrow in enumerate(settings.arrows)
                          if arrow.is_selected and not arrow.is_locked]
                         if self.index == -1 else [])

        if self.index == -1:
            indices_to_remove = [i for i, img in enumerate(settings.images)
                                 if img.is_selected and not img.is_locked]
            if not indices_to_remove and 0 <= settings.active_image_index < len(settings.images):
                active = settings.images[settings.active_image_index]
                if not active.is_locked:
                    indices_to_remove = [settings.active_image_index]
        else:
            indices_to_remove = ([self.index] if 0 <= self.index < len(settings.images)
                                 and not settings.images[self.index].is_locked else [])

        if not indices_to_remove and not arrow_indices:
            return {'CANCELLED'}

        indices_to_remove.sort(reverse=True)

        space_data = getattr(context, 'space_data', None)
        tree = getattr(space_data, 'edit_tree', None) if space_data else None

        parent_frames_to_update = set()
        for idx in indices_to_remove:
            img_item = settings.images[idx]
            if img_item.parent_frame:
                parent_frames_to_update.add(img_item.parent_frame)

        for idx in indices_to_remove:
            img_item = settings.images[idx]
            from ..utils.arrow_geometry import detach_item_anchors
            detach_item_anchors(settings, img_item.item_id)
            is_frame = (getattr(img_item, "item_type", 'IMAGE') == 'FRAME')

            if is_frame:
                frame_name = img_item.frame_node_name
                # Desvincula itens filhos que pertenciam a este frame
                for child in settings.images:
                    if child.parent_frame == frame_name:
                        child.parent_frame = ""

                # Remove nó nativo correspondente se houver na árvore
                if tree and frame_name in tree.nodes:
                    try:
                        tree.nodes.remove(tree.nodes[frame_name])
                    except Exception:
                        pass

                name = img_item.name
                removed_names.append(name)
                settings.images.remove(idx)
            else:
                image = img_item.image_data

                if image:
                    key = (image.name, id(image))
                    if key in _texture_cache:
                        del _texture_cache[key]

                name = img_item.name
                removed_names.append(name)
                settings.images.remove(idx)

                if image and image.users <= 1:
                    try:
                        bpy.data.images.remove(image)
                    except Exception as e:
                        print(f"Kanvas: Could not purge image data {name}: {e}")

        for idx in reversed(arrow_indices):
            removed_names.append(settings.arrows[idx].name)
            settings.arrows.remove(idx)

        from ..properties import suspend_selection_updates
        with suspend_selection_updates():
            settings.active_image_index = next(
                (i for i, item in enumerate(settings.images) if item.is_selected), -1)
            settings.active_arrow_index = next(
                (i for i, arrow in enumerate(settings.arrows) if arrow.is_selected), -1)

        if tree:
            from ..utils.gpu import update_frame_bounds, sync_kanvas_frames
            for fname in parent_frames_to_update:
                update_frame_bounds(tree, settings, fname)
            sync_kanvas_frames(tree, settings)

        if len(removed_names) > 1:
            self.report({'INFO'}, f"Removed {len(removed_names)} item(s)")
        elif len(removed_names) == 1:
            self.report({'INFO'}, f"Removed '{removed_names[0]}'")

        if context.area:
            context.area.tag_redraw()

        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

class KANVAS_OT_DuplicateImage(KanvasTreeOnly, bpy.types.Operator):
    """Duplicate the active image or text card without copying its source file."""
    bl_idname  = "kanvas.duplicate_image"
    bl_label   = "Duplicate Kanvas Item"
    bl_description = 'Duplicate selected unlocked items on the current board'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = get_settings(context)
        if not (0 <= settings.active_image_index < len(settings.images)):
            selected = [idx for idx, i in enumerate(settings.images)
                        if i.is_selected and not i.is_locked and i.item_type != 'FRAME']
            if selected:
                settings.active_image_index = selected[0]
            else:
                return {'CANCELLED'}

        source  = settings.images[settings.active_image_index]
        source_idx = settings.active_image_index
        if source.item_type == 'FRAME' or source.is_locked:
            return {'CANCELLED'}

        copy_name = unique_item_name(settings, f"{source.name}_copy")

        new_img = settings.images.add()
        new_img.item_id = uuid.uuid4().hex

        new_img.item_type = source.item_type
        new_img.name         = copy_name
        new_img.image_data   = source.image_data
        new_img.location     = tuple(source.location)
        new_img.scale_master = source.scale_master
        new_img.scale_xy     = tuple(source.scale_xy)
        new_img.shear_xy     = tuple(source.shear_xy)
        new_img.rotation     = source.rotation
        new_img.opacity      = source.opacity
        new_img.color_tint   = tuple(source.color_tint)
        new_img.parent_frame = source.parent_frame
        new_img.use_color_correction = source.use_color_correction
        new_img.show_in_editor = source.show_in_editor
        if source.item_type == 'IMAGE':
            new_img.mask_enabled = source.mask_enabled
            new_img.mask_brush_size = source.mask_brush_size
            new_img.mask_erase = source.mask_erase
            new_img.mask_tool = source.mask_tool
            new_img.mask_next_sequence = source.mask_next_sequence
            for dab in source.mask_dabs:
                copied_dab = new_img.mask_dabs.add()
                copied_dab.uv = tuple(dab.uv)
                copied_dab.radius_uv = tuple(dab.radius_uv)
                copied_dab.uv_axis_x = tuple(dab.uv_axis_x)
                copied_dab.uv_axis_y = tuple(dab.uv_axis_y)
                copied_dab.erase = dab.erase
                copied_dab.sequence = dab.sequence
            for polygon in source.mask_polygons:
                copied_polygon = new_img.mask_polygons.add()
                copied_polygon.erase = polygon.erase
                copied_polygon.sequence = polygon.sequence
                for vertex in polygon.vertices:
                    copied_vertex = copied_polygon.vertices.add()
                    copied_vertex.uv = tuple(vertex.uv)
            new_img.markup_visible = source.markup_visible
            new_img.markup_tool = source.markup_tool
            new_img.markup_brush_size = source.markup_brush_size
            new_img.markup_erase = source.markup_erase
            new_img.markup_active_index = source.markup_active_index
            for link in source.checklist_associations:
                new_img.checklist_associations.add().card_id = link.card_id
            for region in source.markup_regions:
                copied_region = new_img.markup_regions.add()
                copied_region.region_id = region.region_id
                copied_region.checklist_card_id = region.checklist_card_id
                copied_region.checklist_line_id = region.checklist_line_id
                copied_region.checklist_origin_card_id = region.checklist_origin_card_id
                copied_region.checklist_origin_line_id = region.checklist_origin_line_id
                copied_region.name = region.name
                copied_region.color = tuple(region.color)
                copied_region.opacity = region.opacity
                copied_region.visible = region.visible
                copied_region.next_sequence = region.next_sequence
                for dab in region.dabs:
                    copied_dab = copied_region.dabs.add()
                    copied_dab.uv = tuple(dab.uv)
                    copied_dab.radius_uv = tuple(dab.radius_uv)
                    copied_dab.uv_axis_x = tuple(dab.uv_axis_x)
                    copied_dab.uv_axis_y = tuple(dab.uv_axis_y)
                    copied_dab.erase = dab.erase
                    copied_dab.sequence = dab.sequence
                for polygon in region.polygons:
                    copied_polygon = copied_region.polygons.add()
                    copied_polygon.erase = polygon.erase
                    copied_polygon.sequence = polygon.sequence
                    for vertex in polygon.vertices:
                        copied_vertex = copied_polygon.vertices.add()
                        copied_vertex.uv = tuple(vertex.uv)
        if source.item_type == 'TEXT':
            new_img.text_checklist = source.text_checklist
            new_img.text_show_progress = source.text_show_progress
            new_img.text_markdown = source.text_markdown
            new_img.text_scroll = source.text_scroll
            new_img.text_header = source.text_header
            new_img.text_show_header = source.text_show_header
            new_img.text_width = source.text_width
            new_img.text_height = source.text_height
            new_img.text_scale = source.text_scale
            new_img.text_font_size = source.text_font_size
            new_img.text_color = tuple(source.text_color)
            new_img.text_background = tuple(source.text_background)
            new_img.text_opacity = source.text_opacity
            for line in source.text_lines:
                copied = new_img.text_lines.add()
                copied.line_id = uuid.uuid4().hex
                copied.value = line.value
                copied.done = line.done
                copied.show_color_links = line.show_color_links
                copied.color = tuple(line.color)

        max_z            = max([img.z_index for img in settings.images] + [-1])
        new_img.z_index  = max_z + 1

        if new_img.parent_frame:
            space_data = getattr(context, 'space_data', None)
            tree = getattr(space_data, 'edit_tree', None) if space_data else None
            from ..utils.gpu import update_frame_bounds, sync_kanvas_frames
            update_frame_bounds(tree, settings, new_img.parent_frame)
            sync_kanvas_frames(tree, settings)
        else:
            current_idx = len(settings.images) - 1
            target_idx = source_idx + 1
            if current_idx != target_idx:
                settings.images.move(current_idx, target_idx)

        dup_idx = next((i for i, item in enumerate(settings.images) if item.name == copy_name), -1)
        if dup_idx != -1:
            settings.active_image_index = dup_idx
            for idx, item in enumerate(settings.images):
                item.is_selected = (idx == dup_idx)

        if getattr(context, 'area', None):
            context.area.tag_redraw()

        self.report({'INFO'}, f"Duplicated {source.name}")
        return {'FINISHED'}

class KANVAS_OT_RefreshImage(KanvasTreeOnly, bpy.types.Operator):
    bl_idname  = "kanvas.refresh_image"
    bl_label   = "Reload Image Source"
    bl_description = "Reload the original image file using the current import settings, keeping this reference's layout"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        index = settings.active_image_index
        return (0 <= index < len(settings.images)
                and settings.images[index].item_type == 'IMAGE'
                and settings.images[index].image_data is not None)

    def execute(self, context):
        settings = get_settings(context)
        from ..utils.gpu import ensure_item_ids, get_item_by_id
        from ..properties import suspend_selection_updates
        from ..utils.gpu.gpu_image import invalidate_image_texture

        ensure_item_ids(settings)
        item = settings.images[settings.active_image_index]
        replacement = getattr(self, 'filepath', '')
        kind, source = (('FILE', os.path.abspath(bpy.path.abspath(replacement)))
                        if replacement else image_origin(item.image_data))
        if kind != 'FILE' or not os.path.isfile(source):
            self.report({'WARNING'}, "The selected image file is unavailable")
            return {'CANCELLED'}
        if settings.batch_loading:
            self.report({'WARNING'}, "Wait for the current import to finish")
            return {'CANCELLED'}

        item_id = item.item_id
        item_label = item.name
        original_image = item.image_data
        old_size = tuple(original_image.size)
        old_scale = tuple(item.scale_xy)
        selected_ids = {entry.item_id for entry in settings.images if entry.is_selected}
        active_arrow = settings.active_arrow_index
        new_id = None
        successful = False
        with suspend_selection_updates():
            settings.batch_loading = True
            try:
                new_item = add_image_to_kanvas(context, source, location=tuple(item.location))
                new_id = new_item.item_id if new_item is not None else None
                if new_item is None or new_item.image_data is None:
                    self.report({'ERROR'}, "Could not reload the image source")
                    return {'CANCELLED'}
                new_image = new_item.image_data
                new_size = tuple(new_image.size)
                if min(new_size) <= 0:
                    self.report({'ERROR'}, "The image source has no pixels")
                    return {'CANCELLED'}
                item = get_item_by_id(settings, item_id)
                item.image_data = new_image
                item.scale_xy = (
                    old_scale[0] * old_size[0] / new_size[0],
                    old_scale[1] * old_size[1] / new_size[1],
                )
                new_index = next(i for i, entry in enumerate(settings.images)
                                 if entry.item_id == new_id)
                settings.images.remove(new_index)
                for entry in settings.images:
                    entry.is_selected = entry.item_id in selected_ids
                settings.active_image_index = next(
                    i for i, entry in enumerate(settings.images) if entry.item_id == item_id)
                settings.active_arrow_index = active_arrow
                successful = True
            finally:
                if not successful:
                    if new_id:
                        for index, entry in enumerate(settings.images):
                            if entry.item_id == new_id:
                                settings.images.remove(index)
                                break
                    for entry in settings.images:
                        entry.is_selected = entry.item_id in selected_ids
                    settings.active_image_index = next(
                        (i for i, entry in enumerate(settings.images)
                         if entry.item_id == item_id), -1)
                    settings.active_arrow_index = active_arrow
                settings.batch_loading = False

        invalidate_image_texture(original_image)
        context.area.tag_redraw()
        verb = 'Replaced' if replacement else 'Reloaded'
        self.report({'INFO'}, f"{verb} {item_label}")
        return {'FINISHED'}


class KANVAS_OT_ReplaceImage(KanvasTreeOnly, bpy.types.Operator, ImportHelper):
    bl_idname = 'kanvas.replace_image'
    bl_label = 'Replace Image'
    bl_description = 'Choose another image file for this reference while keeping its position, size, and appearance'
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: bpy.props.StringProperty(  # type: ignore
        default='*.png;*.jpg;*.jpeg;*.tga;*.tif;*.tiff;*.webp;*.exr;*.bmp',
        options={'HIDDEN'},
    )

    @classmethod
    def poll(cls, context):
        return KANVAS_OT_RefreshImage.poll(context)

    def execute(self, context):
        return KANVAS_OT_RefreshImage.execute(self, context)


class KANVAS_OT_ClearImageGPUCache(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.clear_image_gpu_cache'
    bl_label = 'Clear Image GPU Cache'
    bl_description = 'Discard this image\'s GPU texture so it is rebuilt on the next draw; the source file is unchanged'
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return KANVAS_OT_RefreshImage.poll(context)

    def execute(self, context):
        from ..utils.gpu.gpu_image import invalidate_image_texture
        settings = get_settings(context)
        item = settings.images[settings.active_image_index]
        invalidate_image_texture(item.image_data)
        context.area.tag_redraw()
        return {'FINISHED'}


class KANVAS_OT_RelinkMissingImages(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.relink_missing_images'
    bl_label = 'Relink Missing Images'
    bl_description = 'Find missing external image files by name in a chosen folder; packed images are left alone'
    bl_options = {'REGISTER', 'UNDO'}

    directory: bpy.props.StringProperty(  # type: ignore
        name='Folder', subtype='DIR_PATH', options={'SKIP_SAVE'})
    filepath: bpy.props.StringProperty(options={'HIDDEN', 'SKIP_SAVE'})  # type: ignore

    @classmethod
    def poll(cls, context):
        return (KanvasTreeOnly.poll(context)
                and bool(missing_external_items(get_settings(context))))

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        self.layout.prop(self, 'directory')

    def execute(self, context):
        folder = os.path.abspath(bpy.path.abspath(self.directory))
        if not os.path.isdir(folder):
            self.report({'ERROR'}, 'Choose an existing folder')
            return {'CANCELLED'}
        files = {entry.name.casefold(): entry.path for entry in os.scandir(folder)
                 if entry.is_file()}
        settings = get_settings(context)
        from ..utils.gpu import ensure_item_ids
        from ..properties import suspend_selection_updates
        ensure_item_ids(settings)
        missing_ids = [item.item_id for item in missing_external_items(settings)]
        active_id = (settings.images[settings.active_image_index].item_id
                     if 0 <= settings.active_image_index < len(settings.images) else '')
        restored = 0
        for item_id in missing_ids:
            index = next((i for i, item in enumerate(settings.images)
                          if item.item_id == item_id), -1)
            if index < 0:
                continue
            item = settings.images[index]
            _, origin = image_origin(item.image_data)
            names = (os.path.basename(origin),
                     os.path.basename(bpy.path.abspath(item.image_data.filepath)))
            candidate = next((files[name.casefold()] for name in names
                              if name.casefold() in files), None)
            if not candidate:
                continue
            with suspend_selection_updates():
                settings.active_image_index = index
            self.filepath = candidate
            if KANVAS_OT_RefreshImage.execute(self, context) == {'FINISHED'}:
                restored += 1
        self.filepath = ''
        with suspend_selection_updates():
            settings.active_image_index = next(
                (i for i, item in enumerate(settings.images)
                 if item.item_id == active_id), -1)
        if not restored:
            self.report({'WARNING'}, 'No matching image files found in the folder')
            return {'CANCELLED'}
        self.report({'INFO'}, f'Relinked {restored} image(s)')
        return {'FINISHED'}


class KANVAS_OT_OpenImageSource(KanvasTreeOnly, bpy.types.Operator):
    bl_idname = 'kanvas.open_image_source'
    bl_label = 'Open Image Source'
    bl_description = 'Open the original file or URL for the active image'
    bl_options = {'REGISTER'}

    @classmethod
    def description(cls, context, properties):
        settings = get_settings(context)
        if settings and 0 <= settings.active_image_index < len(settings.images):
            return image_origin(settings.images[settings.active_image_index].image_data)[1]
        return cls.bl_description

    @classmethod
    def poll(cls, context):
        if not KanvasTreeOnly.poll(context):
            return False
        settings = get_settings(context)
        if not 0 <= settings.active_image_index < len(settings.images):
            return False
        item = settings.images[settings.active_image_index]
        kind, origin = image_origin(item.image_data)
        return item.item_type == 'IMAGE' and kind in {'FILE', 'URL'} and bool(origin)

    def execute(self, context):
        settings = get_settings(context)
        item = settings.images[settings.active_image_index]
        kind, origin = image_origin(item.image_data)
        if kind == 'FILE':
            if not os.path.isfile(origin):
                self.report({'WARNING'}, f'Source file is missing: {origin}')
                return {'CANCELLED'}
            # Source paths can come from .blend metadata. Never pass an
            # executable or arbitrary document to the OS file association.
            if os.path.splitext(origin)[1].lower() not in bpy.path.extensions_image:
                self.report({'WARNING'}, 'The source is not a supported image file')
                return {'CANCELLED'}
            bpy.ops.wm.path_open(filepath=origin)
        elif kind == 'URL':
            if not safe_link(origin):
                self.report({'WARNING'}, 'Only HTTP and HTTPS source links can be opened')
                return {'CANCELLED'}
            bpy.ops.wm.url_open(url=origin)
        else:
            return {'CANCELLED'}
        return {'FINISHED'}

def average_image_sizes(items):
    """Match displayed longest edges using only uniform scale."""
    valid = []
    for item in items:
        if not item.image_data:
            continue
        width, height = item.image_data.size
        longest = max(abs(width * item.scale_xy[0] * item.scale_master),
                      abs(height * item.scale_xy[1] * item.scale_master))
        if longest > 0:
            valid.append((item, longest))
    if len(valid) < 2:
        return 0

    target = sum(longest for _, longest in valid) / len(valid)
    for item, longest in valid:
        item.scale_master *= target / longest
    return len(valid)


def pack_image_items(items, gap=40, average_size=False):
    """Arrange the supplied items without relying on current UI selection."""
    from ..utils.gpu.gpu_common import get_collective_bounding_box

    if average_size:
        average_image_sizes(items)

    footprints = []
    data_list = []
    for item in items:
        if not item.image_data:
            continue
        width, height = item.image_data.size
        if width <= 0 or height <= 0:
            continue
        data = (item.location, item.scale_xy, item.scale_master,
                item.shear_xy, item.rotation, width, height)
        bounds = get_collective_bounding_box([data])
        if bounds:
            footprints.append((item, bounds[2] - bounds[0], bounds[3] - bounds[1]))
            data_list.append(data)
    if not footprints:
        return 0

    bounds = get_collective_bounding_box(data_list)
    start_x, start_y = bounds[0], bounds[3]
    footprints.sort(key=lambda entry: entry[2], reverse=True)
    total_area = sum((width + gap) * (height + gap) for _, width, height in footprints)
    target_width = max(max(width for _, width, _ in footprints), total_area ** 0.5 * 1.15)
    curr_x, curr_y, row_max_h = start_x, start_y, 0

    for item, width, height in footprints:
        if curr_x + width > start_x + target_width and curr_x > start_x:
            curr_x = start_x
            curr_y -= row_max_h + gap
            row_max_h = 0
        # The AABB of a centered rectangle remains centered after rotation or
        # shear, so these positions preserve both transforms and the gap.
        item.location = (curr_x + width / 2, curr_y - height / 2)
        curr_x += width + gap
        row_max_h = max(row_max_h, height)
    return len(footprints)


class KANVAS_OT_AverageImageSize(KanvasTreeOnly, bpy.types.Operator):
    """Match the displayed longest edge of selected images."""
    bl_idname = "kanvas.average_image_size"
    bl_label = "Average Image Size"
    bl_description = 'Match the displayed longest edge of selected images'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = get_settings(context)
        selected = [item for item in settings.images
                    if item.is_selected and not item.is_locked and item.image_data]
        before = [item.scale_master for item in selected]
        count = average_image_sizes(selected)
        if count < 2:
            self.report({'WARNING'}, "Select at least two images")
            return {'CANCELLED'}
        if all(item.scale_master == old for item, old in zip(selected, before)):
            return {'CANCELLED'}
        affected_frames = {item.parent_frame for item in selected if item.parent_frame}
        if affected_frames:
            space_data = getattr(context, 'space_data', None)
            tree = getattr(space_data, 'edit_tree', None) if space_data else None
            from ..utils.gpu import update_frame_bounds
            for fname in affected_frames:
                update_frame_bounds(tree, settings, fname)
        if context.area:
            context.area.tag_redraw()
        self.report({'INFO'}, f"Averaged the size of {count} images")
        return {'FINISHED'}


class KANVAS_OT_PackImages(KanvasTreeOnly, bpy.types.Operator):
    """Arrange selected images with even gaps; optionally match their sizes."""
    bl_idname  = "kanvas.pack_images"
    bl_label   = "Pack Images"
    bl_description = 'Arrange selected images in rows with even gaps'
    bl_options = {'REGISTER', 'UNDO'}

    gap: bpy.props.IntProperty( # type: ignore
        name="Gap",
        description="Space between packed images",
        default=40,
        min=0,
    )

    average_size: bpy.props.BoolProperty(  # type: ignore
        name="Average Size",
        description="Match the selected images' displayed longest edges before packing",
        default=False,
    )

    def execute(self, context):
        settings = get_settings(context)
        selected = [img for img in settings.images
                    if img.is_selected and not img.is_locked and img.image_data]

        if not selected:
            self.report({'WARNING'}, "No image selected to pack")
            return {'CANCELLED'}

        before = [(tuple(img.location), img.scale_master, img.parent_frame) for img in selected]
        count = pack_image_items(selected, gap=self.gap, average_size=self.average_size)
        if count == 0:
            return {'CANCELLED'}
        space_data = getattr(context, 'space_data', None)
        tree = getattr(space_data, 'edit_tree', None) if space_data else None
        from ..utils.gpu import auto_parent_images_to_frames, update_frame_bounds, sync_kanvas_frames
        affected = auto_parent_images_to_frames(tree, settings, targets=selected)
        for fname in affected:
            update_frame_bounds(tree, settings, fname)
        if affected:
            sync_kanvas_frames(tree, settings)
        if all((tuple(img.location), img.scale_master, img.parent_frame) == old
               for img, old in zip(selected, before)):
            return {'CANCELLED'}
        self.report({'INFO'}, f"Packed {count} images")
        if context.area:
            context.area.tag_redraw()

        return {'FINISHED'}


class KANVAS_OT_ResetTransform(KanvasTreeOnly, bpy.types.Operator):
    """Reset Location, Scale or Rotation of the active Kanvas image"""
    bl_idname = "kanvas.reset_transform"
    bl_label = "Reset Transform"
    bl_description = 'Reset the chosen transform of selected unlocked items'
    bl_options = {'REGISTER', 'UNDO'}

    transform_type: bpy.props.EnumProperty( # type: ignore
        name="Type",
        items=[
            ('LOCATION', "Location", "Reset Position"),
            ('SCALE', "Scale", "Reset Scale and Shear"),
            ('ROTATION', "Rotation", "Reset Rotation")
        ]
    )

    def execute(self, context):
        settings = get_settings(context)
        if not (0 <= settings.active_image_index < len(settings.images)):
            return {'CANCELLED'}

        img = settings.images[settings.active_image_index]

        if self.transform_type == 'LOCATION':
            if tuple(img.location) == (0.0, 0.0):
                return {'CANCELLED'}
            img.location = (0, 0)
        elif self.transform_type == 'SCALE':
            if (tuple(img.scale_xy) == (1.0, 1.0) and img.scale_master == 1.0
                    and tuple(img.shear_xy) == (0.0, 0.0)):
                return {'CANCELLED'}
            img.scale_xy = (1.0, 1.0)
            img.scale_master = 1.0
            img.shear_xy = (0.0, 0.0)
        elif self.transform_type == 'ROTATION':
            if img.rotation == 0.0:
                return {'CANCELLED'}
            img.rotation = 0.0
        else:
            return {'CANCELLED'}

        context.area.tag_redraw()
        return {'FINISHED'}
