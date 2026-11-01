# Images

This page explains how images get onto the board, where Kanvas keeps them, and how to manage the files.

## Adding images

| Method | Notes |
| --- | --- |
| Drag files onto the canvas | One or many files. Supported formats are PNG, JPG/JPEG, TGA, TIF/TIFF, WebP, and EXR |
| **Add > Image** | Choose one file |
| **Add > Multiple Images** | Choose several files at once |
| `Ctrl + V` over the canvas | Pastes copied image files, copied image pixels (Windows), or a copied file path (see [Pasting](#pasting)) |
| **Add > PureRef Scene (.pur)** or drag a `.pur` file | Imports a PureRef board (see [PureRef scenes](#pureref-scenes)) |

When you add several images at once, Kanvas loads them one after another, selects the new images, and arranges them when the batch finishes. Press `Esc` to stop pending files. Images that already loaded stay on the board.

## Pasting

Press `Ctrl + V` with the pointer over the canvas. The new items are placed at the pointer, or at the center of the view when the pointer is outside the canvas. Pasting is disabled while you edit a mask or colors.

What can be pasted depends on your system:

| Clipboard contents | Windows | macOS and Linux |
| --- | --- | --- |
| Image files copied in the file manager | Yes | Not read directly. Copy the file's **path** as text instead |
| Image pixels (a screenshot or "Copy image") | Yes | Not supported yet |
| A local file path as text, one per line | Yes | Yes |

Web addresses (`http://` or `https://`) are not downloaded. If nothing is pasted, save the image to disk and drag the file onto the canvas.

> If you drop an image onto a frame, it attaches to that frame automatically. See [Frames](frames.md).

## Where images are stored

By default, Kanvas does not point at your original file. It makes an optimized copy, so the board stays light and still works if you move or delete the original.

With **Auto-Copy to Assets** and **Optimization** on (the defaults), each import does the following:

1. Reads the original image.
2. Reduces its resolution if it is larger than the **Max Resolution** limit, keeping the aspect ratio.
3. Saves a **WebP** copy in the **Assets Folder**.
4. Loads that copy for display.

The original file is never modified.

The default Assets Folder is `//assets/kanvas`. In Blender, `//` means a path relative to the `.blend` file, so a project saved as `MyProject/scene.blend` keeps its copies in `MyProject/assets/kanvas/`. You can set an absolute path instead.

> **Save your `.blend` before importing** when Auto-Copy is on. A relative folder can only be resolved once the file has a location.

| Auto-Copy | Where the displayed pixels live |
| --- | --- |
| **On** (default) | WebP files in the assets folder |
| **Off** | Packed inside the saved `.blend` file. No external files are created |

Both settings are in **Preferences > General > Storage & Workflow**.

## Resolution and memory

**Max Resolution** limits the longest edge of new images:

| Option | Effect |
| --- | --- |
| 720p, 1080p (default), 2K | Longest edge limited to 720, 1080, or 2048 pixels |
| Original (No Limit) | Keeps the original size |

Smaller images are not enlarged. A 4000 × 2000 image becomes 1080 × 540 at the default limit.

With **Force 8-bit Depth** on, HDR and float sources are converted to 8 bits before they are packed. Turn it off to keep float depth when Auto-Copy is off. The WebP copies made by Auto-Copy are always 8-bit.

Turning **Optimization** off keeps the original dimensions, but Auto-Copy still saves a WebP copy.

These settings apply to **new** imports. They do not rebuild images already on the board. To re-import one reference with the current settings, use **Reload Image Source**.

## Managing an image

Select an image and use the controls in the **Selection** panel.

| Command | What it does |
| --- | --- |
| **Open Image Source** | Opens the original file or URL that Kanvas recorded |
| **Reload Image Source** | Reads the original again and rebuilds the reference with the current import settings. Position, rotation, appearance, and displayed size are kept. The original file must still exist |
| **Replace Image** | Chooses a different file for the same reference. Position, displayed size, rotation, opacity, and frame attachment are kept, and the new file becomes the recorded source |
| **Clear Image GPU Cache** | Frees the texture used for drawing. It does not read any file and is rebuilt when needed |

## Missing files and relinking

If images stored outside the `.blend` go missing, the item list shows how many.

- **Relink** asks for a folder and finds missing files by name in it. It can fix many images at once. Images packed into the `.blend` are skipped.
- **Replace Image** is the way to point one reference at a file with a different name.

## Sharing or moving a project

With Auto-Copy on, move the `.blend` together with its assets folder and keep the folder structure. The WebP copies are external files, and they are not packed automatically.

Keep your original images if you may want to re-import them at a different quality. The recorded source path can stop working if the original moves or lives on another computer.

To make a single self-contained file, turn **Auto-Copy** off before importing, so images are packed into the `.blend`.

## PureRef scenes

Use **Add > PureRef Scene (.pur)** to import a compatible PureRef board. This importer is experimental.

- Embedded PNG and JPG images are **packed into the `.blend`**, even when Auto-Copy is on. Repeated references share one image.
- Position, scale, rotation, opacity, and lock state are copied where the file provides them.
- Simple notes from older scenes become text cards.
- It has been checked against real PureRef 1.10, 2.1.1, and 2.1.3 files.
- Rich text formatting, groups, drawings, linked images, and some crop details are **not** converted. Kanvas reports how many items or details were skipped and lists them in the Blender console.

Importing never changes the `.pur` file, so keep it as your source.

## Image names in Blender

Kanvas keeps the images it uses out of Blender's image pickers. It does this by starting the datablock names with a dot, which Blender hides from selection lists. This covers your pictures, the generated mask and color layers, and the add-on's icon textures.

- They are still visible in the Outliner under **Blender File > Images**.
- To see and use the normal names, turn off **Hide Kanvas Images in Blender Lists** in **Preferences > General > Interface**. The names are restored.

## Good to know

- WebP copies are tied to the source path, the content, the output size, and the conversion options. Two different sources are never merged just because their names and sizes match.
- WebP copies are meant for visual references. Keep the originals when you need the full image data.

## Next

- [Selecting and transforming](transforms.md)
- [Performance and memory](performance.md)
