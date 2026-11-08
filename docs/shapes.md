# Shapes

A shape is a rectangle, triangle, diamond, ellipse, pentagon, hexagon, star, a polygon with vertices you place yourself, or a free path drawn with the pen, closed or open. Use shapes to outline and measure things on an image, to mark areas, or to build simple diagrams with text inside.

There is one kind of item. You draw it, and you can change its kind later without redrawing it.

## Drawing a shape

1. Choose **Add > Shape** and pick a kind.
2. Drag on the canvas to draw it. Hold `Shift` for a square or circle, and `Ctrl` to draw from the center.
3. A click without dragging creates a shape of a default size, centered on the click.

`Esc` cancels. Nothing keeps running while you wait: the choice only applies to your next drag. If you drop a shape inside a [frame](frames.md), it joins that frame.

## Drawing with the pen

Press `Shift+P` on the canvas, or choose **Add > Shape > Pen (free path)**, to draw a free path vertex by vertex. The path updates live as you move the mouse.

- Click to place a corner. Click and drag to place a smooth vertex: the drag pulls its handles, so the path curves through it.
- Click the first vertex again to close the path. It becomes a filled shape.
- Press `Enter` or double-click to finish the path open, as a line with two ends and no fill. An open path needs at least two vertices.
- `Backspace` removes the last vertex, `Ctrl` snaps to the grid, `Shift` keeps each segment at a multiple of 45 degrees, and `Esc` or right click cancels.

While a shape is in **Edit Vertices**, `Shift+P` draws a new contour of that shape instead of a new shape: a hole when you draw inside it, or a separate island outside it. The contour closes like the shape (or stays open, for an open path), and you are back in Edit Vertices when it is done.

## Open paths

An open path is a shape whose outline does not join its last vertex back to its first: a line, a curve, a connector. It is drawn without fill and picked only on its line. Turn **Closed** in the **Selection** panel off or on to open or close any shape; closing it does not bring a fill back by itself. In **Edit Vertices**, an open path keeps at least two vertices, and the line can grow from either end (see below). Open paths and closed shapes cannot be combined.

## Drawing a polygon click by click

Press `Ctrl+P` on the canvas, or choose **Add > Shape > Polygon (click by click)**, then click each vertex. The shape updates live as you move the mouse.

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

Select one shape and press `E`, or turn on **Edit Vertices** in the **Selection** panel. The box handles are replaced by one handle per vertex, and the rest of the canvas is dimmed so the shape stands out (see **Focus While Editing** in [Preferences](preferences.md#editing-focus)). Press `E` or `Esc` to leave.

- Click a vertex to select it. `Shift`+click adds it to the selection or removes it.
- Drag from empty space, or from inside the shape, to select the vertices in a box. Hold `Shift` to add to the selection and `Ctrl` to remove from it. A click inside the shape clears the vertex selection; a click on empty canvas deselects the shape, which also leaves Edit Vertices.
- `Ctrl+A` selects every vertex (press it again to select none) and `Ctrl+I` inverts the selection.
- Drag a vertex to move it together with every other selected vertex. Selected vertices are drawn larger, in the selection color.
- Drag an edge to bend it into a curve that follows the pointer. A click on an edge, without moving, selects its two vertices.
- `Ctrl`+click an edge to add a vertex there; keep the button down to move it right away. On a curved edge the new vertex keeps the curve as it was.
- `Ctrl`+click away from the outline (without dragging) to add a vertex at that point. With one vertex selected, the new vertex comes right after it, so the outline grows towards the click; on an end of an open path, the path grows from that end. With no vertex selected, the new vertex goes into the nearest edge. The new vertex is selected, so each `Ctrl`+click continues from it. A `Ctrl`+drag is still a box that removes from the selection.
- Press `L` with the pointer on a vertex or an edge to select its whole contour (`Shift+L` adds it), or with nothing under the pointer to select the contours of the selected vertices.
- Press `G`, `R` or `S` to move, rotate or scale the selected vertices around the middle of their bounds. Move the mouse, then click or press `Enter` to confirm, or `Esc` or right-click to cancel. `Ctrl` snaps (grid, 15 degree steps or steps of 0.1; with `Shift`, finer). With one vertex selected, `R` and `S` work on the whole shape as usual.
- **Position** in the **Selection** panel shows where the selected vertices are (the middle of their bounds); type a value to move them there.
- **Flip H** and **Flip V** mirror the selected vertices around their middle, and **Reverse** runs their contour the other way round (which end of an open path comes first). The outline does not change with Reverse.
- Press `X` or `Delete`, or click **Delete** in the **Selection** panel, to delete the selected vertices. `Ctrl`+click deletes the vertex under the pointer. A shape keeps at least three vertices. With no vertex selected, `X` does nothing: it never deletes the shape while you edit it.
- Hold `Ctrl` while dragging to snap the grabbed vertex or handle to the grid, and `Shift+Ctrl` for a finer grid. With **Vertices** on in the snapping options (off by default), a dragged vertex also snaps to the vertices of other shapes nearby, to join outlines exactly.
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

**Curve Resolution** (in the **Selection** panel) sets how many straight segments draw each curved edge, and each rounded corner (see **Corner Radius**), from 2 to 64 (16 by default). Lower is lighter and more angular; higher is smoother. It is set per shape, and greyed out on a shape with neither curves nor rounded corners. An ellipse is a curve through four smooth vertices, so its smoothness follows this setting too.

Deleting a vertex joins its two neighbours with a straight edge, which is also what "dissolve" does in a mesh editor. An arrow attached to a deleted vertex, or anywhere on the outline, moves to the nearest point of the new outline; an arrow attached inside the shape keeps its place.

While you edit, a **EDIT VERTICES** badge at the top of the canvas shows the shape's name, its vertex count and how many are selected, and a **Shortcuts** panel at the bottom left lists these keys. It looks and behaves like the one in Mask and Color: click its **-** or **+** button to collapse or expand it, and the choice is shared between the three modes.

Editing a vertex turns the shape into a **Polygon**, and the box follows the new outline. Ellipses can be edited like any shape: their four vertices are Mirrored curves. (An ellipse made with an earlier version keeps its 48 straight vertices; choose **Ellipse** as the kind again to turn it into a curve.) **Edit Vertices** is not saved: it is off every time you open the file.

## Holes and combined shapes

A shape can have more than one outline, called contours: a ring, a frame, the letter "O", an icon with holes. A contour inside another one is a hole; a contour inside a hole is filled again, and so on (the even-odd rule). Clicks in a hole go through to whatever is underneath. Contours may also overlap or cross each other (or themselves): wherever an odd number of them cover a point, it is filled, so the area where two combined shapes overlap is empty.

| Action | How |
| --- | --- |
| **Combine Shapes** | Select two or more shapes, right-click and choose **Combine Shapes**. They become one shape with all their contours, and wherever they overlap a hole opens, so a small shape on top of a large one cuts a hole in it. The active shape keeps its name, look and text; the others are removed. Arrows attached to any of them stay where they are, attached to the result. |
| **Separate Contours** | Right-click a shape with several contours and choose **Separate Contours**, or click **Separate** in its **Selection** panel. Each contour becomes a shape of its own, with the same look. The text stays on the first one. |

In **Edit Vertices**, every contour is edited like a shape of its own: adding a vertex on an edge keeps it in that contour, and the closing edge of each contour links its last vertex back to its first. Deleting vertices until a contour has fewer than three closes it (a hole disappears), as long as another contour remains. The badge counts the contours.

## Appearance

In the **Selection** panel, the fill is in the **Fill** tab, the line (**Outline**, **Join**, **Ends**, **Align**) in the **Line** tab, and **Corner Radius** and **Opacity** in the **Shape** tab.

| Option | What it does |
| --- | --- |
| **Fill** | Turns the fill on or off, with its color and opacity. **Solid**, **Linear** or **Radial** below it picks one color or a [gradient](#gradients) |
| **Outline** | Turns the line on or off, with its color, width, and style (solid, dashed, dotted) |
| **Join** | How the line turns at corners: **Round** (the default), **Miter** (sharp; very sharp corners are cut off) or **Bevel** (cut off straight) |
| **Ends** | How the ends of an open path and of each dash look: **Round** (the default), **Flat** (cut off at the end point) or **Square** (cut off half the line width further). Dots always stay round. |
| **Align** | Where the line lies on a closed outline: **Center** (the default), **Inside**, so the shape keeps its size, or **Outside**. For holes, inside means in the shape around the hole. |
| **Corner Radius** | Rounds every Sharp corner between two straight edges, in canvas units (0 keeps them sharp). The corners stay round on a stretched shape, and a corner never takes more than half of each edge, so a large radius turns short sides into half circles. Curved edges and the ends of an open path are left as they are. |
| **Opacity** | Fades the whole shape: fill, outline, and text |

The defaults look exactly as shapes always did.

Fill and outline cannot both be off, so a shape never disappears: while one is off, the other stays on.

### Gradients

In the **Fill** tab of the **Selection** panel, choose **Linear** or **Radial** (closed shapes only). The first time, the gradient goes from the fill color to clear; after that the shape keeps its own gradient, even while you switch back to **Solid** and again.

| Option | What it does |
| --- | --- |
| **Colors** | Blender's color ramp: click a stop to pick it, drag it to move it, and set its color and opacity below the ramp; `+` and `-` add and remove stops, and the menu next to them flips the ramp. **Interpolation** (Linear, Ease, Constant, B-Spline, Cardinal) and the color mode (RGB, HSV, HSL) work as in the rest of Blender. |
| **Spread** | What lies past the ends: **Pad** keeps the end colors, **Reflect** repeats the gradient mirrored each time, **Repeat** starts it again |
| **Start / End** | Where a linear gradient starts and ends; for a radial one, its **Center** and a point on its **Edge**. Both are measured in the shape's box, from -0.5 to 0.5 on each axis, so the gradient moves, turns and scales with the shape. **Turn 90°** turns it around its middle (a radial one around its center), **Reset** puts it back across the whole shape. |

**On the canvas:** while the sidebar is open on the **Fill** tab with one gradient shape selected, the shape shows the gradient instead of its box handles: a line from the start (round handle) to the end (square handle), a dot in the color of each stop, and for a radial gradient the circle it fills. Drag a handle to move that end, or the line to move both. Hold `Ctrl` to snap to the corners, the middles of the sides and the center of the shape's box, and `Shift` to turn in 15° steps. `Esc` or right-click cancels; each drag is one undo step. Move the shape itself by dragging anywhere else on it, or switch tabs to get its box handles back.

The **Fill** opacity applies on top of the stops' own opacity. A radial gradient stays round on a stretched shape. Editing vertices, combining, separating or cutting shapes leaves the gradient where it was on the canvas. Duplicates and **Copy Style** / **Paste Style** carry the gradient, each shape with colors of its own. The colors are kept in a hidden texture that belongs to the shape (Blender keeps a color ramp only inside a datablock); it is saved with the board and goes away with the shape. A shape whose gradient was made before the color ramp shows **Edit Colors**, which turns its stops into a ramp. If the graphics driver cannot run the gradient drawing, the shape is filled with the gradient's average color instead.

**Copy Style** and **Paste Style** in the context menu copy this appearance to other shapes. **Flip H** and **Flip V** in the **Selection** panel mirror the shape inside its box; arrows attached to it follow.

## Shape tools

Right-click selected shapes and open **Shape Tools**:

| Tool | What it does |
| --- | --- |
| **Union** | One shape covering all the selected shapes |
| **Difference** | The first shape you selected, with the other selected shapes cut out of it (holes where they fall inside). Select the shape to cut first, then the cutters with `Shift`+click |
| **Intersection** | Only the area where all the selected shapes overlap |
| **Exclusion** | All the selected shapes, with the areas where they overlap cut out |
| **Combine** | All the contours in one shape, without merging them: overlaps become holes. See [Holes and combined shapes](#holes-and-combined-shapes). |
| **Separate Contours** | One shape per contour |
| **Offset Outline...** | Adds a copy with the outline moved outwards by a distance (negative: inwards), holes included. **Replace** changes the shape itself instead. |
| **Line to Shape** | Turns the line into a filled shape of the same size and color, to edit, cut or combine it like any shape. A shape with a fill keeps its fill without the line; a line alone is replaced. Dashes are not kept. |
| **Simplify...** | Keeps only the vertices needed to stay within a **Tolerance** of the outline, for traced or imported shapes with too many vertices. **Smooth** makes the remaining vertices Auto, for a smooth curve. |
| **Flip Horizontal / Vertical** | Mirror the selected shapes |

The order of selection decides, not the layers on the canvas. For Union, Intersection and Exclusion, the active shape keeps its name, look and text (the first selected one if the active item is not a shape); the other shapes are removed. Shapes selected together with a box count in the order of the item list. Arrows attached to any of them stay where they are, attached to the result. The tools work on the filled area, so they need closed shapes: close open paths, or use **Line to Shape** on them first. If nothing would be left (an intersection of shapes that do not overlap), nothing changes. The results are made of straight edges: curves are flattened at their **Curve Resolution** and corner radii are built in. Use **Simplify** with **Smooth** to round them again.

## Text inside a shape

Type in the field of the **Text** tab of the **Selection** panel. It is a single line, meant for a short label. The text is centered and turns with the shape. Its size is fixed on the canvas, like the shape's: it grows and shrinks with the zoom, and it is hidden when it would be too small to read. It wraps inside the box of the shape, with the same line breaks at every zoom level, and never goes past the box: a text that does not fit ends in an ellipsis. Make the shape larger to show more. Set the font size and color next to the field, or turn **Text** off to hide it without deleting it. The text is found by the search field of the item list.

## SVG files

**Import:** drag `.svg` files from your file browser onto the canvas, or choose **Add > Shape > Import SVG...**. This adds the outlines of an SVG file as shapes, keeping their curves, fill, stroke, stroke width and dashes. In the file browser's side panel:

| Option | What it does |
| --- | --- |
| **Fit Size** | Scale the drawing so its larger side has the **Size** below (400 by default). Turn it off to keep the SVG units, one unit per canvas unit. |
| **Group** | Group the shapes when the file has more than one shape. |

Everything is named after the file: a single shape takes its name (`logo`), several shapes are numbered (`logo.001`, `logo.002`...) and their group takes the plain name. A dropped drawing lands centered where you drop it; several files dropped together line up to the right of the first one. From the menu, the drawing lands at the center of the view. A drop uses the default options: **Fit Size** on (400) and **Group** on. Paths (every command, arcs included), rectangles (rounded too), circles, ellipses, polygons and polylines are read, inside groups and transforms, with colors from attributes, `style` and simple CSS classes, including `stroke-linejoin` and `stroke-linecap`. Each element becomes one shape, and the subpaths of a path become the contours of that shape, so holes (a letter "O", a ring) stay holes. Lines (`<line>`, polylines and open paths without fill) come in as open paths; other open outlines are closed with a straight edge.

Kanvas fills with the even-odd rule. A path with `fill-rule="nonzero"` (the SVG default) usually draws its holes wound the other way round, and those come in as holes. A contour inside another one and wound the same way would not be a hole under `nonzero`, so it comes in as a separate shape on top, named with a number after the `id`.

Linear and radial gradients come in as shape gradients, with their stops (as color ramp stops), spread, `gradientTransform` and `href` to another gradient. A radial gradient comes in as a circle: its focus point is ignored, and on a stretched element its radius follows the width. A gradient with a single stop is a flat color, and one without stops paints nothing.

What does not carry over: clip paths, masks, images, text and `<use>` references are ignored. The vertex types are worked out from the handles: Sharp corners, Mirrored or Aligned smooth points, and Free for the rest.

**Export:** with shapes selected, right-click and choose **Export Shapes as SVG...**, or click **Export SVG...** in the shape's **Selection** panel. Each shape becomes one `<path>` with its curves, rotation and scale built into the coordinates, plus its fill (gradients as `<linearGradient>` or `<radialGradient>`; SVG only blends linearly in RGB, so a ramp with another interpolation or color mode is written as many close stops that look the same), stroke, opacity, dashes, joins, ends and text. A shape with holes writes one subpath per contour and `fill-rule="evenodd"`, and an open path has no closing `Z`. A shape with a corner radius writes its rounded outline as short straight edges. SVG has no inside or outside line, so a line set to **Inside** or **Outside** goes on a second path that follows the outline at half the line width. Exporting and importing again gives the same outline.

## Connecting shapes with arrows

Arrow ends attach to the corners, the middle of the sides, the outline, or any point inside a shape, and follow it when it changes. Put text in the shapes and connect them with [arrows](arrows.md#attaching-to-shapes) to make a diagram.

## Related pages

- [Frames](frames.md)
- [Arrows](arrows.md)
- [Text cards and checklists](text-cards.md)
