"""Focused tests for the standalone browser's structured read-only reader."""
import json
import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

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
            before = {p: (hashlib.sha256(p.read_bytes()).hexdigest(),
                          p.stat().st_atime_ns, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                      for p in (image, sidecar)}
            self.assertEqual([sidecar], associated_xmp_sidecars(image))
            stdout = json.dumps([
                {"SourceFile": str(image), "EXIF:IFD0:Make": "Maker"},
                {"SourceFile": str(sidecar), "XMP-dc:Description": "sidecar text"},
            ], ensure_ascii=False).encode()
            result = Mock(returncode=0, stdout=stdout, stderr=b"")
            with patch("kim_metadata_reader.shutil.which", return_value="/usr/bin/exiftool"), \
                 patch("kim_metadata_reader.run_process", return_value=result) as run:
                records = read_metadata([image])
            record = records[str(image.resolve())]
            self.assertEqual([str(sidecar.resolve())], record.sidecars)
            self.assertEqual(["Make", "Description"], [e.name for e in record.entries])
            self.assertEqual(str(sidecar.resolve()), record.entries[1].source)
            command = run.call_args.args[0]
            self.assertEqual("--", command[-3])
            self.assertTrue(all(not arg.startswith("-") or arg in {
                "-j", "-a", "-u", "-G0:1:2:4", "-D", "-struct", "-charset",
                "filename=UTF8", "-all:all", "-XMP:*", "--"
            } for arg in command[1:]))
            self.assertEqual(2, len(run.call_args.kwargs["pass_fds"]))
            after = {p: (hashlib.sha256(p.read_bytes()).hexdigest(),
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

    def test_invalid_json_fails_with_readable_error(self):
        with self.assertRaisesRegex(MetadataReadError, "invalid JSON"):
            parse_exiftool_json("not json")

    def test_invalid_utf8_fails_with_readable_error(self):
        with self.assertRaisesRegex(MetadataReadError, "invalid JSON"):
            parse_exiftool_json(b"\xff")


if __name__ == "__main__":
    unittest.main()
