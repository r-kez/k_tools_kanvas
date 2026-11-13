# Preferences

Open **Edit > Preferences > Add-ons > K-Tools: Kanvas**. The settings are grouped in four tabs: **General**, **Controls**, **Aesthetics**, and **About**.

Preferences are global. They apply to every board and every file.

## General

### Storage & Workflow

| Setting | Default | What it does |
| --- | --- | --- |
| **Assets Folder** | `//assets/kanvas` | Where Auto-Copy stores image copies. `//` means next to the `.blend` file. You can use an absolute path |
| **Auto-Copy to Assets** | On | Saves a WebP copy of each imported image in the assets folder. When off, images are packed into the `.blend` |

See [Images](images.md) for how these work together.

### Images on the Board

| Setting | Default | What it does |
| --- | --- | --- |
| **Import Size** | 500 | The longest edge of an image on the board when it comes in (Original, 300, 500, 800 or 1200), so a big picture does not dwarf notes, checklists and frame headers. Only the **Scale** changes, never the pixels, so zooming and scaling up stay sharp. A smaller image keeps its size |
| **Reset Scale to Import Scale** | On | `Alt + S` puts an image back to the Scale it got on import. Off, it goes to 100% of its pixel size |

### Memory Optimization

| Setting | Default | What it does |
| --- | --- | --- |
| **Optimization** | On | Reduces new images before storing them to save memory |
| **Max Resolution** | 1080p | Longest edge of new images: 720p, 1080p, 2K, or Original (No Limit). Shown when Optimization is on |
| **Force 8-bit Depth** | On | Converts HDR and float sources to 8 bits. Shown when Optimization is on |
| **Texture Memory Budget (MB)** | 2048 | How much estimated GPU memory Kanvas may keep loaded. Above it, the least recently used images are released |
| **Mask Resolution** | Image | Resolution of image masks on the canvas: the image's own size (up to 4096), 4096, 2048, 1024 or 512 pixels on the longer side. Higher keeps mask edges sharp on large images. See [Masks](masks.md#mask-resolution) |

### Shapes

| Option | Default | What it does |
| --- | --- | --- |
| **Shape Fill** | Exact (Delaunay) | How the inside of shapes is filled. **Exact** fills every shape correctly, also outlines that cross themselves or each other (combined shapes that overlap). **Fast** uses Blender's quick polygon filler, which may fill crossing outlines wrongly. The same method is used for every shape. The difference in speed only shows while editing very large shapes: about 20 against 16 ms to rebuild a shape of 1920 vertices |

See [Performance and memory](performance.md) for guidance.

### Interface

| Setting | Default | What it does |
| --- | --- | --- |
| **Show Debug Panel** | Off | Shows the **Debug** panel in the sidebar |
| **3D View References Panel** | On | Shows the **Kanvas References** panel in the 3D View sidebar while the scene has [references](references-3d.md) sent from Kanvas |
| **Show Text Card Edit Button** | On | Shows the pencil button on cards and checklists |
| **Show Edit/Move Overlay** | On | Shows the **Edit \| Move** switch at the top of the canvas |
| **Edit/Move Switch in the Panel** | Off | Repeats the **Edit \| Move** switch at the top of the **Kanvas** sidebar panel |
| **Hide Kanvas Images in Blender Lists** | On | Keeps the images Kanvas uses out of Blender's image pickers (see [Images](images.md#image-names-in-blender)) |

### Auto Select

Install and download buttons for the optional segmentation feature, with the amount of space it uses and a button to remove it. See [Auto Select](auto-select.md).

## Controls

### Navigation and gestures

| Setting | Default | What it does |
| --- | --- | --- |
| **Select with Background Drag** | On | A plain left drag on the canvas, including a frame body, starts a box selection |
| **Keep Alt + Drag Selection** | On | An `Alt` + left drag also starts a box selection |
| **Shear Modifier** | `Alt` | The key to hold on an edge handle to shear an image |
| **Scroll Text Cards with Wheel** | Selected Cards | **Selected Cards**: the wheel scrolls a long card only while it is selected. **Any Hovered Card**: any scrollable card under the pointer, which also stops zooming while the pointer is over one. **Off**: the wheel always zooms |

### Scroll wheel modifiers

| Setting | Default | What it does |
| --- | --- | --- |
| **Opacity Scroll Modifier** | `Ctrl` | Hold while scrolling to change image opacity |
| **Scale Scroll Modifier** | `Shift` | Hold while scrolling to scale the active image |
| **Layer Scroll Modifier** | `Alt` | Hold while scrolling over an item to move it up or down the stack (the item list) |

Inside a Kanvas Tree these replace Blender's own use of the wheel with a modifier (sideways and vertical scrolling, and stepping through frames). Outside a Kanvas Tree nothing changes.

### Keymap shortcuts

Every Kanvas shortcut can be reassigned here. The list uses Blender's normal keymap editor, so it supports rebinding, disabling, and restoring defaults. A **Controls Reference** at the bottom of the tab summarizes the main gestures.

Shortcuts only work inside a Kanvas Tree. See the [keyboard and mouse reference](shortcuts.md).

## Aesthetics

### Canvas Style

Choose how cards, frames, selection outlines, and canvas controls are drawn.

| Style | Look |
| --- | --- |
| **Classic** | Flat, simple surfaces. The default |
| **Studio** | Rounded corners with soft shadows and accent lines |
| **Glass** | Translucent surfaces with subtle highlights. Glass does not blur what is behind it |

### Editing Focus

| Option | Default | What it does |
| --- | --- | --- |
| **Focus While Editing** | On | Dims the rest of the canvas while you edit an image's Mask or Color, or a shape's vertices, so the edited item stands out. The mode's badge, shortcut panel and brush stay bright |
| **Dim** | 0.55 | How dark the rest of the canvas becomes |
| **Desaturate Other Images** | Off | While editing, shows the other images with less color, so the edited one stands out by its color too. Only the display changes: each image keeps its own **Saturation**, and nothing is changed in the file |
| **Amount** | 1.0 | How much color the other images lose (1 is grey) |

### Canvas Axes

| Option | Default | What it does |
| --- | --- | --- |
| **Axis Lines** | On | Draws the X and Y lines through the canvas origin, from one edge of the view to the other at any zoom. Turn it off for a clean background |
| **X Axis Color**, **Y Axis Color** | Red, green | Color and opacity of each line |

### Canvas text

| Setting | Default | What it does |
| --- | --- | --- |
| **Soft Text Shadow** | On | Adds a subtle contrast halo behind card text, frame titles, and arrow labels |
| **Shadow Strength** | 50% | 0 to 100%. At 50% it matches the original soft shadow, and 100% is fully opaque |
| **Shadow Spread** | Tight | **Tight**, **Wide**, **Outline**, or **Diffuse**. Diffuse is the broadest and uses extra passes only on large letters |
| **Diffuse Reach** | 1.0 | Size of the Diffuse shadow |

### Arrows

| Setting | Default | What it does |
| --- | --- | --- |
| **Arrow Style** | Filled | **Filled** or **Rounded Stroke**. Applies to every arrow |

### Canvas background and grid

| Setting | Default | What it does |
| --- | --- | --- |
| **Solid Background** | Off | Covers Blender's background in Kanvas Trees only |
| **Background Color** | Dark | Color of the solid background |
| **Grid Lines** | Off | Draws square guide lines aligned with the dots of the Node Editor |
| **Grid Color** | Gray | Color and opacity of the grid |

### Axes, selection, and handles

| Setting | What it does |
| --- | --- |
| **X Axis Color**, **Y Axis Color** | Colors of the origin axes. The axes are drawn when **Show Grid** is on in the **Debug** panel |
| **Selection Color** | Color of selected outlines and transform handles |
| **Outline Thickness** | Thickness of selected image outlines, in screen pixels (default 2) |
| **Gizmo Background** | Adds a subtle background behind transform icons for contrast |
| **Arrow Endpoint Handles**, **Arrow Curve Handle** | Colors of an arrow's handles when it is selected |

## About

A short description of the add-on, its author, and a quick start.

## Resetting

**Reset All Settings** in the **Debug** panel clears the current board and restores its settings to defaults. It affects board content, so use it with care.
