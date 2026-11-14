"""Phase 1 standalone metadata editor planner coverage."""
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from metadata_integrity import sha256_noatime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/bin"))

from kim_metadata_reader import MetadataEntry, MetadataRecord
from kim_metadata_reader import read_metadata
from kim_photo_selection import read_thumbnail
from kim_metadata_editor import (
    FIELD_SPECS, BatchEditDialog, Draft, MetadataEditor, MetadataSettingsDialog, ReviewDialog, SourceChooserDialog, aggregate_field_state, build_plan,
    detected_file_type, field_state, proposed_output,
)
from kim_metadata_sources import (
    MetadataSourcePreferences, SOURCE_PRIORITY_DEFAULT, metadata_representations,
    preferred_representation,
)


def record(path, *, file_type="JPEG", entries=(), error=None):
    values = [MetadataEntry("FileType", ("File",), "FileType", file_type,
                           str(path), "File:FileType")] if file_type else []
    values.extend(entries)
    return MetadataRecord(str(Path(path).resolve()), values, error=error)


def planned_row(plan, field):
    return next(row for row in plan if row["field"] == field)


class MetadataEditorPlannerTests(unittest.TestCase):
    def test_source_priority_settings_round_trip_and_defaults(self):
        class MemorySettings:
            values = {}
            def value(self, key, default=None, type=None):
                value = self.values.get(key, default)
                return type(value) if type is not None else value
            def setValue(self, key, value):
                self.values[key] = value
            def sync(self):
                pass
        settings = MemorySettings()
        preferences = MetadataSourcePreferences(settings)
        self.assertEqual(SOURCE_PRIORITY_DEFAULT, preferences.priority)
        self.assertFalse(preferences.sync_default)
        changed = ("IPTC-IIM", "Embedded XMP", "XMP sidecar", "EXIF")
        preferences.save(changed, True)
        restored = MetadataSourcePreferences(settings)
        self.assertEqual(changed, restored.priority)
        self.assertTrue(restored.sync_default)

    def test_metadata_settings_move_restore_and_sync_default(self):
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        class MemorySettings:
            values = {}
            def value(self, key, default=None, type=None):
                value = self.values.get(key, default)
                return type(value) if type is not None else value
            def setValue(self, key, value):
                self.values[key] = value
            def sync(self):
                pass
        preferences = MetadataSourcePreferences(MemorySettings()).save(sync_default=True)
        dialog = MetadataSettingsDialog(preferences)
        self.assertEqual("Embedded XMP", dialog.sources.item(0).text())
        dialog.sources.setCurrentRow(0)
        dialog.down.click()
        self.assertEqual("XMP sidecar", dialog.sources.item(0).text())
        dialog.reset.click()
        self.assertEqual(SOURCE_PRIORITY_DEFAULT,
                         tuple(dialog.sources.item(index).text() for index in range(dialog.sources.count())))
        self.assertFalse(dialog.sync_default.isChecked())
        dialog.sources.setCurrentRow(3)
        dialog.up.click()
        dialog._save()
        self.assertEqual("EXIF", preferences.priority[-2])
        self.assertFalse(preferences.sync_default)
        dialog.close()

    def test_preferred_source_and_representation_inventory_are_source_specific(self):
        path = str(Path("/tmp/source-priority.jpg").resolve())
        item = record(path, entries=[
            MetadataEntry("Description", ("XMP", "XMP-dc"), None, "XMP caption", path, "XMP-dc:Description"),
            MetadataEntry("Caption-Abstract", ("IPTC", "Other"), 120, "IIM caption", path, "IPTC:Caption-Abstract"),
        ])
        preferred, available = preferred_representation(item, FIELD_SPECS[1], SOURCE_PRIORITY_DEFAULT)
        self.assertEqual("Embedded XMP", preferred.source)
        self.assertEqual(2, len(available))
        preferred, _available = preferred_representation(item, FIELD_SPECS[1],
                                                          ("IPTC-IIM", "Embedded XMP", "XMP sidecar", "EXIF"))
        self.assertEqual("IPTC-IIM", preferred.source)

    def test_ambiguous_preferred_representation_does_not_fall_back_silently(self):
        path = str(Path("/tmp/ambiguous-source.jpg").resolve())
        item = record(path, entries=[
            MetadataEntry("Description", ("XMP", "XMP-dc"), None, "First", path, "XMP-dc:Description"),
            MetadataEntry("Description", ("XMP", "XMP-dc"), None, "Second", path, "XMP-dc:Description"),
            MetadataEntry("Caption-Abstract", ("IPTC", "Other"), 120, "Legacy", path, "IPTC:Caption-Abstract"),
        ])
        preferred, available = preferred_representation(item, FIELD_SPECS[1])
        self.assertIsNone(preferred)
        self.assertGreaterEqual(len(available), 2)
        self.assertTrue(any(rep.source == "IPTC-IIM" for rep in available))

    def test_source_only_edit_targets_only_pinned_representation_and_lists_untouched(self):
        source = str(Path("/tmp/source-only.jpg").resolve())
        item = record(source, entries=[
            MetadataEntry("Description", ("XMP", "XMP-dc"), None, "XMP old", source, "XMP-dc:Description"),
            MetadataEntry("Caption-Abstract", ("IPTC", "Other"), 120, "IIM old", source, "IPTC:Caption-Abstract"),
        ])
        preferred, _ = preferred_representation(item, FIELD_SPECS[1])
        draft = Draft("Replace", "XMP new", preferred.target)
        plan = build_plan([source], {item.path: item}, {source: {"caption": draft}}, "Individual")
        row = planned_row(plan, "Description")
        self.assertEqual("valid", row["status"])
        self.assertEqual("Embedded XMP", row["sources"])
        self.assertEqual("Embedded XMP: XMP-dc:Description", row["targets"])
        self.assertIn("IPTC-IIM: IPTC:Caption-Abstract", row["untouched"])

    def test_sync_missing_counterpart_requires_separate_authorization(self):
        source = str(Path("/tmp/sync-missing.jpg").resolve())
        item = record(source, entries=[MetadataEntry(
            "Description", ("XMP", "XMP-dc"), None, "Before", source, "XMP-dc:Description")])
        preferred, _ = preferred_representation(item, FIELD_SPECS[1])
        draft = Draft("Replace", "After", preferred.target, sync=True)
        row = planned_row(build_plan([source], {item.path: item},
                                     {source: {"caption": draft}}, "Individual"), "Description")
        self.assertEqual("blocked", row["status"])
        self.assertIn("separate authorization", row["warning"])
        draft.create_counterpart = True
        row = planned_row(build_plan([source], {item.path: item},
                                     {source: {"caption": draft}}, "Individual"), "Description")
        self.assertEqual("valid", row["status"])
        self.assertIn("New IPTC-IIM", row["targets"])
        self.assertEqual("True", row["sync"])

    def test_sync_clear_does_not_create_a_missing_counterpart(self):
        source = str(Path("/tmp/sync-clear.jpg").resolve())
        item = record(source, entries=[MetadataEntry(
            "Title", ("XMP", "XMP-dc"), None, "Existing", source, "XMP-dc:Title", "x-default")])
        preferred, _ = preferred_representation(item, FIELD_SPECS[0])
        draft = Draft("Clear", "", preferred.target, sync=True)
        row = planned_row(build_plan([source], {item.path: item},
                                     {source: {"title": draft}}, "Individual"), "Title")
        self.assertEqual("valid", row["status"])
        self.assertEqual("(cleared)", row["after"])
        self.assertNotIn("IPTC-IIM", row["targets"])

    def test_sync_targets_only_embedded_xmp_and_iptc_when_counterpart_exists(self):
        source = str(Path("/tmp/sync-pair.jpg").resolve())
        sidecar = str(Path(source).with_suffix(".xmp"))
        item = record(source, entries=[
            MetadataEntry("Description", ("XMP", "XMP-dc"), None, "Before", source,
                          "XMP:XMP-dc:Image:Description"),
            MetadataEntry("Caption-Abstract", ("IPTC", "Other"), 120, "Legacy", source,
                          "IPTC:Caption-Abstract"),
            MetadataEntry("Description", ("XMP", "XMP-dc"), None, "Sidecar", sidecar,
                          "XMP:XMP-dc:Image:Description"),
        ])
        preferred, available = preferred_representation(item, FIELD_SPECS[1])
        draft = Draft("Replace", "After", preferred.target, sync=True)
        row = planned_row(build_plan([source], {item.path: item},
                                     {source: {"caption": draft}}, "Individual"), "Description")
        self.assertEqual("valid", row["status"])
        self.assertIn("Embedded XMP: XMP-dc:Description", row["targets"])
        self.assertIn("IPTC-IIM: IPTC:Caption-Abstract", row["targets"])
        self.assertNotIn("XMP sidecar", row["targets"])
        self.assertIn("XMP:XMP-dc:Image:Description", row["untouched"])

    def test_batch_requires_explicit_preferred_source_target_policy(self):
        source = str(Path("/tmp/batch-policy.jpg").resolve())
        item = record(source, entries=[MetadataEntry(
            "Description", ("XMP", "XMP-dc"), None, "Before", source, "XMP:XMP-dc:Image:Description")])
        draft = Draft("Replace", "After")
        no_policy = {"paths": (source,), "fields": {"caption": draft}}
        row = planned_row(build_plan([source], {item.path: item}, {}, "Combined", [no_policy]), "Description")
        self.assertEqual("blocked", row["status"])
        self.assertIn("source policy", row["warning"])
        draft.batch_preferred_source = True
        selected = {"paths": (source,), "fields": {"caption": draft}}
        row = planned_row(build_plan([source], {item.path: item}, {}, "Combined", [selected]), "Description")
        self.assertEqual("valid", row["status"])
        self.assertEqual("Embedded XMP", row["sources"])

    def test_batch_target_snapshot_does_not_follow_later_settings_changes(self):
        source = str(Path("/tmp/batch-snapshot.jpg").resolve())
        item = record(source, entries=[
            MetadataEntry("Description", ("XMP", "XMP-dc"), None, "XMP", source, "XMP:XMP-dc:Image:Description"),
            MetadataEntry("Caption-Abstract", ("IPTC", "Other"), 120, "IIM", source, "IPTC:Caption-Abstract"),
        ])
        xmp, _ = preferred_representation(item, FIELD_SPECS[1], SOURCE_PRIORITY_DEFAULT)
        draft = Draft("Replace", "After", batch_preferred_source=True)
        session = {"paths": (source,), "fields": {"caption": draft},
                   "targets": {"caption": {item.path: xmp.target}}}
        changed_priority = ("IPTC-IIM", "Embedded XMP", "XMP sidecar", "EXIF")
        row = planned_row(build_plan([source], {item.path: item}, {}, "Combined",
                                     [session], priority=changed_priority), "Description")
        self.assertEqual("Embedded XMP", row["sources"])

    def test_sidecar_is_never_a_sync_counterpart_and_language_targets_stay_distinct(self):
        source = str(Path("/tmp/sidecar-source.jpg").resolve())
        sidecar = str(Path(source).with_suffix(".xmp"))
        item = record(source, entries=[
            MetadataEntry("Title", ("XMP", "XMP-dc"), "title", "Morning", source, "XMP-dc:Title", "x-default"),
            MetadataEntry("Title", ("XMP", "XMP-dc"), "title-fr", "Matin", source, "XMP-dc:Title-fr", "fr"),
            MetadataEntry("Title", ("XMP", "XMP-dc"), "title", "Sidecar title", sidecar, "XMP-dc:Title", "x-default"),
        ])
        default, reps = preferred_representation(item, FIELD_SPECS[0])
        self.assertEqual("Embedded XMP", default.source)
        self.assertEqual(3, len(reps))
        draft = Draft("Replace", "Sunrise", default.target)
        row = planned_row(build_plan([source], {item.path: item},
                                     {source: {"title": draft}}, "Individual"), "Title")
        self.assertIn("x-default", row["targets"])
        self.assertIn("fr", row["untouched"])
        sidecar_target = next(rep.target for rep in reps if rep.source == "XMP sidecar")
        sidecar_draft = Draft("Replace", "Changed", sidecar_target)
        row = planned_row(build_plan([source], {item.path: item},
                                     {source: {"title": sidecar_draft}}, "Individual"), "Title")
        self.assertEqual("blocked", row["status"])
        self.assertIn("sidecar-capable save mode", row["warning"])

    def test_registry_contains_only_the_six_canonical_fields(self):
        self.assertEqual(
            ["Title", "Description", "Keywords", "Creator",
             "Copyright notice", "Usage terms"],
            [spec.label for spec in FIELD_SPECS],
        )
        self.assertEqual(64, FIELD_SPECS[0].iim_limit)
        self.assertEqual(2000, FIELD_SPECS[1].iim_limit)
        self.assertEqual(64, FIELD_SPECS[2].iim_limit)
        self.assertEqual(32, FIELD_SPECS[3].iim_limit)
        self.assertEqual(128, FIELD_SPECS[4].iim_limit)
        self.assertIsNone(FIELD_SPECS[5].iim)

    def test_field_state_shows_conflict_sources_without_selecting_winner(self):
        path = Path("/tmp/editor-conflict.jpg").resolve()
        item = record(path, entries=[
            MetadataEntry("Description", ("XMP-dc",), None, "XMP text", str(path), "XMP-dc:Description"),
            MetadataEntry("Caption-Abstract", ("IPTC",), None, "IIM text", str(path), "IPTC:Caption-Abstract"),
        ])
        state, shown, sources = field_state(item, FIELD_SPECS[1])
        self.assertEqual("Conflicting", state)
        self.assertIn("XMP text", shown)
        self.assertIn("IIM text", shown)
        self.assertIn("XMP", sources)
        self.assertIn("IPTC-IIM", sources)

    def test_language_alternatives_are_preserved_without_false_conflict(self):
        path = Path("/tmp/editor-languages.jpg").resolve()
        item = record(path, entries=[
            MetadataEntry("Title", ("XMP", "XMP-dc"), "title", "Morning", str(path), "XMP-dc:Title", "x-default"),
            MetadataEntry("Title", ("XMP", "XMP-dc"), "title-fr", "Matin", str(path), "XMP-dc:Title-fr", "fr"),
            MetadataEntry("ObjectName", ("IPTC", "Other"), 5, "Morning", str(path), "IPTC:ObjectName"),
        ])
        state, shown, _sources = field_state(item, FIELD_SPECS[0])
        self.assertEqual("Present populated", state)
        self.assertIn("(fr): Matin", shown)
        self.assertIn("IPTC-IIM: Morning", shown)

    def test_absent_empty_unreadable_and_batch_mixed_are_distinct(self):
        paths = [str(Path("/tmp/mixed-one.jpg").resolve()),
                 str(Path("/tmp/mixed-two.jpg").resolve()),
                 str(Path("/tmp/mixed-three.jpg").resolve())]
        first = record(paths[0], entries=[MetadataEntry(
            "Title", ("XMP", "XMP-dc"), None, "Filled", paths[0], "XMP-dc:Title")])
        second = record(paths[1], entries=[MetadataEntry(
            "Title", ("IPTC", "Other"), 5, "", paths[1], "IPTC:ObjectName")])
        third = record(paths[2], error="Fixture read error")
        self.assertEqual("Present populated", field_state(first, FIELD_SPECS[0])[0])
        self.assertEqual("Present but empty", field_state(second, FIELD_SPECS[0])[0])
        self.assertEqual("Unreadable", field_state(third, FIELD_SPECS[0])[0])
        records = {item.path: item for item in (first, second, third)}
        self.assertEqual("Mixed (1 populated, 1 empty, 1 unreadable)",
                         aggregate_field_state(paths, records, FIELD_SPECS[0]))
        self.assertEqual("Not present", field_state(record("/tmp/missing.jpg"), FIELD_SPECS[0])[0])

    def test_creator_alias_keeps_exif_artist_provenance_visible(self):
        path = str(Path("/tmp/creator-artist.jpg").resolve())
        item = record(path, entries=[MetadataEntry(
            "Artist", ("EXIF", "IFD0", "Author"), 315, "Photo author", path, "EXIF:IFD0:Artist")])
        state, details, sources = field_state(item, FIELD_SPECS[3])
        self.assertEqual("Present populated", state)
        self.assertIn("EXIF: Photo author", details)
        self.assertEqual("EXIF", sources)
        plan = build_plan([path], {item.path: item},
                          {item.path: {"creator": Draft("Replace", "Photo author")}}, "Individual")
        row = planned_row(plan, "Creator")
        self.assertEqual("Replace", row["operation"])
        self.assertIn("embedded XMP-dc:Creator", row["targets"])

    def test_exif_creator_is_inspectable_but_not_invented_as_editable_mapping(self):
        path = str(Path("/tmp/creator-exif-readonly.jpg").resolve())
        item = record(path, entries=[MetadataEntry(
            "Artist", ("EXIF", "IFD0", "Author"), 315, "Camera credit", path,
            "EXIF:IFD0:Artist")])
        preferred, representations = preferred_representation(item, FIELD_SPECS[3])
        self.assertEqual("EXIF", preferred.source)
        self.assertFalse(preferred.editable)
        self.assertEqual(["Camera credit"], preferred.value)
        self.assertEqual(1, len(representations))

    def test_blank_replace_requires_explicit_clear_and_empty_clear_is_no_op(self):
        source = str(Path("/tmp/blank-operation.jpg").resolve())
        item = record(source)
        blank_replace = {source: {"title": Draft("Replace", "")}}
        blocked = build_plan([source], {item.path: item}, blank_replace, "Individual")
        self.assertIn("blank value does not clear", blocked[0]["value"])
        clear = {source: {"title": Draft("Clear", "")}}
        plan = build_plan([source], {item.path: item}, clear, "Individual")
        self.assertEqual("No change required", plan[0]["operation"])

    def test_clear_is_distinct_from_blank_and_review_shows_before_after(self):
        source = str(Path("/tmp/clear-caption.jpg").resolve())
        item = record(source, entries=[MetadataEntry(
            "Description", ("XMP", "XMP-dc"), None, "Current caption", source, "XMP-dc:Description")])
        plan = build_plan([source], {item.path: item},
                          {item.path: {"caption": Draft("Clear", "")}}, "Individual")
        row = planned_row(plan, "Description")
        self.assertEqual("Clear", row["operation"])
        self.assertIn("Current caption", row["value"])
        self.assertIn("Planned: (cleared)", row["value"])

    def test_keyword_replacement_preserves_multiword_terms_and_detects_no_op(self):
        source = str(Path("/tmp/keyword-replace.jpg").resolve())
        item = record(source, entries=[
            MetadataEntry("Subject", ("XMP", "XMP-dc"), "subject",
                          ["blue, sky", "雪"], source, "XMP-dc:Subject"),
            MetadataEntry("Keywords", ("IPTC", "Other"), 25,
                          ["blue, sky", "雪"], source, "IPTC:Keywords"),
        ])
        drafts = {"__batch__": {"keywords": Draft("Replace keywords", "blue, sky\n雪")}}
        plan = build_plan([source], {item.path: item}, drafts, "Batch")
        self.assertEqual("No change required", planned_row(plan, "Keywords")["operation"])

    def test_conflicting_values_need_explicit_replace_or_clear(self):
        source = Path("/tmp/explicit-conflict.jpg")
        item = record(source, entries=[
            MetadataEntry("Description", ("XMP", "XMP-dc"), None, "XMP caption", str(source), "XMP-dc:Description"),
            MetadataEntry("Caption-Abstract", ("IPTC", "Other"), 120, "IIM caption", str(source), "IPTC:Caption-Abstract"),
        ])
        no_resolution = {str(source.resolve()): {"caption": Draft("Fill empty", "New")}}
        blocked = build_plan([str(source)], {item.path: item}, no_resolution, "Individual")
        self.assertIn("Blocked", planned_row(blocked, "Description")["operation"])
        replacement = {str(source.resolve()): {"caption": Draft("Replace", "Resolved caption")}}
        reviewed = build_plan([str(source)], {item.path: item}, replacement, "Individual")
        row = planned_row(reviewed, "Description")
        self.assertEqual("Replace", row["operation"])
        self.assertIn("XMP caption", row["value"])
        self.assertIn("IIM caption", row["value"])
        self.assertIn("Resolved caption", row["value"])

    def test_replace_matching_default_language_does_not_target_translations(self):
        source = Path("/tmp/default-language.jpg")
        item = record(source, entries=[
            MetadataEntry("Title", ("XMP", "XMP-dc"), "title", "Morning", str(source), "XMP-dc:Title", "x-default"),
            MetadataEntry("Title", ("XMP", "XMP-dc"), "title-fr", "Matin", str(source), "XMP-dc:Title-fr", "fr"),
            MetadataEntry("ObjectName", ("IPTC", "Other"), 5, "Morning", str(source), "IPTC:ObjectName"),
        ])
        drafts = {str(source.resolve()): {"title": Draft("Replace", "Morning")}}
        plan = build_plan([str(source)], {item.path: item}, drafts, "Individual")
        self.assertEqual("No change required", planned_row(plan, "Title")["operation"])

    def test_format_detection_uses_reader_value_not_extension(self):
        misleading = record("/tmp/looks-like-jpeg.png", file_type="JPEG")
        self.assertEqual("JPEG", detected_file_type(misleading))
        plan = build_plan(["/tmp/looks-like-jpeg.png"], {misleading.path: misleading}, {}, "Individual")
        self.assertEqual("Leave unchanged", planned_row(plan, "Title")["operation"])
        unsupported = record("/tmp/image.jpg", file_type="PNG")
        blocked = build_plan(["/tmp/image.jpg"], {unsupported.path: unsupported}, {}, "Individual")
        self.assertEqual("Blocked", planned_row(blocked, "Image eligibility")["operation"])

    def test_sidecar_filetype_does_not_override_selected_jpeg_content_type(self):
        image = Path("/tmp/sidecar-type.jpg").resolve()
        sidecar = image.with_suffix(".xmp")
        item = record(image, entries=[MetadataEntry(
            "FileType", ("File", "Other"), None, "XMP", str(sidecar), "File:FileType")])
        self.assertEqual("JPEG", detected_file_type(item))

    def test_plan_reports_targets_byte_limit_and_no_actual_result(self):
        source = Path("/tmp/editor-long-title.jpg")
        item = record(source)
        drafts = {str(source.resolve()): {
            "title": Draft("Replace", "雪" * 22),
        }}
        plan = build_plan([str(source)], {item.path: item}, drafts, "Individual")
        row = planned_row(plan, "Title")
        self.assertEqual("Blocked · Replace", row["operation"])
        self.assertIn("64 UTF-8 bytes", row["value"])
        self.assertIn("XMP-dc:Title", row["targets"])
        self.assertIn("IPTC:ObjectName", row["targets"])
        self.assertEqual("No output planned", row["result"])

    def test_keywords_are_kept_as_one_term_per_line_in_plan(self):
        source = Path("/tmp/keywords.jpg")
        item = record(source)
        drafts = {"__batch__": {"keywords": Draft("Add keywords", "alpine lake\n雪")}}
        plan = build_plan([str(source)], {item.path: item}, drafts, "Batch")
        row = planned_row(plan, "Keywords")
        self.assertEqual("Add keywords", row["operation"])
        self.assertTrue(row["value"].endswith("Planned: alpine lake\n雪"))

    def test_fill_empty_and_identical_replace_are_explicit_no_ops(self):
        source = Path("/tmp/already-described.jpg")
        item = record(source, entries=[MetadataEntry(
            "Title", ("XMP-dc",), None, "Existing", str(source), "XMP-dc:Title")])
        drafts = {str(source.resolve()): {
            "title": Draft("Fill empty", "Proposed"),
            "caption": Draft("Replace", "Same caption"),
        }}
        item.entries.append(MetadataEntry(
            "Description", ("XMP-dc",), None, "Same caption", str(source), "XMP-dc:Description"))
        plan = build_plan([str(source)], {item.path: item}, drafts, "Individual")
        rows = [row for row in plan if row["status"] != "unchanged"]
        self.assertEqual(["No change required", "No change required"],
                         [row["operation"] for row in rows])
        self.assertTrue(all(row["result"] == "No output planned" for row in rows))

    def test_copy_name_uses_stable_numeric_collision_suffix(self):
        with patch("kim_metadata_editor.Path.exists", side_effect=[True, True, False]):
            self.assertEqual(Path("/tmp/photo-metadata-3.JPG"), proposed_output("/tmp/photo.JPG"))

    def test_plan_distinguishes_valid_noop_blocked_and_unchanged(self):
        paths = ["/tmp/valid.jpg", "/tmp/noop.jpg", "/tmp/blocked.jpg"]
        valid = record(paths[0], entries=[MetadataEntry(
            "Description", ("XMP-dc",), None, "Old", paths[0], "XMP-dc:Description")])
        noop = record(paths[1], entries=[MetadataEntry(
            "Description", ("XMP-dc",), None, "Same", paths[1], "XMP-dc:Description")])
        blocked = record(paths[2], file_type="PNG")
        drafts = {"__batch__": {"caption": Draft("Replace", "Same")}}
        plan = build_plan(paths, {item.path: item for item in (valid, noop, blocked)}, drafts, "Batch")
        statuses = {(row["image"], row["field"]): row["status"] for row in plan}
        self.assertEqual("valid", statuses[("valid.jpg", "Description")])
        self.assertEqual("noop", statuses[("noop.jpg", "Description")])
        self.assertEqual("blocked", statuses[("blocked.jpg", "Image eligibility")])
        self.assertEqual("unchanged", statuses[("valid.jpg", "Title")])



class MetadataEditorQtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])
        if not shutil.which("ffmpeg") or not shutil.which("exiftool"):
            raise unittest.SkipTest("ffmpeg and ExifTool are required for JPEG metadata fixtures")
        cls.temp = tempfile.TemporaryDirectory(prefix="kim6-editor-ui-")
        fixture_script = Path(__file__).parent / "fixtures/metadata_browser/generate_fixtures.py"
        subprocess.run([sys.executable, str(fixture_script), "--output-dir", cls.temp.name], check=True)
        cls.fixtures = Path(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def make_editor(self, names, preferences=None):
        from PySide6.QtCore import QSize
        paths = [str((self.fixtures / name).resolve()) for name in names]
        with patch("kim_metadata_editor.MetadataWorker.start", return_value=None):
            editor = MetadataEditor(paths, preferences=preferences)
        records = read_metadata(paths)
        previews = {}
        for path in paths:
            try:
                previews[path] = read_thumbnail(path, QSize(480, 360))[0]
            except (ValueError, OSError):
                from PySide6.QtGui import QImage
                previews[path] = QImage()
        editor._scan_complete(records, previews)
        editor.show()
        self.app.processEvents()
        return editor

    def settings_preferences(self, path):
        from PySide6.QtCore import QSettings
        return MetadataSourcePreferences(QSettings(str(path), QSettings.IniFormat))

    def close_editor(self, editor):
        editor.drafts.clear()
        editor.source_drafts.clear()
        editor.batch_sessions.clear()
        editor.close()
        self.app.processEvents()

    def assert_preview_fits_cached_image(self, editor):
        from PySide6.QtCore import Qt
        self.app.processEvents()
        source = editor.previews[editor.current_preview_path]
        available = editor.preview.contentsRect().size()
        pixmap = editor.preview.pixmap().size()
        self.assertEqual(source.size().scaled(available, Qt.KeepAspectRatio), pixmap)
        self.assertLessEqual(pixmap.width(), available.width())
        self.assertLessEqual(pixmap.height(), available.height())
        self.assertAlmostEqual(source.width() / source.height(),
                               pixmap.width() / pixmap.height(), delta=0.02)
        return pixmap

    def select_rows(self, editor, indexes):
        selected = set(indexes)
        for index in range(editor.file_list.count()):
            editor.file_list.item(index).setSelected(index in selected)
        self.app.processEvents()

    def batch_edit(self, editor, indexes, changes):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QPlainTextEdit
        self.select_rows(editor, indexes)
        self.assertTrue(editor.batch_button.isEnabled())
        self.batch_configuration_error = None

        def configure():
            dialog = self.app.activeModalWidget()
            try:
                self.assertIsInstance(dialog, BatchEditDialog)
                dialog.target_policy.setChecked(True)
                for key, (operation, value) in changes.items():
                    control = dialog.controls[key]
                    control["apply"].click()
                    control["new_target"].setChecked(True)
                    control["operation"].setCurrentText(operation)
                    if operation != "Clear":
                        widget = control["edit"]
                        if isinstance(widget, QPlainTextEdit):
                            widget.setPlainText(value)
                        else:
                            widget.setText(value)
                dialog.add_button.click()
            except Exception as exc:
                self.batch_configuration_error = exc
                if dialog:
                    dialog.reject()
        QTimer.singleShot(0, configure)
        editor.batch_edit_selected()
        if self.batch_configuration_error:
            raise self.batch_configuration_error

    def test_direct_title_edit_and_image_navigation_preserve_multiple_drafts(self):
        from PySide6.QtWidgets import QComboBox, QLineEdit, QPlainTextEdit, QPushButton
        editor = self.make_editor(["complete.jpg", "xmp_only.jpg"])
        self.assertIn("complete.jpg", editor.image_info.text())
        self.assertIn("JPEG", editor.image_info.text())
        title = editor.field_controls["title"]["edit"]
        self.assertIsInstance(title, QLineEdit)
        self.assertEqual("Harbor at dawn", title.text())
        self.assertTrue(title.isEnabled())
        self.assertFalse(editor.findChildren(QComboBox))
        self.assertNotIn("Current value", editor.field_controls["title"]["note"].text())
        title.setText("First image title")
        self.assertEqual("Replace", editor.drafts[editor.paths[0]]["title"].operation)
        editor.next_button.click()
        self.app.processEvents()
        self.assertEqual("雪の山", editor.field_controls["title"]["edit"].text())
        editor.field_controls["title"]["edit"].setText("Second image title")
        editor.previous_button.click()
        self.app.processEvents()
        self.assertEqual("First image title", editor.field_controls["title"]["edit"].text())
        self.assertIn("2 changes", editor.pending_label.text())
        plan = build_plan(editor.paths, editor.records, editor.drafts, "Combined")
        self.assertEqual("valid", planned_row(plan, "Title")["status"])
        second_title = next(row for row in plan if row["image"] == "xmp_only.jpg" and row["field"] == "Title")
        self.assertEqual("Second image title", second_title["after"])
        self.assertFalse(any("Apply changes" in button.text() for button in editor.findChildren(QPushButton)))
        self.close_editor(editor)

    def test_horizontal_and_vertical_splitters_resize_persist_and_restore(self):
        from PySide6.QtCore import QEventLoop, QTimer, Qt
        temp = tempfile.TemporaryDirectory(prefix="kim6-editor-splitters-")
        settings_path = Path(temp.name) / "editor.ini"
        preferences = self.settings_preferences(settings_path)
        editor = self.make_editor(["complete.jpg"], preferences)
        editor.resize(1400, 900)
        self.app.processEvents()
        self.assertEqual(Qt.Horizontal, editor.splitter.orientation())
        self.assertEqual(Qt.Vertical, editor.image_splitter.orientation())
        self.assertEqual(2, editor.splitter.count())
        self.assertEqual(2, editor.image_splitter.count())
        self.assertGreater(editor.splitter.handleWidth(), 0)
        self.assertGreater(editor.image_splitter.handleWidth(), 0)

        app = self.app
        app.processEvents()
        horizontal_before = editor.splitter.sizes()
        vertical_before = editor.image_splitter.sizes()
        self.assert_preview_fits_cached_image(editor)
        total_width = sum(horizontal_before)
        total_height = sum(vertical_before)
        editor.splitter.moveSplitter(min(total_width - 390, horizontal_before[0] + 80), 1)
        app.processEvents()
        self.assert_preview_fits_cached_image(editor)
        editor.image_splitter.moveSplitter(min(total_height - 165, vertical_before[0] + 55), 1)
        app.processEvents()
        self.assertNotEqual(horizontal_before, editor.splitter.sizes())
        self.assertNotEqual(vertical_before, editor.image_splitter.sizes())
        self.assert_preview_fits_cached_image(editor)
        moved_horizontal = editor.splitter.sizes()
        moved_vertical = editor.image_splitter.sizes()
        wait = QEventLoop()
        QTimer.singleShot(300, wait.quit)
        wait.exec()
        stored = self.settings_preferences(settings_path).settings
        self.assertEqual(moved_horizontal, [int(x) for x in stored.value(editor.HORIZONTAL_SPLITTER_KEY)])
        self.assertEqual(moved_vertical, [int(x) for x in stored.value(editor.IMAGE_SPLITTER_KEY)])
        self.close_editor(editor)

        reopened = self.make_editor(["complete.jpg"], self.settings_preferences(settings_path))
        for saved, restored in ((moved_horizontal, reopened.splitter.sizes()),
                                (moved_vertical, reopened.image_splitter.sizes())):
            self.assertAlmostEqual(saved[0] / sum(saved), restored[0] / sum(restored),
                                   delta=1 / sum(restored))
        self.assert_preview_fits_cached_image(reopened)
        reopened.resize(1400, 900)
        app.processEvents()
        for saved, restored in ((moved_horizontal, reopened.splitter.sizes()),
                                (moved_vertical, reopened.image_splitter.sizes())):
            for expected, actual in zip(saved, restored):
                self.assertAlmostEqual(expected, actual, delta=1)
        self.assert_preview_fits_cached_image(reopened)
        self.close_editor(reopened)
        temp.cleanup()

    def test_invalid_saved_splitter_sizes_fall_back_to_visible_panes(self):
        temp = tempfile.TemporaryDirectory(prefix="kim6-editor-invalid-splitter-")
        settings_path = Path(temp.name) / "editor.ini"
        preferences = self.settings_preferences(settings_path)
        preferences.settings.setValue(MetadataEditor.HORIZONTAL_SPLITTER_KEY, [0, 10000])
        preferences.settings.setValue(MetadataEditor.IMAGE_SPLITTER_KEY, [10000, -1])
        preferences.settings.sync()
        editor = self.make_editor(["complete.jpg"], self.settings_preferences(settings_path))
        self.app.processEvents()
        horizontal = editor.splitter.sizes()
        vertical = editor.image_splitter.sizes()
        self.assertGreaterEqual(horizontal[0], 220)
        self.assertGreaterEqual(horizontal[1], 640)
        self.assertGreaterEqual(vertical[0], 120)
        self.assertGreaterEqual(vertical[1], 155)
        self.close_editor(editor)
        temp.cleanup()

    def test_preview_rescales_without_rereading_and_keeps_image_aspect(self):
        with tempfile.TemporaryDirectory(prefix="kim6-editor-preview-") as temporary:
            preferences = self.settings_preferences(Path(temporary) / "editor.ini")
            editor = self.make_editor(["complete.jpg"], preferences)
            cached = editor.previews[editor.paths[0]]
            cache_key = cached.cacheKey()
            try:
                with patch("kim_metadata_editor.read_thumbnail", side_effect=AssertionError("resize reread image")) as read:
                    for dimensions in ((1000, 700), (1400, 900)):
                        editor.resize(*dimensions)
                        self.assert_preview_fits_cached_image(editor)

                    # A tall preview makes width the limiting dimension.
                    editor.image_splitter.moveSplitter(120, 1)
                    editor.splitter.moveSplitter(220, 1)
                    before = self.assert_preview_fits_cached_image(editor)
                    for position in (320, 220):
                        editor.splitter.moveSplitter(position, 1)
                        after = self.assert_preview_fits_cached_image(editor)
                        self.assertNotEqual(before, after)
                        before = after

                    # A wide preview makes height the limiting dimension.
                    editor.splitter.moveSplitter(600, 1)
                    bottom = editor.image_splitter.getRange(1)[1]
                    editor.image_splitter.moveSplitter(bottom, 1)
                    before = self.assert_preview_fits_cached_image(editor)
                    for position in (bottom - 80, bottom):
                        editor.image_splitter.moveSplitter(position, 1)
                        after = self.assert_preview_fits_cached_image(editor)
                        self.assertNotEqual(before, after)
                        before = after
                    editor.splitter.moveSplitter(700, 1)
                    self.assertEqual(before, self.assert_preview_fits_cached_image(editor))

                    for splitter in (editor.splitter, editor.image_splitter):
                        for position in (0, 10000):
                            splitter.moveSplitter(position, 1)
                            self.assert_preview_fits_cached_image(editor)
                            self.assertGreaterEqual(editor.splitter.sizes()[0], 220)
                            self.assertGreaterEqual(editor.splitter.sizes()[1], 640)
                            self.assertGreaterEqual(editor.image_splitter.sizes()[0], 120)
                            self.assertGreaterEqual(editor.image_splitter.sizes()[1], 155)
                    read.assert_not_called()
                    self.assertIs(cached, editor.previews[editor.paths[0]])
                    self.assertEqual(cache_key, cached.cacheKey())
            finally:
                self.close_editor(editor)

    def test_resizing_and_navigation_do_not_modify_image_or_sidecar(self):
        image = self.fixtures / "conflicting_sidecar.jpg"
        sidecar = image.with_suffix(".xmp")
        targets = [image, sidecar]
        def signature(path):
            stat = path.stat()
            return (sha256_noatime(path), stat.st_size,
                    stat.st_atime_ns, stat.st_mtime_ns, stat.st_ctime_ns)
        before = {path: signature(path) for path in targets}
        editor = self.make_editor(["conflicting_sidecar.jpg", "complete.jpg"])
        editor.resize(1000, 700)
        editor.splitter.moveSplitter(editor.splitter.sizes()[0] + 40, 1)
        editor.image_splitter.moveSplitter(editor.image_splitter.sizes()[0] + 30, 1)
        editor.navigate(1)
        editor.navigate(-1)
        self.app.processEvents()
        self.close_editor(editor)
        self.assertEqual(before, {path: signature(path) for path in targets})

    def test_new_value_on_absent_field_uses_fill_empty_and_blank_never_clears(self):
        from PySide6.QtWidgets import QLineEdit
        editor = self.make_editor(["missing_metadata.jpg"])
        title = editor.field_controls["title"]["edit"]
        self.assertIsInstance(title, QLineEdit)
        self.assertIn("New destination:", editor.field_controls["title"]["state"].text())
        title.setText("New title")
        self.assertEqual("Fill empty", editor.drafts[editor.paths[0]]["title"].operation)
        row = planned_row(build_plan(editor.paths, editor.records, editor.drafts, "Combined"), "Title")
        self.assertEqual("blocked", row["status"])
        editor.field_controls["title"]["create_target"].click()
        row = planned_row(build_plan(editor.paths, editor.records, editor.drafts, "Combined"), "Title")
        self.assertEqual("valid", row["status"])
        title.clear()
        self.assertEqual("Leave unchanged", editor.drafts[editor.paths[0]]["title"].operation)
        self.assertNotIn("Clear", editor.drafts[editor.paths[0]]["title"].operation)
        self.close_editor(editor)

    def test_conflicting_values_use_preferred_source_and_alternates_are_inspectable(self):
        editor = self.make_editor(["conflicting_sidecar.jpg"])
        control = editor.field_controls["caption"]
        self.assertIn("Editing: Embedded XMP", control["state"].text())
        self.assertFalse(control["conflict"].isVisible())
        self.assertIn("Other metadata sources (", control["details"].text())
        self.assertTrue(control["details"].isEnabled())
        self.close_editor(editor)

    def test_settings_priority_reorders_individual_preferred_value(self):
        class MemorySettings:
            values = {}
            def value(self, key, default=None, type=None):
                value = self.values.get(key, default)
                return type(value) if type is not None else value
            def setValue(self, key, value):
                self.values[key] = value
            def sync(self):
                pass
        editor = self.make_editor(["complete.jpg"])
        path = editor.paths[0]
        spec = FIELD_SPECS[0]
        self.assertEqual("Embedded XMP", editor._active_representation(path, spec).source)
        editor.preferences = MetadataSourcePreferences(MemorySettings())
        editor.preferences.save(("IPTC-IIM", "Embedded XMP", "XMP sidecar", "EXIF"), False)
        editor._refresh_individual(path)
        self.assertEqual("IPTC-IIM", editor._active_representation(path, spec).source)
        self.assertEqual("Harbor at dawn", editor.field_controls[spec.key]["edit"].text())
        self.close_editor(editor)

    def test_source_switch_with_pending_draft_keeps_original_target_pinned(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QPushButton
        editor = self.make_editor(["complete.jpg"])
        path = editor.paths[0]
        control = editor.field_controls["title"]
        original = editor._active_representation(path, control["spec"])
        control["edit"].setText("Kept XMP draft")
        draft = editor.drafts[path]["title"]
        self.assertEqual(draft.target, original.target)
        alternate = next(item for item in editor._representations(path, control["spec"])
                         if item.source == "IPTC-IIM")

        def choose_alternate():
            dialog = self.app.activeModalWidget()
            self.assertIsInstance(dialog, SourceChooserDialog)
            row = next(index for index in range(dialog.list.count())
                       if dialog.list.item(index).data(256).target.key == alternate.target.key)
            dialog.list.setCurrentRow(row)
            QTimer.singleShot(0, keep_original)
            next(button for button in dialog.findChildren(QPushButton)
                 if button.text() == "Edit this source").click()

        def keep_original():
            box = self.app.activeModalWidget()
            button = next(button for button in box.findChildren(QPushButton)
                          if button.text() == "Keep original draft")
            button.click()

        QTimer.singleShot(0, choose_alternate)
        control["details"].click()
        self.app.processEvents()
        self.assertEqual(1, len(editor.source_drafts))
        self.assertIs(editor.source_drafts[0][2], draft)
        self.assertEqual(alternate.target.key, editor.source_targets[path]["title"].key)
        control["edit"].setText("IPTC draft")
        plan = build_plan(editor.paths, editor.records, editor.drafts, "Combined",
                          editor.batch_sessions, editor.source_drafts, editor.preferences.priority)
        title_rows = [row for row in plan if row["field"] == "Title" and row["status"] == "valid"]
        self.assertEqual({"Embedded XMP", "IPTC-IIM"},
                         {row["sources"].split(" · ", 1)[0] for row in title_rows})
        self.close_editor(editor)

    def test_individual_sync_override_requires_and_records_counterpart_consent(self):
        editor = self.make_editor(["xmp_only.jpg"])
        title = editor.field_controls["title"]
        description = editor.field_controls["caption"]
        title["sync"].setChecked(True)
        title["edit"].setText("Synchronized title")
        draft = editor.drafts[editor.paths[0]]["title"]
        self.assertTrue(draft.sync)
        self.assertFalse(description["sync"].isChecked())
        blocked = planned_row(build_plan(editor.paths, editor.records, editor.drafts, "Combined"), "Title")
        self.assertEqual("blocked", blocked["status"])
        self.assertTrue(title["create_counterpart"].isVisible())
        title["create_counterpart"].setChecked(True)
        valid = planned_row(build_plan(editor.paths, editor.records, editor.drafts, "Combined"), "Title")
        self.assertEqual("valid", valid["status"])
        self.assertIn("New IPTC-IIM: IPTC:ObjectName", valid["targets"])
        self.close_editor(editor)

    def test_individual_clear_requires_explicit_confirmation_and_is_reviewed(self):
        from PySide6.QtWidgets import QMessageBox
        editor = self.make_editor(["complete.jpg"])
        title = editor.field_controls["title"]
        self.assertTrue(title["clear"].isVisible())
        with patch("kim_metadata_editor.QMessageBox.question", return_value=QMessageBox.Yes):
            title["clear"].click()
        self.assertEqual("Clear", editor.drafts[editor.paths[0]]["title"].operation)
        self.assertEqual("", title["edit"].text())
        plan = build_plan(editor.paths, editor.records, editor.drafts, "Combined")
        row = planned_row(plan, "Title")
        self.assertEqual("valid", row["status"])
        self.assertEqual("(cleared)", row["after"])
        review = ReviewDialog(plan, editor, len(editor.paths))
        self.assertIn("Harbor at dawn", review.before_view.toPlainText())
        self.assertEqual("(cleared)", review.after_view.toPlainText())
        review.close()
        self.close_editor(editor)

    def test_batch_checkbox_activates_only_selected_fields_and_reviews_valid_blocked_noops(self):
        from PySide6.QtWidgets import QPushButton
        editor = self.make_editor(["complete.jpg", "missing_metadata.jpg", "malformed.jpg"])
        self.batch_edit(editor, [0, 1, 2], {
            "title": ("Replace", "Shared title"),
            "caption": ("Fill empty", "Only missing images get this"),
            "copyright": ("Clear", ""),
        })
        session = editor.batch_sessions[0]
        self.assertEqual({"title", "caption", "copyright"}, set(session["fields"]))
        self.assertNotIn("keywords", session["fields"])
        self.assertEqual(("complete.jpg", "missing_metadata.jpg", "malformed.jpg"),
                         tuple(Path(path).name for path in session["paths"]))
        plan = build_plan(editor.paths, editor.records, editor.drafts, "Combined", editor.batch_sessions)
        title_rows = [row for row in plan if row["field"] == "Title"]
        caption_rows = [row for row in plan if row["field"] == "Description"]
        copyright_rows = [row for row in plan if row["field"] == "Copyright notice"]
        self.assertEqual(["valid", "valid"], [row["status"] for row in title_rows])
        self.assertEqual({"valid", "noop"}, {row["status"] for row in caption_rows})
        self.assertTrue(any(row["field"] == "Image eligibility" and row["status"] == "blocked"
                            for row in plan))
        self.assertEqual("Clear", next(row for row in copyright_rows
                                        if row["image"] == "complete.jpg")["operation"])
        self.assertEqual("noop", next(row for row in copyright_rows
                                       if row["image"] == "missing_metadata.jpg")["status"])
        self.assertTrue(any(row["status"] == "blocked" for row in plan))
        self.assertTrue(all(row["status"] == "unchanged" for row in plan
                            if row["field"] == "Keywords"))
        review = ReviewDialog(plan, editor, len(editor.paths))
        self.assertIn("3 selected images", review.summary.text())
        self.assertIn("blocked", review.summary.text())
        self.assertFalse(any("Apply" in button.text() or "Write" in button.text()
                             for button in review.findChildren(QPushButton)))
        review.close()
        self.close_editor(editor)

    def test_batch_draft_does_not_overwrite_individual_draft(self):
        editor = self.make_editor(["complete.jpg", "xmp_only.jpg"])
        editor.field_controls["title"]["edit"].setText("Individual title")
        individual = editor.drafts[editor.paths[0]]["title"]
        self.batch_edit(editor, [0, 1], {"title": ("Replace", "Batch title")})
        self.assertIs(editor.drafts[editor.paths[0]]["title"], individual)
        self.assertEqual("Individual title", individual.value)
        plan = build_plan(editor.paths, editor.records, editor.drafts, "Combined", editor.batch_sessions)
        row_a = next(row for row in plan if row["image"] == "complete.jpg" and row["field"] == "Title")
        row_b = next(row for row in plan if row["image"] == "xmp_only.jpg" and row["field"] == "Title")
        self.assertEqual("blocked", row_a["status"])
        self.assertIn("both an Individual change and a Batch change", row_a["warning"])
        self.assertEqual("valid", row_b["status"])
        self.close_editor(editor)

    def test_multiline_description_review_shows_before_and_after(self):
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QPlainTextEdit
        editor = self.make_editor(["xmp_only.jpg"])
        description = editor.field_controls["caption"]["edit"]
        self.assertIsInstance(description, QPlainTextEdit)
        description.setPlainText("First line\nSecond line\nThird line")
        self.assertEqual("Replace", editor.drafts[editor.paths[0]]["caption"].operation)
        plan = build_plan(editor.paths, editor.records, editor.drafts, "Combined")
        review = ReviewDialog(plan, editor, len(editor.paths))
        item = next(item for item in review.items
                    if item.data(0, Qt.UserRole)["field"] == "Description")
        review.tree.setCurrentItem(item)
        self.app.processEvents()
        self.assertEqual("Snow peaks with Unicode metadata.", review.before_view.toPlainText())
        self.assertEqual("First line\nSecond line\nThird line", review.after_view.toPlainText())
        self.assertEqual("Planned result: xmp_only-metadata.jpg", review.result_label.text())
        review.technical_button.setChecked(True)
        self.assertIn("Provenance:", review.technical.toPlainText())
        review.close()
        self.close_editor(editor)


if __name__ == "__main__":
    unittest.main()
