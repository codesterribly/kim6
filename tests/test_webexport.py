"""K11: web exports are distinct outputs, independent of edit policy."""
import base64
import unittest

from support import Workspace


class WebExportTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)

    def export_into_source_directory(self, policy):
        source = self.workspace.ppm("images/photo 雪.ppm")
        occupied = self.workspace.ppm("images/photo 雪_web.ppm")
        before = {path.name: self.workspace.observe(path) for path in (source, occupied)}
        if policy is not None:
            self.workspace.env["KIM_POLICY"] = policy
        self.workspace.env["KIM_WEB_FORMAT"] = "keep"
        self.workspace.respond_to("kdialog", "--inputbox", [
            {"stdout": "3x2\n"}, {"stdout": "75\n"},
        ])
        payload = source.read_bytes()
        self.workspace.respond("magick", output_base64=base64.b64encode(payload).decode())
        result = self.workspace.dispatch("webexport", source.parent, source)
        after = {path.name: self.workspace.observe(path) for path in (source, occupied)}
        self.assertEqual(after, before, "source or occupied export was replaced")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.outputs), 1, "a distinct export must be produced")
        name, content = next(iter(result.outputs.items()))
        output = self.workspace.path(name)
        self.assertEqual(output.parent, source.parent)
        self.assertEqual(output.suffix, ".ppm")
        self.assertNotIn(output.name, before)
        self.assertEqual(content, payload)
        self.assertFalse([call for call in result.calls
                          if call["tool"] == "kdialog" and "--yesnocancel" in call["argv"]],
                         "web export must not offer an overwrite-original choice")

    def test_failed_publication_preserves_occupied_destinations(self):
        source = self.workspace.ppm("images/photo.ppm")
        occupied = self.workspace.ppm("images/photo_web.ppm")
        before = {path.name: self.workspace.observe(path) for path in (source, occupied)}
        destination = self.workspace.path("images/photo_web_1.ppm")
        sentinel = "destination occupied by another invocation\n"
        self.workspace.env["KIM_WEB_FORMAT"] = "keep"
        self.workspace.respond_to("kdialog", "--inputbox", [
            {"stdout": "3x2\n"}, {"stdout": "75\n"},
        ])
        self.workspace.respond("magick", output_base64=base64.b64encode(source.read_bytes()).decode())
        # Occupy the chosen destination at the atomic no-clobber operation.
        # Both destination files belong to other invocations.
        self.workspace.respond("ln", status=73,
                              writes={"images/photo_web_1.ppm": sentinel})
        result = self.workspace.dispatch("webexport", source.parent, source)
        self.assertTrue(any(event["tool"] == "ln" and event["status"] == 73
                            for event in result.events), "publication failure was not reached")
        self.assertEqual({path.name: self.workspace.observe(path) for path in (source, occupied)},
                         before)
        self.assertTrue(destination.exists(), "failed publication deleted the occupied destination")
        self.assertEqual(destination.read_text(), sentinel)
        producer = next(event for event in result.events if event["tool"] == "magick")
        self.assertEqual(producer["status"], 0)
        temporary = producer["output"]
        self.assertFalse(self.workspace.path(temporary).exists(), "temporary export leaked")
        cleanup = [call for call in result.calls if call["tool"] == "rm"]
        self.assertTrue(any(temporary in call["argv"] for call in cleanup))
        self.assertFalse(any(str(destination) in call["argv"] or str(occupied) in call["argv"]
                             for call in cleanup), "cleanup must only remove invocation-owned files")

    def test_create_exports_distinctly_into_source_directory(self):
        self.export_into_source_directory("create")

    def test_overwrite_policy_exports_distinctly_into_source_directory(self):
        self.export_into_source_directory("overwrite")

    def test_unset_policy_exports_without_overwrite_original_prompt(self):
        self.export_into_source_directory(None)


if __name__ == "__main__":
    unittest.main()
