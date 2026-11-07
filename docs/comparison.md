# Comparing two images (A/B)

A **comparison card** shows two images from your board side by side, split by a divider. Use it to check a before and after, two versions of a paint-over, or a photo against its reference.

## Creating one

Use **Add > Compare A/B**. The card appears at the pointer, or at the center of the view. It moves, resizes, locks, snaps, and joins frames like any other card.

## Choosing the images

The card has three buttons in its top-right corner: **Split** (the mode), **A**, and **B**.

1. Click **A**. The cursor becomes an eyedropper.
2. Click an image on the board. It becomes A.
3. Do the same for **B**.

**Shift+click** clears a side. **Esc** or right-click cancels. A button turns solid once its side has an image. The same pickers are in the **Selection** panel, next to **Flip A / B**, which swaps the two images without picking them again.

The card points at the images, it does not copy them. The originals stay where they are, and the card is drawn exactly like the board, so an image looks the same in both places. If you changed an image's brightness, contrast, saturation, or tint, the card shows those changes too. The card does not apply an image's mask or Color Markup, and ignores its rotation and shear. Each image keeps its proportions and is centered in the card, so images of different shapes get empty space around them instead of being stretched.

## Modes

Click the mode button to cycle, or choose **Mode** in the **Selection** panel.

| Mode | What it shows |
| --- | --- |
| **Split** | A on the left of a divider and B on the right. **Drag the divider** directly on the card, or set **Divider** in the panel |
| **Fade** | B drawn over A. Set **B Opacity** in the panel |
| **Difference** | Black where A and B match, brighter where they differ. Use **Amplify** to make small differences easier to see. Needs both images; the images are compared where they overlap on the card |

If your graphics driver cannot build the Difference shader, the card falls back to Fade and prints a note in the console.

## Broken references

If you delete an image that a card uses, that side shows **Pick A** or **Pick B** again. **Check Board** lists these cases and clears them. It never deletes anything.
