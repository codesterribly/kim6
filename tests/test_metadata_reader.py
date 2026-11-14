"""Focused tests for the standalone browser's structured read-only reader."""
import json
import fcntl
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

from metadata_integrity import sha256_noatime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/bin"))
from kim_metadata_reader import (MetadataReadError, associated_xmp_sidecars,
                                 parse_exiftool_json, read_metadata)


class MetadataReaderTests(unittest.TestCase):
    def test_preserves_duplicate_groups_arrays_structures_unicode_and_ids(self):
        path = "/tmp/東京 - image.jpg"
        payload = json.dumps([{
            "SourceFile": path,
            "EXIF:IFD0:Image:Copy0:0x010f:Make": {"val": "Camera Co.", "id": "0x010f"},
            "XMP-dc:Copy0:Subject": {"val": ["café", "雪", "café"], "id": "dc:Subject"},
            "XMP-dc:Copy0:Description": {"val": {"x-default": "Résumé\nline two", "fr": "Résumé"}, "id": "dc:Description"},
            "XMP-dc:Copy0:Title": {"val": "Morning", "id": "title"},
            "XMP-dc:Copy0:Title-fr": {"val": "Matin", "id": "title-fr", "lang": "fr"},
            "IPTC:Application2:Copy1:2:Keywords": {"val": ["extra"], "id": "2"},
        }], ensure_ascii=False)
        record = parse_exiftool_json(payload, [path])[str(Path(path).resolve())]
        self.assertEqual(6, len(record.entries))
        self.assertEqual("Camera Co.", record.entries[0].value)
        self.assertEqual("0x010f", record.entries[0].tag_id)
        self.assertEqual(["café", "雪", "café"], record.entries[1].value)
        self.assertEqual("XMP-dc:Copy0", record.entries[1].group)
        self.assertEqual("Résumé\nline two", record.entries[2].value["x-default"])
        self.assertEqual("x-default", record.entries[3].language)
        self.assertEqual("Title", record.entries[4].name)
        self.assertEqual("fr", record.entries[4].language)
        self.assertEqual("Title-fr", record.entries[4].qualified_name.split(":")[-1])
        self.assertEqual("IPTC:Application2:Copy1:2", record.entries[5].group)

    def test_missing_record_and_exiftool_reported_error_are_preserved(self):
        path = "/tmp/broken.jpg"
        records = parse_exiftool_json(json.dumps([{
            "SourceFile": path,
            "System:Error": "File format error",
        }]), [path])
        record = records[str(Path(path).resolve())]
        self.assertEqual("File format error", record.error)
        self.assertEqual([], record.entries)

    def test_associated_sidecar_is_read_only_and_merged_with_provenance(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "雪.nef"
            sidecar = Path(temporary) / "雪.XMP"
            image.write_bytes(b"fixture image")
            sidecar.write_text("fixture xmp", encoding="utf-8")
            before = {p: (sha256_noatime(p), p.stat().st_size,
                          p.stat().st_atime_ns, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                      for p in (image, sidecar)}
            self.assertEqual([sidecar], associated_xmp_sidecars(image))
            expected = iter(((image, "EXIF:IFD0:Make", "Maker"),
                             (sidecar, "XMP-dc:Description", "sidecar text")))

            def extract(command, *, stdin, timeout):
                path, key, value = next(expected)
                self.assertEqual(path.stat().st_ino, os.fstat(stdin).st_ino)
                self.assertTrue(fcntl.fcntl(stdin, fcntl.F_GETFL) & os.O_NOATIME)
                stdout = json.dumps([{"SourceFile": "-", key: value}]).encode()
                return Mock(returncode=0, stdout=stdout, stderr=b"")

            with patch("kim_metadata_reader.shutil.which", return_value="/usr/bin/exiftool"), \
                 patch("kim_metadata_reader.run_process", side_effect=extract) as run:
                records = read_metadata([image])
            record = records[str(image.resolve())]
            self.assertEqual([str(sidecar.resolve())], record.sidecars)
            self.assertEqual(["Make", "FileName", "Directory", "Description", "FileName", "Directory"],
                             [e.name for e in record.entries])
            self.assertEqual(str(sidecar.resolve()), record.entries[3].source)
            self.assertEqual(2, run.call_count)
            for call in run.call_args_list:
                command = call.args[0]
                self.assertEqual(["--", "-"], command[-2:])
                self.assertTrue(all(not arg.startswith("-") or arg in {
                    "-j", "-a", "-u", "-G0:1:2:4", "-D", "-struct", "-charset",
                    "filename=UTF8", "-all:all", "-XMP:*"
                } for arg in command[1:-2]))
                with self.assertRaises(OSError):
                    os.fstat(call.kwargs["stdin"])
            after = {p: (sha256_noatime(p), p.stat().st_size,
                         p.stat().st_atime_ns, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                     for p in (image, sidecar)}
            self.assertEqual(before, after)

    def test_missing_exiftool_fails_with_actionable_error(self):
        with patch("kim_metadata_reader.shutil.which", return_value=None):
            with self.assertRaisesRegex(MetadataReadError, "Install ExifTool"):
                read_metadata(["/tmp/image.jpg"])

    def test_one_unreadable_input_does_not_abort_other_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            readable = Path(temporary) / "readable.jpg"
            unreadable = Path(temporary) / "unreadable.jpg"
            readable.write_bytes(b"readable fixture")
            unreadable.write_bytes(b"unreadable fixture")
            original_open = os.open

            def open_with_one_denial(filename, flags):
                if str(filename) == str(unreadable.resolve()):
                    raise PermissionError("fixture permission denial")
                return original_open(filename, flags)

            payload = json.dumps([{
                "SourceFile": str(readable.resolve()),
                "File:FileType": {"val": "JPEG", "id": "FileType"},
            }]).encode()
            completed = Mock(returncode=0, stdout=payload, stderr=b"")
            with patch("kim_metadata_reader.shutil.which", return_value="/usr/bin/exiftool"), \
                 patch("kim_metadata_reader.os.open", side_effect=open_with_one_denial), \
                 patch("kim_metadata_reader.run_process", return_value=completed):
                records = read_metadata([readable, unreadable])
            self.assertEqual("JPEG", records[str(readable.resolve())].entries[0].value)
            self.assertIn("unreadable.jpg", records[str(unreadable.resolve())].error)

    def test_partial_exiftool_failure_keeps_values_and_reports_warnings(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "damaged.jpg"
            image.write_bytes(b"fixture")
            payload = json.dumps([{
                "SourceFile": str(image),
                "File:FileType": {"val": "JPEG", "id": "filetype"},
                "System:Warning": "Some metadata could not be decoded",
            }]).encode()
            result = Mock(returncode=1, stdout=payload, stderr=b"Warning: incomplete file")
            with patch("kim_metadata_reader.shutil.which", return_value="/usr/bin/exiftool"), \
                 patch("kim_metadata_reader.run_process", return_value=result):
                record = read_metadata([image])[str(image.resolve())]
            self.assertEqual("JPEG", record.entries[0].value)
            self.assertEqual([
                "Some metadata could not be decoded",
                "ExifTool batch warning: Warning: incomplete file",
            ], record.warnings)
            self.assertIsNone(record.error)

    def test_noatime_unavailable_fails_without_starting_exiftool(self):
        with patch("kim_metadata_reader.os.O_NOATIME", None), \
             patch("kim_metadata_reader.shutil.which", return_value="/usr/bin/exiftool"), \
             patch("kim_metadata_reader.run_process") as run:
            with self.assertRaisesRegex(MetadataReadError, "access timestamps"):
                read_metadata(["/tmp/image.jpg"])
        run.assert_not_called()

    def test_symlink_inputs_are_not_followed(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "source.jpg"
            link = Path(temporary) / "link.jpg"
            source.write_bytes(b"fixture")
            link.symlink_to(source)
            before = source.stat()
            with patch("kim_metadata_reader.run_process") as run:
                record = read_metadata([link])[str(link)]
            run.assert_not_called()
            self.assertIn("symbolic link", record.error)
            self.assertEqual([], record.entries)
            self.assertEqual(before, source.stat())

    def test_symlink_replacement_during_open_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "image.jpg"
            other = Path(temporary) / "other.jpg"
            image.write_bytes(b"fixture")
            other.write_bytes(b"other fixture")
            original_open = os.open

            def replace_before_open(filename, flags):
                image.unlink()
                image.symlink_to(other)
                return original_open(filename, flags)

            with patch("kim_metadata_reader.os.open", side_effect=replace_before_open), \
                 patch("kim_metadata_reader.run_process") as run:
                record = read_metadata([image])[str(image)]
            run.assert_not_called()
            self.assertIsNotNone(record.error)
            self.assertEqual([], record.entries)

    def test_source_replacement_during_extraction_discards_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "image.jpg"
            replacement = Path(temporary) / "replacement.jpg"
            image.write_bytes(b"fixture")
            replacement.write_bytes(b"replacement")

            def replace_during_extraction(command, **kwargs):
                replacement.replace(image)
                return Mock(returncode=0, stdout=b'[{"SourceFile":"-","EXIF:Make":"stale"}]', stderr=b"")

            with patch("kim_metadata_reader.run_process", side_effect=replace_during_extraction) as run:
                record = read_metadata([image])[str(image)]
            self.assertIn("Source changed", record.error)
            self.assertEqual([], record.entries)
            with self.assertRaises(OSError):
                os.fstat(run.call_args.kwargs["stdin"])

    def test_timeout_and_startup_errors_close_the_source_descriptor(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "image.jpg"
            image.write_bytes(b"fixture")
            for error, message in ((subprocess.TimeoutExpired("exiftool", 1), "took too long"),
                                   (OSError("fixture startup failure"), "Could not start ExifTool")):
                with self.subTest(error=error):
                    with patch("kim_metadata_reader.run_process", side_effect=error) as run:
                        with self.assertRaisesRegex(MetadataReadError, message):
                            read_metadata([image])
                    with self.assertRaises(OSError):
                        os.fstat(run.call_args.kwargs["stdin"])

    def test_inputs_share_the_original_timeout_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "image.jpg"
            image.write_bytes(b"fixture")
            image.with_suffix(".xmp").write_bytes(b"sidecar")
            result = Mock(returncode=0, stdout=b'[{"SourceFile":"-","File:FileType":"JPEG"}]', stderr=b"")
            with patch("kim_metadata_reader.time.monotonic", side_effect=[10, 11, 13]), \
                 patch("kim_metadata_reader.run_process", return_value=result) as run:
                read_metadata([image], timeout=10)
            self.assertEqual([9, 7], [call.kwargs["timeout"] for call in run.call_args_list])

    def test_empty_output_and_invalid_json_still_raise(self):
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "image.jpg"
            image.write_bytes(b"fixture")
            for stdout, message in ((b"", "returned no metadata"), (b"not json", "invalid JSON")):
                with self.subTest(stdout=stdout):
                    result = Mock(returncode=1, stdout=stdout, stderr=b"")
                    with patch("kim_metadata_reader.run_process", return_value=result):
                        with self.assertRaisesRegex(MetadataReadError, message):
                            read_metadata([image])

    def test_invalid_json_fails_with_readable_error(self):
        with self.assertRaisesRegex(MetadataReadError, "invalid JSON"):
            parse_exiftool_json("not json")

    def test_invalid_utf8_fails_with_readable_error(self):
        with self.assertRaisesRegex(MetadataReadError, "invalid JSON"):
            parse_exiftool_json(b"\xff")


class MetadataReaderIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="kim6-reader-fixtures-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.fixtures = Path(cls.temporary.name)
        generator = Path(__file__).parent / "fixtures/metadata_browser/generate_fixtures.py"
        subprocess.run([sys.executable, str(generator), "--output-dir", cls.temporary.name],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def test_real_extraction_preserves_fresh_sources_and_rich_metadata(self):
        with tempfile.TemporaryDirectory(prefix="kim6-reader-integrity-") as temporary:
            image = Path(temporary) / "雪 - image.jpg"
            sidecar = image.with_suffix(".XMP")
            for source, target in ((self.fixtures / "complete.jpg", image),
                                   (self.fixtures / "conflicting_sidecar.xmp", sidecar)):
                with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOATIME), "rb") as stream:
                    content = stream.read()
                if target == image:
                    # Duplicate a real APP1 EXIF segment so -a/-G4 must retain
                    # both copies, including their distinct group provenance.
                    start = content.index(b"Exif\x00\x00") - 4
                    self.assertEqual(b"\xff\xe1", content[start:start + 2])
                    length = int.from_bytes(content[start + 2:start + 4], "big")
                    segment = content[start:start + 2 + length]
                    content = content[:2] + segment + content[2:]
                target.write_bytes(content)

            def signature(path):
                stat = path.stat()
                return (sha256_noatime(path), stat.st_size, stat.st_atime_ns,
                        stat.st_mtime_ns, stat.st_ctime_ns)

            before = {path: signature(path) for path in (image, sidecar)}
            record = read_metadata([image])[str(image)]
            self.assertEqual(before, {path: signature(path) for path in before})
            self.assertIsNone(record.error)
            self.assertEqual([str(sidecar)], record.sidecars)
            embedded = [entry for entry in record.entries if entry.source == str(image)]
            adjacent = [entry for entry in record.entries if entry.source == str(sidecar)]
            makes = [entry for entry in embedded if entry.name == "Make"]
            self.assertEqual(["KIM6 Synthetic Camera"] * 2, [entry.value for entry in makes])
            self.assertEqual(2, len({entry.groups for entry in makes}))
            self.assertTrue(any("Copy1" in entry.groups for entry in makes))
            self.assertIn(["harbor", "dawn", "harbor"],
                          [entry.value for entry in embedded if entry.name == "Subject"])
            self.assertIn(["harbor", "dawn", "harbor"],
                          [entry.value for entry in embedded if entry.name == "Keywords"])
            self.assertTrue(any(entry.name == "LocationCreated" and isinstance(entry.value, (dict, list))
                                for entry in embedded))
            titles = {(entry.language, entry.value) for entry in embedded if entry.name == "Title"}
            self.assertIn(("x-default", "Harbor at dawn"), titles)
            self.assertIn(("fr", "Port au lever du jour"), titles)
            self.assertTrue(any(entry.name == "Description" and entry.value == "Sidecar description says gray clouds."
                                for entry in adjacent))
            self.assertTrue(any("XMP-dc" in entry.groups for entry in adjacent))
            for path in (image, sidecar):
                entries = [entry for entry in record.entries if entry.source == str(path)]
                self.assertIn(path.name, [entry.value for entry in entries if entry.name == "FileName"])
                self.assertIn(str(path.parent), [entry.value for entry in entries if entry.name == "Directory"])


if __name__ == "__main__":
    unittest.main()
