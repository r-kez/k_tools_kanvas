# Exporting a picture

Save a PNG of your board: to share a mood board, put a diagram in a document, or use shapes as a texture in Blender.

Right-click on the canvas and choose **Export Image...**. Pick where to save the file, then set the options in the file browser's side panel.

## Options

| Option | What it does |
| --- | --- |
| **Area** | **Selection**: around the selected items and arrows (the default when something is selected). **Whole Board**: around every visible item and arrow. **View**: exactly what the editor shows now. **Image**: the active image alone, upright and at its own resolution (the default when one image is selected). See [Exporting one image](#exporting-one-image). |
| **Only Selected** | With **Selection**: draw only the selected items and the arrows between them, on their own. A selected frame or group brings what is inside it; an item inside a frame comes out without the frame, so the background stays transparent. On by default. Turn it off to get everything inside the area, like a crop of the board. |
| **Crop to Mask** | A masked image counts only for the part its mask shows, so the picture has no transparent margin where the mask hides the image. On by default. Not shown for **View**. |
| **Keep Stretch and Shear** | With **Image**: keep the stretch and shear the image has on the board, for when they are edits of the image itself, such as a corrected aspect ratio. Off by default: the picture has the proportions of the image file. |
| **Color Markup** | With **Image**: paint the image's color markup over it. Off by default. |
| **Scale** | Pixels per canvas unit. At 1, items have the size they have on the canvas at 100% zoom; at 2 the picture is twice as sharp. For **View**, 1 is the size of the editor on screen. For **Image**, pixels per image pixel: 1 is the size of the image itself. The resulting size in pixels is shown below. |
| **Margin** | Empty space around the picture, in pixels |
| **Background** | **Transparent** (the default) keeps transparency around and through the items. **Canvas** uses the color of the canvas. **Color** uses a color you choose. |
| **Load into Blender** | Also adds the picture to the `.blend` file as a packed image, ready to use as a texture in a material. Off by default. |

## What goes into the picture

The picture is drawn exactly like the canvas: images with their adjustments, masks and color markup, shapes with gradients, text cards and checklists, frames and their titles, arrows and their labels, color names, and Blender annotations.

Everything that belongs to the interface stays out: selection outlines and handles, the resize grip of cards, the edit button, gradient handles, the editing focus, the canvas grid and axes, badges and buttons. The selection is cleared only while the picture is drawn and comes back right after.

With **Selection** and **Only Selected**, only the selection is drawn (Blender annotations, which belong to no item, stay out). With **Whole Board**, **View**, or **Only Selected** off, everything inside the area is in the picture. Hidden items never show.

## Exporting one image

With **Area** set to **Image**, the picture is the active image as you edited it in Kanvas, not its place on the board:

- **Kept:** brightness, contrast, saturation, tint, value view, flips and the mask (and the color markup with **Color Markup** on).
- **Left out:** where the image is on the board, its rotation, scale and opacity, and its stretch and shear unless **Keep Stretch and Shear** is on. The picture is upright, at the image's own resolution and fully opaque. A kept shear gives a slanted picture with transparent corners.
- With **Crop to Mask**, the picture is only as large as the part the mask shows: a cutout comes out without the hidden part around it.

If the mask hides the whole image, there is nothing to export.

## Size limits

A picture can be up to 16384 pixels on a side. Large pictures are drawn in pieces of 4096 pixels and joined, so they never need more graphics memory than that. If the size shown in red is too large, lower the **Scale**.

## Related pages

- [Shapes](shapes.md), including gradients
- [Interface and navigation](interface.md#right-click-menu)
