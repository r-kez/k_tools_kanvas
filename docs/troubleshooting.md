# Troubleshooting

## The canvas

**Clicking does nothing, or the left mouse button only pans the canvas.**
The board is in **Move** mode. Press `Tab` over the canvas, or click **Edit** in the switch at the top of the canvas or in the editor header. In Edit mode the left button selects and edits. See [Interface and navigation](interface.md#edit-and-move-modes).

**A shortcut does nothing.**
- The pointer must be over the canvas of a **Kanvas Tree**. Shortcuts are ignored in other editors, over the sidebar, and over the header.
- Inside **Mask** or **Color** editing, some keys have different meanings. For example, `Tab` switches tools instead of the mode. See the [reference](shortcuts.md#mask-and-color-editing).
- You may have changed or disabled the shortcut in **Preferences > Controls**.
- A text field in Blender's interface may have keyboard focus. Move the pointer back to the canvas.

**The mouse wheel zooms instead of scrolling a long text card.**
By default the wheel scrolls a card only while it is **selected**, so click the card first and keep the pointer over it. A card whose text fits entirely never takes the wheel. To scroll any card you hover over, or to turn the feature off, change **Scroll Text Cards with Wheel** in **Preferences > Controls**. In **Move** mode the wheel scrolls any long card under the pointer.

**`Ctrl`, `Shift`, or `Alt` + wheel does something different from what Blender usually does.**
Inside a Kanvas Tree these change an image's opacity, scale, and layer (see [Selecting and transforming](transforms.md#quick-adjustments-with-the-wheel)). They need an image to act on. You can reassign the modifiers in **Preferences > Controls**.

**I cannot select an item.**
It may be **locked**, **hidden**, or inside a locked frame. Check the lock and eye icons in the item list.

**The Edit | Move switch is not at the top of the canvas.**
It is hidden when the canvas is very narrow, or when **Show Edit/Move Overlay** is off in the preferences. `Tab` and the header buttons still work.

**The board looks empty.**
Your content may be outside the view. Click **Recenter** in the middle of the canvas, or press `Numpad .` to frame the selection.

## Images

**An image shows as missing.**
External image files could not be found. The item list shows a count and a **Relink** button, which searches a folder you choose. See [Images](images.md#missing-files-and-relinking).

**Kanvas images do not appear in Blender's image picker.**
This is intentional. Kanvas hides its own images from lists. They are still in **Outliner > Blender File > Images**. To list them normally, turn off **Hide Kanvas Images in Blender Lists** in the preferences.

**"Save the .blend" or the assets folder cannot be created.**
The default assets folder is relative to the `.blend` file, so the file must be saved first. Save it, or choose an absolute **Assets Folder** in the preferences.

**`Ctrl + V` does not paste an image.**
- Pasting copied **pixels** and copied **files** is supported on Windows only. On other systems, copy a file's **path** as text.
- Web addresses are not downloaded. Save the image and drag it in.
- Pasting is disabled while you edit a mask or colors.

**Imported images are lower quality than the originals.**
New images are reduced to the **Max Resolution** (1080p by default) and stored as 8-bit. Change these in the preferences, then use **Reload Image Source** on the images you want to refresh.

## Cards and checklists

**The eye icon is missing from a checklist.**
The eye only appears when the checklist is **linked to at least one image**. See [Color Markup](color-markup.md#linking-a-checklist-to-an-image).

**A link in a card does not open.**
Hold `Ctrl` and click. Only `http` and `https` links open.

## Masks and colors

**Region names do not show on the image.**
**Names** is off by default for each image. Turn it on in the **Markup** subpanel. Names are also hidden while you paint, on very small images, and behind text cards.

**The colors vanished.**
Check the **Markup** checkbox in the subpanel header, the eye on the region, and whether **Isolate Color** is showing a different region. Press `\` to show all.

**Mask or color edges look soft on a large image.**
Masks and color layers are stored at up to 512 pixels on the longest side, so very fine details can look soft on very large images.

## Auto Select

**The Install or Download button reports an error.**
- Read the message under the button. It reports what `pip` or the download said.
- If it mentions online access, enable **Preferences > System > Network > Allow Online Access**.
- Installation needs internet access and a `pip` that works with Blender's Python. Some systems or Python versions may not have a matching ONNX Runtime package.

**The Analyze Image button is disabled, or the tool is missing.**
Both the **ONNX Runtime** and the **model** must be installed, and the image must be **analyzed** before the tool can be chosen. See [Auto Select](auto-select.md).

**"The analysis expired."**
The image changed (size or source) or its analysis was dropped from memory. Press **Analyze Again**.

**The selection is wrong or incomplete.**
Add a click inside the missing part, or `Ctrl + click` on what should be left out.

## Performance

**Zooming out is slow the first time, then fast.**
Images are loaded to the graphics card as they come into view. A budget that is too small makes Kanvas release and reload them. See [Performance and memory](performance.md#texture-memory-budget).

**The board is slow overall.**
See the tips in [Performance and memory](performance.md).

## Saving

**Blender did not auto save while I was working.**
Blender postpones auto save while a modal operation is active, for example in the middle of a drag, a transform, or a Mask or Color editing session. Finish the operation, and it saves normally. Kanvas does not keep any operation running in the background.

## Still stuck?

- Turn on **Show Debug Panel** in the preferences. **Clear GPU Cache** and **Reload Custom Shader** rebuild what Kanvas draws, which fixes most display glitches.
- Look for messages that start with `Kanvas` in Blender's system console (**Window > Toggle System Console** on Windows).
- Report the problem with your Blender version, your operating system, and the steps that cause it.
