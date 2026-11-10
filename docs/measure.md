# Measuring and real scale

Draw lines and rectangles on an image and read how big things are. Tell Kanvas how big one thing really is (the wheel and tire of a car are 66 cm high) and every other mark on that image reads in real units. Send the image to the 3D View and it arrives at its real size.

Marks and scale live in the **Measure** tab of the **Selection** panel, for the active image.

## Marks

A **mark** is a line (two points) or a rectangle (two opposite corners).

1. Select an image and open the **Measure** tab.
2. Under **Marks**, click **Line** or **Rectangle**.
3. Drag on the canvas, from one end to the other. Release to finish.

While you drag, hold `Shift`:

- **Line:** keeps the line along the image's own axes or at 45°.
- **Rectangle:** makes it a square.

Press `Esc` during the drag to cancel it, or before it to put the tool away. A click without a drag draws nothing. Nothing keeps running while the tool waits, so Blender's auto save is never blocked.

Each mark is stored in the image's own coordinates. It follows the image when you move, rotate, scale, stretch or flip it, and when you crop it with a mask.

On the canvas, every mark shows its size in a small label: the length of a line, `width × height` for a rectangle. Marks are drawn on the canvas only: they are never part of an [exported picture](export-image.md).

### Editing a mark

While the **Measure** tab is open and the image is selected, every mark shows its handles on the canvas: a square at each end of a line and at each corner of a rectangle, and a diamond in the middle. Drag to edit:

| Drag | Result |
| --- | --- |
| An end of a line, or a corner of a rectangle | Moves that point (the rest stays) |
| A side of a rectangle | Moves that side |
| The middle, or the body of a line | Moves the whole mark |

- A click on a handle without a drag only makes that mark the active one.
- Hold `Shift` while dragging an end to keep the line along the image axes or at 45°, or a corner to keep the rectangle square.
- Press `Esc` or right-click during the drag to put the mark back as it was.
- The scale mark is edited the same way. Its real size stays what you said, so moving an end changes the scale: `1 px = ...` follows, and so do the other marks and the references in the 3D View.
- A mark cannot be dragged outside the image, or made so small it has no size.

Change the real size, the unit or the side (height or width) of the scale in the **Scale** box. Rename a mark by clicking its name in the list.

With the Measure tab closed, the handles are hidden and clicks move the image as usual.

### The list of marks

| Control | What it does |
| --- | --- |
| Name | Click to rename a mark |
| Size | What the mark reads now, in the unit of the board |
| Eye | Show or hide that mark |
| **-** | Remove the active mark |
| Trash | Remove every mark of the image, and its scale |
| **Show Marks on Canvas** | Show or hide all the marks of this image |

## Scale

Without a scale, marks read in **pixels** of the image.

To give an image a scale, mark something whose real size you know:

1. Under **Scale**, click **Line** or **Rectangle** and drag over that thing.
2. In the box that opens, enter its real size and unit. For a rectangle, say whether you give its **Height** or its **Width**.
3. Click **OK**.

The mark turns amber and gets a pin. The panel shows the result, such as `1 px = 0.3667 cm`. Every other mark of the image now reads in real units.

You can also pick any existing mark in the list and click **Use Active Mark as Scale**. To change the real size afterwards, edit the value and unit under **Scale**. **Clear Scale** takes the scale off (the marks go back to pixels). Removing the scale mark does the same.

Each image has one scale. Two copies of the same picture can have different ones.

For a good scale, mark the longest known distance you can find, and keep it in the same plane as what you want to measure: a photo taken at an angle is only accurate across the plane the scale mark lies on.

### Unit

**Unit** next to **Marks** sets the unit all the marks of the board read in: **mm**, **cm**, **m**, **in** or **ft**. It starts as the unit you gave the first scale, and changing it only changes how the marks are read.

## Real size in the 3D View

When you [send an image to the 3D View](references-3d.md) as a reference image, **Real Scale** makes the reference as big as the image is in real life. The marked wheel comes out 66 cm high in the scene, and so does the car around it.

- **Real Scale** is on by default for images that have a scale. Images without one use **Size**.
- The size takes the scene's **Unit Scale** into account (Scene properties > Units), so 66 cm is 0.66 units at the default scale and 66 units if a unit is a centimeter.
- It follows the picture: with **Crop to Mask**, the reference is as big as the part of the image the mask shows.
- A live reference follows changes at once: edit the scale or the mask in Kanvas and the reference in the 3D View resizes. A reference saved as an image file takes the new size when you click **Update Reference**.
- Turn **Real Scale** off in the reference's **Settings** to set the **Size** by hand.

Overlays are drawn over the screen, not in the scene, so they have no real size.

## Copying

Duplicating an image copies its marks and its scale.

## Related pages

- [References in the 3D View](references-3d.md)
- [Image masks](masks.md)
- [Color Markup](color-markup.md)
