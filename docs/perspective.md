# Straightening perspective

A photo of a wall, a sheet of paper or a screen taken at an angle shows a rectangle as a slanted four-sided shape. **Perspective** straightens it: you drag four corners onto the corners of something that is really a rectangle, and the image shows that rectangle upright.

Nothing of the image is lost. The corners are stored on the item, the file is untouched, and **Show Original** gives the photo back.

## Straightening an image

1. Select the image and open the **Perspective** tab of the Selection panel.
2. Turn on **Edit Corners**. The image shows as it is in the photo, with four handles over it.
3. Drag each handle onto a corner of the rectangle (a wall, a door, a page). The orange edge is the **bottom** of the straightened image; **Turn Corners** passes each corner to the next one if the image comes out turned.
4. Click **Straighten**. The image shows as that rectangle, upright.

**Show Original** brings the photo back, in the same place. **Reset** puts the corners back inside the image.

**Show Whole Image** shows all of the photo straightened, not only the rectangle. What lies beyond the photo is clear, and the rectangle stays where it was. The picture is kept within two rectangles of the rectangle, since the parts of a photo near its horizon would otherwise stretch to infinity.

While **Edit Corners** is on, and while you edit the mask or the color markup, the image shows as it is in the photo, since that is where the mask and the markup are painted. When you finish, the straightened image comes back. Closing the Perspective tab also ends the edit.

## Proportions

A straight rectangle needs to know how wide it is compared to its height. Before you straighten, the tab shows an estimate made from the corners, assuming the photo was taken with a normal camera aimed at the middle of the image (no crop, no shift lens): in that case it is exact. **Straighten** keeps that number. After that, moving a corner leaves the proportions alone, so the image does not stretch as you refine the corners. Type another number for the proportions yourself (for example 1.414 for an A4 sheet, or the measures of a door), or press the dropper to estimate them again from the corners as they are now.

## What follows the correction

The straightened image is an ordinary item, only its box is the rectangle:

- selecting, moving, scaling, rotating, flipping, snapping, aligning and frames work on the rectangle;
- the **mask** and the **color markup** stay painted on the photo and follow the correction;
- **marks** stay on the same spot of the photo and now read lengths on the straightened plane, so a line along a door gives the real height of the door once you give it a scale (see [Measuring](measure.md));
- [Export Image](export-image.md) and the [3D View](references-3d.md) take the straightened picture.

## Limits

- A cropped image (see [Fit Bounds to Mask](masks.md#fitting-the-bounds-to-the-mask)) cannot be straightened: press **Reset Bounds** first. A straightened image cannot be fitted to its mask either.
- The corners have to make a convex four-sided shape, with no crossed sides. A handle that would cross them stops at the last good place.
- The corners stay inside the image.
- Comparison cards show the photo, not the straightened image.
