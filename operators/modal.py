import bpy
import math
from ..utils.gpu.common import rotate_point, get_prefs, get_collective_bounding_box
from ..utils.gpu.image import get_kanvas_texture
from .image import add_image_to_kanvas

class KANVAS_OT_Modal(bpy.types.Operator):
    """Interactive mode for Kanvas: Select and Move images (Passive/Background)"""
    bl_idname = "kanvas.modal"
    bl_label = "Kanvas Interactivity"
    bl_options = {'REGISTER', 'UNDO'}

    # Internal state (not per-instance because it might stay running)
    drag_target = None
    drag_mode = 'NONE' # 'NONE', 'MOVE', 'SCALE_U', 'SCALE_X', 'SCALE_Y', 'ROTATE', 'SHEAR_X', 'SHEAR_Y', 'SELECT_BOX'
    active_gizmo = -1 
    last_mouse_pos = (0, 0)
    
    # For multi-selection transforms
    multi_targets = [] # List of (img, init_loc, init_scale_master, init_scale_xy, init_rot)
    selection_pivot = (0, 0)

    # Storage for "Cancel" (Right Click/ESC during drag)
    init_loc = (0, 0)
    init_mouse_view = (0, 0)
    init_mouse_local = (0, 0)
    init_scale = (1.0, 1.0)
    init_scale_master = 1.0
    init_shear = (0.0, 0.0)
    init_rot = 0.0
    initial_angle = 0.0

    def start_drag(self, context, img, mode, mouse_pos):
        settings = context.scene.kanvas_settings
        self.drag_target = img
        self.drag_mode = mode
        self.last_mouse_pos = mouse_pos
        self.init_loc = (img.location[0], img.location[1])
        
        # Absolute mouse position in view coordinates for snapping
        self.init_mouse_view = (mouse_pos[0], mouse_pos[1])
        
        self.init_scale = (img.scale_xy[0], img.scale_xy[1])
        self.init_scale_master = img.scale_master
        self.init_shear = (img.shear_xy[0], img.shear_xy[1])
        self.init_rot = img.rotation
        
        dx = mouse_pos[0] - img.location[0]
        dy = mouse_pos[1] - img.location[1]
        self.init_mouse_local = rotate_point((dx, dy), (0, 0), -img.rotation)
        
        # Capture selection state for multi-transform
        self.multi_targets = []
        selected_images = [i for i in settings.images if i.is_selected and i.show_in_editor and i.image_data]
        
        if len(selected_images) > 1:
            data_list = []
            for item in selected_images:
                tex = get_kanvas_texture(item.image_data)
                if tex.texture:
                    data_list.append((item.location, item.scale_xy, item.scale_master, item.shear_xy, item.rotation, tex.texture.width, tex.texture.height))
                
                self.multi_targets.append({
                    'img': item,
                    'loc': (item.location[0], item.location[1]),
                    'scale_master': item.scale_master,
                    'scale_xy': (item.scale_xy[0], item.scale_xy[1]),
                    'rot': item.rotation
                })
            
            bbox = get_collective_bounding_box(data_list)
            if bbox:
                self.selection_pivot = ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
                cdx = mouse_pos[0] - self.selection_pivot[0]
                cdy = mouse_pos[1] - self.selection_pivot[1]
                self.init_mouse_local = (cdx, cdy)
            else:
                self.selection_pivot = (img.location[0], img.location[1])
        else:
            if img.is_selected:
                self.multi_targets.append({
                    'img': img,
                    'loc': (img.location[0], img.location[1]),
                    'scale_master': img.scale_master,
                    'scale_xy': (img.scale_xy[0], img.scale_xy[1]),
                    'rot': img.rotation
                })
            self.selection_pivot = (img.location[0], img.location[1])

        if mode == 'ROTATE':
            self.initial_angle = self.get_angle(self.selection_pivot, mouse_pos)

    def get_angle(self, center, mouse):
        return math.degrees(math.atan2(mouse[1] - center[1], mouse[0] - center[0]))

    def get_gizmo_under_mouse(self, context, mouse_pos):
        settings = context.scene.kanvas_settings
        if not settings.show_gizmos:
            return -1

        selected_images = [img for img in settings.images if img.is_selected and img.show_in_editor and img.image_data]
        multi_select = len(selected_images) > 1
        
        region = context.region
        v2d = region.view2d
        view_pixel_size = abs(v2d.region_to_view(1, 1)[0] - v2d.region_to_view(0, 0)[0])
        s_view = settings.gizmo_size * view_pixel_size

        if multi_select:
            data_list = []
            for img in selected_images:
                tex = get_kanvas_texture(img.image_data)
                if tex.texture:
                    data_list.append((img.location, img.scale_xy, img.scale_master, img.shear_xy, img.rotation, tex.texture.width, tex.texture.height))
            
            bbox = get_collective_bounding_box(data_list)
            if not bbox: return -1
            
            min_x, min_y, max_x, max_y = bbox
            mid_x = (min_x + max_x) / 2
            mid_y = (min_y + max_y) / 2
            
            corners = [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
            mids = [(mid_x, min_y), (max_x, mid_y), (mid_x, max_y), (min_x, mid_y)]

            # Check Rotation
            if settings.show_rotate_handles:
                off = s_view * 1.5
                for i, p in enumerate(corners):
                    dx, dy = p[0] - mid_x, p[1] - mid_y
                    mag = (dx**2 + dy**2)**0.5
                    if mag > 0:
                        rh_pos = (p[0] + (dx/mag)*off, p[1] + (dy/mag)*off)
                        if abs(rh_pos[0] - mouse_pos[0]) < s_view/2 and abs(rh_pos[1] - mouse_pos[1]) < s_view/2:
                            return i + 8

            # Check Corners (Scale)
            if settings.show_scale_handles:
                for i, p in enumerate(corners):
                    if abs(p[0] - mouse_pos[0]) < s_view/2 and abs(p[1] - mouse_pos[1]) < s_view/2:
                        return i
            return -1

        # Fallback to single active image gizmos
        if settings.active_image_index >= len(settings.images):
            return -1
        
        img = settings.images[settings.active_image_index]
        if not img.show_in_editor or not img.image_data:
            return -1

        tex_manager = get_kanvas_texture(img.image_data)
        if not tex_manager.texture:
            return -1

        w = tex_manager.texture.width  * img.scale_xy[0] * img.scale_master
        h = tex_manager.texture.height * img.scale_xy[1] * img.scale_master
        loc = img.location
        sh  = img.shear_xy

        corners_rel = [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]
        mids_rel    = [(0, -h/2), (w/2, 0), (0, h/2), (-w/2, 0)]
        
        def apply_shear_scale_rot(p, offset=0):
            ps = (p[0] + p[1] * sh[0], p[1] + p[0] * sh[1])
            if offset != 0:
                mag = (ps[0]**2 + ps[1]**2)**0.5
                if mag > 0:
                    ps = (ps[0] + (ps[0]/mag)*offset, ps[1] + (ps[1]/mag)*offset)
            return rotate_point((ps[0] + loc[0], ps[1] + loc[1]), loc, img.rotation)

        if settings.show_rotate_handles:
            for i, p in enumerate(corners_rel):
                rh_pos = apply_shear_scale_rot(p, offset=s_view * 1.5)
                if abs(rh_pos[0] - mouse_pos[0]) < s_view/2 and abs(rh_pos[1] - mouse_pos[1]) < s_view/2:
                    return i + 8

        if settings.show_scale_handles:
            for i, p in enumerate(mids_rel):
                rh_pos = apply_shear_scale_rot(p)
                if abs(rh_pos[0] - mouse_pos[0]) < s_view/2 and abs(rh_pos[1] - mouse_pos[1]) < s_view/2:
                    return i + 4
            for i, p in enumerate(corners_rel):
                rh_pos = apply_shear_scale_rot(p)
                if abs(rh_pos[0] - mouse_pos[0]) < s_view/2 and abs(rh_pos[1] - mouse_pos[1]) < s_view/2:
                    return i
                    
        return -1

    def find_image_at_pos(self, context, mouse_pos):
        """Returns (index, image_item) or (None, None) if no image under mouse_pos"""
        settings = context.scene.kanvas_settings
        
        for idx in range(len(settings.images) - 1, -1, -1):
            img = settings.images[idx]
            if not img.show_in_editor or not img.image_data: continue
            
            tex_manager = get_kanvas_texture(img.image_data)
            if not tex_manager.texture: continue

            # 1. Inverse Rotation
            p_rel = rotate_point(mouse_pos, img.location, -img.rotation)
            dx = p_rel[0] - img.location[0]
            dy = p_rel[1] - img.location[1]

            # 2. Inverse Shear
            shx, shy = img.shear_xy
            denom = (1.0 - shx * shy)
            if abs(denom) < 0.0001: denom = 0.0001
            
            dy_raw = (dy - dx * shy) / denom
            dx_raw = dx - dy_raw * shx

            # 3. Check AABB
            w = tex_manager.texture.width  * img.scale_xy[0] * img.scale_master
            h = tex_manager.texture.height * img.scale_xy[1] * img.scale_master
            
            if -w/2 <= dx_raw <= w/2 and -h/2 <= dy_raw <= h/2:
                return idx, img
        return None, None

    def modal(self, context, event):
        settings = context.scene.kanvas_settings
        
        # Immediate refresh on modifier press/release for dynamic icons
        if event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT', 'LEFT_ALT', 'RIGHT_ALT', 'LEFT_CTRL', 'RIGHT_CTRL'}:
            settings.shift_is_held = event.shift
            settings.alt_is_held = event.alt
            settings.ctrl_is_held = event.ctrl
            context.area.tag_redraw()
            
        settings.shift_is_held = event.shift
        settings.alt_is_held = event.alt
        settings.ctrl_is_held = event.ctrl
        prefs = get_prefs()
        if not prefs:
            return {'PASS_THROUGH'}

        if not settings.is_modal_running:
            context.area.tag_redraw()
            return {'FINISHED'}

        region = context.region
        v2d = region.view2d
        mouse_x, mouse_y = v2d.region_to_view(event.mouse_region_x, event.mouse_region_y)

        # 0. Handle Drag and Drop
        if event.type in {'DROP_BEGIN', 'DROP_FILE', 'DROP_POST'}:
            if event.type == 'DROP_FILE':
                for f in context.window_manager.drop_files:
                    add_image_to_kanvas(context, f.name, location=(mouse_x, mouse_y))
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}

        if self.drag_mode == 'NONE':
            if event.value == 'PRESS':
                key = event.type
                active_idx = settings.active_image_index
                img = settings.images[active_idx] if 0 <= active_idx < len(settings.images) else None
                if img:
                    # Reset Shortcuts (Alt + Key)
                    if event.alt:
                        if key == 'G':
                            img.location = (0, 0)
                            context.area.tag_redraw()
                            return {'RUNNING_MODAL'}
                        elif key == 'S':
                            img.scale_xy = (1.0, 1.0)
                            img.scale_master = 1.0
                            img.shear_xy = (0.0, 0.0)
                            context.area.tag_redraw()
                            return {'RUNNING_MODAL'}
                        elif key == 'R':
                            img.rotation = 0.0
                            context.area.tag_redraw()
                            return {'RUNNING_MODAL'}

                    if key == prefs.key_move:
                        self.start_drag(context, img, 'MOVE', (mouse_x, mouse_y))
                        return {'RUNNING_MODAL'}
                    elif key == prefs.key_scale:
                        self.start_drag(context, img, 'SCALE_U', (mouse_x, mouse_y))
                        return {'RUNNING_MODAL'}
                    elif key == prefs.key_rotate:
                        self.start_drag(context, img, 'ROTATE', (mouse_x, mouse_y))
                        return {'RUNNING_MODAL'}
                    elif key == 'D' and event.shift:
                        bpy.ops.kanvas.duplicate_image()
                        new_img = settings.images[settings.active_image_index]
                        self.start_drag(context, new_img, 'MOVE', (mouse_x, mouse_y))
                        return {'RUNNING_MODAL'}
                    elif key == prefs.key_delete:
                        bpy.ops.kanvas.remove_image('INVOKE_DEFAULT', index=active_idx)
                        return {'RUNNING_MODAL'}
                    elif key == 'P':
                        # Only pack if multiple are selected
                        selected_count = sum(1 for i in settings.images if i.is_selected)
                        if selected_count > 1:
                            bpy.ops.kanvas.pack_images()
                            return {'RUNNING_MODAL'}

            if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
                if not settings.use_interactivity:
                    return {'PASS_THROUGH'}

                # IMPORTANT: If we are clicking on UI (Headers, Sidebars, Menus), let Blender handle it!
                if context.region.type != 'WINDOW':
                    return {'PASS_THROUGH'}

                if not settings.is_modal_running:
                    return {'PASS_THROUGH'}

                gizmo_idx = self.get_gizmo_under_mouse(context, (mouse_x, mouse_y))
                if gizmo_idx != -1:
                    img = settings.images[settings.active_image_index]
                    self.active_gizmo = gizmo_idx
                    
                    mode = 'NONE'
                    if 0 <= gizmo_idx <= 3: mode = 'SCALE_U'
                    elif gizmo_idx in {4, 6}: mode = 'SCALE_Y'
                    
                    # Dynamic Shear Modifier check
                    mod_is_held = False
                    if prefs.key_shear_mod == 'ALT': mod_is_held = event.alt
                    elif prefs.key_shear_mod == 'SHIFT': mod_is_held = event.shift
                    elif prefs.key_shear_mod == 'CTRL': mod_is_held = event.ctrl

                    if gizmo_idx == 5 or gizmo_idx == 7: 
                        mode = 'SCALE_X' if not mod_is_held else 'SHEAR_Y'
                    elif gizmo_idx == 4 or gizmo_idx == 6:
                        mode = 'SCALE_Y' if not mod_is_held else 'SHEAR_X'
                    
                    if 8 <= gizmo_idx <= 11: mode = 'ROTATE'
                    
                    self.start_drag(context, img, mode, (mouse_x, mouse_y))
                    return {'RUNNING_MODAL'}

                hit_idx, hit_img = self.find_image_at_pos(context, (mouse_x, mouse_y))
                if hit_img:
                    if event.shift:
                        hit_img.is_selected = not hit_img.is_selected
                        if hit_img.is_selected:
                            settings.active_image_index = hit_idx
                    else:
                        if not hit_img.is_selected:
                            for item in settings.images:
                                item.is_selected = False
                        hit_img.is_selected = True
                        settings.active_image_index = hit_idx

                    settings.images.move(hit_idx, len(settings.images) - 1)
                    settings.active_image_index = len(settings.images) - 1
                    
                    if hit_img.is_selected:
                        self.start_drag(context, hit_img, 'MOVE', (mouse_x, mouse_y))
                    context.area.tag_redraw()
                    return {'RUNNING_MODAL'}
                
                # C. No Hit -> Start Box Selection (Alt held) or Pass Through
                if event.alt:
                    self.drag_mode = 'SELECT_BOX'
                    settings.show_box_sel = True
                    settings.box_sel_start = (mouse_x, mouse_y)
                    settings.box_sel_end = (mouse_x, mouse_y)
                    
                    if not event.shift:
                        for item in settings.images:
                            item.is_selected = False
                    
                    context.area.tag_redraw()
                    return {'RUNNING_MODAL'}
                
                if not event.shift:
                    cleared_any = False
                    for item in settings.images:
                        if item.is_selected:
                            item.is_selected = False
                            cleared_any = True
                    if cleared_any:
                        context.area.tag_redraw()
                
                return {'PASS_THROUGH'}

            # Handle Mouse Wheel (Opacity)
            if event.type in {'WHEELUP_MOUSE', 'WHEELDOWN_MOUSE'}:
                _, hit_img = self.find_image_at_pos(context, (mouse_x, mouse_y))
                if hit_img:
                    delta = 0.05 if event.type == 'WHEELUP_MOUSE' else -0.05
                    hit_img.opacity = max(0.0, min(1.0, hit_img.opacity + delta))
                    context.area.tag_redraw()
                    return {'RUNNING_MODAL'}
                return {'PASS_THROUGH'}

        else:
            if event.type == 'MOUSEMOVE':
                self.update_drag(context, event, mouse_x, mouse_y)
                context.area.tag_redraw()
                return {'RUNNING_MODAL'}

            elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
                self.stop_drag(context)
                return {'RUNNING_MODAL'}

            elif event.type in {'ESC', 'RIGHTMOUSE'}:
                self.cancel_drag(context)
                return {'RUNNING_MODAL'}
            
            elif event.type == 'RET' and event.value == 'PRESS':
                self.stop_drag(context)
                return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}


    def update_drag(self, context, event, mouse_x, mouse_y):
        if self.drag_mode == 'SELECT_BOX':
            settings = context.scene.kanvas_settings
            settings.box_sel_end = (mouse_x, mouse_y)
            return

        if not self.drag_target: return
        
        multi_select = len(self.multi_targets) > 1
        
        if multi_select:
            clx = mouse_x - self.selection_pivot[0]
            cly = mouse_y - self.selection_pivot[1]
        else:
            dx = mouse_x - self.drag_target.location[0]
            dy = mouse_y - self.drag_target.location[1]
            curr_local = rotate_point((dx, dy), (0, 0), -self.drag_target.rotation)
            clx, cly = curr_local

        tex_data = self.drag_target.image_data
        half_w = (tex_data.size[0] / 2) if tex_data else 100
        half_h = (tex_data.size[1] / 2) if tex_data else 100

        if self.drag_mode == 'MOVE':
            settings = context.scene.kanvas_settings
            
            region = context.region
            v2d = region.view2d
            curr_mouse_view = v2d.region_to_view(event.mouse_region_x, event.mouse_region_y)
            
            total_dx = curr_mouse_view[0] - self.init_mouse_view[0]
            total_dy = curr_mouse_view[1] - self.init_mouse_view[1]
            
            nx = self.init_loc[0] + total_dx
            ny = self.init_loc[1] + total_dy
            
            settings.show_snap_viz_x = False
            settings.show_snap_viz_y = False

            if settings.use_snapping:
                if settings.snap_grid:
                    nx = round(nx / settings.grid_size) * settings.grid_size
                    ny = round(ny / settings.grid_size) * settings.grid_size
                
                if settings.snap_images:
                    tx, ty = nx, ny
                    tw = (tex_data.size[0] * self.drag_target.scale_xy[0] * self.drag_target.scale_master) if tex_data else 0
                    th = (tex_data.size[1] * self.drag_target.scale_xy[1] * self.drag_target.scale_master) if tex_data else 0
                    
                    t_pts_x = [tx, tx - tw/2, tx + tw/2]
                    t_pts_y = [ty, ty - th/2, ty + th/2]
                    best_dx, best_dy = settings.snap_threshold, settings.snap_threshold
                    
                    for img in settings.images:
                        if img == self.drag_target or not img.show_in_editor: continue
                        if not img.image_data: continue
                        
                        iw = img.image_data.size[0] * img.scale_xy[0] * img.scale_master
                        ih = img.image_data.size[1] * img.scale_xy[1] * img.scale_master
                        i_pts_x = [img.location[0], img.location[0] - iw/2, img.location[0] + iw/2]
                        i_pts_y = [img.location[1], img.location[1] - ih/2, img.location[1] + ih/2]
                        
                        for tp in t_pts_x:
                            for ip in i_pts_x:
                                if abs(tp - ip) < best_dx:
                                    best_dx = abs(tp - ip)
                                    nx = tx + (ip - tp)
                                    settings.snap_viz_x = ip
                                    settings.show_snap_viz_x = True
                        for tp in t_pts_y:
                            for ip in i_pts_y:
                                if abs(tp - ip) < best_dy:
                                    best_dy = abs(tp - ip)
                                    ny = ty + (ip - tp)
                                    settings.snap_viz_y = ip
                                    settings.show_snap_viz_y = True

            main_dx = nx - self.init_loc[0]
            main_dy = ny - self.init_loc[1]
            
            for item in self.multi_targets:
                img = item['img']
                img.location[0] = item['loc'][0] + main_dx
                img.location[1] = item['loc'][1] + main_dy

        elif self.drag_mode == 'SCALE_U':
            dist_init = (self.init_mouse_local[0]**2 + self.init_mouse_local[1]**2)**0.5
            dist_curr = (clx**2 + cly**2)**0.5
            if dist_init > 0:
                scale_factor = (dist_curr / dist_init)
                
                for target in self.multi_targets:
                    item = target['img']
                    item.scale_master = target['scale_master'] * scale_factor
                    
                    if len(self.multi_targets) > 1:
                        item.location[0] = self.selection_pivot[0] + (target['loc'][0] - self.selection_pivot[0]) * scale_factor
                        item.location[1] = self.selection_pivot[1] + (target['loc'][1] - self.selection_pivot[1]) * scale_factor

        elif self.drag_mode == 'SCALE_X':
            self.drag_target.scale_xy[0] = max(0.001, (abs(clx) / half_w) / self.drag_target.scale_master)

        elif self.drag_mode == 'SCALE_Y':
            self.drag_target.scale_xy[1] = max(0.001, (abs(cly) / half_h) / self.drag_target.scale_master)

        elif self.drag_mode == 'SHEAR_X':
            if abs(cly) > 10:
                self.drag_target.shear_xy[0] = clx / cly

        elif self.drag_mode == 'SHEAR_Y':
            if abs(clx) > 10:
                self.drag_target.shear_xy[1] = cly / clx

        elif self.drag_mode == 'ROTATE':
            pivot = self.selection_pivot if multi_select else self.drag_target.location
            curr_angle = self.get_angle(pivot, (mouse_x, mouse_y))
            rot_delta = curr_angle - self.initial_angle
            
            for target in self.multi_targets:
                item = target['img']
                item.rotation = target['rot'] + rot_delta
                
                if len(self.multi_targets) > 1:
                    item.location[0], item.location[1] = rotate_point(target['loc'], self.selection_pivot, rot_delta)

        self.last_mouse_pos = (mouse_x, mouse_y)

    def stop_drag(self, context):
        settings = context.scene.kanvas_settings
        if self.drag_mode == 'SELECT_BOX':
            self.perform_box_selection(context)
            settings.show_box_sel = False

        self.drag_mode = 'NONE'
        self.drag_target = None
        self.active_gizmo = -1
        settings.show_snap_viz_x = False
        settings.show_snap_viz_y = False
        context.area.tag_redraw()

    def perform_box_selection(self, context):
        settings = context.scene.kanvas_settings
        start = settings.box_sel_start
        end = settings.box_sel_end
        
        min_x, max_x = sorted([start[0], end[0]])
        min_y, max_y = sorted([start[1], end[1]])
        
        # Avoid tiny boxes acting as clicks
        if abs(max_x - min_x) < 0.01 and abs(max_y - min_y) < 0.01:
            return

        for idx, img in enumerate(settings.images):
            loc = img.location
            if min_x <= loc[0] <= max_x and min_y <= loc[1] <= max_y:
                img.is_selected = True
                # Set active index to the last one found in box
                settings.active_image_index = idx

    def cancel_drag(self, context):
        settings = context.scene.kanvas_settings
        settings.show_box_sel = False
        if self.drag_target:
            self.drag_target.location = self.init_loc
            self.drag_target.scale_xy = self.init_scale
            self.drag_target.scale_master = self.init_scale_master
            self.drag_target.shear_xy = self.init_shear
            self.drag_target.rotation = self.init_rot
        self.stop_drag(context)

    def invoke(self, context, event):
        if context.area.type == 'NODE_EDITOR':
            settings = context.scene.kanvas_settings
            if settings.is_modal_running:
                return {'CANCELLED'}
                
            self.drag_mode = 'NONE'
            self.drag_target = None
            settings.is_modal_running = True
            
            context.window_manager.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Node Editor not found")
            return {'CANCELLED'}

    def cancel(self, context):
        context.scene.kanvas_settings.is_modal_running = False
