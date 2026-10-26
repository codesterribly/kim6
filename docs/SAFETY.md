# Safety, preservation and troubleshooting

KIM6 is designed to create useful derivatives from Dolphin. Some actions explicitly replace a selected original after the user authorizes that operation. The behavior is action-specific; `KIM_POLICY` does not turn every action into an overwrite operation. See [Actions](ACTIONS.md), [Configuration](CONFIGURATION.md), and [Formats](FORMATS.md).

## What happens to the selected files

| Action family | Source behavior | Filesystem timestamp / metadata behavior |
|---|---|---|
| Compression, conversion, resize, strip metadata, copyright, time shift, datesync, rotation and flips | Follow the action’s create/authorized-overwrite policy. Rotation and flip/flop are explicitly in-place operations. | Image transforms have action-specific metadata behavior. Rotation preserves nanosecond mtime; flip/flop receives a fresh mtime. Stripmeta and metadata edits preserve source mtime when replacing. Datesync deliberately changes the filesystem mtime only in EXIF-to-filesystem mode. |
| Web export, email preparation, video utilities, slideshow, album, print, TIFF join, animation, gallery and collage | Derived artifacts only. A configured `KIM_POLICY=overwrite` does not authorize replacing selected inputs. | Derivative metadata follows each action’s documented policy. Email attachments are retained in a persistent user data location after a successful asynchronous handoff. |
| Rename | A true rename/move or copy follows the selected rename mode. The complete batch is preflighted for conflicts and aliases. | True moves preserve file bytes and appropriate filesystem metadata. Cross-filesystem copies preserve content and supported metadata before safe publication. |

For actions that support both modes, unset `KIM_POLICY` leaves the normal create/overwrite choice to the action dialog. `create` uses collision-safe names; it must not replace occupied files, directories, symlinks or dangling symlinks. `overwrite` authorizes replacement only where that action explicitly supports it and only for the destination shown/selected by that workflow.

## Staging and publication

Generated media is first written to invocation-owned staging on the destination filesystem. The action checks the producer result and validates the staged artifact before publication. Create-new publication uses a no-clobber operation. Authorized replacement uses atomic replacement on supported local Linux filesystems. A failed rename is not followed by a destructive copy-over fallback.

This provides atomic visibility for supported local filesystem operations; it is not a promise of crash durability. Directory-entry and file contents are not necessarily forced to stable storage. KIM6’s cooperative locking does not protect against every unrelated external writer. A non-cooperating program can still race with an operation or alter a target after it is published.

Destination symlinks and ambiguous source/destination aliases are rejected where following them could change the object being processed. Safely resolved symlinked parent directories are allowed. Hard-linked selected files are rejected for in-place operations where modifying their shared inode could alter another name. Derived publication rejects source aliases. Gallery publication uses a new directory name and does not recursively replace an occupied directory.

Cleanup removes only staging files, directories and child processes owned by the current invocation. A producer failure, invalid result, cancellation or publication failure must not delete a pre-existing destination. Earlier completed batch results remain in place if a later item fails. Error and summary dialogs identify failed items rather than claiming a rejected output succeeded.

## Cancellation and process ownership

KDialog progress calls use the shared service/object reference parser. An explicit `wasCancelled=true` stops work. Explicit false permits work to continue. If the progress service disappears, the action treats that as an interruption and stops without claiming that disappearance proves the user clicked Cancel. A failed ownership query, failed method call while the service remains, or malformed reply is an error and also stops publication safely.

Actions check for interruption before starting items and immediately before publishing staged output. Video producers run as invocation-owned FFmpeg processes; cancellation terminates only the owned producer, with bounded graceful termination and a forced stop if needed. Previously published batch outputs are retained.

A KDE service-menu action accepts local files. Remote URL workflows are not silently treated as local pathnames; menu definitions restrict applicable selections to files. Newlines and certain ImageMagick filename metacharacters are rejected in actions whose current path or command syntax cannot represent them unambiguously. Spaces and Unicode are supported through quoted argument arrays and the selected-file argument boundary. Leading dashes are passed after `--` where the action supports that contract.

## Metadata, color and time

Metadata policy is not global:

- `stripmeta --mode all` requests the established full removal behavior; `--mode gps` targets supported location fields; optional AI metadata removal is best-effort and does not prove that an image is no longer identifiable as AI-generated.
- C2PA/Content Credentials are structured or signed provenance records. KIM6 does not promise their complete removal; see the action result and [Feature reference](FEATURES.md).
- Copyright, timestamp shifting and file-to-EXIF date synchronization are metadata edits. They preserve image pixels and filesystem mtime where the action’s contract says so.
- EXIF-to-filesystem date synchronization changes filesystem modification time from the camera capture time, which may have no timezone. KIM6 does not reinterpret that local capture value as UTC.
- Web export defaults to an ICC transform to sRGB. Preserve-profile mode retains a usable embedded profile when the selected encoder supports it. Untagged RGB is treated as sRGB; ambiguous untagged CMYK is not silently guessed.
- Image and video transformations have their own rules for orientation, profile handling, metadata and timestamps. No blanket timestamp or metadata restoration is applied.

See [Formats](FORMATS.md) for delegate-dependent behavior and unsupported round trips.

## Common problems

### A format or codec is unavailable

ImageMagick coders and FFmpeg encoders depend on how the distribution built those tools and which delegates are installed. KIM6 probes the requested operation and fails clearly instead of silently changing the output format or codec. Inspect `magick -list format` and `ffmpeg -hide_banner -encoders`; see [Formats](FORMATS.md).

### Dolphin does not show an action

First verify that all five KIM6 service-menu templates were installed to a KDE service-menu directory and that the installed menu files contain the expected `kim_all` command. Confirm that the action’s MIME filter matches the selected local file. KDE may require a logout/login or menu-cache refresh. On the development system, KDE Frameworks/KIO 6.29 has a known upstream `X-KDE-Submenu` issue; KIM6 keeps its submenus intact and does not recommend flattening them as a workaround. Installation can be verified without relying on submenu display; see [Install](../INSTALL.md).

### Installation or removal reports a conflict

The installer records owned files and checks their content before replacing or removing them. A customized or unrecognized file is preserved and may require a deliberate manual review. Do not use broad `rm` globs in KDE service-menu directories. Review the installer message, check file ownership and permissions, and rerun the supported install/uninstall command after resolving the specific conflict. The installer uses staging and rollback where its tested workflow allows; it cannot reverse unrelated changes made concurrently by other software.

### An action fails or a batch is incomplete

The final dialog reports failed items. Confirm that the source is readable, the destination is writable and the selected format/delegate is available. Check ImageMagick/FFmpeg diagnostics in the action’s error dialog or the terminal when running a controlled CLI example. Do not diagnose a failure by testing an overwrite against an important original.

A safe smoke test uses a disposable copy and an empty temporary output directory:

```sh
work=$(mktemp -d)
cp -- ./example.jpg "$work/input.jpg"
mkdir -- "$work/output"
KIM_POLICY=create kim_all webexport --size 600x600 --quality 75 -- "$work/input.jpg"
```

Web export is derived-only and may choose its configured destination; check the action’s output report. For deterministic isolated testing, follow the exact action CLI help and use an action with an explicit output path. Remove only the test-owned `$work` directory after verifying that it contains no needed files.

### Reporting a bug

Include the KIM6 version or commit, distribution/KDE and tool versions, exact action/options, a small synthetic or safely redacted sample when possible, expected and actual behavior, and the reported error. State whether the failure is repeatable. Never attach private photographs or videos without permission.
