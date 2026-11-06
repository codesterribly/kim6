"""Create, cancel, and explicitly authorize rotation/reflection publication."""

import base64
from pathlib import Path
import shutil
import subprocess
import unittest

from support import Workspace


class InPlaceAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)

        self.source = self.w.ppm("input/original.ppm")
        self.before = self.w.observe(self.source)
        for tool in ("magick", "identify", "exiftool"):
            self.assertIsNotNone(shutil.which(tool), tool)
        self.w.use_real_transform()

        # This suite tests publication authorization, not Qt rendering.
        # Approve only the required preliminary flip review.
        # Unexpected Python helpers must fail closed.
        preview = self.w.bin / 'python3'
        import shlex
        import sys
        preview.write_text(
            "#!/bin/sh\n"
            'if [ "$2" = "flipreview" ]; then\n'
            "  exit 0\n"
            "fi\n"
            f'exec {shlex.quote(sys.executable)} "$@"\n'
        )
        preview.chmod(0o700)

    def dispatch(self, command, *options):
        result = self.w.dispatch(
            command, *options, "--", self.source
        )
        self.assertEqual(
            self.w.observe(self.source), self.before
        )
        return result

    def assert_clean(self):
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))
        self.assertFalse(list(self.w.root.rglob(".kim6-publish.lock")))
        self.assertEqual(list((self.w.control / "tmp").iterdir()), [])

    def assert_preserved(self, result, added=()):
        for name, state in result.before_entries.items():
            if state.kind != "directory":
                self.assertEqual(result.after_entries.get(name), state, name)
        self.assertEqual(
            set(result.after_entries),
            set(result.before_entries) | {
                str(path.relative_to(self.w.root)) for path in added
            },
        )
        self.assert_clean()

    def assert_dialogs(self, result, expected):
        dialogs = [c for c in result.calls if c["tool"] == "kdialog"]
        stages = [
            flag for c in dialogs
            for flag in ("--radiolist", "--warningyesno")
            if flag in c["argv"]
        ]
        self.assertEqual(stages, expected, result.calls)
        if "--radiolist" in stages:
            choice = next(c for c in dialogs if "--radiolist" in c["argv"])
            self.assertEqual(choice["argv"][-6:], [
                "create", "Create new files (originals untouched)", "on",
                "review", "Overwrite originals (confirmation required)", "off",
            ])
        if "--warningyesno" in stages:
            warning = next(c for c in dialogs if "--warningyesno" in c["argv"])
            self.assertIn("Yes, overwrite selected originals", warning["argv"])

    def assert_cancelled_before_processing(self, result, stages):
        self.assertNotEqual(result.returncode, 0, result.events)
        self.assert_dialogs(result, stages)
        self.assertFalse(any(
            c["tool"] in ("magick", "identify", "exiftool", "ln", "mv", "cp")
            or "--progressbar" in c["argv"]
            for c in result.calls
        ), result.calls)
        self.assertEqual(result.outputs, {})
        self.assert_preserved(result)

    def pixels(self, path):
        image = subprocess.run(
            [shutil.which("magick"), str(path), "-depth", "8", "rgb:-"],
            check=True, capture_output=True, timeout=10,
        )
        colors = [bytes.fromhex(c) for c in (
            "ff0000", "00ff00", "0000ff", "ffff00", "ff00ff", "00ffff",
        )]
        return [colors.index(image.stdout[n:n + 3])
                for n in range(0, len(image.stdout), 3)]

    def assert_rendered(self, result, count=1):
        renders = [e for e in result.events if e["tool"] == "magick"]
        self.assertEqual(len(renders), count, result.events)
        self.assertEqual([e["status"] for e in renders], [0] * count, renders)
        for event in renders:
            staged = Path(event["argv"][-1].split(":", 1)[1])
            self.assertTrue(staged.parent.name.startswith(".kim6-stage."))
            self.assertEqual(staged.parent.parent, self.source.parent)
            self.assertNotEqual(staged, self.source)

    def assert_created(self, result, expected, pixels):
        self.assertEqual(result.returncode, 0, result.events)
        self.assert_rendered(result)
        self.assertEqual(set(result.outputs), {
            str(expected.relative_to(self.w.root))
        })
        publications = [e for e in result.events if e["tool"] == "ln"]
        self.assertEqual(len(publications), 1, result.events)
        self.assertEqual(publications[0]["status"], 0)
        self.assertEqual(publications[0]["argv"][:2], ["-T", "--"])
        self.assertEqual(publications[0]["argv"][-1], str(expected))
        self.assertFalse(any(c["tool"] in ("mv", "cp") for c in result.calls))
        state = self.w.observe(expected)
        self.assertEqual(state.kind, "file")
        self.assertNotEqual(state.inode, self.before.inode)
        self.assertEqual(self.pixels(expected), pixels)
        self.assert_preserved(result, (expected,))

    def test_create_policy_rotates_to_distinct_available_destination(self):
        self.w.env["KIM_POLICY"] = "create"
        self.w.ppm("input/original_rotated.ppm")
        self.w.path("input/original_rotated_1.ppm").symlink_to(self.source.name)

        result = self.dispatch(
            "rotate", "--angle", "90"
        )

        self.assert_dialogs(result, [])
        self.assert_created(result, self.w.path("input/original_rotated_2.ppm"),
                            [3, 0, 4, 1, 5, 2])

    def test_default_prompt_cancellation_refuses_flip(self):
        # No policy variable means prompt, but the adapter's unscripted radio
        # response selects Create; cancellation must be injected explicitly.
        self.w.respond_to("kdialog", "--radiolist", {
            "status": 1, "stdout": "review\n",
        })
        self.w.respond_to("kdialog", "--warningyesno", {"status": 0})

        result = self.dispatch(
            "flipflop", "flip"
        )

        self.assert_cancelled_before_processing(result, ["--radiolist"])

    def test_legacy_overwrite_cannot_bypass_confirmation(self):
        self.w.env["KIM_POLICY"] = "overwrite"
        # Exercise auto-orientation rather than the no-orientation skip path.
        self.w.respond_to("exiftool", "-Orientation", {"stdout": "6\n"})

        result = self.dispatch(
            "rotate", "--exif"
        )

        # Unknown policy falls back to prompt, whose actual default is Create.
        self.assert_dialogs(result, ["--radiolist"])
        self.assert_created(result, self.w.path("input/original_auto_rotated.ppm"),
                            [0, 1, 2, 3, 4, 5])

    def test_prompt_can_explicitly_select_derivatives(self):
        self.w.env["KIM_POLICY"] = "prompt"
        self.w.respond_to("kdialog", "--radiolist", {"stdout": "create\n"})
        self.w.respond_to("kdialog", "--warningyesno", {"status": 0})

        result = self.dispatch("flipflop", "flop")

        self.assert_dialogs(result, ["--radiolist"])
        self.assert_created(result, self.w.path("input/original_flipped_horizontal.ppm"),
                            [2, 1, 0, 5, 4, 3])

    def test_warning_approval_alone_cannot_authorize_processing(self):
        self.w.respond_to("kdialog", "--warningyesno", {"status": 0})
        for choice in ("", "cancel\n", "overwrite\n"):
            with self.subTest(choice=choice):
                self.w.respond_to("kdialog", "--radiolist", {"stdout": choice})
                result = self.dispatch("flipflop", "flip")
                self.assert_cancelled_before_processing(result, ["--radiolist"])

    def test_unsupported_policies_require_both_approval_stages(self):
        for policy in ("overwrite", "unsupported"):
            with self.subTest(policy=policy):
                self.w.env["KIM_POLICY"] = policy
                self.w.respond_to("kdialog", "--radiolist", {"stdout": "review\n"})
                self.w.respond_to("kdialog", "--warningyesno", {"status": 1})
                result = self.dispatch("rotate", "--angle", "90")
                self.assert_cancelled_before_processing(
                    result, ["--radiolist", "--warningyesno"]
                )

    def test_refusing_final_confirmation_preserves_source(self):
        self.w.respond_to(
            "kdialog", "--radiolist",
            {"stdout": "review\n"}
        )
        self.w.respond_to(
            "kdialog", "--warningyesno",
            {"status": 1}
        )

        result = self.dispatch(
            "flipflop", "flop"
        )

        self.assert_cancelled_before_processing(
            result, ["--radiolist", "--warningyesno"]
        )

    def test_confirmation_occurs_once_for_batch(self):
        second = self.w.ppm("input/second.ppm")

        self.w.respond_to(
            "kdialog", "--radiolist",
            {"stdout": "review\n"}
        )
        self.w.respond_to(
            "kdialog", "--warningyesno",
            {"status": 0}
        )

        result = self.w.dispatch(
            "flipflop", "flip", "--",
            self.source, second
        )
        self.assertEqual(result.returncode, 0, result.events)
        self.assert_dialogs(result, ["--radiolist", "--warningyesno"])
        self.assert_rendered(result, count=2)
        warning_index = next(i for i, c in enumerate(result.calls)
                             if "--warningyesno" in c["argv"])
        processing_index = next(i for i, c in enumerate(result.calls)
                                if c["tool"] == "identify")
        self.assertLess(warning_index, processing_index)
        for path in (self.source, second):
            self.assertEqual(self.pixels(path), [3, 4, 5, 0, 1, 2])
            name = str(path.relative_to(self.w.root))
            self.assertNotEqual(result.before_entries[name].inode,
                                result.after_entries[name].inode)
        self.assertEqual(set(result.outputs), {"input/original.ppm", "input/second.ppm"})
        self.assertEqual(set(result.before_entries), set(result.after_entries))
        replacements = [e for e in result.events if e["tool"] == "mv"
                        and e["argv"][:2] == ["--no-copy", "-fT"]]
        self.assertEqual([e["status"] for e in replacements], [0, 0], result.events)
        self.assertFalse(any(c["tool"] in ("ln", "cp") for c in result.calls))
        self.assert_clean()

    def test_selected_links_cannot_bypass_explicitly_approved_replacement(self):
        self.w.approve_overwrite()
        alias = self.w.path("input/alias.ppm")
        for kind in ("symlink", "hardlink"):
            with self.subTest(kind=kind):
                alias.unlink(missing_ok=True)
                if kind == "symlink":
                    alias.symlink_to(self.source.name)
                else:
                    alias.hardlink_to(self.source)
                result = self.w.dispatch("flipflop", "flip", "--", alias)
                self.assertNotEqual(result.returncode, 0, result.events)
                self.assert_dialogs(result, ["--radiolist", "--warningyesno"])
                self.assertFalse(any(
                    c["tool"] in ("magick", "identify", "ln", "mv")
                    for c in result.calls
                ), result.calls)
                self.assertEqual(result.outputs, {})
                self.assert_preserved(result)
                alias.unlink()

    def test_failed_render_preserves_approved_original_and_cleans_partial_output(self):
        self.w.approve_overwrite()
        self.w.respond("magick", status=19, stdout="3 2\n",
                       output_base64=base64.b64encode(b"partial image").decode())

        result = self.dispatch("flipflop", "flip")

        self.assertNotEqual(result.returncode, 0, result.events)
        self.assert_dialogs(result, ["--radiolist", "--warningyesno"])
        renders = [e for e in result.events if e["tool"] == "magick"]
        self.assertEqual([e["status"] for e in renders], [19], result.events)
        self.assertIn("output", renders[0])
        self.assertFalse(any(c["tool"] in ("ln", "mv", "cp") for c in result.calls))
        self.assertEqual(result.outputs, {})
        self.assert_preserved(result)

    def test_failed_publication_preserves_approved_original_and_cleans_stage(self):
        self.w.approve_overwrite()
        self.w.respond_to("mv", "--no-copy", {"status": 74})

        result = self.dispatch("rotate", "--angle", "90")

        self.assertNotEqual(result.returncode, 0, result.events)
        self.assert_dialogs(result, ["--radiolist", "--warningyesno"])
        self.assert_rendered(result)
        replacements = [e for e in result.events if e["tool"] == "mv"
                        and "--no-copy" in e["argv"]]
        self.assertEqual([e["status"] for e in replacements], [74], result.events)
        self.assertFalse(any(c["tool"] in ("ln", "cp") for c in result.calls))
        self.assertEqual(result.outputs, {})
        self.assert_preserved(result)


if __name__ == "__main__":
    unittest.main()
