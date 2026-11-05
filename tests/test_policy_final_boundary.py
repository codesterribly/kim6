"""Source protection and create-only publication at the final boundary."""

import base64
import shutil
import subprocess
import unittest

from support import Workspace


class FinalPublicationBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.env["KIM_POLICY"] = "prompt"
        self.source = self.w.png("input/original.png")
        self.before = self.w.observe(self.source)

        self.w.respond_to(
            "kdialog", "--radiolist",
            {"stdout": "review\n"},
        )
        self.w.respond_to(
            "kdialog", "--warningyesno",
            {"status": 0},
        )
        # Continue with the fixture image so destination validation is reached.
        self.w.respond_to(
            "kdialog", "--yesnocancel",
            {"status": 1},
        )

    def collage(self, destination, source=None):
        return self.w.dispatch(
            "collage", "--layout", "grid",
            "--canvas", "400x300",
            "--fit", "fit", "--gap", "12",
            "--frame", "none", "--no-shadow",
            "--output", destination,
            "--", source or self.source,
        )

    def render_fixture(self):
        # The existing bounded real-collage adapter accepts PPM input streams.
        # Keep PNG inputs for source/destination alias checks (PNG output).
        for tool in ("magick", "identify"):
            self.assertIsNotNone(shutil.which(tool), tool)
        self.w.use_real_gallery_collage()
        return self.w.ppm("input/selected.ppm")

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
        self.assertFalse(list(self.w.root.rglob(".kim6-stage.*")))
        self.assertFalse(list(self.w.root.rglob(".kim6-publish.lock")))
        self.assertEqual(list((self.w.control / "tmp").iterdir()), [])

    def assert_rendered(self, result):
        renders = [e for e in result.events if e["tool"] == "magick"]
        # Canvas, tile, composition, and final PNG must all really execute.
        self.assertEqual(len(renders), 4, result.events)
        self.assertEqual([e["status"] for e in renders], [0] * 4, renders)
        self.assertTrue(any(
            e["tool"] == "identify" and e["status"] == 0
            and e["argv"][-1].endswith("/output.png")
            for e in result.events
        ), result.events)

    def assert_numbered_publication(self, result, expected):
        self.assertEqual(result.returncode, 0, result.events)
        self.assert_rendered(result)
        self.assertFalse(any(
            flag in c["argv"]
            for c in result.calls if c["tool"] == "kdialog"
            for flag in ("--radiolist", "--warningyesno")
        ), result.calls)
        self.assertEqual(set(result.outputs), {
            str(expected.relative_to(self.w.root))
        })
        publications = [e for e in result.events if e["tool"] == "ln"]
        self.assertEqual(len(publications), 1, result.events)
        self.assertEqual(publications[0]["status"], 0)
        self.assertEqual(publications[0]["argv"][:2], ["-T", "--"])
        self.assertEqual(publications[0]["argv"][-1], str(expected))
        self.assertFalse(any(c["tool"] in ("mv", "cp") for c in result.calls))
        self.assertEqual(self.w.observe(expected).kind, "file")
        image = subprocess.run(
            [shutil.which("identify"), "-format", "%m %w %h", str(expected)],
            check=True, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(image.stdout, "PNG 400 300")
        self.assert_preserved(result, (expected,))

    def assert_rejected_before_rendering(
        self, destination, extra=(),
        error_expected="Collage: invalid or source-aliasing destination.",
    ):
        snapshots = {
            path: self.w.observe(path)
            for path in (self.source, *extra)
        }

        result = self.collage(destination)
        self.assertNotEqual(result.returncode, 0, result.events)

        for path, snapshot in snapshots.items():
            self.assertEqual(self.w.observe(path), snapshot)

        self.assertFalse(any(
            call["tool"] == "kdialog"
            and "--warningyesno" in call["argv"]
            for call in result.calls
        ))
        self.assertTrue(any(
            call["tool"] == "kdialog"
            and "--error" in call["argv"]
            and error_expected in call["argv"]
            for call in result.calls
        ), result.calls)

        self.assertFalse(any(
            call["tool"] == "magick"
            for call in result.calls
        ))
        self.assertFalse(list(
            self.w.root.rglob(".kim6-stage.*")
        ))
        self.assertEqual(result.outputs, {})
        self.assert_preserved(result)

    def test_explicit_approval_does_not_overwrite_selected_original(self):
        self.assert_rejected_before_rendering(self.source)

    def test_hardlink_alias_of_selected_original_cannot_be_overwritten(self):
        target = self.w.path("input/alias.png")
        target.hardlink_to(self.source)

        # Hardlinked inputs are rejected during input preflight.
        self.assert_rejected_before_rendering(
            target, (target,),
            error_expected="Collage: select regular, unambiguous image files.",
        )

    def test_symlink_output_cannot_replace_an_unrelated_file(self):
        source = self.render_fixture()
        protected = self.w.png("input/other.png")
        target = self.w.path("input/symlink.png")
        target.symlink_to(protected.name)
        # Skip occupied numbered destinations too, including dangling links.
        self.w.png("input/symlink_1.png")
        self.w.path("input/symlink_2.png").symlink_to("missing.png")

        result = self.collage(target, source)

        self.assert_numbered_publication(
            result, self.w.path("input/symlink_3.png")
        )
        self.assertEqual(self.w.observe(target).link_target, protected.name)

    def test_regular_file_collision_selects_numbered_output(self):
        source = self.render_fixture()
        target = self.w.png("input/occupied.png")

        result = self.collage(target, source)

        self.assert_numbered_publication(result, self.w.path("input/occupied_1.png"))

    def test_symlink_to_selected_source_cannot_modify_original(self):
        source = self.render_fixture()
        target = self.w.path("input/source-link.png")
        target.symlink_to(source.name)

        result = self.collage(target, source)

        # The link is an occupied entry: publication must use a distinct name.
        self.assert_numbered_publication(result, self.w.path("input/source-link_1.png"))
        self.assertEqual(self.w.observe(target).link_target, source.name)

    def test_failed_render_preserves_collision_and_cleans_partial_output(self):
        source = self.render_fixture()
        protected = self.w.png("input/other.png")
        target = self.w.path("input/symlink.png")
        target.symlink_to(protected.name)
        self.w.respond_to("magick", "-[0]", {
            "status": 19,
            "output_base64": base64.b64encode(b"partial tile").decode(),
        })

        result = self.collage(target, source)

        self.assertNotEqual(result.returncode, 0, result.events)
        renders = [e for e in result.events if e["tool"] == "magick"]
        self.assertEqual([e["status"] for e in renders], [0, 19], result.events)
        self.assertIn("output", renders[1])  # Partial output was actually written.
        self.assertTrue(any(
            "Collage: could not render an image tile." in c["argv"]
            for c in result.calls
        ), result.calls)
        self.assertFalse(any(c["tool"] in ("ln", "mv") for c in result.calls))
        self.assertEqual(result.outputs, {})
        self.assert_preserved(result)

    def test_failed_publication_preserves_collision_and_cleans_rendered_output(self):
        source = self.render_fixture()
        protected = self.w.png("input/other.png")
        target = self.w.path("input/symlink.png")
        target.symlink_to(protected.name)
        numbered = self.w.path("input/symlink_1.png")
        self.w.respond_to("ln", str(numbered), {"status": 74})

        result = self.collage(target, source)

        self.assertNotEqual(result.returncode, 0, result.events)
        self.assert_rendered(result)
        publications = [e for e in result.events if e["tool"] == "ln"]
        self.assertEqual(len(publications), 1, result.events)
        self.assertEqual(publications[0]["argv"][-1], str(numbered))
        self.assertEqual(publications[0]["status"], 74)
        self.assertFalse(any(c["tool"] in ("mv", "cp") for c in result.calls))
        self.assertEqual(result.outputs, {})
        self.assert_preserved(result)

    def test_cancel_after_canvas_preserves_existing_files_and_cleans_stage(self):
        source = self.render_fixture()
        target = self.w.png("input/occupied.png")
        self.w.respond_to("magick", "-size", {
            "passthrough": True, "interrupt": "cancelled",
        })

        result = self.collage(target, source)

        self.assertNotEqual(result.returncode, 0, result.events)
        renders = [e for e in result.events if e["tool"] == "magick"]
        self.assertEqual([e["status"] for e in renders], [0], result.events)
        self.assertFalse(any(c["tool"] in ("ln", "mv") for c in result.calls))
        self.assertEqual(result.outputs, {})
        self.assert_preserved(result)

    def test_collision_after_planning_is_not_clobbered_at_publication(self):
        source = self.render_fixture()
        protected = self.w.png("input/other.png")
        target = self.w.path("input/symlink.png")
        target.symlink_to(protected.name)
        numbered = self.w.path("input/symlink_1.png")
        relative = str(numbered.relative_to(self.w.root))
        payload = "created after filename planning; preserve me"
        self.w.respond_to("magick", "-size", {
            "passthrough": True, "writes": {relative: payload},
        })

        result = self.collage(target, source)

        self.assertNotEqual(result.returncode, 0, result.events)
        self.assert_rendered(result)
        publications = [e for e in result.events if e["tool"] == "ln"]
        self.assertEqual(len(publications), 1, result.events)
        self.assertEqual(publications[0]["argv"][-1], str(numbered))
        self.assertNotEqual(publications[0]["status"], 0, publications)
        self.assertIn("File exists", publications[0].get("error", ""))
        self.assertFalse(any(c["tool"] in ("mv", "cp") for c in result.calls))
        self.assertEqual(result.outputs, {relative: payload.encode()})
        self.assert_preserved(result, (numbered,))

    def test_create_mode_refuses_selected_source_as_output(self):
        self.w.env["KIM_POLICY"] = "create"

        result = self.collage(self.source)

        self.assertNotEqual(result.returncode, 0, result.events)
        self.assertEqual(
            self.w.observe(self.source), self.before
        )
        self.assertFalse(any(
            call["tool"] == "kdialog"
            and "--warningyesno" in call["argv"]
            for call in result.calls
        ))
        self.assertFalse(any(
            call["tool"] == "magick"
            for call in result.calls
        ))
        self.assertFalse(list(
            self.w.root.rglob(".kim6-stage.*")
        ))
        self.assertEqual(result.outputs, {})
        self.assert_preserved(result)


if __name__ == "__main__":
    unittest.main()
