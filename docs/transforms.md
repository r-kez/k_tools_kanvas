# Selecting and transforming

## Selecting

| To | Do this |
| --- | --- |
| Select one item | Click it |
| Add or remove an item from the selection | `Shift + click` |
| Select with a box | Drag on empty canvas. Hold `Shift` to add to the current selection |
| Select with a box, even starting on an item | Press `B`, then drag. Press `B` again or `Esc` to disarm |
| Select everything visible | `Ctrl + A` |
| Invert the selection | `Ctrl + I` |
| Select a covered image | Select it in the item list |

Selection works across images, text cards, frames, and arrows. Selected images show a colored outline.

> **Select with Background Drag** and **Keep Alt + Drag Selection** in **Preferences > Controls** decide whether a plain drag or an `Alt` drag starts a box selection. With both on, either works.

Locked items cannot be selected, and the box ignores them. Hidden items are not selectable either.

## Layers

The item list is the stacking order: the higher an item is in the list, the more it is in front on the canvas. Images and shapes mix freely, so a shape can sit behind an image or in front of it. A frame or a group carries everything inside it: moving it up or down moves its content with it, and inside it the items have their own order. New items come in at the top of the list, in front. Selecting, moving or transforming an item never changes the order. A click picks the item in front.

| To move the selected items | How |
| --- | --- |
| One step up (to the front) or down (to the back) | `Page Up` / `Page Down`, the ▲ ▼ buttons next to the list, or hold `Alt` and scroll over an item |
| In front of / behind everything at their level | `Shift + Page Up` / `Shift + Page Down`, or the top and bottom buttons next to the list |

Items move among the items of the same frame or group. Text cards and arrows are always drawn above images and shapes, and frames behind their content. The text inside a shape is drawn with the other canvas text, above every image: when an image covers a shape, the shape's text still shows through.

Select an item in the list to reach an image that is covered.

## Moving, rotating, and scaling

Use the on-canvas handles, or the keyboard.

### Handles (gizmos)

When one image is selected:

- **Corner handles** scale the image proportionally.
- **Edge handles** stretch it along one axis.
- The **circular handle** above the image rotates it.
- Hold `Alt` on an edge handle to **shear**. The handle color changes to show shear mode.

With several images selected, one set of handles appears around the whole selection and transforms them together.

Change the size of the handles, or hide scale and rotate handles, in the **Gizmos** panel. The modifier used for shear can be changed in **Preferences > Controls**.

### Keyboard

| Key | Action |
| --- | --- |
| `G` | Move |
| `S` | Scale |
| `R` | Rotate |

After pressing one, move the mouse. **Click or press `Enter`** to confirm. **Press `Esc`** to cancel and restore the original state. Moving a frame header moves everything attached to it.

### Precision while transforming

| Hold | Effect |
| --- | --- |
| `Shift` | Fine adjustment |
| `Ctrl` | Steps (increments). It also inverts snapping while you drag |
| `Ctrl + Shift` | Fine steps |

### Reset

| Shortcut | Action |
| --- | --- |
| `Alt + G` | Reset location |
| `Alt + S` | Reset scale and shear |
| `Alt + R` | Reset rotation |

The right-click menu also has **Reset Transform**. Resets apply to the selected, unlocked items. A group or frame resets with its contents: `Alt + G` moves it and everything inside so its middle sits on the origin, and `Alt + R` / `Alt + S` reset each image and shape inside where it stands (text cards never rotate, so they are left alone).

## Copying a style

**Copy Style** and **Paste Style** in the right-click menu copy the *look* of one item to others of the same kind, without touching position, size, or content:

| Kind | What is copied |
| --- | --- |
| Image | Opacity, color tint, brightness, contrast, saturation, color correction, and the value check (grayscale and posterize) |
| Text card or checklist | Text color, background color, opacity, and font size |
| Frame | Color, opacity, and header font size |

Select the item whose look you want, choose **Copy Style**, then select one or more items of the same kind and choose **Paste Style**. Locked items are skipped, and items of a different kind are left alone. Pasting is one Undo step.

## Duplicating, renaming, deleting

| Action | Shortcut |
| --- | --- |
| Duplicate every selected item and move the copies | `Shift + D` |
| Rename the active item | `F2` |
| Remove the selection | `X` or `Delete` |

`Shift + D` selects only the new copy and starts moving it, so the original stays in place. Duplicating an image does not create another image file.

**Arrows are copied with the diagram.** When both ends of an arrow are attached to items you duplicate, the copy gets its own arrow attached to the copies, with the same label, color, thickness, and style. Arrows with a loose end, or attached to an item you did not duplicate, are not copied.

## Snapping

Open the **Snap** panel. The checkbox in its header turns snapping on or off.

| Option | What it does |
| --- | --- |
| **Grid** | Snaps movement and transforms to a grid |
| **Edges** | Snaps edges and centers to other visible images |
| **Vertices** | In Edit Vertices, snaps a dragged vertex to the vertices of other shapes. Off by default |
| **Step** | Grid spacing in canvas units. Default 20 |
| **Threshold** | How close, in screen pixels, a snap target must be to attract. Default 10 |

Guide lines show the snap targets while you drag. Hold `Ctrl` during a drag to invert the snapping state for that gesture. Text cards also snap when you resize them with `Ctrl` held (see [Text cards](text-cards.md)).

## Image adjustments

Select one image, or several for batch changes, and open the **Selection** panel.

| Control | Effect |
| --- | --- |
| **Opacity** | See-through amount |
| **Color Tint** | Multiplies the image by a color |
| **Brightness** | 0 to 5. Default 1 |
| **Contrast** | 0 to 5. Default 1 |
| **Saturation** | 0 to 5. Default 1 |
| **Flip H / Flip V** | Mirror the image |
| **Color Correction** | Turns the color-space correction used when drawing on or off |
| **Grayscale** | Shows the image in gray tones, to check its values (light and dark) without color |
| **Posterize** | Reduces the image to 2 to 12 gray tones, to see the main shapes of light and shadow. 0 turns it off |

These change how the image is displayed on the board. The image file is untouched.

### Checking values

**Grayscale** and **Posterize** are a quick way to judge a reference the way painters and lighting artists do: if the shapes still read in three or four tones, the values work. They apply to the image only. Color regions from [Color Markup](color-markup.md) stay in color on top. With several images selected, the controls change all of them together. Both are off by default.

### Quick adjustments with the wheel

Scroll while holding a modifier:

| Modifier (default) | Effect |
| --- | --- |
| `Ctrl` + wheel | Opacity of the image under the pointer (or the active image) |
| `Shift` + wheel | Scale of the active image |
| `Alt` + wheel | Move the item under the pointer up or down the stack |

Each modifier can be reassigned in **Preferences > Controls**.

These shortcuts apply only over the canvas of a Kanvas Tree, and only when there is an image to act on. Everywhere else, and when there is no target, the wheel keeps Blender's usual behavior: `Ctrl` + wheel scrolls sideways, `Shift` + wheel scrolls up and down, and `Alt` + wheel steps through frames.

The plain wheel zooms the board, except over a long [text card](text-cards.md#resizing-and-long-text) that is selected, where it scrolls the card.

## Locking and hiding

Use the lock and eye icons in the item list.

- A **locked** item cannot be selected, moved, transformed, duplicated, or deleted.
- Locking a **frame** also locks every item inside it.
- A **hidden** item is not drawn and cannot be selected.

## Next

- [Arranging items](arranging.md)
- [Frames](frames.md)
