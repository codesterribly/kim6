# Getting started with KIM6

KIM6 adds common photo and video actions to Dolphin's right-click menus. These examples use the visible menu labels in the current KIM6 menus. Output names below assume the default suffix position. If you set prefix position, the action tag appears before the filename instead. If an action asks what to do with the result, choose **Create new** to keep the selected originals unchanged. A saved `KIM_POLICY` preference can choose this automatically or skip the question. If it is set to `overwrite`, use a disposable copy for these examples or change the preference to `create` first. See [Safe handling of originals](SAFETY.md) if you are unsure.

## A. Resize a photograph

1. In Dolphin, select `lake.jpg`.
2. Right-click and choose **KIM6 — Compress, resize and web export → Resize (1600x1600 pixels)**.
3. If asked, choose **Create new**.

For a larger image, the size is a maximum width and height, and the photograph keeps its shape. This resize action can enlarge a smaller image. The new file appears beside the selected image as `lake_resized.jpg`. If that name is already used, KIM6 adds a number, such as `lake_resized_1.jpg`. The selected original is unchanged in Create new mode. If you choose to replace it, KIM6 updates the selected file after the new image has been checked.

## B. Make a JPEG copy for sharing

1. Select `lake.jpg`.
2. Right-click and choose **KIM6 — JPEG compression → JPEG quality: 70%**.
3. If asked, choose **Create new**.

KIM6 creates `lake_compressed.jpg` beside the selected file. If the name is taken, it adds a collision number. JPEG quality controls the image encoding; it is not a size percentage, and a smaller file is not guaranteed. Create new leaves the original unchanged. Choosing replacement changes the selected JPEG after validation.

## C. Convert a PNG photograph to JPEG

1. Select `garden.png`.
2. Right-click and choose **KIM6 — Convert and transform → Convert to JPEG**.
3. If asked, choose **Create new**.

The output is `garden.jpg` in the same folder. If that filename is occupied, KIM6 uses a numbered name such as `garden_1.jpg`. Create new leaves `garden.png` untouched. JPEG does not support transparency and is a lossy format, so use a photograph without transparent areas when converting to JPEG. Choose replacement only if you intend to replace the converted destination shown by the action.

## D. Remove GPS coordinates

1. Select `trip.jpg`.
2. Right-click and choose **KIM6 — Publish and organize → Remove GPS coordinates…**.
3. If asked, choose **Create new**.

If `trip.jpg` contains recognized GPS coordinate fields, KIM6 creates `trip_gps.jpg` beside it, with collision numbering if needed. If there is nothing to remove, it reports the item as unchanged and makes no copy. GPS removal does not remove all metadata and cannot guarantee complete location anonymization. Create new keeps the selected original unchanged. Choosing replacement updates the selected file after metadata and image checks.

## E. Process several photographs together

1. In one Dolphin folder, select `lake.jpg`, `garden.jpg`, and `portrait.jpg`. Use Ctrl-click or a selection rectangle to choose several files.
2. Right-click and choose **KIM6 — Compress, resize and web export → Resize (800x800 pixels)**.
3. If asked, choose **Create new**.

KIM6 applies the same size limit to each selected photograph. New files appear in that folder as `lake_resized.jpg`, `garden_resized.jpg`, and `portrait_resized.jpg` (with numbers added to names that are already occupied). The originals are unchanged in Create new mode. KIM6 reports failed items; outputs that finished before a later failure remain available.

## If something does not work

Restart Dolphin after installation. If the action is missing, check [INSTALL.md](../INSTALL.md) for the menu location and the KDE Frameworks/KIO 6.29 submenu issue. If an action reports a missing tool or format, that tool or codec may not be installed; see [Formats and codecs](FORMATS.md). Keep your original files and try again with a copy if you are uncertain about an output choice.
