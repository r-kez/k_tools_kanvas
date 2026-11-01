# Kanvas Architecture Plan: Memory & VRAM Optimization

## Objective
Stabilize the Kanvas addon for high-volume image loading (e.g., 85+ images) and prevent VRAM exhaustion (`EXCEPTION_ACCESS_VIOLATION`) by implementing a robust Level of Detail (LOD) and Viewport Culling pipeline natively within Blender (No external dependencies like PIL).

---

## Phase 1: Native LOD System (RAM Stabilization)
**Goal:** Prevent massive system RAM spikes when importing dozens of high-resolution images.

**Implementation Strategy:**
1. **Intercept the Import Operator (`add_image_to_kanvas`):**
   - When importing an image, load it temporarily via `bpy.data.images.load()`.
2. **Generate Native Thumbnail:**
   - Check the resolution. If the longest edge exceeds a threshold (e.g., `MAX_THUMB_SIZE = 1024`), calculate the scaled dimensions.
   - Use `image.scale(new_w, new_h)`.
3. **Data Packing & Cleanup:**
   - Create a copy of the scaled image (`img.copy()`) and prefix the name with `thumb_`.
   - Pack the thumbnail (`thumb_img.pack()`) so it persists natively.
   - **Crucial:** Call `bpy.data.images.remove()` on the original full-res image immediately after copying to purge it from RAM.
4. **Property Management:**
   - Add a `filepath` string property to the `KanvasImage` PropertyGroup to store the original source path.
   - Point `image_data` to the new `thumb_` image.

---

## Phase 2: Dynamic VRAM Eviction (GPU Stabilization)
**Goal:** Ensure that only images visible to the user consume GPU Video RAM.

**Implementation Strategy:**
1. **Viewport Culling Logic:**
   - Inside the GPU rendering loop (`draw_callback_px`), calculate the exact boundaries of the current Node Editor Viewport using `context.region` and `context.space_data.v2d`.
2. **Visibility Check:**
   - For each `KanvasImage` in the loop, check its spatial coordinates (Location + Dimensions * Scale) against the Viewport boundaries.
3. **Execute `gl_free()`:**
   - If an image is 100% outside the visible viewport, execute `item.image_data.gl_free()`.
   - *Technical Note:* This natively purges the texture from VRAM. The `bpy.data.images` entry remains intact in system RAM. When the user pans back to the image, Blender's internal drawing routine will automatically reload the texture into VRAM on the next frame.

---

## Phase 3: Lazy Loading / LOD Upgrade (Optional Detail Enhancement)
**Goal:** Allow users to view pixel-perfect details of an image without permanently hogging memory.

**Implementation Strategy:**
1. **State Tracking:**
   - Add a boolean `is_full_res` to the `KanvasImage` PropertyGroup.
2. **Trigger Mechanism:**
   - Implement a threshold trigger. This can be based on Camera Zoom (e.g., if the user zooms very close to a specific image) or an explicit user action (e.g., a "Load Full Res" button on the UI/Hover).
3. **The Swap:**
   - When triggered, read the original `filepath`.
   - Load the full-res image via `bpy.data.images.load(filepath)`.
   - Swap the `image_data` pointer to the full-res image.
   - Set `is_full_res = True`.
4. **Downgrade / Cleanup:**
   - If the user zooms out or the image is evicted (Phase 2), delete the full-res version from `bpy.data` and revert the `image_data` pointer back to the `thumb_` version.

---

## Technical Considerations & Guidelines
- **Modularity:** Ensure the `create_native_thumbnail` and visibility math are abstracted into utility functions inside the `utils/` directory, rather than bloating the main operator or drawing loop.
- **Performance Overhead:** The visibility check (AABB collision) must be highly optimized since it runs every frame during pan/zoom. Use simple math (min/max boundary checks).
- **Zero Dependencies:** This architecture completely avoids `PIL/Pillow`, ensuring the addon remains plug-and-play for all users.
