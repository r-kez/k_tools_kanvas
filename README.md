# Kanvas

**Kanvas is a reference board inside Blender.** It turns the Node Editor into an infinite canvas where you collect images, write notes, group ideas, and mark up references, all saved in your `.blend` file.

Requires **Blender 4.2 or newer**. The core add-on needs no extra software.

## What you can do

- **Collect references.** Drag in images, paste them, or import a PureRef board. Keep optimized copies next to your project, or pack everything into the `.blend`.
- **Organize.** Move, rotate, scale, stretch, and shear images. Align, distribute, and pack them. Group items in nested frames that resize to fit, and stack them in the item list, which is the drawing order.
- **Take notes.** Add text cards with Markdown, and checklists with progress. Connect items with arrows.
- **Draw diagrams and vectors.** Add shapes, or draw free paths with the pen, with curves, holes, rounded corners and line styles. Join, cut and intersect shapes, and drag SVG files in or export shapes as SVG.
- **Mark up images.** Hide parts of an image with masks. Paint named color regions to plan work, link them to checklist tasks, mark tasks as done, and isolate one color at a time.
- **Model with your references.** Send images to the 3D View as reference images, cropped to their mask, as a single view or a blueprint set, and update them after editing. Export the board, the selection or one image as PNG.
- **Select a subject with one click.** The optional Auto Select tool uses a small segmentation model that runs locally. It is downloaded only when you choose to.
- **Stay in control.** Switch between **Edit** and **Move** modes so you can browse a board without changing it. Lock frames, hide items, and edit every shortcut.
- **Stay fast.** Boards with hundreds of images stay responsive, and Blender's auto save keeps working.

## Quick start

1. Install the add-on from **Edit > Preferences > Add-ons > Install from Disk**, and enable **K-Tools: Kanvas**.
2. Change an editor to **Kanvas Tree** and click **New**.
3. Save your `.blend` file, then drag images onto the canvas.
4. Press `N` and open the **K-Tools** tab for the controls.

## Documentation

The full documentation is in the [`docs`](docs/index.md) folder:

- [Getting started](docs/getting-started.md)
- [Interface and navigation](docs/interface.md)
- [Images](docs/images.md), [Selecting and transforming](docs/transforms.md), [Arranging items](docs/arranging.md)
- [Frames](docs/frames.md), [Groups](docs/groups.md), [Text cards and checklists](docs/text-cards.md), [Arrows](docs/arrows.md), [Shapes](docs/shapes.md)
- [Image masks](docs/masks.md), [Color Markup](docs/color-markup.md), [Auto Select](docs/auto-select.md)
- [Preferences](docs/preferences.md), [Keyboard and mouse reference](docs/shortcuts.md)
- [Performance and memory](docs/performance.md), [Troubleshooting](docs/troubleshooting.md)

## Status

Kanvas is under active development. The [TODO](TODO.md) lists work in progress, and not every planned item is available yet.

## Credits and license

Developed by Robert Kezives. Licensed **GPL-3.0-or-later**.

Third-party material used by optional features:

- Some interface icons are rasterized from [Tabler Icons](https://github.com/tabler/tabler-icons) (MIT). See `assets/icons/tabler/`.
- Auto Select uses [MobileSAM](https://github.com/ChaoningZhang/MobileSAM) and Meta's [Segment Anything](https://github.com/facebookresearch/segment-anything) decoder, in ONNX form (Apache-2.0), and [ONNX Runtime](https://github.com/microsoft/onnxruntime) (MIT). None of them is bundled. They are downloaded only if you choose to.
