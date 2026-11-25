"""Behavior tests for the offline Photo Story publishing seam."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/bin"))

from kim_story_publication import (  # noqa: E402
    GALLERY_TYPES, IMAGE_LAYOUTS, LEGACY_STYLES, OUTPUT_FORMATS,
    TYPE_DEFAULT_LAYOUTS, VISUAL_STYLES, StoryDocument, StoryElement,
    composition_plan, default_layout_for_type, make_document,
    canonical_visual_style, prepare_publication, publish_prepared,
    publish_prepared_zip, render_website,
)
from kim_preview import identity, inspection_path  # noqa: E402
from PySide6.QtGui import QImage


class StoryPublicationRenderingTests(unittest.TestCase):
    def setUp(self):
        self.doc = StoryDocument(
            title="Harbor <at dusk>",
            introduction="First paragraph.\n\nSecond paragraph.",
            publication_type="photo-essay",
            style="editorial",
            hide_filenames=True,
            elements=(
                StoryElement("image", "one", "", "Light & water", "", "images/001-one.jpg", "/photos/one.jpg"),
                StoryElement("image", "two", "Second frame", "A caption", "", "images/002-two.jpg", "/photos/two.jpg"),
                StoryElement("image", "two-b", "", "A second view", "", "images/003-two-b.jpg", "/photos/two-b.jpg"),
                StoryElement("heading", "chapter", "The crossing", "", "", ""),
                StoryElement("text", "words", "", "", "A <quiet> walk.\n\nThen home.", ""),
                StoryElement("image", "three", "", "", "", "images/004-three.jpg", "/photos/three.jpg"),
            ),
        )

    def test_single_image_description_uses_displayed_image_width(self):
        from dataclasses import replace

        elements = tuple(
            replace(
                item,
                image_width=432,
                image_height=648,
                description=(
                    "Alignment regression paragraph."
                    if item.id == "two"
                    else item.description
                ),
            )
            if item.kind == "image" else item
            for item in self.doc.elements
        )
        document = replace(
            self.doc,
            publication_type="travelogue",
            layout="one-per-section",
            elements=elements,
        )

        rendered = render_website(document)

        self.assertIn(
            "--story-image-render-width:"
            " min(100%, 432px, calc(83svh * 0.66666667))",
            rendered.html,
        )
        self.assertIn(
            "width: var(--story-image-render-width, 100%)",
            rendered.css,
        )
        self.assertIn(
            ".image-feature.layout-one-per-section",
            rendered.css,
        )
        self.assertIn(
            'data-description-for="two"',
            rendered.html,
        )
        self.assertIn(
            "Alignment regression paragraph.",
            rendered.html,
        )

    def test_composition_is_deterministic_and_keeps_consecutive_image_pairs_ordered(self):
        plan = composition_plan(self.doc)
        self.assertEqual(
            [(block.kind, [item.id for item in block.elements]) for block in plan],
            [("hero", ["one"]), ("pair", ["two", "two-b"]), ("section", ["chapter"]),
             ("passage", ["words"]), ("feature", ["three"])],
        )
        self.assertEqual(plan, composition_plan(self.doc))

    def test_html_escapes_authored_text_and_preserves_paragraphs_and_caption_identity(self):
        rendered = render_website(self.doc)
        self.assertIn("Harbor &lt;at dusk&gt;", rendered.html)
        self.assertIn("A &lt;quiet&gt; walk.", rendered.html)
        self.assertIn("Then home.", rendered.html)
        self.assertNotIn("<quiet>", rendered.html)
        self.assertIn("Light &amp; water", rendered.html)
        self.assertNotIn("A caption", rendered.html)
        visible_caption = StoryDocument(**{**self.doc.__dict__, "show_captions": True})
        self.assertIn("A caption", render_website(visible_caption).html)
        self.assertIn("images/002-two.jpg", rendered.html)
        self.assertNotIn('<h2 class="image-heading">three.jpg', rendered.html)
        self.assertEqual(rendered.html.count('src="images/001-one.jpg"'), 1)
        self.assertLess(rendered.html.index("images/001-one.jpg"),
                        rendered.html.index("images/002-two.jpg"))
        self.assertLess(rendered.html.index("images/002-two.jpg"),
                        rendered.html.index("<h2>The crossing</h2>"))
        self.assertIn('href="#section-chapter-', rendered.html)
        self.assertIn('id="section-chapter-', rendered.html)

    def test_filename_visibility_hides_automatic_titles_but_keeps_authored_headings(self):
        hidden = render_website(self.doc)
        visible_doc = StoryDocument(**{**self.doc.__dict__, "hide_filenames": False})
        visible = render_website(visible_doc)
        self.assertNotIn('class="image-filename">three.jpg', hidden.html)
        self.assertIn('class="image-filename">three.jpg', visible.html)
        self.assertIn('class="image-heading">Second frame</h2>', hidden.html)

    def test_styles_are_structurally_distinct_and_offline(self):
        html_by_style = {}
        for style in ("cinematic", "editorial", "journal"):
            doc = StoryDocument(**{**self.doc.__dict__, "style": style})
            rendered = render_website(doc)
            html_by_style[style] = rendered.html
            self.assertIn('href="style.css"', rendered.html)
            self.assertNotIn("https://", rendered.html)
            self.assertNotIn("http://", rendered.html)
            self.assertIn('publication style-' + style + ' ', rendered.html)
            self.assertIn("@media", rendered.css)
            self.assertIn("prefers-reduced-motion", rendered.css)
        self.assertEqual(len(set(html_by_style.values())), 3)

    def test_viewer_links_are_available_without_replacing_the_scrolling_gallery(self):
        rendered = render_website(self.doc)
        self.assertEqual(rendered.html.count('class="gallery-viewer-trigger"'), 4)
        self.assertIn('<main id="story" class="story-flow">', rendered.html)
        self.assertIn('href="images/001-one.jpg"', rendered.html)
        self.assertIn('aria-haspopup="dialog"', rendered.html)
        self.assertIn('id="gallery-viewer"', rendered.html)
        self.assertIn('aria-label="Image viewer"', rendered.html)
        self.assertIn('href="gallery-viewer.css"', rendered.html)
        self.assertIn('src="gallery-viewer.js"', rendered.html)
        self.assertIn('data-viewer-action="previous"', rendered.html)
        self.assertIn('data-viewer-action="next"', rendered.html)
        self.assertIn('data-viewer-action="zoom-in"', rendered.html)
        self.assertIn('data-viewer-action="zoom-out"', rendered.html)
        self.assertNotIn('data-viewer-caption=', rendered.html)
        self.assertIn('prefers-reduced-motion', rendered.viewer_css)
        self.assertIn('ArrowRight', rendered.viewer_js)
        self.assertIn('Escape', rendered.viewer_js)
        self.assertNotIn('/photos/one.jpg', rendered.html)
        self.assertNotIn('http://', rendered.viewer_js + rendered.viewer_css)
        with_captions = render_website(StoryDocument(**{
            **self.doc.__dict__, "show_captions": True,
        }))
        self.assertIn('data-viewer-caption="A caption"', with_captions.html)

    def test_gallery_types_and_visual_styles_are_independent_and_supported(self):
        self.assertEqual(GALLERY_TYPES, ("travelogue", "photo-essay", "illustrated-story", "simple-gallery"))
        self.assertEqual(VISUAL_STYLES, ("classic", "modern", "dramatic", "simple-light", "simple-dark"))
        self.assertEqual(LEGACY_STYLES, ("cinematic", "editorial", "journal"))
        self.assertEqual(IMAGE_LAYOUTS, ("one-per-section", "two-per-section", "adaptive"))
        self.assertEqual(OUTPUT_FORMATS, ("folder", "zip"))
        self.assertEqual(TYPE_DEFAULT_LAYOUTS, {
            "simple-gallery": "one-per-section", "travelogue": "one-per-section",
            "photo-essay": "adaptive", "illustrated-story": "one-per-section",
        })
        self.assertEqual({key: canonical_visual_style(key) for key in VISUAL_STYLES}, {
            "classic": "classic", "modern": "modern", "dramatic": "dramatic",
            "simple-light": "simple-light", "simple-dark": "simple-dark",
        })
        self.assertEqual({key: canonical_visual_style(key) for key in LEGACY_STYLES}, {
            "cinematic": "dramatic", "editorial": "modern", "journal": "classic",
        })
        self.assertEqual(default_layout_for_type("travelogue"), "one-per-section")
        self.assertEqual(default_layout_for_type("photo-essay"), "adaptive")
        self.assertEqual(default_layout_for_type("illustrated-story"), "one-per-section")
        rendered = {}
        for gallery_type in GALLERY_TYPES:
            for visual_style in VISUAL_STYLES:
                document = StoryDocument(**{
                    **self.doc.__dict__, "publication_type": gallery_type,
                    "style": visual_style, "layout": default_layout_for_type(gallery_type),
                })
                page = render_website(document)
                rendered[(gallery_type, visual_style)] = page
                self.assertIn(f'data-gallery-type="{gallery_type}"', page.html)
                self.assertIn(f'data-visual-style="{visual_style}"', page.html)
                self.assertIn(f'gallery-type-{gallery_type}', page.html)
                self.assertIn("@media", page.css)
        self.assertNotEqual(rendered[("travelogue", "classic")].html,
                            rendered[("illustrated-story", "classic")].html)
        self.assertNotEqual(rendered[("travelogue", "classic")].css,
                            rendered[("travelogue", "dramatic")].css)

    def test_one_image_layout_never_pairs_and_two_image_layout_is_bounded(self):
        images = tuple(StoryElement(
            "image", f"aspect-{index}", output_image=f"images/{index:04}.jpg",
            source=f"/private/{index}.jpg", image_width=4000 if index % 2 else 900,
            image_height=600 if index % 2 else 1400,
        ) for index in range(7))
        for layout, maximum in (("one-per-section", 1), ("two-per-section", 2)):
            document = StoryDocument("Story", "", "travelogue", "classic", True,
                                     images, layout=layout)
            plan = composition_plan(document)
            self.assertEqual([item.id for block in plan for item in block.elements],
                             [item.id for item in images])
            self.assertTrue(all(len(block.elements) <= maximum for block in plan))
            self.assertEqual(plan, composition_plan(document))

    def test_descriptions_are_separate_from_optional_captions_and_layout_mode(self):
        image = StoryElement(
            "image", "one", "Harbor", "Short caption", "", "images/0001.jpg",
            "/private/harbor.jpg", description="First paragraph.\n\nSecond paragraph.",
        )
        one = StoryDocument(**{
            **self.doc.__dict__, "elements": (image,), "layout": "one-per-section",
            "show_captions": False, "hide_filenames": True,
        })
        html_one = render_website(one).html
        self.assertIn("First paragraph.", html_one)
        self.assertIn("Second paragraph.", html_one)
        self.assertNotIn("Short caption", html_one)
        self.assertNotIn("harbor", html_one)
        self.assertNotIn("/private/harbor.jpg", html_one)
        self.assertIn('class="image-description prose"', html_one)

        captions_visible = StoryDocument(**{**one.__dict__, "show_captions": True})
        self.assertIn("Short caption", render_website(captions_visible).html)
        self.assertEqual(captions_visible.elements[0].caption, "Short caption")

    def test_layout_modes_bound_groups_and_never_cross_narrative_elements(self):
        images = tuple(StoryElement(
            "image", f"i{index}", output_image=f"images/{index:04}.jpg",
            source=f"/private/{index}.jpg", image_width=600, image_height=900,
            description=f"Description {index}",
        ) for index in range(4))
        sequence = (images[0], images[1],
                    StoryElement("heading", "chapter", "A chapter"), images[2],
                    StoryElement("text", "passage", text="A pause."), images[3])
        base = StoryDocument("Story", "", "photo-essay", "journal", True, sequence)
        for layout in ("one-per-section", "two-per-section", "adaptive"):
            document = StoryDocument(**{**base.__dict__, "layout": layout})
            blocks = composition_plan(document)
            self.assertEqual([e.id for block in blocks for e in block.elements],
                             [e.id for e in sequence])
            self.assertTrue(all(len(block.elements) == 1 for block in blocks
                                if layout == "one-per-section" and block.kind in {"hero", "feature", "pair"}))
            self.assertTrue(all(len(block.elements) <= 2 for block in blocks))
            self.assertEqual(blocks, composition_plan(document))
            rendered = render_website(document)
            self.assertIn(f'data-image-layout="{layout}"', rendered.html)
            self.assertEqual(rendered.html.count('data-description-for="i0"'), 1)
            self.assertEqual(rendered.html.count('data-description-for="i1"'), 1)
            self.assertNotIn("Short caption", rendered.html)

    def test_make_document_preserves_legacy_caption_and_distinct_description(self):
        from types import SimpleNamespace
        source = SimpleNamespace(
            kind="image", id="legacy", source="/private/legacy.jpg",
            heading="Authored heading", caption="Existing caption", text="",
            description="New long-form description",
        )
        document = make_document(
            "Story", "Intro", [source], style="editorial", hide_filenames=True,
            source_identities={source.source: (1, 2, 3)},
            show_captions=False, layout="two-per-section",
        )
        self.assertEqual(document.elements[0].caption, "Existing caption")
        self.assertEqual(document.elements[0].description, "New long-form description")
        self.assertFalse(document.show_captions)
        self.assertEqual(document.layout, "two-per-section")

    def test_blank_content_does_not_invent_nav_labels_or_text(self):
        doc = StoryDocument(
            "", "", "photo-essay", "journal", True,
            (StoryElement("heading", "blank", "", "", "", ""),
             StoryElement("text", "empty", "", "", "", "")),
        )
        rendered = render_website(doc)
        self.assertIn("Untitled story", rendered.html)
        self.assertNotIn("Empty text", rendered.html)
        self.assertNotIn('href="#section-blank"', rendered.html)
        self.assertIn('class="story-title placeholder"', rendered.html)

    def test_output_format_is_validated_as_part_of_the_publication_snapshot(self):
        document = StoryDocument(**{**self.doc.__dict__, "output_format": "zip"})
        self.assertIn('data-output-format="zip"', render_website(document).html)
        invalid = StoryDocument(**{**self.doc.__dict__, "output_format": "pdf"})
        with self.assertRaisesRegex(ValueError, "output format"):
            render_website(invalid)


class StoryPublicationSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="kim-story-publish-test-")
        self.root = Path(self.temp.name)
        self.sources = self.root / "sources"
        self.sources.mkdir()
        self.workspace = self.root / "private-preview"

    def tearDown(self):
        self.temp.cleanup()

    def make_source(self, name, color):
        path = self.sources / name
        image = QImage(96, 64, QImage.Format_RGB32)
        image.fill(color)
        self.assertTrue(image.save(str(path), "PNG"))
        return str(path)

    def test_rendered_viewer_assets_are_included_in_reviewed_folder_and_zip(self):
        from zipfile import ZipFile

        source = self.make_source("viewer-photo.png", 0xff476d83)
        folder_document = self.document_for([source])
        prepared = prepare_publication(folder_document, str(self.workspace / "folder"))
        for name in ("gallery-viewer.css", "gallery-viewer.js"):
            self.assertTrue((Path(prepared.workspace) / name).is_file())
        folder_target = self.root / "viewer-gallery"
        publish_prepared(prepared, str(folder_target))
        self.assertTrue((folder_target / "gallery-viewer.css").is_file())
        self.assertTrue((folder_target / "gallery-viewer.js").is_file())

        zip_document = self.document_for([source], output_format="zip")
        zip_prepared = prepare_publication(zip_document, str(self.workspace / "zip"))
        zip_target = self.root / "viewer-gallery.zip"
        publish_prepared_zip(zip_prepared, str(zip_target), gallery_name="viewer-gallery")
        with ZipFile(zip_target) as archive:
            names = set(archive.namelist())
            self.assertIn("viewer-gallery/gallery-viewer.css", names)
            self.assertIn("viewer-gallery/gallery-viewer.js", names)
            self.assertIsNone(archive.testzip())

    @staticmethod
    def digest(path):
        with inspection_path(path) as (_, fd):
            stream = os.fdopen(os.dup(fd), "rb", buffering=0)
            try:
                return hashlib.file_digest(stream, "sha256").hexdigest()
            finally:
                stream.close()

    def document_for(self, paths, style="modern", output_format="folder"):
        from types import SimpleNamespace
        elements = [SimpleNamespace(kind="image", id=f"image-{i}", source=path,
                                    heading=f"Frame {i}" if i == 0 else "",
                                    caption=f"Caption {i}", text="")
                    for i, path in enumerate(paths)]
        stamps = {path: identity(path) for path in paths}
        return make_document("Light on water", "A real story.", elements,
                             style=style, hide_filenames=True,
                             source_identities=stamps, output_format=output_format)

    def test_prepare_and_publish_preserve_sources_strip_metadata_and_refuse_collisions(self):
        source = self.make_source("harbor.png", 0xff426780)
        if shutil.which("exiftool"):
            tagged = subprocess.run(
                ["exiftool", "-overwrite_original", "-GPSLatitude=51.5",
                 "-GPSLongitude=-0.1", source], capture_output=True, text=True)
            self.assertEqual(tagged.returncode, 0, tagged.stderr)
        before = (self.digest(source), os.stat(source).st_atime_ns,
                  os.stat(source).st_mtime_ns, os.stat(source).st_ctime_ns)
        prepared = prepare_publication(self.document_for([source]), str(self.workspace))
        derivative = Path(prepared.images[0].staged_path)
        self.assertEqual(prepared.images[0].relative_path, "images/0001.jpg")
        self.assertIn('width="96" height="64"', prepared.index_html)
        self.assertEqual(derivative.read_bytes()[:2], b"\xff\xd8")
        self.assertNotIn(b"Exif\x00\x00", derivative.read_bytes())
        if shutil.which("exiftool"):
            metadata = subprocess.run(
                ["exiftool", "-json", "-GPS:all", str(derivative)],
                capture_output=True, text=True, check=True)
            self.assertFalse(any(key.startswith("GPS")
                                 for key in json.loads(metadata.stdout)[0]))
        after_prepare = (self.digest(source), os.stat(source).st_atime_ns,
                         os.stat(source).st_mtime_ns, os.stat(source).st_ctime_ns)
        self.assertEqual(after_prepare, before)

        destination = self.root / "published"
        self.assertEqual(publish_prepared(prepared, str(destination)), str(destination))
        self.assertEqual(sorted(path.name for path in destination.iterdir()),
                         ["gallery-viewer.css", "gallery-viewer.js", "images",
                          "index.html", "style.css"])
        self.assertTrue((destination / "images/0001.jpg").is_file())
        with self.assertRaises(FileExistsError):
            publish_prepared(prepared, str(destination))
        after_publish = (self.digest(source), os.stat(source).st_atime_ns,
                         os.stat(source).st_mtime_ns, os.stat(source).st_ctime_ns)
        self.assertEqual(after_publish, before)

    def test_zip_publication_contains_a_safe_gallery_tree_and_is_create_only(self):
        import zipfile
        source = self.make_source("zip-cover.png", 0xff426780)
        prepared = prepare_publication(
            self.document_for([source], output_format="zip"), str(self.workspace))
        before = (self.digest(source), os.stat(source).st_atime_ns,
                  os.stat(source).st_mtime_ns, os.stat(source).st_ctime_ns)
        destination = self.root / "light-on-water.zip"
        self.assertEqual(publish_prepared_zip(
            prepared, str(destination), gallery_name="light-on-water"), str(destination))
        with zipfile.ZipFile(destination) as archive:
            names = archive.namelist()
            self.assertEqual(names, ["light-on-water/index.html", "light-on-water/style.css",
                                     "light-on-water/gallery-viewer.css",
                                     "light-on-water/gallery-viewer.js",
                                     "light-on-water/images/0001.jpg"])
            self.assertEqual(len(names), len(set(names)))
            self.assertTrue(all(not name.startswith("/") and ".." not in Path(name).parts
                                for name in names))
            self.assertIn(b"Light on water", archive.read("light-on-water/index.html"))
            self.assertEqual(archive.testzip(), None)
            self.assertTrue(all((info.external_attr >> 16) & 0o170000 != 0o120000
                                for info in archive.infolist()))
        self.assertEqual((self.digest(source), os.stat(source).st_atime_ns,
                          os.stat(source).st_mtime_ns, os.stat(source).st_ctime_ns), before)
        original = destination.read_bytes()
        second_archive = self.root / "light-on-water-copy.zip"
        publish_prepared_zip(prepared, str(second_archive), gallery_name="light-on-water")
        self.assertEqual(second_archive.read_bytes(), original)
        with self.assertRaises(FileExistsError):
            publish_prepared_zip(prepared, str(destination), gallery_name="light-on-water")
        self.assertEqual(destination.read_bytes(), original)

    def test_zip_late_collision_source_change_parent_change_and_cancellation_fail_closed(self):
        source = self.make_source("zip-late.png", 0xff426780)
        prepared = prepare_publication(
            self.document_for([source], output_format="zip"), str(self.workspace))
        destination = self.root / "late.zip"
        destination.write_bytes(b"user-owned")
        with self.assertRaises(FileExistsError):
            publish_prepared_zip(prepared, str(destination), gallery_name="gallery")
        self.assertEqual(destination.read_bytes(), b"user-owned")
        symlink_target = self.root / "zip-linked.zip"
        symlink_target.symlink_to(destination)
        with self.assertRaises(FileExistsError):
            publish_prepared_zip(prepared, str(symlink_target), gallery_name="gallery")

        late_destination = self.root / "zip-late-collision.zip"
        def occupy_after_review(current, total, _name):
            if current == total:
                late_destination.write_bytes(b"appeared-after-review")
        with self.assertRaisesRegex(FileExistsError, "appeared after review"):
            publish_prepared_zip(prepared, str(late_destination), gallery_name="gallery",
                                 progress=occupy_after_review)
        self.assertEqual(late_destination.read_bytes(), b"appeared-after-review")
        self.assertEqual(list(self.root.glob(".zip-late-collision.zip.kimng-stage-*")), [])

        parent = self.root / "approved-zip-parent"
        parent.mkdir()
        info = parent.stat()
        approved = (info.st_dev, info.st_ino)
        changed_destination = parent / "changed.zip"
        moved = self.root / "moved-zip-parent"
        parent.rename(moved)
        parent.mkdir()
        with self.assertRaisesRegex(ValueError, "parent changed"):
            publish_prepared_zip(prepared, str(changed_destination), gallery_name="gallery",
                                 approved_parent_identity=approved)
        self.assertFalse(changed_destination.exists())

        changed = QImage(96, 64, QImage.Format_RGB32)
        changed.fill(0xff552211)
        self.assertTrue(changed.save(source, "PNG"))
        with self.assertRaisesRegex(ValueError, "Source changed"):
            publish_prepared_zip(prepared, str(self.root / "changed-source.zip"),
                                 gallery_name="gallery")
        self.assertFalse((self.root / "changed-source.zip").exists())

        fresh = self.make_source("zip-cancel.png", 0xff779955)
        fresh_prepared = prepare_publication(
            self.document_for([fresh], output_format="zip"), str(self.workspace))
        cancelled = [False]
        def cancel_after_write(current, _total, _name):
            if current >= 1:
                cancelled[0] = True
        cancel_destination = self.root / "cancel.zip"
        with self.assertRaisesRegex(InterruptedError, "cancelled"):
            publish_prepared_zip(fresh_prepared, str(cancel_destination), gallery_name="gallery",
                                 cancelled=lambda: cancelled[0], progress=cancel_after_write)
        self.assertFalse(cancel_destination.exists())
        self.assertEqual(list(self.root.glob(".cancel.zip.kimng-stage-*")), [])

    def test_source_change_after_review_blocks_publication_and_symlink_destination_is_blocked(self):
        source = self.make_source("portrait.png", 0xffb77c45)
        prepared = prepare_publication(self.document_for([source]), str(self.workspace))
        changed = QImage(96, 64, QImage.Format_RGB32)
        changed.fill(0xff552211)
        self.assertTrue(changed.save(source, "PNG"))
        with self.assertRaisesRegex(ValueError, "Source changed"):
            publish_prepared(prepared, str(self.root / "changed-output"))
        link = self.root / "linked-output"
        link.symlink_to(self.root / "somewhere")
        fresh_source = self.make_source("safe-again.png", 0xff997755)
        safe_prepared = prepare_publication(self.document_for([fresh_source]), str(self.workspace))
        with self.assertRaises(FileExistsError):
            publish_prepared(safe_prepared, str(link))

    def test_destination_collision_is_not_overwritten_or_silently_renamed(self):
        source = self.make_source("late.png", 0xff447799)
        prepared = prepare_publication(self.document_for([source]), str(self.workspace))
        destination = self.root / "late-collision"
        destination.mkdir()
        marker = destination / "keep.txt"
        marker.write_text("existing", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            publish_prepared(prepared, str(destination))
        self.assertEqual(marker.read_text(encoding="utf-8"), "existing")
        self.assertEqual(list(self.root.glob(".late-collision.kimng-stage-*")), [])

    def test_changed_destination_parent_after_review_is_blocked(self):
        source = self.make_source("parent-check.png", 0xff447755)
        prepared = prepare_publication(self.document_for([source]), str(self.workspace))
        parent = self.root / "approved-parent"
        parent.mkdir()
        info = parent.stat()
        approved = (info.st_dev, info.st_ino)
        destination = parent / "site"
        moved = self.root / "original-parent"
        parent.rename(moved)
        parent.mkdir()
        with self.assertRaisesRegex(ValueError, "parent changed"):
            publish_prepared(prepared, str(destination), approved_parent_identity=approved)
        self.assertFalse(destination.exists())

    def test_cancellation_removes_only_the_private_stage_and_publishes_nothing(self):
        paths = [self.make_source(f"cancel-{i}.png", 0xff335577 + i)
                 for i in range(2)]
        prepared = prepare_publication(self.document_for(paths), str(self.workspace))
        cancelled = [False]
        destination = self.root / "cancelled-output"

        def report(current, total, _name):
            if current == 1:
                cancelled[0] = True

        with self.assertRaisesRegex(InterruptedError, "cancelled"):
            publish_prepared(prepared, str(destination),
                             cancelled=lambda: cancelled[0], progress=report)
        self.assertFalse(destination.exists())
        self.assertEqual(list(self.root.glob(".cancelled-output.kimng-stage-*")), [])

    def test_seventy_one_images_prepare_to_bounded_unique_local_assets(self):
        paths = [self.make_source(f"frame-{index:03}.png", 0xff000000 | index)
                 for index in range(71)]
        prepared = prepare_publication(self.document_for(paths, style="cinematic"),
                                       str(self.workspace))
        self.assertEqual(len(prepared.images), 71)
        self.assertEqual(len({image.relative_path for image in prepared.images}), 71)
        self.assertEqual(prepared.index_html.count('data-element-id="image-0"'), 1)
        self.assertEqual(len(list((self.workspace / "images").glob("*.jpg"))), 71)
        self.assertLess(max(image.byte_size for image in prepared.images), 100_000)

    def test_unavailable_image_is_listed_and_blocks_apply_without_broken_output_links(self):
        source = self.make_source("unavailable.png", 0xff447799)
        document = self.document_for([source])
        Path(source).unlink()
        prepared = prepare_publication(document, str(self.workspace))
        self.assertEqual(len(prepared.blocked), 1)
        self.assertEqual(Path(prepared.blocked[0].source).name, "unavailable.png")
        self.assertIn("Photograph unavailable", prepared.index_html)
        self.assertNotIn("images/0001.jpg", prepared.index_html)
        self.assertNotIn(source, prepared.index_html)
        with self.assertRaisesRegex(ValueError, "blocked by unavailable images"):
            publish_prepared(prepared, str(self.root / "blocked-site"))
        self.assertFalse((self.root / "blocked-site").exists())


if __name__ == "__main__":
    unittest.main()
