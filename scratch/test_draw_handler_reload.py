"""Check legacy visibility compatibility and handler replacement on reload."""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import k_tools_kanvas as addon
from k_tools_kanvas.utils.kanvas_data import get_settings
from k_tools_kanvas.utils.gpu import KanvasDrawHandler


addon.register()
try:
    settings = get_settings(bpy.context)
    assert settings.show_all is True
    registry = bpy.app.driver_namespace
    key = KanvasDrawHandler._registry_key
    first = registry[key]

    # A new module version starts with empty class attributes but can still
    # remove the previous version's handlers via the shared registry.
    KanvasDrawHandler._handler = None
    KanvasDrawHandler._label_handler = None
    KanvasDrawHandler.add_handler()
    second = registry[key]
    assert second != first
    assert second == (KanvasDrawHandler._handler, KanvasDrawHandler._label_handler)
    print('DRAW HANDLER RELOAD PASS')
finally:
    addon.unregister()
