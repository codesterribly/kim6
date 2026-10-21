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
            self.assertEqual(declared, defined, f"{path.name}: declared IDs must match action groups")
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
        self.assertEqual(94, len(entries))
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
        self.assertEqual(6, sum(command.startswith("kim_all compress ") for command in commands))
        self.assertEqual(12, sum(command.startswith("kim_all resize ") for command in commands))
        for required in ("webexport", "resizeandsend", "rename", "album", "print", "gallery",
                         "pelemele", "tiffjoin", "animate", "stripmeta", "rotate", "flipflop",
                         "convert", "about", "license", "manual"):
            self.assertTrue(any(re.search(rf"\b{required}\b", command) for command in commands), required)
        self.assertTrue(any("bmp5" in command for command in commands))
        bmp = next(command for command in commands if "--format bmp" in command)
        self.assertIn("--format bmp --bmp5 -- %F", bmp)
        self.assertTrue(any("KIM6" in line for line in
                            (ROOT / "src/kim_compress.desktop.in").read_text().splitlines()[:8]))
        self.assertIn("MimeType=image/jpeg;", (ROOT / "src/kim_compress.desktop.in").read_text())

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
        self.assertFalse(any(path.name != "kim_all" for path in (runtime / "bin").iterdir()))
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

    def test_upgrade_replaces_legacy_menus_and_removes_identical_legacy_commands(self):
        runtime_bin = self.prefix / "kim6/bin"
        runtime_bin.mkdir(parents=True)
        shutil.copyfile(ROOT / "src/bin/kim_compress", runtime_bin / "kim_compress")
        shutil.copyfile(ROOT / "src/bin/kim_video", runtime_bin / "kim_video")
        customized_legacy = runtime_bin / "kim_rename"
        customized_legacy.write_bytes((ROOT / "src/bin/kim_rename").read_bytes() + b"\n# local edit\n")
        customized_legacy.chmod(0o755)
        legacy_menu = self.prefix / "kim_compressandresize.desktop"
        legacy_menu_text = "[Desktop Entry]\nType=Service\nActions=Compress;\n[Desktop Action Compress]\nExec=kim_compress 50 %D %U\n"
        legacy_menu.write_text(legacy_menu_text)
        result = self.run_install()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertFalse((runtime_bin / "kim_compress").exists())
        self.assertFalse((runtime_bin / "kim_video").exists())
        self.assertFalse(customized_legacy.exists())
        preserved_scripts = list((self.prefix / "kim6").glob(".kim6-preserved.*/legacy/bin/kim_rename"))
        self.assertEqual(1, len(preserved_scripts))
        self.assertEqual((ROOT / "src/bin/kim_rename").read_bytes() + b"\n# local edit\n",
                         preserved_scripts[0].read_bytes())
        self.assertFalse(os.access(preserved_scripts[0], os.X_OK))
        installed_menu = legacy_menu.read_text()
        self.assertIn("kim6/bin/kim_all", installed_menu)
        self.assertNotRegex(installed_menu, r"Exec=.*\bkim_(?!all\b)[A-Za-z0-9_]*")
        preserved_menus = list((self.prefix / "kim6").glob(".kim6-preserved.*/menus/kim_compressandresize.desktop"))
        self.assertEqual(1, len(preserved_menus))
        self.assertEqual(legacy_menu_text, preserved_menus[0].read_text())

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


    def test_failure_during_menu_swap_restores_previous_runtime_and_menus(self):
        runtime = self.prefix / "kim6"
        (runtime / "bin").mkdir(parents=True)
        (runtime / "user-state").write_text("old runtime\n")
        old_menu = self.prefix / "kim_publication.desktop"
        old_menu.write_text("[Desktop Entry]\nType=Service\nExec=kim_galery %U\n")
        tools = self.root / "mv shim"
        tools.mkdir()
        shim = tools / "mv"
        shim.write_text("#!/usr/bin/env bash\n"
                        "for arg in \"$@\"; do\n"
                        "  case \"$arg\" in */menus/kim_convertandrotate.desktop) exit 71 ;; esac\n"
                        "done\nexec /bin/mv \"$@\"\n")
        shim.chmod(0o755)
        result = subprocess.run(["bash", str(ROOT / "install.sh"), "--prefix", str(self.prefix)],
                                cwd=ROOT, env={**self.env, "PATH": f"{tools}:{os.environ['PATH']}"},
                                text=True, capture_output=True)
        self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("old runtime\n", (runtime / "user-state").read_text())
        self.assertEqual("[Desktop Entry]\nType=Service\nExec=kim_galery %U\n", old_menu.read_text())
        self.assertFalse(list(self.prefix.glob(".kim6-stage.*")))
        recovered = self.run_install()
        self.assertEqual(0, recovered.returncode, recovered.stdout + recovered.stderr)
        self.assertTrue((runtime / "bin/kim_all").is_file())

    def test_partial_owned_uninstall_preserves_unrelated_runtime_files(self):
        runtime = self.prefix / "kim6"
        (runtime / "bin").mkdir(parents=True)
        (runtime / ".kim6-owned").touch()
        shutil.copyfile(ROOT / "src/bin/kim_all", runtime / "bin/kim_all")
        (runtime / "my-notes.txt").write_text("user data\n")
        (self.prefix / "kim_publication.desktop").write_text("[Desktop Entry]\nX-KIM6-Managed=true\n")
        result = subprocess.run(["bash", str(ROOT / "uninstall.sh"), "--prefix", str(self.prefix)],
                                cwd=ROOT, env=self.env, text=True, capture_output=True)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual("user data\n", (runtime / "my-notes.txt").read_text())
        self.assertFalse((runtime / "bin/kim_all").exists())


class MenuArgumentExecutionTests(unittest.TestCase):
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
        w.env["KIM_POLICY"] = "overwrite"
        w.use_real_transform()
        rotated = w.dispatch("rotate", "--angle", "90", "--", source)
        self.assertEqual(0, rotated.returncode, rotated.stderr)
        flipped = w.dispatch("flipflop", "flop", "--", source)
        self.assertEqual(0, flipped.returncode, flipped.stderr)
        self.assertEqual((2, 3), w.image_info(source)[1:])
