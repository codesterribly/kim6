# KIM6 human acceptance toolkit

This toolkit prepares disposable fixtures and tracks a person testing every action from Dolphin. The action list is generated from the five checked-in `src/kim_*.desktop.in` templates; run `python3 qa/acceptance.py inventory` to refresh `qa/ACCEPTANCE_PLAN.md`. The plan and progress distinguish technical validation, CLI checks, and actual Dolphin GUI acceptance. No command automates menu clicks.

## Start or resume

From the repository checkout:

```sh
python3 qa/acceptance.py prepare
python3 qa/acceptance.py install-isolated
python3 qa/acceptance.py check-install
python3 qa/acceptance.py status
python3 qa/acceptance.py next --isolated
```

`prepare` creates `qa/generated/masters/` and a separate `qa/generated/cases/` copy for each menu action. It also initializes crash-safe progress in `qa/state/progress.json`. Existing owned cases and saved results are kept on later `prepare` runs; generated `INSTRUCTIONS.txt` files are refreshed from current menu templates, so record notes with the CLI rather than editing those files. Each case contains the exact file names to select. For rotate/flip cases the instruction includes a warning that the action changes only the disposable copy.

`next --isolated` opens the case directory in Dolphin if Dolphin is installed. Right-click the named file(s), choose the menu and label printed by the command, and perform the operation. For save/destination prompts, choose that case directory. Never select files outside `qa/generated/cases/`.

## Test menus from a revision-matched isolated install

The toolkit never changes the live KIM6 installation by itself. When you choose to test the checked-out revision, run:

```sh
python3 qa/acceptance.py install-isolated
python3 qa/acceptance.py check-install
python3 qa/acceptance.py next --isolated
```

The first command explicitly installs into `qa/generated/gui-data/kio/servicemenus/kim6`, with configuration and KDE cache paths under `qa/generated/`. The installer is run with that isolated XDG environment; it does not install into the normal per-user or system service-menu directories. `check-install` compares the installed `kim_all` bytes, required resources, action IDs, permissions and all five menu argument contracts with this checkout. It proves the files match, not that Dolphin displayed or launched them.

`next --isolated` starts Dolphin with a QA-only D-Bus session and QA XDG user-data/config/cache homes. It also restricts `XDG_DATA_DIRS` to `/usr/share` instead of inheriting local custom paths. System-wide service menus under `/usr/share` can still appear. Use only the matching KIM6 menu contract verified by `check-install`; if duplicate or unidentified KIM menus appear, stop rather than guessing. This keeps KIM6 email attachments and user app data inside the ignored QA workspace, but it does not isolate system-wide resources. If Dolphin is already open or this setup is unavailable, open the printed case path manually and follow the isolated-install checklist below. Do not run an in-place action against the normal home Dolphin session while testing.

For testing on another KDE Plasma 6 host such as `homebase`, copy or clone the same repository revision there, then run the commands above on that host. The toolkit does not SSH to another machine. Before GUI testing, verify `git rev-parse HEAD`, `git status --short`, `check-install`, and that installed menus invoke the isolated installed `kim_all`. The KIO 6.29 submenu issue on `natacha` is recorded as a KDE block, not a KIM6 GUI pass; do not flatten or alter menus to work around it.

## Validate and record

After invoking an action manually:

```sh
python3 qa/acceptance.py validate
python3 qa/acceptance.py pass --mode gui --policy create
python3 qa/acceptance.py next --isolated
```

For an authorized overwrite, use `--policy overwrite`; for the in-place rotate/flip cases, use `--policy in-place`; for a rename case, use `--policy rename`. The case instructions print the recommended value. `pass` runs validation again and refuses to record a pass if technical errors remain. Record a direct command-line check with `--mode cli`; it remains separate from GUI verification.

To record a failure or a legitimate skip/block, provide a note or reason:

```sh
python3 qa/acceptance.py fail --note "Describe what happened"
python3 qa/acceptance.py skip --reason "Optional encoder unavailable: libjxl"
python3 qa/acceptance.py blocked --reason "KDE submenu issue"
```

You can also name a case explicitly, for example `python3 qa/acceptance.py validate 'kim_compress.desktop:Compress10'`. The current case is used when the ID is omitted. The six About/License/Manual entries appear in their respective image/video context menus; their selected file only opens that context menu and is not sent to the dispatcher.

## Results, dashboard and reset

Progress is stored outside disposable media in `qa/state/progress.json`; each write is atomically replaced and synced. It survives closing the terminal or reboot. Inspect progress with:

```sh
python3 qa/acceptance.py status --filter pending
python3 qa/acceptance.py status --filter failed
python3 qa/acceptance.py status --filter skipped
python3 qa/acceptance.py status --filter blocked
python3 qa/acceptance.py report
```

`report` writes a timestamped, read-only HTML dashboard and JSON summary under ignored `qa/reports/`. The dashboard groups all actions by menu, links to case instructions and files, and labels GUI versus CLI verification. Record results through the CLI; opening the HTML does not update progress.

Reset only one case after reviewing its results:

```sh
python3 qa/acceptance.py reset 'kim_compress.desktop:Compress10'
python3 qa/acceptance.py prepare
```

Reset removes only that case directory and its saved result. It refuses unknown files rather than deleting them. If an output is not recognized, run `validate` first so known action outputs can be recorded; inspect anything still reported as untracked manually. Pristine masters and other case results are retained. Email attachments are deliberately left in the isolated persistent attachment area on reset: first close the external mail client, then decide whether to remove those specific QA-generated files. This avoids deleting attachments that an asynchronous client may still be reading. The tool refuses symlink escapes and unmarked existing workspaces; do not remove a workspace to recover it.

## Fixture library and optional tools

Fixtures are synthetic: solid-color and geometric photographs, transparent and multi-frame images, EXIF/GPS/rights/AI sample fields where ExifTool is available, sRGB/wide-gamut profile samples where local ICC profiles exist, and short FFmpeg videos with sound, without sound, and multiple audio streams when suitable encoders exist. Names include spaces, Unicode, brackets and a leading dash. `qa/generated/masters/manifest.json` records master SHA-256 hashes and generation capabilities. Every action receives private working copies. No personal media is read, and no copyrighted sample images are downloaded.

ImageMagick 7 is required to prepare the image fixture library. ExifTool, FFmpeg, codecs, ICC profiles, PDF inspection tools, Dolphin and KDE utilities are capability-dependent. The `prepare` summary reports fixture capabilities; unavailable fixtures or encoders are not counted as passed. Record a case as skipped when an optional codec is unavailable, or blocked when the host/KDE environment prevents GUI testing. Technical checks use installed tools such as ImageMagick, ExifTool, FFmpeg/ffprobe and `pdfinfo` when available. They check file integrity, source hashes, formats, dimensions, frames, streams and relevant metadata. They cannot judge subjective visual quality.

## Second-pass safety checks

Print the focused manual checklist with:

```sh
python3 qa/acceptance.py second-pass
```

It covers cancellation, overwrite authorization, collisions, source protection, metadata/color behavior, date handling, animation, video stream copy, slideshow order, partial batch failures, missing tools, and installer/uninstaller checks in isolated directories. Never use personal media or the active installed menus for destructive tests. The installed HTML manual should be opened from the isolated installation when checking its stylesheet.

## Canonical toolkit tests

```sh
python3 -B -m unittest tests.test_acceptance_toolkit -v
python3 -B tests/run.py
```

The toolkit tests validate inventory parity, fixture mapping, workspace/reset safety, persisted status, technical validators, optional tool handling, report totals, and separation of GUI from CLI results. The project’s canonical runner remains `tests/run.py`.
