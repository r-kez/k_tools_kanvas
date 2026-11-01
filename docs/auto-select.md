# Auto Select

**Auto Select** picks a subject with a click, much like *Select Subject* in a photo editor. Click a person, an object, or a screen element, and Kanvas outlines it so you can reveal it in a [mask](masks.md) or paint it in [Color Markup](color-markup.md).

It is **optional and off by default**. Nothing is downloaded, installed, or run until you ask for it.

## How it works

Auto Select uses a small segmentation model (MobileSAM, a compact version of Meta's *Segment Anything*) that runs **entirely on your computer**. Your images are never uploaded anywhere.

The work is split in two:

1. **Analyze Image** runs once per image and takes about half a second to a second on a modern CPU.
2. After that, every click takes a few hundredths of a second.

## Setup (once)

Open **Preferences > Add-ons > K-Tools: Kanvas > General** and find **Auto Select**.

| Step | What it does | Size |
| --- | --- | --- |
| **Install** (ONNX Runtime) | Installs the runtime that executes the model, with `pip`, into the add-on's own data folder. Nothing is installed into Blender itself | about 50 MB |
| **Download** (model) | Downloads the model files from huggingface.co | about 45 MB |

Each button asks for confirmation first, shows progress, and reports problems in plain text. The total is about **95 MB** on disk. The folder is shown in the preferences, together with a **trash** button that removes everything.

The model files are licensed Apache-2.0.

> Both downloads use the internet. If Blender's **Allow Online Access** option is off (**Preferences > System > Network**), Kanvas will not download anything and will tell you so.

## Using it

1. Select an image and click **Analyze Image** in the **Auto Select** box of the **Mask** or **Markup** subpanel. The button reads *Analyzing...* until it is done. The first analysis also loads the model, so it takes a little longer.
2. Enter [Mask](masks.md) or [Color](color-markup.md) mode.
3. Choose the **Auto Select** tool (`A`, `Tab`, or the panel button). It is available once the image is analyzed.
4. Click on what you want.

| Action | Result |
| --- | --- |
| Click | Include the area under the pointer |
| `Ctrl + click` | Exclude an area (use it to refine the result) |
| `Backspace` | Remove the last point |
| `Enter` | Apply the selection |
| `Esc` | Clear the points. Press again to leave the mode |

The outline updates after each click. Green dots mark included points and red dots mark excluded ones. The first point always includes.

When you apply the result:

- In **Mask** mode it reveals the area. In **Color** mode it paints the active region.
- Hold `Alt`, or switch to erase with `E`, to erase the area instead.
- The whole selection is **one** Undo step.

> **Holes:** when painting or revealing, holes inside the selection stay empty. When you **erase**, holes are not applied, because Kanvas cannot know what was there before. A message tells you when this happens.

## Tips

- Click the center of the subject first. If part is missing, add another click there. If too much is selected, `Ctrl + click` on what should be left out.
- Auto Select works on the image **as it is stored on the board**, at its stored resolution. Details smaller than a few pixels in that copy may not be selected.
- The analysis stays in memory for the images you used recently (up to eight). If you replace the image, change its source, or change its size, press **Analyze Again**.
- Uses the CPU. It does not need a powerful graphics card.

## Limits

- It is a general-purpose model. Very thin objects, glass, and busy or low-contrast edges may need extra clicks.
- It has been tested on Windows with Blender 5.1. The runtime packages come from PyPI, and a package may not exist for every Python version, system, or architecture. If installation fails, the message in the preferences says why.
- Very large images are reduced before analysis, so the analysis time stays about the same for any image size.

## Removing it

Click the **trash** button in the **Auto Select** section of the preferences. This deletes the runtime and the model. Masks and colors you already made are kept.

## Next

- [Image masks](masks.md)
- [Color Markup](color-markup.md)
- [Troubleshooting](troubleshooting.md)
