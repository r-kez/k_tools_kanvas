# Shapes

A shape is a rectangle, triangle, diamond, ellipse, pentagon, hexagon, star, or a polygon with vertices you place yourself. Use shapes to outline and measure things on an image, to mark areas, or to build simple diagrams with text inside.

There is one kind of item. You draw it, and you can change its kind later without redrawing it.

## Drawing a shape

1. Choose **Add > Shape** and pick a kind.
2. Drag on the canvas to draw it. Hold `Shift` for a square or circle, and `Ctrl` to draw from the center.
3. A click without dragging creates a shape of a default size, centered on the click.

`Esc` cancels. Nothing keeps running while you wait: the choice only applies to your next drag. If you drop a shape inside a [frame](frames.md), it joins that frame.

## Drawing a polygon click by click

Choose **Add > Shape > Polygon (click by click)**, then click each vertex. The shape updates live as you move the mouse.

- Click the first vertex again, or press `Enter`, to finish. A polygon needs at least three vertices.
- `Backspace` removes the last vertex.
- Hold `Ctrl` to snap vertices to the grid, and `Shift` to keep each side at a multiple of 45 degrees.
- `Esc` or right click cancels and removes the polygon.

The scroll wheel and the middle mouse button still zoom and pan while you draw. Drawing is a short session: nothing keeps running after you finish or cancel.

## Selecting and transforming

A shape behaves like other items: click it to select, drag to move, `Shift`+click to add to the selection, and use `G`, `R`, and `S` for move, rotate, and scale. See [Selecting and transforming](transforms.md).

A selected shape has its own handles, shown while it is the only selected item:

| Handle | What it does |
| --- | --- |
| Corner squares | Scale the whole shape |
| Edge squares | Change the width (left and right) or the height (top and bottom) |
| Circle above the top edge | Rotate |

Hold `Ctrl` while dragging an edge handle to step in whole units, and `Shift` for fine control. The handles follow the **Show Gizmos**, **Scale Handles**, and **Rotate Handles** options.

A shape with a fill is picked anywhere inside it. A shape without a fill is picked only on its outline, so it never blocks the image underneath.

## Changing the kind

In the **Selection** panel, change **Kind**. The vertices are rebuilt inside the same box, so position, size, rotation, and text stay. Choosing **Polygon** keeps the vertices as they are.

## Editing vertices

Turn on **Edit Vertices** in the **Selection** panel. The box handles are replaced by one handle per vertex.

- Click a vertex to select it. `Shift`+click adds it to the selection or removes it.
- Drag from empty space, or from inside the shape, to select the vertices in a box. Hold `Shift` to add to the selection and `Ctrl` to remove from it. A click inside the shape clears the vertex selection; a click on empty canvas deselects the shape, which also leaves Edit Vertices.
- `Ctrl+A` selects every vertex (press it again to select none) and `Ctrl+I` inverts the selection.
- Drag a vertex to move it together with every other selected vertex. Selected vertices are drawn larger, in the selection color.
- Drag an edge to bend it into a curve that follows the pointer. A click on an edge, without moving, selects its two vertices.
- `Ctrl`+click an edge to add a vertex there; keep the button down to move it right away. On a curved edge the new vertex keeps the curve as it was.
- Press `X` or `Delete`, or click **Delete** in the **Selection** panel, to delete the selected vertices. `Ctrl`+click deletes the vertex under the pointer. A shape keeps at least three vertices. With no vertex selected, `X` does nothing: it never deletes the shape while you edit it.
- Hold `Ctrl` while dragging to snap the grabbed vertex or handle to the grid, and `Shift+Ctrl` for a finer grid.
- Press `Esc` to leave Edit Vertices.

### Curves and vertex types

Each vertex has a type that sets how the outline passes through it. Choose it for the selected vertices with the **Vertex Type** buttons in the **Selection** panel, or press `V` on the canvas for a menu.

| Type | What it does |
| --- | --- |
| **Sharp** | A corner with straight edges. Every vertex starts as Sharp, so existing shapes look the same. |
| **Auto** | A smooth curve worked out from the two neighbouring vertices. It updates by itself when you move vertices. |
| **Aligned** | A smooth curve with two handles that stay in line. Drag one and the other turns to match, keeping its own length. |
| **Mirrored** | A smooth curve with two handles that mirror each other. Drag one and the other repeats it: same angle, same length. |
| **Free** | Each handle moves on its own, for a curved corner. Switching a Sharp vertex to Free keeps the edges straight until you drag a handle. |

Selected vertices that are not Sharp show their two handles. Drag a handle to shape the curve; hold `Ctrl` to snap it to the grid. Dragging the handle of an Auto vertex makes it Mirrored, so the curve stays symmetric. Bending an edge turns its Sharp ends into Free (the other edge at each end stays straight) and its Auto ends into Mirrored. Adding a vertex on a curved edge turns Mirrored neighbours into Aligned, since splitting the curve shortens one of their handles. Moving a vertex carries its handles along.

The box handles, frames, picking and arrow anchors follow the curve: the box grows to fit a bulge, a click inside a curved area picks a filled shape, and the anchor in the middle of a curved edge sits on the curve.

**Curve Resolution** (in the **Selection** panel, shown once a shape has a curve) sets how many straight segments draw each curved edge, from 2 to 64 (16 by default). Lower is lighter and more angular; higher is smoother. It is set per shape.

Deleting a vertex joins its two neighbours with a straight edge, which is also what "dissolve" does in a mesh editor. An arrow attached to a deleted vertex, or anywhere on the outline, moves to the nearest point of the new outline; an arrow attached inside the shape keeps its place.

While you edit, a **EDIT VERTICES** badge at the top of the canvas shows the shape's name, its vertex count and how many are selected, and a **Shortcuts** panel at the bottom left lists these keys. It looks and behaves like the one in Mask and Color: click its **-** or **+** button to collapse or expand it, and the choice is shared between the three modes.

Editing a vertex turns the shape into a **Polygon**, and the box follows the new outline. Ellipses have no vertex editing; change the kind first. **Edit Vertices** is not saved: it is off every time you open the file.

## Appearance

| Option | What it does |
| --- | --- |
| **Fill** | Turns the fill on or off, with its color and opacity |
| **Outline** | Turns the line on or off, with its color, width, and style (solid, dashed, dotted) |
| **Opacity** | Fades the whole shape: fill, outline, and text |

Fill and outline cannot both be off, so a shape never disappears: while one is off, the other stays on.

**Copy Style** and **Paste Style** in the context menu copy this appearance to other shapes.

## Text inside a shape

Type in the **Text** field of the **Selection** panel. It is a single line, meant for a short label. The text is centered and turns with the shape. Its size is fixed on the canvas, like the shape's: it grows and shrinks with the zoom, and it is hidden when it would be too small to read. It wraps inside the box of the shape, with the same line breaks at every zoom level, and never goes past the box: a text that does not fit ends in an ellipsis. Make the shape larger to show more. Set the font size and color next to the field, or turn **Text** off to hide it without deleting it. The text is found by the search field of the item list.

## SVG files

**Import:** **Add > Shape > Import SVG...** adds the outlines of an SVG file as shapes, keeping their curves, fill, stroke, stroke width and dashes. In the file browser's side panel:

| Option | What it does |
| --- | --- |
| **Fit Size** | Scale the drawing so its larger side has the **Size** below (400 by default). Turn it off to keep the SVG units, one unit per canvas unit. |
| **Group** | Group the shapes when the file has more than one outline. |

The drawing lands at the center of the view. Paths (every command, arcs included), rectangles (rounded too), circles, ellipses, polygons and polylines are read, inside groups and transforms, with colors from attributes, `style` and simple CSS classes. Each closed outline becomes one shape, named after the element's `id`. Open outlines are closed with a straight edge. Lines and other outlines without area are skipped.

What does not carry over: a shape has one outline, so a hole (a letter "O", a ring) comes in as a second shape on top of the first. Gradients come in as flat gray, and clip paths, masks, images, text and `<use>` references are ignored. The vertex types are worked out from the handles: Sharp corners, Mirrored or Aligned smooth points, and Free for the rest.

**Export:** with shapes selected, right-click and choose **Export Shapes as SVG...**, or click **Export SVG...** in the shape's **Selection** panel. Each shape becomes one `<path>` with its curves, rotation and scale built into the coordinates, plus its fill, stroke, opacity, dashes and text. Exporting and importing again gives the same outline.

## Connecting shapes with arrows

Arrow ends attach to the corners, the middle of the sides, the outline, or any point inside a shape, and follow it when it changes. Put text in the shapes and connect them with [arrows](arrows.md#attaching-to-shapes) to make a diagram.

## Related pages

- [Frames](frames.md)
- [Arrows](arrows.md)
- [Text cards and checklists](text-cards.md)
