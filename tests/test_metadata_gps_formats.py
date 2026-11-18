"""GPS proposals share the standalone engine's verified format eligibility."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import test_metadata_editor_gps as fixtures
import test_metadata_gps_field_actions as routes
import kim_location as gps
from kim_metadata_editor import Draft, ReviewDialog


class GPSFormatTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.GPSProposalTests.setUpClass.__func__)
    setUp = fixtures.GPSProposalTests.setUp
    editor = fixtures.GPSProposalTests.editor
    wait_for = fixtures.GPSProposalTests.wait_for

    def make_image(self, extension, *options):
        path = self.folder / ('image.' + extension)
        result = subprocess.run(['magick', '-size', '16x12', 'xc:blue', *options, str(path)], capture_output=True)
        if result.returncode or not path.exists():
            self.skipTest(extension + ' encoder unavailable: ' + result.stderr.decode(errors='replace')[-300:])
        decoded = subprocess.run(['magick', str(path), 'null:'], capture_output=True)
        if decoded.returncode:
            self.skipTest(extension + ' decoder unavailable: ' + decoded.stderr.decode(errors='replace')[-300:])
        return path

    def check_format(self, extension):
        self.image = self.make_image(extension)
        before = [fixtures.signature(p) for p in (self.image, self.sidecar)]
        members = set(self.folder.iterdir())
        with patch('kim_location.build_plan', side_effect=AssertionError('publication planner')), \
             patch('kim_location.allocate', side_effect=AssertionError('allocate output')), \
             patch('kim_location.assignments', side_effect=AssertionError('writer arguments')):
            snapshot = gps.inspect_editor_gps(str(self.image))
            self.assertEqual([], snapshot['blocked'])
            self.assertEqual({}, snapshot['initial'])  # Sidecar GPS never seeds camera GPS.
            proposal = gps.build_manual_proposal(str(self.image), self.config)
            self.assertEqual('valid', proposal['status'], proposal['blocked'])
            self.assertEqual([-40.25, 71.5], proposal['proposed']['position'])
            self.assertIsNone(proposal['existing']['position'])
            self.assertEqual([10, 20], proposal['sidecars'][0]['existing']['position'])
            self.assertFalse({'target', 'args', 'destination', 'publication'} & proposal.keys())
            editor = self.editor()
            path = str(self.image)
            self.assertTrue(editor.add_gps_button.isEnabled())
            editor.gps_drafts[path] = proposal
            plan = editor._combined_plan()
            self.assertTrue(plan)
            self.assertTrue(all(row.get('gps') for row in plan))
            self.assertEqual('valid', plan[0]['status'])
            self.assertFalse(any('JPEG' in row.get('warning', '') for row in plan))
            review = ReviewDialog(plan, editor)
            review.show(); self.app.processEvents()
            self.assertTrue(review.apply_button.isVisible())
            self.assertFalse(review.apply_button.isEnabled())
            self.assertEqual('Preview only. No output will be created.', review.result_label.text())
            self.assertIn('No camera GPS', review.before_view.toPlainText())
            self.assertIn('40.250000', review.after_view.toPlainText())
            review.technical_button.setChecked(True)
            self.assertIn('GPS fix details', review.technical.toPlainText())
            self.assertIn('timestamps', review.warning_label.text())
            review.reject()
            if extension != 'jpg':
                draft = Draft('Replace', 'Retain blocked description')
                editor.drafts[path] = {'title': draft}
                mixed = editor._combined_plan()
                self.assertTrue(any(row['field'] == 'Image eligibility' and row['status'] == 'blocked' for row in mixed))
                self.assertTrue(any(row.get('gps') and row['status'] == 'valid' for row in mixed))
                self.assertIs(draft, editor.drafts[path]['title'])
            self.assertIs(proposal, editor.gps_drafts[path])
        self.assertEqual(before, [fixtures.signature(p) for p in (self.image, self.sidecar)])
        self.assertEqual(members, set(self.folder.iterdir()))
        self.sidecar.write_text(self.sidecar.read_text() + ' ')
        self.assertIn('changed', gps.proposal_problem(proposal))

    def test_jpeg(self): self.check_format('jpg')
    def test_png(self): self.check_format('png')
    def test_avif(self): self.check_format('avif')
    def test_webp(self): self.check_format('webp')
    def test_tiff(self): self.check_format('tiff')
    def test_heic(self): self.check_format('heic')
    def test_heif(self): self.check_format('heif')

    def assert_blocked(self, path, message):
        before = fixtures.signature(path)
        snapshot = gps.inspect_editor_gps(str(path))
        proposal = gps.build_manual_proposal(str(path), self.config)
        self.assertTrue(snapshot['blocked'])
        self.assertEqual('blocked', proposal['status'])
        self.assertIn(message, ' '.join(snapshot['blocked']))
        self.assertIn(message, ' '.join(proposal['blocked']))
        raw = gps.read_many([str(path)])[str(path)]['raw']
        with self.assertRaises(ValueError) as blocked:
            gps.safe_format(str(path), raw)
        self.assertEqual([str(blocked.exception)], snapshot['blocked'])
        self.assertEqual([str(blocked.exception)], proposal['blocked'])
        self.assertEqual(before, fixtures.signature(path))

    def test_unsupported_mismatched_and_invalid_inputs(self):
        self.assert_blocked(self.make_image('gif'), 'matching extension')
        png = self.make_image('png')
        for extension in ('jpg', 'avif', 'raw', ''):
            with self.subTest(extension=extension):
                path = self.folder / ('mismatch.' + extension)
                path.write_bytes(png.read_bytes())
                self.assert_blocked(path, 'matching extension')
        broken = self.folder / 'broken.png'; broken.write_bytes(b'not an image')
        self.assert_blocked(broken, 'matching extension')

    def test_progressive_jpeg_retains_engine_guard(self):
        self.assert_blocked(self.make_image('jpg', '-interlace', 'Plane'), 'Progressive JPEG')

    def test_animated_webp_and_png_retain_engine_guards(self):
        import struct
        import zlib
        png = self.make_image('png')
        data = png.read_bytes()
        payload = struct.pack('>II', 2, 0)
        chunk = b'acTL' + payload
        png.write_bytes(data[:33] + struct.pack('>I', len(payload)) + chunk + struct.pack('>I', zlib.crc32(chunk)) + data[33:])
        # ExifTool identifies this as APNG, outside the engine's still allowlist.
        self.assert_blocked(png, 'matching extension')
        webp = self.folder / 'animated.webp'
        subprocess.run(['magick', '-size', '16x12', '-delay', '10', 'xc:red', 'xc:blue', '-loop', '0', str(webp)], check=True, capture_output=True)
        self.assert_blocked(webp, 'Animated')


class GPSFormatRoutingTests(unittest.TestCase):
    setUpClass = classmethod(fixtures.GPSProposalTests.setUpClass.__func__)
    setUp = fixtures.GPSProposalTests.setUp
    editor = fixtures.GPSProposalTests.editor
    wait_for = fixtures.GPSProposalTests.wait_for
    make_image = GPSFormatTests.make_image
    # Use the established actual Qt Browser action/dialog/Editor chain.
    route = routes.BrowserDirectGPSRoutingTests.route

    def test_supported_formats_direct_add_map_review_and_edit_cancel(self):
        for extension in ('jpg', 'png', 'avif', 'webp', 'tiff', 'heic', 'heif'):
            with self.subTest(extension=extension):
                self.image = self.make_image(extension)
                routes.BrowserDirectGPSRoutingTests.test_browser_add_starts_empty_then_retains_selection_in_visible_editor(self)
                subprocess.run(['exiftool', '-overwrite_original', '-GPSLatitude=48.5', '-GPSLongitude=2.25',
                                '-GPSLatitudeRef=N', '-GPSLongitudeRef=E', str(self.image)], check=True, capture_output=True)
                routes.BrowserDirectGPSRoutingTests.test_browser_edit_prefills_verified_camera_values_then_cancel_creates_no_editor(self)
                routes.BrowserDirectGPSRoutingTests.test_browser_add_immediate_cancel_never_accepts_late_inspection(self)


if __name__ == '__main__': unittest.main()
