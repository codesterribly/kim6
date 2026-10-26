# KIM6 Human Acceptance Testing

This toolkit prepares disposable media and records a person testing the Dolphin menus. It never clicks menus for you. A technical validation or CLI run is not a GUI acceptance result.

## Start or resume

From the repository checkout:

```sh
python3 -B qa/acceptance.py prepare
python3 -B qa/acceptance.py install-isolated
python3 -B qa/acceptance.py check-install
python3 -B qa/acceptance.py next --isolated
```

`prepare` creates pristine masters and a separate working copy for every one of the 107 current menu actions. Re-running it does not reset case results or replace changed case media. Use `next` to open the first pending case. It prints the exact file, menu label, suggested dialog choices, expected result, source behavior and technical checks. Use `next --case-id 'kim_compress.desktop:Compress50'` to reopen a particular case without changing its recorded result.

Select only the filenames printed for that case. `next --isolated` opens the case folder in Dolphin using a separate QA user data/config/cache tree. You must invoke the menu yourself. Never use personal photos or videos for destructive tests. For rotate/flip and other in-place or overwrite cases, the prepared files are disposable copies.

## Run one case

After the menu action finishes, run:

```sh
python3 -B qa/acceptance.py pass --mode gui --policy create
python3 -B qa/acceptance.py next --isolated
```

Use the policy printed in the case instructions (`create`, `derived`, `in-place` or `rename`). `pass` runs the technical checks and records the pass only if they succeed. If it reports errors, use `validate` for another detailed check after addressing the problem. Only use `--mode gui` after personally selecting the Dolphin action and inspecting the result. To record a direct command-line check, use `pass --mode cli`; it is tracked separately. Failures and environment limits need a note:

```sh
python3 -B qa/acceptance.py fail --mode gui --note 'Describe what happened'
python3 -B qa/acceptance.py skip --mode gui --reason 'Optional AV1 encoder unavailable'
python3 -B qa/acceptance.py blocked --mode gui --reason 'KDE submenu issue'
```

For a specific case, add its stable ID after the command. `status --filter pending|failed|skipped|blocked` shows focused lists. `reset CASE_ID` resets only that case and removes its saved result; it refuses unrecognized files. Do not reset a case until you have reviewed its outputs and notes.

## Isolated installation and its limits

`install-isolated` explicitly runs this checkout's installer with `--prefix qa/generated/gui-data/kio/servicemenus`, plus QA-only `XDG_CONFIG_HOME` and `XDG_CACHE_HOME`. It does not use sudo or write to normal per-user/system service-menu locations. It is still an installation command, so you choose when to run it. If it is interrupted, rerun it after checking the error; the installer is designed to be rerun. `check-install` compares the installed dispatcher, resources, permissions, menu IDs and argument contracts with this checkout. It also reports same-name service menus found in checked system XDG data roots. It does not prove that Dolphin displayed or launched an entry.

The isolated Dolphin session may still show system-wide menus. If duplicate or unidentified KIM6 entries appear, stop rather than guessing. KDE Frameworks/KIO 6.29 can prevent Dolphin service submenus from appearing. Do not flatten or alter the menus to work around it. Actual GUI acceptance should be done on a KDE Plasma 6 machine with working submenus after confirming the target environment is suitable.

## Test the first-run smoke sequence

Follow [SMOKE_TEST.md](SMOKE_TEST.md) for a short install, menu visibility and representative-action check. It is separate from the 107-case plan; passing it does not mark the full plan complete.

## Test on two machines and merge results

Each recorded result includes hostname, Git revision and dirty-tree status, available KDE/Qt versions, GUI/CLI mode and UTC time. Older results created before provenance was added show “not recorded”. Run `prepare` on both checkouts first. It creates the QA-owned `qa/transfers/` folder without changing saved results. Export and import JSON files stay there:

```sh
# On the first machine, after prepare has initialized the state:
python3 -B qa/acceptance.py export

# Copy the printed file manually into the other checkout's qa/transfers/ folder.
# On that machine:
python3 -B qa/acceptance.py import qa/transfers/acceptance-FILE.json
```

Transfer files contain test results and validator records, not fixture media. Prepare the fixtures separately on each machine. Import adds cases that are not recorded locally. If the same case has different results, import makes no changes and lists the conflict. Review both reports and explicitly choose one policy:

```sh
python3 -B qa/acceptance.py import qa/transfers/acceptance-FILE.json --resolve keep-local
python3 -B qa/acceptance.py import qa/transfers/acceptance-FILE.json --resolve use-imported
```

Those options resolve every conflicting case in that file. Export again after resolving to share the merged state. The toolkit never SSHes or copies files between machines for you.

Two records for the same case are treated as a conflict when the stored result record differs, including provenance, note, mode or timestamp. This conservative rule asks you to decide which observation should be the case's current result; each exported JSON remains available as a record of the other machine's observation.

To test the same code revision on another machine, record the full revision on the source machine with `git rev-parse HEAD`. A Git bundle contains committed files only. If the working tree is dirty and you need to test those exact edits, transfer the patch and intended untracked source files too. Review the untracked-file list first; do not include ignored `qa/generated/`, `qa/state/` or `qa/reports/` data in the source archive.

```sh
# On the source machine, from the checkout:
git bundle create ../kim6-acceptance.bundle HEAD
git diff --binary HEAD > ../kim6-working.patch
git ls-files --others --exclude-standard -z > ../kim6-untracked.list
if [ -s ../kim6-untracked.list ]; then tar --create --gzip --file ../kim6-untracked.tar.gz --null --files-from=../kim6-untracked.list; fi
```

Copy the bundle, patch, untracked archive and list to the destination machine using a removable drive or another method you choose. On that machine, after placing them at a convenient path:

```sh
git clone /path/to/kim6-acceptance.bundle kim6-acceptance
cd kim6-acceptance
git checkout --detach FULL_REVISION_FROM_SOURCE
git apply --binary /path/to/kim6-working.patch
if [ -f /path/to/kim6-untracked.tar.gz ]; then tar --extract --gzip --file /path/to/kim6-untracked.tar.gz --directory .; fi
git status --short
python3 -B qa/acceptance.py prepare
python3 -B qa/acceptance.py install-isolated
python3 -B qa/acceptance.py check-install
python3 -B qa/acceptance.py next --isolated
```

Use the actual full revision, inspect the untracked-file list and `git status --short`, and confirm that the intended source changes were applied before testing. If testing only a committed release, omit the patch/archive steps. Do not assume the destination machine has a particular KDE or Qt release; the result record captures versions when the commands are available. Copy/export progress manually as above.

## Progress and reports

```sh
python3 -B qa/acceptance.py status
python3 -B qa/acceptance.py status --filter failed
python3 -B qa/acceptance.py report
```

The HTML report is read-only and groups all cases by menu. It shows pending/passed/failed/skipped/blocked totals, GUI and CLI passes, technical checks, outputs, notes, host, revision and available KDE/Qt versions. `report` also creates a JSON result export. Use the CLI to change status; opening a dashboard cannot mark a case passed.

Progress lives in `qa/state/`, outside disposable cases, and each update is atomically saved. Do not delete that directory to reset testing. Case outputs and email attachments live under the ignored `qa/generated/` tree. Email attachments are intentionally persistent after the external mail draft opens; inspect the exact QA attachment directory and close the mail client before removing any QA-owned attachment.

## Fixtures and optional tools

Fixtures are generated synthetic images, metadata samples and short videos. Their master hashes are recorded and checked; each action gets separate working copies. No personal media is read and no photos are downloaded. ImageMagick 7 is required to prepare image fixtures. ExifTool, FFmpeg codecs, ICC profiles, PDF tools and KDE utilities depend on the host. Missing optional capabilities are shown as unavailable; record a skip or environment block with the exact reason. Technical checks inspect actual image/video data when tools exist, but cannot judge image quality or replace your visual check.

Print the second-pass safety checklist with:

```sh
python3 -B qa/acceptance.py second-pass
```

Run the focused toolkit tests with:

```sh
python3 -B tests/run.py --pattern test_acceptance_toolkit.py
```
