# KIMng implementation status

Updated: November 18, 2026
Repository: https://github.com/codesterribly/kim6
Branch: recovery/kim-all

## Source of truth

Natacha's complete working tree at /home/coolian/tmp/kim6,
including uncommitted changes, is authoritative.

GitHub provides a committed baseline, not necessarily the
latest implementation state.

Homebase is the KDE/Dolphin functional test machine.

Never classify an existing feature as unfinished using an old
backlog entry without inspecting current source and test status.

## Implemented and explicitly accepted

- Convert PDF pages to images.
- Extract embedded images from PDF.
- PDF output collision handling with filenames approved in review.
- PDF Settings and Review Changes interfaces.
- PDF batch progress and cancellation.
- Removal of redundant PDF extraction success notifications.
- KIMng UI Design Standard v1.1 and its accepted conventions.

Both PDF actions belong in Convert/Compress.

Do not reopen accepted functionality without a demonstrated defect
or explicit new requirement.

## Implemented features

The following have implementations in the repository.

Their presence does not by itself certify that every workflow has
received final homebase acceptance.

- Standalone read-only Metadata Browser.
- Two-image metadata comparison.
- Metadata Editor read-only change planner.
- Browser and Editor Dolphin dispatch.
- Metadata preferences in main Settings.
- Shared metadata reading priorities.
- Existing GPS viewer and map integration.
- Editor GPS viewing and proposed location changes.
- GPS proposal review and unsaved-draft preservation.
- Existing GPS modification workflows.
- Image conversion and compression.
- Resize, crop, rotate, and flip.
- Video conversion and review.
- Video utilities.
- Slideshow generation.
- Watermark functionality.
- Other previously implemented KIMng image actions.

Do not propose implementing these from scratch.

Inspect current source before claiming that integration or
polish is missing.

## Active development

Recipes are being developed separately through Codex.

Avoid modifying Recipe files, related execution contracts,
or overlapping shared infrastructure without coordination.

Recipe completion must be verified independently and accepted
by the user.

## Not yet implemented or separately deferred

### Metadata writing

The Metadata Editor is an implemented read-only planner.

Actual metadata writing remains a separately approved milestone.

Required safety work includes:

- Explicit target and metadata representation selection.
- Safe field-level write plans.
- Source and sidecar validation.
- Combined mandatory Review Changes.
- Transaction and rollback protections.
- RAW and associated-sidecar handling.
- Preservation of unrelated metadata and source invariants.

Do not enable writing as an incidental UI change.

### Other deferred work

- CSV import for metadata editing remains a later milestone.
- Broader video metadata editing remains deferred.
- Target-file-size compression is cancelled.
- Estimated output file size is cancelled.

Do not restart cancelled work without explicit approval.

## Requires current-tree verification

- Previously reported Watermark UI issues.
- Any remaining video or slideshow UI defects.
- Specific documentation gaps resulting from recent changes.
- Any new defects observed during actual Dolphin testing.

These are verification candidates, not confirmed unfinished
features.

## Optional future work

- Read-only architecture and performance audit.
- Targeted cleanup only after specific problems are established.
- Metadata writing safety milestones, with separate approval.
- Public documentation and installation verification.

Architecture cleanup is not authorization for broad refactoring.

## Verification and acceptance rules

Before calling a feature unfinished:

1. Check natacha's branch and complete Git status.
2. Inspect the relevant current implementation.
3. Identify existing menu and Settings integration.
4. Check applicable tests and prior acceptance.
5. Distinguish actual defects from desired enhancements.
6. Avoid overlapping active Codex Recipe work.
7. Test changed functionality on homebase in Dolphin.
8. Obtain user acceptance before marking new work accepted.

For homebase tests:

- Sync the complete natacha working tree.
- Run bash install.sh on homebase.
- Run kbuildsycoca6.
- Launch Dolphin explicitly using homebase-dolphin.

Do not commit or push without explicit approval.

## Change control

This document records implementation and acceptance status.
It is not permission to start new work.

Update an entry only when supported by current source,
testing evidence, or explicit user acceptance.

Do not confuse:

- Proposed.
- Coded.
- Automated-tested.
- Homebase-tested.
- Accepted.

When evidence is incomplete, say so rather than guessing.
