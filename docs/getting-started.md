# Getting started

This page takes you from installation to a working board.

## Requirements

- **Blender 4.2 or newer.**
- No extra software for the core add-on. Kanvas is written in Python and uses Blender's own libraries.
- A graphics card that can run Blender. Kanvas draws with the GPU, and large boards benefit from more video memory (see [Performance and memory](performance.md)).
- The optional [Auto Select](auto-select.md) feature downloads about 95 MB of additional files, only when you ask it to.

## Install

1. Open **Edit > Preferences > Add-ons**.
2. Choose **Install from Disk** (in the dropdown at the top right) and select the Kanvas package.
3. Enable **K-Tools: Kanvas**.

## Create your first board

1. Change any editor to the **Kanvas Tree** editor type, using the editor type menu in the top-left corner of the area.
2. In the editor header, click **New** to create a board.
3. Save your `.blend` file. Kanvas stores copies of your images next to the file by default, and that needs a saved location (see [Images](images.md)).

You can open the same board in two editors at once, and changes appear in both. You can also create several trees in one file, each with its own independent board.

## Add content

Everything is added to the board from one of these places:

| To add | How |
| --- | --- |
| Images | Drag image files from your file browser onto the canvas (they land where you drop them), or use **Add > Image** and **Add > Multiple Images** |
| Vector drawings | Drag `.svg` files onto the canvas, or use **Add > Shape > Import SVG...** |
| Pasted images | Copy an image file or image pixels, then press `Ctrl + V` over the canvas |
| A PureRef scene | Drag a `.pur` file onto the canvas, or use **Add > PureRef Scene (.pur)** |
| A note | **Add > Text Card** |
| A task list | **Add > Checklist** |
| A connection | **Add > Arrow**, then click the start and end points |
| A group | Select items and press `Shift + F`, or use **Add > Frame** |

The **Add** menu in the Kanvas Tree header lists all of these.

## Move around the board

- **Pan:** hold the middle mouse button and drag.
- **Zoom:** scroll the mouse wheel.
- **Frame what you selected:** press `Numpad .`.
- **Find your content:** if the board is outside the view, a **Recenter** button appears in the middle of the canvas. Click it.

If the middle mouse button is hard to use, switch to **Move mode**. In Move mode the left mouse button pans the canvas and nothing can be changed by accident. Press `Tab` to toggle between **Edit** and **Move**, or click the switch at the top of the canvas. See [Interface and navigation](interface.md).

## Work with the selection

- Click an item to select it. `Shift + click` adds to the selection.
- Drag on empty canvas to select with a box.
- Press `G`, `S`, or `R` to move, scale, or rotate. Click or press `Enter` to confirm, and `Esc` to cancel.
- Press `X` or `Delete` to remove the selection.
- Right-click an item for a menu of common actions.

The [selecting and transforming](transforms.md) page covers everything in detail.

## Next steps

- Learn the layout of the interface: [Interface and navigation](interface.md).
- Keep your references organized: [Frames](frames.md) and [Arranging items](arranging.md).
- Plan work over a reference: [Color Markup](color-markup.md).
- See every shortcut: [Keyboard and mouse reference](shortcuts.md).
