# KIM6 first-run Dolphin smoke test

This quick check samples installation and representative menus. It is separate from the complete 107-action acceptance plan. A smoke-test pass is not a pass for the full plan.

Use only the disposable files under `qa/generated/cases/`. If fixtures are not ready, start with `python3 -B qa/acceptance.py prepare`. Then explicitly install the isolated copy and check that its files match this checkout:

```sh
python3 -B qa/acceptance.py install-isolated
python3 -B qa/acceptance.py check-install
```

KDE Frameworks/KIO 6.29 may prevent Dolphin service submenus from appearing. Do not modify the menus to work around this issue. Before GUI acceptance testing, verify that the test machine supports the submenus and check its KDE/Qt versions. `check-install` verifies installed files, not actual menu visibility or behavior.

For each operation below, run the `next` command to open the exact disposable case folder in the isolated Dolphin session. Select only the named file and the menu item shown by the printed instructions.

| Check | Commands | What to do and inspect |
|---|---|---|
| JPEG compression | `python3 -B qa/acceptance.py next --isolated --case-id 'kim_compress.desktop:Compress50'` | Select `photo.jpg`, choose the displayed JPEG compression submenu and `JPEG quality: 50%`. Check the resulting JPEG and confirm `photo.jpg` remains unchanged in create mode. |
| Resize | `python3 -B qa/acceptance.py next --isolated --case-id 'kim_compressandresize.desktop:Resize800'` | Select `large.jpg`, choose `Resize (800x800 pixels)`, and compare the result's framing and dimensions. Choose create mode if asked. |
| Convert | `python3 -B qa/acceptance.py next --isolated --case-id 'kim_convertandrotate.desktop:ConvertWEBP'` | Select `photo.jpg`, choose `Convert to WebP`, save in the case folder if asked, and check that the output opens as WebP. |
| Remove GPS | `python3 -B qa/acceptance.py next --isolated --case-id 'kim_publication.desktop:StripGPS'` | Select `metadata.jpg`, choose `Remove GPS coordinates…`, confirm GPS-only removal, and check that the picture still looks the same. Do not use a personal photograph. |
| Video | `python3 -B qa/acceptance.py next --isolated --case-id 'kim_compressandresizevideo.desktop:VideoThumbnail'` | Select `video-audio.mp4`, choose `Extract automatic thumbnail`, and open the resulting image. |
| Installed manual | `python3 -B qa/acceptance.py next --isolated --case-id 'kim_publication.desktop:Manual'` | Right-click the indicated harmless case image, choose the displayed Manual entry, and check that the installed manual opens with readable styling. |

After each action, inspect the result. If it was a real Dolphin interaction and it looks right, use the `pass --mode gui --policy …` command printed by `next` for that case. That command runs and displays the technical checks and records a pass only when they succeed. The six checks above do not automatically change statuses or cover the other menu actions.

To remove only the isolated KIM6 installation after testing, first close its Dolphin windows, then run:

```sh
./uninstall.sh --prefix "$PWD/qa/generated/gui-data/kio/servicemenus"
```

This uninstalls the QA copy only. It does not uninstall a normal user or system KIM6 installation. Confirm removal with `python3 -B qa/acceptance.py check-install` (it should report that the isolated copy is not installed). Keep `qa/state/` and `qa/generated/cases/` to retain acceptance progress and test results.
