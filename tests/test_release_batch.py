#!/usr/bin/env python3
"""KIM6 focused release regression checks.

Uses disposable inputs only. Never modifies user photographs.
Runs static packaging/menu checks and actual Flip tests.
"""

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from support import Workspace


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
RUNTIME = Path.home() / ".local/share/kio/servicemenus/kim6/bin"
DISPATCHER = SOURCE / "bin/kim_all"


def run(*args, env=None, timeout=90):
    return subprocess.run(
        [str(a) for a in args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        timeout=timeout,
    )


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PackagingTests(unittest.TestCase):

    def test_required_runtime_files(self):
        installer = (ROOT / "install.sh").read_text()

        required = (
            "kim_all",
            "kim_collage_dialog.py",
            "kim_contactsheet_dialog.py",
            "kim_album_dialog.py",
            "kim_create_dialog.py",
            "kim_manual_viewer.py",
            "kim_settings_dialog.py",
            "kim_png_metadata.py",
            "kim_jpeg_webp_metadata.py",
            "kim_gif_metadata.py",
            "kim_tiff_verify.py",
            "kim_isobmff_verify.py",
        )

        for name in required:
            with self.subTest(name=name):
                source = SOURCE / "bin" / name
                self.assertTrue(
                    source.is_file(),
                    f"Missing source helper: {source}",
                )

                self.assertIn(
                    "bin/" + name,
                    installer,
                    f"Installer does not reference {name}",
                )

                if name.endswith(".py"):
                    compile(
                        source.read_bytes(),
                        str(source),
                        "exec",
                    )

    def test_bash_syntax(self):
        for name in ("src/bin/kim_all", "install.sh"):
            with self.subTest(name=name):
                result = run("bash", "-n", ROOT / name)
                self.assertEqual(
                    result.returncode, 0, result.stderr
                )

    def test_creation_only_operations(self):
        script = (SOURCE / "bin/kim_all").read_text()

        for name in (
            "action_contactsheet",
            "collage_render_layout",
            "action_pelemele",
        ):
            with self.subTest(action=name):
                self.assertRegex(
                    script,
                    re.escape(name) + r"\(\)\s*[({]",
                )

        for prompt in (
            "Create a new contact-sheet PDF?",
            "Do you want to create a new collage?",
            "Do you want to create a new joined TIFF?",
            "Do you want to create a new GIF animation?",
            "Do you want to create a new print PDF?",
            "Do you want to create a new PDF?",
        ):
            with self.subTest(prompt=prompt):
                self.assertNotIn(
                    f'choose_output_mode "$(gettext '
                    f"'Kim')\" \"$(gettext '{prompt}')",
                    script,
                )

    def test_safe_publication_paths_exist(self):
        script = (SOURCE / "bin/kim_all").read_text()

        for function in (
            "prepare_derived_target",
            "commit_tmp_to_target",
            "choose_output_mode",
            "action_transform_in_place",
        ):
            with self.subTest(function=function):
                self.assertRegex(
                    script,
                    rf"(?m)^{re.escape(function)}\(\)",
                )


class WebExportTests(unittest.TestCase):

    FORMATS = ("jpg", "png", "webp", "avif")
    SIZES = ("1600x1600", "800x800", "128x128")

    def test_twelve_menu_presets(self):
        menus = "\n".join(
            p.read_text()
            for p in SOURCE.glob("*.desktop.in")
        )

        found = set()

        for line in menus.splitlines():
            if not line.startswith("Exec="):
                continue
            if "webexport" not in line:
                continue

            match = re.search(
                r"--size\s+(\d+x\d+)\s+"
                r"--format\s+(jpg|png|webp|avif)\b",
                line,
            )
            if match:
                found.add((match.group(2), match.group(1)))

        expected = {
            (fmt, size)
            for fmt in self.FORMATS
            for size in self.SIZES
        }

        self.assertEqual(
            found, expected,
            f"Missing: {sorted(expected - found)}; "
            f"Unexpected: {sorted(found - expected)}",
        )

    def test_image_encoders_available(self):
        formats = run("magick", "-list", "format")
        self.assertEqual(formats.returncode, 0, formats.stderr)

        for fmt in self.FORMATS:
            with self.subTest(format=fmt):
                # Write binary image data to a temporary file.
                # The text-mode subprocess helper must not decode it.
                with tempfile.TemporaryDirectory(
                    prefix="kim6-encoder-"
                ) as directory:
                    output = Path(directory) / f"test.{fmt}"
                    result = run(
                        "magick", "-size", "19x13",
                        "gradient:red-blue",
                        f"{fmt.upper()}:{output}",
                    )
                    self.assertEqual(
                        result.returncode, 0,
                        f"{fmt} encoder failed: {result.stderr}",
                    )
                    self.assertTrue(output.is_file())
                    self.assertGreater(output.stat().st_size, 0)

                    identification = run(
                        "identify", "-format", "%m %w %h", output
                    )
                    self.assertEqual(
                        identification.returncode, 0,
                        identification.stderr,
                    )
                    expected_format = "JPEG" if fmt == "jpg" else fmt.upper()
                    self.assertEqual(
                        identification.stdout,
                        f"{expected_format} 19 13",
                    )

    def test_webexport_dispatcher_present(self):
        script = (SOURCE / "bin/kim_all").read_text()
        self.assertIn("action_webexport()", script)

        for fmt in self.FORMATS:
            with self.subTest(format=fmt):
                self.assertRegex(
                    script, rf"\b{fmt}\b"
                )


class FlipFunctionalTests(unittest.TestCase):

    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.use_real_transform()
        self.w.env["KIM_POLICY"] = "create"
        self.w.env["KIM_NAME_AFFIX_POSITION"] = "suffix"
        self.path = self.w.path("input")
        self.path.mkdir()

        # Distinctive colored regions expose horizontal/vertical
        # orientation mistakes.
        self.source = self.path / "fixture.png"
        created = run(
            "magick", "-size", "37x23",
            "xc:white",
            "-fill", "red",
            "-draw", "rectangle 0,0 11,22",
            "-fill", "blue",
            "-draw", "rectangle 12,0 36,7",
            f"PNG:{self.source}",
        )

        self.assertEqual(
            created.returncode, 0, created.stderr
        )
        self.original_hash = sha256(self.source)

    def invoke(self, operation):
        result = self.w.dispatch(
            "flipflop", operation, "--", self.source,
        )

        self.assertEqual(
            result.returncode, 0,
            f"Flip {operation} failed:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}",
        )

        self.assertEqual(
            sha256(self.source),
            self.original_hash,
            "Original image was modified",
        )

        outputs = sorted(
            p for p in self.path.glob("*.png")
            if p != self.source
        )

        self.assertTrue(
            outputs,
            f"No derived output for {operation}",
        )

        return outputs

    def test_horizontal_flip_pixels(self):
        outputs = self.invoke("flop")

        expected = self.path / "expected.png"
        result = run(
            "magick",
            self.source,
            "-flop",
            expected,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        candidate = outputs[-1]

        comparison = run(
            "compare",
            "-metric", "AE",
            expected,
            candidate,
            "null:",
        )
        self.assertEqual(
            comparison.returncode, 0,
            f"Horizontal flip pixels differ: "
            f"{comparison.stderr}",
        )

    def test_vertical_flip_pixels(self):
        outputs = self.invoke("flip")

        expected = self.path / "expected.png"
        result = run(
            "magick",
            self.source,
            "-flip",
            expected,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        comparison = run(
            "compare",
            "-metric", "AE",
            expected,
            outputs[-1],
            "null:",
        )
        self.assertEqual(
            comparison.returncode, 0,
            f"Vertical flip pixels differ: "
            f"{comparison.stderr}",
        )

    def test_collision_protection(self):
        first = self.invoke("flop")
        count_before = len(first)

        second = self.invoke("flop")

        self.assertGreater(
            len(second),
            count_before,
            "Repeated flip did not create another file",
        )

        self.assertEqual(
            sha256(self.source),
            self.original_hash,
        )

        for output in second:
            self.assertGreater(output.stat().st_size, 0)

    def test_png_format_preserved(self):
        outputs = self.invoke("flop")

        result = run(
            "identify",
            "-format", "%m %w %h",
            outputs[-1],
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "PNG 37 23")



class RotateReleaseTests(unittest.TestCase):
    """Actual rotation, format preservation and collision tests."""

    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.use_real_transform()
        self.w.env["KIM_POLICY"] = "create"
        self.w.env["KIM_NAME_AFFIX_POSITION"] = "suffix"
        self.directory = self.w.path("input")
        self.directory.mkdir()
        self.source = self.directory / "rotation_fixture.png"

        result = run(
            "magick", "-size", "37x23", "xc:white",
            "-fill", "red",
            "-draw", "rectangle 0,0 11,22",
            "-fill", "blue",
            "-draw", "rectangle 12,0 36,7",
            f"PNG:{self.source}",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        self.original_hash = sha256(self.source)

    def rotate(self, angle):
        before = set(self.directory.glob("*.png"))

        result = self.w.dispatch(
            "rotate", "--angle", str(angle), "--", self.source,
        )

        self.assertEqual(
            result.returncode, 0,
            f"Rotate {angle} failed: {result.stderr}"
        )
        self.assertEqual(
            sha256(self.source),
            self.original_hash,
            "Rotation changed the original image",
        )

        new_files = set(self.directory.glob("*.png")) - before
        self.assertEqual(
            len(new_files), 1,
            f"Expected one new rotated image: {new_files}",
        )
        return next(iter(new_files))

    def test_rotate_90(self):
        self.verify_rotation(90, "23 37")

    def test_rotate_180(self):
        self.verify_rotation(180, "37 23")

    def test_rotate_270(self):
        self.verify_rotation(270, "23 37")

    def verify_rotation(self, angle, dimensions):
        output = self.rotate(angle)

        info = run(
            "identify", "-format", "%m %w %h", output
        )
        self.assertEqual(info.returncode, 0, info.stderr)
        self.assertEqual(info.stdout, "PNG " + dimensions)

        expected = self.directory / "reference.png"
        reference = run(
            "magick", self.source,
            "-rotate", str(angle),
            f"PNG:{expected}",
        )
        self.assertEqual(
            reference.returncode, 0, reference.stderr
        )

        comparison = run(
            "compare", "-metric", "AE",
            expected, output, "null:",
        )
        self.assertEqual(
            comparison.returncode, 0,
            f"Rotation {angle} differs: {comparison.stderr}",
        )

    def test_rotate_collision(self):
        first = self.rotate(90)
        first_hash = sha256(first)

        second = self.rotate(90)

        self.assertNotEqual(first, second)
        self.assertEqual(sha256(first), first_hash)
        self.assertEqual(sha256(self.source), self.original_hash)


class WebExportFunctionalTests(unittest.TestCase):
    """Execute all twelve Web Export menu presets."""

    FORMATS = {
        "jpg": "JPEG",
        "png": "PNG",
        "webp": "WEBP",
        "avif": "HEIC",
    }
    SIZES = {
        "1600x1600": (960, 540),
        "800x800": (800, 450),
        "128x128": (128, 72),
    }

    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)

        self.directory = self.w.root
        self.source = self.w.path("web_fixture.png")
        self.destination = self.w.path("exports")
        self.destination.mkdir()

        result = run(
            "magick",
            "-size", "960x540",
            "gradient:red-blue",
            f"PNG:{self.source}",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        self.original_hash = sha256(self.source)

        self.w.env["KIM_POLICY"] = "create"
        self.w.env["KIM_NAME_AFFIX_POSITION"] = "suffix"

        # Use the existing real-image and simulated-dialog adapters.
        self.w.use_real_web_email()
        self.w.use_real_metadata_tools()

    def tearDown(self):
        # Workspace cleanup is registered with addCleanup().
        pass

    def export(self, fmt, size):
        before = set(self.destination.iterdir())

        result = self.w.dispatch(
            "webexport",
            "--size", size,
            "--format", fmt,
            "--quality", "90",
            "--output-dir", self.destination,
            "--", self.source,
        )

        self.assertEqual(
            result.returncode, 0,
            f"Web Export {fmt}/{size} failed:\n"
            f"stdout: {result.stdout}\n"
            f"stderr: {result.stderr}\n"
            f"calls: {result.calls}",
        )

        self.assertEqual(
            sha256(self.source),
            self.original_hash,
            "Web Export changed the original image",
        )

        new_files = set(self.destination.iterdir()) - before

        self.assertEqual(
            len(new_files), 1,
            f"Expected one new {fmt} export: {new_files}",
        )

        return next(iter(new_files))

    def test_all_twelve_presets(self):
        for fmt in self.FORMATS:
            for size, dimensions in self.SIZES.items():
                with self.subTest(format=fmt, size=size):
                    output = self.export(fmt, size)

                    self.assertEqual(
                        output.suffix.lower(),
                        "." + fmt,
                    )
                    self.assertGreater(output.stat().st_size, 0)

                    info = run(
                        "identify", "-format",
                        "%m %w %h", output,
                    )
                    self.assertEqual(
                        info.returncode, 0, info.stderr
                    )

                    actual_format, width, height = (
                        info.stdout.split()
                    )

                    if fmt == "avif":
                        self.assertIn(
                            actual_format, ("HEIC", "AVIF")
                        )
                    else:
                        self.assertEqual(
                            actual_format,
                            self.FORMATS[fmt],
                        )

                    self.assertEqual(
                        (int(width), int(height)),
                        dimensions,
                    )

                    # Web exports must not carry source
                    # comments or ordinary descriptive tags.
                    metadata = run(
                        "exiftool", "-s3",
                        "-Comment",
                        "-Description",
                        "-ImageDescription",
                        "-GPSLatitude",
                        "-GPSLongitude",
                        output,
                    )
                    self.assertEqual(
                        metadata.returncode, 0,
                        metadata.stderr,
                    )
                    self.assertEqual(
                        metadata.stdout.strip(), "",
                        f"Unexpected web metadata: "
                        f"{metadata.stdout}",
                    )

    def test_web_export_collision(self):
        first = self.export("png", "800x800")
        original_export_hash = sha256(first)

        second = self.export("png", "800x800")

        self.assertNotEqual(first, second)
        self.assertEqual(
            sha256(first),
            original_export_hash,
            "Existing export was overwritten",
        )
        self.assertEqual(
            sha256(self.source),
            self.original_hash,
        )

    def test_source_metadata_not_copied(self):
        tag = run(
            "exiftool", "-overwrite_original",
            "-Comment=KIM6_RELEASE_TEST_MARKER",
            self.source,
        )
        self.assertEqual(
            tag.returncode, 0, tag.stderr
        )

        self.original_hash = sha256(self.source)

        source_metadata = run(
            "exiftool", "-s3", "-Comment", self.source
        )
        self.assertIn(
            "KIM6_RELEASE_TEST_MARKER",
            source_metadata.stdout,
        )

        output = self.export("jpg", "800x800")
        exported_metadata = run(
            "exiftool", "-s3", "-Comment", output
        )
        self.assertEqual(
            exported_metadata.returncode, 0,
            exported_metadata.stderr,
        )
        self.assertNotIn(
            "KIM6_RELEASE_TEST_MARKER",
            exported_metadata.stdout,
        )


if __name__ == "__main__":
    print(f"KIM6 root: {ROOT}", flush=True)
    print(f"Installed dispatcher: {DISPATCHER}", flush=True)
    unittest.main(verbosity=2)
