# KIMng UI Design Standard

**Version:** 1.1\
**Established:** November 18, 2026\
**Status:** Accepted design standard\
**Platform:** KDE Plasma 6, Dolphin, Qt 6, PySide6, KDE Breeze\
**Primary accepted reference:** Convert PDF pages to images

## 1. Purpose and authority

This document defines the approved user-interface conventions for KIMng.

The objective is a coherent, native KDE interface across image processing,
metadata, GPS, PDF, video, Recipes, and publication workflows.

The accepted PDF pages-to-images workflow establishes the reference for
Settings, Review Changes, destination selection, action buttons, batch
progress, and completion reporting.

These conventions apply to new features and substantive UI corrections.
Previously accepted interfaces are not automatically reopened merely
because their presentation differs.

The standard governs presentation and interaction. Existing operation
contracts, publication safety, file handling, and accepted behavior
remain authoritative.

A change to this standard requires explicit user acceptance.

## 2. General design principles

KIMng interfaces must be:

- Native to KDE Plasma 6 and Dolphin.
- Consistent with the active KDE/Breeze theme.
- Compact without sacrificing readability.
- Direct and predictable.
- Clear about source files and proposed output.
- Consistent across individual and batch processing.
- Responsive during long-running operations.
- Honest about validation, warnings, failures, and completion.
- Safe against unintended file modification.

Prefer established KDE and Qt patterns over custom controls.

Do not introduce new top-level Dolphin menus when an existing approved
submenu is the appropriate location.

Do not redesign accepted workflows without a demonstrated need.

## 3. Language and terminology

Use US English, sentence case, and concise established labels.

Use "image" rather than "photo" where practical.

Do not use em dashes in titles, labels, messages, comments, or
documentation.

Avoid verbose table headings when shorter terms convey the same meaning.

Preferred terms:

| Concept | Standard wording |
|---|---|
| Original source | Input |
| Planned output filename | Output |
| Output location | Destination |
| PDF page selection | Pages |
| Processing operation | Action |
| Item result | Status |
| Approval gate | Review Changes |
| Execute approved plan | Apply Changes |
| Return to previous controls | Back |
| Abort without applying | Cancel |

Operation-specific wording is allowed when it adds information.

For example, metadata change planners may use Current and Proposed.

Dialog titles should closely match the corresponding Dolphin menu action.

## 4. Window titles

Use these formats:

| Dialog | Format |
|---|---|
| Settings | KIMng - Action - Settings |
| Review | KIMng - Action - Review Changes |
| Progress | KIMng - Action - Progress |
| Completion | KIMng - Action |
| Error | KIMng - Action |

Use descriptive action names rather than generic titles such as
"Settings" or "Review Changes" alone.

Avoid internal implementation names in user-facing titles.

## 5. Native Qt and KDE components

Use PySide6, Qt 6, and Breeze-native widgets.

Preferred controls include:

- QDialog and appropriate QMainWindow interfaces.
- QDialogButtonBox with correct button roles.
- QTableWidget or model/view tables where appropriate.
- QLineEdit for editable paths.
- QComboBox for standard selections.
- QSpinBox for bounded numerical inputs.
- QCheckBox and QRadioButton for applicable choices.
- QFileDialog for selecting directories and files.
- Native progress reporting through established KIMng infrastructure.

Respect KDE button ordering, keyboard navigation, focus behavior,
accessibility names, resizing, and the active color scheme.

Prefer QIcon.fromTheme() and the shared button presentation helper,
src/bin/kim_dialog_buttons.py.

Avoid competing visual themes or independently styled button systems.

## 6. Standard action buttons

### Back

- Text: Back
- Icon: Breeze black left arrow, normally go-previous.
- Position: Far left of the bottom button row.
- Visibility: Show only when there is a preceding step.
- Behavior: Return to the preceding settings or configuration step.
- Preserve appropriate unsaved controls when navigating backward.
- Do not display Back in a single-stage dialog without a previous step.

### Review Changes

- Text: Review Changes
- Icon: Breeze green checkmark.
- Position: Bottom right, immediately before Cancel.
- Behavior: Validate and present the proposed operation.
- Must not execute a derivative-producing operation.

### Apply Changes

- Text: Apply Changes
- Icon: Breeze green checkmark.
- Position: Bottom right, immediately before Cancel.
- Behavior: Execute only the approved and still-valid review plan.

### Cancel

- Text: Cancel
- Icon: Breeze red X, normally dialog-cancel.
- Position: Far right.
- Behavior: Exit without initiating new work or cancel active work
  according to the operation's safety contract.

Use QDialogButtonBox roles for semantic behavior and the
active KDE/Breeze style for standard button ordering.

AcceptRole, ApplyRole, RejectRole, and ActionRole are not
interchangeable. In particular, AcceptRole can emit accepted(),
while ApplyRole does not automatically accept or close the dialog.

Review Changes validates and opens the review stage without
executing the operation. Apply Changes executes only the approved
plan. Assign roles and connect signals according to those behaviors,
using an outer layout where necessary to preserve KIMng's accepted
button positions.

When Back must appear at the far left, it may be placed in
the outer button-row layout separately from the right-aligned
QDialogButtonBox. Preserve native KDE ordering within the box.

src/bin/kim_dialog_buttons.py is the existing icon-presentation
helper. It does not currently manage button roles or layout.
Do not document it as providing that functionality.

Verify the final arrangement in actual KDE/Dolphin on homebase.

Do not omit icons from these standard actions.

## 7. Dialog sizing and layout

Dialogs should fit their contents rather than occupying unnecessary space.

Requirements:

- Use consistent margins and control spacing.
- Group related controls.
- Minimize empty areas.
- Keep action buttons at the bottom.
- Give tables enough room for filenames and important data.
- Avoid oversized review windows for small batches.
- Permit useful resizing for larger batches.
- Avoid excessive horizontal scrolling.
- Use responsive layouts rather than fixed widget positioning.
- Persist geometry or splitter dimensions where appropriate.

Do not arbitrarily force every dialog to use the same dimensions.

The PDF Settings dialog is the accepted reference for ordinary
settings layouts.

The PDF Review Changes dialog is the accepted reference for
compact batch-review layouts.

## 8. Settings dialog structure

The normal order is:

1. Concise identification of the selected inputs.
2. Operation-specific controls.
3. Optional advanced settings.
4. Space separating settings from destination controls.
5. Destination label and editable path field.
6. Change destination button.
7. Standard Review Changes and Cancel buttons.

Use dropdowns for common choices.

For numerical controls with standard presets, prefer a dropdown
containing the presets and a Custom option that reveals or enables
an appropriate numerical input.

The PDF resolution selector is the accepted example:

- 72 DPI
- 96 DPI
- 150 DPI
- 200 DPI
- 300 DPI
- 600 DPI
- Custom, with an editable DPI value

Operation-specific bounds and defaults must be validated.

## 9. Mandatory Review Changes gate

Every derivative-producing action must present the approved
Review Changes gate before publication.

Presets may populate controls but may not bypass review.

Review must show, as applicable:

- Exact selected source.
- Proposed operation.
- Original preview or relevant source information.
- Planned result or result preview.
- Exact planned output filename.
- Destination directory.
- Warnings and format consequences.
- Blocked and skipped items.
- Operation-specific technical details.

The user must be able to understand what will happen before applying.

Do not silently change output names or destinations after approval.

If the plan becomes invalid, block Apply and require renewed review.

For non-derivative operations, preserve the separately approved
authorization and safety contracts.

## 10. Review table design

Preferred column terminology:

| Column | Meaning |
|---|---|
| Input | Source filename or relevant source |
| Pages | PDF page number or page range, when applicable |
| Output | Exact output filename |
| Destination | Output directory |
| Action | Concise transformation description |
| Status | Ready, Skipped, Blocked, or another justified state |

The accepted PDF table uses:

Input | Pages | Output | Destination | Action | Status

Do not use "Planned output" when "Output" is sufficient.

Do not use "Destination directory" when "Destination" is sufficient.

Column rules:

- Give Input and Output substantial width.
- Keep short Action values in a relatively narrow column.
- Use compact status columns.
- Support user-resizable columns.
- Use reasonable default widths on each opening.
- Persist column widths when useful, not as a universal requirement.
- Enable sorting only where it does not undermine execution order,
  source grouping, or meaningful review sequence.
- Provide full-value tooltips for truncated entries.
- Allow intuitive row selection.
- Maintain sensible widths at different window sizes.
- Do not hide significant warnings solely in a tooltip.

Other workflows may need specialized columns.

For metadata, Current and Proposed may be more meaningful than
Input and Output.

For renaming, current and proposed filenames must be explicit.

Do not impose irrelevant PDF-specific columns on other tools.

## 11. Review summary

Place a concise summary above the review table.

Typical batch information includes:

- Selected source count.
- Ready output count.
- Skipped count.
- Warning count.
- Blocked count.

Distinguish input files from output items when one source produces
multiple outputs.

For example, five PDF documents can produce eight output images.

Do not claim a source is successfully processed merely because its
review state is Ready.

## 12. Details below the review table

Place a selectable, readable details area beneath the table.

The details must change when the selected row changes.

Use real line breaks, never literal backslash-n sequences.

Present information relevant to the actual operation.

Examples:

PDF page rendering:
- Page within source document.
- Rendering resolution.
- Output format and lossless/lossy characteristics.
- Verified or reliably estimated dimensions.
- Relevant memory or size warnings.

Image conversion:
- Color profile behavior.
- Transparency handling.
- Bit-depth and format limitations.
- Lossless/lossy encoding consequences.

Resize:
- Original dimensions.
- Planned dimensions.
- Resampling method.
- Enlargement behavior.

Compression:
- Selected quality or compression settings.
- Lossless/lossy behavior.
- Relevant output limitations.

Metadata:
- Field names and proposed operations.
- Target metadata representation.
- Source provenance and alternatives.
- Sidecar and language considerations.

GPS:
- Selected coordinates and location source.
- Position accuracy or precision reduction.
- Privacy consequences.

Avoid generic boilerplate and duplication of obvious table values.

Do not fabricate output dimensions or estimated output file sizes.

## 13. Destination controls

Default destination:

**Beside each source**

This applies to selections from multiple directories unless a
specific operation has an accepted different destination contract.

Destination controls belong near the bottom of Settings and
Review Changes, separated by a blank line or deliberate spacing.

Standard presentation:

Destination: Beside each source

[Editable path field, empty by default] [Change destination…]

Requirements:

- The path field must be editable.
- An empty path represents Beside each source.
- The placeholder should explain the empty-field behavior.
- Change destination opens a native directory chooser.
- When one output directory is chosen for the entire batch, its path must appear in the editable field.
- Directory validation must occur before approval.
- Review must display the actual planned destination.
- Publication must use the destination the user approved.
- Changing a destination during Review must update the entire plan.
- Any new collision or invalid destination blocks Apply.
- No silently renamed outputs after review.
- Known filename collisions may be resolved during planning
  by proposing deterministic numbered output filenames.
- Every adjusted filename must appear explicitly in Review
  Changes, with a visible warning and the exact proposed name.
- A known collision in one item must not erase otherwise
  valid batch-review entries.
- The user must approve the final proposed filenames.
- A collision appearing after approval must block publication
  rather than trigger another automatic filename change.

Do not replace the editable path field with a non-editable label.

## 14. Standard progress reporting

Use KIMng's existing progress infrastructure rather than creating
an unrelated progress system for each feature.

The existing KDialog and D-Bus progress integration,
including supported qdbus and qdbus6 executable discovery,
and the shared kim_job.py job accounting are reference
implementations.

Reuse the established transport discovery and progress-reference
validation where applicable. Do not assume every Linux
distribution installs the same qdbus executable name.

Do not introduce another progress transport merely for
portability without a demonstrated need.

A batch progress interface should present:

- Descriptive KIMng action title.
- Current source item and total.
- Current source filename or path.
- Current page or operation step when relevant.
- Current output filename.
- Active stage, such as rendering, validating, or publishing.
- Overall percentage or completed count.
- Succeeded count.
- Failed count.
- Cancelled count.
- Skipped count.
- Remaining count.
- Functional Cancel or Cancel All control.

For one-to-many operations, clearly distinguish source files,
pages, and planned outputs.

Progress must update during processing.

Avoid claiming success before publication validation.

The progress window must close on success, failure, or cancellation.

A window must not remain stranded after initialization errors.

Progress service references must accept the documented valid D-Bus
forms returned by the supported KDE environment.

Malformed or unavailable progress replies must not be interpreted
as successful processing.

Keep progress labels readable with proper line breaks and avoid
unnecessary horizontal expansion.

## 15. Publication and source safety

The UI must accurately reflect the actual execution contract.

For derivative-producing actions:

- Preserve the selected originals.
- Capture source identity during planning.
- Revalidate sources before and during execution as appropriate.
- Use the approved output filenames and destinations.
- Detect occupied output paths and late collisions.
- Never silently rename an output after approval.
- Stage produced files privately.
- Validate generated files before publication.
- Use safe no-clobber publication for create-only results.
- Use authorized atomic replacement where explicitly supported.
- Never partially overwrite an existing output.
- Clean up invocation-owned staging files after interruption.
- Preserve already published batch outputs when later work fails.
- Report successful, failed, skipped, and cancelled work accurately.

Never restore timestamps merely to conceal an unsafe source read.

Metadata inspection must preserve source access times and other
required source invariants.

Recipes are derivative-only and retain their separately approved
rights and step controls.

Actual metadata editing remains subject to separately approved
writing, transaction, sidecar, and rollback requirements.

## 16. Cancellation behavior

Cancellation must:

- Stop scheduling new work.
- Interrupt the active operation safely.
- Terminate owned child processes and delegates as necessary.
- Wait for owned processes to stop before deleting their staging.
- Prevent unapproved publication.
- Preserve unrelated files.
- Preserve outputs already published successfully.
- Close owned progress windows.
- Report cancellation distinctly from processing failure.

Do not terminate unrelated KDialog processes or desktop jobs.

Do not treat a disappeared progress service as proof the user
explicitly selected Cancel.

Handle D-Bus communication errors using the established
fail-closed behavior.

## 17. Completion and error reporting

A successful operation should report meaningful completion data.

Where useful, include:

- Number of outputs created.
- Number of failures or skipped items.
- Saved output directory or filenames.
- Open folder.
- Done.

## Successful operation behavior

For ordinary successful processing, close the progress window
and return control to Dolphin without opening an additional
completion or informational dialog.

A successful operation must not require the user to dismiss a
redundant "Completed", "Images created", or equivalent popup.

The completed progress state and the published results are
sufficient confirmation for routine file-processing actions.

Exceptions require a specific usability reason, such as:

- The user must take another action to finish the workflow.
- Important information genuinely requires acknowledgement.
- The operation explicitly requests an interactive result view.

Do not introduce completion popups merely to repeat successful
output counts or reassure the user that the operation worked.

This rule applies to new KIMng workflows. Existing accepted
interfaces should be corrected separately when necessary,
without unrelated refactoring.

Failure, cancellation, blocked publication, or important
undisclosed warnings must still be reported accurately.

Never suppress a meaningful error or conceal partial results
under the silent-success rule.

Failure messages must identify the actual failure when possible.

Avoid generic "Something went wrong" messages.

For batches, report actual counts and retained outputs.

Separate warnings from failures.

Do not describe an operation as successful when publication,
validation, or cancellation checks failed.

## 18. Dolphin menu integration

Use the existing approved menu categories where appropriate.

The PDF pages-to-images operation belongs under:

KIMng - Convert/Compress

Do not add a standalone top-level PDF Tools submenu for it.

Menu items should use concise sentence-case action names.

Respect existing KDE Plasma 6 limitations concerning nested
service-menu submenus.

Use correct KDE service-menu MIME registration.

Maintain mixed-selection behavior and per-action format validation.

Service-menu changes must be installed and verified through the
existing KIMng installer inventory and desktop menu checks.

## 19. Operation-specific variations

The accepted PDF design is a reference, not a requirement that
every workflow have the same exact controls or dimensions.

Examples:

- Metadata Browser is read-only and may use a larger inspection UI.
- Metadata Compare needs a two-image comparison layout.
- Metadata Editor uses change proposals and field-level controls.
- GPS tools require maps and coordinate-specific controls.
- Crop requires a meaningful image and crop preview.
- Collage requires composition controls.
- Video conversion needs codec and stream information.
- Recipes need step editing, validation, and destination controls.

Use the common language, button placement, destination treatment,
review gate, and progress principles wherever applicable.

Preserve established specialist interactions when they are justified.

## 20. Accessibility and usability

Use Qt's native accessibility and keyboard facilities.

Associate labels with their controls using QLabel.setBuddy()
where appropriate. When keyboard mnemonics are intended,
define them explicitly using the label's ampersand mnemonic.

Use QWidget.setAccessibleName() and setAccessibleDescription()
where visible labels alone do not sufficiently identify a control.

Maintain logical tab order and predictable initial focus.
Do not duplicate accessible names unnecessarily.

Ensure:

- Keyboard navigation.
- Readable labels and sufficient contrast through the KDE theme.
- No critical information conveyed only through color.
- Selectable diagnostic details.
- Helpful tooltips for truncated filenames.
- Useful tab order.
- Resizable review content.
- No blocking inspection on the GUI thread where asynchronous
  processing is necessary.
- Visible reasons when Apply or Run is disabled.

Do not substitute a decorative icon for meaningful status text.

## 21. Implementation and testing workflow

Natacha is the development workstation.

Homebase is the functional KDE/Dolphin test machine.

Standard workflow:

1. Inspect natacha's complete working-tree status.
2. Preserve uncommitted changes and avoid overlapping active work.
3. Back up files before risky edits.
4. Make narrowly scoped source changes on natacha.
5. Perform syntax and static source checks.
6. Run git diff --check.
7. Synchronize the complete working tree to homebase, including
   uncommitted changes.
8. Run bash install.sh on homebase.
9. Run kbuildsycoca6 on homebase.
10. Launch Dolphin from natacha using homebase-dolphin.
11. Test in actual KDE/Dolphin on homebase.
12. Obtain explicit acceptance before declaring completion.

Never perform functional application testing on natacha.

Do not commit or push without explicit approval.

Do not modify unrelated work to enforce visual consistency.

## 22. UI acceptance checklist

Before accepting a new or substantially modified dialog, verify:

- [ ] Title follows the KIMng convention.
- [ ] Action matches the Dolphin menu item.
- [ ] Widgets use native KDE/Breeze presentation.
- [ ] Standard buttons use the correct icons.
- [ ] Back is at the far left.
- [ ] Review/Apply and Cancel are at the bottom right.
- [ ] Review is mandatory for derivative-producing operations.
- [ ] Tables use concise, operation-appropriate headings.
- [ ] Input and Output filenames are readable.
- [ ] Action and Status columns are appropriately sized.
- [ ] Details update with the selected row.
- [ ] Details use correct line breaks.
- [ ] Destination controls are at the bottom.
- [ ] Default destination is clear.
- [ ] Destination field is editable where applicable.
- [ ] Review identifies exact planned output filenames.
- [ ] Warnings and blocked items are visible.
- [ ] Review and actual publication use the same approved plan.
- [ ] Batch progress shows current source, output, and counts.
- [ ] Cancellation stops work and cleans up owned resources.
- [ ] Progress closes after completion or error.
- [ ] Ordinary successful processing returns to Dolphin
      without a redundant completion popup.
- [ ] Progress windows close on success, error, and cancellation.
- [ ] Failure and cancellation reporting remains accurate.
- [ ] Source preservation and collision rules are verified.
- [ ] Dialog is sized appropriately.
- [ ] Existing accepted behavior remains intact.
- [ ] Functional testing occurred on homebase in Dolphin.
- [ ] User acceptance was obtained.

## 23. Accepted reference and versioning

The accepted baseline is the November 18, 2026 KIMng
Convert PDF pages to images workflow.

Accepted characteristics include:

- Compact Settings dialog.
- Standard resolution presets and Custom DPI.
- Editable destination controls.
- Review Changes with concise columns:
  Input, Pages, Output, Destination, Action, Status.
- Selected-row details beneath the table.
- Standard Back, Review, Apply, and Cancel icons and placement.
- Mandatory approval before processing.
- KDialog batch progress with current source, page, output,
  stage, counts, and cancellation.
- Successful multi-PDF output publication on homebase.
- Routine successful processing does not require dismissing
  a separate completion notification.

The accepted reference does not imply that every implementation
detail is immutable or that later discovered defects are accepted.

Changes to this standard should be documented with a new version,
specific rationale, and explicit approval.

## 24. Version 1.1 review decisions

Gemini's independent review of version 1.0 was evaluated
against Qt 6 documentation and the accepted KIMng PDF UI.

Adopted:
- Clarification of button semantics versus KDE layout.
- qdbus and qdbus6 portability language.
- One-directory-for-batch destination terminology.
- Explicit native Qt accessibility guidance.
- Back button visibility rules.

Modified:
- Button placement guidance does not claim that the
  shared icon helper manages layout.
- Column persistence and sorting remain conditional.

Rejected:
- Mandatory redesign of accepted dialogs.
- Custom progress systems replacing existing KIMng infrastructure.
- Broad QTableWidget to model/view rewrites.
- Fixed dimensions across all dialogs.
- New accessibility dependencies.

No runtime changes are authorized by this document revision.

## 25. Related implementation references

- src/bin/kim_pdf_pages.py
- src/bin/kim_preview.py
- src/bin/kim_dialog_buttons.py
- src/bin/kim_job.py
- src/bin/kim_job_process.py
- src/bin/kim_all
- src/kim_convertandrotate.desktop.in
- install_inventory.sh
- docs/DEVELOPMENT.md
- docs/ACTIONS.md

The working tree on natacha remains authoritative over committed
GitHub contents and historical documentation.

This document is a design standard, not authorization to refactor
existing dialogs or change publication behavior.
