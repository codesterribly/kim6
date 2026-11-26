# Recipes: Reusable Image Workflows

Recipes let you combine image operations into a saved workflow and run them directly from **Dolphin's KIMng - Recipes menu**. A recipe can handle one image or a batch. KIMng shows what it intends to produce before processing, and **recipes never modify the source images**.

## Start in Dolphin

![KDE Dolphin KIMng - Recipes menu showing Root shortcuts, Run a recipe…, and Recipe editor…](images/screenshots/06-recipes.png)

1. Select one or more supported images and right-click.
2. Open **KIMng - Recipes → Run a recipe…**, then choose **Web Export** or another saved recipe in the recipe selector. A user recipe placed in the **Root** group can also be launched directly from the Dolphin submenu.
3. Review the selected images and the **Run a Recipe** window before starting. Inspect any reported problems, the planned operations, the expected filenames, and the destination.
4. When all files are ready, use the Runner destination selector to keep the recipe default, save beside each source, or choose another directory. Review the resulting filenames and directory before running. The finished results are separate files.

The Recipes menu also provides **Recipe editor…** for creating and managing your own workflows. The runner and editor group recipes under **Built-In**, **Root**, user-created folders, and **Unfiled**. Only user recipes assigned to **Root** are published directly into the Dolphin submenu; folders do not become nested Dolphin menus.

![Run a Recipe displaying readiness and planned outputs](images/screenshots/11-run-recipe.png)

Inspect the selected images, enabled processing steps, planned output filenames, metadata consequences, and destination before running a recipe.

## Web Export: a ready-to-use recipe

The supplied **Web Export** recipe auto-orients images, fits them within **1600 × 1600 pixels** without enlarging smaller images, applies **sRGB** color handling, converts to **JPEG at quality 95**, and **removes all metadata**. It names outputs `{filename}_web.jpg` and saves them in a **Web** subfolder beside each source. The built-in recipe supplies the default Web subfolder, while the Runner allows a per-run destination override without changing that saved default. Originals are unchanged.

This workflow is more than a change of file extension. Its three optional rights-metadata steps, **Set Creator / Artist**, **Set Copyright Notice**, and **Set Usage Rights**, are present but disabled. You can inspect the steps in Recipe Editor. Built-in definitions are protected: **Duplicate to Edit** creates a customizable copy rather than changing the supplied recipe.

### Included recipes

The following recipes are shipped with this checkout. You can duplicate a built-in to customize it.

| Built-in recipe | Description |
|---|---|
| Web Export | Auto-orient, fit within 1600 × 1600 without upscaling, sRGB, JPEG quality 95, strip metadata, and save to a Web subfolder. |

## Web Export preset submenu versus recipe

KIMng provides two distinct Web Export workflows:

- **KIMng - Web Export** offers twelve direct Dolphin presets,
  covering JPEG, PNG, WebP, and AVIF at three maximum
  image sizes (1600, 800, and 128 pixels).
- **KIMng - Recipes → Run a recipe… → Web Export**
  runs the built-in, multi-step recipe.

The built-in recipe auto-orients images, fits them within
1600 × 1600 without enlargement, applies sRGB handling,
converts to JPEG at quality **95**, strips metadata, and
writes `{filename}_web.jpg` into a `Web` subfolder.

These workflows have different configuration and processing
paths. Do not assume their output settings are identical.

## Create and edit recipes

![KIMng Recipe Editor with ordered steps, destination choices, and live output preview](images/screenshots/12-recipe-editor.png)

Open **Recipe editor…** from the Recipes submenu. The Editor uses three resizable panels:

- **Recipes:** Browse and search built-in and user Recipes, manage folders, and import or export definitions.
- **Editing:** Change the Recipe title, optional description, ordered operations, step settings, and output destination.
- **Preview:** Inspect example images, planned filenames, image properties, metadata effects, and publication information.

Each Recipe has a name and an optional multiline description. Descriptions explain what a Recipe does and when to use it. The Recipe search includes descriptions as well as names and folders. Hovering over a Recipe displays its title alongside its description.

Add processing steps, configure their options, arrange them in execution order, and enable or disable individual steps. Disabled steps remain in the definition but are not executed.

Built-in Recipes are read-only. Use **Duplicate Recipe** (toolbar) or **Duplicate to Edit** (context/action control) to create an editable user copy.

When the Editor opens with images already selected in Dolphin, it provides **Run with selected images**. Use **Choose other images & run…** to select another set. The Editor also supports opening without an initial image selection.

### Recipe folders and organization

User Recipes may be assigned to **Root**, **Unfiled**, or a named folder.

- **Root:** Recipes receive direct shortcuts in Dolphin's KIMng Recipes submenu.
- **Unfiled:** Recipes remain available in the Editor and Runner without a folder assignment.
- **Named folders:** Organize Recipes in the Editor and Runner without creating nested Dolphin submenus.

Drag a saved user Recipe onto a valid folder to move it. Valid destinations are highlighted during dragging. Alternatively, select a Recipe and use **Move to Folder…** or its context-menu action.

Built-in Recipes cannot be moved. Moving a Recipe changes its library organization, not its configured image output destination.

The Editor protects unsaved changes when switching or moving Recipes.

### Descriptions and Recipe search

Descriptions support multiple lines and up to 5,000 characters. They are stored with the Recipe and preserved during import, export, and duplication.

The Editor searches Recipe names, descriptions, and folder names. The Runner displays the selected Recipe's description in a read-only **About this recipe** section. Recipes without descriptions do not require that section.

### Import and export

The **Import/Export** dropdown sits below the selected-Recipe management controls and provides four actions:

| Action | Behavior |
|---|---|
| **Import Recipe…** | Import one validated schema 3 Recipe from JSON, assigning a new user Recipe ID. |
| **Export Recipe…** | Export a built-in or saved user Recipe to portable JSON, without its local folder assignment. |
| **Import Recipe bundle…** | Import multiple Recipes and their folder organization from one validated bundle. |
| **Export Recipe bundle…** | Export the saved user Recipe library, including its folder definitions, as one JSON file. |

Individual Recipe exports suggest a descriptive filename containing the Recipe name and an ID suffix. Existing export files are not overwritten.

Individual imports preserve descriptions, operations, and output settings, but create new user identities. Duplicate names can be renamed during import, and existing Recipes are not replaced.

A Recipe bundle preserves the collection's folder organization. On import, matching folder names reuse existing folders; new folder names create new folders. Imported Recipes receive new IDs, and conflicting Recipe names receive an imported suffix. The Editor requests confirmation before saving a bundle import.

Bundle exports contain saved user Recipes rather than built-in definitions. Export files remain separate from the application's active Recipe library.

### JSON schema 3

KIMng currently uses Recipe schema **3** for individual Recipes, the user library, and Recipe bundles. Older schema versions are not supported by this new project.

An individual Recipe contains:

- `schema`: Integer `3`.
- `id`: Recipe identifier.
- `name`: Display name.
- `description`: Multiline plain text.
- `media`: Supported media type, currently `image`.
- `steps`: Ordered operations with their parameters and enabled states.
- `destination`: Output destination configuration.
- `folder`: Optional assignment inside the local user library.

A portable individual Recipe omits `folder`, because another KIMng installation may not have the same folder IDs.

The active user library contains `schema`, `recipes`, and `folders`. Portable bundles additionally identify themselves with `kind: "kimng-recipe-bundle"` and contain `schema`, `recipes`, and `folders`.

KIMng validates imported JSON and Recipe operations before adding them to the user library. Importing never replaces an existing Recipe silently. Recipe definitions do not themselves contain the source image files.

The JSON files are UTF-8. Use the Editor's import/export actions rather than manually editing the active library unless you are deliberately developing or debugging KIMng.

### Processing steps

The Recipe Editor offers **27 operations** in four groups. Each entry below uses the label shown in **Add Operation…**. Some operations have format-dependent parameters or ordering requirements.

#### Geometry & Orientation

| Operation | Behavior |
|---|---|
| **Auto-Orient** | Apply embedded camera orientation to the rendered image. |
| **Crop Image** | Crop the rendered image using the configured geometry or selection. |
| **Flip Image** | Mirror horizontally or vertically. |
| **Resize by Percentage** | Resize by a percentage, including enlargement above 100%. |
| **Resize Long Edge** | Fit the longest dimension to a pixel limit, with optional upscaling. |
| **Resize to Exact Dimensions** | Set both width and height exactly; may stretch the picture. |
| **Resize to Fit** | Fit inside maximum width and height, preserving proportions; optional upscaling. |
| **Resize with Custom Geometry** | Use supported ImageMagick geometry, including fit, fill, and conditional resize. |
| **Rotate** | Rotate through an angle; supports conditional landscape/portrait application. |

#### Format & Color

| Operation | Behavior |
|---|---|
| **Color Profile** | Preserve a supported profile or convert to sRGB. |
| **Compress Image** | Set final compression preset or custom encoder quality, PNG level, and JPEG options. |
| **Convert Format** | Choose output format and applicable encoder options, including JPEG quality. |
| **Add Watermark / Overlay** | Render a text, image, camera-detail, or caption overlay where supported. |

#### Metadata & Copyright

| Operation | Behavior |
|---|---|
| **Remove AI Metadata** | Remove recognized AI-related metadata. |
| **Remove All Metadata** | Remove all available metadata; normalize orientation first if required. |
| **Remove Descriptive Metadata** | Remove descriptive EXIF/IPTC/XMP while keeping the ICC profile and orientation. |
| **Remove GPS Location** | Remove recognized GPS/location metadata. |
| **Set Copyright** | Set creator, copyright notice, and usage rights, inherited or overridden. |
| **Set Copyright Notice** | Set copyright notice, inherited from Settings unless overridden. |
| **Set Creator / Artist** | Set creator/artist, inherited from Settings unless overridden. |
| **Set Usage Rights** | Set usage terms, inherited from Settings unless overridden. |

#### Filenames & Dates

| Operation | Behavior |
|---|---|
| **Adjust Image Capture Date** | Adjust existing camera capture timestamps by a fixed offset. |
| **Change Output Filename** | Transform the planned output name, such as case, prefix, suffix, replacement, sequence, or capture date. |
| **Keep Source File Date** | Preserve the source file modification timestamp on the derivative. |
| **Rename Output File** | Set output filename pattern, for example `{filename}_recipe`; preview includes extension. |
| **Set Image Capture Date** | Use a specific time, embedded capture time, or file mtime as the capture date. |
| **Synchronize File Date** | Synchronize the derivative filesystem date with the planned capture time. |

**JPEG quality is not a separate operation.** Configure quality through **Convert Format** or **Compress Image**. The final encoding options are applied during output creation. Step order matters, especially for orientation, metadata removal, date operations and naming. All operations can be enabled or disabled independently.

### Output filename patterns

In **Rename Output File**, `{filename}` means the original name without its extension. A pattern of `{filename}_recipe` produces `vacation_recipe.jpg` from `vacation.jpg` when the output format is JPEG. The editor shows an output example so you can verify the result without decoding placeholder syntax.

KIMng determines the output extension from the chosen format, so the pattern does not need to repeat `.jpg`, `.png`, or another extension. Output patterns also support `{date}` (capture-date component, when available) and `{index}` (batch position). The preview shows each resolved name; missing required date information blocks that planned name rather than inventing a date.

When a planned output filename already exists, the Recipe planner can choose a free numbered filename **before** Review Changes approval. It also checks for collisions between images in the batch. The final filename is shown in the reviewed output plan. If the planner cannot resolve a conflict safely, the affected result is blocked.

After approval, the filename is binding. If another process creates that target before publication, KIMng blocks the affected output and requires renewed review rather than silently renumbering or overwriting it.

## Preflight and output preview

**Run a Recipe** lists each selected image and provides an output preview for the selected file. With no recipe selected, the files wait for a recipe instead of beginning an unnecessary inspection. After selection, status changes as files are inspected, and each is marked **Ready** or **Problem** as appropriate. The Run button stays disabled until every required preflight check succeeds.

The preview can include the input and output filenames, output folder, format and dimensions, capture-time handling, orientation, metadata handling, and ICC profile information. Disabled steps are visible in the configured operation list but do not affect the output.

The Editor groups preview properties into expandable **Files**, **Image details**, **Metadata**, and **Publication details** sections. Full property values remain available through tooltips and copying even when the columns truncate their display. The expansion state of each group can be remembered.

Adding JPEG and PSD files does not require the interface to freeze until the batch is analyzed: pending filenames appear promptly and input inspection continues in background workers. A large PSD may still take time to decode, but the window remains usable.

## Photoshop PSD inputs and Fix Recipe

KIMng can **read** PSD images in supported workflows but **does not create PSD output files**. If a selected PSD lacks a valid output format in the recipe, preflight reports a problem and offers **Fix recipe…**. This opens the existing editor so you can add **Convert Format** and select a supported output type. KIMng does not silently choose a format on your behalf.

After saving a correction and returning, preflight starts again using the updated recipe. Closing the editor without saving keeps the existing recipe and diagnostic. For a protected built-in recipe, duplicate it before editing. The source PSD remains unchanged.

PSD inputs are treated as rendered image sources rather than editable Photoshop documents with preserved layers. Color-profile and precision handling depend on the input and the selected output format. See [Image and Video Format Support](FORMATS.md#photoshop-psd-inputs) for details.

## Destinations, safety, and cancellation

Recipes are **derivative-only**. They do not offer in-place modification or overwrite of source images. The recipe's configured destination and exact output names appear before processing. Destination modes include beside each original, a named subfolder beside each original, and one directory (fixed or chosen when running). The Runner always presents a destination override selector with **Use recipe default**, **Beside each source**, and **Choose another directory…**; the user can retain the recipe setting without modifying the saved recipe. Existing filenames and duplicate batch targets are resolved during planning when safe numbering is available. Unresolved conflicts block approval. Execution uses the frozen reviewed source identities, exact output paths and operations. A target created after review blocks that output without renaming it; earlier successful outputs remain in place.

Recipes and standalone Crop stage complete derivatives privately on the destination filesystem and publish them with an atomic no-replace hard link. Filesystems or permissions that cannot support this publication fail closed; KIMng does not write a partial image directly to the final filename. Source or destination identity changes require a new review. Cancellation and failures remove private stages while retaining published outputs; a durability-sync failure after publication is reported as a warning alongside the created path. Support for exFAT, FAT32, NTFS and network destinations must be verified individually.

File inspection, required encoder checks, and the preflight plan must succeed before a run begins. A failed or cancelled operation must not be reported as a completed publication. Successfully committed outputs can remain available if a later file in the batch fails or the user cancels.

## Completion messages and diagnostic details

Publication tools such as PDF Album can show a compact completion window with the saved output path, **Open folder**, and **Done**. Where there is additional information about the source files, **Details (N)** expands to grouped, selectable diagnostics with **Copy Details**. The details control is omitted when there is nothing to disclose. Informational details are not necessarily failures. Successful background publications can finish without a separate completion dialog when there are no source advisories. A publication failure is reported through the existing error path, not as a success notice. Previously published outputs remain available when a later item fails.

## Current scope

Recipes currently process images. Video recipes, visual thumbnail previews, and in-place recipe operations are not part of this workflow. The text/table output preview reports planned results rather than attempting to simulate every rendered pixel.

For the exact Dolphin entry points, see [Dolphin Menu Actions](ACTIONS.md). For global output settings, see [Command and Configuration Reference](commandconfig.md). The [illustrated User Guide](index.html#recipes) starts with the Recipes menu in Dolphin.
