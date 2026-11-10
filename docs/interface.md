# Interface and navigation

## The Kanvas Tree

A **Kanvas Tree** is the editor type that shows a board. The board is an infinite canvas. Items you can place on it are:

- **Images**, the references themselves
- **Text cards** and **checklists**
- **Frames** that group other items
- **Arrows** that connect items

Each tree stores its own board. The same tree shown in two editors displays the same board, and a change in one appears in the other. To copy a board, duplicate the tree.

> Image items can share Blender image data, so duplicating an item does not necessarily create another image file. Save the `.blend` file to keep the board.

## Edit and Move modes

Every board is in one of two modes:

| Mode | Left mouse button | Use it to |
| --- | --- | --- |
| **Edit** | Selects, moves, and edits items. This is the full Kanvas behavior | Build and arrange a board |
| **Move** | Pans the canvas. Nothing is selected or changed | Browse a board safely, especially when the middle mouse button is hard to use |

In Move mode the cursor becomes a hand over the canvas.

There are three ways to switch:

- Press `Tab` with the pointer over the canvas.
- Click **Edit** or **Move** in the switch at the top of the canvas. You can hide it in the preferences (see below).
- Use the **Edit | Move** buttons in the editor header or at the top of the **Kanvas** sidebar panel.

The mode is saved with the board. `Tab` is not affected in other editors, and it keeps its original meaning inside [Mask and Color editing](masks.md), where it switches tools.

**Show Edit/Move Overlay** in **Preferences > General > Interface** (or in the **Kanvas** sidebar panel) hides the switch on the canvas. The shortcut and the header buttons keep working.

## Navigating the canvas

| Action | How |
| --- | --- |
| Pan | Middle mouse drag, or left mouse drag in Move mode |
| Zoom | Mouse wheel. Over a selected, long text card the wheel scrolls the card instead (see [Text cards](text-cards.md#resizing-and-long-text)) |
| Frame the selection | `Numpad .` |
| Return to your content | Click the **Recenter** button that appears when content is off-screen |

The **Recenter** button points toward your content and stays within the free area next to Blender's side panels. On an empty board it appears only when the origin is out of view, and it takes you back there.

## Sidebar panels

Press `N` over the canvas and open the **K-Tools** tab.

| Panel | Contents |
| --- | --- |
| **Kanvas** | The Edit and Move switch and the overlay option |
| **Items** | The item list, plus the list and settings of arrows |
| **Selection** | Actions and properties for what is selected, in tabs (see below). It shows "Nothing selected" when empty |
| **Align** | Align and distribute commands |
| **Gizmos** | Size and visibility of the transform handles |
| **Snap** | Grid and edge snapping |
| **Debug** | Diagnostics and reset tools. Hidden unless enabled in the preferences |

### The Selection panel

When something is on that you might not see from the tab you are in (a mask, color markup, a mode being edited), a line above the tabs says so. Rename items in the item list or with `F2`. Images, shapes and text cards show **tabs**, so only one group of settings is open at a time:

| Item | Tabs |
| --- | --- |
| Image | **Image** (file, source, position, rotation, scale, stretch, shear, flip) · **Adjust** (opacity, brightness, contrast, saturation, tint, value checks) · **Mask** · **Color** (color markup) |
| Shape | **Shape** (kind, vertices, contours, corners, position and size, opacity, SVG export) · **Fill** (color or gradient) · **Line** · **Text** |
| Text card | **Card** (position, size, colors, opacity) · **Content** (title, text, Markdown, checklist) |

Frames, groups and comparison cards have few settings and show them without tabs. Entering a mode opens its tab: `M` the **Mask** tab, `C` the **Color** tab, `E` the **Shape** tab; leaving the mode keeps the tab. Each kind of item remembers its tab for the session, so selecting another shape keeps you in **Fill**. In a narrow sidebar the tabs show only their icons; hover one for its name.

### The Items panel

The item list shows every item on the board, in stacking order: the top of the list is the front of the canvas (see [Layers](transforms.md#layers)). In the list you can:

- **Search** by name, and also by the text inside cards and checklists and by the names of color regions (a task text for linked regions). Matching items stay visible together with the frames that hold them. The **X** button clears the search.
- **Select** any item, including images that are covered by others on the canvas.
- **Hide or show** an item with the eye icon. Hidden items stay on the board but are not drawn or editable.
- **Lock** an item with the lock icon. A locked image, card, or frame cannot be selected, moved, transformed, duplicated, or deleted. Click the lock again to unlock it. Locking a frame also locks everything inside it.
- **Delete** the selected item.
- **Reorder** the selected items with the arrow buttons beside the list: one step up or down, or to the top or bottom of their level.

When an item's image file is missing on disk, the list shows how many are missing and a **Relink** button (see [Images](images.md#missing-files-and-relinking)).

The **checkmark** button beside the list runs **Check Board**. It looks for broken references: image links to a checklist that was deleted, color regions that follow a task that no longer exists, arrow ends attached to a deleted item, items that belong to a missing frame, and items that share an identity. It lists what it found, and **Repair** clears only those broken references. It never deletes items, images, paint, or text. An item with no image needs **Replace Image** and is only reported.

Arrows are listed and edited below the item list (see [Arrows](arrows.md)). The settings of the selected image, card, or frame are in the **Selection** panel.

## Right-click menu

Right-click an item to open the **Kanvas** menu. Its entries depend on the selection:

- **Frame:** create a frame around the selection, attach it to a frame, release it from a frame, or fit a frame to its content.
- **Arrange:** Pack, align, and distribute.
- **Reset Transform:** location, scale, or rotation.
- **Edit:** duplicate, **Copy Style**, **Paste Style**, or delete.
- **Add:** the same entries as the **Add** menu.
- **Export Image...:** save a PNG of the selection, the board or the view (see [Exporting a picture](export-image.md)).
- **Fit Bounds to Mask** and **Reset Bounds:** for masked images, make the image only as big as its mask shows, and give it its whole size back (see [Image masks](masks.md#fitting-the-bounds-to-the-mask)).
- **Send to 3D View...:** with images selected, add them to the 3D View as reference images or overlays (see [References in the 3D View](references-3d.md)).

## Hover cursor and feedback

- Selected images get a colored outline. The color and thickness are set in **Preferences > Aesthetics > Selection Outlines**.
- A small **pencil** button appears on text cards and checklists to edit them. You can turn it off in **Preferences > General > Interface**.
- The status bar shows short messages after actions such as an Auto Select result or a blocked command.

## Undo

Kanvas uses Blender's Undo system, so `Ctrl + Z` and `Ctrl + Shift + Z` work as usual. A drag, a transform, or a whole Mask editing session counts as one Undo step. Selecting items, opening menus, and other actions that change nothing do not add steps.

While you edit a mask or a color markup, `Ctrl + Z` undoes one completed stroke or shape at a time. When you finish editing, the whole session becomes one Undo step.

## Blender annotations

Strokes made with Blender's native annotation tool in a Kanvas Tree are drawn above your images, so notes and sketches stay visible over your references.

## Next

- [Images](images.md)
- [Selecting and transforming](transforms.md)
- [Keyboard and mouse reference](shortcuts.md)
