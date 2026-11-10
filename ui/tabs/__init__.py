"""Tabs of the Selection panel: one module per tab, chosen by the kind of item.

Each kind with tabs (image, shape, text card) has an enum on the window manager
(`KanvasPanelTabs`, session only) and a table here naming the module that draws each
tab. The panel draws a short header (`common.draw_header`), the tab bar, and only the
open tab, so the panel stays short however many options an item has. Items with few
options (frames, groups, comparison cards) are drawn without tabs by `ui/sections`.

A tab module has one function, `draw(layout, context, settings, item)`.
"""

from importlib import import_module

# kind -> {tab identifier: module name in this package}
TABS = {
    'image': {'MAIN': 'image_main', 'ADJUST': 'image_adjust',
              'MASK': 'image_mask', 'MARKUP': 'image_markup',
              'MEASURE': 'image_measure'},
    'shape': {'MAIN': 'shape_main', 'FILL': 'shape_fill',
              'LINE': 'shape_line', 'TEXT': 'shape_text'},
    'text': {'CARD': 'text_card', 'CONTENT': 'text_content'},
}

# Below this sidebar width (in unscaled pixels) the tabs show only their icons; the
# name stays in the tooltip.
ICON_ONLY_WIDTH = 220


def tab_kind(item):
    """Which tab set an item uses, or None for items drawn without tabs."""
    if item.item_type == 'SHAPE':
        return 'shape'
    if item.item_type == 'TEXT':
        return None if item.text_compare else 'text'
    if item.item_type == 'IMAGE':
        return 'image'
    return None


def current_tab(context, kind):
    tabs = getattr(context.window_manager, 'kanvas_tabs', None)
    tab = getattr(tabs, kind, None) if tabs is not None else None
    return tab if tab in TABS[kind] else next(iter(TABS[kind]))


def draw_tab_bar(layout, context, kind):
    tabs = context.window_manager.kanvas_tabs
    region = getattr(context, 'region', None)
    scale = getattr(getattr(context, 'preferences', None), 'view', None)
    scale = getattr(scale, 'ui_scale', 1.0) or 1.0
    narrow = region is not None and region.width / scale < ICON_ONLY_WIDTH
    row = layout.row(align=True)
    row.scale_y = 1.2
    row.prop(tabs, kind, expand=True, icon_only=narrow)


def draw_tabbed(layout, context, settings, item):
    """Header, tab bar and the open tab of an item. False for items without tabs."""
    kind = tab_kind(item)
    if kind is None:
        return False
    from .common import draw_header
    draw_header(layout, settings, item)
    draw_tab_bar(layout, context, kind)
    layout.separator(factor=0.6)
    module = import_module(f'.{TABS[kind][current_tab(context, kind)]}', __name__)
    module.draw(layout.column(), context, settings, item)
    return True
