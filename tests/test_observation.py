"""Passing checks for K02 observation and failure-injection infrastructure."""
import os
import base64
import unittest

from support import Workspace


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)

    def test_observation_distinguishes_truncation_replacement_and_deletion(self):
        path = self.workspace.ppm("input/photo.ppm")
        original = self.workspace.observe(path)
        self.assertTrue(original.exists)
        self.assertEqual(original.kind, "file")
        self.assertEqual(len(original.sha256), 64)
        path.write_bytes(b"short")
        truncated = self.workspace.observe(path)
        self.assertEqual(truncated.inode, original.inode)
        self.assertLess(truncated.size, original.size)
        self.assertNotEqual(truncated.sha256, original.sha256)
        replacement = self.workspace.ppm("replacement.ppm")
        replacement.replace(path)
        replaced = self.workspace.observe(path)
        self.assertNotEqual(replaced.inode, original.inode)
        self.assertEqual(replaced.sha256, original.sha256)
        path.unlink()
        self.assertFalse(self.workspace.observe(path).exists)

    def test_observation_keeps_symlink_identity_and_nanosecond_mtime(self):
        first = self.workspace.ppm("first.ppm")
        second = self.workspace.ppm("second.ppm")
        link = self.workspace.path("link.ppm")
        link.symlink_to(first.name)
        before = self.workspace.observe(link)
        self.assertEqual(before.kind, "symlink")
        self.assertEqual(before.link_target, "first.ppm")
        self.assertIsNone(before.sha256)
        link.unlink()
        link.symlink_to(second.name)
        self.assertNotEqual(self.workspace.observe(link), before)
        os.utime(first, ns=(1_600_000_000_000_000_000, 1_600_000_001_123_456_789))
        first.chmod(0o640)
        state = self.workspace.observe(first)
        self.assertEqual(state.mtime_ns, 1_600_000_001_123_456_789)
        self.assertEqual(state.mode, 0o640)

    def test_producer_can_write_its_actual_output_then_fail(self):
        output = self.workspace.path("out/producer.ppm")
        self.workspace.respond("magick", output_base64=base64.b64encode(b"partial\x00").decode(),
                               status=23, stderr="injected producer failure\n")
        result = self.workspace.command("magick", "--", "unused", str(output))
        self.assertEqual(output.read_bytes(), b"partial\x00")
        self.assertEqual(result.returncode, 23)
        self.assertEqual(result.events[-1]["status"], 23)
        self.assertEqual(result.events[-1]["output"], str(output))

    def test_filesystem_fault_can_fail_one_call_then_use_normal_adapter(self):
        self.workspace.sequence("mktemp", [
            {"status": 73, "stderr": "injected allocation failure\n"},
            {"passthrough": True},
        ])
        failed = self.workspace.command("mktemp", str(self.workspace.path("stage_XXXXXX")))
        succeeded = self.workspace.command("mktemp", str(self.workspace.path("stage_XXXXXX")))
        self.assertEqual(failed.returncode, 73)
        self.assertEqual(succeeded.returncode, 0, succeeded.stderr)
        self.assertTrue(succeeded.stdout.strip())
        self.assertTrue(self.workspace.path(succeeded.stdout.strip()).is_file())

    def test_result_reports_deleted_entries_and_metadata_only_changes(self):
        source = self.workspace.ppm("source.ppm")
        deleted = self.workspace.command("rm", "--", str(source))
        before, after = deleted.changed_entries["source.ppm"]
        self.assertTrue(before.exists)
        self.assertFalse(after.exists)
        first = self.workspace.ppm("first.ppm")
        reference = self.workspace.ppm("reference.ppm")
        os.utime(reference, ns=(1_600_000_000_000_000_000, 1_600_000_002_000_000_000))
        changed = self.workspace.command("touch", "-r", str(reference), str(first))
        before, after = changed.changed_entries["first.ppm"]
        self.assertEqual(before.sha256, after.sha256)
        self.assertNotEqual(before.mtime_ns, after.mtime_ns)

    def test_dialog_injections_do_not_depend_on_policy_prompt_order(self):
        self.workspace.respond_to("kdialog", "--inputbox", [
            {"stdout": "3x2\n"}, {"stdout": "75\n"},
        ])
        self.workspace.respond_to("kdialog", "--yesnocancel", {"status": 1})
        progress = self.workspace.command("kdialog", "--progressbar", "Working", "2")
        size = self.workspace.command("kdialog", "--inputbox", "Size", "")
        quality = self.workspace.command("kdialog", "--inputbox", "Quality", "")
        policy = self.workspace.command("kdialog", "--yesnocancel", "Policy")
        self.assertEqual(progress.stdout, "org.kde.kdialog-test /ProgressDialog\n")
        self.assertEqual(size.stdout, "3x2\n")
        self.assertEqual(quality.stdout, "75\n")
        self.assertEqual(policy.returncode, 1)

    def test_dangling_symlink_remains_an_observable_existing_entry(self):
        link = self.workspace.path("dangling.jpg")
        link.symlink_to("missing.jpg")
        state = self.workspace.observe(link)
        self.assertTrue(state.exists)
        self.assertEqual(state.kind, "symlink")
        self.assertEqual(state.link_target, "missing.jpg")
        self.assertIsNone(state.sha256)


if __name__ == "__main__":
    unittest.main()
