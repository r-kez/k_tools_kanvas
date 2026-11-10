# References in the 3D View

Send images from your board to the 3D View as **reference images**: a front and a side view for a blueprint, a sketch to model over, a cutout to match. The reference shows the image as you edited it in Kanvas, so a masked cutout arrives without the hidden part around it.

## Sending images

1. Select one or more images on the board.
2. Right-click and choose **Send to 3D View...**, or click **Send to 3D View...** at the bottom of the **Image** tab of the **Selection** panel.
3. Choose a view for each image and set the options, then click **OK**.

The references are placed at the **3D cursor**, in a collection called **Kanvas References**.

With several images selected, each one gets the next view of a blueprint set: Front, Right, Top, Back, Left, Bottom. The active image gets Front. Uncheck an image to leave it out, or pick its view from the list.

### Options

| Option | Default | What it does |
| --- | --- | --- |
| **View** | Front, Right, ... | Which view the reference faces: **Front**, **Back**, **Right**, **Left**, **Top**, **Bottom**, or **Current View** (the angle of the 3D View now) |
| **Size** | 5 m | Length of the longer side of the image in the scene |
| **Type** | Reference | **Reference** is hidden behind objects in front of it, **Background** is drawn behind everything, **In Front** over everything |
| **Opacity** | 1 | Below 1, the reference lets the scene show through |
| **Only Axis Aligned** | On | The reference shows only when you look along its axis (for example, a Front reference only in the front view), as in a blueprint. Not used with **Current View** |
| **Show in Perspective** | On | Also show the reference in perspective views, not only orthographic ones |
| **Crop to Mask** | On | Only the part of the image its mask shows |
| **Keep Stretch and Shear** | Off | Keep the stretch and shear the image has on the board, for when they are edits of the image itself |
| **Color Markup** | Off | Paint the image's color markup over it |

The picture is the image as it looks on the board: brightness, contrast, saturation, tint, value view, flips and mask are kept. Its place, rotation, scale and opacity on the board are left out, so the reference is upright and at the image's own resolution.

## The Kanvas tab of the 3D View

The **Kanvas** tab of the 3D View sidebar (`N`) lists the references of the scene in the **References** panel.

- Click a row to select its reference in the scene. The eye shows or hides it.
- **Update Reference** (the refresh button) makes the picture again from the image on the board. Use it after editing the mask or the adjustments. **Update All References** does it for every reference.
- **Show in Kanvas** (the magnifier) selects the image on its board and frames it in an open Kanvas editor.
- **Remove Reference** (the trash button) deletes the reference from the scene. The image stays on the board.
- **Settings**, closed at first, has the size, opacity, depth and visibility of the active reference, and how its picture is made (**Crop to Mask**, **Stretch and Shear**, **Color Markup**). Change these, then click **Update Reference**.

A reference whose image was deleted from the board is marked **Not on the board**. It keeps working in the scene, but it can no longer be updated.

A reference you delete in the 3D View leaves the list on its own.

To hide the Kanvas tab, turn off **3D View References Panel** in **Preferences > General > Interface**.

## Where the pictures are stored

- In a saved `.blend` file, each picture is written as a PNG to a `references` folder inside the **Assets Folder** (by default `//assets/kanvas/references`), and the reference loads it from there.
- In a file that was never saved, the picture is packed into the `.blend` file.

Updating a reference rewrites its picture in place.

## Related pages

- [Image masks](masks.md)
- [Exporting a picture](export-image.md), which can save the same picture as a PNG with **Area** set to **Image**
- [Preferences](preferences.md)
