"""K02 acceptance tests: ordinary failures intentionally expose production bugs.

Run separately: python3 -B tests/run.py --pattern test_preservation.py
KNOWN_BUG names identify currently broken cases; no expectedFailure/skip masks
them. Producers are controlled external adapters, not real media commands.
"""
import base64
import os
import json
import unittest

from support import Workspace


class PreservationTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)

    def protect(self, *paths):
        for path in paths:
            if not path.is_symlink():
                os.utime(path, ns=(1_600_000_000_000_000_000, 1_600_000_001_123_456_789))
        return {str(path.relative_to(self.workspace.root)): self.workspace.observe(path)
                for path in paths}

    def assert_preserved(self, before):
        after = {name: self.workspace.observe(name) for name in before}
        differences = {
            name: {key: (value, vars(after[name])[key])
                   for key, value in vars(state).items() if value != vars(after[name])[key]}
            for name, state in before.items() if state != after[name]
        }
        self.assertFalse(differences, "preservation violation: " + json.dumps(differences))

    def assert_event(self, result, tool, status):
        matches = [event for event in result.events
                   if event["tool"] == tool and event["status"] == status]
        self.assertTrue(matches, f"intended {tool} status {status} not observed: {result.events}")
        return matches

    def producer(self, tool, payload=None, status=0, **options):
        response = {"status": status, **options}
        if payload is not None:
            response["output_base64"] = base64.b64encode(payload).decode()
        self.workspace.respond(tool, **response)

    def test_KNOWN_BUG_conversion_failure_before_output_keeps_existing_destination(self):
        source = self.workspace.ppm("input/photo 雪.ppm")
        destination = self.workspace.jpeg("input/photo 雪.jpg")
        before = self.protect(source, destination)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        self.producer("magick", status=23, stderr="injected failure before output\n")
        result = self.workspace.dispatch("convert", "jpg", source)
        self.assert_event(result, "magick", 23)
        self.assert_preserved(before)

    def test_KNOWN_BUG_failed_conversion_keeps_destination_symlink(self):
        source = self.workspace.ppm("input/photo.ppm")
        referent = self.workspace.jpeg("retained.jpg")
        destination = self.workspace.path("input/photo.jpg")
        destination.symlink_to("../retained.jpg")
        before = self.protect(source, referent, destination)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        self.producer("magick", status=23)
        result = self.workspace.dispatch("convert", "jpg", source)
        self.assert_event(result, "magick", 23)
        self.assert_preserved(before)

    def test_failed_stage_allocation_preserves_source_and_destination(self):
        source = self.workspace.jpeg("input/source.jpg")
        destination = self.workspace.jpeg("out/existing.jpg")
        before = self.protect(source, destination)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        self.workspace.sequence("mktemp", [{"passthrough": True}, {"status": 73}])
        result = self.workspace.dispatch("resize", "3x2", destination.parent, source)
        self.assert_event(result, "mktemp", 73)
        self.assertFalse([call for call in result.calls if call["tool"] == "magick"])
        self.assert_preserved(before)

    def test_failed_publication_directory_check_preserves_source(self):
        source = self.workspace.jpeg("input/source.jpg")
        before = self.protect(source)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        self.producer("magick", source.read_bytes())
        self.workspace.respond("mkdir", status=73)
        result = self.workspace.dispatch("resize", "3x2", source.parent, source)
        self.assert_event(result, "magick", 0)
        self.assert_event(result, "mkdir", 73)
        self.assert_preserved(before)

    def test_KNOWN_BUG_failed_move_does_not_fall_back_to_overwriting_source(self):
        source = self.workspace.jpeg("input/source.jpg")
        before = self.protect(source)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        self.producer("magick", source.read_bytes())
        self.workspace.respond("mv", status=73)
        result = self.workspace.dispatch("resize", "3x2", source.parent, source)
        self.assert_event(result, "magick", 0)
        self.assert_event(result, "mv", 73)
        fallback = [call for call in result.calls
                    if call["tool"] == "cp" and call["argv"][-1] == str(source)]
        self.assert_preserved(before)
        self.assertFalse(fallback, "failed commit attempted destructive copy fallback")

    def test_KNOWN_BUG_failed_copy_fallback_cannot_truncate_source(self):
        source = self.workspace.jpeg("input/source.jpg")
        before = self.protect(source)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        self.producer("magick", source.read_bytes())
        self.workspace.respond("mv", status=73)
        self.producer("cp", b"truncated during fallback", status=74)
        result = self.workspace.dispatch("resize", "3x2", source.parent, source)
        self.assert_event(result, "mv", 73)
        # Once fixed, avoiding the fallback entirely is the correct outcome.
        # If it is attempted, the adapter must expose the intended copy failure.
        for event in result.events:
            if event["tool"] == "cp":
                self.assertEqual(event["status"], 74)
        self.assert_preserved(before)

    def test_create_conversion_collision_survives_partial_producer_failure(self):
        source = self.workspace.ppm("input/source.ppm")
        destination = self.workspace.jpeg("input/source.jpg")
        before = self.protect(source, destination)
        self.workspace.env["KIM_POLICY"] = "create"
        self.producer("magick", b"partial derivative", status=23)
        result = self.workspace.dispatch("convert", "jpg", source)
        event = self.assert_event(result, "magick", 23)[0]
        self.assertNotEqual(event.get("output"), str(destination))
        self.assert_preserved(before)

    def test_KNOWN_BUG_web_overwrite_default_format_never_replaces_selected_jpeg(self):
        source = self.workspace.jpeg("input/photo.jpg")
        destination = self.workspace.jpeg("out/existing.jpg")
        before = self.protect(source, destination)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        self.workspace.respond_to("kdialog", "--inputbox", [
            {"stdout": "3x2\n"}, {"stdout": "75\n"},
        ])
        self.producer("magick", source.read_bytes())
        result = self.workspace.dispatch("webexport", destination.parent, source)
        self.assert_event(result, "magick", 0)
        self.assert_preserved(before)

    def test_cancel_before_processing_preserves_existing_files(self):
        source = self.workspace.ppm("input/source.ppm")
        destination = self.workspace.jpeg("input/source.jpg")
        before = self.protect(source, destination)
        self.workspace.respond_to("kdialog", "--yesnocancel", {"status": 2})
        result = self.workspace.dispatch("convert", "jpg", source)
        self.assert_event(result, "kdialog", 2)
        self.assertFalse([call for call in result.calls if call["tool"] == "magick"])
        self.assert_preserved(before)

    def test_KNOWN_BUG_cancel_after_producer_output_prevents_source_replacement(self):
        source = self.workspace.jpeg("input/source.jpg")
        before = self.protect(source)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        self.producer("magick", source.read_bytes(), cancel=True)
        result = self.workspace.dispatch("resize", "3x2", source.parent, source)
        event = self.assert_event(result, "magick", 0)[0]
        self.assertTrue(event.get("cancel_requested"), "cancellation injection not reached")
        # A real progress reference is still required: the adapter does NOT
        # accept kim_all's malformed qdbus arguments to manufacture a green test.
        self.assert_preserved(before)


def failed_producer_case(action, payload, status):
    def test(self):
        if action == "convert":
            source = self.workspace.ppm("input/source.ppm")
            destination = self.workspace.jpeg("input/source.jpg")
            arguments = ("convert", "jpg", source)
        else:
            source = self.workspace.jpeg("input/source.jpg")
            destination = self.workspace.jpeg("out/existing.jpg")
            arguments = {"resize": ("resize", "3x2", destination.parent, source),
                         "compress": ("compress", "75", destination.parent, source),
                         "stripmeta": ("stripmeta", source)}[action]
        before = self.protect(source, destination)
        self.workspace.env["KIM_POLICY"] = "overwrite"
        tool = "exiftool" if action == "stripmeta" else "magick"
        self.producer(tool, payload, status=status)
        result = self.workspace.dispatch(*arguments)
        self.assert_event(result, tool, status)
        self.assert_preserved(before)
    return test


# Each generated method receives its own setUp/cleanup and is an ordinary test.
# No producer-validity or metadata policy is inferred from a successful exit.
for action in ("convert", "resize", "compress", "stripmeta"):
    for scenario, payload, status in (
        ("failure_before_output", None, 23),
        ("nonempty_partial_then_failure", b"nonempty partial output", 23),
        ("zero_exit_invalid_output", b"not an image", 0),
        ("zero_exit_incomplete_output", b"\xff\xd8\xff\xe0", 0),
    ):
        if action == "convert" and scenario == "failure_before_output":
            continue  # Explicitly named conversion cleanup regression above.
        classification = "acceptance" if scenario == "failure_before_output" else "KNOWN_BUG"
        setattr(PreservationTests, f"test_{classification}_{action}_{scenario}",
                failed_producer_case(action, payload, status))


def web_case(policy):
    def test(self):
        source = self.workspace.ppm("input/photo 雪.ppm")
        # This selected original is ALSO the first export's default destination.
        selected_destination = self.workspace.ppm("out/photo 雪_web.ppm")
        unrelated = self.workspace.ppm("out/existing export.ppm")
        before = self.protect(source, selected_destination, unrelated)
        self.workspace.env["KIM_WEB_FORMAT"] = "keep"
        answers = [{"stdout": "3x2\n"}, {"stdout": "75\n"}]
        if policy in ("create", "overwrite"):
            self.workspace.env["KIM_POLICY"] = policy
        elif policy == "config_overwrite":
            self.workspace.configure("KIM_POLICY", "overwrite")
        else:
            # If a source-protection fix removes this inappropriate choice,
            # an unused policy response is harmless; preservation is the contract.
            self.workspace.respond_to("kdialog", "--yesnocancel",
                                      {"status": 1 if policy == "prompt_overwrite" else 0})
        self.workspace.respond_to("kdialog", "--inputbox", answers)
        valid_ppm = b"P3\n3 2\n255\n0 0 0 255 0 0 0 255 0\n0 0 255 255 255 0 255 255 255\n"
        self.producer("magick", valid_ppm)
        result = self.workspace.dispatch("webexport", unrelated.parent, source, selected_destination)
        producers = self.assert_event(result, "magick", 0)
        self.assertEqual(len(producers), 2, "both selected originals must be exercised")
        if policy == "config_overwrite":
            self.assertTrue([call for call in result.calls
                             if call["tool"] == "kreadconfig6" and call["argv"][-1] == "KIM_POLICY"])
        self.assert_preserved(before)
        # Refusing all processing must not make source protection pass vacuously.
        exports = {name: content for name, content in result.outputs.items() if name not in before}
        self.assertEqual(len(exports), 2, "two distinct new exports are required")
        self.assertTrue(all(name.startswith("out/") for name in exports))
        self.assertTrue(all(content == valid_ppm for content in exports.values()))
    return test


for policy in ("create", "overwrite", "prompt_create", "prompt_overwrite", "config_overwrite"):
    classification = "KNOWN_BUG" if "overwrite" in policy else "acceptance"
    setattr(PreservationTests, f"test_{classification}_web_{policy}_preserves_all_selected_originals",
            web_case(policy))


if __name__ == "__main__":
    unittest.main()
