# KIM6 Metadata Tools: Metadata Editor and Read-Only Metadata Browser

**Version:** 1.2, complete consolidated design-review baseline extending editor v1.0.1 with a separate read-only Metadata browser (engineering qualification pending)
**Date:** November 12, 2026
**Supersedes:** metadata tools v1.1 (November 12, 2026); editor v1.0.1 remains the frozen write-policy baseline; earlier versions remain historical records
**Status:** Editor v1.0.1 remains the frozen write-policy baseline. The standalone read-only metadata browser is an agreed product direction; the refined viewer UI, explicit editor-launch affordance, and export defaults in v1.2 are design recommendations pending owner approval and empirical qualification. Neither tool is implemented or proven. No writer may be enabled until its applicable engineering gates pass.
**Repository target:** `docs/METADATA_EDITOR_DESIGN.md`
**Dolphin entries:** KIM6 > **Organize Metadata** > **View metadata…** (new separate read-only window) and **Edit metadata…** (existing proposed editor).
**In scope:** Still images only. **Video metadata viewing and editing are deferred.** An unsupported video selected with images is reported, not silently processed.

> **Read this first:** Sections 1–19 are the **only authoritative design contract**. Requirements and acceptance cases refer back to those sections. The appendix records historical decisions, external reviews, and earlier document versions, but creates **no competing rules**. A capability labeled *planned* is not implemented or proven. No KIM6 code change is authorized by this design document alone.

**Design-control note:** The v1.0.1 editor contract (META-001..092, WF-01..60, ENG-01..10) is preserved without reopening settled write rules. The **separate read-only Metadata browser** is tracked as VIEW-001..014, VB-01..10 and VENG-01..03. Version 1.2 refines this independent viewer, not the editor: explicit launch of a separate editor, Overview defaults, conservative report fields, structured extraction qualification, and delivery ordering. These viewer UX details remain recommendations for feedback, not owner-approved implementation or proven ExifTool behavior. No repository or media modifications are authorized by this document.

**Permanent KIM6 constraints:** Work from the latest complete `natacha` working tree, including uncommitted changes. Implement one feature at a time, then synchronize the entire tree to `homebase`, install, refresh `kbuildsycoca6`, and test through Dolphin in `/home/coolian/Pictures`. Obtain user acceptance before pushing. Use native PySide6/KDE/Breeze controls with KDE button roles. Use sentence-case labels, the term *image*, and no em dashes. All derivative actions default to **Beside each source** and must show actual output filenames in the mandatory Review Changes step.

## Executive baseline, version 1.2

- **Two deliberately separate tools** under Organize Metadata: a read-only **Metadata browser** for examining existing information, and an **Edit metadata…** dialog with its own Individual and Batch workflow. One window per selection for each action. They share a read model, not a write-capable browser UI. A user-clicked **Open in editor…** action may launch an independent editor for explicitly selected still images; no edits, transaction state, or permissions carry over.
- **Create copies** is the consistent default for all selection sizes. In-place and sidecar operations are explicit, future capability-gated modes. Recipes remain derivative-only.
- **No hidden writes or skips.** Only an explicit, freshly confirmed Review Changes plan may commit; blocked files can be excluded by named reason/category inside Review Changes with a clear acknowledgment and a new revision.
- **First writable scope:** validated local JPEG with six logical fields (Title, Caption/Description, Keywords, Creator, Copyright Notice, Rights Usage Terms). Other fields may be inspected but are read-only until qualified.
- **Legacy compatibility:** paired IPTC-IIM/XMP is the default for applicable fields; an advanced **Modern XMP only** storage profile can be selected upfront when qualified, as well as from an overflow warning; never a silent fallback.
- **Preservation:** staged output, source freshness validation, verified intended metadata, unchanged JPEG codestream and other protected structures, honest per-file outcomes. Persistent backups are required before any in-place edits.
- **Interchange:** machine-exact CSV/TSV and a separately labeled, tested spreadsheet-friendly profile; never promise lossless arbitrary spreadsheet round trips.
- **No catalog/cloud dependency, video viewing/editing in this new feature, audio/document tagging, silent image recompression, or silent metadata normalization.**

## Contents

1. [Principles and scope](#1-principles-and-scope)
2. [User experience and interface](#2-user-experience-and-interface) (including §2.1 standalone Metadata browser)
3. [Field registry and canonical JPEG metadata contract](#3-field-registry-and-canonical-jpeg-metadata-contract)
4. [Individual and batch operation semantics](#4-individual-and-batch-operation-semantics)
5. [Review Changes and exclusions](#5-review-changes-and-exclusions)
6. [Save modes, filenames, and iteration](#6-save-modes-filenames-and-iteration)
7. [Import, export, and text descriptions](#7-import-export-and-text-descriptions)
8. [Image/sidecar compatibility and provenance](#8-image-sidecar-compatibility-and-provenance)
9. [Preservation, transactions, and recovery](#9-preservation-transactions-and-recovery)
10. [Metadata conflicts and technical inspection](#10-metadata-conflicts-and-technical-inspection)
11. [Templates, navigation, and completeness](#11-templates-navigation-and-completeness)
12. [Privacy, accessibility, and malicious input](#12-privacy-accessibility-and-malicious-input)
13. [Performance and implementation boundaries](#13-performance-and-implementation-boundaries)
14. [Requirements register](#14-requirements-register)
15. [Acceptance scenarios](#15-acceptance-scenarios)
16. [Negative and edge-case register](#16-negative-and-edge-case-register)
17. [Delivery stages and implementation gates](#17-delivery-stages-and-implementation-gates)
18. [Open engineering validations](#18-open-engineering-validations)
19. [Change control and handoff](#19-change-control-and-handoff)
20. [Appendix: review disposition and decision history](#20-appendix-review-disposition-and-decision-history)
21. [References](#21-references)

## 1. Principles and scope

**Product objective:** A pair of still-image metadata tools, a viewer and an editor, suited to both casual image users and professional photographers/digital asset managers. Professional standards are supported underneath, while everyday editing is legible and uncluttered. KIM6 does not become a mandatory media catalog, gallery, or cloud service.

**Users and jobs:** Read and compare existing image metadata without risk of edits; individually caption images, add rights and creator credits, tag large shoots, inventory missing metadata, inspect metadata from RAW+JPEG collections, and import structured captions maintained in LibreOffice or other tools. Retain existing file-based workflows in Dolphin.

**First writable increment:** JPEG images on qualified local filesystems, with Title, Caption/Description, Keywords, Creator, Copyright Notice, and Rights Usage Terms. The six-field set is a release *target* subject to individual field safety verification; a field that does not pass is disabled with an honest explanation, not simulated. Expanded fields and formats are staged capabilities, not scope creep for this increment.

**Later still-image editing functionality:** PNG (still), TIFF, WebP (still), HEIC/HEIF, AVIF, RAW sidecars, accessibility fields, people/places, partial historical dates, hierarchical keywords, advanced rights, metadata completeness, and spreadsheet round-trip. The separate viewer may read a broader set of still-image types **only when reading them is qualified**, independent of write support. Each capability requires its own qualification. Animated images (including APNG) follow KIM6's existing fail-closed safety policy. Video editing is entirely out of scope.

**Fundamental invariants:**

0. The read-only Metadata browser contains no editor/write/rename/sidecar/repair operation and makes no intentional changes to selected media or companions. An explicitly clicked **Open in editor…** action may launch the separate editor using only the user-confirmed selected-file paths, with no pending operations or automatic Review/Apply. Copying values and explicitly exporting a report may create user-requested clipboard/report output, but never alter source media.

1. No metadata is written merely by changing a control, importing a row, or choosing a template.
2. No unedited or unrecognized metadata is silently discarded to create a normalized replacement.
3. No source image is modified under Create copies; no sibling RAW/JPEG/XMP or motion-video companion is modified merely because it shares a basename.
4. No file outside the exact authorized target set is modified or used as a substitute destination.
5. No validation bypass, hidden fallback from copies to originals or sidecars, hidden skipped file, or claim of batch-level atomicity.
6. No claim of supported writes or preservation stronger than verified evidence.

## 2. User experience and interface

The Dolphin action **Edit metadata…** launches one PySide6/KDE dialog for the whole selection, not one dialog per image. Main layout: resizable image list and preview at left; main editable fields at right; a compact toolbar for Import and Export; footer for mode, scope, pending changes, save strategy, destination, and **Review Changes…**. Preview generation and metadata scanning must not freeze the UI.

```text
Edit metadata                                             48 images
[Individual] [Batch]                         [Import…] [Export…]
+--------------------------+-------------------------------------------+
| Image list / thumbnail   | Describe | Keywords | People & Places    |
| IMG_1042.jpg             | Creator & Rights | More Metadata       |
| IMG_1043.jpg             |                                           |
| ...                      | Title                                     |
|                          | [____________________________________]    |
| [preview]                | Caption / Description                     |
|                          | [____________________________________]    |
| filename, warnings       | Keywords                                  |
| previous / next          | [mountains] [sunrise] [+]                  |
+--------------------------+-------------------------------------------+
| Scope: Current image   Pending: 2 fields                |
| Save: Create copies   Destination: Beside each source   |
| Issues: 1   [Cancel]                   [Review Changes…] |
+--------------------------------------------------------+
```

The five sections are **Describe**, **Keywords**, **People & Places**, **Creator & Rights**, and **More Metadata**. *Describe* is the default. Headline and accessibility descriptions are separate from Caption/Description; detailed GPS editing belongs to the existing Location/GPS tools. Advanced raw tag/namespace inspection is available without overwhelming the default form.

**Always-visible independent indicators:** (a) active operation scope: Current image or Batch N selected; (b) number of pending edits and targeted files; (c) selected save mode with explicit destination. The currently previewed thumbnail must **not** implicitly change batch scope. An optional All selected files aggregate view is read-only until a batch operation is deliberately chosen.

**Navigation and editing:** Individual caption edits belong to the current image and stay in memory while navigating to another image. Batch operations remain independent. Switching modes, closing the dialog, clearing selection, or otherwise discarding pending edits requires an explicit keep/discard/cancel choice; no media is written until review and Apply. Use predictable Next/Previous shortcuts, sensible tab focus, screen-reader labels, text-only explanations of statuses, and remembered window/splitter sizing. Avoid forests of tooltips, modal warning cascades, or scrollable dead space.

**Status vocabulary:** Absent, Present empty, Present populated, Unreadable, Conflicting, Unsupported; Mixed is a batch aggregate; Pending Replace and Pending Clear are operations, not read states. Show reasons for blocked files. Never present unreadable or conflicted data as blank.

**UI copy examples:** “48 images selected”; “Batch: 46 eligible, 2 blocked”; “Title is 72 UTF-8 bytes; legacy IPTC limit is 64”; “Create copies”; “Destination: Beside each source”; “Planned result: IMG_1001-metadata.jpg”; “Exclude 2 blocked files”; “Write modern XMP only (limited compatibility)”; “Continue editing created copies”. Controls are actual native Qt widgets, not separate decorative simulations.

### 2.1 Standalone Metadata browser (introduced in v1.1, refined in v1.2)

**Placement and identity:** Under **Organize Metadata**, use adjacent actions **View metadata…** and **Edit metadata…**. The first opens a separate window titled **Metadata browser**. There are no editable metadata fields, Apply button, Review Changes gate, automatically opened editor, or write controller in the browser. Sharing read-only parsing and field definitions with the editor is encouraged; sharing its write transaction/pending state is not. Opening or closing the browser cannot discard, commit, or import an editor's pending operations. The viewer remains useful even before any metadata-writing capability passes its gates. A user-invoked secondary **Open in editor…** control is permitted only as the explicit, isolated launch defined below.

**Scope:** Operate on the selected still-image file(s) handed off by Dolphin. No implicit recursive directory scan, database/index creation, search outside the selection, motion-photo extraction, or network/cloud lookup. Multiple selections remain in one window. Show a visible unsupported-file row for a video or other non-image, without attempting to browse its metadata in this phase. Display metadata for a read-qualified still image even when KIM6 cannot edit that image. No file format is promised readable until tested.

**Proposed browse layout:** Resizable source list and optional image preview at left; content at right. The planned views are **Overview** (human-readable groups), **All tags** (available tags), and later **Compare** (selected-file differences). The browser is a distinct application window, **not a sixth editor section** and not a replacement for the editor's More Metadata inspection. The first viewer increment contains **Overview + All tags + Search**, and Compare ships as a separate second increment after qualification. Default Overview order: **Description**, **Creator & Rights**, **Camera & capture**, **Location**, **File & color**, **Other metadata**. These are presentation groups, not new metadata schemas.

```text
Metadata browser                                         48 images
[Overview] [All tags]                   [Search tags or values…]
+-------------------------------+-----------------------------------+
| Image selection               |  Description                     |
| IMG_1042.jpg                  |  Title: Mountain sunrise         |
| IMG_1043.cr3                  |  Caption: (not present)          |
| ...                           |  Creator & Rights                |
| [preview, if available]       |  Creator: A. Photographer        |
|                               |  Copyright: (not present)        |
| IMG_1042.jpg, JPEG, read OK   |  Camera & capture                |
|                               |  Camera: Canon EOS R5            |
|                               |  [ ] Show empty fields           |
+-------------------------------+-----------------------------------+
| 48 selected, 45 read, 2 unsupported, 1 unreadable       |
| [Open in editor…] [Copy value] [Export report…] [Close]|
+----------------------------------------------------------+
```

**Overview:** Favor approachable labels and original data types. Present groups in this order: **Description**, **Creator & Rights**, **Camera & capture**, **Location**, **File & color**, **Other metadata**. Default to showing all populated/conflicting/unreadable fields **plus the six core descriptive/rights slots** (Title, Caption/Description, Keywords, Creator, Copyright Notice, Usage Terms), even when those six are absent. Hide other merely absent fields by default; provide a persistent, clearly labeled **Show empty fields** checkbox (initially off) to reveal the complete supported schema. This filter never hides warnings, conflicts, unreadable values, or core-slot absence. Display **Not present**, **Present but empty**, **Unreadable**, **Conflicting**, or **Unavailable in this format** as distinct states, never interchangeable blanks. Show duplicate values from different sources with a source badge/line rather than silently declaring one correct. Dates with unknown timezone or partial precision remain unknown/partial; locale formatting is presentation-only. Distinguish filesystem properties, embedded EXIF, IPTC-IIM, XMP, ICC and camera MakerNotes, and an external XMP sidecar when a relationship has been established. Metadata read errors do not imply field absence.

**All tags:** Searchable table with columns **Field**, **Value**, **Group / namespace**, and **Source file**. A toggle may switch human-friendly names to raw qualified tag names. Duplicate and unknown tags should be discoverable if the selected metadata-reading backend exposes them safely; do not advertise an exhaustive binary decode. Display huge strings with a collapsed preview and a clear **Show full value** operation. Binary blobs show a type/size placeholder by default, not megabytes of unreadable text. Sort/filter by category, namespace or issue without losing the user's active selection. Per-file search is the default; searching across all selected files must be labeled differently. Clearly show **0 matches** versus **0 metadata tags read**.

**Compare and selection aggregate:** When 2 or more images are selected, offer a differences-oriented comparison of selected files and fields; highlight **Same**, **Different**, **Missing**, **Unreadable**, and **Conflict** without color-only communication. To avoid enormous matrices, use bounded/virtualized rows and let the user choose two files first, expanding to more only when performance is proven. A per-file navigation step is not a batch edit. No comparison result may trigger a write or decide which source should be authoritative. A compact count of missing captions or GPS-present items may link to filtered files, but a full collection-health report is a later capability.

**Copy and report export:** Allow explicit Copy value, Copy field and value, Copy selected rows, and **Export report…**. Initial report formats may be human-readable text and structured JSON/TSV only after their output representations pass testing; no automatic export and no silent inclusion of all tags because a filter is active. Show report scope (current image vs selected files), exact columns/fields and output path before exporting. The conservative **initial report profile has Description, Camera & capture, and Creator & Rights groups checked**, but **GPS coordinates, camera/device serial numbers, full local paths, personal contact information and other sensitive identifiers remain unchecked regardless of their group**. These need explicit per-field opt-in and a privacy warning. An advanced all-tags export must separately acknowledge sensitive inclusion. Metadata may include GPS, contact information, face identifiers, or exact capture times: **viewer display is not itself permission to broadcast them**. Respect chosen redactions; avoid leaking sensitive values through headers, filenames or hidden columns. A report is an explicitly generated file, never an altered image/sidecar. Report exports do not bypass the editor's write rules because they never modify media.

**No unintended source changes:** Metadata reads, thumbnail generation, clipboard operations, filtering, comparison, and report previews may not intentionally write to selected files, related files, or their directories. No embedded-thumbnail repair, orientation normalization, ExifTool write mode, file retimestamp, sidecar creation, or source-directory thumbnail cache. Internal ephemeral caching in memory is permitted; any optional persistent cache must be separately designed and must not become a catalog or metadata authority. Read-only should be presented as a property of the tool, not a guarantee that all metadata parses are correct.

**Security and responsiveness:** Treat tags and embedded thumbnails as untrusted input; enforce file-size/parse/time/memory limits, do not interpret metadata as markup or execute embedded URLs, avoid arbitrary linked-document extraction, isolate per-file failures and support cancellation of ongoing scans. Use asynchronous incremental reads and virtualized result lists; show **Scanning**, **Ready**, **Partial**, **Unsupported**, and **Failed** states with explanatory details. Never silently omit unreadable or unsupported selected files. A malformed image must not crash the whole window.

**Read-engine contract:** A narrow read-only metadata service returns file identity, capability, source/namespace-qualified tags, typed values/language, read diagnostics and explicit sidecar origin; it cannot accept edit operations or write targets. Reuse the editor's canonical *field definitions* without importing its write transaction machinery. **Do not parse human-formatted ExifTool text** for canonical metadata. Under VENG-01 evaluate bounded structured output such as `exiftool -j -a -u -g1 -struct` and a uniquely qualified variant using `-G4` against duplicate-tag fixtures. ExifTool warns that JSON entries with identical names may still be suppressed even with `-a`; demonstrate that all required duplicates can be distinguished, or report a qualified limitation. Verify language alternatives, arrays, XMP structures, unknown tags, MakerNotes, source grouping, multiline/Unicode values and sidecar identity against fixtures. `-struct` is not proof that every language alternative is exposed losslessly; use supplementary targeted extraction where required. **Do not use unbounded `-b` binary extraction** in the general listing: show bounded type/size placeholders, with explicit separate inspection only if safely implemented. Bound command output, runtime, memory and previews, and capture read errors per file. **Viewer read support and editor write support have independent capability matrices.**

**Explicit editor launch (independent handoff):** When the user clicks a secondary **Open in editor…** control, pass only the **current explicitly selected still-image rows** as file paths to a **new, independent** Edit metadata… window. Do not infer that the entire Dolphin selection or current preview is intended when multiple rows are selected; show the count (for example, **Open 3 selected images in editor…**). No viewer filters, inferred corrections, read caches, clipboard values, metadata edits or pending operations are transferred. The editor starts with its standard **Create copies** default and zero pending changes; all writer capability checks and Review Changes requirements remain intact. Viewer stays open. If the editor action is not installed/available or the selected files have no supported editor capability, disable the control or give a reason instead of silently launching an unsupported write workflow. The browser itself remains read-only. This convenience does not become a dependency of Stage V.

**Proposed first viewer milestone:** one still image or a modest selection, Overview + All tags, search, preview, visible core absent slots, clear source labels, meaningful read/unsupported states, Copy value, and Close. **Open in editor…** may be included when the separate editor is installed and qualified, but is not necessary for Stage V acceptance. Compare, advanced filters, report export and bulk completeness follow after the initial viewer passes acceptance. This milestone has no write dependency and need not wait for the JPEG publisher, but repository integration must first be inspected on `natacha`.

**Proposed v1.2 viewer UX decisions awaiting owner sign-off:** (a) ship Compare in the **second** viewer increment; (b) show **Description, Creator & Rights, Camera & capture** first in Overview, with the six core slots always visible; (c) hide nonessential absent fields behind **Show empty fields**; (d) default report groups to Description, Camera & capture, and Creator & Rights with sensitive fields opt-in; (e) permit only the **explicit independent** Open in editor… launch described above. None of these decisions block read-only Stage 0 qualification. They are not new permissions to modify media.

## 3. Field registry and canonical JPEG metadata contract

The field registry is the common typed source of truth for editing, CSV mapping, templates, review, write planner, and verification. Each entry supplies logical ID and UI help; value type/cardinality and language alternatives; metadata source/group; qualified XMP and IIM targets; allowed operations; format-specific eligibility; limit/encoding validation; equality rules; unaffected-structure preservation requirements; import/export representation; verification procedures; and user-visible remediation.

### 3.1 First JPEG field mappings and legacy byte limits

These are **standards-backed intended tag destinations**, not a claim that an exact ExifTool command sequence has been tested on `natacha`. IPTC-IIM limits are **octet (encoded byte) limits**, not Unicode character limits.

| UI logical field | Intended XMP property / ExifTool tag | IPTC-IIM equivalent / ExifTool tag | Maximum IIM bytes | Value model |
|---|---|---|---:|---|
| Title | `dc:title` / `XMP-dc:Title` | 2:05 Object Name / `IPTC:ObjectName` | 64 | XMP language alternatives; one legacy scalar |
| Caption / Description | `dc:description` / `XMP-dc:Description` | 2:120 Caption/Abstract / `IPTC:Caption-Abstract` | 2000 | XMP language alternatives; one legacy scalar |
| Keywords | `dc:subject` / `XMP-dc:Subject` | 2:25 Keywords / `IPTC:Keywords` | 64 **per keyword** | XMP bag; repeatable IIM terms |
| Creator | `dc:creator` / `XMP-dc:Creator` | 2:80 By-line / `IPTC:By-line` | 32 **per creator** | Ordered XMP sequence; repeatable IIM entries |
| Copyright Notice | `dc:rights` / `XMP-dc:Rights` | 2:116 Copyright Notice / `IPTC:CopyrightNotice` | 128 | XMP language alternatives; one legacy scalar |
| Rights Usage Terms | `xmpRights:UsageTerms` / `XMP-xmpRights:UsageTerms` | **No IIM equivalent** | N/A | XMP language alternatives |

**Not all six fields are paired.** Usage Terms is XMP-only by standard design; it must not be written into a vaguely similar legacy field. Title is distinct from Headline; Description is distinct from accessibility-specific Alt Text and Extended Description. Existing technical EXIF/MakerNotes, dates, embedded previews, orientation, and ICC data are inspection/preservation concerns, not permission to rewrite them.

**Argument shapes for engineering validation (NOT verified commands):** Every write uses qualified tag names and separate subprocess arguments, never shell interpolation or a guessed tag group. ExifTool list-type tags (e.g., `XMP-dc:Subject`, `XMP-dc:Creator` and `IPTC:Keywords`) are **not** comma-delimited scalar strings. The writer must prove repeated qualified `-TAG=value` assignments, or a carefully tested `-sep` strategy that does not split literal commas, semicolons or Unicode phrases. Preserve order for `dc:creator` (`rdf:Seq`); preserve independent terms for `dc:subject` (`rdf:Bag`). Test append, replace, remove and no-op behavior without accidentally flattening or accumulating values.

**Language alternative trap:** ExifTool documents that writing a `lang-alt` tag without a language qualifier can remove other languages. For default-language edits, qualify `x-default` explicitly, for example `-XMP-dc:Title-x-default=<value>`, `-XMP-dc:Description-x-default=<value>` and `-XMP-dc:Rights-x-default=<value>`, with the actual field-specific syntax validated first. `UsageTerms` is also language-alternative. A localized `fr-FR` or other entry is a distinct value; its modification requires separate explicit scope and review. Do not silently replace all language alternatives.

**IPTC charset trap:** `-charset iptc=UTF8` is not a universal conversion of existing legacy text. Detect existing encoding as far as reliably possible; preserve unedited values; qualify a transition to UTF-8 and `IPTC:CodedCharacterSet` on fixtures, and block ambiguous cases. Validate exact flags, arrays, language targeting, charset transitions and read-back with official IPTC fixtures and installed ExifTool versions under ENG-01.

### 3.2 Compatibility storage profiles and overflow resolution

**Default profile: Compatible XMP + IPTC.** For fields with both representations, update the logically equivalent XMP and IIM tags and verify both. For Rights Usage Terms, XMP is the only standard target; that fact does not imply degraded compatibility. An unedited conflict remains unchanged. Editing a conflicted field requires an explicit chosen source/value and a reviewed resolution.

**Advanced profile: Modern XMP only (limited legacy compatibility).** Expose a single clearly labeled **Storage profile** selector under **More Metadata**, also visible as a compact summary in Review Changes. The selected profile applies consistently to the **fields being edited in the current operation**, not blindly to unedited fields. It is a deliberate choice for users who need long text or modern-only workflows. It is **offered only when the corresponding exact writer, selective legacy handling and read-back verification have passed ENG-04**. A non-capable editor shows the control as unavailable with a reason, not as an optimistic checkbox. A mixed batch must not change the profile automatically for individual files.

Under Modern XMP only, write the selected modern XMP values. **Do not silently create an inconsistent legacy shadow value.** For each changed field, if an existing IIM equivalent would contradict the final XMP value, selectively remove **only that field's obsolete IIM representation** if this is qualified, with a separate reviewed removal count and affected filenames. If the IIM equivalent already matches, preserve it unless the user explicitly requested its removal. Preserve unrelated IIM properties in the same container. If the tool cannot safely perform selective removal or prove the remaining legacy fields are intact, block that field/file. This mode does not promise full IPTC-IIM interoperability.

**Removal of the final legacy IPTC-IIM dataset:** The ENG-04 qualification fixtures must include a JPEG whose Photoshop APP13 IPTC resource (`8BIM` resource ID `0x0404`) contains only the IIM dataset being removed. Examine the staged result for zero-length/orphan `0x0404` resources, empty APP13 Photoshop containers, incorrect lengths/padding, and any unrelated remaining Photoshop resources. Do **not** assume ExifTool always leaves an empty resource or always removes it. An intact but empty representation is not automatically corrupt; qualify its behavior with `ExifTool -validate` diagnostics **and** independent resource/third-party reader checks. Remove or rewrite a container only if that action is explicitly qualified and preserves all unrelated APP13 resources. If cleanup or interoperability cannot be proven, block the operation rather than publishing an uncertain JPEG.

**Encoded-byte UX:** For legacy-constrained fields, show UTF-8 byte count/limit live while typing, with a quiet near-limit warning (initial 80% threshold subject to usability tests). For a different qualified encoding, compute actual target-encoding bytes; Unicode character count is not the IIM byte count. If a value exceeds the compatible profile's limit, offer **Shorten value** or **Switch to Modern XMP only**, where qualified. The inline recovery choice and the advanced selector are two entry points to the **same global operation profile**, never conflicting per-field modes hidden in the batch. Changing the profile invalidates the review and recomputes all affected files/legacy removals. The warning must explain how many files and fields lose legacy representation, not simply say "XMP only".

**Exact review language:** “Modern XMP only: some older applications may not display these changes. N legacy values will be removed because they conflict with the updated XMP values.” The review lists each affected field/file; neither silently truncates IIM nor deletes an entire IPTC block. A field with no applicable legacy counterpart is not counted as a compatibility loss.

### 3.3 Typed values and keyword equality

Each logical value carries read status, source namespace/group, language/ordering where relevant, original encoded representation and validation diagnostics. Distinguish absent, empty, unreadable, and conflicting values, and preserve multi-language XMP arrays and ordered creators. An initially supported field with an unrepresentable complex value is read-only/blocked, not flattened. **Mixed** belongs only to batch aggregation. **Clear** is a deliberate operation, not a blank edit box.

Keyword add/remove/replace uses individual exact terms, including multiword phrases. Preserve capitalization, Unicode, hierarchy and stable ordering unless the user explicitly chooses a normalized operation. Do not merge case-folded or normalized-looking keywords automatically. Hierarchical keyword conventions and rating/label mappings need separate external interoperability validation before offering writes.

### 3.4 More fields, later

Read-only inspector first: Headline, Alt Text, Extended Description, image subject/location, people shown, IPTC Date Created (including year-only and month-only historical precision), EXIF capture time and offsets, rights URLs, licensing/PLUS, region structures, technical EXIF, GPS summary, and C2PA. No invented date/time precision or timezone; no accidental EXIF DateTimeOriginal updates. Only validated fields become editable in later increments.

## 4. Individual and batch operation semantics

**Individual:** Each selected image has separate in-memory pending edits. Navigating does not apply changes or broadcast captions to all files. The user can edit one image while the rest remain unchanged.

**Batch:** Every scalar field defaults to **Leave unchanged**. Other operations:

| Operation | Exact behavior |
|---|---|
| Leave unchanged | No touch, including existing conflicts and all source representations |
| Fill empty | Apply to readable, logically absent or explicitly present-empty fields, not unreadable/conflicting/unsupported |
| Replace | Explicitly replace eligible target fields; show number of overwritten populated values and exact impacted files |
| Clear | Explicitly remove selected metadata values in all applicable representations; show count and compatibility consequences |
| Add keywords | Set-union by exact term under validated rules, retaining existing terms and hierarchy |
| Remove keywords | Remove explicitly named exact terms only |
| Replace keywords | Set the exact selected list, with visible removal count and order/duplicate policy |

A mixed batch such as **72 populated and 28 empty** displays **Multiple different values (72 populated, 28 empty)**, not a blank caption. Choosing Fill empty affects only 28 eligible entries after reviewing individual applicability. Conflicted or unreadable representations do not count as empty. If one of two equivalent namespace representations is absent and another populated, the **logical field is populated**, not an invitation to fill.

Actual per-file eligibility is computed from requested field + file structure + provenance + strategy + destination/filesystem + existing metadata + value encoding + source freshness. Unsupported files are not hidden or called successful. An operation that results in no logical changes is **No change required** and creates no copy. Batch behavior and user-selected targets remain clear even if the preview selection changes.

## 5. Review Changes and exclusions

Every write path, imported record, keyword operation, template, and restore action ends in a standardized **Review Changes** step with a separate explicit **Apply Changes** action. The initial editor never directly writes. The review is a *snapshot* of the exact typed operations, source identities/fingerprints, metadata baselines, resolution choices, save mode, final output paths, sibling decisions, and user exclusions. It is not a loose preview that a later writer can reinterpret.

**Review summary includes:** Selected; Eligible to change; No change needed; Excluded; Blocked; Awaiting attention; exact output path/filename or source target; old → planned values for every affected field; synchronized XMP/IIM tags; special removal warnings; destination and backup behavior; storage estimates; pending conflicts; provenance; and per-file detail for large batches. Search/filter and virtualized rows prevent huge pages.

### 5.1 Grouped blockers and explicit inline exclusions

Apply remains disabled **while any blocked file is included**. Do not lump unrelated problems into one unexplained count. In Review Changes, group blockers by actionable **reason**, with file names, expandable details and a suggested remediation. For example: *Unsupported format (1 GIF)*; *Permission denied (1)*; *Content Credentials/provenance (1)*; *Malformed/corrupt JPEG (1)*; *Metadata value/legacy limit (N)*. A file can carry more than one reason; category counts must not double-count unique excluded files.

- Offer **Exclude 1 unsupported file**, **Exclude 1 permission-denied file**, and similar explicit reason-group actions, plus **Exclude all currently blocked files** only as an additional deliberate action. Category and bulk controls start unchecked/unselected; none act silently. Selecting any action identifies the exact distinct filenames before acceptance. Excluded files retain their reasons in the final report.
- A **field/profile blocker** is not automatically a file-exclusion recommendation. A legacy byte-limit failure should first offer correction or a qualified Modern XMP only profile; excluding the file is still possible explicitly. Corruption, permission errors and signed-media blockers are visibly differentiated from benign non-image selections.
- Recompute file eligibility, unique counts, planned output names, storage needs and field-level changes **inside the same Review Changes dialog**. Increment the immutable plan revision and revoke previous Apply approval. The user must confirm the new summary before Apply is enabled. No forced return to Dolphin.
- Allow inspection and **Include again** before confirmation; never automatically exclude a newly blocked file during commit. In a 200-file selection, explicitly excluding a GIF and a read-only file produces “200 selected, 198 eligible, 2 excluded by user,” not “200 completed.”

### 5.2 Immutable plan and late changes

Changing a field, scope, save mode, output directory, file order relevant to naming, companion policy, namespace profile, collision state, exclusions, source bytes, or target identity invalidates prior approval and requires a new plan confirmation. During commit, revalidate a suitably strong source fingerprint (not only mtime), file identity and destination availability. A late collision or external modification must not result in publishing under an old plan. Snapshotting metadata once is not permission to overwrite a file changed by another application.

Example summary:

```text
Review changes
200 files selected    198 eligible    2 excluded by user
121 will change       77 no change required
Save mode: Create copies
Destination: Beside each source  [Change Destination…]

[Show affected] [Show excluded] [Show warnings] [Show all]

Example result: IMG_0001-metadata.jpg
Title: Old title -> New title
Storage: Compatible XMP + IPTC

[Cancel]                     [Apply Changes]
```

**Results** distinguish Verified committed; Unchanged; Excluded by user (with category and filename); Blocked; Failed before publish; Failed during publish/recovery-needed; and Not attempted due to cancellation. Grouped blocker counts must use unique-file totals and display multi-reason membership without duplicate exclusions. Never call a partially completed batch fully successful.

## 6. Save modes, filenames, and iteration

**Default for any count:** **Create copies**. This never modifies originals, including timestamps or associated sidecars. **Edit originals** is a future explicit opt-in with persistent recovery and a separate approval. **Write XMP sidecars** is a separate explicit, capability-dependent option with no silent fallback. A nondefault preference may be remembered only after its safety is demonstrated and made conspicuous at each review. Recipes continue to produce derivatives only.

**Default destination:** **Beside each source**. **Change Destination…** selects an optional shared destination; it must update both planned target filenames and actual output publishing. The directory field/picker must support a usable editable path in line with other KIM6 UI work. Always show **Planned result** per source before Apply, including mixed-directory selections.

**Naming:** Reuse KIM6 Output Filenames affix settings. Without an action-specific affix, append `-metadata` to the stem (`IMG_0001-metadata.jpg`), preserving extension case (`.JPG`). Resolve existing file collisions with stable numeric disambiguation (`-metadata-2`) for the *reviewed directory state*. Never overwrite an existing file. Shared destination colliding basenames from different directories are disambiguated. A late collision triggers fresh review; no race-driven silent renaming. No-op means no derivative.

**After commit / continued editing:** Include **Continue editing created copies** (or **Open created copies in editor**) only when verified outputs exist. The action opens a *fresh editing context* containing only actual verified outputs and no previously committed pending operations; Excluded/Failed/Unchanged are not inventively turned into outputs. This **does not change the global Create copies default**.

When continuing, make the next write strategy an **explicit choice**, with consequences and final filenames shown before the next review:

1. **Create another version (default, always available when eligible).** Keep all current derivatives intact. Use deterministic, provenance-aware naming: for a verified output of this KIM6 editing session `IMG_0001-metadata.jpg`, the next generation is `IMG_0001-metadata-2.jpg`, not `IMG_0001-metadata-metadata.jpg`. Track the *original base stem and configured affix from the verified transaction*, rather than stripping text from arbitrary source filenames that happen to end in `-metadata`. Honor action-specific affix rules and existing `-N` version collisions; never silently overwrite.
2. **Update these created copies (in place, recoverable), optional and gated.** Available only after the full **Edit originals** backup, journal, preservation, filesystem and restore safety requirements in §9.3 have passed. A newly created output is now an existing user file; being generated this session does **not** exempt it from full protection. Show explicit original-output target paths, persistent backup/storage costs and in-place consequences. Require the standard Review Changes confirmation. If this capability is not qualified in Stage 1, disable it with a reason instead of promising overwrite-on-iteration.

A second pass must never silently select the original source files or change the save strategy just because the user pressed Continue. Encourage editing title/caption/keywords together before the first Apply, but do not force it.

**Related media:** Discover plausible RAW/JPEG/XMP relationships with provenance and path confidence, but do not assume shared basename means shared identity. The selected JPEG alone is changed by default. Companion sync is a separately reviewed future action. No writes to related video/motion components.

## 7. Import, export, and text descriptions

**Supported concepts:** CSV, TSV and UTF-8 text descriptions, with explicit field mapping; export metadata to CSV; KIM6-controlled round-trip edits. This is a Stage 3 workflow, not a prerequisite for the first JPEG writer.

### 7.1 Import workflow

1. Choose CSV/TSV or text. Detect UTF-8 BOM, delimiters, quoted commas, escaped quotes, multiline cells and newline styles. Show a preview before interpreting any value.
2. Match spreadsheet records to selected media by an explicit key: safe relative path, verified KIM6 round-trip identity, or *only if unambiguous* basename. Do not silently match duplicate basenames in different folders, and prevent path traversal outside the authorized selected set.
3. Map columns to logical metadata fields; show unsupported fields and duplicate mappings. Distinguish empty spreadsheet cells, absent columns and an explicit **Clear** operation. Blank/absent means **Leave unchanged** unless the user explicitly selected a supported alternative.
4. Choose per-field conflict semantics: Leave, Fill empty, Replace, Clear, keyword Add/Remove/Replace. Identify old baselines and file changes. Any stale record must be reviewed as a conflict, not blindly applied.
5. Preview matched/unmatched/ambiguous/duplicate/stale rows, destination paths and each planned field change, then use normal Review Changes. No import writes immediately.

**Plain text:** Support one UTF-8 description applied to chosen images or matching `IMG_0001.txt` text to `IMG_0001.jpg` with ambiguity checks. Literal quotes, commas, Unicode, newlines and meaningful whitespace are preserved. Show any trimming/normalization explicitly.

### 7.2 Two explicitly distinct CSV export profiles

| Profile | Purpose | Guarantees and cautions |
|---|---|---|
| **Machine-exact CSV/TSV** | Scripts, backups, deterministic KIM6-to-KIM6 exchange | Quoted RFC 4180-style fields (or specified TSV), exact Unicode strings, explicit schema version, chosen relative/opaque identifiers, original baseline, typed operations. **Not safe to open casually in a spreadsheet when values begin with formula-triggering characters.** |
| **Spreadsheet-friendly CSV** | Inspect/edit in supported LibreOffice or other tested applications | Harden dangerous spreadsheet cell prefixes according to the tested application/profile; explain that exported cells may have escaped text and that arbitrary spreadsheet resaving can alter data. Preserve original values through a documented, reversible *KIM6-controlled* scheme when its markers/baseline survive. If markers were altered/lost, flag ambiguity and require human review; never guess or silently strip a leading quote or tab. |

Use an export profile selector with the safest spreadsheet-friendly option recommended when opening in LibreOffice is the user's intended workflow; explicitly label machine-exact mode for technical users. The version and profile are recorded in the document/header or companion verified data. Never assume all spreadsheet applications preserve formatting, leading zeros, long numeric identifiers or dates. Prefer stable opaque record identifiers rather than relying on spreadsheet interpretation of bare long numeric keys; include relative paths that remain human-checkable.

**Formula injection:** Quoting CSV cells alone does not stop formula execution. Danger includes prefixes `=`, `+`, `-`, `@`, control characters and certain full-width equivalents, plus delimiter/quote manipulation. Some programs strip leading apostrophes/tabs when files are edited and saved, so a reversible escaping algorithm must be qualified against exact application/version workflows. Import must preserve literal values such as `=35mm lens`, not incorrectly call them formulas, discard the `=`, or consider them user edits merely because the export was protected. If safe round-trip cannot be proven for a profile, warn or block rather than promise it.

**Privacy:** Exported columns are explicit and previewed. GPS, contact information, full absolute paths and serials are unchecked by default. External-facing inventory export without KIM6 control columns is useful, but it is **not** automatically a safe editable round-trip file.

## 8. Image/sidecar compatibility and provenance

**Eligible initial write:** a real, qualified local JPEG with supported internal structure, field, metadata encoding, file identity, destination and provenance status. File extension alone never determines permission. Unsupported structures are viewable when safely readable, and read-only with a reason. An unknown or unsupported `smb://`, KIO URL, network mount, symbolic link or multiple-hardlink source is not silently redirected through a temporary copy for in-place editing. Copying a readable source to a qualified local output may be evaluated separately.

**Candidate later formats:** still PNG, TIFF, still WebP, HEIC/HEIF, still AVIF, RAW plus XMP sidecar. Format-specific preservation tests are required. GIF and animated images are conservatively inspect-only or blocked. APNG remains fail-closed until independently qualified. Video metadata, motion-photo components and audio-only formats are out of scope.

**Companions:** Detect `DSC_0042.CR3`, `DSC_0042.JPG`, `DSC_0042.xmp` as *possibly related* and disclose the relationships. Never change the RAW or sidecar when only the JPEG was selected. Embedded XMP and sidecar XMP are separate stores: do not treat syncing equivalent IIM/XMP *within one image* as approval to edit a companion sidecar.

**C2PA/Content Credentials:** Existing signed/provenance media may be invalidated by a metadata write. Detect where actual installed qualified tooling allows; a detected or indeterminate/failed relevant provenance check blocks the operation unless a proven preservation/re-signing path exists. A tool's failure to detect credentials is not proof that credentials never existed. Preserve original data and show a concrete reason, not merely a generic error.

## 9. Preservation, transactions, and recovery

The editor is a **targeted metadata writer**, not a library that serializes only known fields back into a fresh image. Unrelated XMP, IIM, EXIF, MakerNotes, ICC profiles, embedded previews, orientation, camera data, metadata-language alternatives, application-specific blocks and opaque segments must not be silently dropped. Preserve filesystem mtime by default where qualification permits, while distinguishing capture dates and legitimate XMP metadata-modify timestamps.

### 9.1 Per-file staged pipeline

1. Safely read and inventory source, companions, metadata source groups, provenance and filesystem properties.
2. Construct exact typed plan and validate field limits, file identity, eligibility, privileges, destination, collision, free space and unsupported structures.
3. For Create copies, stage on the eligible target filesystem; for original editing (later), establish persistent verified pre-edit recovery material and durable journal **before** publication.
4. Write fully qualified metadata to the stage, never streaming destructive changes over the live original. Keep original input available for verification.
5. Independently re-read each intended XMP/IIM target and ensure requested operations produced exact logical values while preserving unrelated metadata and media structures.
6. Revalidate source identity/fingerprint and final target collisions immediately before commit; invalidate stale plans rather than racing ahead.
7. Flush and publish the verified stage using a tested atomic rename/commit pattern on supported local filesystems, with documented fsync and directory durability behavior. Re-read the published output and record a truthful result.
8. Stop safely on failure, and separate Verified, Unchanged, Excluded, Blocked, Failed, Not attempted and Recovery needed.

Do not promise multi-file global atomicity. A batch crash after 31 successful files is not a full rollback; a durable per-file journal must identify what committed and which files need human recovery. Cancellation stops scheduling more files and allows in-flight per-file work to reach a safe checkpoint. A stage file is not proof that a transaction committed.

### 9.2 Exact JPEG media-preservation verification

**Stage 1 JPEG contract:** successful decoding is not evidence of unchanged compressed image data. Use a qualified, bounds-checked marker-aware parser/comparator. **Classify markers and nested resources by function, not by raw byte offsets or total APP-segment counts.** JPEG metadata writers can legitimately insert, split or reorder APPn segments. This must not cause false rejection, but neither can it excuse changes to compressed image data or protected auxiliary resources.

| Comparator class | Required invariant |
|---|---|
| **A. Codestream and decode-critical structures** | Preserve the logical sequence and bytes of SOI/EOI framing; each SOF/DQT/DHT/DAC/DRI/DNL and any other required decoding marker; each SOS header; **every** entropy-coded scan payload including stuffed `0xFF00` and in-scan RST markers. Scan count/order, parameters and payload must match exactly. Interleaved metadata marker positions do not enter the codestream hash. |
| **B. Non-target metadata and auxiliary structures** | Preserve APP0/JFIF, APP1 EXIF/MakerNotes and embedded previews, APP2 ICC (including multipart parts and ordering), APP14 Adobe, untouched COM data, vendor/unknown APP resources, and non-IPTC Photoshop APP13 image resource blocks. Require byte-identical content where possible, otherwise a separately justified, exact logical-equivalence policy under ENG-02. Do not automatically exempt an entire APP1 or APP13 just because its marker type may contain target metadata. |
| **C. Authorized target metadata** | Only specifically reviewed XMP content within APP1 (including extended/multi-segment XMP when qualified), and IPTC-IIM datasets within Photoshop APP13 may change. APP insertion/splitting/reordering is permitted **solely** as necessary for those changes. Verify changed tags through qualified structured read-back, verify preservation of unrelated fields within the same target resource, and protect unrelated Photoshop image resource blocks. |

**Implementation choice:** Prefer a maintained and tested existing JPEG marker/resource inspection library, or a narrowly scoped bounds-checked marker walk combined with independent ExifTool structure/validation diagnostics, where the chosen combination proves every Class A/B/C invariant above. **Pillow decoding or `ExifTool -validate` alone does not prove byte-identical compressed scans, protected-resource preservation, or exact permitted changes.** Do not build a general-purpose JPEG decoder or an unnecessarily broad Photoshop/ICC parser from scratch for Stage 0. If no proven existing component covers a required structure, either implement and test the minimum bounded parser needed for that structure or fail closed for those files. ENG-02 must record the exact library versions, supported structures, fixtures and known limits.

**Parser requirements:** identify metadata subtypes from segment signatures and nested resource structure. Multiple SOS scans/progressive JPEGs, byte stuffing, restart markers, length fields, Exif APP1, XMP APP1, extended XMP, multi-part ICC and mixed Photoshop APP13 IRBs are separate fixtures. The comparator must compare all scan payloads and the decoding-critical sequence independent of where unrelated APP markers appear. It must not simply hash bytes from the first SOS to EOI, require identical APP marker positions, or exempt all APP1/APP13 content wholesale.

**Fail closed:** unsupported arithmetic/lossless JPEG modes, unknown markers with potential decode implications, malformed lengths, ambiguous APP payloads, parser disagreements or an inability to prove protected-resource preservation block publication. An objective scan hash is a necessary part of evidence, not proof by itself that the rest of the image was preserved. The document does not claim the comparator is implemented or validated; **ENG-02** must supply tested code and fixtures before any JPEG write is enabled.

### 9.3 Future in-place recovery and storage controls

**Edit originals is disabled until all of the following pass:** verified backup of each original in a private persistent Qt/XDG application-data location (not disposable cache); owner-only access; a crash-recoverable per-file manifest/journal; adequate space preflight across source, stage and backup filesystems; preservation/restore tests; nonlocal/link/ACL/xattr/ownership policies; and explicit user approval in Review Changes.

Retain recovery copies by default until the user **manually deletes** them. Never automatically remove the sole verified recovery copy during session close, cache cleanup or when a soft threshold is crossed. Add a configurable **soft warning** starting at **5 GiB** of retained recovery storage (product default proposed for usability validation), plus warnings if the backup volume is low on space. Show actual retained size, estimated upcoming backup growth and a **Manage recovery backups…** action in Settings and the completion summary whenever originals were edited. Hard-block only when actual capacity/permissions or safety requirements cannot be met; do not silently purge.

**Restore is a new reviewed write:** show original and current target identity, created/modified timestamps, relevant diff and overwrite consequences. If another process changed the live file since the saved transaction, require explicit resolution, not blind overwrite. Preserve the current version at a recoverable point before replacement. No unverified “Undo successful” message. Backup cleanup has its own explicit confirmation and must not confuse temporary stages with recoverable originals.

### 9.4 Filesystem safety boundaries

Stage in target directory/on target filesystem where required to qualify atomic rename; follow tested `fsync` ordering for file, parent directory and journal; do not represent rename atomicity as universal power-loss durability. An atomic replacement can change inode identity, hardlinks and symlink behavior. Refuse unsafe in-place operations unless preserving permissions, ownership, ACLs, xattrs, timestamps and link semantics is validated. Qualified local-only initial policy is deliberately conservative. External edits between initial read and publication invalidate the reviewed plan even if mtime stayed unchanged.

## 10. Metadata conflicts and technical inspection

Read both IIM and XMP rather than choosing one silently. When equivalent fields disagree, show each original value and namespace in a compact conflict panel, and offer an explicit Resolve choice before a field is edited. Do not resolve unedited conflicts automatically. If one namespace contains an empty value and another a populated value, the logical field is not empty. Conflicts never qualify as Fill empty.

The advanced inspector may expose raw qualified tag names, original data types, language alternatives, multi-value arrays and provenance status, but is **read-only by default**. Technical EXIF inspection never implies editing camera capture parameters. A malformed, unparseable or unsupported field is marked Unreadable/Unsupported, not blank.

Field-level diff shows **which IIM, XMP and other representations will be written or removed**. The limited-compatibility XMP-only path, when available, must disclose the selective removal of a conflicting IIM counterpart, not bury it in a generic “description changed” line.

## 11. Templates, navigation, and completeness

**Templates** reuse existing KIM6 Settings for Creator, Copyright and Usage Terms where the user explicitly loads them, and use the same logical field definitions as editor/import/Recipes rights fields without automatically changing Recipes. A template prepares pending operations; no template bypasses Review Changes. Reuse a reference image through an explicit field checklist; do not copy technical camera EXIF blindly.

**Keyboard-first captioning:** next/previous image; use previous caption; apply template to current image or declared batch; visible unsaved marker and per-image pending buffer. Editing one field in Individual must never become a Batch Replace because a thumbnail was clicked. A user returning to an earlier image sees their unsaved caption exactly as entered. Close/mode change must not discard work silently.

**Metadata completeness** (later) analyzes selected images only and counts missing captions/rights/keywords, conflicts, GPS presence and unsupported format cases. Each category filters to affected selected files. GPS presence is an informational/privacy condition, not inherently an error. No arbitrary, opaque “quality score” or required catalog/database.

**Useful additional actions:** search/replace scoped to selected fields with preview; export inventory; local keyword history; filename-based variables with expansion visible in review. Each is a separate scoped implementation after foundational safety.

## 12. Privacy, accessibility, and malicious input

**Privacy:** No new cloud, telemetry, online accounts, subscription, or mandatory AI. Minimize logging of raw captions, GPS data, contact details, camera serials, identifiers and full local paths. Recovery backups contain sensitive originals and need owner-only permissions. Export previews enumerate exact columns and warn about sensitive content; GPS/contact/absolute paths are unchecked by default. Never leave extra unapproved image copies in temp/cache directories.

**Untrusted input:** Metadata, thumbnails, JPEG structures, filenames, paths, CSV contents and text descriptions can be malformed or adversarial. Bound image and metadata parser complexity, memory and thumbnail resources. Protect against directory traversal via imported paths and duplicate basenames. ExifTool invocation must use safe argument vectors or carefully framed persistent `-stay_open` requests; user strings must never become shell commands, command switches or untrusted file targets. Handle filenames starting with `-`, embedded newlines, Unicode, and literal shell metacharacters safely.

**Accessible authoring:** Title, Headline and Caption are separate from IPTC Alt Text (Accessibility) and Extended Description (Accessibility); an optional Copy caption action is explicit rather than automatic. Use native Qt accessibility roles, complete keyboard operation, readable status text (not color-only), locale-aware displays and stable focus. Keep accessibility-specific fields ready for later verified writes, without misleading users that initial JPEG six-field writing supports them.

## 13. Performance and implementation boundaries

Do not decode media, launch ExifTool for every field, or synchronously scan large selections on the Qt GUI thread. Use cancellable bounded workers, incremental statuses, lazy previews and virtualized file/review lists. A persistent ExifTool `-stay_open` process is a planned optimization for large batches once request framing, timeouts, cancellation, process restart, output isolation and error attribution are proven. A simple reliable per-file read path may be appropriate during initial JPEG qualification.

**Suggested layers:** (0) independent read-only metadata browser UI and narrow read-only service, (1) editor UI/state controller, (2) shared field registry and metadata read model, (3) validated operation planner, (4) import/export adapters, (5) write/verification engine, (6) publication and transaction/recovery engine, (7) format/capability inventory. Only editing and other metadata-modifying entry points use the **same** write planner and mandatory Review Changes; the standalone browser must not invoke or depend on the write planner. Keep interfaces modular to permit later video support without implementing it now. Avoid a large refactor to current `kim_all` merely to introduce metadata editing.

**Integration:** Standalone **View metadata…** and **Edit metadata…** actions under Organize Metadata. Creator/copyright/usage defaults from Settings, Review Changes convention, Output Filenames settings and Beside each source destination policy, Location/GPS tools, native KDE button roles and Dolphin action labels. The current `natacha` tree is the only implementation baseline; old zip archives and upstream `master` are not authoritative. No image pixels, color profiles, technical metadata or filesystem modification times are silently altered for convenience.

## 14. Requirements register

The following is a **tracking register**, not a claim of delivery. Specific details elsewhere in this document govern the acceptance of each item.

| ID | Requirement | Status | Priority |
|---|---|---|---|
| META-001 | Still-image-only scope; video deferred | Decided | P0 |
| META-002 | Entry under Organize Metadata as **Edit metadata…** | Accepted direction | P0 |
| META-003 | One KIM6 editor window for an entire Dolphin selection | Decided | P0 |
| META-004 | Progressive-disclosure, KDE-native, sentence-case interface | Decided | P0 |
| META-005 | Distinct Individual and Batch workflows | Accepted direction | P0 |
| META-006 | Resizable media list/preview and responsive editing pane | Accepted direction | P1 |
| META-007 | Five decided sections: Describe, Keywords, People & Places, Creator & Rights, More Metadata | Decided | P1 |
| META-008 | Central field schema with professional IPTC/XMP/EXIF mappings | Accepted direction | P0 |
| META-009 | Distinct Title, Headline, Caption/Description, Alt Text, Extended Description | Accepted direction | P1 |
| META-010 | Keyword add/remove/replace and planned hierarchical keyword support | Accepted direction | P1 |
| META-011 | Creator, copyright, rights, attribution and licensing fields | Decided | P0 |
| META-012 | People, place, dates and capture information within still-image scope | Accepted direction | P1 |
| META-013 | Preserve technical fields and unknown metadata by default | Decided | P0 |
| META-014 | Explicit leave/fill/replace/clear field operations | Accepted direction | P0 |
| META-015 | Explicit mixed/empty/conflicting/unsupported field states | Accepted direction | P0 |
| META-016 | CSV, TSV and plain-text metadata imports | Decided | P1 |
| META-017 | Column mapping, delimiter/encoding detection, import preview | Accepted direction | P1 |
| META-018 | Unambiguous file matching, duplicates detection, no guessing | Accepted direction | P0 |
| META-019 | Metadata CSV export and safe round-trip import | Accepted direction | P1 |
| META-020 | Shared-text and basename-matched companion `.txt` descriptions | Accepted direction | P1 |
| META-021 | Reusable metadata templates and KIM6 Settings inheritance | Accepted direction | P1 |
| META-022 | Metadata source/namespace conflict detection and explicit resolution | Accepted direction | P0 |
| META-023 | RAW/JPEG/XMP companion awareness | Accepted direction | P1 |
| META-024 | Consistent save policy: copies default for all selection sizes; explicit original and supported sidecar alternatives | Decided policy; implementation gated | P0 |
| META-025 | Standardized Review Changes before writing | Decided | P0 |
| META-026 | Staged writes, read-back verification, and truthful results | Accepted direction | P0 |
| META-027 | Recoverable in-place edits with persistent, managed original backups before modification | Decided policy; implementation gated | P0 |
| META-028 | Accurate partial-failure handling for a multi-file batch | Accepted direction | P0 |
| META-029 | Detect external source changes and refuse stale plans before commit | Decided | P0 |
| META-030 | Signed-media/C2PA awareness; no silent invalidation | Accepted direction | P0 |
| META-031 | Preserve filesystem modification time by default where supported | Accepted direction | P1 |
| META-032 | Capability-driven format support; no unsupported write promises | Decided | P0 |
| META-033 | Metadata completeness checks and actionable filters | Accepted direction | P2 |
| META-034 | Fast individual captioning/keyboard navigation | Accepted direction | P1 |
| META-035 | Metadata search and replace | Proposed | P2 |
| META-036 | Multilingual and structured metadata without silent flattening | Accepted direction | P1 |
| META-037 | Clear unsupported/read-only states with reasons | Accepted direction | P0 |
| META-038 | Asynchronous scanning/preview to keep the UI responsive | Accepted direction | P1 |
| META-039 | Per-file progress, cancellation, and recovery summaries | Accepted direction | P0 |
| META-040 | Advanced raw metadata inspection without exposing it by default | Accepted direction | P2 |
| META-041 | No duplicate GPS editor; integrate Location/GPS actions | Decided | P1 |
| META-042 | Explicit namespace-targeted, verified IPTC-IIM/XMP mapping and synchronization | Decided policy; verification gated | P0 |
| META-043 | Preserve image pixels and relevant structural content | Decided | P0 |
| META-044 | Format-specific metadata write and verification policy | Accepted direction | P0 |
| META-045 | Accessibility, keyboard and locale-aware operation | Accepted direction | P1 |
| META-046 | Review destination updates are reflected in actual publication | Decided | P0 |
| META-047 | User-visible warnings for metadata-derived privacy implications | Decided v1.0 design; engineering qualification pending | P1 |
| META-048 | Persistent transaction and recovery semantics defined before in-place writes | Decided policy; retention/UX open | P0 |
| META-049 | No unexpected catalog, cloud, or online dependencies | Accepted direction | P1 |
| META-050 | Metadata-specific acceptance tests and failure scenarios | Decided | P0 |
| META-051 | A save-mode choice must never change implicitly with selection count | Decided | P0 |
| META-052 | Persist recoverable originals for in-place edits; no disposable cache-only backups | Decided policy; implementation gated | P0 |
| META-053 | Revalidate source identity and freshness immediately before each commit | Decided | P0 |
| META-054 | Explicit canonical field-to-namespace write policy; do not rely on ExifTool unqualified-tag behavior | Decided policy; verification gated | P0 |
| META-055 | Per-file crash-recovery journal and filesystem-aware stage/commit process | Decided policy; implementation gated | P0 |
| META-056 | Plan a persistent ExifTool session for efficient large batches; robust process failure handling required | Accepted technical direction | P1 |
| META-057 | Preflight sufficient storage for staged data, backups, and retention overhead | Decided | P0 |
| META-058 | Preserve or safely refuse operations affecting permissions, ownership, ACLs, xattrs, links, and inode semantics | Decided safety constraint; qualification gated | P0 |
| META-059 | Never silently switch to sidecars or in-place writes after a selected mode fails | Decided | P0 |
| META-060 | Document exact verification evidence and remaining guarantees per supported image format | Decided | P0 |
| META-061 | Make IPTC-IIM/XMP equivalent-field synchronization conform to tested IPTC interoperability expectations when both representations apply; never write only one silently | **Decided, validation gated** | P0 |
| META-062 | Use typed, source-aware metadata values with per-language and multivalue preservation; distinguish unreadable from absent | Decided, validation gated | P0 |
| META-063 | Pin the planned source snapshot, target file identity, field operations, and output path to a review revision; invalidate it on relevant change | Decided, validation gated | P0 |
| META-064 | Define explicit all-blocked vs valid-subset policy at preflight; no automatic skips and no false batch-wide atomicity | Decided, validation gated | P0 |
| META-065 | Define deterministic naming, collision handling, companion behavior, and disk usage for Create copies | Decided, validation gated | P0 |
| META-066 | Make CSV round trips loss-aware: schema version, matching identity, edit-intent encoding, stale-value detection, and reversible protection against spreadsheet formula interpretation | Decided, validation gated | P0 |
| META-067 | Separate user-edited IPTC creation date from camera EXIF capture timestamps and support partial historical dates without inventing precision or timezone | Decided, validation gated | P1 |
| META-068 | Make storage capability a composition of format, file structure, metadata field, write strategy, filesystem, and provenance, not only extension | Decided, validation gated | P0 |
| META-069 | Treat import files, metadata values, filenames and previews as untrusted; constrain parsing, subprocess arguments, path traversal and resource usage | Decided, validation gated | P0 |
| META-070 | Minimize exposure of metadata, GPS, names, emails and original images in logs, export files, backups and transaction records | Decided, validation gated | P0 |
| META-071 | Define keyboard-first, low-friction individual captioning with explicit uncommitted changes and no implicit background writes | Decided, validation gated | P1 |
| META-072 | Publish a compact field support matrix with read/write/sidecar/copy behavior and exact reasons for unsupported fields | Decided, validation gated | P1 |
| META-073 | Define verification tiers and evidence for image payload preservation, auxiliary assets, logical field equivalence and post-commit inspection | Decided, validation gated | P0 |
| META-074 | Treat restoration as a separate reviewed write, guarding against changes made to the target after the original operation | Decided, validation gated | P0 |
| META-075 | Define default and advanced rules for multi-value keywords, language alternatives, whitespace, Unicode normalization and term ordering | Decided, validation gated | P1 |
| META-076 | Give every blocked/error result one concrete remediation path; prefer consolidated reports over modal dialog cascades | Decided, validation gated | P1 |
| META-077 | Use a bounded, resumable scan/planning workflow for large selections; no preview decoder or metadata reader on the UI thread | Decided, validation gated | P1 |
| META-078 | Specify handling of nonlocal Dolphin/KIO URLs, unstable remote filesystems, links, and sources outside selected directories | Decided, validation gated | P0 |
| META-079 | Distinguish embedded metadata consistency from companion-sidecar synchronization; never conflate them in one checkbox | Decided, validation gated | P0 |
| META-080 | Define whether a file is truly unchanged (no-op), field validation is blocked, or actual write failed, in both review and report | Decided, validation gated | P0 |
| META-081 | Use exact user-visible wording for save-mode consequences, blocked formats, conflicts, and irreversible actions; validate with novices and DAM users | Decided, validation gated | P1 |
| META-082 | Add a small golden-fixture interoperability matrix for Lightroom/Photo Mechanic/digiKam round trips and IPTC tests, with documented limitations | Decided, validation gated | P1 |
| META-083 | Preserve original unknown data and linked sidecar identities when creating derivative copies, or block unsupported pairing | Decided, validation gated | P0 |
| META-084 | Limit first-release interactive editability to a small proven field set; inspect more fields read-only without implying future edits are already supported | Decided, validation gated | P0 |

| META-085 | Group blockers by reason in Review Changes; exclude individual categories or explicitly all blocked files with named-file acknowledgment, unique counts and fresh plan confirmation | Decided v1.0 design; engineering qualification pending | P0 |
| META-086 | Show live IIM byte counters and provide one qualified advanced **Modern XMP only** storage profile selectable upfront or via overflow resolution; review selective conflicting-IIM removals | Decided v1.0 design; engineering qualification pending | P0 |
| META-087 | Continue editing verified outputs with explicit version-or-recoverable-update choice; default to copies, normalize suffix only via proven transaction provenance | Decided v1.0 design; engineering qualification pending | P1 |
| META-088 | Warn when persistent recovery storage exceeds a configurable soft threshold without deleting recoverable originals | Decided v1.0 design; engineering qualification pending | P1 |
| META-089 | Verify JPEG using three-class marker/resource policy: decode-critical scan stream exact; unrelated auxiliary metadata preserved; only reviewed XMP/IPTC subresources may change | Decided v1.0 design; engineering qualification pending | P0 |
| META-090 | Distinguish machine-exact CSV from spreadsheet-friendly, tested formula-safe CSV; do not promise arbitrary spreadsheet reversibility | Decided v1.0 design; engineering qualification pending | P1 |
| META-091 | Provide one normative rule per topic, with superseded audits and closed decisions recorded only in historical appendix | Decided v1.0 design; engineering qualification pending | P0 |
| META-092 | Map six first-wave fields and byte limits; explicitly validate list-item writes, x-default language targeting and IIM charset conversion before enabling writer | Decided v1.0 design; engineering qualification pending | P0 |

**P0:** correctness/safety or foundational functionality. **P1:** essential to a strong working experience. **P2:** valuable follow-on. Priority does not imply implementation order or that an open decision has been resolved.

---


### Standalone browser requirements (new VIEW register, editor META numbering unchanged)

The VIEW identifiers define a separate read-only tool. **Agreed** denotes the user's requested independent viewer and non-writing boundary; **Proposed detail** identifies UI and export defaults that may be adjusted during the UX pass. These rows do not silently amend the original 92 editor requirements.

| ID | Requirement | Status | Priority |
|---|---|---|---|
| VIEW-001 | Separate **View metadata…** action under Organize Metadata; standalone window, not embedded in editor | Agreed direction | P0 |
| VIEW-002 | No code path in the browser may modify selected images, sidecars, timestamps or pending editor state | Agreed principle; qualification pending | P0 |
| VIEW-003 | Read-qualified still-image metadata can be inspected even when that format is not writable in the editor | Agreed direction; capability-gated | P0 |
| VIEW-004 | One resizable viewer for entire Dolphin selection, explicit per-file scan/unsupported/error states | Proposed detail | P0 |
| VIEW-005 | Overview shows Description, Creator & Rights, Camera & capture first; core six slots always visible, other absent fields hidden until Show empty fields; sources and unreadable/conflict states explicit | Proposed v1.2 refinement | P0 |
| VIEW-006 | All tags with search, namespace/source, raw names, duplicates where exposed, safe binary handling | Proposed detail | P0 |
| VIEW-007 | Clear file preview and keyboard navigation; metadata scanning does not block Qt GUI | Proposed detail | P1 |
| VIEW-008 | Compare differences across selected images, without implied edits or source precedence | Proposed later increment | P1 |
| VIEW-009 | Copy value/rows; explicit report export with Description, Camera & capture and Creator & Rights checked, but GPS/serial/full paths/contact identifiers off by default | Proposed v1.2 refinement; export qualification pending | P1 |
| VIEW-010 | Preserve date precision, language alternatives, multi-value types and sidecar provenance | Proposed detail; read qualification pending | P0 |
| VIEW-011 | No automatic recursion, background indexing, catalog, network fetch or video metadata scanning | Proposed default consistent with scope | P0 |
| VIEW-012 | Treat binary and textual metadata as untrusted; bound parsing, thumbnails, display and cancellation | Proposed safety requirement | P0 |
| VIEW-013 | Separate reader capability gates; structured ExifTool JSON candidate tested for duplicate-group identity, arrays/languages, bounded output and safe binaries | Proposed v1.2 refinement | P0 |
| VIEW-014 | No automatic or state-carrying handoff; optional explicit Open in editor… launches a separate editor for current selected image rows, zero pending edits and standard Review Changes | Proposed v1.2 refinement | P0 |

## 15. Acceptance scenarios

These are **acceptance scenarios to design for**, not instructions to add unrelated regression suites immediately. Work through each during UX specification and test the implemented portion of the feature when ready.

### WF-01: One JPEG, one caption

**Given** one compatible JPEG with existing camera EXIF, **when** the user adds a caption and reviews the change, **then** the caption is readable on reopening and unrelated technical/rights data remains intact. Pixel content is not modified by the metadata-only action.

### WF-02: One JPEG, existing caption

An existing caption is shown accurately. The editor does not interpret a blank input or a navigation action as a deletion. **Clear** requires an explicit operation and appears in Review Changes.

### WF-03: 100-image batch with mixed descriptions

Seventy-two have descriptions, 28 do not. **Fill empty** targets only 28; **Replace** clearly warns of 72 overwritten values. The result report matches what was actually written and verified.

### WF-04: Batch keywords

Adding `wildlife` does not erase existing keywords. Removing `birds` does not remove `wetlands`. Replacing the list shows full old/new values for affected files in review.

### WF-05: Nested directories and duplicate filenames

CSV references `IMG_0001.JPG`; two selected directories contain that basename. KIM6 reports an ambiguous match and blocks automatic assignment until the identity is resolved.

### WF-06: Plain text descriptions

One `.txt` file can fill selected images' missing captions; individual companion `.txt` files can map to images by unambiguous basename. Neither route bypasses Review Changes.

### WF-07: CSV round-trip

Export selected metadata, change some captions in LibreOffice, import, review only intended changes, and preserve untouched fields. Missing/duplicate/stale rows are explained.

### WF-08: RAW/JPEG/XMP relationship

The editor detects companions. An edit to the selected JPEG does not silently update the RAW or XMP sidecar. Optional synchronization requires explicit scope and compatible format support.

### WF-09: IPTC/XMP conflict

Different values from two metadata sources are displayed with attribution. Nothing is silently normalized merely by opening or saving another unrelated field.

### WF-10: Signed media

Image has Content Credentials. An edit that would invalidate them is blocked or handled by an explicitly supported safe path; the user never receives a false preservation claim.

### WF-11: Unsupported or read-only image

The image may be inspected where reading is supported. Incompatible writes are visibly disabled or excluded with a reason, without falsely reporting success.

### WF-12: Failure while writing

The operation fails or is interrupted. Source and recovery state follow the defined policy. Completed files are individually identified. The UI does not claim the batch completed successfully.

### WF-13: Source changes while editor is open

If another process changes a source after initial scan, KIM6 detects the stale plan and requires revalidation or abort instead of overwriting unreviewed changes.

### WF-14: Metadata template inheritance

User applies creator/copyright defaults from KIM6 Settings. Existing values are not replaced unless the selected operations permit it. All changes appear in Review Changes.

### WF-15: Large batch and UI responsiveness

Selecting hundreds or thousands of images does not freeze interaction indefinitely or create one dialog per file. Scan/progress/cancellation states remain legible.

### WF-16: Files from different source directories

With **Create copies**, Beside each source generates output beside each original in its own directory. **Change Destination…** updates preview and actual output targets identically.

### WF-17: Language alternatives and structured values

Opening or editing one descriptive field does not silently flatten/remove unrelated localized alternatives or structured metadata entries.

### WF-18: No-op and cancellation

Opening, viewing, navigating and cancelling make no changes to source media. A no-op change set is clearly identified, with Apply disabled or appropriately handled.

### WF-19: Accessibility descriptions

Caption, Alt text and Extended description can have different values; copying from one to another is optional and explicitly visible.

### WF-20: Metadata completeness filtering

Users can identify images missing descriptions or containing metadata conflicts and filter to those images without involving a media catalog or online service.

### WF-21: Identical default for one file and many

Given one JPEG, and then 100 JPEGs, the initial save mode in both cases is **Create copies**, with **Beside each source** as the default copy destination. Changing selection size or switching Individual/Batch does not silently alter the save mode or write to originals.

### WF-22: In-place backup survives session closure

Given an explicitly chosen, supported Edit originals operation, a verified persistent original backup and recoverable transaction record exist **before** any original is modified. Closing the dialog, normal application exit, or an OS cache cleanup does not silently erase the only backup.

### WF-23: Stale or linked source blocks unsafe in-place edit

Given a source that changes after review, or a linked/source filesystem configuration that cannot be handled without changing semantics, KIM6 refuses the stale or unsafe commit and explains the alternatives. It does not replace a newer source or silently break hardlink/symlink expectations.

### WF-24: Namespace synchronization is explicit

Given a JPEG with different IPTC-IIM and XMP captions, editing an unrelated field preserves those different captions. Editing the caption itself shows all intended namespace writes. After commit, each intended representation passes read-back validation.

### WF-25: Crash or storage failure during batch

Given multiple files and an interruption after some commits, KIM6 can distinguish verified committed files, untouched files, and recovery-needed files using persistent records. No global all-or-nothing claim or false success is shown. In-place originals have verified recovery material under the adopted policy.

### WF-26: Backup capacity preflight

Given insufficient room for the required verified backup and stage, KIM6 refuses **Edit originals** before touching originals, with an actionable space/capability explanation. It never silently switches to an unbacked write.

### WF-27: Mode change invalidates prior review

Given a planned copy edit, the user changes to Edit originals or Write XMP sidecars. KIM6 recomputes eligibility, paths, conflicts and recovery requirements, then requires a new Review Changes confirmation. The old copy plan cannot be applied under a different mode.

---

### WF-28: IPTC-IIM and XMP agreement on a supported field

Given a JPEG with an existing XMP caption and legacy IPTC-IIM caption, an explicitly reviewed caption edit produces the chosen value in each required representation under the selected compatibility policy; an unrelated IPTC property is unchanged. The IPTC interoperability test flags no unintended changes. If the value cannot fit the validated legacy byte limit, the **Compatible XMP + IPTC** write is blocked pending resolution. No implicit truncation or silent XMP-only fallback is permitted; switching to **Modern XMP only** requires an explicit user choice, successful ENG-04 qualification for the affected files, and a fresh Review Changes confirmation.

### WF-29: Caption belongs to one image, not the batch

Given Individual mode with 100 selected images and pending captions on three different files, switching the preview and returning preserves each pending caption separately. Switching into Batch mode does not merge or broadcast those values. Cancelling does not write media.

### WF-30: CSV with numeric-looking filenames and spreadsheet formulas

A collection includes `00001234.jpg`, a title beginning with `=`, and a multiline UTF-8 caption. Exporting, editing in a supported spreadsheet workflow and reimporting does not silently change filename identity, execute spreadsheet formulas, damage the caption or interpret an escaped value as a Clear instruction.

### WF-31: An old CSV is reimported after media changed

After CSV export, a different application changes the image caption. The importer detects the stale baseline and requires explicit conflict review; it does not blindly replace the newer value.

### WF-32: IPTC date with partial precision

An archival image has a date known only to the year `1918`. Display and import retain the precision **year only**; they do not invent January 1, midnight or a timezone. Editing IPTC Date Created does not silently change EXIF DateTimeOriginal or the filesystem mtime.

### WF-33: Interrupted partial batch

Given 100 planned writes, 31 files have completed safely when the process crashes. On recovery, KIM6 distinguishes the 31 committed/verified results from staged, unattempted and ambiguous targets. It does not claim global rollback, and it must not reapply an already committed write without checking.

### WF-34: Restore after external change

An original-edit backup exists, but an external application has subsequently modified the live target. Restoration refuses a blind overwrite and offers a reviewed resolution path. The original backup remains available until its authorized retention/cleanup policy applies.

### WF-35: Nonlocal and linked files

A selection contains `smb://` files, a symlink, a hardlinked image and a regular local JPEG. Unsafe in-place operations are explained and blocked without altering links or silently switching save modes. The regular JPEG may be processed only under the explicitly chosen subset policy.

### WF-36: Unsupported provenance state

A media file contains signed credentials or provenance data that cannot be reliably evaluated by the available detector. KIM6 does not claim safety from lack of detection; the applicable conservative policy is shown before any affected write.

### WF-37: Large collection with useful partial results

For thousands of images, scanning and thumbnail generation remain responsive. The user sees file counts, progress and meaningful statuses before every image has been decoded. Cancellation does not leave an accepted Review Changes plan referencing unfinished scans.

### WF-38: Two imports target the same field

A CSV has duplicate rows or columns that both map to Caption / Description. KIM6 identifies the ambiguity, does not choose the last silently, and requires an explicit resolution before planning a write.

### WF-39: Plain text and Unicode edge cases

An imported text description contains quotation marks, commas, non-ASCII names, newlines and leading/trailing spaces. The preview shows the exact parsed content, any optional normalization is disclosed, and the resulting metadata round-trips without corruption.

### WF-40: Copy naming and destination collision

Two different source directories contain `IMG_0001.jpg` and the user selects one shared destination. Review displays two distinct planned outputs. Repeating the action never silently overwrites an old copy, and changing the destination invalidates the previous review.

### WF-41: Destination and source privacy

A selection contains GPS positions, creator contact details and private archival descriptions. By default, logs and transaction manifests do not contain unnecessary raw metadata values, CSV export discloses the selected columns, and persistent backups use restricted permissions.

### WF-42: Save strategy and sidecar relationships

A selected JPEG is related to an XMP sidecar and a RAW image. **Create copies** changes only the explicitly selected output(s) and warns if the sidecar relationship would become ambiguous. Switching to sidecar mode never silently edits a different sibling image.

### WF-43: No-op versus failure

The user replaces a caption with the same value. KIM6 reports no metadata change required, without writing or creating a misleading derivative. A genuinely failed write and an intentionally excluded file appear as different result categories.

---

### WF-44: Paired-tag write blocked without silent truncation

A JPEG caption exceeds the verified IPTC-IIM encoded byte limit, even though XMP can represent it. The initial writer blocks the operation with the exact incompatible representation and an actionable explanation. Neither XMP nor IIM is partially published. A previous legacy caption is not silently retained beside a newer XMP caption.

### WF-45: Paired-tag write preserves other languages and creators

A JPEG has two `dc:description` language alternatives and two `dc:creator` entries. Editing a supported default-language caption preserves the other language entry. A single-creator edit that cannot represent the list without loss is blocked rather than flattening the second creator. Both applicable IPTC and XMP representations are verified.

### WF-46: Blocked batch with explicit exclusion

A 100-image batch contains two read-only or unsupported targets. Apply is disabled while those targets are included. The user chooses **Exclude 2 blocked files** inside Review Changes, inspects/acknowledges their exact filenames, sees the updated **98 eligible, 2 excluded** plan revision and confirms it in place before applying. Results list the two as **Excluded**, not failed or successful.

### WF-47: Deterministic copy naming, suffix and no-op

A source `IMG_1001.JPG` already has `IMG_1001-metadata.JPG` beside it. With no configured action-specific affix, the planned result is `IMG_1001-metadata-2.JPG`. The extension case is preserved; no existing file is overwritten. If the requested metadata already matches the source, no new copy is generated. Changing the destination or encountering a new collision requires another review.

### WF-48: Review plan changed after confirmation

An image's content changes between completing review and committing, even when the filesystem mtime is retained. A sufficiently strong source fingerprint detects the change and prevents publication under the old plan. Edited fields, target paths and save mode remain unchanged until the user reviews the new plan.

### WF-49: KIM6 CSV v1 blank, Clear and stale baseline

A round-trip export is edited in LibreOffice, preserving exact strings including a leading `=`, `00001234.jpg`, and a Unicode multiline caption. A blank imported cell means **Leave unchanged**. Machine-exact CSV preserves literal values; a supported spreadsheet-friendly profile must reconstruct protected literals from verified export metadata or flag ambiguity rather than silently strip escape characters. An explicit **Clear** operation only affects the named field and selected files. A stale baseline blocks unattended import and identifies the conflicting row/field. This test's supported spreadsheet version is recorded.

### WF-50: Manual-retention backup and reviewed restore

After a supported in-place edit, the editor closes, the system reboots, and an administrator clears ordinary temporary caches. The recovery record and verified original backup still exist in KIM6's private persistent data directory. The user can locate the transaction. Restoring over a subsequently changed target requires a fresh review and a recoverable protection point; manual cleanup is a separate explicit operation.

### WF-51: Privacy, remote source and malicious input

A selected `smb://` URL and a local symlink are presented for inspection but not silently written through a local cache path. A CSV row containing `../other.jpg` cannot escape the selected target set. Metadata containing shell metacharacters, newlines or tag-like arguments cannot be executed as a subprocess command. GPS and contact fields are not included by default in a CSV export, and logs do not contain raw sensitive metadata.

### WF-52: Final verification with honest tiered results

An edited JPEG is re-read to verify each intended qualified XMP/IPTC tag and unrelated supported tags. The compressed image content, ICC profile, orientation and embedded preview structures meet the stated preservation contract; the file exists at the exact reviewed output path after commit. If any applicable verification fails, the candidate is not reported as successful. A mid-commit interruption produces explicit committed, untouched and recovery-needed states, not a blanket success message.

---



### WF-53: Grouped Review blockers and no accidental skip
A selection contains 198 JPEGs, a GIF and a read-only image. Review shows all 200, grouped as **1 unsupported format** and **1 permission-denied**, with each filename. Apply starts disabled. User can choose to exclude just the GIF, just the permission-denied file, or both explicitly; exclusions update unique file counts without hiding the reasons. A field-level IIM overflow first offers text correction or a qualified profile change rather than presenting exclusion as the only remedy. A new revision is confirmed inside Review Changes. An additional blocker occurring after confirmation is never excluded automatically.

### WF-54: Batch storage profile and legacy overflow
A 200-JPEG batch includes 40 Titles longer than the 64-byte IIM limit. By default **Compatible XMP + IPTC** shows count/limit warnings and blocks affected writes, without 40 separate modal dialogs. User selects **Modern XMP only** once under More Metadata (or from the first overflow resolution). The plan recomputes all changed fields/files, explicitly shows legacy IIM values requiring selective removal and warns about reduced interoperability. Matching legacy values and unrelated IIM fields are preserved. The user confirms the new plan and each published output passes read-back; unqualified files remain blocked. No XMP-only fallback occurs automatically. Where the last applicable IIM dataset is removed, the staged APP13/`8BIM 0x0404` representation is inspected for valid empty-resource handling and third-party reader interoperability under ENG-04.

### WF-55: Multiple creators and keyword per-entry constraints
A JPEG has two creators, including a non-ASCII name longer than 32 encoded bytes, and three multiword keywords. Editing a different logical field leaves the ordered creator sequence and all keywords unchanged. An unsupported creator rewrite is blocked rather than flattening the list. The 64-byte IIM keyword constraint applies to **each keyword**, not to the total concatenated list.

### WF-56: Continue editing outputs without suffix multiplication
An initial pass creates 10 verified `-metadata` copies. Continue selects exactly those 10, clears completed pending edits and presents an explicit next-write choice. **Create another version** (default) uses recorded KIM6 output provenance so `IMG_0001-metadata.jpg` yields `IMG_0001-metadata-2.jpg` when available, not `IMG_0001-metadata-metadata.jpg`; it never silently rereads or writes the first-pass originals. **Update these created copies** appears only after in-place/recovery qualification and requires its own explicit selection, persistent backup and Review Changes. A user-selected source named `family-metadata.jpg` with no KIM6 transaction provenance is not arbitrarily stripped of `-metadata`.

### WF-57: Recovery soft threshold and manual cleanup
Persistent original-edit recovery uses 5.5 GiB and the user threshold is 5 GiB. KIM6 warns and links to **Manage recovery backups…** without deleting any backup. Insufficient actual free space blocks a new in-place operation before modifying media. A manually deleted recovery transaction is removed only after explicit confirmation and verified eligibility.

### WF-58: Progressive JPEG and three-class preservation comparator
A progressive JPEG contains multiple SOS segments. The writer inserts APP1 XMP and may split extended XMP or rearrange APP marker positions. The comparator accepts valid movement of **authorized target resources** while verifying all codestream/decode-critical markers and scan payloads match exactly, all protected APP0/APP1 EXIF/APP2 ICC/APP14/COM/vendor and unrelated APP13 Photoshop resources remain unchanged (or explicitly qualified equivalent), and only reviewed XMP/IPTC subresources change. Unknown critical structures block publishing. Comparing raw APP marker counts/positions or hashing first SOS to EOI is invalid.

### WF-59: Formula-leading literal in two CSV profiles
A title is literally `=35mm lens`, another filename begins with zeros, and a caption contains embedded newlines. A machine-exact export preserves their literal values byte-for-byte when imported as data. A spreadsheet-friendly export uses a documented tested protection scheme, and KIM6 can undo it **only** when trustworthy markers/baseline survive. If external software strips or changes escaping so intent is ambiguous, import requires manual field-level resolution; it never silently alters text or executes a formula as metadata.

### WF-60: Spec cross-reference cannot override canonical policy
A developer searching for META-085, OPEN-31 or prior §28.6 finds one current normative blocker/exclusion rule in §5. Historical notes in the appendix are labeled non-normative. No earlier open question contradicts the current interface or writer semantics.


### Standalone browser acceptance scenarios (VB, separate from editor WF cases)

**VB-01: Read-only window from Dolphin.** Selecting a JPEG and choosing View metadata… opens exactly one Metadata browser. Browsing and closing create no media or sidecar writes, no output image and no Review Changes. The image can be edited only in the independent Edit metadata… workflow, launched from Dolphin or, when implemented, explicitly from the browser.

**VB-02: Multi-file read status.** Select 20 still images, including one malformed image and one file not readable by the installed backend. The viewer shows 20 selected, explicit Ready/Partial/Unsupported/Failed per-file results, and remains navigable; no file is silently dropped or called empty.

**VB-03: Format reading is distinct from writing.** A RAW image has readable camera/EXIF metadata but no qualified write support. The browser displays supported information with correct source, while the editor independently blocks unsupported writes; no edit affordance appears in the browser.

**VB-04: Duplicate metadata sources.** An embedded XMP caption, a legacy IIM caption and a companion XMP file disagree. All read sources are identified and available for inspection; the viewer never silently chooses or synchronizes a winner.

**VB-05: Search, default Overview and large values.** Searching `Lens` returns matching tags, including raw qualified names. Overview shows Description, Creator & Rights and Camera & capture prominently; the six core slots remain visible when absent, whereas other missing fields appear only after checking Show empty fields. An unreadable/conflicting field never vanishes due to that toggle. A very long Unicode caption and binary preview use bounded display, can be expanded when safe, and never freeze the UI or corrupt the source. Structured extraction fixtures include repeated named tags, lists, language alternatives and multiline text, with no silent collision loss.

**VB-06: Sensitive-data report.** A still image contains GPS, a camera serial number, a full local path and copyright contact email. Export report defaults to checked Description, Camera & capture, and Creator & Rights groups but **each sensitive field remains unchecked**; it previews exact fields and destination, warns about personal/location details, and requires explicit opt-in for GPS/serial/full paths/contact identifiers. No network map tiles are fetched merely by opening the viewer. Redactions apply to data cells and headers/path fields, not only the visible table.

**VB-07: Selection comparison.** Two JPEGs have identical camera names, different captions and one missing copyright field. Compare distinguishes Same/Different/Missing, with full source labels and no accidental batch edits. A third unreadable image is labeled Unreadable, not Missing.

**VB-08: Linked file and sidecar safety.** Selected JPEG, RAW and `.xmp` companions have overlapping basenames. A confirmed relationship can be shown without assuming matching names prove identical assets. No relative-path lookup escapes the authorized selection or causes implicit media changes.

**VB-09: Malformed values, security and cancellation.** A deliberately malformed maker note and metadata value containing HTML, an embedded URL and shell-like text render as inert text, not executable markup. A large selection can be canceled while processing, leaving every source unchanged and clearly labeled by scan state.

**VB-10: Explicit independent viewer-to-editor launch.** From a viewer containing 20 files, a user explicitly selects two still-image rows and clicks Open 2 selected images in editor…. Exactly those two paths open in a separate editor window with **zero pending edits**, ordinary Create copies default and all standard validation/Review Changes rules. The viewer remains open; it never triggers Apply or transfers hidden operations. If the editor is not installed or cannot accept the selected files, the launch is unavailable with a clear reason. Closing either window does not mutate the other's state or source files.

## 16. Negative and edge-case register

For each of these, the eventual test plan should record: **input condition, expected UI state, permitted action, source preservation guarantee, verification result, and recovery path.**

| Case | Risk | Required disposition |
|---|---|---|
| Duplicate basenames across directories | Wrong caption on wrong file | Ambiguous-match blocker |
| CSV has duplicated rows for one image | Multiple unintended edits | Conflict/duplicate report and explicit resolution |
| Source CSV contains multiline quoted captions | Broken parsing | Standards-compliant parser and preview |
| CSV contains formula-like cell text | Spreadsheet code execution when exported | Defensive CSV export handling |
| Imported row lacks a value | Mistaken deletion | Empty versus absent versus explicit Clear semantics |
| Unicode/encoding ambiguity | Corrupted descriptions/names | Detect/override encoding; lossless round-trip where feasible |
| Long captions and huge keyword lists | Clipped or slow UI | Scrolling, wrapping, responsive editing |
| Image read-only/permission denied | Failed or partial writes | Preflight and per-file explanation |
| Full disk / no temp space | Broken publication or recovery | Space checks and safe abort |
| Crash or power loss | Incomplete transaction | Persistent journal, verified backup for original edits, recovery inspection |
| Single-to-batch transition changes save default | Unexpected modification of originals | Create copies remains default regardless of selection count |
| Backup stored only in OS cache | Original permanently lost after cleanup | Refuse in-place editing without persistent managed recovery copy |
| Backup cleanup on session close | Recovery window unexpectedly disappears | Never erase sole recovery copy on ordinary session exit |
| Backup location has insufficient capacity | Mid-batch unrecoverable commit | Conservative preflight and block original edits |
| Unqualified ExifTool tag updates preferred group only | Divergent IPTC-IIM/XMP values | Explicit field-to-namespace mappings and independent read-back verification |
| Rename replaces inode with another file | Hardlink semantics unexpectedly change | Detect linked files and preserve-or-refuse with approved policy |
| Symlink points to outside selection | Wrong file modified or symlink replaced | Inspect identity and refuse ambiguous in-place operation |
| ACLs, ownership or extended attributes are lost | Permission/access regression | Verify preservation or block original editing |
| Same-directory rename without directory durability | File missing or stale after abrupt power loss | Durable stage/journal protocol where supported; disclose limitations |
| Remote or unusual filesystem | Atomicity/durability assumptions false | Capability-driven refusal or clearly bounded safe mode |
| Changing save mode after review | Plan no longer describes actual targets | Invalidate and regenerate Review Changes |
| Source edited externally during session | Lost updates | Revalidate source identity/state |
| Path moved/renamed during commit | Wrong target or failure | Recheck and abort safely |
| Source and output path collision | Accidental overwrite | Collision-safe naming and explicit policy |
| Two files normalize to same output filename | Hidden collision | Resolve during review, not after commit |
| Companion XMP present but conflicting | Ambiguous authoritative value | Surface conflict, do not guess |
| Multiple RAW/JPEG files share base | Incorrect relationship | Mark uncertain/ambiguous |
| Unsupported metadata field for one format | Silent skip | Capability warning/block |
| Unsupported write format but readable file | False assumption of editability | Read-only state and explanation |
| Animated PNG/GIF/WebP mistaken for still | Broken animation | Detect actual structure; respect KIM6 fail-closed rules |
| Truncated, malformed or hostile metadata | Crash or unsafe parser behavior | Safe parsing, limits, informative failure |
| Unknown/private camera tags | MakerNotes loss | Preserve or refuse unsafe write |
| ICC profile or orientation inadvertently changed | Appearance corruption | Format-specific preservation verification |
| Capture timestamp lacks timezone | Wrong time interpretation | Preserve ambiguity; avoid invented offset |
| Image contains GPS in multiple metadata sources | Inconsistent privacy state | Detect/report; defer GPS editing to established tool |
| C2PA manifest present | Signature invalidation | Detect and block unsupported mutation |
| Batch includes files in multiple directories | Wrong output paths | Per-file destination plan |
| Mixed language alternatives | Data loss on flattening | Structured read/write model |
| Repeated creators/licensors | Flattened field or dropped values | Preserve arrays and structs |
| Filesystem with weak atomic rename guarantees | Unsafe commit claim | Document limits and safe fallback/refusal |
| Filesystem timestamp update | Unexpected mtime change | Preserve by default where supported |
| UI closes with pending changes | Lost work | Confirm discard; no implicit save |
| Cancellation during commit | Unclear state | Per-file state/journal and final summary |
| Background source scanning | Frozen UI | Incremental progress and cancel |
| Multiple selected files opening multiple windows | Workflow failure | Enforce one editor instance per invocation |
| File extension lies about actual format | Wrong writer | Detect format from content/capability |
| Unrecognized metadata namespaces | Unintended metadata deletion | Preserve or refuse broad rewrite |
| Browser shows missing when tag was unreadable | False metadata conclusions | Separate unreadable/partial from absent; show diagnostic |
| Read-only viewer accidentally calls writer helper | Hidden source modification | Narrow read-only service with no mutation API; negative fixtures |
| Metadata viewer auto-fetches map/linked image URL | Unwanted network/privacy leak | No fetch on open; explicit user action only for later external links |
| Viewer exports all tags without showing GPS/serial columns | Sensitive-data disclosure | Preview scope and sensitive fields, conservative default |
| Large binary tag or malformed MakerNote | UI freeze, crash or arbitrary text execution | Bounded parsing and inert text rendering |
| Selected video accidentally processed in still-image viewer | Scope creep/unverified parser | Explicit unsupported video row and no video scanning |

| Imported CSV targets a file outside authorized root | Directory traversal / wrong target | Require selected-file membership and canonical path validation |
| CSV file contains formula-like text or numeric-looking identifiers | Injection, corrupted identity on spreadsheet round trip | Reversible export safety, stable identity, parse preview |
| Source metadata reader reports malformed versus absent | Incorrect Fill empty overwrite | Distinct unreadable/error state; no write until resolved |
| IPTC IIM value exceeds encoded byte limit | Silent truncation or half-synchronized values | Validate encoded bytes and block/explicitly choose compatible write profile |
| Same image is selected twice through links | Duplicate writes and false counts | Deduplicate by verified identity and explain link behavior |
| Multiple rows/columns map to same logical field | Last-writer-wins without review | Surface conflict before planning writes |
| Restoring backup over externally changed image | Overwrite newer work | Treat restore as independently reviewed transaction |
| Exported CSV inadvertently includes location/contact information | Privacy leak | Column-aware explicit export preview and safe permissions |
| Metadata differs only in language alternative | Partial overwrite or false conflict | Language-aware read, display, write and conflict logic |
| Image has embedded sidecar-like XMP plus external XMP | Incorrect precedence / orphaned copy | Distinguish sources and identify companion relation explicitly |
| Missing or unavailable provenance detector | False reassurance | Never claim signed-media safety from absence of a positive match |
| Nonlocal KIO URL passed as local path | Wrong processing or unsafe assumptions | Refuse unsupported remote targets with clear explanation |

---

## 17. Delivery stages and implementation gates

These stages describe scope, not authority to change code. Each feature is implemented individually on the current `natacha` tree and accepted on `homebase` before moving to the next.

| Stage | Scope | Exit criteria |
|---|---|---|
| **0: Qualification (separable reader and writer tracks)** | Read-only viewer integration and structured extraction (VENG-01/02) may be qualified independently of writer-specific ExifTool/IPTC tag writes, charset, JPEG comparator, filesystem and review checks (ENG-01..). No writer fixtures are prerequisite to a viewer-only increment. | Independent, recorded evidence for each feature's own supported claims; current `natacha` integration inspected |
| **V: Independent read-only browser (may ship before Stage 1)** | One Dolphin invocation for selected still images; Overview, All tags, search, per-file diagnostics and Copy value; independent VENG-01/02 qualification. Compare and report follow in later viewer increments. Optional explicit editor-launch control activates only when a separately qualified editor exists. | VB-01/02/03/04/05/09, VENG-01/02; no source writing or pending editor-state mutation; no dependency on ENG-01/02 or JPEG publisher |
| **1: First safe JPEG copy** | One selected JPEG, six target fields where qualified, Create copies, exact planned filename, mandatory review, verified staged output | WF-01/02/18/24/28/43/44/47/48/52/54/58 pass for applicable supported structures |
| **2: Robust Individual and Batch** | Multi-file scope, mixed field operations, inline blocked exclusions, navigation/pending buffers, templating, partial outcomes, continue-editing outputs | WF-03/04/11/15/16/25/29/33/37/46/53/56 plus failure injection |
| **3: Import/export and completeness** | CSV/TSV/text wizard, two export profiles, conflict/stale matching, metadata templates and completeness filters | WF-05/06/07/30/31/38/39/49/51/59 with named tested spreadsheet versions |
| **4: Expanded still-image/pro workflows** | Safe sidecars, additional still formats, advanced IPTC/rights, accessibility, RAW pairing, later in-place edit with recovery | Capability-specific fixtures; in-place recovery/backup/free-space and restore acceptance incl. WF-22/23/34/50/57 |

**Stage V is independent, not a blocker for Stage 1.** It may be delivered and accepted *before* Stage 1, or Stage 1 may proceed independently once its own writer gates pass. Neither feature requires the other to be installed. The optional Open in editor… affordance is capability-gated and must not hold up viewer release. **P0 safety requirements apply whenever the relevant operation is introduced.** A stage description does not permit lower assurance for a new write format. “Core six fields” means *targeted for testing*, not guaranteed if any field fails qualification. Before first writer: user-visible Review Changes must be complete even if advanced batch features are not yet shipped.

## 18. Open engineering validations

The old OPEN-01 to OPEN-43 list has been **retired as the active normative queue**. Their settled policy outcomes live in §§1–13 and the decision-history appendix. The items below are practical validation gates, not excuses to improvise different product behavior.

| Gate | Required evidence | Blocks release of |
|---|---|---|
| **ENG-01: JPEG tag/charset proof** | Test exact ExifTool list-item syntax (`-XMP-dc:Subject=item` repeated vs qualified `-sep`, no comma-as-list), ordered multi-creators (`rdf:Seq`), default-language `-XMP-dc:Title-x-default=...`/Description/Rights/UsageTerms preserving other `xml:lang` values, charset conversion with `CodedCharacterSet`, per-item IIM limits, and all untouched fields. Record tested installed ExifTool version. | Each first-wave writable field |
| **ENG-02: JPEG codestream comparator** | Validate class A decode-critical markers and multi-SOS scan payloads exactly; class B APP0/JFIF, APP1 EXIF, APP2 ICC, APP14, COM, vendor and unrelated APP13 resources; class C only approved APP1 XMP/APP13 IPTC edits. Accept permitted marker relocations/APP insertion without relaxing nested-resource checks. Prefer a proven existing library or minimal bounds-checked marker walk plus independent structural diagnostics; neither Pillow decode nor ExifTool `-validate` alone suffices. Record dependencies, fixtures, split extended XMP, malformed-file refusal, parser limits and failure behavior. | First JPEG metadata publisher |
| **ENG-03: Review state machine** | Same-screen blocker exclusion with revised plan revision, scope/pending indicators, exact filenames, destination/collision changes, stale-source invalidation, accessibility | First writer and batch |
| **ENG-04: Limited XMP-only mode** | Qualify proactive operation-wide Modern XMP only profile and inline overflow switch, exact selective removal only for contradictory IIM equivalents, preservation of matching/unrelated IIM, full batch re-planning, language alternatives and truthful compatibility counts. Include removal of the **last** `IPTC-IIM` dataset from Photoshop `APP13` / `8BIM 0x0404`; inspect empty-resource/container behavior, lengths/padding, preservation of other IRBs, ExifTool diagnostics and independent third-party reader outcomes. Fail closed if ambiguous. | Display/enabling advanced profile or inline recovery |
| **ENG-05: Publication and filesystem** | Staged copy behavior, atomicity/durability limits, mtime, ACL/xattr/identity checks, source fingerprint, late collisions, power-loss/fault simulations | Each writable filesystem/strategy |
| **ENG-06: ExifTool process management** | Correct request framing, timeout/restart, batch item isolation, cancellation, hostile filename handling | Persistent ExifTool batch acceleration |
| **ENG-07: Spreadsheet literal safety** | Precise profile specification and supported LibreOffice/other versions; formula and Unicode, leading-zero, multiline, external resave behavior, ambiguous escape handling | Spreadsheet-friendly export/round-trip |
| **ENG-08: In-place recovery** | Backup location/owner permissions, managed manifests, space preflight, soft threshold settings, restore over changed target, manual cleanup, crash recovery | Edit originals and Restore |
| **ENG-09: Sidecar and formats** | Pairing, conflict handling, safe writes, ICC/EXIF/unknown data retention for each additional format | Each new still format/sidecar |
| **ENG-10: Real-world interoperable results** | IPTC test fixtures, named versions of Lightroom Classic, Photo Mechanic, digiKam and ExifTool when available; documented failures/limitations | Marketing/claims of cross-application behavior |

**Known choices still needing UI measurement rather than a new product decision:** near-limit warning threshold (starting point 80%), recovery warning default (starting point 5 GiB), precise editing controls for advanced metadata, real-world layout width and keyboard shortcuts. Tests may tune these numbers without changing preservation or review requirements.


### Viewer-specific engineering qualification gates (VENG, not editor write gates)

| Gate | Required evidence | Blocks release of |
|---|---|---|
| **VENG-01: Reader/capability and structured extraction matrix** | Compare structured JSON candidates `exiftool -j -a -u -g1 -struct` and family-4 uniquely qualified (`-G4`) output; do not scrape formatted text. Verify JSON duplicate-name collision behavior (because `-a` alone does not guarantee unique JSON names), multiple values/lists, XMP languages and structures, unknown tags, MakerNotes, sidecar source identity, Unicode/multiline content, binary placeholders without unbounded `-b`, bounded output and malformed-file errors. Probe each claimed still format; record ExifTool version and honest partial/unsupported states. | Each viewer format/read claim |
| **VENG-02: Read-only boundary and responsiveness** | Confirm browser and readers never call write operations or touch source/sidecar bytes; safe parser/thumbnail limits, inert rendering, cancellation and large selection behavior; distinguish file-system atime from intentional writes | First standalone browser milestone |
| **VENG-03: Comparison and report safety** | Verify stable cross-file identity, source-aware comparison, truthful Missing/Unreadable, report redaction and selection scoping, output permissions, JSON/TSV/text encoding and formula-like literals | Compare/export controls when introduced |

## 19. Change control and handoff

- Maintain stable META, WF, ENG, VIEW, VB, and VENG identifiers. Editor IDs are not renumbered by introduction of the separate read-only browser. A change to one policy must update its canonical paragraph, requirement row, relevant workflow cases, and the revision history together. Do **not** append another overriding normative section.
- Label **Decided**, **Validation pending**, **Deferred**, and **Implemented/tested** accurately. Acceptance of design is not acceptance of code or a supported format.
- A reviewer's proposed change should identify the affected canonical section and test scenario; do not silently resurrect an older OPEN item or duplicate contradictory wording.
- Use one feature at a time; no enormous refactor of `kim_all` simply to accommodate metadata editing. Test full current `natacha` tree on `homebase` with Dolphin and get user acceptance before push.
- After each design revision, issue a **complete, independently shareable, versioned Markdown specification** with the change log intact. Reviewer should not need this conversation or v0.1–v0.6 files to understand current requirements.

## 20. Appendix: review disposition and decision history

### Version 1.2 viewer usability and reader qualification review, November 12, 2026

An external review of v1.1 identified five viewer-specific refinements. Recommended dispositions: (1) allow a **user-clicked, independent Open in editor…** launch, while forbidding any implicit handoff or transferred edits; (2) deliver Compare in a later viewer increment and place Creator & Rights prominently; (3) keep six core metadata slots visible but hide most other absent fields behind Show empty fields; (4) evaluate structured ExifTool JSON instead of scraping human-formatted output, including `-G4` collision disambiguation and bounded binary behavior; and (5) make Stage V explicitly independent of Stage 1 writer implementation. The default report profile is Description, Camera & capture and Creator & Rights, **excluding** GPS, serial identifiers, full paths and sensitive contact data unless opted in. These recommendations refine VIEW/VB/VENG only and are **pending owner approval**. ExifTool's documented JSON behavior is a design basis, not test evidence on `natacha`.

### Version 1.1 addition, November 12, 2026

The owner requested a **metadata browsing and viewing component completely outside the editor** while away from the development workstation. Version 1.1 added a separate read-only Dolphin action and viewer contract in §2.1, plus VIEW/VB/VENG registers and delivery stage V. **The v1.0.1 editor's write rules remain unchanged.** The viewer's visual grouping, Compare timing and report defaults were proposals. Version 1.2 records an external review and recommends an explicit independent editor-launch action, prioritized rights display, empty-field filter, privacy-aware default report columns, structured ExifTool JSON qualification and independent Stage V scheduling. These viewer details remain subject to owner sign-off and engineering tests. No code was inspected or modified on `natacha`. This historical note is non-normative and does not override §2.1.


**This appendix is historical and non-normative.** The canonical requirements are §§1–13. Earlier v0.3 audits and v0.4 §28 overrides have been folded into those sections and removed as independently authoritative material. A prior “Open” note never overrides the current contract.

### 20.1 First Gemini review (informed v0.5, November 12, 2026)

| Finding | Adopted disposition |
|---|---|
| All-or-nothing batch blocker causes avoidable friction | **Accepted with safety:** visible single-click exclusion and same-screen revised-plan confirmation, no hidden skip; §5, WF-53 |
| Hard IIM byte limits create a usability cliff | **Accepted with safeguards:** live encoded-byte warnings, qualified explicit XMP-only limited-compatibility mode and reviewed legacy-field removal, never silent divergence; §3, WF-54 |
| Create copies can branch into confusing derivative versions | **Accepted:** Continue editing created copies targets only verified outputs in a new clean editing context; §6, WF-56 |
| Persistent manual backup retention may exhaust storage | **Accepted:** soft configurable warning, management link and hard space preflight, no automatic loss of recovery; §9, WF-57 |
| JPEG preservation verification lacks an objective mechanism | **Accepted with correction:** compare each scan/required decoding parameters with a marker-aware parser, not everything between first SOS and EOI; §9, WF-58 |
| Formula-escaped CSV can lose reversibility | **Accepted with caveat:** machine-exact vs tested spreadsheet-friendly profile; arbitrary external spreadsheet round trips not guaranteed; §7, WF-59 |
| Repeated normative contracts, stale OPEN items, historical audit bloat | **Accepted:** one canonical specification, compact historical appendix and ENG validation register; §§1–19 |
| Exact tag mapping and command/charset behavior not fully specified | **Partly accepted:** official IPTC field/property/limit mapping now explicit, but ExifTool write-argument, encoding, language and array behavior remains a measured implementation gate, not an unverified copy-paste command; §3, ENG-01 |

### 20.2 Timeline and superseded design records

| Version | Date | Retained decision lineage |
|---|---|---|
| 0.1 | Nov 8, 2026 | Still-image metadata scope, Dolphin menu placement, professional fields, batch operations, CSV/text workflows, Review Changes, initial 50 requirements |
| 0.2 | Nov 10, 2026 | Copies default regardless of selection count; in-place requires persistent recovery; explicit namespace writes; ExifTool, filesystem and cancellation safeguards |
| 0.3 | Nov 12, 2026 | Deep audit of typed fields, immutable plans, CSV, partial dates, naming, provenance, privacy and verification |
| 0.4 | Nov 12, 2026 | Ratified META-061 through META-084; first six JPEG field target, strict paired XMP/IIM, blocked-file exclusions, recovery and testing contracts; appended override section |
| 0.5 (review draft) | Nov 12, 2026 | Consolidated one authoritative design; proposed Gemini UX feedback with technical corrections; META-085..092, WF-53..60 and ENG-01..10; removed duplicate normative audits |
| **0.6 (review draft)** | **Nov 12, 2026** | **Resolved the second Gemini review without new feature IDs: explicit continuation strategy and provenance-aware naming; advanced batch-wide XMP-only profile; reason-group exclusions; ExifTool list/lang-alt pitfalls; three-class JPEG comparator; tightened ENG gates and scenarios** |
| **1.0 (design-freeze candidate)** | **Nov 12, 2026** | **Fixed WF-28 compatibility contradiction; added conditional empty APP13/`8BIM 0x0404` qualification and reader checks under ENG-04; made ENG-02 library reuse permissible without relaxing byte-preservation guarantees; consolidated v0.5/v0.6 proposals into frozen design baseline with owner sign-off still required. No new META, WF, or ENG IDs.** |
| **1.0.1 (editorial correction)** | **Nov 12, 2026** | **Aligned META-047 status with the settled privacy warning policy in §12; updated §19 historical-file reference to v0.1–v0.6. No product, workflow, engineering gate, or acceptance-scenario changes. Owner sign-off and ENG qualification remain pending.** |

### 20.3 Second Gemini review (informed v0.6, November 12, 2026)

| Observation | Disposition, canonical location |
|---|---|
| Continue editing derivatives can create repeated `-metadata` suffixes | **Accept with correction:** provenance-aware version sequence and an explicit option for recoverable in-place updating when qualified. No implicit change from Create copies; §6, WF-56. |
| Per-field XMP-only resolution creates batch friction | **Accept:** one advanced operation-wide storage profile, also selectable through the inline overflow warning; count all affected/removable IIM values; §3.2, WF-54, ENG-04. |
| Blocked-file exclusion conceals different risks | **Accept:** reason-group controls, names, unique counts and differentiated remediation; §5.1, WF-53. |
| ExifTool array and language-alt write traps | **Confirm from ExifTool docs:** repeated list arguments or qualified separator, preserve `rdf:Seq` order and explicit `x-default`; do not assert untested CLI incantations work in all supported versions; §3.1, ENG-01. |
| JPEG writer may insert/split/reorder APP segments | **Accept and refine:** three-class comparison of decode-critical, protected auxiliary, and explicitly authorized nested target resources; not APP position/count equality; §9.2, ENG-02. |
| Freeze scope and avoid endless META identifiers | **Accept as change-control recommendation:** refine META-085..092 and WF-53..60 in place, keep ten ENG gates, require evidence before expanding Stage 1; §19. |

**Historical note (v0.6):** At that revision these refinements were review proposals. They are consolidated into the v1.0 product-design baseline for owner sign-off, but this is **not** evidence that ExifTool, C2PA checks, JPEG parsing or original editing work. ENG gates still determine which controls may be enabled. The document revision does not change KIM6 source files.

### 20.4 Third Gemini review (informed v1.0, November 12, 2026)

| Observation | v1.0 disposition |
|---|---|
| WF-28 contradicted the advanced Modern XMP only profile | **Fixed:** compatible-mode overflow blocks unless the user explicitly switches to a qualified XMP-only mode and re-confirms the fresh review; §3.2, WF-28, WF-54. |
| Final IIM removal may leave an empty APP13 / Photoshop IPTC resource | **Accepted as a validation risk, not an observed universal ExifTool defect:** qualify selective removal, empty resource/container structure, preservation of unrelated IRBs and reader behavior; §3.2, WF-54, ENG-04. |
| Building a complete custom JPEG parser would distract from Stage 1 | **Accepted with guardrails:** reuse a proven component or build a minimal bounds-checked marker walk; independent tests must still establish three-class invariants. Neither image decoding nor ExifTool `-validate` alone proves exact preservation; §9.2, ENG-02. |
| Freeze the scope before implementation | **Accepted as product-design target:** no new tracked requirements or workflows. The v1.0 contract is ready for owner sign-off; engineering gates and code/repository change authorization remain separate. |

### 20.4.1 Editorial v1.0.1 and viewer v1.1 tracking

- **v1.0.1:** Corrected META-047's accepted privacy-warning status and updated archival version references, without modifying editor product behavior.
- **v1.1:** Added a separate read-only Metadata browser action, architecture, phased UI, VIEW-001..014, VB-01..09 and VENG-01..03; no existing editor write rule changed.
- **v1.2:** Refined viewer-only contract: optional explicit independent Open in editor… launch, core six field visibility and Show empty fields toggle, Description/Creator & Rights/Camera & capture overview order, privacy-aware report selection defaults, structured JSON VENG-01 qualification including JSON duplicate-name issues, and Stage V / Stage 1 independence; added VB-10. All editor META/WF/ENG policy unchanged.

### 20.5 Closed historical questions

The former **OPEN-01..OPEN-43** identifiers remain searchable here as a historical family, but are **not** a second active question register. Examples: OPEN-01 is settled by Create copies (see §6); OPEN-02 and OPEN-21/22 by persistent recovery (§9); OPEN-09/31 by explicit Review exclusions (§5); OPEN-28/23 by paired tag and XMP-only profiles (§3); OPEN-33 by explicit CSV semantics (§7); OPEN-36 by verified preservation (§9). Technical matters not yet verified are relisted once as **ENG-01..ENG-10** in §18. Historical audit detail remains available in earlier archived v0.1–v0.4 snapshots and is not necessary to interpret this self-contained document.

### 20.6 External review from November 10, 2026

Ratified: mandatory review, video deferral, format realism, preserved original media, planned persistent ExifTool sessions, explicit IPTC/XMP synchronization and staged per-file publication. Rejected: silently choosing in-place for one image but copies for batches; deleting the sole original backup when the dialog closes or cache is cleaned. ExifTool's unqualified tags do not guarantee synchronized equivalent IIM/XMP fields. These remain unchanged through v1.0.

### 20.7 Questions worth asking further reviewers

1. Which professional descriptive fields should follow the first six, and what real-world cross-application behavior is essential?
2. Does inline exclusion plus revised-plan acknowledgment make large mixed selections efficient without undermining auditability?
3. Can a qualified advanced **Modern XMP only** batch profile be explained with clear IIM-removal counts and no accidental change to other fields?
4. What tested three-class JPEG marker/resource comparator and failure fixtures safely handle segmented APP1/APP13 while protecting every scan?
5. How should a tested LibreOffice CSV profile retain literal formula-leading captions without claiming universal spreadsheet reversibility?
6. Which recovery storage thresholds and UI controls best serve image collections on constrained Linux partitions?

## 21. References

The following are relevant standards, official technical sources and interoperability targets. These references informed the **design**, not an assertion of completed tool integration.

- [IPTC Photo Metadata Standard 2025.1](https://iptc.org/std/photometadata/specification/IPTC-PhotoMetadata-2025.1.html), especially §§5.3.4, 7.3, 7.6, 7.11, 7.18, 7.20 and 7.25.
- [IPTC Photo Metadata interoperability tests](https://iptc.org/standards/photo-metadata/interoperability-tests/).
- [IPTC Photo Metadata Technical Reference](https://iptc.org/std/photometadata/documentation/techreference/).
- [IPTC Photo Metadata User Guide](https://iptc.org/std/photometadata/documentation/userguide/).
- [ExifTool application documentation](https://exiftool.org/exiftool_pod2.html), tag groups, arrays, stay-open and write arguments.
- [ExifTool command-line reference](https://exiftool.org/exiftool_pod.html), JSON `-j`/`-g`/`-G`/`-G4`, `-struct`, duplicate-tag name collisions, binary output and read-side inspection limitations.
- [digiKam Metadata View manual](https://docs.digikam.org/en/right_sidebar/metadata_view.html), precedent for a distinct informational metadata view, filtering, search and copy/export.
- [ExifTool FAQ](https://exiftool.org/faq.html), character encodings, IIM legacy conversion and CodedCharacterSet.
- [ExifTool XMP Tags](https://exiftool.org/TagNames/XMP.html), language-alternative `x-default` targeting and behavior when unqualified.
- [ExifTool FAQ §17](https://exiftool.org/faq.html), list-type writing syntax and the non-equivalence of comma-delimited scalar values.
- [Exiv2 JPEG segment overview](https://dev.exiv2.org/projects/exiv2/wiki/The_Metadata_in_JPEG_files), APPn, SOS, DHT, DQT and progressive JPEG marker roles.
- [OWASP CSV Injection guidance](https://owasp.org/www-community/attacks/CSV_Injection) and [WSTG CSV Injection testing](https://wstg.owasp.org/latest/4-Web_Application_Security_Testing/07-Injection/21-CSV_Injection/), which caution against universal spreadsheet escaping claims.
- [Linux rename(2)](https://man7.org/linux/man-pages/man2/rename.2.html) and [fsync(2)](https://man7.org/linux/man-pages/man2/fsync.2.html), filesystem atomicity and durability distinctions.
- [C2PA specifications](https://c2pa.org/specifications/specifications/), credential/provenance verification implications.
- Adobe Lightroom Classic, Photo Mechanic, digiKam and ExifTool as real-world interoperability test targets, not bundled dependencies.

**Final confirmation:** Still images only; video viewing/editing deferred in these new tools. The first writable editor target remains verified JPEG with six logical fields, Create copies, exact file destinations and mandatory Review Changes. Editor baseline: **92 META requirements, 60 WF scenarios, 10 ENG gates unchanged**. Standalone browser design: **14 VIEW requirements, 10 VB scenarios, 3 VENG gates**, with separate Stage V that can proceed before Stage 1. All viewer refinements in v1.2 are recommendations pending owner sign-off and empirical qualification. No code or source media has been changed by creating this document.
