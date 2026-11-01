# Text cards and checklists

Text cards hold notes on the board. A **checklist** is a text card whose lines are tasks you can check off, and it can be linked to images so each task gets its own color (see [Color Markup](color-markup.md#linking-a-checklist-to-an-image)).

## Creating a card

Use **Add > Text Card** or **Add > Checklist**. The card appears at the pointer, or at the center of the view. Select it and edit its content and appearance in the **Selection** panel.

## Editing text

- Click the small **pencil** button on the card to edit its text right on the canvas.
- Or edit the text in the **Selection** panel.

Cards support several lines and wrap text to the card width. Line breaks stay in the same places as you zoom.

## Card settings

Open the **Selection** panel with a card selected.

**Layout**

| Setting | Effect |
| --- | --- |
| **Position** | Location on the board |
| **Width** and **Height** | Card size. Width also controls text wrapping, without changing the font size |
| **Overall Scale** | Scales the card and its text together (0.25 to 8) |
| **Font Size** | Base text size (8 to 72). Default 18 |

**Appearance**

| Setting | Effect |
| --- | --- |
| **Text** | Text color |
| **Background** | Card color |
| **Opacity** | Background opacity |

**Content**

| Setting | Effect |
| --- | --- |
| **Title** | The card's name. It is also its name in the item list |
| **Show Title** | Draws the title at the top of the card |
| **Checklist** | Turns every line into a task with a checkbox |
| **Markdown** | Formats the text (see below) |

### Resizing and long text

The handle at the lower-right corner changes the width and height independently. Hold `Ctrl` while resizing to snap the edges to other items or to the grid.

When the text is longer than the card, you can:

- **Scroll with the mouse wheel.** Select the card, then scroll with the pointer over it.
- **Drag the scrollbar** at the right edge.
- **Make the card taller.**

The scrollbar becomes wider while the card is selected. Soft accent lines at the top or bottom of the card show where text is hidden.

By default the wheel scrolls a card only while it is **selected**, so zooming the board is never interrupted by accident when the pointer passes over a long note. A card that fits entirely never captures the wheel. In **Move** mode, where nothing can be selected, the wheel scrolls any long card under the pointer. You can change this in **Preferences > Controls > Scroll Text Cards with Wheel**.

Cards can belong to frames and take part in alignment and distribution.

## Markdown

Turn on **Markdown** for a card to format its text. The text stays plain and editable.

| Syntax | Result |
| --- | --- |
| `# Heading` to `###### Heading` | Headings, levels 1 to 6 |
| `**bold**`, `*italic*`, `~~strike~~` | Bold, italic, and strikethrough. They can be combined |
| `` `code` `` | Inline code |
| A fenced block with three backticks | Code block |
| `- item`, `1. item` | Bulleted and numbered lists. Lists can be nested |
| `- [ ] task`, `- [x] task` | Task markers |
| `> quote` | Block quote |
| `---` | Horizontal rule |
| `[name](https://example.com)` | A link. `Ctrl + click` opens it |
| A table written with pipe (vertical bar) separators | Tables with left, center, or right aligned columns |

Notes:

- Only `http` and `https` links open. Links appear in a distinct color.
- Italic text is shown with a light underline.
- Table outer pipes are optional, and text inside a cell wraps to the card width.
- Setext headings, HTML, reference-style links, footnotes, and images are not supported yet.

## Checklists

Turn on **Checklist** (or create the card with **Add > Checklist**). Each line becomes a task.

- **Check a task** by clicking its checkbox on the canvas, or in the **Selection** panel.
- **Show Progress** draws the percentage of completed tasks at the top of the card.
- Add, remove, and reorder tasks with the buttons in the panel. **Sort** orders them as **Open First**, **Completed First**, **Alphabetical A-Z**, or **Alphabetical Z-A**.
- Task text supports inline **bold**, *italic*, ~~strikethrough~~, `code`, and safe web links (`Ctrl + click` to open). Headings, lists, and tables are not interpreted in checklists.

Each task has a color. It is used when the checklist is linked to images. With a linked checklist, an eye icon also appears next to each checkbox, which draws or hides arrows from that task to its painted areas.

For linking and color options see [Color Markup](color-markup.md#linking-a-checklist-to-an-image).

## Performance with many cards

Cards re-draw only when they are visible and large enough to read. Very small cards at a distant zoom are not drawn. Layouts for Markdown and checklists are cached, so a board with many cards stays responsive. See [Performance and memory](performance.md).

## Next

- [Arrows](arrows.md)
- [Color Markup](color-markup.md)
