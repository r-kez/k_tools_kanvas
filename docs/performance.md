# Performance and memory

Kanvas is designed to handle boards with hundreds of images. This page explains what it does for you, and what you can adjust.

## What Kanvas does automatically

- **Draws only what is visible.** Items outside the view are skipped, and images far too small to see are not drawn.
- **Reuses work.** Text layouts, Markdown, color masks, and image shapes are cached, so a redraw costs little when nothing changed.
- **Keeps images loaded.** Textures stay in video memory, so zooming out over a large board does not reload them. They are released only when idle for a long time, or when the memory budget is exceeded. The least recently used images go first.
- **Avoids permanent background tasks.** Kanvas does not keep a modal operator running, so Blender's **auto save** keeps working. Blender postpones auto save only while you are in the middle of a drag, a transform, or a Mask or Color editing session.

## Image resolution

Images are the biggest cost. The defaults already limit new images to 1080 pixels on the longest edge and convert them to 8 bits. See [Images](images.md#resolution-and-memory).

| If your board is... | Try |
| --- | --- |
| Slow with many large images | Keep **Optimization** on and lower **Max Resolution** to 720p |
| Showing banding or low detail on a few images | Raise **Max Resolution**, then use **Reload Image Source** on those images |
| Using too much video memory | Lower the **Texture Memory Budget** |
| For references that need HDR | Turn **Force 8-bit Depth** off |

These settings apply to **new** imports. Use **Reload Image Source** to re-import existing images.

## Texture Memory Budget

**Texture Memory Budget (MB)** in **Preferences > General > Memory Optimization** is the estimated video memory Kanvas may keep loaded. The default is 2048 MB.

- With a budget large enough for the whole board, zooming out is smooth.
- With a smaller budget, Kanvas releases the images you have not looked at recently when the limit is passed. They reload when you return to them, which can cause a brief pause.

As a guide, an image whose longest edge is 1080 pixels typically uses about 3 to 4 MB of video memory, and larger images use proportionally more. The budget is an estimate, so set it comfortably below the video memory of your graphics card, leaving room for Blender itself.

Blender also has its own **Preferences > Viewport > Textures > Limit Size**, which reduces texture resolution everywhere, including in Kanvas.

## Tips for large boards

- Use **frames** and hide groups you are not working on. Hidden items are not drawn.
- Use **Move mode** to browse a finished board, so a stray click cannot move or change anything.
- Keep text cards a reasonable size. Very long Markdown documents are cached, but they cost more to build.
- If memory seems stuck after heavy use, run **Clear GPU Cache** from the **Debug** panel. Textures are rebuilt as needed.

## The Debug panel

Turn on **Show Debug Panel** in **Preferences > General > Interface** to see:

| Button | What it does |
| --- | --- |
| **Reload Custom Shader** | Rebuilds the drawing shader |
| **Clear GPU Cache** | Discards cached textures |
| **Reset All Settings** | Clears the current board and restores default settings. This removes content, so use it with care |

It also has **Show Grid**, which draws the origin axes, and **Show Hitbox Debug**, which outlines the transform handle areas.

## Next

- [Troubleshooting](troubleshooting.md)
