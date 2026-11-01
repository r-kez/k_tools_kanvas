# Color Markup

**Color Markup** lets you paint named colors over an image to plan work, call out parts, or track tasks. The colors sit on top of the image. They do not change its visibility mask, and the image file is never modified.

Each image keeps its own list of **color regions**. A region has a name, a color, an opacity, and the paint itself. Regions are saved with the image item, and duplicating the item copies them.

## The Markup panel

Select an image and open the **Markup** subpanel under **Selection**. The checkbox in its header shows or hides all colors on that image.

| Control | What it does |
| --- | --- |
| Region list | Every color region, with its color swatch, name, and an eye to hide it |
| **+** and **−** | Add or remove a region |
| Up and down arrows | Reorder regions. Regions linked to a checklist also reorder the tasks |
| Shuffle button | Give every region a new random color (see [Colors](#colors)) |
| **Opacity** | How strong the active region's color is |
| **Names** | Show each region's name on the image (see [Names](#names-on-the-image)) |
| **Isolate Color** | Show one region at a time (see [Isolating](#isolating-one-color)) |
| **Brush Size** and **Erase** | Settings for the painting tools |
| **Edit Colors** | Start painting |

## Colors from the image

The eyedropper button next to **Edit Colors** adds one color region for each **dominant color** of the image. Choose how many (2 to 12), and Kanvas creates a region for each, named with its hex code (for example `#D92626`), biggest areas first. Colors that are almost the same are merged, so a flat image may give fewer than you asked for.

The regions start empty. Paint them like any other region, or use them as a palette to pick from. The image file is never changed.

## Painting

1. Pick a region in the list.
2. Press `C`, or click **Edit Colors**.
3. Paint with a tool.
4. Press `C` to finish.

The tools are **Brush**, **Polygon**, **Rectangle**, and **Auto Select**. They work exactly like the mask tools, so see [Image masks](masks.md#tools) for each one. Switch with `Tab`, or press `B`, `P`, or `A`.

While you paint:

| Action | Result |
| --- | --- |
| Click a swatch in the color strip at the top of the canvas | Switch to that region |
| Click **+** in the strip, or press `Shift + C` | Add a new region |
| `<` and `>` (also `,` and `.`) | Previous and next region |
| Double-click a swatch, or press `Shift + E` | Open **Edit Color** to change that color |
| Hold `S` and click on painted area | Pick the region under the pointer |
| `E` | Switch between paint and erase |
| Hold `Alt` | Temporarily use the opposite mode |
| `Ctrl + Z` and `Ctrl + Shift + Z` | Undo and redo completed marks |

## Colors

New regions use a set of six hand-picked colors in order. After that, Kanvas picks random colors that are as different as possible from the ones already in use, so many regions stay easy to tell apart.

The **shuffle** button next to the region list gives all regions a new set of well-spread random colors. It can be undone. For regions linked to a checklist, the matching task color changes too.

## Inverse

Turn on **Inverse** to color **everything on the image except the area you painted**. Paint a part, tick Inverse, and the rest of the image takes the color. Untick it to go back. Painting after that works on the same area as before. Inverse is set per region.

## Isolating one color

Busy images with many regions can become hard to read. **Isolate** shows one region at a time, and hides the others, their names, and their arrows.

| To | Do this |
| --- | --- |
| Isolate the active region | Click **Isolate Color** |
| Go to the next region | `]`, or the right arrow next to the button |
| Go to the previous region | `[`, or the left arrow |
| Show everything again | `\`, or click the isolated region's button again |

Stepping with `]` goes through every region and then returns to showing all. Picking a different region in the list while isolating moves the isolation to it. If several images are selected, the shortcut works on all of them, each with its own position in its list. Isolating works the same on linked and unlinked images.

## Names on the image

**Names** (off by default, set per image) writes each region's name at the middle of every painted **island**, which is each separate connected area of that color. For a linked region, the name is the task text.

- The name sits in the deepest part of the island, so it stays inside the paint even on curved shapes.
- The text shrinks to fit. If it would be smaller than 8 pixels, it is not drawn.
- Tiny specks of paint are ignored.
- Names are hidden while you paint, on very small images, and behind text cards.

## Linking a checklist to an image

You can link a checklist to images, so each task gets a color region.

1. Select the checklist and one or more images.
2. In the checklist's **Selection** panel, click **Link Selected**.

What happens:

- Each task gets its own color region on every linked image, with the task's color and name.
- Regions follow the checklist. Reordering tasks reorders the regions, and renaming a task renames its region.
- To remove a link, use the unlink button next to **Link Selected**. The paint you made stays.

### Task arrows and the eye

Once a checklist is linked, an **eye** icon appears next to each task checkbox. It draws or hides arrows from that task to its painted area. Arrows follow the task as the card scrolls.

**Point All Islands** (per image, off by default) draws an arrow to every island of the region instead of only the nearest one.

### Marking tasks as done

With **Done Lines** on (per image, only when a checklist is linked), a region whose task is checked gets dark diagonal lines drawn over its paint. **Opacity** next to it sets how strong the lines are. Unlinked regions never get lines.

## Hiding colors

- The eye on a region hides that region.
- The **Markup** checkbox in the panel header hides all colors on the image.

## Next

- [Auto Select](auto-select.md)
- [Text cards and checklists](text-cards.md)
