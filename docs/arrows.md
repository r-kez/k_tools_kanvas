# Arrows

Arrows show relationships between items. An arrow end can be attached to an image or card, and it then follows that item when it moves or transforms.

## Creating an arrow

There are two ways.

**Add > Arrow**

1. Choose **Add > Arrow**.
2. Click where the arrow should start.
3. Click where it should end.

**Quick Arrow**

1. Hold `A`.
2. Drag from a free point, or from an anchor on an item, to where the arrow should end.

Place an endpoint on an image or a text card to **attach** it. Images offer anchors at their corners and edge centers, and also at points inside the image. Cards offer anchors on their edges.

## Attaching to shapes

An arrow end attaches to a [shape](shapes.md) in three ways, so you can build diagrams:

- **Corners and sides:** near a corner of the shape, or the middle of a side, the end snaps to it. An ellipse offers eight points, one every 45 degrees. The snap points are shown while you place or drag an end.
- **The outline:** close to the edge, the end attaches to the nearest point of the outline.
- **Inside:** anywhere inside the shape, the end attaches exactly where you release it.

The end follows the shape when it moves, turns, scales, or is resized. When you edit a shape's vertices, attached ends stay where they were. Deleting a shape leaves the arrow where it was.

## Editing an arrow

Click an arrow to select it. You can then:

| To | Do this |
| --- | --- |
| Move an endpoint | Drag the endpoint handle |
| Bend the arrow | Drag the **center handle** to change its curvature |
| Straighten it | **Reset Curvature**, in the panel. Endpoints do not move |
| Move the whole arrow | Drag the line. It is released from any attachments, and its ends may attach again where it lands |
| Detach one end | Use the detach button next to that end in the panel. The endpoint stays where it is |
| Remove it | Select it and use **Remove Arrow**, or press `X` or `Delete` |

Arrows can be selected together with other items: `Shift + click` and box selection add arrows to the selection. Moving, deleting, and focusing work on the whole selection. When items move, arrow ends attached to moving items go with them, and ends attached to items that stay put are released from them during the move. Cancelling the move restores the attachments.

## Arrow settings

Arrows are listed in the **Items** panel. Select one to edit it:

| Setting | Effect |
| --- | --- |
| **Label** | Text shown at the midpoint of the arrow |
| **Color** | Arrow color |
| **Thickness** | Stroke width, 1 to 20 |
| **Line** | Solid, Dashed or Dotted |
| **Heads** | Arrowhead at the End (default), at Both ends, or None for a plain line |
| **Lock Arrow** | Prevents selecting, moving, and deleting the arrow |

The label follows the middle of the curve. While an arrow is selected, its label shifts slightly so the center handle stays reachable. When space is tight, the drawn label is shortened, and the full text stays in the panel.

## Appearance

**Preferences > Aesthetics > Arrows** sets the style for every arrow:

- **Filled**, the default solid arrow
- **Rounded Stroke**, a rounded outline

The colors of the endpoint and curvature handles are under **Arrow Handles**.

Arrows are drawn behind text cards and frame titles, so text stays readable.

## Next

- [Image masks](masks.md)
- [Color Markup](color-markup.md)
