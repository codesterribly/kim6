"""Contract tests for the installed unified Dolphin entry point."""
from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from support import Workspace


ROOT = Path(__file__).resolve().parents[1]
MENU_TEMPLATES = sorted((ROOT / "src").glob("kim_*.desktop.in"))


def action_entries(path):
    text = path.read_text(encoding="utf-8")
    entries = []
    for section in re.split(r"\n(?=\[Desktop Action )", text):
        if section.startswith("[Desktop Action "):
            action_id = section.split("]", 1)[0][len("[Desktop Action "):]
            exec_line = next((line[5:] for line in section.splitlines() if line.startswith("Exec=")), "")
            name_line = next((line for line in section.splitlines() if line.startswith(("Name=", "_Name="))), "")
            entries.append((action_id, exec_line, name_line))
    return entries


class MenuContractTests(unittest.TestCase):
    def test_each_menu_action_uses_unified_dispatcher_and_local_argument_boundary(self):
        self.assertEqual(5, len(MENU_TEMPLATES))
        entries = [entry for path in MENU_TEMPLATES for entry in action_entries(path)]
        self.assertGreater(len(entries), 60)
        for path in MENU_TEMPLATES:
            text = path.read_text(encoding="utf-8")
            declared = next(line.split("=", 1)[1].rstrip(";").split(";") for line in text.splitlines()
                            if line.startswith("Actions="))
            defined = [action_id for action_id, _, _ in action_entries(path)]
            # Actions= determines menu order; group order may differ.
            self.assertCountEqual(declared, defined, f"{path.name}: declared IDs must match action groups")
            self.assertEqual(len(defined), len(set(defined)), f"{path.name}: duplicate action IDs")
        for action_id, command, label in entries:
            with self.subTest(action=action_id):
                self.assertTrue(command, f"{action_id} has no Exec")
                self.assertRegex(command, r"(?:^|/)kim_all(?:\s|$)", command)
                self.assertNotRegex(command, r"\bkim_(?!all\b)[A-Za-z0-9_]*", command)
                executable = shlex.split(command)[0]
                self.assertTrue(executable == "kim_all" or executable.endswith("/kim_all"), command)
                if action_id not in {"Manual", "License", "About"}:
                    self.assertIn("-- %F", command)
                else:
                    self.assertNotIn("%F", command)
                self.assertTrue(label, f"{action_id} has no display label")

    def test_supported_menu_capabilities_and_presets_are_represented(self):
        entries = [entry for path in MENU_TEMPLATES for entry in action_entries(path)]
        commands = [command for _, command, _ in entries]
        self.assertEqual(108, len(entries))
        dispatcher = (ROOT / "src/bin/kim_all").read_text()
        self.assertNotRegex(dispatcher, r"action_[A-Za-z0-9_]+\(\)\s*\{\s*:\s*;\s*\}")
        routes = set(re.findall(r'^\s{4}([a-z][a-z0-9]*)\)\s+[^;]*;', dispatcher, re.M))
        for action_id, command, _ in entries:
            if action_id in {"Manual", "License", "About"}:
                continue
            argv = shlex.split(command)
            self.assertGreaterEqual(len(argv), 2, action_id)
            self.assertIn(argv[1], routes, f"{action_id}: no dispatcher route for {argv[1]}")
            self.assertIn("%F", argv)
            self.assertEqual(argv[-1], "%F")
            self.assertNotRegex(command, r"`|\$\(|\$[A-Za-z_{]")
        legacy_video = {command for command in commands
                        if command.startswith("kim_all video ") and "--crf " in command}
        self.assertEqual(24, len(legacy_video))
        metadata_commands = {action_id: command for action_id, command, _ in entries}
        self.assertEqual("kim_all stripmeta --mode gps -- %F", metadata_commands["StripGPS"])
        self.assertEqual("kim_all stripmeta --mode ai -- %F", metadata_commands["RemoveAIMetadata"])
        self.assertEqual("kim_all copyright --interactive -- %F", metadata_commands["SetCopyright"])
        self.assertEqual("kim_all timeshift --interactive -- %F", metadata_commands["AdjustCaptureTime"])
        self.assertEqual("kim_all datesync --interactive -- %F", metadata_commands["DateSync"])
        self.assertEqual("kim_all slideshow --interactive -- %F", metadata_commands["Slideshow"])
        self.assertEqual("kim_all resize --custom-percent -- %F",
                         dict((action_id, command) for action_id, command, _ in entries)["ResizePercent"])
        expected_video = {
            f"kim_all video --size {size} --crf {crf} --codec {codec} --container {container} -- %F"
            for size in ("hd720", "hd1080") for crf in (17, 23, 29)
            for codec in ("libx264", "libx265") for container in ("orig", "mp4")
        }
        self.assertEqual(expected_video, legacy_video)
        av1_commands = {command for command in commands if "--codec av1" in command}
        self.assertEqual({
            "kim_all video --size hd720 --codec av1 --av1-quality high --container mp4 -- %F",
            "kim_all video --size hd720 --codec av1 --av1-quality balanced --container mp4 -- %F",
            "kim_all video --size hd1080 --codec av1 --av1-quality high --container mp4 -- %F",
            "kim_all video --size hd1080 --codec av1 --av1-quality balanced --container mp4 -- %F",
            "kim_all video --size hd1080 --codec av1 --av1-quality custom --container mp4 -- %F",
        }, av1_commands)
        utility_actions = {
            "VideoFrameAt": "kim_all videoframes --mode single --format png --interactive -- %F",
            "VideoThumbnail": "kim_all videoframes --mode thumbnail --format jpg -- %F",
            "VideoContactSheet": "kim_all videoframes --mode contact --format jpg --interactive -- %F",
            "ExtractVideoAudio": "kim_all videoaudio --mode extract --format m4a --interactive -- %F",
            "MuteVideo": "kim_all videoaudio --mode mute -- %F",
            "VideoToGif": "kim_all videogif --interactive -- %F",
        }
        video_menu = dict((action_id, command) for action_id, command, _ in action_entries(
            ROOT / "src/kim_compressandresizevideo.desktop.in"))
        for action_id, command in utility_actions.items():
            self.assertEqual(command, video_menu[action_id])
        self.assertEqual(6, sum(command.startswith("kim_all compress ") for command in commands))
        self.assertEqual(13, sum(command.startswith("kim_all resize ") for command in commands))
        for required in ("webexport", "resizeandsend", "rename", "album", "print", "gallery",
                         "pelemele", "tiffjoin", "animate", "stripmeta", "copyright", "timeshift",
                         "rotate", "flipflop", "convert", "about", "license", "manual"):
            self.assertTrue(any(re.search(rf"\b{required}\b", command) for command in commands), required)
        self.assertTrue(any("bmp5" in command for command in commands))
        bmp = next(command for command in commands if "--format bmp" in command)
        self.assertIn("--format bmp --bmp5 -- %F", bmp)
        self.assertTrue(any("KIM6" in line for line in
                            (ROOT / "src/kim_compress.desktop.in").read_text().splitlines()[:8]))
        self.assertIn("MimeType=image/jpeg;", (ROOT / "src/kim_compress.desktop.in").read_text())

    def test_compression_preset_labels_describe_jpeg_quality(self):
        entries = dict((action_id, (command, label)) for action_id, command, label in
                       action_entries(ROOT / "src/kim_compress.desktop.in"))
        for action_id, quality in (("Compress10", 10), ("Compress30", 30), ("Compress50", 50),
                                   ("Compress70", 70), ("Compress90", 90)):
            command, label = entries[action_id]
            self.assertIn(f"--quality {quality}", command)
            self.assertIn(f"JPEG quality: {quality}%", label)
        self.assertIn("quality", entries["CompressCustom"][1].lower())

    def test_kde_service_menu_actions_have_valid_structure(self):
        validator = shutil.which("desktop-file-validate")
        merge = shutil.which("intltool-merge")
        if not merge:
            self.skipTest("intltool-merge is unavailable")
        with tempfile.TemporaryDirectory(prefix="kim6-desktop-validate-") as temporary:
            for path in MENU_TEMPLATES:
                rendered = Path(temporary) / path.name.removesuffix(".in")
                merged = subprocess.run([merge, "--desktop-style", str(ROOT / "po"), str(path), str(rendered)],
                                        text=True, capture_output=True)
                self.assertEqual(0, merged.returncode, f"{path}: {merged.stdout}{merged.stderr}")
                text = rendered.read_text(encoding="utf-8")
                self.assertIn("Type=Service", text)
                self.assertIn("X-KDE-ServiceTypes=KonqPopupMenu/Plugin", text)
                self.assertIn("X-KDE-Protocol=file", text)
                self.assertIn("Name=KIM6", text)
                if validator:
                    # desktop-file-validate implements the freedesktop
                    # Application Exec/actions schema, while KIO service menus
                    # use Type=Service plus KDE action groups. Keep its result
                    # available in assertion detail when KDE's service format
                    # gains standard-validator support.
                    result = subprocess.run([validator, str(rendered)], text=True, capture_output=True)
                    if result.returncode:
                        self.assertIn('only valid for type "Application"', result.stdout + result.stderr)


class InstallWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kim6-install-test-")
        self.root = Path(self.temp.name)
        self.data_home = self.root / "xdg data"
        self.prefix = self.data_home / "kio/servicemenus"
        self.prefix.mkdir(parents=True)
        self.env = os.environ.copy()
        self.env.update({"HOME": str(self.root / "home"), "XDG_DATA_HOME": str(self.data_home),
                         "XDG_CACHE_HOME": str(self.root / "xdg cache"),
                         "XDG_CONFIG_HOME": str(self.root / "xdg config"),
                         "KIM6_INSTALL_PREFIX": str(self.prefix), "LANG": "C", "LC_ALL": "C"})
        Path(self.env["HOME"]).mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def run_install(self):
        return subprocess.run(["bash", str(ROOT / "install.sh"), "--prefix", str(self.prefix)],
                              cwd=ROOT, env=self.env, text=True, capture_output=True)

    def test_fresh_and_repeated_install_only_deploy_unified_runtime(self):
        first = self.run_install()
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        runtime = self.prefix / "kim6"
        self.assertTrue((runtime / "bin/kim_all").is_file())
        self.assertTrue(os.access(runtime / "bin/kim_all", os.X_OK))
        self.assertTrue((runtime / "gallery/index.part1").is_file())
        self.assertTrue((runtime / "ABOUT").is_file())
        self.assertTrue((runtime / "INSTALL.md").is_file())
        self.assertTrue((runtime / "docs/index.html").is_file())
        self.assertTrue((runtime / "docs/work.css").is_file())
        self.assertFalse((runtime / ".kim6-owned").exists(), "a separate runtime ownership marker is not installed")
        if shutil.which("msgfmt"):
            for language in ("de", "es", "fr", "hu", "it", "nl", "zh_TW"):
                translation = runtime / f"locale/{language}/LC_MESSAGES/kim6.mo"
                self.assertTrue(translation.is_file(), translation)
                self.assertEqual(0o644, translation.stat().st_mode & 0o777)
        expected_runtime_bin = {
            "kim_all",
            "kim_png_metadata.py",
            "kim_jpeg_webp_metadata.py",
            "kim_gif_metadata.py",
            "kim_tiff_verify.py",
            "kim_isobmff_verify.py",
        }
        self.assertEqual(
            expected_runtime_bin,
            {path.name for path in (runtime / "bin").iterdir()},
        )
        for companion in expected_runtime_bin - {"kim_all"}:
            installed = runtime / "bin" / companion
            self.assertTrue(installed.is_file(), installed)
            self.assertEqual(
                0o644, installed.stat().st_mode & 0o777,
                installed,
            )
        menu_files = list(self.prefix.glob("kim_*.desktop"))
        self.assertEqual(5, len(menu_files))
        for path in menu_files:
            self.assertNotRegex(path.read_text(), r"Exec=.*\bkim_(?!all\b)[A-Za-z0-9_]*")
        second = self.run_install()
        self.assertEqual(0, second.returncode, second.stdout + second.stderr)
        self.assertEqual(5, len(list(self.prefix.glob("kim_*.desktop"))))
        installed_dispatcher = runtime / "bin/kim_all"
        for menu in self.prefix.glob("kim_*.desktop"):
            for _, command, _ in action_entries(menu):
                executable = shlex.split(command)[0]
                self.assertEqual(str(installed_dispatcher), executable)
                self.assertTrue(Path(executable).is_file())
        cache_builder = shutil.which("kbuildsycoca6")
        if cache_builder:
            cache = subprocess.run([cache_builder, "--noincremental"], env=self.env,
                                   text=True, capture_output=True, timeout=30)
            self.assertEqual(0, cache.returncode, cache.stdout + cache.stderr)

    def test_default_user_install_uses_xdg_data_home(self):
        tools = self.root / "user id tool"
        tools.mkdir()
        fake_id = tools / "id"
        fake_id.write_text("#!/bin/sh\nprintf '1000\\n'\n")
        fake_id.chmod(0o755)
        result = subprocess.run(["bash", str(ROOT / "install.sh")], cwd=ROOT,
                                env={**self.env, "PATH": f"{tools}:{os.environ['PATH']}"},
                                text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue((self.data_home / "kio/servicemenus/kim6/bin/kim_all").is_file())

    def test_default_system_install_uses_first_xdg_data_dir(self):
        tools = self.root / "root id tool"
        tools.mkdir()
        fake_id = tools / "id"
        fake_id.write_text("#!/bin/sh\nprintf '0\\n'\n")
        fake_id.chmod(0o755)
        first_data = self.root / "first system data"
        second_data = self.root / "second system data"
        result = subprocess.run(["bash", str(ROOT / "install.sh")], cwd=ROOT,
                                env={**self.env, "PATH": f"{tools}:{os.environ['PATH']}",
                                     "XDG_DATA_DIRS": f"{first_data}:{second_data}"},
                                text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue((first_data / "kio/servicemenus/kim6/bin/kim_all").is_file())
        self.assertFalse((second_data / "kio/servicemenus").exists())

    def test_installed_service_menus_are_data_files_not_executables(self):
        result = self.run_install()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        for menu in self.prefix.glob("kim_*.desktop"):
            with self.subTest(menu=menu.name):
                self.assertFalse(menu.stat().st_mode & 0o111, f"service menu should not be executable: {menu}")
        dispatcher = self.prefix / "kim6/bin/kim_all"
        self.assertTrue(dispatcher.stat().st_mode & 0o111, "the unified dispatcher must remain executable")

    def test_installed_about_license_and_manual_use_installed_resources(self):
        result = self.run_install()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        runtime = self.prefix / "kim6"
        tools = self.root / "fake tools"
        tools.mkdir()
        opened = self.root / "opened paths.txt"
        opener = tools / "xdg-open"
        opener.write_text("#!/bin/sh\nprintf '%s\\n' \"$1\" >> \"$KIM_OPEN_LOG\"\n")
        opener.chmod(0o755)
        dialog = tools / "kdialog"
        dialog.write_text("#!/bin/sh\nexit 0\n")
        dialog.chmod(0o755)
        gettext_log = self.root / "gettext-env.txt"
        gettext = tools / "gettext"
        gettext.write_text("#!/bin/sh\nprintf '%s|%s\\n' \"$TEXTDOMAIN\" \"$TEXTDOMAINDIR\" >> \"$KIM_GETTEXT_LOG\"\nprintf '%s' \"$1\"\n")
        gettext.chmod(0o755)
        env = {**self.env, "PATH": f"{tools}:{os.environ['PATH']}", "KIM_OPEN_LOG": str(opened),
               "KIM_GETTEXT_LOG": str(gettext_log)}
        for action in ("about", "license", "manual"):
            opened.unlink(missing_ok=True)
            action_result = subprocess.run([str(runtime / "bin/kim_all"), action], cwd=self.root,
                                           env=env, text=True, capture_output=True, timeout=10)
            self.assertEqual(0, action_result.returncode, action_result.stdout + action_result.stderr)
            if action == "about":
                if (runtime / "locale").is_dir():
                    self.assertIn(f"kim6|{runtime / 'locale'}", gettext_log.read_text())
                continue
            opened_path = Path(opened.read_text().strip())
            self.assertTrue(opened_path.is_file())
            self.assertTrue(opened_path.is_relative_to(runtime))

    def test_install_and_uninstall_preserve_unrelated_files(self):
        unrelated = self.prefix / "kim_personal.desktop"
        unrelated.write_text("user-owned\n")
        result = self.run_install()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        removed = subprocess.run(["bash", str(ROOT / "uninstall.sh"), "--prefix", str(self.prefix)],
                                 cwd=ROOT, env=self.env, text=True, capture_output=True)
        self.assertEqual(0, removed.returncode, removed.stdout + removed.stderr)
        self.assertEqual("user-owned\n", unrelated.read_text())
        self.assertFalse((self.prefix / "kim6").exists())
        self.assertEqual([unrelated], list(self.prefix.glob("kim_*.desktop")))

        repeated = subprocess.run(["bash", str(ROOT / "uninstall.sh"), "--prefix", str(self.prefix)],
                                  cwd=ROOT, env=self.env, text=True, capture_output=True)
        self.assertEqual(0, repeated.returncode, repeated.stdout + repeated.stderr)
        self.assertEqual("user-owned\n", unrelated.read_text())

    def test_upgrade_replaces_known_resources_and_keeps_unknown_files(self):
        installed = self.run_install()
        self.assertEqual(0, installed.returncode, installed.stdout + installed.stderr)
        customized = self.prefix / "kim6/ABOUT"
        unknown = self.prefix / "kim6/my-notes.txt"
        customized.write_text("locally customized About text\n")
        unknown.write_text("keep this file\n")

        upgraded = self.run_install()
        self.assertEqual(0, upgraded.returncode, upgraded.stdout + upgraded.stderr)
        self.assertEqual((ROOT / "ABOUT").read_bytes(), customized.read_bytes())
        self.assertEqual("keep this file\n", unknown.read_text())

    def test_dispatcher_identifies_runtime_for_upgrade_and_uninstall(self):
        runtime = self.prefix / "kim6"
        (runtime / "bin").mkdir(parents=True)
        shutil.copyfile(ROOT / "src/bin/kim_all", runtime / "bin/kim_all")
        old_about = runtime / "ABOUT"
        old_about.write_text("older KIM6 about resource\n")
        user_data = runtime / "user-data.txt"
        user_data.write_text("keep this unrelated file\n")

        installed = self.run_install()
        self.assertEqual(0, installed.returncode, installed.stdout + installed.stderr)
        self.assertEqual((ROOT / "ABOUT").read_bytes(), old_about.read_bytes())
        self.assertEqual("keep this unrelated file\n", user_data.read_text())

        removed = subprocess.run(["bash", str(ROOT / "uninstall.sh"), "--prefix", str(self.prefix)],
                                 cwd=ROOT, env=self.env, text=True, capture_output=True)
        self.assertEqual(0, removed.returncode, removed.stdout + removed.stderr)
        self.assertFalse((runtime / "bin/kim_all").exists())

    def test_install_refuses_symlinked_runtime_without_touching_referent(self):
        external = self.root / "external runtime"
        external.mkdir()
        sentinel = external / "keep.txt"
        sentinel.write_text("outside KIM6\n")
        (self.prefix / "kim6").symlink_to(external, target_is_directory=True)

        result = self.run_install()
        self.assertNotEqual(0, result.returncode)
        self.assertIn("refusing unsafe directory", result.stderr)
        self.assertEqual("outside KIM6\n", sentinel.read_text())
        self.assertTrue((self.prefix / "kim6").is_symlink())
        self.assertFalse(list(self.prefix.rglob("*.tmp.*")))

    def test_uninstall_refuses_symlinked_runtime_without_removing_menus(self):
        external = self.root / "external runtime"
        external.mkdir()
        sentinel = external / "keep.txt"
        sentinel.write_text("outside KIM6\n")
        (self.prefix / "kim6").symlink_to(external, target_is_directory=True)
        menu = self.prefix / "kim_compress.desktop"
        menu.write_text("[Desktop Entry]\nX-KIM6-Managed=true\n")

        result = subprocess.run(["bash", str(ROOT / "uninstall.sh"), "--prefix", str(self.prefix)],
                                cwd=ROOT, env=self.env, text=True, capture_output=True)
        self.assertNotEqual(0, result.returncode)
        self.assertIn("refusing unsafe runtime path", result.stderr)
        self.assertEqual("outside KIM6\n", sentinel.read_text())
        self.assertEqual("[Desktop Entry]\nX-KIM6-Managed=true\n", menu.read_text())

    def test_uninstall_preserves_unrelated_nested_runtime_symlink(self):
        runtime = self.prefix / "kim6"
        (runtime / "bin").mkdir(parents=True)
        external = self.root / "external resource"
        external.write_text("outside KIM6\n")
        (runtime / "user-link").symlink_to(external)

        result = subprocess.run(["bash", str(ROOT / "uninstall.sh"), "--prefix", str(self.prefix)],
                                cwd=ROOT, env=self.env, text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertTrue((runtime / "user-link").is_symlink())
        self.assertEqual("outside KIM6\n", external.read_text())

    def test_uninstall_is_idempotent_for_an_existing_empty_prefix(self):
        first = subprocess.run(["bash", str(ROOT / "uninstall.sh"), "--prefix", str(self.prefix), "--no_message"],
                               cwd=ROOT, env=self.env, text=True, capture_output=True)
        second = subprocess.run(["bash", str(ROOT / "uninstall.sh"), "--prefix", str(self.prefix), "--no_message"],
                                cwd=ROOT, env=self.env, text=True, capture_output=True)
        self.assertEqual(0, first.returncode, first.stdout + first.stderr)
        self.assertEqual(0, second.returncode, second.stdout + second.stderr)

    def test_upgrade_recognizes_legacy_menus_and_removes_known_legacy_commands(self):
        runtime_bin = self.prefix / "kim6/bin"
        runtime_bin.mkdir(parents=True)
        shutil.copyfile(ROOT / "src/bin/kim_compress", runtime_bin / "kim_compress")
        shutil.copyfile(ROOT / "src/bin/kim_video", runtime_bin / "kim_video")
        shutil.copyfile(ROOT / "src/bin/kim_rename", runtime_bin / "kim_rename")
        legacy_menu = self.prefix / "kim_compressandresize.desktop"
        legacy_menu_text = "[Desktop Entry]\nType=Service\nActions=Compress;\n[Desktop Action Compress]\nExec=kim_compress 50 %D %U\n"
        legacy_menu.write_text(legacy_menu_text)
        result = self.run_install()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertFalse((runtime_bin / "kim_compress").exists())
        self.assertFalse((runtime_bin / "kim_video").exists())
        self.assertFalse((runtime_bin / "kim_rename").exists())
        installed_menu = legacy_menu.read_text()
        self.assertIn("kim6/bin/kim_all", installed_menu)
        self.assertNotRegex(installed_menu, r"Exec=.*\bkim_(?!all\b)[A-Za-z0-9_]*")

    def test_failed_preflight_keeps_existing_install_untouched(self):
        runtime = self.prefix / "kim6"
        runtime.mkdir()
        (runtime / "important-user-file").write_text("keep\n")
        old_menu = self.prefix / "kim_publication.desktop"
        old_menu.write_text("[Desktop Entry]\nExec=kim_galery %U\n")
        empty_path = self.root / "empty-path"
        empty_path.mkdir()
        result = subprocess.run(["/bin/bash", str(ROOT / "install.sh"), "--prefix", str(self.prefix)],
                                cwd=ROOT, env={**self.env, "PATH": str(empty_path)}, text=True, capture_output=True)
        self.assertNotEqual(0, result.returncode)
        self.assertEqual("keep\n", (runtime / "important-user-file").read_text())
        self.assertEqual("[Desktop Entry]\nExec=kim_galery %U\n", old_menu.read_text())


    def test_interrupted_install_is_repaired_by_rerunning(self):
        runtime = self.prefix / "kim6"
        (runtime / "bin").mkdir(parents=True)
        (runtime / "user-state").write_text("old runtime\n")
        shutil.copyfile(ROOT / "src/bin/kim_compress", runtime / "bin/kim_compress")
        old_menu = self.prefix / "kim_publication.desktop"
        old_menu.write_text("[Desktop Entry]\nX-KIM6-Managed=true\nName=old owned menu\n")
        tools = self.root / "mv shim"
        tools.mkdir()
        shim = tools / "mv"
        shim.write_text("#!/usr/bin/env bash\n"
                        "if [[ \"${@: -1}\" == */kim_publication.desktop && \"$*\" == *.tmp.* ]]; then exit 71; fi\n"
                        "exec /bin/mv \"$@\"\n")
        shim.chmod(0o755)
        result = subprocess.run(["bash", str(ROOT / "install.sh"), "--prefix", str(self.prefix)],
                                cwd=ROOT, env={**self.env, "PATH": f"{tools}:{os.environ['PATH']}"},
                                text=True, capture_output=True)
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("kim_publication.desktop", result.stderr)
        self.assertEqual("old runtime\n", (runtime / "user-state").read_text())
        self.assertEqual("[Desktop Entry]\nX-KIM6-Managed=true\nName=old owned menu\n", old_menu.read_text())
        self.assertTrue((runtime / "bin/kim_all").is_file())
        self.assertTrue((runtime / "bin/kim_compress").is_file(),
                        "legacy commands remain until every menu points to kim_all")
        updated_menus = [path for path in self.prefix.glob("kim_*.desktop")
                         if path.name != "kim_publication.desktop"]
        self.assertEqual(4, len(updated_menus))
        self.assertTrue(all('Exec="' in path.read_text() and "kim6/bin/kim_all" in path.read_text()
                            for path in updated_menus))
        self.assertFalse(list(self.prefix.rglob("*.tmp.*")))

        recovered = self.run_install()
        self.assertEqual(0, recovered.returncode, recovered.stdout + recovered.stderr)
        self.assertTrue((runtime / "bin/kim_all").is_file())
        self.assertFalse((runtime / "bin/kim_compress").exists())
        self.assertNotIn("old owned menu", old_menu.read_text())

    def test_unmarked_menu_collision_is_refused_without_modification(self):
        runtime = self.prefix / "kim6"
        old_menu = self.prefix / "kim_compress.desktop"
        old_content = "[Desktop Entry]\nType=Service\nName=unrelated\nExec=custom-launcher %F\n"
        old_menu.write_text(old_content)
        result = self.run_install()
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertIn("refusing unrelated or unsafe menu file", result.stderr)
        self.assertEqual(old_content, old_menu.read_text())
        self.assertFalse(runtime.exists())
        removed = subprocess.run(["bash", str(ROOT / "uninstall.sh"), "--prefix", str(self.prefix)],
                                 cwd=ROOT, env=self.env, text=True, capture_output=True)
        self.assertEqual(0, removed.returncode, removed.stdout + removed.stderr)
        self.assertEqual(old_content, old_menu.read_text())

    def test_symlinked_menu_is_refused_by_install_and_uninstall(self):
        external = self.root / "external menu.desktop"
        content = "[Desktop Entry]\nName=not KIM\nExec=some-launcher\n"
        external.write_text(content)
        menu = self.prefix / "kim_compress.desktop"
        menu.symlink_to(external)

        installed = self.run_install()
        self.assertNotEqual(0, installed.returncode)
        self.assertIn("refusing unrelated or unsafe menu file", installed.stderr)
        removed = subprocess.run(["bash", str(ROOT / "uninstall.sh"), "--prefix", str(self.prefix)],
                                 cwd=ROOT, env=self.env, text=True, capture_output=True)
        self.assertNotEqual(0, removed.returncode)
        self.assertIn("refusing unsafe menu path", removed.stderr)
        self.assertTrue(menu.is_symlink())
        self.assertEqual(content, external.read_text())

    def test_partial_uninstall_preserves_unrelated_runtime_files(self):
        runtime = self.prefix / "kim6"
        (runtime / "bin").mkdir(parents=True)
        shutil.copyfile(ROOT / "src/bin/kim_all", runtime / "bin/kim_all")
        shutil.copyfile(ROOT / "src/bin/kim_compress", runtime / "bin/kim_compress")
        legacy_script = runtime / "bin/kim_rename"
        legacy_script.write_text("#!/bin/sh\n# old KIM script\n")
        (runtime / "my-notes.txt").write_text("user data\n")
        (self.prefix / "kim_publication.desktop").write_text("[Desktop Entry]\nX-KIM6-Managed=true\n")
        result = subprocess.run(["bash", str(ROOT / "uninstall.sh"), "--prefix", str(self.prefix)],
                                cwd=ROOT, env=self.env, text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("user data\n", (runtime / "my-notes.txt").read_text())
        self.assertFalse((runtime / "bin/kim_all").exists())
        self.assertFalse((runtime / "bin/kim_compress").exists())
        self.assertFalse(legacy_script.exists())
        self.assertTrue(runtime.is_dir(), "unknown files keep the runtime directory in place")


class MenuArgumentExecutionTests(unittest.TestCase):
    def test_missing_image_stack_dependencies_fail_before_processing_with_specific_message(self):
        for missing_tool in ("magick", "identify"):
            with self.subTest(missing_tool=missing_tool):
                w = Workspace()
                self.addCleanup(w.close)
                source = w.jpeg("input/photo.jpg")
                w.env["KIM_POLICY"] = "create"
                (w.bin / missing_tool).unlink()
                result = w.dispatch("compress", "--quality", "75", "--", source)
                self.assertNotEqual(0, result.returncode)
                error_dialogs = [call for call in result.calls if call["tool"] == "kdialog"
                                 and "--error" in call["argv"]]
                self.assertTrue(error_dialogs, result.calls)
                self.assertIn("ImageMagick", " ".join(error_dialogs[0]["argv"]))
                self.assertFalse(any(call["tool"] in {"magick", "identify"} for call in result.calls))
                self.assertEqual(source.read_bytes(),
                                 (w.root / "input/photo.jpg").read_bytes())

    def test_missing_exiftool_is_not_reported_as_an_exif_date_failure(self):
        w = Workspace()
        self.addCleanup(w.close)
        source = w.jpeg("input/photo.jpg")
        (w.bin / "exiftool").unlink()
        w.respond("kdialog", stdout="1")
        result = w.dispatch("rename", "exifdate", "--", source)
        self.assertNotEqual(0, result.returncode)
        errors = [call for call in result.calls if call["tool"] == "kdialog" and "--error" in call["argv"]]
        self.assertTrue(errors, result.calls)
        self.assertIn("ExifTool", " ".join(errors[-1]["argv"]))
        self.assertTrue(source.is_file())
        self.assertFalse((w.root / "input/20260101_000000.jpg").exists())

    def test_newline_filename_is_rejected_before_line_record_path_mapping(self):
        w = Workspace()
        self.addCleanup(w.close)
        source = w.jpeg("input/line\nbreak.jpg")
        original = source.read_bytes()
        result = w.dispatch("resize", "--size", "2x2", "--", source)
        self.assertNotEqual(0, result.returncode)
        errors = [call for call in result.calls if call["tool"] == "kdialog" and "--error" in call["argv"]]
        self.assertTrue(errors, result.calls)
        self.assertIn("line break", " ".join(errors[-1]["argv"]).lower())
        self.assertFalse(any(call["tool"] in {"magick", "identify"} for call in result.calls))
        self.assertEqual(original, source.read_bytes())
        self.assertEqual([source], list(source.parent.iterdir()))

    def test_newline_filename_rejects_the_entire_mixed_batch(self):
        w = Workspace()
        self.addCleanup(w.close)
        valid = w.jpeg("input/valid.jpg")
        invalid = w.jpeg("input/line\nbreak.jpg")
        originals = {path: path.read_bytes() for path in (valid, invalid)}
        result = w.dispatch("resize", "--size", "2x2", "--", valid, invalid)
        self.assertNotEqual(0, result.returncode)
        self.assertFalse(any(call["tool"] in {"magick", "identify"} for call in result.calls))
        self.assertEqual(originals, {path: path.read_bytes() for path in originals})
        self.assertEqual({valid, invalid}, set(valid.parent.iterdir()))

    def test_image_menu_option_contracts_reach_real_dispatcher_actions(self):
        w = Workspace()
        self.addCleanup(w.close)
        source = w.jpeg("input/selected file 雪.jpg")
        w.env["KIM_POLICY"] = "create"
        w.use_real_compression()
        result = w.dispatch("compress", "--quality", "73", "--", source)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(source.with_name("selected file 雪_compressed.jpg").is_file(), str(result.after_entries))

        w.use_real_conversion()
        result = w.dispatch("convert", "--format", "png", "--", source)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(source.with_suffix(".png").is_file())

        wr = Workspace()
        self.addCleanup(wr.close)
        resize_source = wr.jpeg("input/selected file 雪.jpg")
        wr.env["KIM_POLICY"] = "create"
        wr.use_real_resize()
        result = wr.dispatch("resize", "--size", "2x2", "--", resize_source)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(resize_source.with_name("selected file 雪_resized.jpg").is_file(), str(result.events))

    def test_rotation_and_flip_menu_contracts_accept_delimited_files(self):
        w = Workspace()
        self.addCleanup(w.close)
        source = w.ppm("selected/input image.ppm")
        w.approve_overwrite()
        w.use_real_transform()
        rotated = w.dispatch("rotate", "--angle", "90", "--", source)
        self.assertEqual(0, rotated.returncode, rotated.stderr)
        flipped = w.dispatch("flipflop", "flop", "--", source)
        self.assertEqual(0, flipped.returncode, flipped.stderr)
        self.assertEqual((2, 3), w.image_info(source)[1:])
