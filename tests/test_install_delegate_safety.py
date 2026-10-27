"""Focused KIM6 installer ownership and ImageMagick registry guards."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DelegateRegistryTests(unittest.TestCase):
    def probe(self, registry, coder, operation):
        source = (ROOT / "src/bin/kim_all").read_text()
        start = source.index("image_coder_supports() {\n")
        end = source.index("\n}\n", start) + 2
        function = source[start:end]

        code = (
            "magick() { printf '%s\\n' \"$REGISTRY\"; }\n"
            + function
            + '\nimage_coder_supports "$1" "$2"\n'
        )

        return subprocess.run(
            ["bash", "-c", code, "_", coder, operation],
            env={**os.environ, "REGISTRY": registry},
            capture_output=True,
            text=True,
            timeout=5,
        ).returncode == 0

    def test_three_column_image_magick_registry(self):
        registry = " JXL rw+ JPEG XL\n WEBP r-- WebP\n AVIF -w+ AV1"

        self.assertTrue(self.probe(registry, "JXL", "write"))
        self.assertTrue(self.probe(registry, "JXL", "read"))
        self.assertTrue(self.probe(registry, "AVIF", "write"))
        self.assertFalse(self.probe(registry, "WEBP", "write"))
        self.assertFalse(self.probe(registry, "MISSING", "read"))

    def test_four_column_image_magick_registry(self):
        registry = " JXL JXL rw+ JPEG XL\n HEIC HEIC r-- HEIC"

        self.assertTrue(self.probe(registry, "JXL", "write"))
        self.assertTrue(self.probe(registry, "HEIC", "read"))
        self.assertFalse(self.probe(registry, "HEIC", "write"))


class InstallOwnershipTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="kim6-ownership-")
        self.addCleanup(temporary.cleanup)

        self.base = Path(temporary.name)
        self.prefix = self.base / "kio/servicemenus"
        self.runtime = self.prefix / "kim6"

        self.runtime.joinpath("docs").mkdir(parents=True)

        self.unrelated = self.runtime / "docs/index.html"
        self.unrelated.write_text("unrelated user file\n")

        self.menu = self.prefix / "kim_publication.desktop"
        self.menu.write_text(
            "[Desktop Entry]\nX-KIM6-Managed=true\n"
        )

    def test_uninstall_menu_does_not_claim_unrelated_runtime(self):
        result = subprocess.run(
            [
                "bash",
                str(ROOT / "uninstall.sh"),
                "--prefix",
                str(self.prefix),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(self.menu.exists())
        self.assertEqual(
            self.unrelated.read_text(),
            "unrelated user file\n",
        )

    def test_install_refuses_menu_only_claim_on_unrelated_runtime(self):
        tools = self.base / "tools"
        tools.mkdir()

        stub = tools / "intltool-merge"
        stub.write_text("#!/bin/sh\nexit 0\n")
        stub.chmod(0o755)

        result = subprocess.run(
            [
                "bash",
                str(ROOT / "install.sh"),
                "--prefix",
                str(self.prefix),
            ],
            env={
                **os.environ,
                "PATH": (
                    str(tools)
                    + os.pathsep
                    + os.environ.get("PATH", "")
                ),
            },
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "unrecognized runtime directory",
            result.stderr,
        )
        self.assertEqual(
            self.unrelated.read_text(),
            "unrelated user file\n",
        )
        self.assertFalse(
            (self.runtime / "bin/kim_all").exists()
        )

    def test_uninstall_recognizes_legacy_kim_script(self):
        legacy = self.runtime / "bin/kim_compress"
        legacy.parent.mkdir()

        legacy.write_text(
            "#!/bin/bash\nSOURCE_TRANSLATION_TTT\n"
        )

        notes = self.runtime / "user-notes.txt"
        notes.write_text("keep me\n")

        result = subprocess.run(
            [
                "bash",
                str(ROOT / "uninstall.sh"),
                "--prefix",
                str(self.prefix),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(legacy.exists())
        self.assertFalse(self.unrelated.exists())
        self.assertEqual(
            notes.read_text(),
            "keep me\n",
        )


if __name__ == "__main__":
    unittest.main()
