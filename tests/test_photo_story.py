"""Focused behavior tests for the in-memory Photo Story editor."""

import os
from pathlib import Path
import hashlib
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/bin'))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PySide6.QtCore import QPoint, Qt, QEventLoop, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QSizePolicy

from kim_photo_story_dialog import PhotoStoryDialog, StorySequence
from kim_photo_story_preview import StoryPreviewWindow, build_composition_plan
from kim_preview import identity, inspection_path


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if predicate():
            return
        loop = QEventLoop()
        QTimer.singleShot(5, loop.quit)
        loop.exec()
    raise AssertionError('Qt operation did not settle')


def safe_digest(path):
    with inspection_path(path) as (_, fd):
        with os.fdopen(os.dup(fd), 'rb', buffering=0) as stream:
            return hashlib.file_digest(stream, 'sha256').digest()


class StorySequenceTests(unittest.TestCase):
    def test_mixed_elements_keep_identity_and_content_when_moved(self):
        sequence = StorySequence()
        first = sequence.add_image('/photos/harbor.jpg')
        heading = sequence.add_heading('The first morning', after_id=first.id)
        second = sequence.add_image('/photos/valletta.jpg')
        passage = sequence.add_text('Finding our way\n\nOne step at a time.', after_id=second.id)
        second.heading = 'Along the coast'
        second.caption = 'A quiet path.'

        sequence.move(heading.id, 0)
        sequence.move(passage.id, 1)

        self.assertEqual(
            [(item.kind, item.title_or_text) for item in sequence.elements],
            [('heading', 'The first morning'), ('text', 'Finding our way\n\nOne step at a time.'),
             ('image', ''), ('image', '')],
        )
        self.assertEqual(sequence.get(second.id).source, '/photos/valletta.jpg')
        self.assertEqual(sequence.get(second.id).heading, 'Along the coast')
        self.assertEqual(sequence.get(second.id).caption, 'A quiet path.')
        self.assertEqual(len({item.id for item in sequence.elements}), 4)

    def test_insertion_after_selection_append_without_selection_and_remove(self):
        sequence = StorySequence()
        image = sequence.add_image('/photos/one.jpg')
        heading = sequence.add_heading(after_id=image.id)
        passage = sequence.add_text(after_id=image.id)
        tail = sequence.add_text()

        self.assertEqual([item.id for item in sequence.elements],
                         [image.id, passage.id, heading.id, tail.id])
        self.assertEqual(sequence.get(heading.id).text, '')
        self.assertEqual(sequence.remove(passage.id).id, passage.id)
        self.assertEqual([item.id for item in sequence.elements],
                         [image.id, heading.id, tail.id])

    def test_duplicate_source_is_not_added_twice(self):
        sequence = StorySequence()
        first = sequence.add_image('/photos/one.jpg')
        self.assertIsNone(sequence.add_image('/photos/one.jpg'))
        self.assertEqual(len(sequence.elements), 1)
        self.assertEqual(sequence.elements[0].id, first.id)


class PhotoStoryDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kimng-photo-story-')
        self.root = Path(self.temp.name)
        self.paths = []
        for name, color in (('harbor.png', 0xff46677c), ('coast.png', 0xffd4a66a)):
            path = self.root / name
            image = QImage(240, 160, QImage.Format_RGB32)
            image.fill(color)
            self.assertTrue(image.save(str(path)))
            self.paths.append(str(path))
        self.dialog = PhotoStoryDialog(self.paths)
        self.dialog.show()
        wait_until(lambda: all(
            path in self.dialog.sequence_view.thumbnails
            or path in self.dialog.sequence_view.unavailable
            for path in self.paths
        ))

    def tearDown(self):
        self.dialog.close()
        wait_until(lambda: self.dialog.sequence_view.thumbnail_worker is None)
        self.temp.cleanup()

    def select(self, element_id):
        row = self.dialog.sequence.index_of(element_id)
        self.dialog.story_list.setCurrentRow(row)
        QApplication.processEvents()

    def test_continuous_editors_and_website_style_switch_preserve_content(self):
        first, second = self.dialog.sequence.elements
        self.select(first.id)
        self.dialog.image_heading.setText('Harbor at sunset')
        self.dialog.image_caption.setPlainText('Boats return.\nLights come on.')

        heading = self.dialog.add_heading()
        self.dialog.heading_editor.setText('The first morning')
        passage = self.dialog.add_text()
        self.dialog.text_editor.setPlainText('Finding our way\n\nPast the old walls.')
        self.assertEqual(self.dialog.sequence.elements,
                         [first, heading, passage, second])

        self.assertEqual(self.dialog.canvas_blocks[heading.id].heading_editor.text(),
                         'The first morning')
        self.assertEqual(self.dialog.canvas_blocks[passage.id].passage_editor.toPlainText(),
                         'Finding our way\n\nPast the old walls.')

        ids = [self.dialog.visual_style_selector.itemData(i)
               for i in range(self.dialog.visual_style_selector.count())]
        for i in range(self.dialog.visual_style_selector.count()):
            self.dialog.visual_style_selector.setCurrentIndex(i)
            QApplication.processEvents()
            self.assertEqual(self.dialog.sequence.get(passage.id).text,
                             'Finding our way\n\nPast the old walls.')
        self.assertEqual(ids, ['classic', 'modern', 'dramatic', 'simple-light', 'simple-dark'])

        self.select(first.id)
        self.assertEqual(self.dialog.sequence.get(first.id).heading, 'Harbor at sunset')
        self.assertEqual(self.dialog.sequence.get(first.id).caption,
                         'Boats return.\nLights come on.')
        self.assertEqual(self.dialog.canvas_blocks[first.id].description_editor.toPlainText(), '')

    def test_move_remove_status_and_filename_visibility(self):
        first, second = self.dialog.sequence.elements
        heading = self.dialog.add_heading(after_id=first.id)
        self.dialog.heading_editor.setText('The coast')
        self.dialog.move_element(heading.id, 2)
        self.assertEqual(self.dialog.sequence.elements[1], second)
        self.assertEqual(self.dialog.sequence.elements[2], heading)
        self.assertEqual(self.dialog.active_element_id, heading.id)
        self.assertIn('2 images, 1 heading, 0 text passages', self.dialog.status.text())

        self.dialog.remove_element(heading.id)
        self.assertEqual(self.dialog.active_element_id, second.id)
        self.assertEqual(len(self.dialog.sequence.elements), 2)
        self.assertFalse(self.dialog.show_filenames.isChecked())
        self.dialog.show_filenames.setChecked(True)
        self.select(second.id)
        self.dialog.image_heading.setText('User title')
        self.assertEqual(self.dialog.sequence.get(second.id).heading, 'User title')

    def test_passage_editor_is_multiline_and_story_order_fills_panel(self):
        passage = self.dialog.add_text()
        self.assertIsInstance(self.dialog.text_editor, QPlainTextEdit)
        self.assertGreaterEqual(self.dialog.text_editor.minimumHeight(), 120)
        self.assertEqual(self.dialog.story_list.sizePolicy().verticalPolicy(),
                         QSizePolicy.Policy.Expanding)
        self.dialog.text_editor.setPlainText('One\n\nTwo')
        self.assertEqual(self.dialog.sequence.get(passage.id).text, 'One\n\nTwo')

    def test_destination_defaults_beside_one_source_folder_and_requires_shared_parent_for_mixed_sources(self):
        self.assertEqual(self.dialog.destination_parent, str(self.root))
        other_dir = self.root / 'another-folder'
        other_dir.mkdir()
        image_path = other_dir / 'third.png'
        image = QImage(80, 60, QImage.Format_RGB32)
        image.fill(0xff557799)
        self.assertTrue(image.save(str(image_path)))
        self.dialog.add_paths([str(image_path)])
        self.assertEqual(self.dialog.destination_parent, '')
        self.assertIn('choose a shared destination', self.dialog.destination_label.text().lower())

    def test_drag_reorder_keeps_selection_and_content_attached_to_identity(self):
        first, second = self.dialog.sequence.elements
        self.select(first.id)
        self.dialog.image_heading.setText('First image title')
        self.dialog.image_caption.setPlainText('First image caption')
        self.dialog.canvas_blocks[first.id].description_editor.setPlainText(
            'First description.\n\nA second paragraph.')
        heading = self.dialog.add_heading(after_id=second.id)
        self.dialog.heading_editor.setText('Chapter two')
        passage = self.dialog.add_text(after_id=heading.id)
        self.dialog.text_editor.setPlainText('A paragraph.\n\nAnother paragraph.')
        self.select(passage.id)

        # Exercise the same model-row move notification used by internal drag/drop.
        moved = self.dialog.story_list.takeItem(
            self.dialog.story_list.row(self.dialog.sequence_view.item_for_id(heading.id)))
        self.dialog.story_list.insertItem(1, moved)
        self.dialog.sequence_view.sync_order()

        self.assertEqual(self.dialog.active_element_id, passage.id)
        self.assertEqual(self.dialog.sequence.elements,
                         [first, heading, second, passage])
        self.assertEqual(self.dialog.sequence.get(first.id).caption, 'First image caption')
        self.assertEqual(self.dialog.sequence.get(first.id).description,
                         'First description.\n\nA second paragraph.')
        self.assertEqual(self.dialog.sequence.get(heading.id).heading, 'Chapter two')
        self.assertEqual(self.dialog.sequence.get(passage.id).text,
                         'A paragraph.\n\nAnother paragraph.')

    def test_empty_and_unavailable_states_and_source_files_remain_unchanged(self):
        hashes = {path: hashlib.sha256(Path(path).read_bytes()).digest()
                  for path in self.paths}
        empty = PhotoStoryDialog()
        self.assertEqual(empty.status.text(), 'Add images or story elements to begin.')
        self.assertEqual(empty.canvas_element_order(), [])
        empty.close()

        broken = str(self.root / 'missing.png')
        element = self.dialog.add_paths([broken])
        self.assertEqual(len(element), 1)
        self.select(self.dialog.sequence.elements[-1].id)
        wait_until(lambda: broken in self.dialog.sequence_view.unavailable)
        self.assertEqual(self.dialog.canvas_blocks[element[0]].image_preview.text(),
                         'Image preview unavailable')
        self.assertEqual({path: hashlib.sha256(Path(path).read_bytes()).digest()
                          for path in self.paths}, hashes)

    def test_mixed_navigation_boundaries_and_removal_of_each_type(self):
        image = self.dialog.sequence.elements[0]
        self.dialog.remove_element(self.dialog.sequence.elements[1].id)
        heading = self.dialog.add_heading()
        self.dialog.heading_editor.setText('Chapter')
        passage = self.dialog.add_text()
        self.dialog.text_editor.setPlainText('Passage')
        self.select(heading.id)
        self.assertEqual(self.dialog.active_element_id, heading.id)
        self.select(image.id)
        self.assertEqual(self.dialog.active_element_id, image.id)
        self.select(passage.id)
        self.assertEqual(self.dialog.active_element_id, passage.id)

        self.dialog.remove_element(heading.id)
        self.assertNotIn(heading.id, [item.id for item in self.dialog.sequence.elements])
        self.dialog.remove_element(passage.id)
        self.assertNotIn(passage.id, [item.id for item in self.dialog.sequence.elements])
        self.dialog.remove_element(image.id)
        self.assertIsNone(self.dialog.story_list.currentItem())
        self.assertEqual(self.dialog.status.text(), 'Add images or story elements to begin.')

    def test_image_content_stays_with_each_image_across_selection_and_story_edits(self):
        first, second = self.dialog.sequence.elements
        self.select(first.id)
        self.dialog.image_heading.setText('Harbor')
        self.dialog.image_caption.setPlainText('First caption.\nStill first.')
        self.select(second.id)
        self.dialog.image_heading.setText('Coast')
        self.dialog.image_caption.setPlainText('A different caption.')

        heading = self.dialog.add_heading()
        self.dialog.heading_editor.setText('A new chapter')
        self.dialog.add_text()
        self.dialog.text_editor.setPlainText('Unrelated words.')
        self.select(first.id)
        self.assertEqual(self.dialog.image_heading.text(), 'Harbor')
        self.assertEqual(self.dialog.image_caption.toPlainText(), 'First caption.\nStill first.')
        self.select(second.id)
        self.assertEqual(self.dialog.image_heading.text(), 'Coast')
        self.assertEqual(self.dialog.image_caption.toPlainText(), 'A different caption.')
        self.assertEqual(self.dialog.sequence.get(heading.id).heading, 'A new chapter')

    def test_empty_element_placeholders_and_long_sequence_scroll(self):
        heading = self.dialog.add_heading()
        self.assertEqual(self.dialog.story_list.currentItem().text(), 'Untitled heading')
        self.assertEqual(self.dialog.heading_editor.placeholderText(), 'Untitled section heading')
        passage = self.dialog.add_text()
        self.assertEqual(self.dialog.story_list.currentItem().text(), 'Empty text passage')
        self.assertEqual(self.dialog.text_editor.placeholderText(), 'Write a narrative passage…')
        for index in range(45):
            self.dialog.add_text()
            self.dialog.text_editor.setPlainText(f'Passage {index}')
        QApplication.processEvents()
        self.assertGreater(self.dialog.story_list.verticalScrollBar().maximum(), 0)
        self.assertEqual(self.dialog.sequence.get(heading.id).heading, '')
        self.assertEqual(self.dialog.sequence.get(passage.id).text, '')

    def test_closing_during_thumbnail_work_stops_the_worker(self):
        view = self.dialog.sequence_view
        view.thumbnails.clear()
        view.unavailable.clear()
        view.thumbnail_timer.stop()
        view.load_thumbnails()
        worker = view.thumbnail_worker
        self.assertIsNotNone(worker)
        self.dialog.close()
        self.assertTrue(view.stopped)
        wait_until(lambda: view.thumbnail_worker is None)
        self.assertFalse(self.dialog.isVisible())

    def test_continuous_canvas_edits_descriptions_and_outline_navigation(self):
        first, second = self.dialog.sequence.elements
        self.assertEqual(self.dialog.canvas_scroll.verticalScrollBar().value(), 0)
        self.assertEqual(self.dialog.canvas_element_order(), [first.id, second.id])
        self.assertIsInstance(self.dialog.canvas_blocks[first.id].description_editor,
                              QPlainTextEdit)
        first.description = "An existing multi-paragraph description.\n\nIt remains distinct."
        first.caption = "An existing short caption."
        self.dialog.refresh_canvas_element(first.id)
        block = self.dialog.canvas_blocks[first.id]
        self.assertEqual(block.caption_toggle.text(), "Edit caption")
        self.assertEqual(block.caption_toggle.toolTip(), "An existing short caption.")
        block.description_editor.setPlainText("New prose.\n\nA second paragraph.")
        self.assertEqual(self.dialog.sequence.get(first.id).description,
                         "New prose.\n\nA second paragraph.")
        self.assertEqual(self.dialog.sequence.get(first.id).caption,
                         "An existing short caption.")
        minimum_height = block.description_editor.minimumHeight()
        block.description_editor.setPlainText("A long line of story text. " * 100)
        QApplication.processEvents()
        self.assertGreater(block.description_editor.height(), minimum_height)
        self.assertEqual(self.dialog.sequence.get(first.id).description,
                         "A long line of story text. " * 100)
        block.description_editor.setPlainText("New prose.\n\nA second paragraph.")

        self.dialog.add_heading(after_id=first.id)
        chapter = self.dialog.sequence.elements[1]
        self.dialog.add_text(after_id=chapter.id)
        passage = self.dialog.sequence.elements[2]
        self.assertEqual(self.dialog.canvas_element_order(),
                         [first.id, chapter.id, passage.id, second.id])
        self.dialog.show()
        QApplication.processEvents()
        self.dialog.story_list.setCurrentRow(3)
        wait_until(lambda: self.dialog.canvas_scroll.verticalScrollBar().value() > 0)
        self.assertEqual(self.dialog.active_element_id, second.id)

        self.dialog.canvas_scroll.verticalScrollBar().setValue(0)
        wait_until(lambda: self.dialog.active_element_id == first.id)
        focus = QApplication.focusWidget()
        bar = self.dialog.canvas_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())
        wait_until(lambda: self.dialog.active_element_id != first.id)
        self.assertIs(QApplication.focusWidget(), focus)
        self.assertIn(self.dialog.active_element_id, {chapter.id, passage.id, second.id})
        self.assertEqual(self.dialog.canvas_blocks[first.id].description_editor.toPlainText(),
                         "New prose.\n\nA second paragraph.")

    def test_continuous_canvas_keeps_seventy_one_elements_scrollable(self):
        paths = []
        for index in range(71):
            path = self.root / f"canvas-{index:03}.png"
            image = QImage(40, 30, QImage.Format_RGB32)
            image.fill(0xff335577 + index)
            self.assertTrue(image.save(str(path)))
            paths.append(str(path))
        large = PhotoStoryDialog(paths)
        large.show()
        QApplication.processEvents()
        self.assertEqual(len(large.canvas_blocks), 71)
        self.assertGreater(large.canvas_scroll.verticalScrollBar().maximum(), 0)
        self.assertLessEqual(len(large.sequence_view.thumbnails), 64)
        large.close()
        wait_until(lambda: large.sequence_view.thumbnail_worker is None)

    def test_publication_settings_are_independent_and_default_private(self):
        first = self.dialog.sequence.elements[0]
        first.caption = "Keep this caption"
        first.description = "Long description"
        self.assertFalse(self.dialog.show_captions.isChecked())
        self.assertFalse(self.dialog.show_filenames.isChecked())
        self.assertEqual(self.dialog.layout_selector.currentData(), "adaptive")
        self.dialog.show_captions.setChecked(True)
        self.dialog.layout_selector.setCurrentIndex(
            self.dialog.layout_selector.findData("one-per-section"))
        document = self.dialog._publication_document()
        self.assertTrue(document.show_captions)
        self.assertTrue(document.hide_filenames)
        self.assertEqual(document.layout, "one-per-section")
        self.assertEqual(document.elements[0].description, "Long description")
        self.assertEqual(document.elements[0].caption, "Keep this caption")

    def test_caption_controls_collapse_without_losing_text_and_visibility_is_independent(self):
        first = self.dialog.sequence.elements[0]
        block = self.dialog.canvas_blocks[first.id]
        self.assertEqual(block.caption_toggle.text(), "Add caption")
        self.assertFalse(block.caption_container.isVisible())
        block.caption_toggle.click()
        self.assertTrue(block.caption_container.isVisible())
        block.caption_editor.setPlainText("A line worth keeping.")
        block.caption_toggle.click()
        self.assertFalse(block.caption_container.isVisible())
        self.assertEqual(first.caption, "A line worth keeping.")
        self.assertEqual(block.caption_toggle.text(), "Edit caption")
        self.assertFalse(self.dialog.show_captions.isChecked())
        block.caption_toggle.click()
        self.assertEqual(block.caption_editor.toPlainText(), "A line worth keeping.")
        self.dialog.show_captions.setChecked(True)
        self.dialog.show_captions.setChecked(False)
        self.assertEqual(first.caption, "A line worth keeping.")

    def test_gallery_type_style_layout_and_output_options_are_independent(self):
        first = self.dialog.sequence.elements[0]
        block = self.dialog.canvas_blocks[first.id]
        block.image_heading.setText("Harbor at dusk")
        block.description_editor.setPlainText("A lasting memory.\n\nOne more paragraph.")
        block.caption_toggle.click()
        block.caption_editor.setPlainText("The evening crossing.")
        self.assertEqual(self.dialog.gallery_type_selector.currentData(), "photo-essay")
        self.assertEqual(self.dialog.visual_style_selector.currentData(), "modern")
        self.assertEqual(self.dialog.layout_selector.currentData(), "adaptive")
        self.assertEqual(self.dialog.layout_reset_button.isVisible(), False)
        self.assertEqual(self.dialog.output_format_selector.currentData(), "folder")
        self.assertIn("index.html", self.dialog.output_format_explanation.text())
        self.assertEqual(self.dialog.preview_button.text(), "Preview in browser")

        self.dialog.gallery_type_selector.setCurrentIndex(
            self.dialog.gallery_type_selector.findData("travelogue"))
        self.assertEqual(self.dialog.layout_selector.currentData(), "one-per-section")
        self.assertFalse(self.dialog.layout_reset_button.isVisible())
        self.dialog.visual_style_selector.setCurrentIndex(
            self.dialog.visual_style_selector.findData("dramatic"))
        self.assertEqual(self.dialog.layout_selector.currentData(), "one-per-section")
        self.dialog.layout_selector.setCurrentIndex(
            self.dialog.layout_selector.findData("two-per-section"))
        self.dialog.gallery_type_selector.setCurrentIndex(
            self.dialog.gallery_type_selector.findData("illustrated-story"))
        self.assertEqual(self.dialog.layout_selector.currentData(), "two-per-section")
        self.dialog.layout_reset_button.click()
        self.assertEqual(self.dialog.layout_selector.currentData(), "one-per-section")
        self.dialog.output_format_selector.setCurrentIndex(
            self.dialog.output_format_selector.findData("zip"))
        self.assertIn("extract", self.dialog.output_format_explanation.text().lower())
        document = self.dialog._publication_document()
        self.assertEqual(document.publication_type, "illustrated-story")
        self.assertEqual(document.style, "dramatic")
        self.assertEqual(document.layout, "one-per-section")
        self.assertEqual(document.output_format, "zip")
        self.assertTrue(self.dialog.destination_label.text().endswith(".zip"))
        self.assertEqual(first.heading, "Harbor at dusk")
        self.assertEqual(first.description, "A lasting memory.\n\nOne more paragraph.")
        self.assertEqual(first.caption, "The evening crossing.")

    def test_gallery_settings_explanation_without_thumbnail(self):
        first = self.dialog.sequence.elements[0]
        original_source = first.source

        self.assertTrue(self.dialog.style_preview_image.isHidden())

        note = self.dialog.style_preview_note.text()
        self.assertIn("Photography leads", note)
        self.assertIn("single images and pairs", note)

        previous_title = self.dialog.style_preview_title.text()

        self.dialog.gallery_type_selector.setCurrentIndex(
            self.dialog.gallery_type_selector.findData("travelogue"))
        self.dialog.visual_style_selector.setCurrentIndex(
            self.dialog.visual_style_selector.findData("classic"))

        title = self.dialog.style_preview_title.text()
        note = self.dialog.style_preview_note.text()

        self.assertNotEqual(previous_title, title)
        self.assertIn("Travelogue", title)
        self.assertIn("Classic", title)
        self.assertIn("One image at a time", note)
        self.assertIn("Single-image sections", note)

        self.assertTrue(self.dialog.style_preview_image.isHidden())
        self.assertEqual(first.source, original_source)
        self.assertEqual(first.id, self.dialog.sequence.elements[0].id)


class FullStoryPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kimng-full-story-')
        self.root = Path(self.temp.name)
        self.paths = []
        for name, width, height, color in (
            ('landscape.png', 360, 200, 0xff315f7e),
            ('portrait.png', 180, 320, 0xffd59c4a),
        ):
            path = self.root / name
            image = QImage(width, height, QImage.Format_RGB32)
            image.fill(color)
            self.assertTrue(image.save(str(path)))
            self.paths.append(str(path))
        self.editor = PhotoStoryDialog(self.paths)

    def tearDown(self):
        self.editor.close()
        wait_until(lambda: self.editor.sequence_view.thumbnail_worker is None)
        self.temp.cleanup()

    def test_preview_website_uses_browser_and_preserves_the_editor_snapshot(self):
        first, second = self.editor.sequence.elements
        self.editor.story_title.setText('<The blue coast>')
        self.editor.introduction.setPlainText('A beginning.\n\nA second paragraph.')
        self.editor.image_heading.setText('Harbor')
        self.editor.canvas_blocks[first.id].description_editor.setPlainText(
            'A first description.\n\nA second paragraph.')
        self.editor.image_caption.setPlainText('Boats return at dusk.')
        heading = self.editor.add_heading()
        self.editor.heading_editor.setText('The long way around')
        passage = self.editor.add_text()
        self.editor.text_editor.setPlainText('<script>no code</script>\n\nKeep walking.')
        self.editor.add_paths([])
        original = [(item.id, item.kind, item.source, item.heading, item.caption, item.text,
                     item.description)
                    for item in self.editor.sequence.elements]
        selected = self.editor.active_element_id

        index = self.root / 'index.html'
        index.write_text('<!doctype html><title>Prepared site</title>', encoding='utf-8')
        prepared = type('Prepared', (), {'workspace': str(self.root)})()
        with patch('kim_story_publish.prepare_for_browser', return_value=prepared), \
                patch('kim_photo_story_dialog.QDesktopServices.openUrl', return_value=True) as open_url:
            self.editor.full_preview_button.click()
        self.assertEqual(open_url.call_count, 1)
        self.assertEqual(open_url.call_args.args[0].toLocalFile(), str(index))

        self.assertEqual(self.editor.active_element_id, selected)
        self.assertEqual([(item.id, item.kind, item.source, item.heading, item.caption, item.text,
                           item.description)
                          for item in self.editor.sequence.elements], original)

    def test_review_changes_prepares_exact_html_plan_and_enables_apply_for_free_destination(self):
        from kim_story_publish import StoryReviewDialog
        document = self.editor._publication_document()
        destination = str(self.root / "approved-site")
        review = StoryReviewDialog(document, destination, self.editor)
        review.show()
        wait_until(lambda: review.prepared is not None or "failed" in review.status.text().lower())
        self.assertIsNotNone(review.prepared)
        self.assertTrue(review.apply_button.isEnabled())
        self.assertIn("Gallery type: Photo essay", review.details.text())
        self.assertIn("Visual style: Modern", review.details.text())
        self.assertEqual(review.table.rowCount(), len(document.elements))
        self.assertEqual(review.destination, destination)
        self.assertEqual(review.back_button.text(), "Back")
        self.assertEqual(review.cancel_button.text(), "Cancel")
        self.assertEqual(review.apply_button.text(), "Apply")
        with patch('kim_story_publish.QDesktopServices.openUrl', return_value=True) as open_url:
            review.open_preview.click()
        self.assertEqual(open_url.call_count, 1)
        self.assertEqual(open_url.call_args.args[0].toLocalFile(),
                         str(Path(review.prepared.workspace) / 'index.html'))
        review.apply()
        wait_until(lambda: bool(review.publication_path)
                   or review.status.text().startswith("Publication blocked:"))
        self.assertEqual(review.publication_path, destination)
        self.assertTrue((Path(destination) / 'index.html').is_file())
        self.assertTrue((Path(destination) / 'images/0001.jpg').is_file())
        self.assertEqual(Path(destination).stat().st_mode & 0o777, 0o755)
        self.assertEqual((Path(destination) / 'index.html').stat().st_mode & 0o777, 0o644)

    def test_review_lists_unavailable_images_and_keeps_apply_disabled(self):
        from kim_story_publish import StoryReviewDialog
        document = self.editor._publication_document()
        Path(self.paths[0]).unlink()
        review = StoryReviewDialog(document, str(self.root / 'blocked-site'), self.editor)
        review.show()
        wait_until(lambda: review.prepared is not None or 'failed' in review.status.text().lower())
        self.assertEqual(len(review.prepared.blocked), 1)
        self.assertFalse(review.apply_button.isEnabled())
        self.assertIn('blocked', review.table.item(0, 0).text().lower())
        self.assertIn('unavailable', review.prepared.index_html.lower())
        review.reject()

    def test_review_includes_approved_caption_filename_and_layout_choices(self):
        from kim_story_publish import StoryReviewDialog
        first = self.editor.sequence.elements[0]
        self.editor.canvas_blocks[first.id].description_editor.setPlainText(
            'A longer description.\n\nAnother paragraph.')
        self.editor.image_caption.setPlainText('A preserved caption.')
        self.editor.show_captions.setChecked(True)
        self.editor.show_filenames.setChecked(True)
        self.editor.layout_selector.setCurrentIndex(
            self.editor.layout_selector.findData('one-per-section'))
        document = self.editor._publication_document()
        review = StoryReviewDialog(document, str(self.root / 'settings-site'), self.editor)
        review.show()
        wait_until(lambda: review.prepared is not None
                   or 'failed' in review.status.text().lower())
        self.assertIn('Image arrangement: One image per story section',
                      review.details.text())
        self.assertIn('Captions: shown', review.details.text())
        self.assertIn('Filenames: shown', review.details.text())
        self.assertEqual(review.prepared.document.layout, 'one-per-section')
        self.assertTrue(review.prepared.document.show_captions)
        self.assertFalse(review.prepared.document.hide_filenames)
        self.assertIn('A preserved caption.', review.prepared.index_html)
        self.assertIn('A longer description.', review.prepared.index_html)
        review.reject()

    def test_review_and_apply_use_the_approved_zip_format_type_style_and_layout(self):
        import zipfile
        from kim_story_publish import StoryReviewDialog
        self.editor.gallery_type_selector.setCurrentIndex(
            self.editor.gallery_type_selector.findData("travelogue"))
        self.editor.story_title.setText("Harbor notes")
        self.editor.visual_style_selector.setCurrentIndex(
            self.editor.visual_style_selector.findData("classic"))
        self.editor.output_format_selector.setCurrentIndex(
            self.editor.output_format_selector.findData("zip"))
        document = self.editor._publication_document()
        destination = self.root / "harbor-notes.zip"
        review = StoryReviewDialog(document, str(destination), self.editor)
        review.show()
        wait_until(lambda: review.prepared is not None
                   or "failed" in review.status.text().lower())
        self.assertTrue(review.apply_button.isEnabled(), review.status.text())
        for expected in ("Gallery type: Travelogue", "Visual style: Classic",
                         "Image arrangement: One image per story section",
                         "Output format: ZIP archive", str(destination),
                         "harbor-notes/index.html", "harbor-notes/images/0001.jpg"):
            self.assertIn(expected, review.details.text())
        self.assertEqual(review.prepared.document.output_format, "zip")
        self.assertEqual(review.prepared.document.publication_type, "travelogue")
        self.assertEqual(review.prepared.document.style, "classic")
        review.apply()
        wait_until(lambda: bool(review.publication_path)
                   or review.status.text().startswith("Publication blocked:"))
        self.assertEqual(review.publication_path, str(destination))
        with zipfile.ZipFile(destination) as archive:
            self.assertIn("harbor-notes/index.html", archive.namelist())
            self.assertIn("harbor-notes/style.css", archive.namelist())
            self.assertTrue(any(name.startswith("harbor-notes/images/")
                                for name in archive.namelist()))

    def test_composition_groups_adjacent_compatible_images_without_crossing_story_elements(self):
        sequence = StorySequence()
        images = [sequence.add_image(f'/images/photo-{index}.jpg') for index in range(7)]
        chapter = sequence.add_heading('The old city', after_id=images[3].id)
        passage = sequence.add_text('A pause between walks.', after_id=chapter.id)
        aspects = {
            images[0].source: 1.8, images[1].source: 1.7,
            images[2].source: 1.75, images[3].source: 1.6,
            images[4].source: 1.8, images[5].source: 1.75,
            images[6].source: 1.6,
        }

        plan = build_composition_plan(sequence.elements, aspects)

        self.assertEqual(
            [(block.kind, block.element_ids) for block in plan],
            [('cover', (images[0].id,)),
             ('image', (images[1].id,)),
             ('pair', (images[2].id, images[3].id)),
             ('heading', (chapter.id,)), ('text', (passage.id,)),
             ('image', (images[4].id,)),
             ('pair', (images[5].id, images[6].id))],
        )
        flattened = [element_id for block in plan for element_id in block.element_ids]
        self.assertEqual(flattened, [element.id for element in sequence.elements])
        self.assertEqual(len(flattened), len(set(flattened)))

    def test_composition_does_not_pair_unknown_or_incompatible_aspects(self):
        sequence = StorySequence([f'/images/photo-{index}.jpg' for index in range(4)])
        plan = build_composition_plan(
            sequence.elements,
            {sequence.elements[0].source: 1.8,
             sequence.elements[1].source: 1.7,
             sequence.elements[2].source: 1.8,
             sequence.elements[3].source: 0.56},
        )

        self.assertEqual([block.kind for block in plan], ['cover', 'image', 'image', 'image'])
        self.assertEqual(plan[2].element_ids, (sequence.elements[2].id,))

    def test_cinematic_title_is_integrated_over_the_unique_full_width_cover(self):
        element = self.editor.sequence.elements[0]
        window = StoryPreviewWindow(
            self.editor, title='A dramatic opening', introduction='First light over the harbor.',
            elements=[element], theme_key='cinematic', hide_filenames=True,
            source_stamps=self.editor.sequence_view.source_stamps,
            source_aspects={element.source: 1.8})
        window.resize(1280, 900)
        window.show()
        wait_until(lambda: window.image_views[element.id].has_image)
        hero = window.opening_header.parentWidget()
        photo = window.image_views[element.id]

        self.assertEqual(hero.objectName(), 'storyCinematicHero')
        self.assertEqual(window.rendered_element_ids, (element.id,))
        self.assertEqual(len(window.image_views), 1)
        self.assertLess(window.title_label.geometry().bottom(), window.opening_header.height())
        self.assertGreater(hero.width(), 1100)
        title_y = window.title_label.mapTo(hero, QPoint(0, 0)).y()
        self.assertGreater(title_y, 0)
        self.assertLess(title_y, photo.height())
        window.reject()
        wait_until(lambda: window.thumbnail_worker is None)

    def test_travel_journal_places_masthead_before_an_unframed_expansive_photo(self):
        element = self.editor.sequence.elements[0]
        window = StoryPreviewWindow(
            self.editor, title='A warm opening', introduction='A long walk by the sea.',
            elements=[element], theme_key='journal', hide_filenames=True,
            source_stamps=self.editor.sequence_view.source_stamps,
            source_aspects={element.source: 1.8})
        window.resize(1280, 900)
        window.show()
        wait_until(lambda: window.image_views[element.id].has_image)
        title_y = window.title_label.mapTo(window.page, QPoint(0, 0)).y()
        photo_y = window.image_views[element.id].mapTo(window.page, QPoint(0, 0)).y()

        self.assertLess(title_y, photo_y)
        self.assertEqual(window.image_views[element.id].treatment, 'journal-open')
        self.assertGreaterEqual(window.image_views[element.id].width(), 1000)
        window.reject()
        wait_until(lambda: window.thumbnail_worker is None)

    def test_two_up_spread_preserves_caption_identity_and_reflows_narrowly(self):
        paths = list(self.paths)
        for index in range(2):
            path = self.root / f'wide-{index}.png'
            image = QImage(360, 200, QImage.Format_RGB32)
            image.fill(0xff315f7e + index)
            self.assertTrue(image.save(str(path)))
            paths.append(str(path))
        sequence = StorySequence(paths)
        for index, element in enumerate(sequence.elements):
            element.caption = f'Caption {index + 1}'
        aspects = {path: 1.8 for path in paths}
        stamps = {path: identity(path) for path in paths}
        window = StoryPreviewWindow(
            self.editor, title='A visual sequence', introduction='Images in order.',
            elements=sequence.elements, theme_key='journal', hide_filenames=True,
            source_stamps=stamps, source_aspects=aspects)
        image_ids = [element.id for element in sequence.elements]

        self.assertEqual(window.rendered_element_ids, tuple(image_ids))
        self.assertEqual(len(window.image_views), 4)
        self.assertIs(window.pair_containers[image_ids[2]], window.pair_containers[image_ids[3]])
        for index, element_id in enumerate(image_ids):
            self.assertEqual(window.caption_labels[element_id].text(), f'Caption {index + 1}')

        window.resize(640, 560)
        window.show()
        QApplication.processEvents()
        self.assertEqual(window.scroll.horizontalScrollBar().maximum(), 0)
        window.reject()
        wait_until(lambda: window.thumbnail_worker is None)

    def test_blank_elements_are_not_rendered_as_authored_placeholders(self):
        sequence = StorySequence()
        blank_heading = sequence.add_heading()
        blank_passage = sequence.add_text()
        source_stamps = {}
        window = StoryPreviewWindow(
            self.editor, title='', introduction='', elements=sequence.elements,
            theme_key='editorial', hide_filenames=True, source_stamps=source_stamps)
        self.assertEqual(window.element_order, (blank_heading.id, blank_passage.id))
        self.assertEqual(window.rendered_element_ids, ())
        self.assertEqual(window.title_label.text(), 'Untitled story')
        self.assertFalse(window.introduction_label.isVisible())
        self.assertIn('Nothing to preview yet', window.empty_state.text())
        window.close()

    def test_filename_visibility_hides_only_automatic_photo_headings(self):
        first, second = self.editor.sequence.elements
        first.heading = 'A user-authored title'
        visible = StoryPreviewWindow(
            self.editor, title='', introduction='', elements=[first, second],
            theme_key='editorial', hide_filenames=False,
            source_stamps=self.editor.sequence_view.source_stamps)
        hidden = StoryPreviewWindow(
            self.editor, title='', introduction='', elements=[first, second],
            theme_key='editorial', hide_filenames=True,
            source_stamps=self.editor.sequence_view.source_stamps)
        self.assertEqual(visible.heading_labels[first.id].text(), 'A user-authored title')
        self.assertEqual(hidden.heading_labels[first.id].text(), 'A user-authored title')
        self.assertEqual(visible.heading_labels[second.id].text(), 'portrait')
        self.assertEqual(visible.heading_labels[second.id].objectName(),
                         'storyPhotographAutoHeading')
        self.assertNotIn(second.id, hidden.heading_labels)
        visible.close()
        hidden.close()

    def test_each_theme_changes_the_editorial_system_not_only_the_color(self):
        theme_keys = [self.editor.theme_selector.itemData(i)
                      for i in range(self.editor.theme_selector.count())]
        summaries = set()
        for key in theme_keys:
            window = StoryPreviewWindow(
                self.editor, title='A story', introduction='An opening.', elements=[],
                theme_key=key, hide_filenames=False, source_stamps={})
            spec = window.presentation
            summaries.add((spec['page_width'], spec['title_size'], spec['image_height'],
                           spec['display_font'], spec['photo_treatment'], spec['section_treatment']))
            self.assertEqual(window.theme_key, key)
            self.assertEqual(window.element_order, ())
            window.close()
        self.assertEqual(len(theme_keys), 10)
        self.assertGreaterEqual(len(summaries), 8)

    def test_image_aspect_ratios_are_preserved_and_window_reflows_narrowly(self):
        sequence = StorySequence(self.paths)
        window = StoryPreviewWindow(
            self.editor, title='A story', introduction='', elements=sequence.elements,
            theme_key='journal', hide_filenames=False,
            source_stamps=self.editor.sequence_view.source_stamps)
        window.resize(900, 700)
        window.show()
        wait_until(lambda: all(window.image_views[item.id].has_image
                               for item in sequence.elements))
        landscape = window.image_views[sequence.elements[0].id].displayed_rect
        portrait = window.image_views[sequence.elements[1].id].displayed_rect
        self.assertAlmostEqual(landscape.width() / landscape.height(), 360 / 200, delta=0.02)
        self.assertAlmostEqual(portrait.width() / portrait.height(), 180 / 320, delta=0.02)

        window.resize(640, 560)
        QApplication.processEvents()
        self.assertLessEqual(window.page.width(), window.stage.width())
        self.assertEqual(window.scroll.horizontalScrollBar().maximum(), 0)
        window.reject()
        wait_until(lambda: window.thumbnail_worker is None)

    def test_source_hash_and_all_timestamps_are_unchanged(self):
        first = self.editor.sequence.elements[0]
        self.editor.sequence_view.request_preview(first.source)
        wait_until(lambda: first.source in self.editor.sequence_view.thumbnails)
        before = {path: (safe_digest(path), os.stat(path).st_atime_ns,
                         os.stat(path).st_mtime_ns, os.stat(path).st_ctime_ns)
                  for path in self.paths}
        window = StoryPreviewWindow(
            self.editor, title='A story', introduction='', elements=self.editor.sequence.elements,
            theme_key='essay', hide_filenames=True,
            source_stamps=self.editor.sequence_view.source_stamps)
        window.show()
        wait_until(lambda: window.image_views[first.id].has_image)
        window.reject()
        wait_until(lambda: window.thumbnail_worker is None)
        after = {path: (safe_digest(path), os.stat(path).st_atime_ns,
                        os.stat(path).st_mtime_ns, os.stat(path).st_ctime_ns)
                 for path in self.paths}
        self.assertEqual(after, before)

    def test_changed_source_is_rejected_by_the_preview_identity_check(self):
        path = self.paths[0]
        original_stamp = identity(path)
        changed = QImage(120, 80, QImage.Format_RGB32)
        changed.fill(0xffcc3344)
        self.assertTrue(changed.save(path))
        element = StorySequence([path]).elements
        window = StoryPreviewWindow(
            self.editor, title='A story', introduction='', elements=element,
            theme_key='cinematic', hide_filenames=False,
            source_stamps={path: original_stamp})
        window.show()
        view = window.image_views[element[0].id]
        wait_until(lambda: view.status == 'unavailable')
        self.assertFalse(view.has_image)
        window.reject()
        wait_until(lambda: window.thumbnail_worker is None)

    def test_seventy_one_images_load_incrementally_with_bounded_cache(self):
        paths = []
        for index in range(71):
            path = self.root / f'frame-{index:03}.png'
            image = QImage(32, 24, QImage.Format_RGB32)
            image.fill(0xff000000 | index)
            self.assertTrue(image.save(str(path)))
            paths.append(str(path))
        sequence = StorySequence(paths)
        stamps = {path: identity(path) for path in paths}
        window = StoryPreviewWindow(
            self.editor, title='Seventy one moments', introduction='',
            elements=sequence.elements, theme_key='cinematic',
            hide_filenames=True, source_stamps=stamps,
            source_aspects={path: 1.5 for path in paths})
        self.assertEqual(len(window.image_views), 71)
        self.assertEqual(window.rendered_element_ids,
                         tuple(element.id for element in sequence.elements))
        self.assertGreater(len(window.pair_containers), 0)
        window.show()
        wait_until(lambda: bool(window.image_cache))
        self.assertLessEqual(len(window.image_cache), window.cache_limit)
        self.assertLessEqual(len(window.thumbnail_paths), window.batch_limit)
        window.reject()
        wait_until(lambda: window.thumbnail_worker is None)

    def test_missing_image_is_reported_and_repeated_windows_close_cleanly(self):
        missing = str(self.root / 'gone.png')
        sequence = StorySequence([missing])
        for _ in range(3):
            window = StoryPreviewWindow(
                self.editor, title='A story', introduction='', elements=sequence.elements,
                theme_key='golden', hide_filenames=True, source_stamps={missing: None})
            window.show()
            wait_until(lambda: window.image_views[sequence.elements[0].id].status == 'unavailable')
            window.reject()
            wait_until(lambda: window.thumbnail_worker is None)


if __name__ == '__main__':
    unittest.main()
