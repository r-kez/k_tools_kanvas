import bpy
import os
import shutil
from pathlib import Path

def copy_image_to_project(image: bpy.types.Image, target_subdir: str):
    """
    Copies the source file of a Blender Image to the project assets folder.
    Relativizes the path if successful.
    """
    if not image or not image.filepath:
        return False

    # 1. Check if the .blend is saved
    if not bpy.data.is_saved:
        return "ERROR: Save the .blend file first!"

    # 2. Get absolute paths
    src_path = Path(bpy.path.abspath(image.filepath))
    if not src_path.exists():
        return f"ERROR: Source file not found: {src_path}"

    # 3. Define target directory
    project_dir = Path(bpy.path.abspath("//"))
    target_dir = project_dir / target_subdir
    
    # Create target directory if it doesn't exist
    target_dir.mkdir(parents=True, exist_ok=True)

    # 4. Define target file path
    target_path = target_dir / src_path.name
    
    # 5. Check if it's already there (to avoid redundant copy)
    if src_path.resolve() == target_path.resolve():
        return True

    try:
        # 6. Copy file
        shutil.copy2(src_path, target_path)
        
        # 7. Update Blender image path and relativize
        image.filepath = bpy.path.relpath(str(target_path))
        image.reload()
        return True
    except Exception as e:
        return f"ERROR: Failed to copy file: {str(e)}"
