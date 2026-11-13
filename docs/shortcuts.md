# Keyboard and mouse reference

All shortcuts below are defaults. They work **only while the pointer is over the canvas of a Kanvas Tree**, and never affect other Blender editors. You can change them in **Preferences > Add-ons > K-Tools: Kanvas > Controls**.

## Mouse

| Action | Result |
| --- | --- |
| Left click | Select. In Move mode, pans the canvas |
| `Shift` + left click | Add or remove an item from the selection |
| Left drag on an item | Move it |
| Left drag on empty canvas | Box select (`Shift` adds) |
| `Alt` + left drag | Box select |
| Middle drag | Pan |
| Wheel | Zoom. Over a long text card, scrolls the card instead (see [Text cards](text-cards.md#resizing-and-long-text)) |
| `Ctrl` + wheel | Opacity of the image under the pointer; line width with the pencil picked or strokes picked |
| `Shift` + wheel | Scale of the active image |
| `Alt` + wheel | Move the item under the pointer up or down the stack |
| `Page Up` / `Page Down` | Move the selected items one step up (front) or down (back) the list |
| `Shift + Page Up` / `Shift + Page Down` | Move the selected items to the front / back |
| Right click | Context menu |
| `Ctrl` + click on a link in a card | Open the link |

## Overlays in the 3D View

These work over a Kanvas overlay in a 3D View, not over the board. See [Placing an overlay](references-3d.md#placing-an-overlay).

| Shortcut | Action |
| --- | --- |
| `Alt` + drag | Move the overlay under the pointer |
| `Alt` + right drag | Rotate it (`Ctrl` for steps of 15 degrees) |
| `Alt` + `Shift` + drag | Scale it |
| `Alt` + `Ctrl` + wheel | Opacity |
| `Shift` while moving or rotating, `Ctrl` while scaling | Ten times slower, for fine work |
| `Alt` + `Home` | Reset its place, rotation and size |

## Selection and navigation

| Shortcut | Action |
| --- | --- |
| `Ctrl + A` | Select everything visible |
| `Ctrl + I` | Invert the selection |
| `B`, then drag | Box select, even when the drag starts on an item |
| `Numpad .` | Frame the selection |
| `Tab` | Toggle **Edit** and **Move** mode |
| `Esc` | Cancel a transform, a drag, or an armed box |

## Transform

| Shortcut | Action |
| --- | --- |
| `G` | Move |
| `S` | Scale |
| `R` | Rotate |
| `Alt + G` | Reset location |
| `Alt + S` | Reset scale and shear (scale goes back to the import scale, see **Import Size** in the preferences) |
| `Alt + R` | Reset rotation |
| Click or `Enter` | Confirm a transform |
| `Esc` | Cancel a transform |
| `Shift` (while transforming) | Fine adjustment |
| `Ctrl` (while transforming) | Steps. Also inverts snapping |
| `Alt` on an edge handle | Shear |

## Editing items

| Shortcut | Action |
| --- | --- |
| `Shift + D` | Duplicate every selected item and move the copies |
| `Ctrl + G` | Group the selected items (see [Groups](groups.md)) |
| `Ctrl + L` | Connect the selected items with arrows (see [Arrows](arrows.md#connecting-items)) |
| `Ctrl + Shift + G` | Ungroup |
| `F2` | Rename the active item |
| `X` or `Delete` | Remove the selection (in Edit Vertices: the selected vertices) |
| `Ctrl + V` | Paste images |
| `P` | Pack the selected images |
| `Shift + F` | Create a frame around the selection |
| Hold `F` while moving | Release the item from its frame |
| `Alt + U` | Release selected items from their frame |
| Hold `A`, then drag | Quick arrow |
| `Shift + P` | Pen: draw a free path (in Edit Vertices: a new contour of the shape) |
| `Ctrl + P` | Polygon: draw a closed polygon click by click |

## Edit Vertices

Select one shape and press `E` to enter **Edit Vertices** (see [Shapes](shapes.md#editing-vertices)). These work while it is on.

| Shortcut | Action |
| --- | --- |
| Click a vertex | Select it |
| `Shift + click` a vertex | Add it to the selection, or remove it |
| Drag from empty space or inside the shape | Box select (`Shift` adds, `Ctrl` removes) |
| `Ctrl + A` / `Ctrl + I` | Select all vertices (again: none) / invert |
| Drag a vertex | Move every selected vertex |
| Drag an edge | Bend it into a curve (a click selects its two vertices) |
| Drag a handle of a selected vertex | Shape the curve |
| `V` | Vertex type: Sharp, Auto, Aligned, Mirrored or Free |
| `Ctrl + click` an edge | Add a vertex there |
| `Ctrl + click` away from the outline | Add a vertex there, after the selected one (an open path grows from that end) |
| `L` / `Shift + L` | Select the contour under the pointer / add it |
| `G`, `R`, `S` | Move, rotate, scale the selected vertices |
| `Shift + P` | Draw a new contour of the shape |
| `X` or `Delete` | Delete the selected vertices |
| `Ctrl + click` a vertex | Delete that vertex |
| `Ctrl` / `Shift + Ctrl` while dragging | Snap to the grid / a finer grid |
| Drag a vertex with **Vertices** snapping on | Snap to the vertices of other shapes |
| `E` or `Esc` | Leave Edit Vertices |

## Mask and Color editing

| Shortcut | Action |
| --- | --- |
| `M` | Start or finish Mask editing |
| `C` | Start or finish Color editing |
| `Tab` | Next tool |
| `B` | Brush |
| `P` | Polygon |
| `A` | Auto Select (after the image is analyzed) |
| `E` | Toggle between reveal/paint and erase |
| Hold `Alt` | Temporarily use the opposite mode |
| Middle drag, wheel | Pan, zoom |
| `Ctrl + Z`, `Ctrl + Shift + Z` | Undo, redo a completed mark |
| `Enter`, `Esc` | Finish editing (`Esc` cancels an unfinished shape first) |

### Brush

| Shortcut | Action |
| --- | --- |
| Drag | Paint |
| `Shift + click` | Straight line |
| `Shift + drag` | Straight line at 45° steps |
| `Ctrl + wheel` | Brush size |

### Polygon

| Shortcut | Action |
| --- | --- |
| Click | Add a vertex |
| Hold `Shift` | Snap the next edge to 45° |
| Double-click, `Enter`, or click the first vertex | Close |
| `Esc` | Cancel the shape |

### Rectangle

| Shortcut | Action |
| --- | --- |
| Drag | Draw |
| `Shift` | Square |
| `Ctrl` | From the center |
| `Shift + Ctrl` | Centered square |

### Auto Select

| Shortcut | Action |
| --- | --- |
| Click | Include |
| `Ctrl + click` | Exclude |
| `Backspace` | Remove the last point |
| `Enter` | Apply |
| `Esc` | Clear the points |

### Color mode only

| Shortcut | Action |
| --- | --- |
| `<` and `>` | Previous and next color |
| `Shift + C` | Add a color |
| `Shift + E` | Edit the active color |
| Hold `S`, then click | Pick the color under the pointer |

## Color Markup display

| Shortcut | Action |
| --- | --- |
| `]` | Isolate the next color (then back to showing all) |
| `[` | Isolate the previous color |
| `\` | Show all colors |

## Text cards

| Action | Result |
| --- | --- |
| Click the pencil | Edit the card |
| Drag the scrollbar | Scroll long text |
| `Ctrl` while resizing | Snap the edges |
| `Ctrl + click` a link | Open it |
| Click a checklist checkbox | Check or uncheck the task |
| Wheel over a selected card | Scroll long text |
