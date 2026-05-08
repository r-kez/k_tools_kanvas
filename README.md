# Kanvas 🎨

Kanvas is a professional, high-performance reference image engine for the Blender Node Editor. It allows users to overlay, manipulate, and organize reference images directly within the node graph without blocking standard workflow.

## 🚀 Key Features

- **Passive Interaction Mode**: A background modal system that allows you to move images and nodes simultaneously.
- **12-Point Transformation Gizmos**: Advanced handles for Uniform Scale, Stretch, Rotation, and Shearing.
- **Post-Pixel Visuals**: Gizmos and outlines maintain a constant screen-space size regardless of viewport zoom level.
- **GPU Accelerated**: Blazing fast rendering using the Blender GPU API.
- **Automatic Depth Management**: Clicking an image automatically brings it to the foregroun

## 🖱️ Interaction & Shortcuts

To start interacting, toggle **INTERACTIVE MODE** in the Kanvas panel (Node Editor N-Panel).

### Selection
- **Left Click**: Select an image and bring it to front.
- **Click Empty Space**: Standard Blender node navigation (pass-through).

### Transformation Shortcuts (Active Image)
- `G`: Grab/Move image.
- `S`: Scale (Uniform).
- `R`: Rotate.
- `Alt + G`: Reset Location to (0,0).
- `Alt + S`: Reset Scale & Shear to defaults.
- `Alt + R`: Reset Rotation to 0.
- `Shift + D`: Duplicate active image.
- `X` or `Delete`: Remove active image.
- `ESC` or `Right Click`: Cancel current transformation.
- `Enter` or `Left Click`: Confirm transformation.

### Advanced Gizmo Controls
| Handle Type | Action | Description |
| :--- | :--- | :--- |
| **White Corners** | **Uniform Scale** | Scales the image while preserving aspect ratio. |
| **Pink Midpoints** | **Stretch** | Non-uniform scale (horizontal or vertical). |
| **Green Outer Handles** | **Rotate** | Rotate the image with a dedicated offset handle. |
| **Shift + Pink Mids** | **Shear** | Hold Shift while dragging midpoints to tilt/shear the image. |

## ⚙️ Configuration

Located in the Node Editor **N-Panel > Kanvas**:

- **Interactive Mode**: Toggle the background interaction engine.
- **Show Gizmos**: Globally show/hide transformation handles.
- **Scale/Rotate Toggles**: Individually enable/disable specific handle types.
- **Gizmo Size**: Adjust the pixel-size of the handles.
- **Opacity & Tint**: Control the visual appearance of each reference image.

## 📂 Technical Details

- **Icon Path**: `assets/icons/` (standardized PNGs).
- **Shader**: Custom GPU shader with Scene Linear to sRGB conversion for color accuracy.
- **State Management**: Persistent data stored per scene in `bpy.context.scene.kanvas_settings`.

---
*Developed by Robert Kezives*
