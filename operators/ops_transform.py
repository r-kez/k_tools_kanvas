import bpy
from ..utils.kanvas_data import get_settings
from .kanvas_context import KanvasTreeOnly
import math
from ..utils.gpu.gpu_common import rotate_point

class KANVAS_OT_TransformImage(KanvasTreeOnly, bpy.types.Operator):
    """Short-lived modal to handle drag transformations"""
    bl_idname = "kanvas.transform_image"
    bl_label = "Transform Kanvas Image"
    bl_description = 'Move, scale, or rotate the active image with the mouse'
    bl_options = {'REGISTER', 'UNDO'}

    mode: bpy.props.StringProperty( # type: ignore
        name="Mode", default='MOVE')
    index: bpy.props.IntProperty( # type: ignore
        name="Index", default=0)

    def invoke(self, context, event):
        self.settings = get_settings(context)
        if not (0 <= self.settings.active_image_index < len(self.settings.images)):
            return {'CANCELLED'}

        self.img = self.settings.images[self.settings.active_image_index]
        if getattr(self.img, "item_type", 'IMAGE') == 'FRAME' or not self.img.image_data:
            return {'CANCELLED'}
        
        # Garante que a imagem está selecionada ao interagir
        if not self.img.is_selected:
            for item in self.settings.images:
                item.is_selected = False
            self.img.is_selected = True
        
        # Joga para frente (Z-index)
        other_z = [img.z_index for img in self.settings.images if img != self.img]
        max_other_z = max(other_z) if other_z else -1
        if self.img.z_index <= max_other_z:
            self.img.z_index = max_other_z + 1
        # Converte a posição inicial do mouse
        v2d = context.region.view2d
        self.init_mouse = v2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
        
        # Guarda o estado inicial da imagem
        self.init_loc = (self.img.location[0], self.img.location[1])
        self.init_scale = (self.img.scale_xy[0], self.img.scale_xy[1])
        self.init_scale_master = self.img.scale_master
        self.init_rot = self.img.rotation

        # Inicia o loop modal restrito ao clique
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        # Atualiza o estado das teclas para o desenho da GPU
        self.settings.alt_is_held = event.alt
        self.settings.shift_is_held = event.shift
        self.settings.ctrl_is_held = event.ctrl

        v2d = context.region.view2d
        mouse_x, mouse_y = v2d.region_to_view(event.mouse_region_x, event.mouse_region_y)

        if event.type == 'MOUSEMOVE':
            if self.mode == 'MOVE':
                dx = mouse_x - self.init_mouse[0]
                dy = mouse_y - self.init_mouse[1]
                self.img.location = (self.init_loc[0] + dx, self.init_loc[1] + dy)
            
            elif self.mode == 'SCALE':
                # Distância atual do mouse ao centro da imagem
                center = self.img.location
                init_dist = math.hypot(self.init_mouse[0] - center[0], self.init_mouse[1] - center[1])
                curr_dist = math.hypot(mouse_x - center[0], mouse_y - center[1])
                
                if init_dist > 0.1:
                    ratio = curr_dist / init_dist
                    self.img.scale_master = self.init_scale_master * ratio

            elif self.mode == 'ROTATE':
                center = self.img.location
                
                # Ângulo inicial do mouse em relação ao centro (em radianos)
                # O atan2 já lida com o sinal dos eixos.
                a1 = math.atan2(self.init_mouse[1] - center[1], self.init_mouse[0] - center[0])
                a2 = math.atan2(mouse_y - center[1], mouse_x - center[0])
                
                # A diferença em graus
                diff = math.degrees(a2 - a1)
                
                # Aplica a rotação acumulada
                self.img.rotation = self.init_rot + diff

            elif self.mode == 'STRETCH':
                center = self.img.location
                
                # Desfaz a rotação no mouse para trabalhar em eixos locais (Alinhados à imagem)
                curr_l = rotate_point((mouse_x, mouse_y), center, -self.img.rotation)
                
                bw = self.img.image_data.size[0] * self.img.scale_master
                bh = self.img.image_data.size[1] * self.img.scale_master
                if bw == 0 or bh == 0: return {'RUNNING_MODAL'}

                # Detecta se quer Shear (Hold Modifier) ou Stretch (Padrão)
                from ..utils.gpu.gpu_common import get_prefs
                prefs = get_prefs()
                mod_key = prefs.key_shear_mod if prefs else 'ALT'
                
                is_shear = False
                if mod_key == 'ALT': is_shear = event.alt
                elif mod_key == 'SHIFT': is_shear = event.shift
                elif mod_key == 'CTRL': is_shear = event.ctrl
                
                if self.index in {1, 3}: # Meios Laterais
                    if not is_shear:
                        new_w = abs(curr_l[0] - center[0]) * 2
                        self.img.scale_xy[0] = new_w / bw
                    else:
                        self.img.shear_xy[1] = (curr_l[1] - center[1]) / (bw / 2 * self.img.scale_xy[0])
                
                elif self.index in {0, 2}: # Meios Superior/Inferior
                    if not is_shear:
                        new_h = abs(curr_l[1] - center[1]) * 2
                        self.img.scale_xy[1] = new_h / bh
                    else:
                        self.img.shear_xy[0] = (curr_l[0] - center[0]) / (bh / 2 * self.img.scale_xy[1])

            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            context.area.tag_redraw()
            return {'FINISHED'}
        
        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            # Restaura se o usuário cancelar
            self.img.location = self.init_loc
            self.img.scale_xy = self.init_scale
            self.img.scale_master = self.init_scale_master
            self.img.rotation = self.init_rot
            context.area.tag_redraw()
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}
