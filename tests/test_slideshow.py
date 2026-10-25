"""Small real FFmpeg slideshow integration tests."""
import shutil
import json
import os
import subprocess
import unittest
from support import Workspace


class SlideshowTests(unittest.TestCase):
    def setUp(self):
        if not all(shutil.which(x) for x in ('ffmpeg', 'ffprobe', 'magick')):
            self.skipTest('FFmpeg, ffprobe and ImageMagick required')
        self.w = Workspace()
        self.addCleanup(self.w.close)
        self.w.env['KIM_POLICY'] = 'overwrite'
        self.w.use_real_slideshow_tools()
        self.images = [self.w.png('input/slide 2 [test].png'), self.w.png("input/slide 10 O'Neil 雪.png")]
        subprocess.run([shutil.which('magick'), '-size', '8x8', 'xc:red', str(self.images[0])], check=True)
        subprocess.run([shutil.which('magick'), '-size', '8x8', 'xc:blue', str(self.images[1])], check=True)
        self.source_bytes = [path.read_bytes() for path in self.images]

    def test_creates_h264_mp4_in_natural_name_order_even_when_policy_is_overwrite(self):
        result = self.w.dispatch('slideshow', '--seconds-per-photo', '1', '--size', '160x120',
                                 '--fps', '2', '--', *self.images)
        self.assertEqual(0, result.returncode, result.stderr)
        output = self.images[0].with_name('slide 2 [test]_slideshow.mp4')
        self.assertTrue(output.is_file())
        probe = subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-show_entries',
                                'format=format_name,duration:stream=codec_name,width,height,r_frame_rate,nb_frames,codec_type',
                                '-of', 'default=noprint_wrappers=1', str(output)],
                               check=True, capture_output=True, text=True).stdout
        self.assertIn('codec_name=h264', probe)
        self.assertIn('width=160', probe)
        self.assertIn('height=120', probe)
        self.assertIn('nb_frames=4', probe)
        self.assertNotIn('codec_type=audio', probe)
        self.assertEqual(self.source_bytes, [path.read_bytes() for path in self.images])
        colors = subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-select_streams', 'v:0',
                                 '-show_entries', 'stream=color_primaries,color_transfer,color_space',
                                 '-of', 'default=noprint_wrappers=1', str(output)],
                                check=True, capture_output=True, text=True).stdout
        self.assertIn('color_primaries=bt709', colors)
        self.assertIn('color_transfer=bt709', colors)
        self.assertIn('color_space=bt709', colors)
        decoded_samples = []
        for timestamp in ('0.2', '1.2'):
            sample = subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-ss', timestamp, '-i', str(output),
                                     '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                                    check=True, capture_output=True, timeout=10).stdout
            center = (60 * 160 + 80) * 3
            decoded_samples.append(sample[center:center + 3])
        self.assertGreater(decoded_samples[0][0], decoded_samples[0][2])
        self.assertGreater(decoded_samples[1][2], decoded_samples[1][0])
        self.assertEqual(0, subprocess.run([shutil.which('ffmpeg'), '-v', 'error', '-xerror', '-i',
                                            str(output), '-f', 'null', '-'], capture_output=True).returncode)

    def test_single_image_still_produces_one_derived_slideshow(self):
        self.w.env['KIM_POLICY'] = 'overwrite'
        before = self.images[0].read_bytes()
        result = self.w.dispatch('slideshow', '--seconds-per-photo', '1', '--size', '160x120',
                                 '--fps', '1', '--', str(self.images[0]))
        self.assertEqual(0, result.returncode, result.stderr)
        output = self.images[0].with_name('slide 2 [test]_slideshow.mp4')
        self.assertTrue(output.is_file())
        self.assertEqual(before, self.images[0].read_bytes())
        self.assertEqual(1, int(subprocess.run([shutil.which('ffprobe'), '-v', 'error', '-select_streams', 'v:0',
                                               '-count_frames', '-show_entries', 'stream=nb_read_frames',
                                               '-of', 'csv=p=0', str(output)], check=True,
                                              capture_output=True, text=True).stdout.strip().rstrip(',').split(',')[0]))

    def test_service_loss_during_frame_preparation_stops_owned_magick_and_publishes_nothing(self):
        plan = json.loads(self.w.plan.read_text())
        plan.update(slideshow_hold_magick=True, slideshow_interrupt_during_frame=True)
        self.w.plan.write_text(json.dumps(plan))
        before = [self.w.observe(path) for path in self.images]
        result = self.w.dispatch('slideshow', '--seconds-per-photo', '1', '--size', '160x120',
                                 '--fps', '1', '--', *self.images)
        self.assertNotEqual(0, result.returncode)
        marker = self.w.control / 'slideshow-magick.pid'
        self.assertTrue(marker.exists(), result.events)
        with self.assertRaises(ProcessLookupError):
            os.kill(int(marker.read_text()), 0)
        self.assertEqual(before, [self.w.observe(path) for path in self.images])
        self.assertFalse(self.images[0].with_name('slide 2 [test]_slideshow.mp4').exists())
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))
