"""Bounded end-to-end tests for the standalone contact-sheet action."""
import json
import shutil
import unittest
from support import Workspace


class ContactSheetTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.source = self.w.ppm('in/one.ppm')
        self.w.path('out').mkdir()
        tools = {name: shutil.which(name) for name in ('magick', 'identify')}
        if not all(tools.values()):
            raise unittest.SkipTest('ImageMagick tools unavailable')
        plan = json.loads(self.w.plan.read_text())
        plan['real_contactsheet_tools'] = tools
        self.w.plan.write_text(json.dumps(plan))
        self.w.env['KIM_POLICY'] = 'create'
        self.w.env['MAGICK_TEMPORARY_PATH'] = str(self.w.control / 'tmp')
        self.w.env['MAGICK_THREAD_LIMIT'] = '1'

    def test_contactsheet_prints_labeled_pdf_and_preserves_source(self):
        target = self.w.path('out/contact.pdf')
        before = self.w.observe(self.source)
        result = self.w.dispatch('contactsheet', '--dpi', '150', '--grid', '3x4',
                                 '--output', target, '--', self.source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.w.observe(self.source), before)
        self.assertTrue(target.is_file())
        self.assertTrue(target.read_bytes().startswith(b'%PDF-'))
        self.assertFalse(list(self.w.path('out').glob('.kim6-stage.*')))

    def test_invalid_options_do_not_publish(self):
        target = self.w.path('out/contact.pdf')
        result = self.w.dispatch('contactsheet', '--grid', '8x100',
                                 '--output', target, '--', self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(target.exists())
        self.assertFalse(list(self.w.path('out').glob('.kim6-stage.*')))

    def test_failed_render_does_not_replace_existing_pdf(self):
        target = self.w.path('out/contact.pdf')
        target.write_bytes(b'existing destination')
        before = self.w.observe(target)
        self.w.approve_overwrite()
        self.w.respond('magick', status=1)
        result = self.w.dispatch('contactsheet', '--dpi', '150', '--grid', '3x4',
                                 '--output', target, '--', self.source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(target), before)
        self.assertFalse(list(self.w.path('out').glob('.kim6-stage.*')))

    def test_create_mode_preserves_occupied_destination_and_uses_numbered_output(self):
        target = self.w.path('out/contact.pdf')
        target.write_bytes(b'existing unrelated PDF')
        before_target = self.w.observe(target)
        before_source = self.w.observe(self.source)

        result = self.w.dispatch('contactsheet', '--dpi', '150', '--grid', '3x4',
                                 '--output', target, '--', self.source)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.w.observe(target), before_target)
        self.assertEqual(self.w.observe(self.source), before_source)
        numbered = self.w.path('out/contact_1.pdf')
        self.assertTrue(numbered.is_file())
        self.assertTrue(numbered.read_bytes().startswith(b'%PDF-'))
        self.assertFalse(list(self.w.path('out').glob('.kim6-stage.*')))

    def test_overwrite_mode_refuses_symlink_destination(self):
        protected = self.w.path('out/protected.pdf')
        protected.write_bytes(b'protected PDF')
        target = self.w.path('out/contact.pdf')
        target.symlink_to(protected.name)
        before_target = self.w.observe(target)
        before_protected = self.w.observe(protected)
        before_source = self.w.observe(self.source)
        self.w.approve_overwrite()

        result = self.w.dispatch('contactsheet', '--dpi', '150', '--grid', '3x4',
                                 '--output', target, '--', self.source)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.w.observe(target), before_target)
        self.assertEqual(self.w.observe(protected), before_protected)
        self.assertEqual(self.w.observe(self.source), before_source)
        self.assertFalse(list(self.w.path('out').glob('.kim6-stage.*')))

    def test_failed_pdf_validation_preserves_existing_output(self):
        target = self.w.path('out/contact.pdf')
        target.write_bytes(b'existing unrelated PDF')
        before_target = self.w.observe(target)
        before_source = self.w.observe(self.source)
        self.w.approve_overwrite()
        self.w.respond_to('identify', '-regard-warnings', {'status': 70})

        result = self.w.dispatch('contactsheet', '--dpi', '150', '--grid', '3x4',
                                 '--output', target, '--', self.source)

        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(any(call['tool'] == 'magick' and
                            call['argv'][-1].startswith('PDF:') for call in result.calls))
        self.assertEqual(self.w.observe(target), before_target)
        self.assertEqual(self.w.observe(self.source), before_source)
        self.assertFalse(list(self.w.path('out').glob('.kim6-stage.*')))

    def test_gallery_assets_are_scoped_to_gallery_action(self):
        source = (self.w.production).read_text()
        gallery = source.split('action_gallery() {', 1)[1].split('\naction_print() {', 1)[0]
        album = source.split('action_album() {', 1)[1].split('\naction_compress() {', 1)[0]
        self.assertIn('local -a files=() image_assets=() thumb_assets=()', gallery)
        self.assertNotIn('image_assets=()', album)
