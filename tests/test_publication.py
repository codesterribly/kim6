"""K12: staging and publication through existing dispatcher actions."""
import base64
import json
import os
import signal
import shutil
import tempfile
import subprocess
import unittest
from pathlib import Path
from support import Workspace


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)
        self.source = self.workspace.ppm("input/photo.ppm")
        self.destination = self.workspace.jpeg("input/photo.jpg")
        self.workspace.env["KIM_POLICY"] = "overwrite"

    def produce(self, payload=None, status=0, **options):
        payload = self.destination.read_bytes() if payload is None else payload
        self.workspace.respond("magick", status=status,
                               output_base64=base64.b64encode(payload).decode(), **options)

    def web(self, directory=None):
        self.workspace.env["KIM_WEB_FORMAT"] = "keep"
        self.workspace.respond_to("kdialog", "--inputbox", [
            {"stdout": "3x2\n"}, {"stdout": "75\n"},
        ])
        return self.workspace.dispatch("webexport", directory or self.source.parent, self.source)

    def assert_clean(self):
        self.assertFalse(list(self.workspace.root.rglob(".kim6-stage.*")))
        self.assertFalse(list(self.workspace.root.rglob(".kim6-publish.lock")))
        self.assertEqual(list((self.workspace.control / "tmp").iterdir()), [])

    def test_web_stage_is_private_and_on_destination_filesystem(self):
        self.produce(self.source.read_bytes())
        result = self.web()
        self.assertEqual(result.returncode, 0, result.stderr)
        producer = next(e for e in result.events if e["tool"] == "magick")
        stage = Path(producer["output"])
        self.assertEqual(stage.parent.parent, self.source.parent)
        self.assertTrue(stage.parent.name.startswith(".kim6-stage."))
        allocations = [e for e in result.events if e["tool"] == "mktemp"]
        self.assertTrue(all(e["directory_mode"] == 0o700 for e in allocations))
        self.assertEqual(result.outputs, {"input/photo_web.ppm": self.source.read_bytes()})
        self.assert_clean()


    def convert(self):
        return self.workspace.dispatch("convert", "jpg", self.source)

    def protect(self, *paths):
        return {path: self.workspace.observe(path) for path in paths}

    def assert_preserved(self, before):
        self.assertEqual({path: self.workspace.observe(path) for path in before}, before)

    def test_conversion_failure_before_output_keeps_destination(self):
        before = self.protect(self.source, self.destination)
        self.workspace.respond("magick", status=23)
        result = self.convert()
        self.assertTrue(any(e["tool"] == "magick" and e["status"] == 23 for e in result.events))
        self.assert_preserved(before)
        self.assert_clean()

    def test_conversion_nonempty_failed_output_is_never_published(self):
        before = self.protect(self.source, self.destination)
        self.produce(b"partial bytes", status=23)
        self.convert()
        self.assert_preserved(before)
        self.assert_clean()

    def test_conversion_zero_exit_invalid_output_is_never_published(self):
        before = self.protect(self.source, self.destination)
        self.produce(b"this is not an image")
        result = self.convert()
        self.assertTrue(any(e["tool"] == "identify" and e["status"] != 0 for e in result.events))
        self.assert_preserved(before)
        self.assert_clean()

    def test_conversion_zero_exit_incomplete_output_is_never_published(self):
        before = self.protect(self.source, self.destination)
        self.produce(b"\xff\xd8\xff\xe0")
        self.convert()
        self.assert_preserved(before)
        self.assert_clean()

    def test_supported_overwrite_uses_validated_stage_and_atomic_replacement(self):
        payload = self.destination.read_bytes()
        self.destination.write_bytes(b"preexisting destination")
        self.destination.chmod(0o640)
        os.utime(self.destination, ns=(1_600_000_000_000_000_000, 1_600_000_001_123_456_789))
        before = self.workspace.observe(self.destination)
        self.produce(payload)
        result = self.convert()
        self.assertEqual(self.destination.read_bytes(), payload)
        after = self.workspace.observe(self.destination)
        self.assertNotEqual(after.inode, before.inode)
        self.assertEqual(after.mode, 0o640)
        self.assertGreater(after.mtime_ns, before.mtime_ns)
        producer = next(e for e in result.events if e["tool"] == "magick")
        self.assertEqual(Path(producer["output"]).parent.parent, self.destination.parent)
        self.assertTrue(any(e["tool"] == "identify" and e["status"] == 0 for e in result.events))
        self.assertTrue(any(e["tool"] == "mv" and "--no-copy" in e["argv"]
                            and e["status"] == 0 for e in result.events))
        self.assertFalse(any(e["tool"] == "cp" for e in result.events))
        self.assert_clean()

    def test_unsupported_rename_only_tool_refuses_overwrite(self):
        before = self.protect(self.source, self.destination)
        self.produce()
        self.workspace.respond_to("mv", "--help", {"stdout": "no rename-only support\n"})
        result = self.convert()
        self.assert_preserved(before)
        self.assertFalse(any(e["tool"] == "mv" and "--help" not in e["argv"]
                             and "--version" not in e["argv"] for e in result.events))
        self.assert_clean()

    def test_failed_overwrite_has_no_destructive_copy_fallback(self):
        before = self.protect(self.source, self.destination)
        self.produce()
        self.workspace.respond_to("mv", "--no-copy", {"status": 73})
        self.workspace.respond("cp", output_base64=base64.b64encode(b"truncated").decode(), status=74)
        result = self.convert()
        self.assertTrue(any(e["tool"] == "mv" and e["status"] == 73 for e in result.events))
        self.assertFalse(any(e["tool"] == "cp" for e in result.events))
        self.assert_preserved(before)
        self.assert_clean()

    def test_overwrite_destination_symlink_and_referent_survive(self):
        referent = self.workspace.jpeg("retained.jpg")
        self.destination.unlink()
        self.destination.symlink_to("../retained.jpg")
        before = self.protect(self.source, self.destination, referent)
        self.produce(referent.read_bytes())
        self.convert()
        self.assert_preserved(before)
        self.assert_clean()

    def test_overwrite_dangling_destination_survives(self):
        self.destination.unlink()
        self.destination.symlink_to("missing.jpg")
        before = self.protect(self.source, self.destination)
        self.produce(self.workspace.jpeg("valid.jpg").read_bytes())
        self.convert()
        self.assert_preserved(before)
        self.assertFalse(self.workspace.path("input/missing.jpg").exists())
        self.assert_clean()

    def test_overwrite_hardlinked_destination_is_refused(self):
        alias = self.workspace.path("alias.jpg")
        os.link(self.destination, alias)
        before = self.protect(self.destination, alias)
        self.produce()
        self.convert()
        self.assert_preserved(before)
        self.assert_clean()

    def test_create_collision_uses_distinct_filename(self):
        occupied = self.workspace.ppm("input/photo_web.ppm")
        before = self.protect(occupied, self.source)
        self.produce(self.source.read_bytes())
        result = self.web()
        self.assertEqual(set(result.outputs), {"input/photo_web_1.ppm"})
        self.assert_preserved(before)
        self.assert_clean()

    def test_create_dangling_destination_is_not_replaced(self):
        occupied = self.workspace.path("input/photo_web.ppm")
        occupied.symlink_to("missing.ppm")
        before = self.protect(occupied)
        self.produce(self.source.read_bytes())
        self.web()
        self.assert_preserved(before)
        self.assertFalse(self.workspace.path("input/missing.ppm").exists())
        self.assert_clean()

    def test_create_destination_symlink_referent_is_untouched(self):
        referent = self.workspace.ppm("retained.ppm")
        occupied = self.workspace.path("input/photo_web.ppm")
        occupied.symlink_to("../retained.ppm")
        before = self.protect(occupied, referent)
        self.produce(self.source.read_bytes())
        self.web()
        self.assert_preserved(before)
        self.assert_clean()

    def test_failed_create_publication_preserves_newly_occupied_entry(self):
        occupied = self.workspace.path("input/photo_web.ppm")
        self.produce(self.source.read_bytes())
        self.workspace.respond("ln", status=17, writes={"input/photo_web.ppm": "other invocation"})
        result = self.web()
        self.assertTrue(any(e["tool"] == "ln" and e["status"] == 17 for e in result.events))
        self.assertEqual(occupied.read_text(), "other invocation")
        self.assertFalse(any(e["tool"] in ("cp", "mv") for e in result.events))
        self.assert_clean()

    def test_failed_create_publication_removes_only_owned_stage(self):
        sentinel = self.workspace.ppm("input/.kim6-stage.unrelated/keep.ppm")
        before = self.protect(sentinel)
        self.produce(self.source.read_bytes())
        self.workspace.respond("ln", status=73)
        result = self.web()
        self.assertTrue(any(e["tool"] == "ln" and e["status"] == 73 for e in result.events))
        self.assertFalse(self.workspace.path("input/photo_web.ppm").exists())
        self.assert_preserved(before)
        self.assertEqual(list(self.source.parent.glob(".kim6-stage.*")), [sentinel.parent])

    def test_cross_device_publication_is_refused(self):
        self.produce(self.source.read_bytes())
        self.workspace.respond_to("stat", "%d", [{"stdout": "1\n"}, {"stdout": "2\n"}])
        result = self.web()
        self.assertFalse(self.workspace.path("input/photo_web.ppm").exists())
        self.assertFalse(any(e["tool"] in ("cp", "mv", "ln") for e in result.events))
        self.assert_clean()

    def test_link_cross_device_error_has_no_fallback(self):
        self.produce(self.source.read_bytes())
        self.workspace.respond("ln", status=18, stderr="EXDEV\n")
        result = self.web()
        self.assertTrue(any(e["tool"] == "ln" and e["status"] == 18 for e in result.events))
        self.assertFalse(self.workspace.path("input/photo_web.ppm").exists())
        self.assertFalse(any(e["tool"] in ("cp", "mv") for e in result.events))
        self.assert_clean()

    def test_symlinked_parent_resolves_to_destination_filesystem(self):
        directory = self.workspace.path("exports")
        directory.mkdir()
        link = self.workspace.path("linked exports")
        link.symlink_to(directory, target_is_directory=True)
        self.produce(self.source.read_bytes())
        result = self.web(link)
        producer = next(e for e in result.events if e["tool"] == "magick")
        self.assertEqual(Path(producer["output"]).parent.parent, directory)
        self.assertEqual((directory / "photo_web.ppm").read_bytes(), self.source.read_bytes())
        self.assert_clean()

    def test_preexisting_cooperative_lock_is_preserved(self):
        lock = self.workspace.path("input/.kim6-publish.lock")
        lock.mkdir()
        marker = lock / "owner"
        marker.write_text("another invocation")
        before = self.protect(lock, marker, self.destination)
        self.produce()
        self.convert()
        self.assert_preserved(before)
        self.assertEqual(list(lock.iterdir()), [marker])

    def test_concurrent_create_attempts_have_one_atomic_winner(self):
        self.produce(self.source.read_bytes(), barrier="publication")
        self.workspace.env["KIM_WEB_FORMAT"] = "keep"
        self.workspace.respond_to("kdialog", "Max image size (e.g. 1600x1600):", {"stdout": "3x2\n"})
        self.workspace.respond_to("kdialog", "Quality (1-100):", {"stdout": "75\n"})
        processes = []
        try:
            # Snapshot only after BOTH processes exit: ordinary Workspace._run
            # snapshots can race the other invocation's legitimate stage cleanup.
            for _ in range(2):
                processes.append(subprocess.Popen(
                    [str(self.workspace.dispatcher), "webexport", str(self.source.parent), str(self.source)],
                    cwd=self.workspace.root, env=self.workspace.env, start_new_session=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE))
            for process in processes:
                stdout, stderr = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, (stdout, stderr))
        finally:
            for process in processes:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate()
        events = [json.loads(line) for line in self.workspace.events.read_text().splitlines()]
        publications = [e for e in events if e["tool"] == "ln"]
        self.assertEqual(len(publications), 2)
        self.assertEqual(sum(e["status"] == 0 for e in publications), 1)
        self.assertEqual(self.workspace.path("input/photo_web.ppm").read_bytes(), self.source.read_bytes())
        self.assert_clean()

    def test_conversion_stage_allocation_failure_keeps_destination(self):
        before = self.protect(self.source, self.destination)
        self.produce()
        self.workspace.sequence("mktemp", [{"passthrough": True}, {"status": 73}])
        result = self.convert()
        self.assertFalse(any(e["tool"] == "magick" for e in result.events))
        self.assert_preserved(before)
        self.assert_clean()

    def test_absent_overwrite_destination_occupied_during_production_is_preserved(self):
        payload = self.destination.read_bytes()
        self.destination.unlink()
        self.produce(payload, writes={"input/photo.jpg": "newly occupied destination"})
        self.convert()
        self.assertEqual(self.destination.read_text(), "newly occupied destination")
        self.assert_clean()

    def test_overwrite_cross_device_rename_error_preserves_destination(self):
        before = self.protect(self.source, self.destination)
        self.produce()
        self.workspace.respond_to("mv", "--no-copy", {"status": 18, "stderr": "EXDEV\n"})
        result = self.convert()
        self.assertTrue(any(e["tool"] == "mv" and e["status"] == 18 for e in result.events))
        self.assertFalse(any(e["tool"] == "cp" for e in result.events))
        self.assert_preserved(before)
        self.assert_clean()

    def test_existing_atomic_overwrite_metadata_policy_is_preserved(self):
        self.destination.chmod(0o640)
        os.utime(self.destination, ns=(1_600_000_000_000_000_000, 1_600_000_001_123_456_789))
        before = self.workspace.observe(self.destination)
        # Keep exercising the unchanged legacy helper through an unmigrated action.
        self.workspace.respond("exiftool", output_base64=base64.b64encode(self.destination.read_bytes()).decode())
        result = self.workspace.dispatch("stripmeta", self.destination)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self.workspace.observe(self.destination)
        self.assertEqual(after.mode, before.mode)
        self.assertEqual(after.mtime_ns, before.mtime_ns)
        self.assertNotEqual(after.inode, before.inode)
        self.assert_clean()

    def test_unmigrated_overwrite_fails_closed_on_unsupported_tools(self):
        before = self.protect(self.destination)
        # Keep exercising the unchanged legacy helper through an unmigrated action.
        self.workspace.respond("exiftool", output_base64=base64.b64encode(self.destination.read_bytes()).decode())
        self.workspace.respond_to("mv", "--help", {"stdout": "no rename-only support\n"})
        result = self.workspace.dispatch("stripmeta", self.destination)
        self.assertNotEqual(result.returncode, 0)
        self.assert_preserved(before)
        self.assert_clean()


    def test_real_installed_mv_performs_authorized_atomic_replacement(self):
        self.workspace.use_real_mv()
        payload = self.destination.read_bytes()
        self.destination.write_bytes(b"existing synthetic target")
        self.destination.chmod(0o640)
        before = self.protect(self.source, self.destination)
        self.produce(payload)
        result = self.convert()
        self.assertEqual(self.destination.read_bytes(), payload)
        self.assertNotEqual(self.workspace.observe(self.destination).inode,
                            before[self.destination].inode)
        self.assertEqual(self.workspace.observe(self.destination).mode, 0o640)
        self.assertEqual(self.workspace.observe(self.source), before[self.source])
        actual = [e for e in result.events if e["tool"] == "mv" and "--help" not in e["argv"]
                  and "--version" not in e["argv"]]
        self.assertEqual(len(actual), 1)
        self.assertEqual(actual[0]["status"], 0)
        self.assertTrue("--exchange" in actual[0]["argv"] or "--no-copy" in actual[0]["argv"])
        self.assertFalse(any(e["tool"] == "cp" for e in result.events))
        self.assert_clean()

    def test_real_installed_backend_injected_failure_preserves_destination(self):
        self.workspace.use_real_mv()
        help_text = subprocess.run([shutil.which("mv"), "--help"],
                                   capture_output=True, text=True, check=True).stdout
        operation = "--no-copy" if "--no-copy" in help_text else "--exchange"
        before = self.protect(self.source, self.destination)
        self.produce()
        self.workspace.respond_to("mv", operation, {"status": 73})
        result = self.convert()
        self.assertTrue(any(e["tool"] == "mv" and operation in e["argv"]
                            and e["status"] == 73 for e in result.events))
        self.assertFalse(any(e["tool"] == "cp" for e in result.events))
        self.assert_preserved(before)
        self.assert_clean()

    def test_real_installed_backend_supports_unmigrated_atomic_caller(self):
        self.workspace.use_real_mv()
        self.destination.chmod(0o640)
        os.utime(self.destination, ns=(1_600_000_000_000_000_000, 1_600_000_001_123_456_789))
        before = self.workspace.observe(self.destination)
        # Keep exercising the unchanged legacy helper through an unmigrated action.
        self.workspace.respond("exiftool", output_base64=base64.b64encode(self.destination.read_bytes()).decode())
        result = self.workspace.dispatch("stripmeta", self.destination)
        self.assertEqual(result.returncode, 0, result.stderr)
        after = self.workspace.observe(self.destination)
        self.assertNotEqual(after.inode, before.inode)
        self.assertEqual(after.mode, before.mode)
        self.assertEqual(after.mtime_ns, before.mtime_ns)
        self.assert_clean()

    def test_atomic_caller_rehomes_cross_device_stage_before_real_publication(self):
        self.workspace.use_real_mv()
        before = self.workspace.observe(self.destination)
        # Keep exercising the unchanged legacy helper through an unmigrated action.
        self.workspace.respond("exiftool", output_base64=base64.b64encode(self.destination.read_bytes()).decode())
        # Scratch and destination appear different; destination-side stage then
        # matches the destination. Real cp and mv effects stay test-owned.
        self.workspace.respond_to("stat", "%d", [
            {"stdout": "1\n"}, {"stdout": "2\n"},
            {"stdout": "2\n"}, {"stdout": "2\n"},
        ])
        result = self.workspace.dispatch("stripmeta", self.destination)
        self.assertEqual(result.returncode, 0, result.stderr)
        copies = [e for e in result.events if e["tool"] == "cp"]
        self.assertEqual(len(copies), 1)
        self.assertEqual(Path(copies[0]["argv"][-1]).parent.parent, self.destination.parent)
        self.assertNotEqual(copies[0]["argv"][-1], str(self.destination))
        self.assertEqual(copies[0]["status"], 0)
        after = self.workspace.observe(self.destination)
        self.assertNotEqual(after.inode, before.inode)
        self.assertEqual(after.mode, before.mode)
        self.assertEqual(after.mtime_ns, before.mtime_ns)
        self.assert_clean()

    def test_failed_cross_device_stage_preparation_preserves_destination(self):
        before = self.protect(self.destination)
        # Keep exercising the unchanged legacy helper through an unmigrated action.
        self.workspace.respond("exiftool", output_base64=base64.b64encode(self.destination.read_bytes()).decode())
        self.workspace.respond_to("stat", "%d", [{"stdout": "1\n"}, {"stdout": "2\n"}])
        self.workspace.respond("cp", status=74,
                               output_base64=base64.b64encode(b"partial private copy").decode())
        result = self.workspace.dispatch("stripmeta", self.destination)
        self.assertTrue(any(e["tool"] == "cp" and e["status"] == 74 for e in result.events))
        self.assertFalse(any(e["tool"] == "mv" for e in result.events))
        self.assert_preserved(before)
        self.assert_clean()


    def test_native_exchange_cross_device_error_preserves_both_files(self):
        executable = shutil.which("mv")
        version = subprocess.run([executable, "--version"], capture_output=True,
                                 text=True, check=True).stdout.strip()
        if version != "mv (uutils coreutils) 0.12.0":
            self.skipTest("native exchange proof applies to audited uutils 0.12.0")
        if not Path("/dev/shm").is_dir() or not os.access("/dev/shm", os.W_OK):
            self.skipTest("second writable local filesystem unavailable")
        stage = self.workspace.path("native-stage")
        stage.write_bytes(b"synthetic prepared bytes")
        with tempfile.TemporaryDirectory(prefix="kim6-exdev-", dir="/dev/shm") as folder:
            target = Path(folder) / "target"
            target.write_bytes(b"synthetic existing destination")
            if stage.stat().st_dev == target.stat().st_dev:
                self.skipTest("test locations share a filesystem")
            before_stage = (stage.stat().st_ino, stage.read_bytes())
            before_target = (target.stat().st_ino, target.read_bytes())
            result = subprocess.run([executable, "--exchange", "-T", "--", str(stage), str(target)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((stage.stat().st_ino, stage.read_bytes()), before_stage)
            self.assertEqual((target.stat().st_ino, target.read_bytes()), before_target)


if __name__ == "__main__":
    unittest.main()
