import bpy
import bpy.utils.previews
import os

_preview_collections = {}

def get_icon(name):
    """Get the icon ID for a custom icon in assets/icons/"""
    global _preview_collections
    
    pcoll = _preview_collections.get("main")
    if not pcoll:
        pcoll = bpy.utils.previews.new()
        _preview_collections["main"] = pcoll
        
    if name not in pcoll:
        addon_dir = os.path.dirname(os.path.dirname(__file__))
        icon_path = os.path.join(addon_dir, "assets", "icons", f"{name}.png")
        if os.path.exists(icon_path):
            pcoll.load(name, icon_path, 'IMAGE')
            
    if name in pcoll:
        return pcoll[name].icon_id
    return 0

def register():
    pass

def unregister():
    global _preview_collections
    for pcoll in _preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    _preview_collections.clear()
