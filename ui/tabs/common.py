"""Pieces shared by the tabs: the line above the tab bar, spacing and row helpers."""

# Space between the groups of a tab, in Blender's separator units.
GAP = 1.2


def gap(layout):
    """Space between two groups of settings in a tab."""
    layout.separator(factor=GAP)


def draw_header(layout, settings, item):
    """What is on in the tabs you cannot see (a mask, color markup, a mode being
    edited), so switching tabs never hides that something is active. Nothing when
    there is nothing to say: the name is in the item list (and F2)."""
    layout.use_property_split = False
    notes = []
    if item.item_type == 'IMAGE':
        if item.mask_enabled:
            notes.append(('Mask', 'MOD_MASK'))
        if item.markup_visible and len(item.markup_regions):
            count = len(item.markup_regions)
            notes.append((f'{count} color' + ('' if count == 1 else 's'), 'BRUSH_DATA'))
        if item.mask_editing:
            notes = [('Editing mask', 'GREASEPENCIL')]
        elif item.markup_editing:
            notes = [('Editing colors', 'GREASEPENCIL')]
    elif item.item_type == 'SHAPE' and item.shape_edit_vertices:
        notes.append(('Editing vertices', 'EDITMODE_HLT'))
    if notes:
        row = layout.row(align=True)
        row.alignment = 'LEFT'
        for text, icon in notes:
            row.label(text=text, icon=icon)


LABEL_FACTOR = 0.3   # share of the width the labels on the left take, in every tab


def labelled(layout, label):
    """A row with the label in a fixed-width column on the left; returns the right side."""
    split = layout.split(factor=LABEL_FACTOR, align=True)
    split.label(text=label)
    return split.row(align=True)


def vector_row(layout, label, owner, prop, labels=('X', 'Y')):
    """A labelled row with the two components of a vector property."""
    row = labelled(layout, label)
    row.prop(owner, prop, index=0, text=labels[0])
    row.prop(owner, prop, index=1, text=labels[1])
    return row


def pair_row(layout, label, owner, props, labels=('X', 'Y')):
    """A labelled row with two properties side by side (width and height...)."""
    row = labelled(layout, label)
    for prop, text in zip(props, labels):
        row.prop(owner, prop, text=text)
    return row


def wide_row(layout, label, owner, prop, **options):
    """A labelled row with one field."""
    row = labelled(layout, label)
    row.prop(owner, prop, text='', **options)
    return row
