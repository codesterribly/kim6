"""Selection counts and destructive-target descriptions before publication."""

from pathlib import Path
import unittest

from support import Workspace

SCRIPT = Path(__file__).resolve().parents[1] / "src/bin/kim_all"


class PolicyOutputContextTests(unittest.TestCase):
    def test_source_modification_actions_require_batch_authorization(self):
        operations = (
            ("compress", ("--quality", "65", "--"),
             "Yes, overwrite selected originals"),
            ("resize", ("--size", "100x100", "--"),
             "Yes, overwrite selected originals"),
            ("convert", ("jpg",),
             "Yes, overwrite existing files"),
        )

        for name, options, confirm_label in operations:
            with self.subTest(action=name):
                w = Workspace()
                try:
                    one = w.jpeg("input/one.jpg")
                    two = w.jpeg("input/two.jpg")
                    before = (w.observe(one), w.observe(two))

                    w.env["KIM_POLICY"] = "prompt"
                    w.respond_to(
                        "kdialog", "--radiolist",
                        {"stdout": "review\n"},
                    )
                    w.respond_to(
                        "kdialog", "--warningyesno",
                        {"status": 1},
                    )

                    result = w.dispatch(name, *options, one, two)

                    dialogs = [
                        c for c in result.calls
                        if c["tool"] == "kdialog"
                    ]
                    choices = [
                        c for c in dialogs
                        if "--radiolist" in c["argv"]
                    ]
                    warnings = [
                        c for c in dialogs
                        if "--warningyesno" in c["argv"]
                    ]

                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(len(choices), 1, result.events)
                    self.assertEqual(len(warnings), 1, result.events)

                    self.assertIn(
                        "Selected files: 2",
                        " ".join(choices[0]["argv"]),
                    )
                    self.assertIn(
                        "Selected files: 2",
                        " ".join(warnings[0]["argv"]),
                    )
                    self.assertIn(
                        confirm_label,
                        " ".join(warnings[0]["argv"]),
                    )

                    self.assertEqual(
                        (w.observe(one), w.observe(two)),
                        before,
                    )
                    self.assertFalse(any(
                        c["tool"] == "magick"
                        for c in result.calls
                    ))
                finally:
                    w.close()

    def test_derived_output_calls_identify_output_replacement(self):
        src = SCRIPT.read_text()

        action_names = (
            "action_album",
            "action_contactsheet",
            "action_print",
            "action_tiffjoin",
            "action_animate",
            "collage_render_layout",
            "action_collage",
        )

        for name in action_names:
            with self.subTest(action=name):
                opening = (
                    f"{name}() (\n"
                    if name == "collage_render_layout"
                    else f"{name}() {{\n"
                )
                closing = (
                    "\n)\n"
                    if name == "collage_render_layout"
                    else "\n}\n"
                )

                begin = src.index(opening)
                end = src.index(closing, begin)
                body = src[begin:end]

                self.assertEqual(body.count("choose_output_mode"), 1)
                self.assertIn('"${#files[@]}" output)', body)


if __name__ == "__main__":
    unittest.main()
