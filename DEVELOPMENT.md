
# KIM6 Development Guide

KIM6 is a KDE Plasma 6 Dolphin service-menu extension for image and video processing. The original collection of standalone Bash scripts has been consolidated into a single executable, `src/bin/kim_all`.

The original scripts are retained in the repository for historical reference. All current Dolphin menu actions use `kim_all`.

This document covers the project structure, development conventions, testing, and the behavior that should be preserved when modifying KIM6.

## Repository Structure

| Path | Purpose |
|---|---|
| `src/bin/kim_all` | Main executable containing image and video processing functions. |
| `src/kim_*.desktop.in` | Five KDE Dolphin service-menu definitions containing 107 actions. |
| `src/gallery/` | Templates used to generate HTML photo galleries. |
| `tests/run.py` | Test runner. |
| `tests/support.py`, `tests/adapter.py` | Shared test fixtures and helpers. |
| `tests/test_*.py` | Unit and integration tests. |
| `install.sh`, `uninstall.sh` | Installation and removal scripts. |
| `po/` | Translation files. |
| `docs/` | User documentation and HTML manual. |
| `docs/archive/upstream/` | Archived documentation from earlier versions. |

`README.md` provides the project overview, and `INSTALL.md` covers installation and removal.

The `docs/` directory contains additional references:

- `ACTIONS.md` — Complete Dolphin menu and action inventory.
- `CLI.md` — Command-line options and dispatcher arguments.
- `FEATURES.md` — Detailed descriptions of KIM6 functionality.
- `FORMATS.md` — Supported image and video formats.
- `CONFIGURATION.md` — Configuration options and defaults.
- `SAFETY.md` — File handling, preservation, and overwrite behavior.
- `index.html` — HTML user manual.

## Dolphin Service Menus

KIM6 uses five KDE service-menu definitions in `src/`. These menus call the `kim_all` executable with an action name, optional arguments, and the files selected in Dolphin.

For example:

```sh
kim_all compress --quality 70 -- %F
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

See [ACTIONS.md](docs/ACTIONS.md) for the complete menu definitions and [CLI.md](docs/CLI.md) for command-line arguments.

## Runtime Dependencies and Format Support

KIM6 uses Bash and common command-line utilities, along with:

- **ImageMagick 7:** Image processing, format conversion, galleries, and related operations.
- **ExifTool:** Metadata, timestamps, and copyright information.
- **FFmpeg and ffprobe:** Video processing and media inspection.
- **KDialog and qdbus:** KDE dialogs, progress reporting, and cancellation.

Specific operations may also require optional image encoders, format delegates, ICC profiles, `xdg-open`, email clients, or `setsid`. Installation from source uses `intltool-merge`.

KIM6 checks for required tools and probes optional format support where appropriate. An image extension alone does not guarantee that the installed ImageMagick build can read or write that format.

Missing encoders or unsupported formats should produce an error rather than silently substituting another format.

See [FORMATS.md](docs/FORMATS.md) for details about supported formats and dependencies.

## Configuration

`load_kim_config` reads configuration from:

```sh
${KIM_CONFIG_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/kim_kdeimagemenu}
```

Configuration is read using `kreadconfig6`, from the `<default>` group.

Recognized environment variables take precedence over their corresponding KConfig values.

Invalid KConfig values fall back to defaults where a setting has a constrained value. Invalid environment values follow the validation or fallback behavior of the corresponding action.

`KIM_POLICY` is the output-policy setting.

See [CONFIGURATION.md](docs/CONFIGURATION.md) for the available keys, defaults, and affected actions.

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

See [SAFETY.md](docs/SAFETY.md) for the user-facing explanation of file handling and its limitations.

## Shared Helper Functions

Several functions in `src/bin/kim_all` provide common behavior across multiple actions.

### File selection

`collect_valid_files()` validates regular-file selections for actions using line-based file lists.

Publication, date, and rename operations perform additional checks involving canonical paths, file identity, and symbolic links.

### Temporary files and publication

`tmp_for_target()` creates a temporary staging directory beside the intended destination and returns a path for generated output.

`register_stage_dir()` and `cleanup_stages()` track temporary directories created by the current operation.

`commit_tmp_to_target()` moves validated output into place using the selected create or authorized overwrite policy.

`atomic_overwrite_file()` remains available as a compatibility wrapper, although current actions use `tmp_for_target()` and `commit_tmp_to_target()`.

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

Rotation and flip/flop operations replace the selected image after validation, independently of `KIM_POLICY`.

### Metadata and dates

Metadata-only operations use ExifTool and verify the resulting metadata while preserving image pixels, color profiles, permissions, and modification times as appropriate.

Date synchronization supports separate operations for filesystem timestamps and embedded image metadata.

### Web export

Web export always creates separate output files. By default, it uses ICC-managed conversion to sRGB for web compatibility.

### Video processing

Video utilities create separate outputs. Video transcoding can replace an existing file only when authorized.

Slideshow generation always creates a separate output file.

### Renaming

Rename operations use filesystem move or copy behavior. They check the complete batch for naming conflicts before making changes and avoid unintentionally replacing existing files.

Renaming does not use the same publication mechanism as image transformations.

### Special image formats

Not every image is a single-frame RGB photograph. Animated images, multipage documents, RAW formats, layered files, vector graphics, PDFs, and HDR images may require different processing or may be unsupported by particular actions.

Format-specific validation is important when modifying conversion and transformation functions.

## Adding or Modifying Actions

Most KIM6 functionality is implemented as action functions in `src/bin/kim_all`. Dolphin invokes these functions through the service-menu definitions in `src/`.

When adding or changing an action:

1. Identify the relevant function and its command-line arguments.
2. Check the supported input formats, output naming, and existing file-handling behavior.
3. Reuse the existing helpers for file validation, temporary files, progress reporting, and cancellation.
4. Add or update tests for the intended behavior, including error handling and preservation of existing files.
5. Update the corresponding service-menu definition, translations, CLI help, and documentation when necessary.

Test changes against temporary files rather than personal photographs or videos.

See [ACTIONS.md](docs/ACTIONS.md) for the menu-action inventory and [CLI.md](docs/CLI.md) for dispatcher arguments.

## Testing

For required tools and installation instructions, see [INSTALL.md](INSTALL.md). Tests requiring optional image formats or video codecs may be skipped when those capabilities are unavailable.

KIM6 uses Python's `unittest` framework, with a custom test runner in `tests/run.py`.

Tests cover individual processing functions, file preservation, error handling, cancellation, and installer behavior.

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

The uninstaller removes recognized KIM6 files without deleting unrelated files. Existing installations from older versions are also supported where their files can be identified.

Installation updates are performed one file at a time. An interrupted installation can be completed by running `install.sh` again.

Before preparing a release:

1. Run the complete test suite and static checks.
2. Verify all five Dolphin service menus and their 107 action mappings.
3. Test installation, upgrading, and uninstallation using temporary directories.
4. Test the menus in Dolphin on a supported KDE Plasma system.
5. Review the installation instructions and user documentation.

See [INSTALL.md](INSTALL.md) for installation options.

## Contributions and Translations

Contributions should include a description of the change, relevant tests, and enough information to reproduce any bugs being fixed.

Changes to file-processing operations should explain how existing source and destination files are preserved, particularly when error handling or overwriting is involved.

Preserve historical author notices and GPL license headers.

Translations are maintained in `po/` using gettext and intltool. When changing menu labels or other translated text, update the relevant translation sources and keep message identifiers consistent.

Historical development and release documentation is preserved in the [upstream archive](docs/archive/upstream/ARCHIVE.md).
