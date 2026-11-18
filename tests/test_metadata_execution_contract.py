"""Focused M1 tests. Never publish metadata or create image outputs."""
import dataclasses
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0,
    os.environ.get(
        "KIMNG_TEST_RUNTIME", str(ROOT / "src/bin")
    ),
)

from kim_metadata_editor import (
    Draft, FIELD_SPECS, MetadataEditor, new_destination,
)
from kim_metadata_execution_plan import (
    build_execution_contract, verify_execution_contract,
)
from kim_metadata_reader import read_metadata
from kim_metadata_sources import SOURCE_PRIORITY_DEFAULT
from kim_location import build_manual_proposal


class MetadataExecutionContractTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which("magick"):
            self.skipTest("ImageMagick required for disposable images")

        self.directory = tempfile.TemporaryDirectory(prefix="kimng-m1-")
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.image = self.root / "camera.jpg"

        subprocess.run(
            ["magick", "-size", "12x10", "xc:blue", str(self.image)],
            check=True, stdout=subprocess.DEVNULL,
        )
        self.path = str(self.image)
        self.records = read_metadata([self.path])

        title = next(
            spec for spec in FIELD_SPECS if spec.key == "title"
        )
        target = new_destination(self.path, title)
        self.draft = Draft(
            "Replace", "A test title", target,
            authorize_new_target=True,
        )

    def plan(self, draft=None, source_drafts=()):
        drafts = {
            self.path: {
                "title": self.draft if draft is None else draft,
            }
        }
        return build_execution_contract(
            [self.path], self.records, drafts, (),
            source_drafts, {}, SOURCE_PRIORITY_DEFAULT,
        )

    def test_editor_has_lazy_contract_entry_point(self):
        self.assertTrue(
            callable(MetadataEditor.snapshot_execution_contract)
        )

    def test_frozen_target_and_no_publication(self):
        before = self.image.stat()
        existing = set(self.root.iterdir())

        plan = self.plan()

        self.assertFalse(plan.blocked)
        self.assertFalse(plan.publication_authorized)
        self.assertEqual(1, plan.schema_version)
        self.assertEqual(
            "XMP-dc:Title",
            plan.images[0].changes[0].target.qualified_tag,
        )
        self.assertEqual(
            "x-default",
            plan.images[0].changes[0].target.language,
        )
        self.assertFalse(Path(plan.images[0].output.path).exists())
        self.assertEqual(existing, set(self.root.iterdir()))

        after = self.image.stat()
        self.assertEqual(
            (
                before.st_size, before.st_atime_ns,
                before.st_mtime_ns, before.st_ctime_ns,
            ),
            (
                after.st_size, after.st_atime_ns,
                after.st_mtime_ns, after.st_ctime_ns,
            ),
        )

        verify_execution_contract(plan)

        with self.assertRaises(dataclasses.FrozenInstanceError):
            plan.images[0].source = "changed"

    def test_late_output_collision_is_blocked(self):
        plan = self.plan()
        Path(plan.images[0].output.path).write_text("occupied")

        with self.assertRaisesRegex(ValueError, "occupied"):
            verify_execution_contract(plan)

    def test_new_sidecar_blocks_stale_plan(self):
        plan = self.plan()
        self.image.with_suffix(".xmp").write_text(
            '<x:xmpmeta xmlns:x="adobe:ns:meta/"/>'
        )

        with self.assertRaisesRegex(ValueError, "Sidecar"):
            verify_execution_contract(plan)

    def test_changed_sidecar_blocks_stale_plan(self):
        sidecar = self.image.with_suffix(".xmp")
        sidecar.write_text(
            '<x:xmpmeta xmlns:x="adobe:ns:meta/"/>'
        )
        plan = self.plan()
        sidecar.write_text(
            '<x:xmpmeta xmlns:x="adobe:ns:meta/">changed</x:xmpmeta>'
        )

        with self.assertRaisesRegex(ValueError, "Sidecar"):
            verify_execution_contract(plan)

    def test_replaced_image_blocks_stale_plan(self):
        plan = self.plan()
        replacement = self.root / "replacement.jpg"
        shutil.copyfile(self.image, replacement)
        os.replace(replacement, self.image)

        with self.assertRaisesRegex(ValueError, "Image changed"):
            verify_execution_contract(plan)

    def test_unqualified_target_is_blocked(self):
        plan = self.plan(draft=Draft("Replace", "Test", None))

        self.assertTrue(plan.blocked)
        self.assertIn(
            "qualified", plan.images[0].changes[0].reason
        )

    def test_unqualified_sync_cannot_be_compiled(self):
        draft = dataclasses.replace(self.draft, sync=True)
        plan = self.plan(draft=draft)

        self.assertTrue(plan.blocked)
        self.assertIn(
            "synchronization",
            plan.images[0].changes[0].reason,
        )

    def test_duplicate_target_is_blocked(self):
        plan = self.plan(
            source_drafts=[(self.path, "title", self.draft)]
        )
        self.assertTrue(plan.blocked)
        self.assertEqual(
            2,
            sum(
                change.status == "blocked"
                for change in plan.images[0].changes
            ),
        )

    def test_gps_only_png_contract(self):
        png = self.root / "no-gps.png"
        subprocess.run(
            ["magick", "-size", "12x10", "xc:blue", str(png)],
            check=True, stdout=subprocess.DEVNULL,
        )
        proposal = build_manual_proposal(
            str(png),
            {
                "method": "manual",
                "latitude": "42.1",
                "longitude": "-71.2",
            },
        )
        self.assertEqual(
            "valid", proposal["status"], proposal.get("blocked")
        )

        plan = build_execution_contract(
            [str(png)], {}, {}, (), (),
            {str(png): proposal}, SOURCE_PRIORITY_DEFAULT,
        )
        self.assertEqual(
            "valid", plan.images[0].changes[0].status
        )
        self.assertFalse(plan.blocked)
        self.assertFalse(plan.publication_authorized)
        self.assertFalse(Path(plan.images[0].output.path).exists())

        verify_execution_contract(plan)


if __name__ == "__main__":
    unittest.main()
