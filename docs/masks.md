# Image masks

A **mask** shows only part of an image. It is stored with the image item on the board, so each instance of an image can have its own mask. The original file is never changed.

## Editing a mask

1. Select an image.
2. Press `M`, or click **Edit Mask (M)** in the **Mask** tab of the **Selection** panel. **Use Mask** at the top of the tab turns the mask on or off.
3. Paint, draw, or select the parts you want to show.
4. Press `M` again to finish.

While you edit:

- A small indicator at the top of the canvas shows the active tool and whether you are revealing or erasing.
- A shortcut list at the lower left shows one action per row.
- `Enter`, `Esc`, or a right click finish editing, unless a shape is half-drawn (in that case the first press cancels the shape).

The **Mask** checkbox in the panel header shows or hides the mask. **Clear Image Mask** (the trash button) removes every mark from that image.

## Tools

Switch tools with `Tab`, or press `B` (Brush), `P` (Polygon), or `A` (Auto Select, once an image is analyzed). The panel has a button for each tool too.

### Brush

Paints freehand.

| Action | Result |
| --- | --- |
| Drag | Paint |
| `Shift + click` | Draw a straight line from the last point |
| `Shift + drag` | Straight line, snapped to 45° steps |
| `Ctrl + wheel` | Change the brush size |

The brush size is measured in pixels of the source image. You can also set it with the **Brush** slider (1 to 512).

### Polygon

Draws straight-edged shapes.

| Action | Result |
| --- | --- |
| Click | Add a vertex |
| `Shift` | Snap the next edge to 45° steps |
| Double-click, `Enter`, or click the first vertex | Close the shape (at least three vertices) |
| `Esc` | Cancel the unfinished shape. Press again to finish editing |

### Rectangle

Draws a rectangle by dragging.

| Action | Result |
| --- | --- |
| Drag | Draw a rectangle |
| Hold `Shift` | Constrain to a square |
| Hold `Ctrl` | Draw from the center |
| `Shift + Ctrl` | Square from the center |
| `Esc` | Cancel |

### Auto Select

Selects a subject with one click. It needs a one-time setup, described in [Auto Select](auto-select.md).

## Reveal and erase

By default, the tools **reveal** the image. To erase instead:

- Press `E` to switch between Reveal and Erase. This stays until you press `E` again.
- Hold `Alt` to use the opposite mode temporarily.

You can also use the **Erase** toggle in the panel.

## Navigating while you edit

| Action | How |
| --- | --- |
| Pan | Middle mouse drag |
| Zoom | Wheel, or `Ctrl` + middle mouse drag |

Panning and zooming never discard a half-drawn polygon.

## Undo and redo

`Ctrl + Z` undoes the last completed stroke or shape, and `Ctrl + Shift + Z` redoes it. When you finish editing, Blender treats the whole session as one Undo step.

## Good to know

- Brush marks, eraser marks, and polygons are applied **in the order you made them**, so a later mark can cover an earlier one.
- Edges use partial pixel coverage and linear filtering, so they stay smooth.
- The mask texture is capped at 512 pixels on its longest side, which keeps even very large images fast.
- Duplicating an image duplicates its mask.

## Next

- [Color Markup](color-markup.md)
- [Auto Select](auto-select.md)
