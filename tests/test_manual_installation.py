"""Isolated installation regression tests for the KIM6 offline HTML manual.

Runs install.sh and uninstall.sh only with disposable --prefix directories.
Stubs menu translation and KDE's global cache refresh: these tests verify
manual packaging, not translation or a user's Dolphin environment.
"""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
MANUAL_FILES = (
    "docs/index.html",
    "docs/work.css",
    "docs/reference/ABOUT.html",
    "docs/reference/ACTIONS.html",
    "docs/reference/commandconfig.html",
    "docs/reference/DEVELOPMENT.html",
    "docs/reference/FORMATS.html",
    "docs/reference/INSTALL.html",
    "docs/reference/LICENSE.html",
    "docs/reference/README.html",
    "docs/images/kim6-photo-actions.png",
    "docs/images/kim6-video-conversion.png",
    "docs/images/kim6-video-utilities.png",
    "docs/images/kim6-settings-dialog.png",
    "docs/images/kim6-collage-dialog.png",
    "docs/images/kim6-animated-gif-dialog.png",
)


class ManualInstallationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="kim6-manual-test-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.prefix = self.base / "kio" / "servicemenus"
        self.runtime = self.prefix / "kim6"

        # Avoid global KDE cache activity, and keep this packaging test
        # independent of the system's intltool installation and translations.
        fake_bin = self.base / "test-bin"
        fake_bin.mkdir()
        merge = fake_bin / "intltool-merge"
        merge.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            "previous=''\n"
            "current=''\n"
            "for arg do previous=$current; current=$arg; done\n"
            "cp -- \"$previous\" \"$current\"\n",
            encoding="utf-8",
        )
        merge.chmod(0o755)
        cache = fake_bin / "kbuildsycoca6"
        cache.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        cache.chmod(0o755)

        self.env = os.environ.copy()
        self.env["PATH"] = str(fake_bin) + os.pathsep + self.env.get("PATH", "")

    def run_installer(self, script, *, succeeds=True):
        result = subprocess.run(
            ["bash", str(ROOT / script), "--prefix", str(self.prefix)],
            cwd=ROOT,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        details = (
            f"{script} exit status: {result.returncode}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        if succeeds:
            self.assertEqual(0, result.returncode, details)
        else:
            self.assertNotEqual(0, result.returncode, details)
        return result

    def assert_manual_matches_checkout(self):
        for relative in MANUAL_FILES:
            with self.subTest(file=relative):
                source = ROOT / relative
                installed = self.runtime / relative
                self.assertTrue(source.is_file(), f"Missing source: {source}")
                self.assertTrue(installed.is_file(), f"Not installed: {relative}")
                self.assertFalse(installed.is_symlink(), f"Symlinked output: {relative}")
                self.assertEqual(source.read_bytes(), installed.read_bytes())

    def test_install_upgrade_uninstall_and_preserve_unrelated_file(self):
        self.run_installer("install.sh")
        self.assert_manual_matches_checkout()
        engine = self.runtime / "bin/kim_png_metadata.py"
        self.assertEqual(engine.read_bytes(),
                         (ROOT / "src/bin/kim_png_metadata.py").read_bytes())
        self.assertFalse(engine.is_symlink())

        # A modified managed HTML file is restored on an upgrade.
        readme = self.runtime / "docs/reference/README.html"
        readme.write_text("outdated manual\n", encoding="utf-8")
        self.run_installer("install.sh")
        self.assert_manual_matches_checkout()

        # Unknown user files must never be removed by the uninstaller.
        unrelated = self.runtime / "docs/reference/user-notes.txt"
        unrelated.write_text("leave this file alone\n", encoding="utf-8")
        self.run_installer("uninstall.sh")
        for relative in MANUAL_FILES:
            with self.subTest(removed=relative):
                self.assertFalse((self.runtime / relative).exists())
        self.assertEqual("leave this file alone\n", unrelated.read_text())
        self.assertFalse((self.runtime / "docs/images").exists())

        # Repeated uninstallation is safe and does not remove unknown files.
        self.run_installer("uninstall.sh")
        self.assertTrue(unrelated.is_file())

    def test_installed_menus_use_installed_dispatcher(self):
        self.run_installer("install.sh")
        dispatcher = self.runtime / "bin/kim_all"
        self.assertTrue(dispatcher.is_file())

        menu_names = tuple(
            path.name.removesuffix(".in")
            for path in sorted((ROOT / "src").glob("kim_*.desktop.in"))
        )
        self.assertEqual(10, len(menu_names))

        for name in menu_names:
            with self.subTest(menu=name):
                template = (ROOT / "src" / (name + ".in")).read_text()
                installed = (self.prefix / name).read_text()
                expected = sum(
                    line.startswith("Exec=")
                    for line in template.splitlines()
                )
                commands = [
                    line for line in installed.splitlines()
                    if line.startswith("Exec=")
                ]

                self.assertGreater(expected, 0)
                self.assertEqual(expected, len(commands))

                for command in commands:
                    self.assertTrue(
                        command.startswith(f'Exec="{dispatcher}" '),
                        command,
                    )

    def test_reject_symlinked_reference_directory(self):
        self.run_installer("install.sh")
        directory = self.runtime / "docs/reference"
        outside = self.base / "external-reference"
        outside.mkdir()
        sentinel = outside / "do-not-touch.txt"
        sentinel.write_text("outside\n", encoding="utf-8")

        for file in directory.iterdir():
            file.unlink()
        directory.rmdir()
        directory.symlink_to(outside, target_is_directory=True)

        self.run_installer("install.sh", succeeds=False)
        self.run_installer("uninstall.sh", succeeds=False)
        self.assertEqual("outside\n", sentinel.read_text())
        self.assertTrue((self.runtime / "bin/kim_all").is_file())

    def test_reject_symlinked_illustration_file(self):
        self.run_installer("install.sh")
        illustration = self.runtime / "docs/images/kim6-settings-dialog.png"
        outside = self.base / "do-not-overwrite.png"
        outside.write_bytes(b"unrelated data\n")
        illustration.unlink()
        illustration.symlink_to(outside)

        self.run_installer("install.sh", succeeds=False)
        self.run_installer("uninstall.sh", succeeds=False)
        self.assertEqual(b"unrelated data\n", outside.read_bytes())
        self.assertTrue((self.runtime / "bin/kim_all").is_file())


if __name__ == "__main__":
    unittest.main()
