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

- Drag a vertex to move it.
- Drag an edge to add a vertex there and move it.
- `Ctrl`+click a vertex to delete it. A shape keeps at least three vertices.
- Hold `Ctrl` while dragging a vertex to snap it to the grid.

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

## Connecting shapes with arrows

Arrow ends attach to the corners, the middle of the sides, the outline, or any point inside a shape, and follow it when it changes. Put text in the shapes and connect them with [arrows](arrows.md#attaching-to-shapes) to make a diagram.

## Related pages

- [Frames](frames.md)
- [Arrows](arrows.md)
- [Text cards and checklists](text-cards.md)
