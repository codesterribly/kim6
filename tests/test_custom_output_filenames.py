"""Focused tests for configurable output filename labels."""

import ast
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "src/bin/kim_all"
UI = ROOT / "src/bin/kim_settings_dialog.py"


def function(name):
    lines = RUNTIME.read_text().splitlines(keepends=True)
    i = lines.index(name + "() {\n")
    j = lines.index("}\n", i + 1)
    return "".join(lines[i:j + 1])


HELPERS = "\n".join(map(function, (
    "kim6_known_affix_key",
    "kim6_affix_value",
    "affixed_filename",
    "kim6_load_user_settings",
    "video_utility_target",
)))


def run(command, **env):
    p = subprocess.run(
        ["bash", "-c", "set -e\n" + HELPERS + "\n" + command],
        env={**os.environ, **env},
        text=True,
        capture_output=True,
        timeout=10,
    )
    if p.returncode:
        raise AssertionError(p.stderr)
    return p.stdout.strip().splitlines()


def settings():
    tree = ast.parse(UI.read_text())
    selected = []

    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id in {
                "AFFIX_ITEMS", "AFFIX_DEFAULTS", "AFFIX_PATTERN",
                "DEFAULTS", "VALID_POLICIES", "VALID_AFFIXES"
            }
            for t in node.targets
        ):
            selected.append(node)

        if isinstance(node, ast.FunctionDef) and node.name in {
            "load_settings", "save_settings"
        }:
            selected.append(node)

    scope = {"re": re, "os": os, "tempfile": tempfile}
    module = ast.Module(body=selected, type_ignores=[])
    exec(compile(module, str(UI), "exec"), scope)
    return scope


class OutputFilenameTests(unittest.TestCase):

    def test_all_defaults_and_positions(self):
        config = settings()
        self.assertEqual(len(config["AFFIX_ITEMS"]), 21)

        for tag, _, ext, joiner in config["AFFIX_ITEMS"]:
            key = "KIM_AFFIX_" + tag.upper().replace("-", "_")
            self.assertEqual(config["DEFAULTS"][key], tag)

            for pos, name in (
                ("suffix", f"photo{joiner}{tag}.{ext}"),
                ("prefix", f"{tag}{joiner}photo.{ext}"),
            ):
                self.assertEqual(
                    run(
                        f'affixed_filename photo "{tag}" "{ext}" "" "_" "{joiner}"',
                        **{key: tag, "KIM_NAME_AFFIX_POSITION": pos}
                    ),
                    [name],
                )

    def test_custom_numbers_compounds_and_frames(self):
        self.assertEqual(
            run(
                "affixed_filename photo compressed jpg 2",
                KIM_AFFIX_COMPRESSED="com"
            ),
            ["photo_com_2.jpg"],
        )

        self.assertEqual(
            run(
                "affixed_filename photo compressed jpg 2",
                KIM_AFFIX_COMPRESSED="com",
                KIM_NAME_AFFIX_POSITION="prefix",
            ),
            ["com_photo_2.jpg"],
        )

        self.assertEqual(
            run(
                "affixed_filename photo gps_ai png",
                KIM_AFFIX_GPS="loc",
                KIM_AFFIX_AI="gen",
            ),
            ["photo_loc_gen.png"],
        )

        self.assertEqual(
            run(
                "affixed_filename clip frame-00-01-30 png",
                KIM_AFFIX_FRAME="snap",
            ),
            ["clip_snap-00-01-30.png"],
        )

    def test_rejects_unicode_and_unsafe_labels(self):
        for value in (
            "é", "../evil", "/tmp", "a.b", "a b", "", "x" * 33
        ):
            self.assertEqual(
                run(
                    "affixed_filename photo compressed jpg",
                    KIM_AFFIX_COMPRESSED=value,
                ),
                ["photo_compressed.jpg"],
            )

    def test_saved_settings_validation_and_precedence(self):
        config = settings()

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kim6/settings.conf"
            values = config["DEFAULTS"].copy()
            values["KIM_AFFIX_COMPRESSED"] = "com"
            values["KIM_AFFIX_AUDIO"] = "sound"

            config["save_settings"](path, values)

            self.assertEqual(
                config["load_settings"](path)["KIM_AFFIX_COMPRESSED"],
                "com",
            )
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

            self.assertEqual(
                run(
                    "kim6_load_user_settings; "
                    "affixed_filename photo compressed jpg; "
                    'affixed_filename clip audio mp3 "" "_" "-"',
                    XDG_CONFIG_HOME=directory,
                ),
                ["photo_com.jpg", "clip-sound.mp3"],
            )

            self.assertEqual(
                run(
                    "kim6_load_user_settings; "
                    "affixed_filename photo compressed jpg",
                    XDG_CONFIG_HOME=directory,
                    KIM_AFFIX_COMPRESSED="zip",
                ),
                ["photo_zip.jpg"],
            )

            with path.open("a") as f:
                f.write(
                    "KIM_AFFIX_WEB=é\n"
                    "KIM_AFFIX_AUDIO=$(false)\n"
                )

            self.assertEqual(
                run(
                    "kim6_load_user_settings; "
                    "affixed_filename clip web jpg; "
                    'affixed_filename clip audio mp3 "" "_" "-"',
                    XDG_CONFIG_HOME=directory,
                ),
                ["clip_web.jpg", "clip-sound.mp3"],
            )

    def test_video_separators_and_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "clip.mp4"
            source.write_bytes(b"data")

            self.assertEqual(
                run(
                    f'video_utility_target "{source}" audio mp3 "-"; '
                    'printf "%s\n" "$VIDEO_UTILITY_TARGET"'
                ),
                [str(source.with_name("clip-audio.mp3"))],
            )

        self.assertEqual(
            run('affixed_filename clip transcoded mp4 "" "_" "-"'),
            ["clip-transcoded.mp4"],
        )

        self.assertEqual(
            run("affixed_filename garden web jpg"),
            ["garden_web.jpg"],
        )


if __name__ == "__main__":
    unittest.main()
