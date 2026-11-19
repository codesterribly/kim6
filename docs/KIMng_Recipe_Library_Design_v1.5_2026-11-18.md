# KIMng Recipe Library, Built-in Workflows and Browser Redesign

**Design specification v1.5 | November 18, 2026**\
**Status:** Design baseline ready for controlled implementation after the Phase 0 read-only audit. Integrates three independent Gemini review rounds and final engineering corrections. Phase 0 findings can require targeted amendments. Explicit approval is required for each coding milestone; this document is not implementation authorization.\
**Repository:** https://github.com/codesterribly/kim6\
**Branch:** `recovery/kim-all`\
**GitHub branch commit inspected:** `7a2bc2748e31935d8865a631bbc903491424cdf1` (November 18, 2026).\
**Source precedence:** Natacha's full current working tree remains authoritative when actual editing begins. This document uses the current committed branch for its read-only architectural assessment, not the November 3 backup.

## 1. Executive summary

KIMng should turn its existing declarative Recipes feature into a small curated library and a practical user-managed collection, without becoming a full digital asset management application. The **two permanent browser roots are `Built-ins` and `User`**. Built-ins are organized by audience (Everyday, Hiker, Digital asset manager); users can create nested folders, organize personal recipes freely, and install externally shared recipes under `User / Imported` by default.

Both **Recipe editor** and **Run a recipe** must provide a readable, resizable, searchable recipe tree. A single shared search contract indexes **entire recipe names, full 0–255-character descriptions (including built-in local overrides), and all ancestor folder names**. Descriptions are editable for personal recipes. Local description-only overrides are permitted for built-ins, but shipped operation definitions are immutable. The editor provides **Import…** and **Export…** for individual recipes and multi-recipe collections using **one bounded, versioned JSON exchange envelope**, not ZIP packages.

**Folder location and Dolphin publication must be independent**: a user recipe may live anywhere under User and optionally be pinned directly to Dolphin via a separate flag. Existing special-Root shortcuts must migrate without losing their menu entries. Imported recipes never acquire menu shortcuts automatically.

The existing **Web Export** recipe and all accepted behavior must remain intact. KIMng's mandatory **Review Changes** gate, create-only publishing, source integrity, and exact approved destination/filename requirements apply to every recipe. Current planner code can number an occupied name and warns that it might change at publication: that behavior must be isolated and corrected before accepting expanded recipe publication. Add built-ins one at a time only after their individual operations are verified safe. Candidate recipes that require multi-output, date sequencing, or unimplemented print features stay in the design as deferred proposals.

This specification incorporates three technical critiques from Gemini but distinguishes **confirmed source observations, accepted product decisions, and proposed implementation methods**. It is not an authorization to code.

## 2. Decision status and scope

### Product requirements retained

- Exactly two permanent top-level tree roots: **Built-ins** (managed) and **User** (user-managed).
- Built-ins initially categorized **Everyday**, **Hiker**, and **Digital asset manager**. Additional categories are permitted.
- Arbitrarily organized nested user folders within a reasonable validated depth. Folders are not Dolphin submenus.
- Prominent, readable recipe/folder tree in both editor and runner, with resizable panes, visible paths, keyboard support, and saved size/expansion preferences.
- One shared case-insensitive **multi-token AND search over full name + complete description + full ancestor path**, across both roots by default. Description-only matching is mandatory.
- Description max **255 Unicode code points after newline normalization**, with live counter and robust import/storage validation.
- Editable personal descriptions **and editable local overrides to built-in descriptions**, without modifying built-in steps. Restore shipped text on demand.
- Safe individual and package-like collection sharing through **Import… / Export…** in Recipe editor; default import target `User / Imported`; no automatic execution or shortcut installation.
- Explicit per-user **Show in Dolphin menu** property, independent of recipe folder. Existing Root shortcuts preserved through migration.
- Derivative-only execution, mandatory Review Changes, atomic safe publishing, and no unapproved output renaming after review.

### Engineering decisions adopted from review

- One bounded declarative `.kimng-recipes.json` exchange document for one or many recipes. **No ZIP support in this milestone**.
- A unified folder-and-recipe navigation tree instead of separate cramped tree/list panels in the editor; preserve existing steps and live preview.
- A carefully staged **schema-v2 migration**, with a safe original-config backup before the first v2 write and schema-1 in-memory read compatibility. Do not attempt to make old releases parse future schema 2.
- Keep existing recipe field `folder` (folder ID) to reduce call-site churn; add `dolphin_shortcut` independently.
- Prefer one pure-Python shared catalog/search layer and a reusable `QTreeWidget` browser; introduce a custom Qt model/proxy only if measured requirements demand it.
- Require a collapsible preview or equivalent constrained-width arrangement at 1366×768, and keep action buttons accessible.
- Define folder deletion and import destination handling deterministically before code.
- Separate menu pinning from folder membership; a folder node is never a fake shortcuts folder.
- Select Qt's simplest maintainable shared tree/search architecture after actual UI measurements. `QTreeView` with models/proxy is a candidate, not an unconditional requirement; `QTreeWidget` remains viable if behavior is correct.
- Privacy recipes must pass a cross-namespace metadata and color-management verification before release.

### Constraints and unresolved choices

- UI geometry, the precise Qt widget implementation, and final resource ceilings require Phase 0 measurement and testing. The behavioral contracts in this specification are requirements; proposed implementation mechanisms must not be mistaken for verified existing code.
- The source safety collision discrepancy is a **distinct prerequisite defect** requiring its own acceptance, not permission to refactor publication in the browser phase.
- Do not invent missing primitives for chronological trip sets, multi-output DAM derivatives, print crop/pad workflows, or GPS approximation. Defer until verified/approved.
- No marketplace/network client, third-party code execution, nested Dolphin service menus, video recipe engine, new metadata writer, new GPS subsystem, or automatic AI image enhancement.
- Previously cancelled target-file-size compression and output size estimation remain cancelled.

## 3. Verified branch architecture and present limitations

The following were inspected directly from the current committed GitHub `recovery/kim-all` branch, **not** inferred from screenshots or an old archive:

| File | Verified current behavior | Consequence |
|---|---|---|
| `src/bin/kim_recipe_core.py` | Recipe schema 1 requires `schema`, `id`, `name`, `media`, `steps`, `destination`; only `folder` is optional. Strict `keys()` rejects unknown recipe fields. | `description` cannot simply be added in UI; validator, persistence and tests must change together. |
| Same | Library schema 1 contains `recipes` and `folders`; folder records require only `id` and `name`. | Nested folders need explicitly designed parent linkage and validation/migration. |
| Same | Folder names are unique globally and folder management is flat; `create_folder` has no parent, `delete_folder` unfiles member recipes. | Introduce scoped sibling uniqueness, cycle prevention, and a deliberate deletion policy. |
| Same | `ROOT_FOLDER = '@kimng-root'`, user recipe Root shortcuts, and `library_groups()`'s `Built-In`, `Root`, ordinary folder, `Unfiled` presentation groups. | Two new top-level roots must **not silently delete or reinterpret existing Root shortcuts**. |
| Same | Built-in definitions must be unfiled and are loaded from `src/recipes/builtins.json`; user library is in XDG config `kimng/recipes.json`. | Built-in categorization needs a new supported mechanism, not simply adding `folder` to built-ins.json without changing validation. |
| `src/recipes/builtins.json` | One supplied built-in, `web-export`, with auto-orient, fit to 1600×1600, sRGB, JPEG quality 95, strip-all metadata, disabled rights-writing steps, `_web` naming, `Web` subfolder. | Preserve this actual definition unless its behavior is separately approved for change. Do not confuse it with separate Web Export menu presets. |
| `src/bin/kim_recipe_dialog.py` | Editor has compact `QComboBox` selector, `Recipe folder` combo, create/rename/delete folder buttons, and `QSplitter` between editor controls and Preview. It protects unsaved changes and built-in operations. | Add an understandable tree without destroying the operation editor, preview, or unsaved-change checks. Existing splitter space must be managed. |
| `src/bin/kim_recipe_run.py` | Runner has `QLineEdit` labeled `Search recipes or folders…` and grouped `QComboBox` selector. `refresh_selector()` matches case-folded query against folder label and recipe name, **not descriptions**. | Expand search explicitly to complete descriptions and hierarchical paths, preferably through one shared browser/search model. |
| `src/bin/kim_recipe_menu.py` | Only user recipes assigned to special Root get direct Dolphin menu entries; editor and chooser remain top-level menu items. | Preserve shortcut publishing and cache sync; no nested Dolphin folders. |
| `docs/RECIPES.md` | Documents Root, Built-In, ordinary folders, Unfiled, source-safe derivative recipes and one existing Web Export built-in. | Update documentation only after behavior is implemented and verified. |

**Verified publication discrepancy:** `plan()` currently probes occupied output names and can preselect a numbered alternative; the `PreviewRow.certainty` text warns of a possible later name change. Trace execution to confirm the exact late-collision path before changing it. Project policy requires the approved output name to remain binding; a new late collision must block or trigger renewed review. Treat this as a distinct safety defect, not a silent documentation edit.

## 4. Information architecture

The two top-level roots and hierarchical organization are product requirements. Folder membership and Dolphin shortcut publication are independent. The diagram below is the proposed browser model, not evidence that every listed built-in is shipped.

### Folder location and Dolphin menu pinning

**Approved direction:** The old `ROOT_FOLDER = '@kimng-root'` is a menu publication mechanism, not a meaningful organizational folder. Replace this coupling with an independent persisted **`dolphin_shortcut` boolean** on User recipe definitions (false by default) and a visible editor checkbox **Show in Dolphin menu**. Do **not** create `User / Dolphin shortcuts` as a folder or imply that folder movement controls shortcut status. A *Dolphin shortcuts* filter is optional, and must be visually distinguished from real folders if provided.

**Migration mapping (proposal):** Existing user recipes with `folder == '@kimng-root'` retain stable IDs, steps, naming and destination; set `dolphin_shortcut = true`, and place them in the **User / Unfiled** virtual presentation group (no assigned user folder). Existing ordinary folder membership retains the `folder` field pointing to the unchanged folder ID under User. Existing unfiled recipes stay unfiled and are **not** pinned unless they previously used Root. Do not silently publish additional recipes. `kim_recipe_menu.py` must query pinned User recipes regardless of their nested folder location, preserve safe shortcut IDs, and run existing menu synchronization when pinned membership, recipe names, or disambiguating folder paths change. When multiple pinned recipes share the same casefolded display name, append the shortest **unambiguous folder path** in parentheses; fall back to a safe abbreviated stable ID only if paths remain ambiguous. Desktop action identifiers continue to derive from immutable recipe IDs. Keep menu sync asynchronous/nonblocking where currently supported and surface errors. No nested Dolphin menus.

Existing Root recipes may be assigned to any user folder after migration **without losing their Dolphin shortcut**. Unpinning removes only their direct menu entry, not the recipe. Import resets pinning to false regardless of the bundle's contents. Built-in pinning is not required for this milestone; users can launch built-ins from Choose saved recipe or duplicate a built-in for a personal pinned copy.

### Two-root display and hierarchical navigation

```text
Recipes
├── Built-ins
│   ├── Everyday
│   │   ├── Web export
│   │   ├── Share images                    (candidate)
│   │   └── Share privately                (candidate)
│   ├── Hiker
│   │   ├── Create a trip album            (deferred candidate)
│   │   └── Share a hike privately         (candidate, pending audit)
│   └── Digital asset manager
│       └── Create client proofs           (candidate)
└── User
    ├── Unfiled                          (virtual presentation group)
    ├── Imported                         (normal user folder, created on demand)
    │   └── Shared hiking recipes
    └── Clients
        └── Acme
            └── Client proofs            [Show in Dolphin menu: enabled]
```

This tree is conceptual; **only Web Export is confirmed shipped** at the inspected commit. A recipe may be in any User folder and pinned independently. The two root labels are exact UI wording. Unfiled is a special display group, not a third root.

### Built-in category ownership

Shipped category definitions and built-in recipe placement are KIMng-controlled. Users cannot move, rename or delete shipped folders or shipped recipe definitions. Adding new built-in recipes during upgrades must not overwrite personal content or local description overrides. Built-in recipe identity should use stable IDs, never folder names or paths. Optional categorization can be stored separately from operation definitions.

### User hierarchy rules

- User folders can be nested; permit folder rename and movement while keeping references stable.
- Allow sibling folders with distinct names and optionally identical names under different parents. Enforce case-folded normalized uniqueness among siblings.
- Prevent cycles, invalid parent references, duplicate IDs, excessive depth or unsafe names. A depth cap can protect UI/data consistency, but should not be arbitrarily tiny.
- **Folder deletion contract:** Deleting a User folder with contents shows its total descendant recipe count. Confirm **Move to Unfiled and delete** or **Cancel**. Confirmation moves all recipes in that folder and its descendants to virtual `User / Unfiled`, removes the selected folder and all descendant folders, and keeps recipe IDs, descriptions, shortcuts and steps intact. Empty folder deletion still requires a clear confirmation. No cascade deletion of recipes. Perform the entire change as a single validated atomic library save.
- No arbitrary eight-level nesting limit. Set a documented, generous resource/maximum-depth bound from usability and import security testing, apply it consistently to folder operations and exchange validation, and reject cycles regardless of depth.
- Drag and drop is optional and should not be a prerequisite for folder management. Buttons and context actions are sufficient initially.
- Sorting should initially be alphabetical within folders, with stable ties. User-custom ordering is a future enhancement.
- **User / Imported** is a reserved default *destination*, not a third root. It should be a normal User-owned folder after creation: users can reorganize its contents and create subfolders. If renamed or moved, preserve the stable designated import-target ID or select/recreate the destination explicitly rather than silently scattering imports.

## 5. Description field: precise contract

**Requirement:** Every recipe supports plain-text `description`, maximum **255 Unicode code points** after normalization, including the last permitted character in the search index. Empty descriptions are valid for User recipes; shipped built-ins should have useful descriptions. JSON can accommodate 255 characters without performance concerns; the bound supports concise copy and predictable UI.

- **Input:** Multiline `QPlainTextEdit` (or a plain-text equivalent), placed near Recipe name. Show a live `N / 255` counter, including for Unicode input and paste. Do not silently truncate over-limit paste: show an actionable error and block Save until corrected.
- **Normalization:** Convert `\r\n` and `\r` to `\n`. Convert tab to a normal space on entry/import (or reject consistently; normalization is preferred). Preserve ordinary Unicode and user-authored line breaks.
- **Validation:** Forbid NUL, other C0/C1 controls except LF, and Unicode bidirectional override/isolate controls that can spoof displayed text (`U+202A`–`U+202E`, `U+2066`–`U+2069`). Keep normal accents, combining marks, emoji and international scripts. Count with Python `len(normalized_text)`; do not confuse JSON bytes, UTF-16 code units, or visible grapheme clusters. Apply same rules to user recipes, built-ins, imports, exports and overrides.
- **Safety:** Display as Qt plain text, never rich HTML; no execution/markup. Reject malformed JSON or invalid descriptions without damaging the existing library.
- **Editing:** User recipe description changes persist with the recipe and participate in current dirty/Save-Discard-Cancel behavior.
- **Built-in overrides:** Keep a small **user-owned mapping keyed by stable built-in recipe ID in the existing `recipes.json` library**, not a third persistence file. Built-in steps, name/category and shipped description remain unmodified. The displayed/searchable text is the override if present. Offer **Restore default description** and remove the override key on restore. When a built-in disappears after an update, retain its override harmlessly until an explicit cleanup policy is separately approved; never attach it to a different ID. Duplicate to User copies the *effective* visible description into the new editable recipe.
- **Results:** Show wrapped/clamped excerpt for compactness, but search the **entire description**, including line breaks and the final character. Selected details can reveal the entire text.

## 6. Search: explicit functional contract

A **single shared search implementation** must serve the **Recipe editor** and **Run a recipe** dialogs. This is a core acceptance requirement.

### Indexed fields, without exceptions

1. Complete recipe name.
2. **Complete description, up to and including its 255th character, including user edits/overrides.**
3. Full folder path, including all ancestors and both permanent roots.

Example: `remove precise coordinates` must match a recipe with that phrase in its description even if the name is `Share a hike privately` and folder is `Built-ins / Hiker`. A term near the end of a 255-character description must be discoverable. Search must not index only the first visible line or the clamped result snippet.

### Interaction rules

- Case-insensitive, Unicode-aware normalization (`casefold`-style). Search should update while typing, without a Search button.
- Multiword search uses logical AND across tokens; terms may occur across **different fields**. For example, `hiker gps` may match the folder path `Built-ins / Hiker` plus description `Remove GPS coordinates`.
- Default scope: all recipes under both roots. Provide optional explicit **Search within selected folder** (including descendants); do not scope silently merely because a folder is selected.
- Match ordering: recipe-name match first, then folder-path match, then description-only match; apply stable alphabetical ordering within equal ranks. Do not overengineer fuzzy matching initially.
- Search result displays recipe name, full folder path, description snippet, and built-in/user provenance where not already obvious.
- Selecting a result identifies the correct recipe by immutable ID. Clearing search restores browsing without discarding the current selection or draft.
- Empty query shows hierarchical browsing; empty results show a useful `No matching recipes` message and an easy way to clear filters.
- Keyboard: Ctrl+F focuses search; Escape clears query when appropriate; arrows navigate **focused** results; Enter or double-click deliberately activates the focused recipe but **never publishes outputs**; accessible labels and screen-reader semantics required.
- **Active recipe vs. focus:** Keep a separately tracked `active_recipe_id` for the loaded editor draft or runner preflight, distinct from the keyboard-focused tree row. Search and focus movement alone must not change the active recipe. If the active recipe is hidden by the search filter, show `Active recipe: <name> (hidden by filter)` plus an accessible **Clear filter** action. Activation of a different recipe prompts Save / Discard / Cancel in the editor and redoes preflight in the runner.
- Search paths must be matched as complete ancestor names, and also support separator-insensitive tokens, such that `builtins hiker` finds `Built-ins / Hiker` without typing slashes. Avoid stripping meaningful hyphens from actual names.
- Must handle Unicode names, identical recipe names in different folders, moves/renames and description changes without stale indexes.
- Performance: libraries are bounded and small enough for in-memory search; shared, deterministic model and filtering are preferred over expensive indexing or external search infrastructure.

### Mandatory example tests

| Query | Required result |
|---|---|
| `GPS` | Any recipe with GPS in name, description or full folder path. |
| `coordinates` | A recipe with `coordinates` **only in its description**. |
| `client JPEG` | Match if `client` appears in folder/name and `JPEG` appears in description. |
| `hiker` | Show matching recipes under Built-ins / Hiker, even if titles omit the word. |
| A word at the 255-character end | Match the complete stored description, not a truncated visual excerpt. |
| Different case or supported Unicode | Find the same matching recipe with normalized search. |

## 7. Recipe editor UI design

Prefer a **three-pane resizable editor** rather than a separate tree and recipe list consuming a fourth panel:

```text
KIMng - Recipe editor
[Search recipe names, full descriptions, folders...         ]
┌─────────────────────┬─────────────────────────────────┬──────────────────────┐
│ Built-ins / User    │ Recipe settings / steps         │ Existing live preview│
│ nested folder/      │ Recipe name                     │ Output properties    │
│ recipe tree         │ Description      [125 / 255]    │ and warnings         │
│                     │ Folder path / Move...           │                      │
│ User / Clients      │ [x] Show in Dolphin menu        │                      │
│   Acme              │ Ordered step list               │                      │
│     Client proofs   │ Step parameters                 │                      │
│ User / Imported     │ Destination                     │                      │
└─────────────────────┴─────────────────────────────────┴──────────────────────┘
[New] [Duplicate to edit] [Import…] [Export…] [Save] [existing Run behavior]
```

This is a structural concept, **not** a command to replace the current editor forms or rescale them blindly. Measure on KDE/Breeze at 1366×768 and 1920×1080 as well as the normal homebase display before accepting a final splitter topology. Avoid one giant fixed-size dialog and maintain usable operation/parameter controls.

- Folder and recipe nodes share one clearly indented navigation tree; expand/collapse works with standard Breeze icons. Built-in and User roots remain fixed, visible and unmistakable. Empty folders are visible. The folder pane should be meaningfully larger than today's selector, initially roughly 25–30% of available width where viable, with minimum sizes and user-adjustable splitters. Persist geometry/expanded folders/selection sensibly without restoring off-screen dimensions.
- Searching may temporarily display a **flat list of matched recipe nodes** showing name, full path and a description excerpt; the empty query returns the hierarchy. A matched recipe must remain associated with its stable recipe ID. Folder headings must not be confused with executable recipes.
- Both tree and details display the full selected folder breadcrumb; tooltip-only folder labels are insufficient. Selection highlighting, screen-reader labels and keyboard operation are required.
- The middle pane retains existing step order, enabled state controls, operation picker, parameter editor and destination behavior. The right pane retains the existing live preview and warnings. Preserve ephemeral built-in run-time parameter behavior already supported, but don't persist modifications to shipped steps.
- User descriptions are directly editable. For built-ins, only the local description override is editable; other protected fields remain read-only. `Duplicate to edit` retains its role. A local description-only edit must not turn the built-in recipe into an independently executable modified definition.
- Folder management actions apply only under User. Move/rename/delete prompts must protect nested descendants, maintain IDs, and never delete recipes implicitly. Folder deletion uses the fixed **Move all descendant recipes to Unfiled and delete folders / Cancel** contract defined in Section 4; show the descendant recipe count before committing.
- Show **Import…** and **Export…** as discoverable actions, with sane selection and browse dialogs; do not add them to the Run dialog unless a later usability test demonstrates a need.
- **Dirty editor behavior:** Search typing, arrow-key focus movement, and visual filtering never discard or switch the loaded draft. If filtering hides the active recipe, display the active-recipe banner and Clear filter action. Only explicit activation of another recipe triggers the established Save / Discard / Cancel guard.
- **Qt implementation decision:** Prefer a pure-Python `RecipeCatalog` (folder graph, effective descriptions, complete paths, search/ranking) and a small reusable `RecipeBrowserWidget` using `QTreeWidget` for both dialogs. Keep stable recipe IDs and expanded folder IDs separate from view items. Empty query shows hierarchy; nonempty query shows ranked flat matches with path and description excerpts. If Phase 0 demonstrates that `QTreeView` plus model/proxy would be simpler or more reliable, that choice requires a concrete justification. No SQLite or external indexing service.
- **Responsive layout:** Right-hand Live Preview must be user-collapsible (or switch to a demonstrably usable stacked layout) at constrained widths. The editor form may scroll vertically, but the primary action buttons must remain fixed and visible. Consider auto-collapsing preview for initial windows narrower than approximately 1440 px; do not override an explicit user preference. Clamp restored window geometry and all splitter sizes to the current screen's available geometry, guarding monitor changes and zero-width panes.

## 8. Run a recipe dialog UI design

The chooser must prominently expose the **same Built-ins/User tree and search behavior** as the editor. The current runner has a `QLineEdit` plus a compact grouped `QComboBox`; do not merely extend the combo search and leave folder readability unresolved.

- Include a resizable folder/recipe pane with clear full paths and descriptions; selected recipe detail shows the complete description and planned steps before review.
- Search names + complete 255-character descriptions + full folder paths across both roots by default. A focused-folder scope may be offered as an **explicit** toggle, not inferred silently from selection.
- Preserve the current input-file queue, preflight worker, warnings, enabled operation list, preview, destination controls, repair flow and mandatory Review Changes. The chooser must not run an image merely because a recipe is highlighted or Enter is pressed in search.
- When an operation-specific review intentionally hides recipe selection controls, do not reintroduce irrelevant tree UI there. Shared browser means shared **chooser behavior**, not an unconditional tree on every review window.
- Recipe filtering must not replace/clear the currently planned recipe without deliberate choice; queued files and preflight results remain logically associated with the active recipe until changed.
- Use native Qt/Breeze controls, persistent but screen-bounded splitter state, accessible names and standard keyboard handling (`Ctrl+F`, Escape clear, arrows, Enter selects but never applies).

## 9. Importing and exporting recipes

### 9.1 User workflows and editor actions

**Import…** opens a local file chooser for `.kimng-recipes.json` and an **Import recipes** preview with the incoming recipe names, complete descriptions, original grouping, proposed new full paths, compatibility and warnings. The default destination is **User / Imported**. On the first successful import create that normal User folder lazily. Preserve nested source folders *beneath* the target folder. Users may select a different User folder and relocate imported recipes afterward. Never create a third root.

**Export…** operates on the selected built-in, User recipe, multiple selected recipes, or a selected User folder/subtree. Show a summary of recipes, relative folder structure, portable settings removed or transformed, and destination filename. Exporting a built-in is read-only and allowed without first duplicating it. **Export the built-in's effective visible description:** use the local description override when one is active, otherwise the shipped description. Serialize that description as the ordinary `description` field of the portable recipe; **never include internal `builtin_description_overrides` keys or override-state markers**. Imported copies become ordinary editable User recipes with that same description, not linked to the shipped built-in. Unknown/retired built-in override IDs are not exported as recipes. Saving an exchange file must not modify any source images.

### 9.2 One unified, versioned JSON exchange document

**Decision:** One `.kimng-recipes.json` file covers a single recipe or an arbitrary bounded collection. No ZIP, tar, nested archives, embedded binary assets, scripts, templates, or remote references in the initial exchange feature. This eliminates archive traversal/decompression complexity and improves inspection in Kate/KWrite.

Illustrative conceptual envelope (not a final drop-in schema):

```json
{
  "format": "kimng-recipe-bundle",
  "version": 1,
  "exported_at": "2026-11-18T00:00:00Z",
  "author": "optional unverified attribution",
  "folders": [{"key": "trail", "parent_key": null, "name": "Trail"}],
  "recipes": [{"folder_key": "trail", "recipe": {"schema": 2, "name": "Trail sharing", "description": "Export safe sharing copies.", "media": "image", "steps": [{"op": "image.auto_orient"}], "destination": {"mode": "beside"}}}]
}
```

The exchange schema is independently versioned from the internal library schema. Exchange recipes omit installed recipe IDs, or ignore supplied IDs if a future compatibility reader accepts them; every import creates fresh internal IDs. `author` and timestamps are not authenticated evidence of provenance. No checksums/signatures are necessary for the first format; if added later, digests do not prove authorship.

- Bound the encoded file (initial target **1 MiB**), item count (initial target **100 recipes**), folder count, recursion depth (e.g., **16**), string lengths, operation count, and overall in-memory library capacity. Confirm actual limits against schema and test data before freezing them.
- Use the current strict duplicate-key JSON reader where applicable. Validate top-level envelope, keys/types, recipe media and every allowlisted operation with existing recipe validators, enabled flags, order/parameters, 255-character descriptions, relative folder graph and destination semantics. Unknown future versions/steps fail with precise diagnostics. **Do not silently discard unsupported steps**.
- Each imported recipe is converted into the installed schema explicitly and receives a safe fresh internal ID. All imported folders live under User. Reject cycles, deeply nested structures, unsafe names, reserved system IDs and malicious Unicode spoofing. Never interpret description/author strings as HTML or code.
- A file can be opened/imported even when no image is selected; **importing is never executing**. Import preview is separate from image Review Changes.

### 9.3 Conflicts, atomicity and default import folder

- Show conflicts (same sibling name, duplicate content or source ID), offer **Skip**, **Rename imported copy**, or **Change destination** with clear final paths. An imported recipe can never overwrite a User recipe or a Built-in. No silent renaming.
- Confirm the selected valid subset or all chosen recipes together; commit one atomic library update after complete validation. Cancellation or a failed validation leaves the existing library untouched. New installed recipe IDs are generated locally; imported/exported IDs must never overwrite current IDs.
- Store an optional user-library `import_folder_id` pointer to the normal Imported folder, so a user rename (e.g., `Downloaded`) doesn't lose the target. If that folder is deleted, a subsequent import creates `User / Imported` anew after preview. Allow importing into any selected User subfolder.
- Imported recipe **output destinations** are distinct from their **User / Imported organizational folder**. Safe single-segment `subfolder` output destinations may remain configured and are shown explicitly in the import review; they still resolve beside each image source at execution. Import never authorizes filesystem creation or execution. Untrusted `dolphin_shortcut` flags are discarded/forced false; imports never alter the Dolphin menu until the user explicitly pins a recipe later.
- Re-importing a shared file must not silently replace a prior import. Optional import-source metadata is informational only, not a synchronization/update mechanism.

### 9.4 Destinations, privacy and validation

- Local absolute destination paths, usernames, secrets and environment-specific settings must **not** be exported silently. Export summarizes any sanitized fields; leave the existing saved recipe unmodified.
- **Three destination cases, deterministic:** (1) `beside` remains `beside`; (2) `subfolder` with one safe filename component (no `/`, `\`, `..`, leading dot, NUL/control characters, or Unicode spoofing characters; bounded to 60 characters to match the current filename-component convention) remains `subfolder` and is clearly displayed; (3) `directory`/absolute path, malformed subfolder, unsupported mode, or any other unsafe destination is **not activated**. Import preview must show the original proposal as escaped, untrusted plain text where safe to display, propose **Beside each source**, and require affirmative acknowledgement of the replacement. Unsupported or malformed destination structures that cannot be parsed safely may block that recipe entirely. No silent rewrite or automatic path trust.
- Export local absolute paths only as a disclosed sanitized replacement (normally `beside`), never leak path text, usernames, secrets or local filenames into exported payloads or author metadata without explicit consent. The original saved User recipe remains unchanged.
- Warn when imported steps strip metadata, change GPS, set rights, change capture dates, require encoders, or otherwise affect output. Actual source-image publishing always invokes the ordinary Review Changes gate; an Import confirmation is **not** permission to run the recipe.
- Imported files are declarative only. Reject arbitrary shell/Python, executable hooks, unrecognized external commands, URL-fetch actions and all unsupported operation IDs. Reuse the existing validated image pipeline; never execute content supplied as file names or descriptions.
- Test malicious JSON (duplicate keys, excessive strings/depth, wrong types, unsupported ops, path escapes, deceptive Unicode, malformed folders), rollback after partial import failure, and import/export round-trip accuracy. No ZIP-specific tests or archive extraction paths remain.

### 9.5 Conceptual Import dialog

```text
KIMng - Import recipes
Source: ~/Downloads/shared-recipes.kimng-recipes.json
Destination: User / Imported                        [Change…]
[x] Trail photos       User / Imported / Hikes       Ready
[x] Client proofs      User / Imported / Clients     Rename needed
[ ] Unknown format     Not importable                Unsupported step
Selected description: [...full 255-character plain text...]
Warnings: local output destination will use Beside each source
[Cancel]                                         [Import selected]
```

Only selected, valid, user-approved recipes are installed. Bad entries must be clearly blocked, not quietly repaired.

## 10. Data model and migration strategy

### 10.1 Verified baseline and proposed v2

The current branch uses strict **recipe schema 1** and **library schema 1**. The recipe validator accepts required `schema`, `id`, `name`, `media`, `steps`, `destination` and optional `folder` only. The library contains `recipes` and a flat list of folders with `id` and `name`. The shipped built-in loader rejects folder assignments and stores built-ins separately; user library storage is XDG config `kimng/recipes.json`.

**Proposed library schema 2** remains a single user-owned JSON document, with `schema: 2`, `recipes`, hierarchical `folders`, `builtin_description_overrides` (default `{}`), and `import_folder_id` (default `null`). User recipes gain optional `description` (default empty) and `dolphin_shortcut` (default false); **retain the existing recipe key `folder`** as a reference to a stable folder ID or omit it for Unfiled. Folder records gain a `parent_id` (null = direct child of User). IDs remain stable across migration. Sibling folder names must be unique under case-folded normalization; duplicates across different parents are permitted. Built-in categories are KIMng-managed metadata, not User folder entries. Keep built-in descriptions locally overridable in user configuration, not a third file.

```text
User recipe: stable id, name, description (0..255), media, steps,
             destination, optional folder reference, dolphin_shortcut (bool)
User folder: stable id, name, parent_id (folder ID or null)
Built-in description overrides: {builtin_recipe_id: effective local description}
Import target: optional stable User folder ID
Exchange bundle: separate format/version with portable relative folder keys
```

**Do not** add downloaded recipes to `src/recipes/builtins.json`, and do not treat exported IDs or path strings as authoritative library identities. Built-in categories may be stored in a KIMng-managed catalog/index or a validated built-in category field; preserve the current built-in recipe loader contract unless explicitly evolved.

### 10.2 Safe migration and rollback expectations

1. Phase 0: inventory all callers of `validate`, `validate_library`, `library_groups`, `ROOT_FOLDER`, `plan`, and the publication executor, plus menu rendering, folder CRUD, current tests, and any uncommitted overlaps on natacha. Freeze the exact v2 contract before edits.
2. Read schema 1 and schema 2 through explicit validated pathways. Prefer in-memory conversion of schema 1; **do not rewrite configuration on read or mere dialog opening**.
3. Before **first v2 write**, create a durable, non-overwriting schema-1 backup such as `recipes.v1.bak.json`, with original content and restrictive permissions preserved. Reject symlink/hardlink redirection, flush/fsync backup contents and directory metadata as appropriate, and fail closed if backup cannot be created. Save v2 through same-directory temporary file, fsync and atomic replacement; do not claim a transactional menu update if the subsequent menu sync fails. Never rewrite configuration on read.
4. Preserve user recipe IDs, step order and enabled flags, destination modes and paths, naming tokens, folders, all previous settings, and shortcuts. Map old `@kimng-root` to `dolphin_shortcut=true` + unfiled folder; other recipes default false.
5. Convert flat folder IDs to User child folders with `parent_id=null`; preserve stable IDs. Disallow duplicate sibling names under normalized casefold, broken parent references, cycles, excessive depth and unsafe names. Deleting a folder moves all descendant recipes to Unfiled and removes the descendant folders only after explicit confirmation.
6. Store local built-in description overrides inside the user library; changing them cannot mutate packaged built-ins. Reconcile by stable recipe ID, never title or folder path.
7. Perform validation and atomic replacement for all migrations/imports. On exceptions, existing config remains readable and intact; no partially written folders or menu entries. Menu updates follow only a successfully committed change in pin membership/name; report synchronization failures without pretending publication succeeded.
8. **Rollback:** An older release with strict schema 1 cannot read v2. Do not promise binary backward compatibility. Document restore of pre-migration backup for users intentionally downgrading; do not weaken legacy validation to pretend rollback is transparent.
9. Follow source permission/symlink protections in existing code; never read or write arbitrary user-config paths from exchange content.
10. Test migrated real-shape libraries and repeated, interrupted, invalid and idempotent transitions. No commit or deployment before the separately accepted migration milestone.

## 11. Built-in recipe catalog and example defaults

These are **product candidates**. Suggested defaults must be validated against the actual operations, image formats, output planner, metadata safety and color tools; no unimplemented capability should be presented as already working.

### Everyday

| Recipe | Primary job | Proposed steps/policy | Complexity |
|---|---|---|---|
| **Web export** | Existing web publishing workflow | **Preserve current shipped settings**: auto-orient, fit 1600×1600, sRGB, JPEG quality 95, strip metadata, `_web` output in Web subfolder | Existing |
| **Share images** | Email and messaging | Auto-orient, max 2048 px, no enlargement, JPEG quality ~85, color compatibility, derivatives; preserve necessary rendering data | Low/moderate |
| **Share privately** | Share without revealing sensitive information | Resize/convert plus explicit cross-namespace GPS, serial and identifying metadata removal; retain required rendering/color information | Moderate, privacy-critical |
| **Prepare for printing** | Create derivatives for 4×6, 5×7, 8×10, etc. | Target pixel dimensions and print resolution, crop vs pad approval, no stretching, profile/resolution warnings | High, color/crop dependent |
| Create smaller copies | Straightforward reduced-size duplicates | Resize without unnecessary format conversion | Low, **likely fold into Share images options** |
| Create a listing image set | Online listings | Standardize sizes and format without altering product truth | Moderate |
| Prepare images for a digital frame | Display-specific size and aspect | Resize with optional padding, never stretch | Moderate |
| Create a family contact sheet | Printable visual index | Reuse existing contact-sheet facility, optional dates/filenames | Depends on composition support |

### Hiker

| Recipe | Primary job | Proposed steps/policy | Complexity |
|---|---|---|---|
| **Create a trip album** | Ordered, shareable trip set | Chronological sort, safely handle missing/ambiguous capture dates, sequence names, resize, preserve/cull GPS by explicit option | Moderate/high |
| **Share a hike privately** | Share scenery without exposing exact location | Existing GPS removal where verified; approximation only if connected to Recipes and proven safe | Moderate/high; distinct hiking-facing UX, shared technical implementation possible |
| **Create a trail contact sheet** | Trail/trip image index | Reuse contact-sheet engine, optionally display filename, capture time and GPS/elevation, only when present | Moderate/high |
| Trail condition report | Maintenance or survey documentation | Dated numbered contact sheet/PDF with explicitly approved coordinates | Later |
| Geotagged field collection | Retain location provenance for field work | Explicit GPS retention, capture time, manifest later | Later |
| Before-and-after comparison | Compare manually paired field images | User-confirmed pairing; no inferred false match | Later |
| Trip map package | Map-linked images | Reuse existing KIMng GPS/map subsystem; no separate engine | Later, high |

### Digital asset manager

| Recipe | Primary job | Proposed steps/policy | Complexity |
|---|---|---|---|
| **Create client proofs** | Client review set | 1600px max, JPEG quality ~85, optional verified watermark, explicit naming; batch numbering only when supported; contact sheet later | Low/moderate for simple exports; sequencing requires verification |
| **Prepare client delivery** | High-quality controlled deliverables | Configurable JPEG/TIFF where supported, dimensions, ICC, naming, rights/metadata validation | High |
| **Create DAM derivatives** | Multiple standardized renditions | Named large preview, medium web rendition and thumbnail, deterministic output paths, pre-reviewed multi-output plan | Later, high |
| Prepare an archive copy | Preservation-oriented derivative | Lossless suitable format, no resize, explicit metadata policy, checksums/manifest later; **not a backup or original preservation master** | High |
| Create editorial submissions | Publisher-specific exports | Requirements-driven profiles for dimensions, name, embedded credit/caption and rights | Later |
| Prepare licensed images | Rights-aware delivery | Metadata-writer approval prerequisite; never quietly edit original/sidecar | Deferred |
| Create catalog thumbnails | Consistent downstream thumbnails | Fit without unintended crops; safe naming | Moderate |
| Prepare an ingest package | Validate and report asset readiness | Metadata completeness checks, filenames, provenance, manifest | Later |
| Create a visual inventory | Index and audit selected assets | Contact sheet plus manifest (filenames, dimensions, outputs, optional checksums) | Later |

### Release feasibility and dependency gates

- **Near-term candidates:** Share images; Create client proofs **without unverified batch numbering or watermarking**. These are plausible compositions of currently registered resize, convert, color and filename operations but still require live execution verification.
- **Privacy-gated:** Share privately and Share a hike privately require tests that explicitly prove location/identifying metadata policy across EXIF/IPTC/XMP/MakerNotes and sidecars as applicable, plus conversion to sRGB *before* metadata removal when necessary to preserve appearance. Do not claim privacy from the presence of a step label alone.
- **Engine-dependent:** Trip album chronological order/sequence across sources; trail contact sheet composition; print sizes/crop-or-pad/PPI; one-to-many DAM derivatives; before/after paired inputs; map-linked packages. Keep in catalog but **do not ship as functional** until separately supported and reviewed.
- **Rights-gated:** Any workflow depending on metadata writing, completeness validation or RAW/sidecar transactions stays blocked until the relevant approved writer/safety milestone.

### Potential recipe experience additions

- **Recommended / Smaller files / Highest quality** variants where genuinely useful, preferably preset options within one recipe rather than dozens of duplicate recipes.
- Show warnings for GPS, missing rights, mixed orientation, unsupported encoder, inadequate print resolution, malformed capture dates, transparency and animation handling.
- Format compatibility checks should block rather than silently coerce potentially destructive choices.
- Saved delivery profiles for specific clients or publications, eventually shareable as **validated declarative data only**; never import arbitrary executable code.
- Keep technical requirements and safety policies structured and read-only, distinct from editable human description text.

## 12. Shared execution and source-safety contract

Every built-in, personal and imported recipe must preserve KIMng's approved output contract:

1. **Derivative only:** no modifications, overwrites or renaming of original images. Presets only prefill settings. One mandatory **Review Changes** gate before derivative creation.
2. Review displays source, operations, original/result preview when applicable, **exact planned output filename and directory**, warnings, skipped/blocked items and explicit Apply/Cancel. Default output is **Beside each source**, including mixed source directories; `Change Destination…` must update the approved plan and execution.
3. **Known current defect to isolate:** The inspected `kim_recipe_core.py` planner checks a collision and may choose a numbered alternate filename, and its certainty message says the filename may change when saving. This is inconsistent with the project's stronger accepted rule. Before expanding recipes, reproduce and trace planner vs. execute behavior, then minimally enforce that a **late collision blocks or triggers renewed Review Changes** rather than silently changing an approved name. Never weaken source identity checks or permit overwriting.
4. **Exact-plan binding:** Review must show a deterministic `approved_output_path` for each source. Detect both already-occupied target paths and **intra-batch duplicate destinations** before enabling Apply. Approval freezes each `(source_path, source_identity, output_path, operation_plan)` tuple. Execution consumes that immutable approved tuple and may not re-plan, change destinations, or auto-number output names. If the user changes destination or operations, invalidate the old approval and present updated Review Changes.
5. **Race-safe, complete-file, no-replace publication:** A mere `exists()` check followed by `os.replace()` is unsafe and explicitly prohibited. Render/encode the complete derivative into a securely created, hidden staged regular file **in the approved destination directory/on the same filesystem**; validate completion, close/flush it, and perform any required file and directory durability synchronization. Publish the completed file using a **verified atomic no-replace primitive** supported by that target filesystem, such as Linux `renameat2(..., RENAME_NOREPLACE)` with correctly checked semantics or a same-directory `os.link(staged_path, approved_output_path)` followed by stage unlink. An existing destination, including one created after Review Changes, must cause an explicit blocked collision result without overwriting or renaming. Stage cleanup must run on failure/cancellation, but must never remove a successfully published output. Verify permissions, symlinks, hard-link support, failure behavior, and crash/durability semantics in Phase 0 and focused filesystem tests before selecting the mechanism. **There is no permitted fallback to writing bytes directly into the final approved path with `O_CREAT | O_EXCL`**, because such an output could be visible partially written. If the actual destination filesystem cannot support an atomic no-replace publication of a completed file, fail closed with a clear unsupported-filesystem diagnosis and leave the original images untouched. Any alternative requires separately reviewed proof that it provides *both* no-overwrite and no-partial-visibility guarantees. Execution must consume the immutable approved plan, not recompute filenames or destinations.
6. Preserve source identity before/after inspection; safe staging/atomic publication, cancellation, error reporting and explicit confirmation of actually published outputs. Existing per-batch partial success semantics require accurate reporting; do not assert blanket rollback without implementing it.
7. Use a single final approved publication plan. Do not allow imported settings to bypass it or write undeclared extra outputs. Multi-output recipes require reviewed enumeration of **all** derivatives per source.
8. Metadata privacy: inspect exact handler behavior, including GPS namespaces (`GPS:all`, XMP GPS variants, location structures), MakerNotes, ICC, EXIF/IPTC/XMP and sidecar interactions as applicable. A recipe named **Share privately** must define what remains. Converting to sRGB prior to strip-all may protect rendering appearance, but must be empirically verified on representative input profiles and formats.
9. Reuse existing KIMng GPS map/viewer/writer rather than adding competing GPS facilities. Unsaved metadata-editor drafts stay safe. Rights writing remains under separate implementation approval and mandatory combined Review Changes.
10. Confirm encoder/format behavior for JPEG, PNG, WebP, HEIC/RAW derivatives, transparency, animation, PSD and ICC before claiming universal compatibility. APNG remains fail-closed; GIF support must not regress. Preserve `Fix Recipe` behavior for PSD where needed.
11. Importing/exchanging recipes is **data management, not source image processing**. A successful import never executes a recipe or authorizes any derivative output.

## 13. Recommended phased implementation and acceptance

Each phase represents a separately approved and accepted scope. Do not treat this backlog as approval to edit, deploy, commit or push. User acceptance after real KDE/Dolphin testing is required before advancing.

### Phase 0: Read-only baseline audit and design freeze

- On natacha inspect `git status`, branch and overlapping uncommitted work first. Inventory all recipe storage, browser, runner, menu and execution call-sites; correlate GitHub commit `7a2bc2748e31935d8865a631bbc903491424cdf1` findings with live working tree.
- Reproduce/trace current exact-name collision behavior without making code changes; identify the smallest separately approvable correction.
- Confirm step registry, strip/color behavior, folder/migration fixtures, built-in loader and test coverage. Finalize schema-v2, exchange-v1 and UI layout contract with focused test matrix.

### Phase 1: Approved-output collision safety (separate defect, separately approved)

- Reproduce and trace `plan()` through actual publication; fix only exact reviewed output path binding. Check existing target collision, two selected sources with same planned target in one shared output directory, and another process creating the target after review. Execute the approved plan, do not re-plan or renumber, and publish with an atomic no-replace primitive that publishes only a fully staged file. Confirm unsupported target filesystems fail closed rather than exposing a partial final file. Ensure late collision is clearly blocked, source identity and cancellation remain safe, and successful earlier batch outputs are reported accurately. Accept on homebase before more recipes publish. Do not silently broaden the change into the library UI.

### Phase 2: Schema-v2 migration, descriptions and Dolphin menu decoupling

- Add schema-1 read compatibility and guarded first-write backup; nested folder-capable v2 representation retaining existing `folder` recipe keys; 0–255 descriptions and user-library built-in overrides; stable `dolphin_shortcut` property.
- Migrate old Root menu membership to pin flag with no shortcut loss. Add description UI/counter and Show in Dolphin menu checkbox. Confirm that moving a pinned recipe doesn't unpin it.
- Test invalid/Unicode descriptions, backup/rollback instructions, idempotent migration, built-in override resets and unchanged source operations.

### Phase 3: Shared search and catalog discovery

- Implement one pure-Python shared catalog/search contract with casefolded cross-field AND search over complete recipe name, full description and complete ancestor path; test final-character match, built-in overrides and path-separator-insensitive matches.
- Wire runner first where useful, then editor. Distinguish focused row from active recipe. Keep active recipe/preflight and editor draft stable during filtering; explicit Enter/double-click activation is required. Show hidden-active banner and Clear filter. Prefer a shared QTreeWidget browser unless measured evidence favors a full model/proxy implementation.

### Phase 4: Prominent two-root hierarchical browser

- Install native expandable `Built-ins`/`User` tree in both chooser/editor, with nested User folder CRUD and deterministic move-to-Unfiled deletion of all descendants after explicit confirmation. Prefer unified folder/recipe tree, three-pane editor, resizable splitter and persisted screen-clamped sizing; offer preview collapse or alternate narrow arrangement. Preserve existing preview, operation controls and pinned action buttons.
- Verify at normal desktop and reduced laptop resolutions, including 1366×768. Do not replace operation-specific Review Changes with the recipe browser.

### Phase 5: Safe JSON-only sharing

- Implement `.kimng-recipes.json` one-or-many import/export with bounded strict validator, explicit three-case destination policy (beside, safe single-component subfolder, unsafe destination requiring acknowledged replacement/block), name conflict resolution, atomic writes, fresh IDs, no automatic pinning and `User / Imported` default. Export built-ins as portable copies using their **effective visible description** (local override if set, otherwise shipped), without exporting override-map keys; protect local paths and user secrets.
- Round-trip selected recipes, whole subtrees, nested folders, descriptions, rights settings and ordered steps. Run malformed/malicious JSON tests. No ZIP parsing or archive extraction.

### Phase 6: Curated built-in rollout, one recipe at a time

- Start with Share images or simple Create client proofs. Audit each against current engine, add a built-in description/category, inspect exact planned outputs, run live homebase tests, request acceptance and only then move to the next.
- Privacy recipes require metadata-and-color fixture audit. Defer unavailable print, multi-output, chronological sequence, contact sheet and GPS approximation functions rather than quietly approximating them.

### Shared verification and deployment protocol

- Use focused tests, Python/Bash syntax checks as appropriate, `git diff --check`, and identify pre-existing failures separately from regressions. Do not manufacture broad new test suites or alter unrelated code.
- For live homebase tests: record natacha Git status; sync natacha's **complete** working tree including uncommitted edits (`rsync -a --delete --exclude='.git/'` with appropriate preservation checks); run `bash install.sh` on homebase; run `kbuildsycoca6`; explicitly launch **`homebase-dolphin` from natacha** (SSH to `coolian@homebase` opening `/home/coolian/Pictures`). Headless Qt passes alone are not acceptance.
- Never commit or push without explicit user approval. If drafting a substantial Codex prompt, explicitly require inventory/read/apply/report of *relevant installed Matt Pocock skills* before editing, plus files in scope, protections, acceptance criteria and no unauthorized commits/pushes.

## 14. Acceptance criteria matrix

| ID | Must-pass acceptance criterion |
|---|---|
| R-01 | Both dialogs display permanent, distinguishable Built-ins and User roots with readable icons and folder paths. |
| R-02 | Built-ins can be categorized (Everyday, Hiker, Digital asset manager); only verified existing built-ins are shown as shipped. |
| R-03 | User nested folder create/rename/move/delete is stable; invalid parents/cycles are blocked. Confirmed folder deletion moves every descendant recipe to Unfiled without deleting recipes. |
| R-04 | Existing flat folders, old Root shortcuts, Unfiled recipes, IDs, steps, destinations and filenames survive v2 migration intact. |
| R-05 | Moving/renaming a recipe or folder does not alter the independently persisted Show in Dolphin menu pin. |
| R-06 | Pinned recipes synchronize with Dolphin menus; unpinned recipes do not, and imported recipes are never auto-pinned. Duplicate pinned names are disambiguated using folder paths without changing stable action IDs. |
| R-07 | User descriptions and built-in local description overrides are editable, saved, restorable and capped at 255 normalized code points with a live counter. |
| R-08 | **Both dialogs search complete descriptions through character 255**, including description-only matches and local built-in overrides. |
| R-09 | Search includes name + full ancestors; multi-token cross-field AND, casefold, separator-insensitive path matching, stable selection, clear results and keyboard navigation work. |
| R-10 | Focused tree row and active recipe remain independent. Search/filter/arrow keys never discard a draft, change active preflight or execute. A hidden active recipe shows an explicit banner and Clear filter. |
| R-11 | Three-pane editor (or accepted equivalent) has resizable, persistent, screen-bounded layout with a collapsible preview or working narrow layout; action buttons stay visible at 1366×768 and 1920×1080. |
| R-12 | Editor retains all existing ordered steps, parameters, destination, live preview and built-in protection; Duplicate to edit produces independent User copies. |
| R-13 | Current Web Export recipe runs unchanged unless a separate approved fix changes it. |
| R-14 | Every recipe preserves mandatory Review Changes, source identity, atomic derivative safety and exact approved output directory/filename. |
| R-15 | Disk and intra-batch collisions block approval; exact approved source/identity/output tuples are consumed by execution; atomic no-replace publication blocks late collisions with **no silent rename or overwrite**. |
| R-16 | The editor has visible Import… and Export… actions supporting single or multiple recipes using only `.kimng-recipes.json`. |
| R-17 | Imported recipes default to User / Imported, preserve safe relative subfolders and become ordinary editable User recipes. |
| R-18 | Export supports user recipes and read-only built-ins; it shows/sanitizes local settings and round-trips supported steps, descriptions, and grouping. |
| R-19 | Import preview displays original/effective output destinations, preserves safe single-component subfolders, blocks or explicitly acknowledges unsafe replacements, displays descriptions/compatibility/conflicts, and requires selection confirmation. |
| R-20 | Import never runs operations, installs Dolphin shortcuts, changes Built-ins or overwrites an existing recipe. |
| R-21 | Strict JSON key/type/size/depth, Unicode, operation, path and schema validation protects against untrusted files. |
| R-22 | Invalid/cancelled import leaves user library unchanged; accepted imports save atomically, survive restart and maintain stable internal IDs. |
| R-23 | Privacy-named built-ins are not shipped before confirmed EXIF/IPTC/XMP/GPS/MakerNotes/ICC behavior on representative fixtures. |
| R-24 | No unsupported engine-dependent recipe is presented as operational; per-recipe homebase acceptance precedes the next built-in. |
| R-25 | Focused tests, `git diff --check`, homebase installation, `kbuildsycoca6`, and actual Dolphin UI are verified. |
| R-26 | No commits, pushes, unrelated edits, or unsafe worktree replacement occur without authorization. |

## 15. Architecture risks and mitigations

| Risk | Mitigation and gate |
|---|---|
| Strict schema-1 keys reject additions | Explicit schema-v2 read/migrate/write, tests and backup before first write. |
| Existing Root is both storage group and menu pin | Separate `dolphin_shortcut` from placement; preserve old pins and IDs. |
| Older releases reject v2 | Document backup restoration; do not promise rollback compatibility. |
| Nested folder ID cycles or orphans | Validate graph, sibling uniqueness, depth and delete policy atomically. |
| Crowded editor | Use one folder/recipe tree, collapsible preview or narrow-layout alternative, scrollable form and pinned actions; clamp restored geometry. |
| Shared search becomes inconsistent | One normalizer/matcher/search contract for both dialogs; test description-only and final character. |
| Built-in descriptions diverge from packaged defaults | Keep small user-owned override map keyed by stable ID, with Restore default. |
| Untrusted JSON executes steps or steals paths | Strict allowlisted operations; preserve safe `beside` or single-component subfolders, reject/acknowledge unsafe destination replacement; never execute on import. |
| Duplicate names/IDs overwrite existing data | Fresh safe import IDs, conflict preview, explicit rename/skip, atomic save. |
| User credentials/local paths exported | Summarize and sanitize only export document; never mutate saved recipe. |
| Output filename changes after approval | Detect disk/intra-batch collisions; consume immutable approved paths; use atomic no-replace final publication, never check-then-replace. |
| Privacy recipes leak GPS or degrade color | Audit metadata coverage and ICC/sRGB ordering with real files. |
| Multiple outputs published without plan | Defer until one-to-many publication and combined review are accepted. |
| Too much abstraction for small library | Measure actual `QTreeWidget` vs model/view maintenance and performance before adding framework. |
| Dilution of product via too many built-ins | Curate a small launch set; defer unsupported candidates and keep categories navigable. |

## 16. Final engineering verification questions (after two Gemini reviews)

Two Gemini reviews have been considered. Further reviewers should concentrate on remaining correctness and compatibility questions, not re-litigate decided product requirements without evidence.

1. Does `dolphin_shortcut` migration preserve every direct-menu behavior of `ROOT_FOLDER`, including name changes, save conflicts and menu synchronization? Identify exact affected call sites.
2. Is schema-v2 storage best implemented with additive recipe fields and a folder `parent_id`, while retaining the existing `folder` reference name, or does a full field rename reduce risk? Specify one migration contract.
3. Can the 255-code-point Unicode normalization and disallowed-character policy be enforced consistently by Qt input, strict JSON import and library validators? Identify corner cases.
4. Does a small shared catalog and `QTreeWidget` satisfy both dialogs, or would `QTreeView`/model/proxy materially reduce complexity? Show a concrete tradeoff rather than an abstract preference.
5. Is the three-pane editor usable at 1366×768 while preserving step controls, parameters and preview, or should browse/details be collapsible? How should persisted splitters handle changed monitors?
6. What minimal fix ensures the reviewed exact output filename cannot change during execution? Point to planner and execution interactions and race conditions, without proposing unrelated refactoring.
7. What is the clearest user-facing import preview for changes to relative subfolders, unsafe absolute destinations, name collisions and unsupported steps? What must block?
8. Is one `.kimng-recipes.json` envelope sufficient for single and whole-folder export? Which limits (bytes, recipe count, folders, depth) fit the existing library validator and user workflows?
9. How should local built-in description overrides survive retirements/renames while remaining separate from shipped operation data?
10. Which first built-ins are demonstrably expressible with the current registered operations, and which have hidden limitations involving multiple sources, numbering, watermarking, color, GPS, or metadata?
11. What cross-namespace metadata fixture matrix suffices before asserting that Share privately or Share a hike privately removes sensitive information?
12. Are any requirements still contradictory, insecure or unnecessarily complicated? Rank only actionable findings with file/function references and minimal fixes.

**Requested reviewer output:** separate confirmed code observations from conjectures; prioritize blockers, provide exact behavior-level corrections, and do not modify source or generate patches.

## 17. Second Gemini review: adopted decisions and exact behavioral clarifications

This section is a change-control record for v1.4, **not** a substitute for the integrated requirements above.

| Second-review topic | v1.4 decision |
|---|---|
| Late collision TOCTOU | Critical safety prerequisite, separately approved; immutable approval and fully staged, atomic no-replace publication. A pre-write existence check followed by `os.replace` is insufficient; directly writing the final path via `O_EXCL` is also insufficient because partial output can be visible. Unsupported destination filesystems fail closed. |
| Intra-batch collisions | Reject duplicate approved output paths before Apply, including mixed source directories publishing to one shared directory. |
| Portable destination | Preserve `beside` and safe single-component `subfolder`; unsafe/absolute destinations cannot activate and require acknowledged local replacement or block. |
| Editor space at 1366×768 | Collapsible preview (or tested narrow alternative), scrollable middle form, fixed bottom actions, clamped geometry. |
| Duplicate Dolphin menu names | Use shortest unambiguous ancestor path in displayed labels; immutable IDs drive actions. |
| Active/focused recipe | Independent state. Search, typing and arrow focus do not activate or change preflight. Hidden active recipe banner and clear-filter control. |
| Folder deletion | Confirm move of every descendant recipe to User / Unfiled; remove subtree folders, not recipes, as one atomic mutation. |
| Search punctuation/path terms | Search full description plus names/ancestors, with path separator-tolerant token matching. |
| Built-in override orphan IDs | Retain harmlessly; never bind to another ID; exclude unknown IDs when exporting built-in copies. |
| Qt browser architecture | Start with shared pure-Python catalog and reusable QTreeWidget; custom Qt model only if justified by tests. |
| Internal storage | Existing two JSON locations only; user library schema 2 retains recipe `folder` reference; no SQLite or third override file. |
| User folder depth | Apply a documented resource-safety cap after measuring UI and import behavior; do not silently impose an arbitrary eight-level UX restriction. |
| Sharing | One bounded `.kimng-recipes.json` for single/multiple recipes, fresh IDs and no automatic pinning; nested import folders preserved. Built-in export carries the effective visible description as ordinary portable text, not override metadata. |
| Product scope | Keep the full catalog of candidate recipes and defer those needing capabilities not yet verified. |

**Verification status:** GitHub branch `recovery/kim-all` commit `7a2bc2748e31935d8865a631bbc903491424cdf1` was inspected for the baseline noted in Section 3. Proposed schema and UI changes are not implemented or verified. Gemini's environment did not inspect repository code directly; its suggestions are evaluated against the documented audit and the current-branch observations. Natacha's complete working tree must still be inspected read-only before editing.

## 18. Design conclusion

Build the recipe-library foundation before filling it. The agreed design centers on **Built-ins and User roots**, user-managed nested folders, prominently navigable trees, editable **255-character full-text-searchable descriptions**, locally customizable built-in descriptions, independent Dolphin menu pinning, and **JSON-only** recipe exchange landing by default in **User / Imported**. Both dialogs share one search contract across **name + complete description + full folder path**. Import/export must be safe, inspectable, and separate from recipe execution.

The current committed branch already has a working recipe engine, a run-dialog search field, flat folder management, built-in Web Export, preview and menu synchronization. Preserve those capabilities instead of replacing the entire system. Migrate deliberately, verify publication safety first, retain the broader recipe catalog as a roadmap with capability gates, and accept one change/recipe at a time in actual KDE/Dolphin.

**Accepted from Gemini reviews:** menu pin/placement separation, JSON-only exchange, unified folder/recipe tree, schema-v2 strategy, metadata/privacy audit, deterministic folder deletion, active-vs-focused recipe separation, responsive/collapsible preview, safe destination triage, explicit output-plan/no-replace safety, and feasibility-based rollout. **Modified:** prefer simple QTreeWidget plus shared pure-Python catalog over an automatic custom model framework; reject an arbitrary eight-level User folder cap. **Rejected:** removal of local editable built-in description overrides, which remain an explicit product requirement.

**Status:** Design baseline v1.5, ready to use for Phase 0 read-only architecture audit and subsequent separately approved milestones. No KIMng repository files were changed; no commits or pushes were made.


## 19. Final independent review closure and implementation-readiness gates (v1.5)

The third Gemini review assessed v1.4 as **ready to freeze and implement**, conditional on the Phase 0 read-only audit and two final clarifications. This v1.5 text integrates both: (a) a complete-file atomic no-replace publication requirement with fail-closed behavior on unsupported filesystems; and (b) export of a built-in recipe's effective visible description, without internal override metadata. The preceding sections are the normative specification; this section records closure and the go/no-go criteria.

### 19.1 Final decisions, including deliberate deviations from Gemini

| Issue | Final requirement |
|---|---|
| Hard-link publication vs. `O_EXCL` fallback | Same-filesystem staging and atomic no-replace publishing of a **completed** derivative are required. The direct-to-final-path `O_EXCL` fallback proposed by Gemini is **rejected** because a partial image can become visible. An unsupported filesystem blocks publication. |
| Export built-in with description override | Export the effective displayed description as the portable recipe's `description`; omit internal override dictionaries and state markers. |
| Browser implementation | Prefer shared pure-Python catalog and reused native `QTreeWidget` browser; no mandatory custom model/proxy or SQLite. |
| User folder depth | No arbitrary eight-level product restriction. Apply a documented, tested security/resource bound appropriate to the chosen schema and actual UI. |
| Editable built-in descriptions | Preserve local overrides, with restore-default action, in the existing user-owned JSON storage. Shipped operations remain protected. |
| Root shortcuts | Migrate legacy Root assignment into an independent `dolphin_shortcut` flag without breaking existing Dolphin shortcuts. |
| Import/export | Single bounded JSON exchange format; `User / Imported` default; preserve safe relative output subfolders; do not execute or pin imported recipes. |
| Publication prerequisites | Phase 1 collision/plan binding fix is a distinct user-approved defect correction, not an implicit component of recipe UI work. |

### 19.2 Required Phase 0 report before implementation

Phase 0 is **read-only**, performed against natacha's complete actual working tree at `/home/coolian/tmp/kim6`, including uncommitted edits. The report must contain:

1. `git status --short --branch`, current branch/head, all overlapping uncommitted recipe and publication changes, and any relevant existing backups. Do not reset, clean, pull, merge, rebase, switch branches, stage, commit or push.
2. A call-site map for `ROOT_FOLDER`, `library_groups()`, `validate()`, `validate_library()`, `load_library()`, `save_library()`, the Dolphin service-menu publisher, the recipe planner and the actual publication executor. Distinguish planned paths and user-reviewed paths from paths actually used during publication.
3. The exact on-disk schema-v1 samples and tests needed for lossless schema-v2 migration, including legacy Root shortcuts, flat folders, unfiled recipes, and current built-ins. No on-disk migration in Phase 0.
4. A verified step registry and capability matrix for resize/convert, ICC/sRGB, strip-all/strip-GPS, copyright/rights, date sequencing, watermark, contact sheets, preview and multiple outputs. Do not claim an operation is supported just because a similarly named standalone action exists.
5. A publication safety analysis covering on-disk collisions, same-batch collisions, late collisions, staging directory/filesystem, atomic no-replace support, cleanup, symlink behavior, source identity and cancellation. Record limitations on exFAT/FAT32/NTFS/SMB or other destinations as *to be tested*, not generalized claims of support.
6. A concise implementation map and focused acceptance matrix for the **first separately proposed change only**. Obtain approval before edits.

### 19.3 Final acceptance gates by milestone

| Phase | Gate | What must be demonstrated |
|---|---|---|
| 0 | Read-only audit accepted | Live-working-tree inventory, concrete dependencies, exact schema/exchange contracts and reproduction notes supplied; no edits. |
| 1 | Publication defect accepted | Review-approved exact output path consumed without renaming; disk, batch and late collisions blocked; completed-file atomic no-replace on supported filesystem; unsupported filesystem fails closed; cancellation/source integrity verified in Dolphin. |
| 2 | Storage and descriptions accepted | Old recipe library retained/backed up; legacy shortcuts retained; edits persist; 255-codepoint descriptions and built-in overrides work; duplicate menu labels are clear. |
| 3 | Full-text search accepted | Both dialogs search **all 255 description characters**, recipe name and full ancestor folder path with cross-field AND; filtered-out active recipe and dirty draft remain safe. |
| 4 | Browser accepted | Permanent `Built-ins` and `User` roots, nested User folders, readable KDE navigation, explicit safe folder deletion, usable 1366×768 layout and persisted geometry. |
| 5 | Exchange accepted | Import/export single and grouped JSON recipes, effective built-in description, safe `User / Imported` layout, destination policy, conflicts, fresh IDs, malicious-input defense, no automatic run or pin. |
| 6 | Each recipe accepted individually | Output, previews, metadata/color consequences and failure paths verified through the mandatory Review Changes gate in actual homebase Dolphin. |

Successful focused tests and a successful homebase installation are **not** user acceptance. Preserve approved behavior at every gate. For live tests follow the established natacha status check, complete-tree synchronization, `bash install.sh`, `kbuildsycoca6`, and explicit Dolphin launch using `homebase-dolphin` from natacha. No commits or pushes without separate explicit approval.

### 19.4 Decision on freezing

**v1.5 is the final design baseline for implementation planning**, not a claim that the current code satisfies it. Phase 0 may expose exact-signature or filesystem facts requiring a small recorded amendment. No speculative fourth architecture review is required in the absence of new evidence. The first authorized action, if approved, should be Phase 0 only, followed by an explicit go/no-go decision on the isolated publication defect.
