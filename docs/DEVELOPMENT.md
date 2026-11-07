
# KIM6 Development Guide

KIM6 is a KDE Plasma 6 Dolphin service-menu extension for image and video processing. The original collection of standalone Bash scripts has been consolidated into a single executable, `src/bin/kim_all`.

The original scripts are retained in the repository for historical reference. All current Dolphin menu actions use `kim_all`.

This document covers the project structure, development conventions, testing, and the behavior that should be preserved when modifying KIM6.

## Repository Structure

| Path | Purpose |
|---|---|
| `src/bin/kim_all` | Main executable containing image and video processing functions. |
| `src/kim_*.desktop.in` | 12 KDE Dolphin service-menu definitions containing 89 executable static actions and four visual separator entries. |
| `src/gallery/` | Templates used to generate HTML photo galleries. |
| `tests/run.py` | Test runner. |
| `tests/support.py`, `tests/adapter.py` | Shared test fixtures and helpers. |
| `tests/test_*.py` | Unit and integration tests. |
| `install.sh`, `uninstall.sh` | Installation and removal scripts. |
| `po/` | Translation files. |
| `docs/` | User documentation and HTML User Guide. |
| `docs/archive/upstream/` | Archived documentation from earlier versions. |

`README.md` provides the project overview, and `INSTALL.md` covers installation and removal.

The `docs/` directory contains additional references:

- `ACTIONS.md` - Complete Dolphin menu and action inventory.
- `commandconfig.md` - detailed descriptions of KIM6 functionality, command-line options and configuration.
- `FORMATS.md` - Supported image and video formats.
- `RECIPES.md` - The Recipes submenu, editor, step definitions, preflight and derivative-only outputs.
- `index.html` - HTML User Guide with CSS styling (`work.css`).
- `reference/` - Generated HTML pages from the Markdown sources; never edit generated pages directly.

## Recipe Architecture

The Recipes subsystem extends KIM6's Dolphin photo workflows with ordered, versioned JSON definitions and a Qt editor and runner. Files in `src/bin/` include `kim_recipe_core.py`, `kim_recipe_image.py`, `kim_recipe_dialog.py`, `kim_recipe_run.py`, and `kim_recipe_menu.py`; the shipped definitions are kept under `src/recipes/`.

The Recipes submenu has two static entries, Choose saved recipe… and Recipe editor…; only user recipes assigned to Root get direct runtime-generated Dolphin shortcuts. Built-in, Root, named folders and Unfiled are selection groups in the Qt runner/editor. The run dialog validates each selected input before allowing execution. Steps can be disabled without removing them. PSD inputs that cannot produce a valid output format raise a preflight problem instead of selecting an encoder implicitly.

**Safety contract:** Recipes publish derivatives only, never overwrite selected source images, and must guard against output filename collisions. Costly source inspection and capability probes run in workers instead of blocking the Qt GUI thread. Stale preflight results must not revive invalidated plans; repair opens the editor using a completion signal rather than nesting another editor exec() loop. Standalone editor-to-run handoffs retain their existing modal dialog behavior and selected images. Cancellation or failed publication must never be presented as success.

See [RECIPES.md](RECIPES.md) for user-facing behavior and [ACTIONS.md](ACTIONS.md) for service-menu entry points.

## Dolphin Service Menus

KIM6 uses 12 KDE service-menu definitions in `src/`, representing eight image-related and four video-related submenu categories. These menus call the `kim_all` executable with an action name, optional arguments, and the files selected in Dolphin.

For example:

```sh
kim_all compress --recommended -- %F
```

The `%F` placeholder supplies the selected file paths. The `--` separator marks the end of command options so filenames beginning with a hyphen are handled correctly.

The service-menu definitions use KDE's `Type=Service`, `X-KDE-ServiceTypes=KonqPopupMenu/Plugin`, `X-KDE-Protocol=file`, and `X-KDE-Submenu` entries.

When modifying menu actions:

- Preserve existing action IDs and command arguments unless intentionally changing their behavior.
- Use Bash arrays to handle filenames containing spaces or special characters.
- Keep MIME type restrictions appropriate for the selected action.
- Update the action reference and translations when menu labels or arguments change.

The installer replaces the `kim_all` command in each menu with the absolute path to the installed executable.

The dispatcher's command-line help is maintained in `src/bin/kim_all` and should remain consistent with the documented options.

See [ACTIONS.md](ACTIONS.md) for the complete menu definitions and [commandconfig.md](commandconfig.md) for command-line arguments.

## Embedded User Guide rendering

`src/bin/kim_settings_dialog.py` embeds the installed
`docs/index.html` using `PySide6.QtWebEngineWidgets.QWebEngineView`.
The binding is optional for general KIM6 operation but required for
the full HTML guide inside Settings/About.

For Ubuntu or Debian, the package is
`python3-pyside6.qtwebenginewidgets`. The Qt WebEngine runtime
libraries alone do not provide the Python import. `install.sh`
checks `from PySide6.QtWebEngineWidgets import QWebEngineView`
and reports the missing optional dependency.

The guide opens from a local file URL, so installed CSS, illustrations,
and reference pages must retain their relative paths. The application
keeps an external-browser action and a limited Markdown fallback.

When modifying this tab, keep the status label hidden during successful
HTML rendering and give the WebEngine widget the available vertical
space. Restore a status message only for fallback or missing-file
conditions. Do not disable HTML rendering merely because the process
has SSH environment variables.

### Service-menu executable permissions

KIM6 installs its Dolphin service-menu `.desktop` files with
permissions `0755`. Dolphin requires these files to be authorized
for execution in the supported KDE environment. Changing them to
`0644` causes authorization failures.

`install.sh` and dynamic recipe-menu generation must preserve
the installed permissions. Do not confuse executable KDE service
menus with ordinary nonexecutable desktop data files.

## Runtime Dependencies and Format Support

KIM6 uses Bash and common command-line utilities, along with:

- **ImageMagick 7:** Image processing, format conversion, galleries, and related operations.
- **ExifTool:** Metadata, timestamps, and copyright information.
- **FFmpeg and ffprobe:** Video processing and media inspection.
- **KDialog and qdbus:** KDE dialogs, progress reporting, and cancellation.

Specific operations may also require optional image encoders, format delegates, ICC profiles, `xdg-open`, email clients, or `setsid`. Installation from source uses `intltool-merge`.

KIM6 checks for required tools and probes optional format support where appropriate. An image extension alone does not guarantee that the installed ImageMagick build can read or write that format.

Missing encoders or unsupported formats should produce an error rather than silently substituting another format.

See [FORMATS.md](FORMATS.md) for details about supported formats and dependencies.

## Configuration

The user-facing entry point is **Actions → KIM6 - Settings/About → Settings** in Dolphin. `src/bin/kim_settings_dialog.py` validates and atomically writes preferences to `${XDG_CONFIG_HOME:-$HOME/.config}/kim6/settings.conf`.

`kim6_load_user_settings()` in `src/bin/kim_all` reads supported `KEY=value` data without executing the file. Persisted settings include `KIM_POLICY`, `KIM_NAME_AFFIX_POSITION`, 21 allowlisted `KIM_AFFIX_*` labels, three web-export quality values (default 95), and three copyright fields. Labels are validated as 1–32 ASCII filename-safe characters. `affixed_filename()` resolves configured labels centrally, including compound GPS/AI and timestamped video frame names. The Output Filenames Settings tab provides editable labels, previews and Restore Defaults. User-chosen output names and Rename Images are unaffected. Explicit environment variables take precedence. `KIM_WEB_FORMAT` and `KIM_WEB_COLOR_MODE` are environment-only, not saved by Settings.

`KIM_POLICY` accepts `create` or `prompt`. `choose_output_mode()` implements the Create/Overwrite choice and the second overwrite warning. `confirm_inplace_overwrite()` handles operations that require original-file modification. No setting silently authorizes replacement. See [Configuration and Defaults](commandconfig.md#configuration-and-defaults).

## File Safety and Error Handling

KIM6 processes files that may be irreplaceable. Changes to image and video actions must preserve the following behavior:

1. **File paths:** Treat selected filenames as untrusted input. Use Bash arrays and `--` separators. Check symbolic links and file aliases where appropriate. Spaces and Unicode are supported; filenames containing carriage returns or line feeds are rejected by operations that cannot safely process them.

2. **Temporary files:** Never write generated output directly to an original or final destination. Use `tmp_for_target()` to create temporary output on the destination filesystem, and validate the result before moving it into place.

3. **Publishing results:** `commit_tmp_to_target()` handles creating or overwriting output files. Create mode refuses to replace occupied paths, including symlinks. Overwriting must be explicitly authorized and use the supported atomic replacement mechanism rather than copying or truncating the destination.

4. **Atomic replacement:** On supported local filesystems, completed files are moved into place atomically. This prevents users from seeing partially written output, but it does not guarantee durability after a system crash or protect against changes made by other programs.

5. **Cleanup:** Remove only temporary files, directories, and child processes created by the current operation. Failed operations must preserve existing destination files and selected sources.

6. **Cancellation:** Use `progress_cancelled()` to detect cancellation. Missing, failed, or malformed D-Bus responses must be handled safely. Check cancellation before publishing results and before continuing with later files in a batch.

7. **Output validation:** Check that generated files contain valid results, not merely that a command returned successfully. Depending on the operation, this includes verifying format, dimensions, image frames, PDF pages, video streams, timestamps, color profiles, or metadata.

8. **Metadata and timestamps:** Preserve each action's documented behavior. Rotation preserves the original modification time; other transformations and metadata operations have their own rules. Do not apply metadata or timestamp restoration indiscriminately.

See [File Publication and Cancellation](#file-publication-and-cancellation) below for the implementation details and limitations.

## Shared Helper Functions

Several functions in `src/bin/kim_all` provide common behavior across multiple actions.

### File selection

`collect_valid_files()` validates regular-file selections for actions using line-based file lists.

Publication, date, and rename operations perform additional checks involving canonical paths, file identity, and symbolic links.

### Temporary files and publication

`tmp_for_target()` creates a temporary staging directory beside the intended destination and returns a path for generated output.

`register_stage_dir()` and `cleanup_stages()` track temporary directories created by the current operation.

`commit_tmp_to_target()` moves validated output into place using the selected create or authorized overwrite policy.

`commit_tmp_to_target()` is used for publishing validated outputs. `atomic_overwrite_file()` is also defined in the dispatcher; current actions use `tmp_for_target()` and `commit_tmp_to_target()`.

### Progress and cancellation

The following functions manage KDialog progress reporting:

- `progress_open()`
- `progress_label()`
- `progress_value()`
- `progress_cancelled()`
- `progress_close()`

They manage the dialog's D-Bus service and object-path references.

### Video processing

Video helpers inspect files using `ffprobe`, execute FFmpeg operations, monitor progress, and manage cancellation.

Process cleanup is restricted to child processes started by the current KIM6 operation.

These shared functions affect multiple actions. Changes should be tested against the operations that depend on them.

## Action Behavior

Different KIM6 actions have different file-handling requirements.

### Image transformations

Resizing, compression, and conversion generate and validate output before publishing it. Most support creating new files or explicitly authorized overwriting.

Rotation, EXIF auto-orientation, flip, and flop select Create or Overwrite through `choose_output_mode()`. Create publishes validated transformed copies. Overwrite requires explicit two-stage authorization and replaces selected originals only after validation.

### Metadata and dates

Metadata operations use ExifTool where appropriate, alongside native PNG, JPEG/WebP and GIF metadata engines and TIFF/ISOBMFF verification helpers. Result checks preserve image pixels, color profiles, permissions, and modification times where supported. Selective GPS removal targets recognized coordinate tags. Selective AI removal targets recognized IPTC AI prompt and system tags and removes `DigitalSourceType` only for recognized AI classifications. Neither selective mode guarantees removal of all related information; unrecognized generator-specific fields and signed C2PA / Content Credentials may remain.

Date synchronization supports separate operations for filesystem timestamps and embedded image metadata. Before a direct original-file mtime update, the selected source's link count, device and inode are checked to detect unexpected path replacement. The create-copy path must not explicitly restore atime on the selected original. Camera-time shifting changes wall-clock date tags, not timezone interpretation; subsecond and timezone-offset metadata follow the documented per-action contract.

### Web export

Web export always creates separate output files. By default, it uses ICC-managed conversion to sRGB for web compatibility. It refuses animated APNG rather than allowing an ImageMagick decoder to flatten the animation silently; nonanimated PNG remains supported. Conversion retains a dedicated APNG/FFmpeg path with frame and timing checks.

### Video processing

Video utilities create separate outputs. Video transcoding can replace an existing file only when authorized.

Slideshow generation always creates a separate output file.

### Renaming

Rename operations use filesystem move or copy behavior. They check the complete batch for naming conflicts before making changes and avoid unintentionally replacing existing files.

Renaming does not use the same publication mechanism as image transformations.

### Special image formats

Not every image is a single-frame RGB image. Animated images, multipage documents, RAW formats, layered files, vector graphics, PDFs, and HDR images may require different processing or may be unsupported by particular actions.

Format-specific validation is important when modifying conversion and transformation functions. In particular, ImageMagick can identify some animated APNG inputs as a single PNG frame. Conversion has a dedicated APNG/FFmpeg path, while Resize and Web Export must refuse animated APNG rather than relying on a misleading one-frame decoder result. Preserve any existing animation/ICC checks unless a targeted regression demonstrates they need changing.

## Adding or Modifying Actions

Most KIM6 functionality is implemented as action functions in `src/bin/kim_all`. Dolphin invokes these functions through the service-menu definitions in `src/`.

When adding or changing an action:

1. Identify the relevant function and its command-line arguments.
2. Check the supported input formats, output naming, and existing file-handling behavior.
3. Reuse the existing helpers for file validation, temporary files, progress reporting, and cancellation.
4. Add or update tests for the intended behavior, including error handling and preservation of existing files.
5. Update the corresponding service-menu definition, translations, CLI help, and documentation when necessary.

Test changes against temporary files rather than personal images or videos.

See [ACTIONS.md](ACTIONS.md) for the menu-action inventory and [commandconfig.md](commandconfig.md) for dispatcher arguments.

## Testing

For required tools and installation instructions, see [INSTALL.md](../INSTALL.md). Tests requiring optional image formats or video codecs may be skipped when those capabilities are unavailable.

KIM6 uses Python's `unittest` framework, with a custom test runner in `tests/run.py`.

Regression coverage includes processing functions, file preservation, error handling, cancellation, installation, output authorization, and source/destination aliases. Overwrite tests simulate both dialog confirmations using the isolated `Workspace`. The APNG validation cases use animated fixtures when FFmpeg is available.

Run an individual test module while developing:

```sh
python3 -B tests/run.py --pattern test_resize.py
```

Run the full test suite:

```sh
python3 -B tests/run.py
```

Tests use temporary directories and generated media files. Some tests run ImageMagick, ExifTool, or FFmpeg directly, while others use controlled command adapters to simulate failures.

Before submitting changes, check Bash syntax and run ShellCheck:

```sh
bash -n src/bin/kim_all install.sh uninstall.sh
shellcheck src/bin/kim_all install.sh uninstall.sh
git --no-pager diff --check
```

Installer tests should use temporary installation directories rather than modifying the active Dolphin installation.

KDE service menus use `Type=Service`, which may not be handled correctly by generic desktop-entry validators. Use the project's KDE-specific menu tests for structural validation.

Automated menu tests verify definitions and command arguments, but actual menu display and interaction should also be tested in Dolphin.

## Installation and Release Testing

The installation scripts support user, system-wide, and custom installation directories.

The installer copies the KIM6 executable, supporting resources, translations, and Dolphin service menus. Running it again updates an existing installation.

The uninstaller removes recognized KIM6-owned files and leaves unrelated files in place.

Installation updates are performed one file at a time. An interrupted installation can be completed by running `install.sh` again.

Before preparing a release:

1. Run the complete test suite and static checks.
2. Verify all 12 Dolphin service-menu definitions, 89 executable static actions, and four separator entries against the current source.
3. Test installation, upgrading, and uninstallation using temporary directories.
4. Test the menus in Dolphin on a supported KDE Plasma system.
5. Review the installation instructions and user documentation.

See [INSTALL.md](../INSTALL.md) for installation options.

## Contributions and Translations

Contributions should include a description of the change, relevant tests, and enough information to reproduce any bugs being fixed.

Changes to file-processing operations should explain how existing source and destination files are preserved, particularly when error handling or overwriting is involved.

Preserve historical author notices and GPL license headers.

Translations are maintained in `po/` using gettext and intltool. When changing menu labels or other translated text, update the relevant translation sources and keep message identifiers consistent.

For the project's origins and earlier contributors, see [Project history](../README.md#project-history). More detailed upstream material remains in the source repository under `docs/archive/upstream/` and is not bundled with the offline User Guide.

## File Publication and Cancellation

### Staging and publication

Generated media is first written to invocation-owned staging on the destination filesystem. The action checks the producer result and validates the staged artifact before publication. Create-new publication uses a no-clobber operation. Authorized replacement uses atomic replacement on supported local Linux filesystems. A failed rename is not followed by a destructive copy-over fallback.

This provides atomic visibility for supported local filesystem operations; it is not a promise of crash durability. Directory-entry and file contents are not necessarily forced to stable storage. KIM6’s cooperative locking does not protect against every unrelated external writer. A non-cooperating program can still race with an operation or alter a target after it is published.

Destination symlinks and ambiguous source/destination aliases are rejected where following them could change the object being processed. Safely resolved symlinked parent directories are allowed. Hard-linked selected files are rejected for in-place operations where modifying their shared inode could alter another name. Derived publication rejects source aliases. Gallery publication uses a new directory name and does not recursively replace an occupied directory.

Cleanup removes only staging files, directories and child processes owned by the current invocation. A producer failure, invalid result, cancellation or publication failure must not delete a pre-existing destination. Earlier completed batch results remain in place if a later item fails. Error and summary dialogs identify failed items rather than claiming a rejected output succeeded.

### Cancellation and process ownership

KDialog progress calls use the shared service/object reference parser. An explicit `wasCancelled=true` stops work. Explicit false permits work to continue. If the progress service disappears, the action treats that as an interruption and stops without claiming that disappearance proves the user clicked Cancel. A failed ownership query, failed method call while the service remains, or malformed reply is an error and also stops publication safely.

Actions check for interruption before starting items and immediately before publishing staged output. Video producers run as invocation-owned FFmpeg processes; cancellation terminates only the owned producer, with bounded graceful termination and a forced stop if needed. Previously published batch outputs are retained.

A KDE service-menu action accepts local files. Remote URL workflows are not silently treated as local pathnames; menu definitions restrict applicable selections to files. Newlines and certain ImageMagick filename metacharacters are rejected in actions whose current path or command syntax cannot represent them unambiguously. Spaces and Unicode are supported through quoted argument arrays and the selected-file argument boundary. Leading dashes are passed after `--` where the action supports that contract.

## Reporting a Bug

Include the KIM6 version or commit, distribution/KDE and tool versions, exact action/options, a small synthetic or safely redacted sample when possible, expected and actual behavior, and the reported error. State whether the failure is repeatable. Never attach private images or videos without permission.

## Installer Safety and Recovery

The installer identifies KIM6 installations using the dispatcher and recognized service menus. It refuses unrelated files with conflicting menu names and symlinked runtime or menu paths. Listed files are installed using temporary sibling files rather than broad filename globs. Unknown runtime files are preserved and prevent removal of their parent directory. Interrupted installations can be recovered by rerunning the installer.

Installation is not a whole-tree transaction. There is no digest manifest, customization recovery copy, or automatic rollback. If interrupted, files already replaced stay replaced; rerunning the installer completes the remaining files. A hard kill or power loss can leave a hidden temporary sibling, which the installer does not glob-delete. Content at a known KIM6 path is replaced on upgrade and removed on uninstall, so copy out any edits first. Each individual replacement uses a temporary sibling file, but the runtime and menus can temporarily contain files from different releases. Uninstall is likewise rerunnable but not transactional.

## Local Smoke Test

Test web export with a synthetic JPEG rather than a personal image. Run from the repository root:

```sh
work=$(mktemp -d)
mkdir -- "$work/output"

magick -size 640x480 xc:gray80 "$work/input.jpg"

KIM_POLICY=create ./src/bin/kim_all webexport \
  --output-dir "$work/output" \
  --size 600x600 \
  --quality 75 \
  -- "$work/input.jpg"

find "$work/output" -maxdepth 1 -type f -print
```

Check the output before removing the temporary directory. The original synthetic image is not overwritten. This test requires ImageMagick and the normal KIM6 runtime dependencies.

See [Command and Configuration Reference](commandconfig.md) for additional options.

## Documentation screenshot assets

Approved, individually anonymized application screenshots are
stored in `docs/images/screenshots/`.

The User Guide places these images alongside the relevant
workflow instructions.

Screenshots must accurately depict KDE Plasma/Dolphin and KIM6.
Preserve actual application controls, image previews, and maps.
Remove identifying usernames, hostnames, personal paths, and
identifying filenames before publication.

Do not replace real image or map content with generic placeholders,
and do not combine individual dialogs into screenshot montages.

Preserve approved screenshots without recompression or resizing.
Use descriptive alt text, task-oriented captions, and links to
the full-resolution images.

The generated HTML reference pages are built from Markdown sources.
Regenerate them after documentation changes.

## Building the offline HTML User Guide

Markdown is the authoritative documentation source. The illustrated
landing page is maintained in `docs/index.html`, and the reference
pages under `docs/reference/` are generated from Markdown.

Pandoc is required to build the reference pages, but is not required
for users viewing the installed User Guide.

During a normal non-root installation from a writable checkout,
`./install.sh` automatically regenerates the HTML reference pages when
Python 3 and Pandoc are available. This happens before the files are
installed, so a separate documentation build command is not normally
necessary.

If both tools are available but the installer is running as root or the
reference directory is not writable, the installer checks the generated
pages without modifying the checkout. Stale pages cause installation
to stop with an error.

If Python 3 or Pandoc is unavailable, installation uses the generated
HTML already included in the repository. Release builds must therefore
include current generated pages.

The landing page (`docs/index.html`) is intentionally maintained by hand.
Automatic regeneration covers the Markdown-derived reference pages, not
the landing page's examples, illustrations, or layout.


After editing Markdown, run:

    python3 tools/build_manual.py

Check that the generated reference pages are up to date:

    python3 tools/build_manual.py --check

Run the documentation tests:

    python3 -B tests/run.py --pattern test_documentation.py

Commit generated HTML alongside its Markdown source changes.
Do not edit `docs/reference/` directly.

The landing page, stylesheet and illustrations are maintained
separately. Their content and presentation must be reviewed when
corresponding user-facing functionality changes.

## Deferred Enhancements

The following improvements are planned for future development. They are not implemented in the current release.

### Format-aware Dolphin menu filtering

Investigate hiding redundant or inapplicable conversion actions according to the selected image format. For example, **Convert to JPEG** would normally be unnecessary when only JPEG images are selected.

The design must account for KDE service-menu MIME filtering, mixed-format batch selections, and situations where same-format re-encoding remains useful. Runtime format and encoder validation must remain in place regardless of menu visibility.

### Translation infrastructure and localization

KIM6 currently ships with English source strings only. The seven
obsolete translation catalogs were retired after the English interface
and Dolphin service menus changed substantially.

The gettext infrastructure remains available for future localization.
The current `po/kim6.pot` template was rebuilt from the active unified
dispatcher, active Python source files, and all 12 Dolphin menu
templates. Archived scripts and historical documents were excluded.

To regenerate the template after additional English UI changes:

1. Extract `gettext` strings from `src/bin/kim_all` with GNU
   `xgettext --language=Shell --keyword=gettext`.
2. Extract explicitly marked translation strings from active
   `src/bin/*.py` files with `xgettext --language=Python`.
3. Extract the `_Name` and `_X-KDE-Submenu` values from all 12
   `src/kim_*.desktop.in` templates and include them as gettext
   source strings.
4. Merge the extraction results using `msgcat --use-first
   --sort-output` and write the result to `po/kim6.pot`.
5. Validate the template using `msgfmt --check` and verify that
   no archived sources are included.

Future language catalogs can be created from this template.
Do not reuse the retired catalogs as translations for the
current application.

Not every Python dialog string currently has a translation marker.
Full graphical-interface localization remains future work.
English source strings are used as the fallback without overriding
the user's system locale settings.

File-safety warnings, destructive-operation confirmations,
placeholders, filenames, and command terminology require
particular care when new translations are prepared.
