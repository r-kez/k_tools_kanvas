import bpy
from ..utils.kanvas_data import get_settings
from .kanvas_context import KanvasTreeOnly
from ..utils.gpu.gpu_common import rotate_point
# Substitua o import acima pelo caminho correto da sua função rotate_point

class KANVAS_OT_SelectImage(KanvasTreeOnly, bpy.types.Operator):
    """Select Kanvas images (Click or Shift+Click)"""
    bl_idname = "kanvas.select_image"
    bl_label = "Select Image"
    bl_description = 'Select an image on the canvas; hold Shift to add to the selection'
    bl_options = {'INTERNAL'}

    deselect_all: bpy.props.BoolProperty(default=False)
    toggle: bpy.props.BoolProperty(default=False)

    def invoke(self, context, event):
        settings = get_settings(context)
        
        # Converte a posição do mouse para o espaço 2D
        v2d = context.region.view2d
        mouse_x, mouse_y = v2d.region_to_view(event.mouse_region_x, event.mouse_region_y)

        # Se clicou no fundo (ação de deselecionar)
        if self.deselect_all:
            for item in settings.images:
                item.is_selected = False
            context.area.tag_redraw()
            return {'FINISHED'}

        # Lógica para achar a imagem sob o mouse (do seu código original)
        sorted_indices = sorted(range(len(settings.images)), key=lambda i: settings.images[i].z_index, reverse=True)
        hit_idx, hit_img = None, None

        for idx in sorted_indices:
            img = settings.images[idx]
            if not img.show_in_editor or not img.image_data: continue

            # Aplica a rotação inversa para testar a colisão num retângulo reto
            p_rel = rotate_point((mouse_x, mouse_y), img.location, -img.rotation)
            dx = p_rel[0] - img.location[0]
            dy = p_rel[1] - img.location[1]

            shx, shy = img.shear_xy
            denom = (1.0 - shx * shy)
            if abs(denom) < 0.0001: denom = 0.0001

            dy_raw = (dy - dx * shy) / denom
            dx_raw = dx - dy_raw * shx

            w = img.image_data.size[0] * img.scale_xy[0] * img.scale_master
            h = img.image_data.size[1] * img.scale_xy[1] * img.scale_master

            if -w/2 <= dx_raw <= w/2 and -h/2 <= dy_raw <= h/2:
                hit_idx = idx
                hit_img = img
                break # Achou a imagem mais ao topo!

        if hit_img:
            if self.toggle: # Shift pressionado
                hit_img.is_selected = not hit_img.is_selected
                if hit_img.is_selected:
                    settings.active_image_index = hit_idx
            else:
                if not hit_img.is_selected:
                    for item in settings.images:
                        item.is_selected = False
                hit_img.is_selected = True
                settings.active_image_index = hit_idx

        else:
            # Clicou fora de tudo
            if not self.toggle:
                for item in settings.images:
                    item.is_selected = False

        context.area.tag_redraw()
        return {'FINISHED'}
