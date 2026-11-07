# November 3, 2026 audit - Step 2 implementation

Implemented against `recovery/kim-all`, starting at
`42477c8292581d616e5a4eadc69fe87f40e34147`. The working tree was clean before
editing. All work remains uncommitted. Only ARCH-005 through ARCH-009 are in scope.

## Results and work counts

These are work counts, not elapsed-time speedup claims. Generated disposable
fixtures were used throughout; no personal images were inspected. None of the
five findings was already completely resolved.

| Finding / controlled operation | Before | After | Evidence |
|---|---:|---:|---|
| ARCH-005: helper Python processes per successful GPS image | 8 | 4 | Actual CLI subprocess replay of the dispatcher's per-image sequence |
| ARCH-005: full plan reads/decodes | 8 | 4 | Instrumented helper entry points on the same generated-image scenario |
| ARCH-005: approval digests | 5 | 4 | Instrumented `approval_digest` during that sequence |
| ARCH-005: entry searches | 8 | 4 | Static call-path count; the combined stage reuses its selected entry |
| ARCH-005: canonicalizations selecting row 500 | 500 | 1 | Instrumented `absolute` in old/new `approved_entry` against a 500-entry lookup fixture |
| ARCH-007: staged GPS-removal verification ExifTool requests | 15 | 1 | Real ExifTool wrapper log, identical 15 selections and fixtures |
| ARCH-007: whole selective-GPS operation ExifTool requests | 19 | 5 | Actual dispatcher adapter logs with Python enabled, native encoded-data verification retained |
| ARCH-008: cold ordinary Recipe plan ExifTool requests | 7 | 3 | Counted real `run` calls; ImageMagick stays at 2 |
| ARCH-009: intrinsic inspections for ten placements of one logo | 10 | 1 | Real tool-request count in one inspection scope |
| ARCH-009: ExifTool / ImageMagick requests for those placements | 20 / 30 | 2 / 3 | Same generated logo and per-image geometry sequence |

The GPS counts exclude the unchanged initial whole-plan approval verification.
The CLI replay isolates the helper sequence; it does not count unrelated shell,
process-monitor, or image-validation processes. Plan read/digest instrumentation
runs those same entry points in process. Searches are explicitly a static count.
The 500-row canonicalization probe isolates lookup work and does not claim to
represent 500 real GPS publications.

Recipe presentation measurements used real offscreen Qt widgets, one warning
per result, a fixed selected row, and one final summary refresh. A counting
results dictionary recorded every `values()` / `items()` iterator visit;
`os.stat` and property-field generation were instrumented.

| Rows | Full-result iterator visits before → after | Warning identity stats before → after | Selected-property rebuilds before → after |
|---:|---:|---:|---:|
| 10 | 325 → 0 | 65 → 10 | 10 → 1 |
| 100 | 25,750 → 0 | 5,150 → 100 | 100 → 1 |
| 500 | 628,750 → 0 | 125,750 → 500 | 500 → 1 |

These warning-stat fixtures deliberately lack a captured identity, exercising
the fallback path on both versions. Successful real Recipe rows now carry the
already-inspected source identity, eliminating these additional grouping stats
entirely. Per-result updates still occur once per input. Filesystem work needed
for source inspection, filename collision checks and publication is retained.
The measurements cover collapsed warning details. No event-loop latency or
interactive responsiveness improvement is claimed.

## Implementation

**ARCH-005 - completed with bounded reductions.** `kim_preview entry` combines
state, exact target selection, dependency validation and the live pre-item guard.
The shell consumes its NUL-delimited response only to select the work. A combined
location `stage` command writes and verifies within one parsed-plan lifetime,
reusing the selected immutable entry and one integrity digest. It rechecks live
source, destination and dependency identities after writing. Canonicalization
was moved outside the entry-search generator. Both final publication guards
still independently reload and validate the approval plan. The existing
`write`, `verify`, and preview query interfaces remain available.

**ARCH-006 - completed for normal result delivery.** Ready, problem and repair
counts update from the affected row, including replacement results. Execution
job counts also update on completion rather than rescanning on every stage.
Diagnostics append for ordered results and rebuild only for replacements or
out-of-order problems. Warning groups accumulate once, preserving original
source identities and existing captions/details; hidden technical text is
materialized on disclosure. Selected properties rebuild only when the selected
row, generation or recipe changes. The Run predicate additionally requires
`ready == len(files)`, so cancelled rows cannot authorize execution.

Generation rejection, pending-worker gating, recipe/destination invalidation,
validated execution snapshots, cancellation and existing diagnostic text remain.
Replacing a warning-bearing row genuinely rebuilds warning groups. Expanded
warning details must reflect new data and can still regenerate the detailed
text; this batch does not introduce a new presentation framework.

**ARCH-007 - completed for compatible selective-removal verification.** A single
ExifTool JSON query verifies the union of known empty GPS/AI removal selections.
Family 0/1/4 groups, duplicate instances and structured values are retained.
Only absent fields or empty strings satisfy removal; arrays, objects, numeric
zero, unexpected nonempty values and malformed/duplicate JSON fail closed.
Retained structured location text is not accidentally included in removed leaf
selections. The allowlist prevents unrelated queries from entering this path.
Scalar/copyright/date comparisons keep their exact existing `-s3` print
conversion. Without Python on PATH, verification retains the complete original
per-tag path. Further scalar/date batching is deferred because it requires
careful ExifTool print-conversion equivalence and gives less benefit here.

**ARCH-008 - completed for selected planning observations.** Copyright, GPS, AI,
ICC description and ICC information share one deliberate text-valued query for
ordinary inputs. Numeric header/date inspection remains separate, as does the
existing descriptive-metadata preservation query. Family 0/1 matching preserves
EXIF/IPTC/XMP distinctions. PSD original-document metadata and normalized
composite ICC observations remain separate because they describe different
objects. Private execution-source snapshots are still inspected freshly.
No broad metadata cache or new PSD parser was introduced.

**ARCH-009 - completed.** Intrinsic logo identity, oriented dimensions, opacity,
profile/color checks and decode validation are reused within an explicit
batch/generation context, bounded to 64 paths and discarded on exit. Every
lookup checks current regular-file identity and the current sRGB policy profile
identity. Replacement, metadata changes, symlinks, policy changes and cancellation
cannot silently reuse old facts. Placement/scaling stays per image. GUI workers
and direct Recipe preview/execution share the scope only within their batch;
private execution-logo copying, identity checks, color inspection and rendering
remain fresh.

## Safety checks deliberately retained

Independent decoded-pixel, binary ICC, JPEG/WebP encoded-data, TIFF encoded-data,
ISOBMFF container and PNG presentation checks remain in place. Staging and atomic
create/explicit-overwrite publication are unchanged. Both final GPS publication
guards reload the plan. Original-source metadata digests, reference/GPX identity,
destination identity, hardlink/symlink rejection, exact approved names, external
create/prompt policy and cancellation gates remain mandatory.

No persistent service, global approval cache, new dependency, image-processing
concurrency, format support, output naming or user workflow was introduced.

## Verification

- Added `tests/test_processing_reuse.py`: eleven focused checks covering actual
  work counts, distinct namespaces/dates, structured GPS removal selections,
  malformed/duplicate/structured response refusal and empty/missing handling,
  staged publication, pixels/ICC/source/collision preservation, changed GPS
  approvals/sources/dependencies/destinations, authorized overwrite staging,
  mid-stage destination changes and missing-plan rejection, logo replacement/policy/cancellation, generation
  invalidation and Run gating for 10/100/500 rows.
- New focused checks: 11/11 passed (a ten-test module run plus the added
  response-refusal check). The staged-publication count assertion was also
  rechecked independently after its addition.
- `test_recipe_correctness.py`: 20/20 passed, including capture fractions and
  offsets, independent EXIF/XMP clocks, PSD raw metadata and source preservation.
- Differential old/new handler comparison: all 16 outcomes matched across
  generated JPEG, PNG, TIFF and PSD files, each with rename, GPS stripping,
  conversion and date-shift plans. Both successful states and refusal decisions
  were compared, not merely process exit codes.
- `test_recipe_workflow.py`: 15 passed; one failure and one timeout reproduced
  against the starting implementation: the existing menu-caption expectation
  (`KIM6 Recipes` versus `KIM6 - Recipes`) and the editor-to-run test timeout.
- `test_metadata_actions.py`: 20 initially passed; nine new missing-Python
  failures were corrected by retaining the legacy verification fallback and all
  nine passed on focused rerun. Two unrelated failures reproduce at the starting
  implementation: missing copied `kim_preview.py` in the interactive copyright
  fixture and the timeshift adapter's rename-only publication rejection.
- Three existing job tests passed: result counts/source warning grouping,
  warning disclosure/copy, and cancellation retaining the first publication.
- Python syntax validation, Bash syntax validation and `git diff --check` pass.
  ShellCheck reports the same 17 pre-existing diagnostics, with no new diagnostic
  code/message combinations.
- Two-axis code review: Standards - no findings; Spec - no confirmed correctness
  findings. The Spec reviewer requested confirmation of separate before/after,
  PSD and fallback evidence, supplied above.

The repository-wide regression suite, installer and Dolphin menu installation
were not run. Existing tests/fixtures were not changed to suppress failures.
Synthetic PSD tests do not establish rendering fidelity for personal Photoshop
files. No wall-clock speedup or responsiveness claim is made.

## Guidance, skills and changed files

Read `docs/DEVELOPMENT.md`; no applicable AGENTS.md, CLAUDE.md, glossary or ADR
was present. Inventoried the installed Matt Pocock engineering skill directories.
Read `improve-codebase-architecture`, `codebase-design`, `diagnosing-bugs`,
`implement`, `code-review` and `tdd`.

Applied `codebase-design` for small interfaces and controlled observation
lifetimes, `diagnosing-bugs`' performance-measurement loop, `implement` for the
scoped implementation and focused checks, and `code-review` with separate
Standards and Spec agents. The architecture skill's scope/YAGNI guidance informed
the limited scope; its audit/report/grilling workflow was not run. TDD was read
but a full pre-agreed-seam red/green skill workflow was not claimed. Explicit
user requirements overrode the implement skill's full-suite and commit steps.

Modified runtime files: `src/bin/kim_all`, `kim_preview.py`, `kim_location.py`,
`kim_recipe_run.py`, `kim_job.py`, `kim_recipe_image.py`, `kim_image_ops.py`, and
`kim_recipe_core.py`. Added this report and `tests/test_processing_reuse.py`.
All changes remain uncommitted; no push or release was made.

Final status: eight modified runtime files and two untracked additions (this
report and the focused test module). The tracked runtime diff is 279 insertions
and 74 deletions. Final diff inspection found no unrelated modifications.
