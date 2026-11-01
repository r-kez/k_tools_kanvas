import bpy
from ..utils.kanvas_data import get_settings
import math
from ..utils.gpu.gpu_common import rotate_point

# 1. GIZMO BASE (Apenas lógica, não registrável diretamente)
class KANVAS_GT_BaseGizmo:
    def draw(self, context):
        pass

    def test_select(self, context, location):
        settings = get_settings(context)
        if sum(bool(img.is_selected and img.image_data and img.show_in_editor)
               for img in settings.images) != 1:
            return -1
        # O mouse já vem em Region Space (pixels da área)
        mx, my = location
        
        # Converte a posição do Gizmo (View Space) para Region Space
        v2d = context.region.view2d
        gx = self.matrix_basis[0][3]
        gy = self.matrix_basis[1][3]
        rx, ry = v2d.view_to_region(gx, gy)
        
        # Hitbox em pixels de tela (mais confiável)
        radius = getattr(self, "hitbox_radius", 20)
        
        dist = math.hypot(mx - rx, my - ry)

        if dist < radius:
            return 0
        return -1

# Gizmo de Movimento (Central)
class KANVAS_GT_MoveGizmo(bpy.types.Gizmo, KANVAS_GT_BaseGizmo):
    bl_idname = "KANVAS_GT_move_gizmo"

    def test_select(self, context, location):
        settings = get_settings(context)
        if sum(bool(img.is_selected and img.image_data and img.show_in_editor)
               for img in settings.images) != 1:
            return -1
        mx, my = location
        v2d = context.region.view2d
        
        # Posição central em Region Space
        gx = self.matrix_basis[0][3]
        gy = self.matrix_basis[1][3]
        rx, ry = v2d.view_to_region(gx, gy)
        
        # Hitbox (convertemos o mouse de volta para view space para testar contra o retângulo rotacionado)
        mouse_view = v2d.region_to_view(mx, my)
        
        w = getattr(self, "hitbox_w", 50)
        h = getattr(self, "hitbox_h", 50)
        rot = getattr(self, "hitbox_rot", 0)

        p_rel = rotate_point(mouse_view, (gx, gy), -rot)
        dx = abs(p_rel[0] - gx)
        dy = abs(p_rel[1] - gy)

        if dx < w and dy < h:
            return 0
        return -1

# Gizmo de Escala (Cantos)
class KANVAS_GT_ScaleGizmo(bpy.types.Gizmo, KANVAS_GT_BaseGizmo):
    bl_idname = "KANVAS_GT_scale_gizmo"

# Gizmo de Rotação (Externo)
class KANVAS_GT_RotateGizmo(bpy.types.Gizmo, KANVAS_GT_BaseGizmo):
    bl_idname = "KANVAS_GT_rotate_gizmo"


# 2. O NOSSO GIZMOGROUP 
class KANVAS_GGT_ImageGizmos(bpy.types.GizmoGroup):
    bl_idname = "KANVAS_GGT_image_gizmos"
    bl_label = "Kanvas Gizmos"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', 'SCALE'}

    @classmethod
    def poll(cls, context):
        # kanvas.interact now draws and handles these same controls. Keeping this
        # older group active steals clicks on an already selected image and
        # routes movement through kanvas.transform_image, which has no Snap.
        return False

    def setup(self, context):
        # 1. Gizmos de Escala (4 Cantos) - Prioridade Alta
        self.scale_gizmos = []
        for i in range(4):
            gz = self.gizmos.new("KANVAS_GT_scale_gizmo")
            gz.target_set_operator("kanvas.transform_image").mode = 'SCALE'
            gz.use_draw_modal = True
            gz.select_bias = 1.0 # Ganha se houver sobreposição
            self.scale_gizmos.append(gz)

        # 2. Gizmos de Rotação (4 Cantos Externos) - Prioridade Alta
        self.rotate_gizmos = []
        for i in range(4):
            gz = self.gizmos.new("KANVAS_GT_rotate_gizmo")
            gz.target_set_operator("kanvas.transform_image").mode = 'ROTATE'
            gz.use_draw_modal = True
            gz.select_bias = 1.0
            self.rotate_gizmos.append(gz)

        self.stretch_gizmos = []
        for i in range(4):
            gz = self.gizmos.new("KANVAS_GT_scale_gizmo")
            props = gz.target_set_operator("kanvas.transform_image")
            props.mode = 'STRETCH'
            props.index = i
            gz.use_draw_modal = True
            gz.select_bias = 1.0
            self.stretch_gizmos.append(gz)

        # 4. Gizmo de Movimento (Corpo da Imagem) - Prioridade Baixa
        self.move_gizmo = self.gizmos.new("KANVAS_GT_move_gizmo")
        self.move_gizmo.target_set_operator("kanvas.transform_image").mode = 'MOVE'
        self.move_gizmo.use_draw_modal = True
        self.move_gizmo.select_bias = -1.0 # Perde se houver sobreposição

    def draw_prepare(self, context):
        settings = get_settings(context)

        # Collective handles are drawn and handled by kanvas.interact. The
        # active-image gizmos would otherwise intercept a group transform.
        if sum(bool(item.is_selected and item.image_data and item.show_in_editor)
               for item in settings.images) != 1:
            self.hide_all()
            return
        
        if not (0 <= settings.active_image_index < len(settings.images)):
            self.hide_all()
            return

        img = settings.images[settings.active_image_index]
        if not img.is_selected or not img.show_in_editor or not img.image_data:
            self.hide_all()
            return

        self.show_all()

        # Dados da imagem
        loc = img.location
        rot = img.rotation
        w = img.image_data.size[0] * img.scale_xy[0] * img.scale_master
        h = img.image_data.size[1] * img.scale_xy[1] * img.scale_master
        
        # 1. Configura Gizmo de Movimento (Tamanho Total da Imagem)
        self.move_gizmo.matrix_basis[0][3] = loc[0]
        self.move_gizmo.matrix_basis[1][3] = loc[1]
        self.move_gizmo.hitbox_w = w / 2
        self.move_gizmo.hitbox_h = h / 2
        self.move_gizmo.hitbox_rot = rot

        # 2. Configura Gizmos de Escala e Rotação
        corners = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]
        gizmo_size = settings.gizmo_size
        
        for i, (gz_s, gz_r) in enumerate(zip(self.scale_gizmos, self.rotate_gizmos)):
            # Posição do canto com Shear (opcional, vamos simplificar por enquanto)
            # cp = (corners[i][0] + corners[i][1] * img.shear_xy[0], corners[i][1] + corners[i][0] * img.shear_xy[1])
            cp = corners[i]
            
            # Posição final rotacionada
            pos_canto = rotate_point((cp[0] + loc[0], cp[1] + loc[1]), loc, rot)
            
            # Escala
            gz_s.matrix_basis[0][3] = pos_canto[0]
            gz_s.matrix_basis[1][3] = pos_canto[1]
            gz_s.hitbox_radius = 20 # 20 pixels de raio é generoso

            # Rotação (Offset do canto)
            mag = math.hypot(cp[0], cp[1])
            if mag > 0:
                off = gizmo_size * 1.5
                po = (cp[0] + (cp[0]/mag)*off, cp[1] + (cp[1]/mag)*off)
                pos_rot = rotate_point((po[0] + loc[0], po[1] + loc[1]), loc, rot)
                
                gz_r.matrix_basis[0][3] = pos_rot[0]
                gz_r.matrix_basis[1][3] = pos_rot[1]
                gz_r.hitbox_radius = 20

        # 3. Configura Gizmos de Stretch/Shear (Meios)
        mids = [(0, -h/2), (w/2, 0), (0, h/2), (-w/2, 0)]
        for i, gz in enumerate(self.stretch_gizmos):
            pos_mid = rotate_point((mids[i][0] + loc[0], mids[i][1] + loc[1]), loc, rot)
            gz.matrix_basis[0][3] = pos_mid[0]
            gz.matrix_basis[1][3] = pos_mid[1]
            gz.hitbox_radius = 20

    def hide_all(self):
        self.move_gizmo.hide = True
        for gz in self.scale_gizmos: gz.hide = True
        for gz in self.rotate_gizmos: gz.hide = True
        for gz in self.stretch_gizmos: gz.hide = True

    def show_all(self):
        self.move_gizmo.hide = False
        for gz in self.scale_gizmos: gz.hide = False
        for gz in self.rotate_gizmos: gz.hide = False
        for gz in self.stretch_gizmos: gz.hide = False
