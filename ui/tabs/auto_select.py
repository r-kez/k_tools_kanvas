"""Auto Select box shared by the Mask and Markup tabs."""


def draw_auto_select(layout, img, tool_property):
    """Analyze button and tool toggle for Auto Select (explicit, opt-in)."""
    from ...utils import sam_engine
    column = layout.box().column(align=True)
    column.label(text="Auto Select", icon='VIEWZOOM')
    if not sam_engine.ready():
        column.label(text="Install it in Preferences > General", icon='INFO')
        return
    analysis = sam_engine.snapshot('analyze')
    working = analysis['state'] == 'working'
    analyzed = sam_engine.is_analyzed(img.image_data)
    row = column.row(align=True)
    row.enabled = not working
    row.operator("kanvas.sam_analyze_image",
                 text=("Analyzing..." if working
                       else "Analyze Again" if analyzed else "Analyze Image"),
                 icon='VIEWZOOM')
    tool = column.row(align=True)
    tool.enabled = analyzed
    tool.prop_enum(img, tool_property, 'AUTO', text="Auto Select Tool (A)")
    if analysis['state'] == 'error':
        column.label(text=analysis['message'][:60], icon='ERROR')
