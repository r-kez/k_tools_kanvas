# Groups

A group keeps several items together. Select items, press `Ctrl + G`, and they move, hide, and lock as one. Unlike a [frame](frames.md), a group draws nothing around its items.

## Creating and dissolving a group

| Action | Shortcut |
| --- | --- |
| Group the selected items | `Ctrl + G` |
| Ungroup | `Ctrl + Shift + G` |

Both are also in the context menu, and the shortcuts can be changed in the add-on preferences. A group needs at least two items. Ungrouping keeps every item where it is and selects them.

## Groups do not nest

A group never holds another group:

- Grouping new items together with a group adds them to that group.
- Grouping items that belong to a group, and other items, adds the other items to that group.
- Grouping two groups merges them into one.

An item belongs to at most one group. If all the grouped items were inside the same frame, the group stays in that frame.

## Working with a group

- **Select:** click any item of the group to select the whole group. `Ctrl`+click selects that item alone, so you can move or edit it without ungrouping.
- **Box select:** a box that touches a group selects the group.
- **Move, delete, duplicate:** act on every member. Deleting a group deletes its items. Duplicating a group copies all its items into a new group.
- **Lock and hide:** the lock and eye in the item list apply to every member.
- **Frames:** items dropped near a group do not join it. Only `Ctrl + G` adds items.

A group is shown only while it is selected: a thin dashed outline around its items, with its name above. Select a group and rename it in the **Selection** panel.

## In the item list

A group is listed as a **Group** item with its members below it. Use the arrow to collapse it, like a frame. A group with no items left is removed automatically.

## Related pages

- [Frames](frames.md)
- [Selecting and transforming](transforms.md)
- [Keyboard and mouse reference](shortcuts.md)
