"""Isolated installation regression tests for the KIMng offline HTML manual.

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
    'docs/index.html',
    'docs/work.css',
    'docs/images/kimng-brand-icon.png',
    "docs/images/kimng-guide-icon.png",
    'docs/reference/ABOUT.html',
    'docs/reference/ACTIONS.html',
    'docs/reference/commandconfig.html',
    'docs/reference/DEVELOPMENT.html',
    'docs/reference/FORMATS.html',
    'docs/reference/INSTALL.html',
    'docs/reference/LICENSE.html',
    'docs/reference/README.html',
    'docs/reference/RECIPES.html',
    'docs/images/screenshots/01-main-menu.png',
    'docs/images/screenshots/02-convert-compress.png',
    'docs/images/screenshots/03-create-publish.png',
    'docs/images/screenshots/04-location-gps.png',
    'docs/images/screenshots/05-organize-metadata.png',
    'docs/images/screenshots/06-recipes.png',
    'docs/images/screenshots/07-resize-crop-rotate.png',
    'docs/images/screenshots/08-settings-about.png',
    'docs/images/screenshots/09-web-export.png',
    'docs/images/screenshots/10-settings-menu.png',
    'docs/images/screenshots/11-run-recipe.png',
    'docs/images/screenshots/12-recipe-editor.png',
    'docs/images/screenshots/13-preview-changes.png',
    'docs/images/screenshots/14-check-extensions.png',
    'docs/images/screenshots/15-modify-gps.png',
    'docs/images/screenshots/16-reduce-gps-precision.png',
    'docs/images/screenshots/17-crop-image.png',
    'docs/images/screenshots/18-set-dates.png',
    'docs/images/screenshots/19-create-collage.png',
    'docs/images/screenshots/20-review-web-export.png',
    'docs/images/screenshots/21-video-menu-overview.png',
    'docs/images/screenshots/22-video-av1-presets.png',
    'docs/images/screenshots/23-video-utilities.png',
)

RETIRED_MANUAL_FILES = (
    'docs/images/screenshots/kim6-animated-gif-dialog.png',
    'docs/images/screenshots/kim6-collage-dialog.png',
    'docs/images/screenshots/kim6-convert-menu.png',
    'docs/images/screenshots/kim6-metadata-menu.png',
    'docs/images/screenshots/kim6-photo-actions.png',
    'docs/images/screenshots/kim6-recipe-editor.png',
    'docs/images/screenshots/kim6-recipes-menu.png',
    'docs/images/screenshots/kim6-settings-dialog.png',
    'docs/images/screenshots/kim6-settings-general.png',
    'docs/images/screenshots/kim6-video-conversion.png',
    'docs/images/screenshots/kim6-video-utilities.png',
    'docs/reference/STEP2_IMPLEMENTATION.html',
)


class ManualInstallationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="kimng-manual-test-")
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.prefix = self.base / "kio" / "servicemenus"
        self.runtime = self.prefix / "kimng"

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
        helpers=('kim_ui','kim_date_tools','kim_date_dialog','kim_filename','kim_job','kim_job_process','kim_action_dialog')
        for helper in helpers:
            self.assertEqual((self.runtime/'bin'/(helper+'.py')).read_bytes(),(ROOT/'src/bin'/(helper+'.py')).read_bytes())
        import sys
        # Pass the isolated installed runtime explicitly, never the checkout.
        imported=subprocess.run([sys.executable,'-B','-c',
            'import sys;sys.path.insert(0,sys.argv[1]);'+ ';'.join('import '+helper for helper in helpers),str(self.runtime/'bin')],
            cwd=self.base,env=self.env,capture_output=True,text=True)
        self.assertEqual(imported.returncode,0,imported.stderr)
        self.assertEqual((self.runtime / 'bin/kim_psd_source.py').read_bytes(),
                         (ROOT / 'src/bin/kim_psd_source.py').read_bytes())
        for name in ('kim_convertandrotate.desktop', 'kim_publication.desktop', 'kim_webemail.desktop', 'kim_recipes.desktop'):
            menu = (self.prefix / name).read_text()
            self.assertIn('image/vnd.adobe.photoshop;', menu)
            self.assertIn('application/x-photoshop;', menu)
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
        self.assertEqual(12, len(menu_names))

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

    def test_installed_recipe_manual_and_referenced_screenshots_are_packaged(self):
        self.run_installer('install.sh')
        # The installed overview links to Recipes, and the new guide uses all
        # five screenshots. Compare bytes with the current checkout, including intentional screenshot placeholders.
        references = (
            'docs/reference/RECIPES.html',
            'docs/images/screenshots/06-recipes.png',
            'docs/images/screenshots/12-recipe-editor.png',
            'docs/images/screenshots/02-convert-compress.png',
            'docs/images/screenshots/05-organize-metadata.png',
            'docs/images/screenshots/08-settings-about.png',
        )
        for relative in references:
            with self.subTest(file=relative):
                source = ROOT / relative
                self.assertTrue(source.is_file(), relative)
                installed = self.runtime / relative
                self.assertTrue(installed.is_file(), 'Not installed: ' + relative)
                self.assertFalse(installed.is_symlink(), relative)
                self.assertEqual(installed.read_bytes(), source.read_bytes())

    def test_new_manual_assets_uninstall_preserves_unrecognized_neighbors(self):
        self.run_installer('install.sh')
        self.assert_manual_matches_checkout()
        neighbors = [self.runtime / 'docs/images/user-photo.png',
                     self.runtime / 'docs/reference/user-guide.html']
        for path in neighbors:
            path.write_bytes(b'not managed by KIMng')
        self.run_installer('uninstall.sh')
        for relative in MANUAL_FILES:
            self.assertFalse((self.runtime / relative).exists(), relative)
        for path in neighbors:
            self.assertEqual(path.read_bytes(), b'not managed by KIMng')

    def test_reject_symlinked_manual_directory(self):
        for relative in ("docs/reference", "docs/images/screenshots"):
            with self.subTest(directory=relative):
                self.check_symlinked_manual_directory(relative)

    def check_symlinked_manual_directory(self, relative):
        self.run_installer("install.sh")
        directory = self.runtime / relative
        outside = self.base / ("external-" + directory.name)
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
        self.assertTrue(directory.is_symlink())
        self.assertTrue((self.runtime / "bin/kim_all").is_file())
        directory.unlink()

    def test_reject_symlinked_illustration_file(self):
        self.run_installer("install.sh")
        illustration = self.runtime / "docs/images/screenshots/10-settings-menu.png"
        outside = self.base / "do-not-overwrite.png"
        outside.write_bytes(b"unrelated data\n")
        illustration.unlink()
        illustration.symlink_to(outside)

        self.run_installer("install.sh", succeeds=False)
        self.run_installer("uninstall.sh", succeeds=False)
        self.assertEqual(b"unrelated data\n", outside.read_bytes())
        self.assertTrue((self.runtime / "bin/kim_all").is_file())



    def test_retired_documentation_not_installed(self):
        self.run_installer("install.sh")
        self.assert_manual_matches_checkout()

        for relative in RETIRED_MANUAL_FILES:
            path = self.runtime / relative
            self.assertFalse(path.exists(), relative)
            self.assertFalse(path.is_symlink(), relative)

    def test_upgrade_removes_retired_documentation(self):
        self.run_installer("install.sh")

        for relative in RETIRED_MANUAL_FILES:
            path = self.runtime / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"retired KIMng documentation")

        unrelated = self.runtime / "docs/reference/user-notes.txt"
        unrelated.write_bytes(b"preserve unrelated content")

        self.run_installer("install.sh")
        self.assert_manual_matches_checkout()

        for relative in RETIRED_MANUAL_FILES:
            self.assertFalse((self.runtime / relative).exists())

        self.assertEqual(
            unrelated.read_bytes(),
            b"preserve unrelated content"
        )

    def test_uninstall_removes_retired_documentation(self):
        self.run_installer("install.sh")

        for relative in RETIRED_MANUAL_FILES:
            path = self.runtime / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"retired KIMng documentation")

        unrelated = self.runtime / "docs/reference/user-notes.txt"
        unrelated.write_bytes(b"preserve unrelated content")

        self.run_installer("uninstall.sh")

        for relative in RETIRED_MANUAL_FILES:
            self.assertFalse((self.runtime / relative).exists())

        self.assertEqual(
            unrelated.read_bytes(),
            b"preserve unrelated content"
        )

    def test_retired_documentation_symlink_is_refused(self):
        self.run_installer("install.sh")

        outside = self.base / "outside-documentation"
        outside.write_bytes(b"must remain unchanged")

        retired = self.runtime / RETIRED_MANUAL_FILES[0]
        retired.symlink_to(outside)

        dispatcher = self.runtime / "bin/kim_all"
        original = dispatcher.read_bytes()

        self.run_installer("install.sh", succeeds=False)
        self.run_installer("uninstall.sh", succeeds=False)

        self.assertTrue(retired.is_symlink())
        self.assertEqual(outside.read_bytes(), b"must remain unchanged")
        self.assertEqual(dispatcher.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
