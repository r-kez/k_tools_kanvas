# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
import bpy

bl_info = {
    "name": "Kanvas",
    "author": "Robert Kezives",
    "description": "",
    "blender": (5, 0, 0),
    "version": (0, 0, 1),
    "location": "",
    "warning": "",
    "category": "Generic",
}

from . import auto_load

auto_load.init()

def draw_kanvas_header(self, context):
    """Draw Kanvas controls in the Node Editor header."""
    if not hasattr(context, "space_data") or not context.space_data or context.space_data.type != 'NODE_EDITOR':
        return
    
    tree = context.space_data.edit_tree
    if not tree or tree.bl_idname != 'KanvasNodeTree':
        return

    layout = self.layout
    settings = context.scene.kanvas_settings
    # Only show a start button if modal is not active
    if not settings.is_modal_running:
        layout.operator("kanvas.modal", text="Start Kanvas", icon='PLAY')
    else:
        layout.label(text="Kanvas Active", icon='CHECKMARK')

@bpy.app.handlers.persistent
def ensure_kanvas_protection(dummy):
    """Ensure all Kanvas trees are protected from Purge on file load."""
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'KanvasNodeTree':
            tree.use_fake_user = True

def register():
    auto_load.register()
    
    # Manual fallback for Scene properties to prevent AttributeError if auto_load fails partially
    if not hasattr(bpy.types.Scene, "kanvas_settings"):
        from . import properties
        properties.register()

    bpy.types.NODE_HT_header.append(draw_kanvas_header)
    bpy.app.handlers.load_post.append(ensure_kanvas_protection)

def unregister():
    if ensure_kanvas_protection in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(ensure_kanvas_protection)
    bpy.types.NODE_HT_header.remove(draw_kanvas_header)
    auto_load.unregister()
    
    if hasattr(bpy.types.Scene, "kanvas_settings"):
        from . import properties
        properties.unregister()
