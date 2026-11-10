# References in the 3D View

Send images from your board to the 3D View, in two ways:

- **Reference Image:** an image in the scene, facing a view. Use it for blueprints (a front and a side view) or a sketch to model over.
- **Overlay:** the image drawn over the 3D View, on top of whatever you are working on, like a tracing sheet. Use it to compare a silhouette, check proportions, or match a camera to a photo.

Both are **live** by default: Kanvas draws them straight from the board, so when you edit the image in Kanvas (its mask, brightness, flips...) the 3D View follows at once, with the same colors as the board.

Both show the image as you edited it in Kanvas, so a masked cutout arrives without the hidden part around it.

## Sending images

1. Select one or more images on the board.
2. Right-click and choose **Send to 3D View...**, or click **Send to 3D View...** at the bottom of the **Image** tab of the **Selection** panel.
3. At the top of the dialog, choose **Reference Image** or **Overlay**.
4. Set the options, then click **OK**.

Reference images are placed at the **3D cursor**, in a collection called **Kanvas References**.

With several images selected as reference images, each one gets the next view of a blueprint set: Front, Right, Top, Back, Left, Bottom. The active image gets Front. Uncheck an image to leave it out, or pick its view from the list.

### Reference image options

| Option | Default | What it does |
| --- | --- | --- |
| **Live** | On | Kanvas draws the reference from the board, so edits show at once. Off, the picture is saved as an image file instead (see [Live or image file](#live-or-image-file)) |
| **View** | Front, Right, ... | Which view the reference faces: **Front**, **Back**, **Right**, **Left**, **Top**, **Bottom**, or **Current View** (the angle of the 3D View now) |
| **Real Scale** | On | Shown for images that have a [scale](measure.md#scale). The reference gets the size the image has in real life, so the element you marked comes out as big as you said. **Size** is then not used |
| **Size** | 5 m | Length of the longer side of the image in the scene |
| **Type** | Reference | **Reference** is hidden behind objects in front of it (in X-ray the part behind them shows through, as faintly as the objects are solid), **Background** is drawn behind everything, **In Front** over everything |
| **Opacity** | 1 | Below 1, the reference lets the scene show through |
| **Only Axis Aligned** | Off | The reference shows only when you look straight along its axis (for example, a Front reference only in the front view), as in a blueprint. It then hides as soon as you orbit, in perspective too. Off, as with Blender's own reference images, it shows from every angle. Not used with **Current View** |
| **Show in Perspective** | On | Also show the reference in perspective views, not only orthographic ones |
| **Crop to Mask** | On | Only the part of the image its mask shows. Off, the reference is the image's [bounds](masks.md#fitting-the-bounds-to-the-mask): the whole image, or the part it was fitted to |
| **Keep Stretch and Shear** | Off | Keep the stretch and shear the image has on the board, for when they are edits of the image itself |
| **Color Markup** | Off | Paint the image's color markup over it, whether or not the board shows it |

### Overlay options

| Option | Default | What it does |
| --- | --- | --- |
| **Opacity** | 0.5 | How much of the scene shows through |
| **Size** | 0.5 | Height of the overlay as a share of the height of the 3D View |
| **Anchor** | Center | Where the overlay sits: the middle or a corner of the 3D View. It is placed in the whole editor, so opening or closing the toolbar (`T`) or the sidebar (`N`) never moves it |
| **Show In** | Any View | Which 3D Views show the overlay: any, only perspective ones, only orthographic ones (Front, Top...), or only when you look through the camera |
| **Fit to Camera** | Off | When you look through the camera, the overlay fits inside the camera frame, whatever its size and anchor |
| **Keep Stretch and Shear** | Off | The overlay has the stretch and shear the image has on the board, for when they are edits of the image itself |
| **Crop to Mask** | On | Only the part of the image its mask shows |
| **Color Markup** | Off | Show the image's color markup, whether or not the board shows it |

### What the picture shows

The picture is the image as it looks on the board: brightness, contrast, saturation, tint, value view, flips and mask are kept. Its place, rotation, scale and opacity on the board are left out, so the reference is upright and at the image's own resolution.

## The Kanvas tab of the 3D View

The **Kanvas** tab of the 3D View sidebar (`N`) lists the references of the scene in the **References** panel.

- Click a row to select its reference in the scene. The eye shows or hides a reference or an overlay.
- **Hide Overlays**, above the list, hides every overlay at once; click again to show them.
- **Update Reference** (the refresh button) makes the picture of a reference saved as an image file again from the image on the board. **Update All References** does it for every one of them. Live references and overlays need no update.
- **Show in Kanvas** (the magnifier) selects the image on its board and frames it in an open Kanvas editor.
- **Remove Reference** (the trash button) deletes the reference from the scene, or the overlay from the view. The image stays on the board.
- **Settings**, closed at first, has the options of the active row:
  - For a reference image: its size (or **Real Scale**), opacity, depth and visibility, how its picture is made (**Crop to Mask**, **Stretch and Shear**, **Color Markup**), and **Save as Image File** or **Make Live**. A live reference follows these at once; one saved as a file needs **Update Reference**.
  - For an overlay: **Adjust in the View**, opacity, size, anchor, offset, **Flip**, **Show In**, **Fit to Camera**, **Crop to Mask**, **Stretch and Shear** and **Color Markup**.

A row whose image was deleted from the board is marked **Not on the board**. A reference image keeps working in the scene but can no longer be updated; an overlay stops showing until you remove it.

A reference you delete in the 3D View leaves the list on its own.

To hide the Kanvas tab, turn off **3D View References Panel** in **Preferences > General > Interface**.

## Placing an overlay

Turn on **Adjust in the View** in the overlay's **Settings**. A blue frame appears around the overlay:

- Drag inside the frame to move the overlay.
- Drag the square at its top right corner to scale it.
- Right-click or press `Esc` during a drag to cancel it.

Turn **Adjust in the View** off when you are done. While it is off, the overlay ignores the mouse, so you can click and select objects under it. You can also type the **Offset** and **Size** in the panel.

**Flip** mirrors the overlay from left to right, the classic way to see proportions with fresh eyes. **Show In** keeps the overlay out of the views it is not meant for; **Camera** goes well with **Fit to Camera**.

## Live or image file

A **live** reference is an image empty like any other: you select, move, rotate and scale it, and set its **Size**, **Offset**, opacity and depth in the Object properties as usual. It holds a placeholder image with the proportions of the picture (named `.Kanvas Ref ...`, hidden from image lists), and Kanvas draws the picture on it. Live references are drawn from the farthest to the nearest for the view you have, so a nearer picture covers a farther one from either side (by the distance of their middle; **Background** ones first, **In Front** ones last). The placeholder is clear to the eye (a 2% veil), but Blender does not select an image empty by pixels that are fully clear, so you can click anywhere on the picture to select it, not only on its frame. The placeholder is a generated image, so it adds nothing to the file and never asks to be saved.

Live references keep the colors of the board. An image file on an empty is shown through the scene's view transform (AgX by default), which makes it look washed out; a live reference is not.

Choose **Save as Image File** in **Settings** when the reference must work without Kanvas, for example in a file you send to someone who does not have the add-on: the picture becomes a PNG, which no longer follows the board until you click **Update Reference**. **Make Live** turns it back. Without Kanvas, a live reference shows nothing.

## Where the pictures are stored

Overlays and live references store no picture: they draw the image from the board. For references saved as image files:

- In a saved `.blend` file, each picture is written as a PNG to a `references` folder inside the **Assets Folder** (by default `//assets/kanvas/references`), and the reference loads it from there.
- In a file that was never saved, the picture is packed into the `.blend` file.

Updating a reference rewrites its picture in place.

## Related pages

- [Image masks](masks.md)
- [Exporting a picture](export-image.md), which can save the same picture as a PNG with **Area** set to **Image**
- [Preferences](preferences.md)
