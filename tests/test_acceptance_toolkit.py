"""Behavioral tests for the human Dolphin acceptance toolkit."""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
import re
import tempfile
import sys
import unittest
from unittest import mock
import shutil
import os
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from qa import acceptance


class AcceptanceInventoryTests(unittest.TestCase):
    def test_every_menu_action_has_one_complete_unique_case(self):
        cases = acceptance.load_cases(ROOT)
        self.assertEqual(108, len(cases))
        ids = [case["id"] for case in cases]
        self.assertEqual(len(ids), len(set(ids)))
        expected = {
            (menu.name, entry["action_id"])
            for menu in sorted((ROOT / "src").glob("kim_*.desktop.in"))
            for entry in acceptance.parse_menu(menu)
        }
        self.assertEqual(expected, {(case["menu"], case["action_id"]) for case in cases})
        for case in cases:
            with self.subTest(case=case["id"]):
                for key in ("label", "dispatcher", "fixtures", "expected", "source_behavior",
                            "dependencies", "technical_checks", "human_checks", "interactive_choices"):
                    self.assertTrue(case[key], f"{case['id']} missing {key}")
        info = [case for case in cases if case["dispatcher"][0] in {"about", "license", "manual"}]
        self.assertEqual(6, len(info))

    def test_case_instructions_use_real_submenu_and_action_specific_steps(self):
        cases = acceptance.load_cases(ROOT)
        preset = next(case for case in cases if case["action_id"] == "Compress50")
        text = acceptance._instructions(preset, Path("/qa/generated/cases/example"))
        self.assertIn("KIM6 — JPEG compression → JPEG quality: 50%", text)
        self.assertIn("Menu path:", text)
        self.assertIn("Output location: This case folder", text)
        self.assertIn("quality 50", text.lower())
        self.assertIn("photo_compressed.jpg", text)
        self.assertIn("selected source remains unchanged", text.lower())
        self.assertNotIn("KIM6 → JPEG compression →", text)
        rotate = next(case for case in acceptance.load_cases(ROOT) if case["action_id"] == "Rotate90")
        rotate_text = acceptance._instructions(rotate, Path("/qa/generated/cases/rotate"))
        self.assertIn("validate --policy in-place", rotate_text)
        self.assertIn("pass --mode gui --policy in-place", rotate_text)
        convert = next(case for case in acceptance.load_cases(ROOT) if case["action_id"] == "ConvertWEBP")
        self.assertEqual(["photo.jpg"], convert["fixtures"])
        self.assertIn("WEBP", acceptance._case_guidance(convert)[1])
        percent = next(case for case in acceptance.load_cases(ROOT) if case["action_id"] == "ResizePercent")
        self.assertIn("50%", acceptance._case_guidance(percent)[0])
        self.assertIn("half the source width and height", acceptance._case_guidance(percent)[1])
        av1 = next(case for case in acceptance.load_cases(ROOT) if case["action_id"] == "Av1hd720Balanced")
        self.assertIn("AV1 balanced quality", acceptance._case_guidance(av1)[0])
        self.assertNotIn("CRF ", acceptance._case_guidance(av1)[0])
        self.assertNotIn("custom AV1", " ".join(acceptance._interactive_choices("video", ["--codec", "libx264", "--crf", "23"], "Transcode 720 medium H.264" )).lower())

    def test_import_is_conflict_aware_and_provenance_is_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state" / "progress.json"
            acceptance._save_result(state_path, "A", "passed", "gui", "looked correct")
            local = acceptance.load_state(state_path)["results"]["A"]
            self.assertIn("provenance", local)
            self.assertEqual("gui", local["mode"])
            export = root / "bundle.json"
            acceptance.export_state(state_path, export, [{"id": "A"}, {"id": "B"}])
            bundle = json.loads(export.read_text())
            self.assertEqual("A", bundle["results"]["A"]["case_id"])
            self.assertIn("hostname", bundle["source"])
            self.assertIn("git_revision", bundle["source"])

            bundle["results"]["B"] = {"case_id": "B", "status": "failed", "mode": "gui",
                                       "note": "problem", "provenance": {"hostname": "qa-test-host"}}
            export.write_text(json.dumps(bundle))
            acceptance._save_result(state_path, "B", "passed", "gui", "different local result")
            before = acceptance.load_state(state_path)
            with self.assertRaisesRegex(acceptance.MergeConflict, "B"):
                acceptance.import_state(state_path, export, {"A", "B"})
            self.assertEqual(before, acceptance.load_state(state_path))
            merged = acceptance.import_state(state_path, export, {"A", "B"}, resolution="use-imported")
            self.assertEqual("failed", merged["results"]["B"]["status"])

    def test_export_and_import_reject_symlinks_and_unknown_case_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state" / "progress.json"
            acceptance._save_result(state_path, "A", "passed", "gui")
            export = root / "bundle.json"
            acceptance.export_state(state_path, export, [{"id": "A"}])
            with self.assertRaisesRegex(acceptance.SafetyError, "unknown case"):
                acceptance.import_state(state_path, export, {"different"})
            alias = root / "alias.json"
            alias.symlink_to(export)
            with self.assertRaisesRegex(acceptance.SafetyError, "symlink"):
                acceptance.read_import_bundle(alias)

    def test_cli_export_import_round_trip_uses_explicit_paths_inside_qa(self):
        with tempfile.TemporaryDirectory(dir=acceptance.QA_DIR) as tmp:
            root = Path(tmp)
            first_state = acceptance._owned_tree(root / "first-state", ".kim6-acceptance-state-owner", acceptance.OWNER_TEXT)
            second_state = acceptance._owned_tree(root / "second-state", ".kim6-acceptance-state-owner", acceptance.OWNER_TEXT)
            case_id = "kim_compress.desktop:Compress10"
            acceptance._save_result(first_state / "progress.json", case_id, "passed", "gui", "visual check done")
            bundle = root / "transfer.json"
            exported = acceptance.run_cli(["--state-dir", str(first_state), "export", "--output", str(bundle)])
            imported = acceptance.run_cli(["--state-dir", str(second_state), "import", str(bundle)])
            self.assertEqual(0, exported)
            self.assertEqual(0, imported)
            row = acceptance.load_state(second_state / "progress.json")["results"][case_id]
            self.assertEqual("passed", row["status"])
            self.assertEqual("gui", row["mode"])
            self.assertEqual("visual check done", row["note"])

    def test_prepare_creates_owned_transfer_inbox_without_touching_other_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            qa_root = root / "qa"
            repo = root / "repo"
            repo_qa = repo / "qa"
            repo_qa.mkdir(parents=True)
            generated = root / "generated"
            state_dir = root / "state"
            acceptance._owned_tree(state_dir, ".kim6-acceptance-state-owner", acceptance.OWNER_TEXT)
            original_progress = {"version": acceptance.STATE_VERSION, "current_case": None,
                                 "results": {"existing": {"status": "passed", "mode": "gui"}}}
            acceptance.save_state(state_dir / "progress.json", original_progress)
            with mock.patch.object(acceptance, "QA_DIR", qa_root), \
                    mock.patch.object(acceptance, "load_cases", return_value=[]), \
                    mock.patch.object(acceptance, "write_plan", return_value=repo_qa / "ACCEPTANCE_PLAN.md"), \
                    mock.patch.object(acceptance, "_make_masters", return_value={"sha256": {}, "capabilities": {}}):
                acceptance.prepare(generated, state_dir, repo)
            transfer_dir = qa_root / "transfers"
            marker = transfer_dir / ".kim6-acceptance-transfer-owner"
            self.assertEqual(acceptance.OWNER_TEXT, marker.read_text())
            self.assertEqual(original_progress, acceptance.load_state(state_dir / "progress.json"))

    def test_duplicate_action_ids_in_one_menu_are_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            menu = Path(tmp) / "kim_test.desktop.in"
            menu.write_text("""[Desktop Entry]\nActions=One;One;\n\n[Desktop Action One]\n_Name=One\nExec=kim_all about\n""")
            with self.assertRaisesRegex(acceptance.InventoryError, "duplicate"):
                acceptance.parse_menu(menu)

    def test_case_plan_is_derived_from_templates_and_has_correct_fixture_classes(self):
        cases = acceptance.load_cases(ROOT)
        image = next(case for case in cases if case["action_id"] == "Compress10")
        video = next(case for case in cases if case["action_id"].startswith("Videohd"))
        manual = next(case for case in cases if case["action_id"] == "Manual")
        self.assertTrue(any(name.endswith(".jpg") for name in image["fixtures"]))
        self.assertTrue(any("video" in name for name in video["fixtures"]))
        self.assertTrue(manual["fixtures"], "a context-menu file is needed to reveal this menu entry")
        self.assertNotIn("%F", manual["exec"], "informational action must not receive the context file")
        audio = next(case for case in cases if case["action_id"] == "ExtractVideoAudio")
        self.assertIn("video-multiaudio.mkv", audio["fixtures"])
        plan = acceptance.render_plan(cases)
        self.assertIn("108 menu actions", plan)
        self.assertIn("Manual", plan)
        self.assertEqual(108, len(re.findall(r"^\| `kim_[^`]+` \| `[^`]+` \|", plan, re.MULTILINE)))

    def test_media_duration_and_probe_rate_helpers_handle_common_shapes(self):
        self.assertEqual(2.5, acceptance._media_duration({"format": {"duration": "2.5"}}))
        self.assertIsNone(acceptance._media_duration({"format": {"duration": "N/A"}}))
        self.assertEqual(25.0, acceptance._rate_value("25/1"))
        self.assertAlmostEqual(29.97, acceptance._rate_value("30000/1001"), places=2)
        self.assertIsNone(acceptance._rate_value("0/0"))

    def test_generated_checklist_separates_measured_properties_from_human_review(self):
        cases = acceptance.load_cases(ROOT)
        for action_id in ("Album", "Print", "TiffJoin", "Animation", "VideoToGif", "Slideshow", "VideoContactSheet"):
            case = next(item for item in cases if item["action_id"] == action_id)
            text = " ".join(case["technical_checks"])
            self.assertIn("Automated:", text)
            self.assertIn("Human:", text)
        self.assertIn("Human: inspect timing and loop behavior", " ".join(next(c for c in cases if c["action_id"] == "VideoToGif")["technical_checks"]))


class AcceptanceStateAndSafetyTests(unittest.TestCase):
    def test_atomic_state_round_trip_and_pass_fail_skip_statuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state" / "progress.json"
            acceptance.save_state(path, {"results": {"A": {"status": "passed", "mode": "gui"}}})
            self.assertEqual("passed", acceptance.load_state(path)["results"]["A"]["status"])
            self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_pass_fail_skip_and_blocked_records_persist_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state" / "progress.json"
            acceptance._save_result(path, "A", "passed", "gui", policy="create")
            acceptance._save_result(path, "B", "failed", "gui", "pixel order was wrong")
            acceptance._save_result(path, "C", "skipped", "cli", "optional encoder unavailable")
            acceptance._save_result(path, "D", "blocked", "gui", "KDE submenu issue")
            state = acceptance.load_state(path)
            self.assertEqual({"A", "B", "C", "D"}, set(state["results"]))
            self.assertEqual("failed", state["results"]["B"]["status"])
            self.assertEqual("KDE submenu issue", state["results"]["D"]["reason"])
            totals = acceptance.result_totals([{"id": key, "menu": "m", "label": key} for key in "ABCD"], state)
            self.assertEqual((1, 1, 1, 1), (totals["passed"], totals["failed"], totals["skipped"], totals["blocked"]))

    def test_workspace_refuses_symlink_escape_and_unowned_existing_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            outside = root / "outside"
            outside.mkdir()
            link = root / "generated"
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(acceptance.SafetyError, "symlink"):
                acceptance.claim_workspace(link)
            unowned = root / "unowned"
            unowned.mkdir()
            (unowned / "keep.txt").write_text("user data")
            with self.assertRaisesRegex(acceptance.SafetyError, "owned"):
                acceptance.claim_workspace(unowned)
            self.assertEqual("user data", (unowned / "keep.txt").read_text())

    def test_toolkit_paths_reject_parent_traversal_and_external_targets(self):
        with tempfile.TemporaryDirectory() as tmp:
            outside = Path(tmp) / "outside"
            with self.assertRaisesRegex(acceptance.SafetyError, "inside"):
                acceptance.assert_toolkit_path(acceptance.QA_DIR / ".." / outside.name, "workspace")
            with self.assertRaisesRegex(acceptance.SafetyError, "inside"):
                acceptance.assert_toolkit_path(outside, "workspace")

    def test_reset_refuses_unknown_files_and_only_removes_explicitly_owned_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "generated"
            acceptance.claim_workspace(workspace)
            case_dir = acceptance.create_owned_case_dir(workspace, "menu--Action")
            (case_dir / "input.jpg").write_bytes(b"input")
            (case_dir / "unexpected.txt").write_text("do not delete")
            with self.assertRaisesRegex(acceptance.SafetyError, "untracked"):
                acceptance.reset_case_dir(workspace, "menu--Action", {"input.jpg"})
            self.assertTrue((case_dir / "unexpected.txt").exists())
            acceptance.reset_case_dir(workspace, "menu--Action", {"input.jpg", "unexpected.txt"})
            self.assertFalse(case_dir.exists())

    def test_reset_refuses_symlink_or_directory_substituted_for_known_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workspace = root / "generated"
            acceptance.claim_workspace(workspace)
            case_dir = acceptance.create_owned_case_dir(workspace, "menu--Action")
            outside = root / "important.txt"
            outside.write_text("keep me")
            (case_dir / "input.jpg").symlink_to(outside)
            with self.assertRaisesRegex(acceptance.SafetyError, "symlink"):
                acceptance.reset_case_dir(workspace, "menu--Action", {"input.jpg"})
            self.assertTrue((case_dir / "input.jpg").is_symlink())
            self.assertEqual("keep me", outside.read_text())

            (case_dir / "input.jpg").unlink()
            (case_dir / "input.jpg").mkdir()
            with self.assertRaisesRegex(acceptance.SafetyError, "regular file"):
                acceptance.reset_case_dir(workspace, "menu--Action", {"input.jpg"}, {"input.jpg"})
            self.assertTrue((case_dir / "input.jpg").is_dir())

    def test_cli_reset_accepts_recorded_fixture_after_inventory_mapping_changes(self):
        with tempfile.TemporaryDirectory(dir=acceptance.QA_DIR) as tmp:
            root = Path(tmp)
            generated = acceptance.claim_workspace(root / "generated")
            acceptance._owned_tree(generated / "cases", ".kim6-acceptance-owner", acceptance.OWNER_TEXT)
            case_id = "kim_compressandresizevideo.desktop:ExtractVideoAudio"
            case_dir = acceptance.create_owned_case_dir(generated, case_id)
            (case_dir / "video-audio.mp4").write_bytes(b"old recorded fixture")
            (case_dir / "case.json").write_text(json.dumps({"id": case_id, "fixtures": ["video-audio.mp4"]}))
            state_dir = acceptance._owned_tree(root / "state", ".kim6-acceptance-state-owner", acceptance.OWNER_TEXT)
            acceptance.save_state(state_dir / "progress.json", acceptance.default_state())
            result = acceptance.run_cli(["--generated", str(generated), "--state-dir", str(state_dir), "reset", case_id])
            self.assertEqual(0, result)
            self.assertFalse(case_dir.exists())

    def test_reset_of_one_case_leaves_other_case_and_saved_progress_alone(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "generated"
            acceptance.claim_workspace(workspace)
            first = acceptance.create_owned_case_dir(workspace, "menu--A")
            second = acceptance.create_owned_case_dir(workspace, "menu--B")
            (first / "input.jpg").write_bytes(b"case A")
            (second / "input.jpg").write_bytes(b"case B")
            acceptance.reset_case_dir(workspace, "menu--A", {"input.jpg"})
            self.assertFalse(first.exists())
            self.assertEqual(b"case B", (second / "input.jpg").read_bytes())

    def test_failed_atomic_state_replacement_keeps_previous_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state" / "progress.json"
            acceptance.save_state(path, {"results": {"A": {"status": "passed"}}})
            with mock.patch.object(acceptance.os, "replace", side_effect=OSError("simulated crash before replace")):
                with self.assertRaises(OSError):
                    acceptance.save_state(path, {"results": {"B": {"status": "failed"}}})
            self.assertIn("A", acceptance.load_state(path)["results"])
            self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_modified_source_is_an_error_for_derived_cases_and_requires_overwrite_authorization(self):
        baseline = {"photo.jpg": hashlib.sha256(b"before").hexdigest()}
        current = {"photo.jpg": hashlib.sha256(b"after").hexdigest()}
        derived = {"source_behavior": "derived", "fixtures": ["photo.jpg"]}
        authorized = {"source_behavior": "authorized_overwrite", "fixtures": ["photo.jpg"]}
        self.assertTrue(acceptance.check_source_preservation(derived, baseline, current, "create").errors)
        self.assertTrue(acceptance.check_source_preservation(authorized, baseline, current, "create").errors)
        self.assertFalse(acceptance.check_source_preservation(authorized, baseline, current, "overwrite").errors)
        inplace = {"source_behavior": "in_place", "fixtures": ["photo.jpg"]}
        self.assertFalse(acceptance.check_source_preservation(inplace, baseline, current, "in-place").errors)

    def test_missing_tool_is_reported_as_blocked_not_as_a_pass(self):
        result = acceptance.capability("av1-encoder", False, "libsvtav1 or libaom-av1 is unavailable")
        self.assertEqual("blocked", result["status"])
        self.assertIn("unavailable", result["reason"])

    def test_report_totals_keep_gui_and_cli_verification_separate(self):
        cases = [{"id": "A", "menu": "m", "label": "One"},
                 {"id": "B", "menu": "m", "label": "Two"}]
        state = {"results": {"A": {"status": "passed", "mode": "cli"},
                             "B": {"status": "passed", "mode": "gui"}}}
        totals = acceptance.result_totals(cases, state)
        self.assertEqual(1, totals["gui_verified"])
        self.assertEqual(1, totals["cli_verified"])
        self.assertEqual(0, totals["not_tested"])

    def test_instruction_policy_matches_environment_then_kconfig_precedence(self):
        case = {"source_behavior": "authorized_overwrite"}
        acceptance._effective_policy.cache_clear()
        with mock.patch.dict(os.environ, {"KIM_POLICY": "overwrite"}, clear=False):
            self.assertEqual("overwrite", acceptance._validation_policy(case))
        acceptance._effective_policy.cache_clear()
        with tempfile.TemporaryDirectory() as tmp:
            config_file = Path(tmp) / "kim_kdeimagemenu"
            config_file.write_text("[<default>]\nKIM_POLICY=overwrite\n")
            with mock.patch.dict(os.environ, {"KIM_CONFIG_FILE": str(config_file)}, clear=True), \
                    mock.patch.object(acceptance.shutil, "which", return_value="/usr/bin/kreadconfig6"), \
                    mock.patch.object(acceptance, "_run", return_value=subprocess.CompletedProcess([], 0, "overwrite\n", "")):
                self.assertEqual("overwrite", acceptance._validation_policy(case))
        acceptance._effective_policy.cache_clear()

    def test_dashboard_includes_per_case_validator_details_and_provenance(self):
        case = {"id": "A", "menu": "m", "label": "One"}
        state = {"results": {"A": {"status": "passed", "mode": "gui", "updated_at": "2026-10-26T00:00:00Z",
                                         "note": "looked right", "provenance": {"hostname": "qa-test-host", "git_revision": "abc123",
                                         "kde_version": "KDE 6", "qt_version": "6.9", "test_mode": "gui"}}},
                 "validations": {"A": {"checks": ["format is valid"], "warnings": [], "errors": [], "outputs": []}}}
        dashboard = acceptance._render_html([case], state)
        for phrase in ("qa-test-host", "abc123", "KDE 6", "format is valid", "looked right", "GUI verified"):
            self.assertIn(phrase, dashboard)

    def test_named_next_prints_that_case_without_marking_it_passed(self):
        with tempfile.TemporaryDirectory(dir=acceptance.QA_DIR) as tmp:
            root = Path(tmp)
            generated = acceptance.claim_workspace(root / "generated")
            acceptance._owned_tree(generated / "cases", ".kim6-acceptance-owner", acceptance.OWNER_TEXT)
            case_id = "kim_compress.desktop:Compress10"
            case_dir = acceptance.create_owned_case_dir(generated, case_id)
            (case_dir / "case.json").write_text(json.dumps({"id": case_id, "fixtures": ["photo.jpg"],
                                                             "unavailable_fixtures": []}))
            (case_dir / "photo.jpg").write_bytes(b"disposable fixture")
            state_dir = acceptance._owned_tree(root / "state", ".kim6-acceptance-state-owner", acceptance.OWNER_TEXT)
            acceptance.save_state(state_dir / "progress.json", {**acceptance.default_state(),
                                                                 "results": {case_id: {"status": "failed", "mode": "gui"}}})
            from contextlib import redirect_stdout
            from io import StringIO
            output = StringIO()
            with redirect_stdout(output):
                result = acceptance.run_cli(["--generated", str(generated), "--state-dir", str(state_dir),
                                             "next", "--no-open", "--case-id", case_id])
            self.assertEqual(0, result)
            self.assertIn("JPEG quality: 10%", output.getvalue())
            self.assertEqual("failed", acceptance.load_state(state_dir / "progress.json")["results"][case_id]["status"])

    def test_dashboard_links_cases_and_never_calls_technical_validation_gui_acceptance(self):
        cases = [{"id": "kim_test.desktop:Action", "menu": "kim_test.desktop.in", "label": "Photo <test>"}]
        state = {"results": {"kim_test.desktop:Action": {"status": "passed", "mode": "cli", "note": "technical only"}}}
        dashboard = acceptance._render_html(cases, state)
        self.assertIn("CLI verified", dashboard)
        self.assertIn("technical only", dashboard)
        self.assertIn("&lt;test&gt;", dashboard)
        self.assertIn("INSTRUCTIONS.txt", dashboard)
        self.assertIn("Read-only dashboard", dashboard)

    def test_installed_menu_contract_checker_accepts_matching_isolated_resources_only(self):
        with tempfile.TemporaryDirectory(dir=acceptance.QA_DIR) as tmp:
            generated = Path(tmp) / "generated"
            acceptance.claim_workspace(generated)
            acceptance._owned_tree(generated / "cases", ".kim6-acceptance-owner", acceptance.OWNER_TEXT)
            prefix = generated / "gui-data" / "kio" / "servicemenus"
            runtime = prefix / "kim6" / "bin" / "kim_all"
            runtime.parent.mkdir(parents=True)
            shutil.copy2(ROOT / "src/bin/kim_all", runtime)
            for resource in ("ABOUT", "LICENSE.md", "INSTALL.md", "docs/index.html", "docs/work.css",
                             "gallery/index.part1", "gallery/index.part2"):
                destination = prefix / "kim6" / resource
                destination.parent.mkdir(parents=True, exist_ok=True)
                source_path = ROOT / "src" / resource if resource.startswith("gallery/") else ROOT / resource
                shutil.copy2(source_path, destination)
            for template in (ROOT / "src").glob("kim_*.desktop.in"):
                target = prefix / template.name.removesuffix(".in")
                installed_text = template.read_text().replace("Exec=kim_all", f'Exec="{runtime}"')
                installed_text = installed_text.replace("_Name=", "Name=").replace("_X-KDE-Submenu=", "X-KDE-Submenu=")
                target.write_text(installed_text, encoding="utf-8")
                target.chmod(0o644)
            self.assertEqual(0, acceptance._check_isolated_install(generated))

    def test_isolated_dolphin_uses_qa_user_data_and_warns_about_system_menus(self):
        if not shutil.which("dolphin") or not shutil.which("dbus-run-session"):
            self.skipTest("Dolphin or dbus-run-session unavailable")
        with tempfile.TemporaryDirectory(dir=acceptance.QA_DIR) as tmp:
            generated = acceptance.claim_workspace(Path(tmp) / "generated")
            acceptance._owned_tree(generated / "cases", ".kim6-acceptance-owner", acceptance.OWNER_TEXT)
            dispatcher = generated / "gui-data" / "kio" / "servicemenus" / "kim6" / "bin" / "kim_all"
            dispatcher.parent.mkdir(parents=True)
            dispatcher.write_text("test-owned dispatcher")
            with mock.patch.object(acceptance.subprocess, "Popen") as popen:
                message = acceptance._open_dolphin(generated / "cases", isolated=True, generated=generated)
            argv = popen.call_args.args[0]
            self.assertIn("XDG_DATA_DIRS=/usr/share", argv)
            self.assertIn(f"XDG_DATA_HOME={generated / 'gui-data'}", argv)
            self.assertIn("System-wide menus", message)

    @unittest.skipUnless(shutil.which("magick") and shutil.which("identify"), "ImageMagick unavailable")
    def test_real_validator_rejects_extension_mismatch_after_full_decode(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp) / "case"
            case_dir.mkdir()
            source = case_dir / "source.png"
            output = case_dir / "result.jpg"
            acceptance._draw_image(shutil.which("magick"), source, "#cc2244", 64, 48)
            shutil.copy2(source, output)
            case = {"id": "m:A", "route": "convert", "args": [], "source_behavior": "derived", "fixtures": ["source.png"]}
            result = acceptance.validate_case_data(case, case_dir, {"source.png": acceptance.sha256(source)})
            self.assertTrue(any("extension suggests JPEG" in error for error in result["errors"]))
            self.assertTrue(any("Image fully decoded" in check for check in result["checks"]))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg/ffprobe unavailable")
    def test_real_video_validator_checks_codec_container_duration_and_full_decode(self):
        source_master = acceptance.GENERATED / "masters" / "video-audio.mp4"
        if not source_master.is_file():
            self.skipTest("generated video fixture is unavailable")
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp) / "case"
            case_dir.mkdir()
            source = case_dir / "source.mp4"
            output = case_dir / "result.mp4"
            shutil.copy2(source_master, source)
            shutil.copy2(source_master, output)
            source_info = acceptance._video_info(source)
            case_record = {"fixtures": [source.name], "baseline_video_info": {source.name: source_info}}
            (case_dir / "case.json").write_text(json.dumps(case_record))
            case = {"id": "menu:Video", "route": "video", "args": ["--size", "hd720", "--codec", "libx264", "--container", "mp4"],
                    "source_behavior": "authorized_overwrite", "fixtures": [source.name]}
            result = acceptance.validate_case_data(case, case_dir, {source.name: acceptance.sha256(source)})
            self.assertFalse(result["errors"], result["errors"])
            self.assertTrue(any("Duration approximately matches source" in check for check in result["checks"]))
            self.assertTrue(any("fully decoded" in check for check in result["checks"]))
            self.assertEqual(acceptance.sha256(source_master), acceptance.sha256(source))

    @unittest.skipUnless(shutil.which("magick") and shutil.which("exiftool"), "ImageMagick/ExifTool unavailable")
    def test_real_metadata_fixture_and_gps_validator_inspect_actual_tags_and_pixels(self):
        with tempfile.TemporaryDirectory() as tmp:
            case_dir = Path(tmp) / "case"
            case_dir.mkdir()
            source = Path(acceptance.GENERATED / "masters" / "metadata.jpg")
            if not source.is_file():
                self.skipTest("generated metadata fixture library has not been prepared")
            case_source = case_dir / "metadata.jpg"
            shutil.copy2(source, case_source)
            tags = acceptance._exiftool_json(case_source)
            self.assertTrue(any(key.startswith("GPS:") for key in tags))
            self.assertTrue(any(key.endswith("DateTimeOriginal") for key in tags))
            self.assertTrue(acceptance._icc_digest(case_source))
            output = case_dir / "metadata_gps.jpg"
            shutil.copy2(case_source, output)
            before = acceptance._image_signature(case_source)
            proc = acceptance._run([shutil.which("exiftool"), "-overwrite_original", "-GPS:all=", str(output)])
            self.assertEqual(0, proc.returncode, proc.stderr)
            os.utime(output, ns=(case_source.stat().st_atime_ns, case_source.stat().st_mtime_ns))
            case = {"id": "m:GPS", "route": "stripmeta", "args": ["--mode", "gps"],
                    "source_behavior": "derived", "fixtures": ["metadata.jpg"]}
            record = {"baseline_pixel_signatures": {"metadata.jpg": before},
                      "baseline_icc_sha256": {"metadata.jpg": acceptance._icc_digest(case_source)},
                      "baseline_mtime_ns": {"metadata.jpg": case_source.stat().st_mtime_ns},
                      "baseline_mode": {"metadata.jpg": case_source.stat().st_mode & 0o777},
                      "fixtures": ["metadata.jpg"]}
            (case_dir / "case.json").write_text(__import__("json").dumps(record))
            result = acceptance.validate_case_data(case, case_dir, {"metadata.jpg": acceptance.sha256(case_source)})
            self.assertFalse(result["errors"], result["errors"])
            self.assertEqual(before, acceptance._image_signature(output))

    def test_optional_validator_dependency_is_a_warning_not_a_pass_claim(self):
        with mock.patch.object(acceptance.shutil, "which", return_value=None):
            with self.assertRaises(FileNotFoundError):
                acceptance._image_info(Path("missing.png"))
        self.assertEqual("blocked", acceptance.capability("magick", False, "ImageMagick unavailable")["status"])

    def test_date_sync_validator_respects_local_wall_time_offsets_and_subseconds(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "photo.jpg"
            path.write_bytes(b"synthetic timestamp target")
            local_sec = int(time.mktime(time.strptime("2024:02:29 23:45:06", "%Y:%m:%d %H:%M:%S")))
            os.utime(path, ns=(local_sec * 1_000_000_000 + 123_000_000, local_sec * 1_000_000_000 + 123_000_000))
            self.assertTrue(acceptance._datetime_matches_file_mtime(path, {
                "ExifIFD:DateTimeOriginal": "2024:02:29 23:45:06", "ExifIFD:SubSecTimeOriginal": "123"}))
            utc_sec = int(datetime(2024, 3, 1, 1, 0, tzinfo=timezone(timedelta(hours=2))).timestamp())
            os.utime(path, ns=(utc_sec * 1_000_000_000, utc_sec * 1_000_000_000))
            self.assertTrue(acceptance._datetime_matches_file_mtime(path, {
                "ExifIFD:DateTimeOriginal": "2024:03:01 01:00:00", "ExifIFD:OffsetTimeOriginal": "+02:00"}))
            self.assertFalse(acceptance._datetime_matches_file_mtime(path, {"DateTimeOriginal": "not-a-date"}))


if __name__ == "__main__":
    unittest.main()
