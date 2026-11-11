import os
import zipfile
import shutil
from pathlib import Path

# --- CONFIGURATION ---
# Detect paths relative to this script (assumes script is in ADDON_DIR/scratch/)
SCRIPT_DIR = Path(__file__).parent.resolve()
ADDON_DIR = SCRIPT_DIR.parent
# Where the zip will be saved (relative to ADDON_DIR)
BUILD_DIR = ADDON_DIR.parent / "builds"

# Files and folders to ignore
IGNORE_PATTERNS = {
    '.git',
    '.github',
    '.vscode',
    '__pycache__',
    '.gitignore',
    '.bak',
    '.bak2',
    'package_addon.py',
    'TODO.md',
    'scratch',
    'README.md',
    'RELEASE_NOTES.md',
    'mkdocs.yml',
    'requirements-docs.txt',
    'site'
}

IGNORE_EXTENSIONS = {
    '.pyc',
    '.pyo',
    '.bak',
    '.bak2'
}

def get_version():
    """Extract version from blender_manifest.toml"""
    manifest_path = ADDON_DIR / "blender_manifest.toml"
    if not manifest_path.exists():
        return "unknown"
    
    with open(manifest_path, 'r') as f:
        for line in f:
            if line.startswith('version ='):
                return line.split('=')[1].strip().replace('"', '')
    return "unknown"

def package_addon():
    version = get_version()
    addon_id = ADDON_DIR.name
    # Standard Extensions Platform naming convention: add-on-{id}-v{version}.zip
    zip_name = f"add-on-{addon_id.replace('_', '-')}-v{version}.zip"
    
    # Ensure build directory exists
    if not BUILD_DIR.exists():
        BUILD_DIR.mkdir(parents=True)
        print(f"Created build directory: {BUILD_DIR}")

    zip_path = BUILD_DIR / zip_name

    print(f"Packaging {addon_id} v{version}...")
    print(f"Target: {zip_path}")

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(ADDON_DIR):
            # Convert to Path object for easier handling
            root_path = Path(root)
            
            # Relative path from addon dir
            rel_path = root_path.relative_to(ADDON_DIR)
            
            # Filter directories
            dirs[:] = [d for d in dirs if d not in IGNORE_PATTERNS]
            
            for file in files:
                # Filter files
                if file in IGNORE_PATTERNS or any(file.endswith(ext) for ext in IGNORE_EXTENSIONS):
                    continue
                
                file_path = root_path / file
                # The path inside the ZIP should include the addon folder name as root 
                # (Standard Blender extension structure)
                archive_name = Path(addon_id) / rel_path / file
                
                zipf.write(file_path, archive_name)
                #print(f"  Added: {archive_name}")

    print("-" * 30)
    print(f"SUCCESS! Created: {zip_name}")
    print(f"Location: {zip_path}")

if __name__ == "__main__":
    package_addon()
