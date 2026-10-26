# KIM6 development guide

This guide describes the checked-in Plasma 6 implementation. KIM6 has one processing entry point, `src/bin/kim_all`; historical standalone scripts remain references and are not invoked by menus or the dispatcher. Feature scope is frozen for the first polished release. Fixes should preserve the documented policies and tests rather than add new processing capabilities.

## Repository map

| Path | Purpose |
|---|---|
| `src/bin/kim_all` | Dispatcher, action implementations, configuration, staging/publication, progress and validation helpers. |
| `src/kim_*.desktop.in` | Five KDE service-menu templates and the 107 visible menu actions. |
| `src/gallery/` | HTML gallery template fragments installed beside the dispatcher. |
| `tests/run.py` | Canonical unittest discovery and runner. |
| `tests/support.py`, `tests/adapter.py` | Disposable workspaces, synthetic fixtures and command adapters used by action tests. |
| `tests/test_*.py` | Action, preservation, cancellation, publication and integration regressions. |
| `install.sh`, `uninstall.sh` | Explicit-inventory Plasma 6 installation, upgrade and safe owned-resource removal. |
| `po/` | gettext translations and desktop-entry catalogs. |
| `docs/` | User references and the GitHub Pages manual. |
| `docs/archive/upstream/` | Byte-preserved upstream and pre-overhaul documentation snapshots. |

`README.md` is the landing page. `INSTALL.md` covers deployment. `docs/ACTIONS.md` is the one complete menu/action inventory. `docs/CLI.md`, `FEATURES.md`, `FORMATS.md`, `CONFIGURATION.md`, and `SAFETY.md` are the detailed references. `docs/index.html` is the static web manual.

## Dispatcher and menu boundary

Dolphin service-menu templates invoke `kim_all <action> ... -- %F`. `%F` forwards local selected paths as separate arguments. Preserve the `--` separator and use Bash arrays for paths; never use `eval`, shell concatenation, or a legacy script as an intermediate entry point. The installer replaces the bare `kim_all` token with the absolute installed executable path.

Menu definitions use `Type=Service`, `X-KDE-ServiceTypes=KonqPopupMenu/Plugin`, `X-KDE-Protocol=file`, and `X-KDE-Submenu`. Do not flatten menus to work around the known KIO 6.29 submenu regression. Keep each action’s MIME filter aligned with actual inputs. Follow `docs/ACTIONS.md` when editing IDs, labels, presets, and dispatcher arguments.

The dispatcher’s usage output is also maintained in `src/bin/kim_all`; every action option documented in `docs/CLI.md` must match its parser. Menu-facing dialog flags are action-local. Do not introduce a global parser rewrite.

## Runtime and capability probing

Runtime tools include Bash/core utilities, ImageMagick 7 (`magick`, `identify`), ExifTool, FFmpeg/ffprobe, KDialog and qdbus. Specific workflows need optional encoders/delegates, ICC profiles, `xdg-open`, mail clients, `intltool-merge`, or `setsid`. Actions report missing required tools and probe optional codecs before claiming support. Do not infer encoding support from an extension or silently change the requested format. See [FORMATS.md](docs/FORMATS.md).

Tests use disposable synthetic files and command adapters for controlled failure injection. Real-tool tests use small fixtures and skip only capability-dependent cases with a stated reason. Never point tests at personal media or installed KDE menu directories.

## Configuration

`load_kim_config` reads `${KIM_CONFIG_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kim_kdeimagemenu}` using `kreadconfig6`, group `<default>`. Recognized environment values override KConfig. Invalid KConfig values fall back to defaults where a key has a constrained value; invalid environment values follow that action’s validation or fallback behavior. `KIM_POLICY` is the sole output-policy variable. See [CONFIGURATION.md](docs/CONFIGURATION.md) for exact keys, defaults, and action scope.

## Safety invariants

Keep these invariants when changing actions or shared helpers:

1. Treat selected paths as untrusted input. Use arrays, `--` separators, no-follow checks where required, and explicit alias checks. Spaces and Unicode are supported; CR/LF filenames are rejected where line-based path protocols cannot represent them safely.
2. Never give a producer an original or final destination as its output path. Stage generated content on the destination filesystem with `tmp_for_target()` and validate it before publication.
3. `commit_tmp_to_target()` owns create/overwrite publication. Create mode refuses any occupied entry, including symlinks. Overwrite is explicit and fails closed if rename-only atomic replacement cannot be established. Do not add a copy/truncate fallback.
4. Publication provides atomic visibility on supported local filesystems, not crash durability and not protection from arbitrary external writers. Cooperative KIM6 publishers are serialized where the helper documents it.
5. Cleanup may remove only invocation-owned stages or child processes. A failure must preserve pre-existing targets and selected sources.
6. Use `progress_cancelled()` as the stop predicate. A disappeared D-Bus service is an interruption; failed or malformed queries stop safely with an error. Check immediately before publication and stop later batch items.
7. Validate real output bytes and semantics: producer status, decodability, format, dimensions, frame/page count, streams, timing, profiles or metadata as appropriate. A nonempty file or zero exit is not enough.
8. Preserve action-specific policies. Rotations preserve mtime; other transform and metadata actions have their documented distinctions. Do not add blanket metadata/timestamp restoration.

See [SAFETY.md](docs/SAFETY.md) for the user-facing behavior and limits.

## Shared helper responsibilities

- `collect_valid_files()` handles regular-file selections for line-record action paths. Publication and date/rename collectors apply additional canonical-path, identity and link checks.
- `tmp_for_target()` allocates an owned stage directory next to a target and returns a stage file inside it. `register_stage_dir()` and `cleanup_stages()` track ownership for cleanup.
- `commit_tmp_to_target()` publishes validated staged files in create or authorized overwrite mode. `atomic_overwrite_file()` remains as a compatibility wrapper and is covered directly by publication tests; current action flows use `tmp_for_target()` and `commit_tmp_to_target()`. Do not use the wrapper as a reason to bypass target checks.
- `progress_open()`, `progress_label()`, `progress_value()`, `progress_cancelled()`, and `progress_close()` manage owned KDialog references and D-Bus checks. The reference parser maintains separate service and object-path arguments.
- Video helpers probe with ffprobe, run monitored FFmpeg children, and terminate only the process owned by this invocation.

These helpers encode safety policy. Change a helper only for a demonstrated defect with a focused regression test and review of all callers.

## Action families

Image transformation actions generate and validate staged pixels. Most follow create or authorized overwrite policy; rotation and flip/flop explicitly replace the selected input, independent of `KIM_POLICY`. Metadata-only edits use ExifTool and verify tags, pixels, profiles, permissions and mtime. Date synchronization has separate filesystem-time and embedded-metadata directions. Web export is always derived-only and performs ICC-managed sRGB conversion by default. Video utility actions are derived-only; transcoding may overwrite only after authorization. Slideshow generation is always derived-only. Renaming is a filesystem operation with whole-batch preflight and safe no-clobber move/copy semantics; it is not an image-publication transaction.

Do not assume all images are still RGB photographs: animations, multipage images, RAW, layered files, vectors, PDFs and HDR require action-specific handling or rejection.

## Adding or changing a supported action

1. Confirm the user-visible option already exists or is approved for the current scope; feature freeze means no new processing features.
2. Identify its public dispatcher arguments, input MIME scope, output policy, naming, metadata/timestamp behavior, dependencies, cancellation points and validation requirements.
3. Add a focused regression through the public dispatcher before changing behavior. Include real-tool fixtures when they provide meaningful evidence and controlled failure adapters for dangerous cases.
4. Keep menu ID/label/argument changes synchronized with `docs/ACTIONS.md`, translations, CLI help and relevant references. Maintain selected-file argument boundaries.
5. Test failure and cancellation preservation, not only success. Confirm cleanup removes owned stages and no unrelated files.
6. Run independent accuracy and standards review for meaningful changes.

## Test and static-check workflow

Run one focused module while iterating:

```sh
python3 -B tests/run.py --pattern test_resize.py
```

Run all tests with the canonical runner:

```sh
python3 -B tests/run.py
```

Do not replace the project’s unittest workflow with generic pytest discovery. The adapters record status, streams, argument boundaries and filesystem changes. Real ImageMagick/ExifTool/FFmpeg fixtures complement—but do not get replaced by—controlled failures.

Before review, run:

```sh
bash -n src/bin/kim_all install.sh uninstall.sh
shellcheck src/bin/kim_all install.sh uninstall.sh
python3 -B -c 'import ast, pathlib; [ast.parse(p.read_text(), filename=str(p)) for p in pathlib.Path("tests").glob("*.py")]'
git --no-pager diff --check
```

KDE service menus are `Type=Service`; generic desktop-entry validation may not understand their action groups. Use the KDE-specific menu and isolated installer tests. Do not claim GUI acceptance from parsing alone.

## Installer and release checks

Use disposable prefixes for installation tests. The installer recognizes a populated runtime from the `kim_all` dispatcher, a recognized KIM menu, or an old `.kim6-owned` marker; an empty directory can also be adopted after an interrupted first install. New installs do not create markers. The uninstaller can identify the runtime from the dispatcher or a recognized KIM menu and does not require the old marker. Menus are recognized through their KIM marker or a recognized old KIM command. The installer checks known destinations and symlinks, then replaces each listed file through a temporary sibling file. There is no whole-install transaction, digest manifest, customization backup, or rollback: an interrupted upgrade can leave a mixed version, and rerunning the installer completes it. A hard kill can leave a hidden temporary sibling, which the installer does not sweep. Content at known KIM6 paths is replaced or removed; unlisted runtime data remains. Uninstall removes only the listed runtime files and leaves nonempty directories in place.

Release verification should include the canonical suite, shell/Python checks, all five KDE templates and 107 action mappings, isolated fresh/repeated/upgrade/failure/uninstall tests, installation modes, and manual review of the documentation. Do not run upgrade/uninstall tests against the live desktop. Follow actual installer options documented in [INSTALL.md](INSTALL.md).

## Contributions and translations

Contributions should include a focused test, clear reproduction details, and a description of source/destination preservation. Preserve historical author notices and GPL headers. Translation sources live in `po/`; regenerate/update catalogs only through the established gettext/intltool workflow and ensure current menu message IDs stay synchronized. Do not execute obsolete release commands copied from the [historical archive](docs/archive/upstream/ARCHIVE.md).
