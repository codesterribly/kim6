"""Focused pixel/metadata/Qt boundaries for the real-world Recipe pass.

The private Photoshop fixture stays outside the tree. Synthetic documents here
exercise failure boundaries; they do not establish Photoshop rendering fidelity.
"""
import copy
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_recipes as base
import kim_recipe_core as core
import kim_psd_source as psd
from kim_recipe_image import ImageHandler


def step(op, **parameters):
    return dict(op=op, **copy.deepcopy(__import__('kim_recipe_image').DEFAULTS[op])) | parameters


@unittest.skipUnless(shutil.which('magick') and shutil.which('exiftool'), 'real image tools required')
class CorrectnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kim6-correctness-'); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.source = self.root/'No Date.png'
        self.cmd('magick','-size','40x30','gradient:red-blue','-profile',psd.srgb(),self.source)
        self.before = (self.source.read_bytes(),self.source.stat().st_mtime_ns)

    def cmd(self,*args):
        return subprocess.run(list(map(str,args)),capture_output=True,check=True,timeout=30).stdout

    def execute(self,steps,source=None):
        result = core.execute(base.recipe(steps),[source or self.source])[0]
        self.assertTrue(result['ok'],result)
        self.assertEqual((self.source.read_bytes(),self.source.stat().st_mtime_ns),self.before)
        return Path(result['output'])

    def test_set_dateless_date_subseconds_offsets_and_file_sync(self):
        for zone in ('unknown','UTC','+05:30','-04:00'):
            with self.subTest(zone=zone):
                steps = [step('metadata.set_capture',datetime='2024-02-29 00:00:00.123456789',timezone=zone,fields='all')]
                if zone != 'unknown': steps.append({'op':'file.sync_date'})
                output = self.execute(steps)
                self.assertEqual(self.cmd('exiftool','-s3','-EXIF:DateTimeOriginal',output).strip(),b'2024:02:29 00:00:00')
                self.assertEqual(self.cmd('exiftool','-s3','-EXIF:SubSecTimeOriginal',output).strip(),b'')
                offset = self.cmd('exiftool','-s3','-EXIF:OffsetTimeOriginal',output).strip()
                self.assertEqual(offset, b'' if zone == 'unknown' else b'+00:00' if zone == 'UTC' else zone.encode())
                if zone == 'unknown': self.assertFalse(self.cmd('exiftool','-s3','-IPTC:TimeCreated',output).strip())
                else: self.assertEqual(output.stat().st_mtime_ns % 1000000000,0)

    def test_invalid_ambiguous_date_zone_and_unsupported_container_preflight(self):
        for clock,zone in [('2024-02-30 12:00:00','UTC'),('2024-02-29','UTC'),('2024-02-29 12:00','UTC'),('2024-02-29 12:00:00',''),('2024-02-29 12:00:00','+14:30')]:
            with self.subTest(clock=clock,zone=zone):
                self.assertTrue(core.preview(base.recipe([step('metadata.set_capture',datetime=clock,timezone=zone)]),[self.source])[0].problems)
        steps = [step('image.convert',format='pdf'),step('metadata.set_capture',datetime='2024-02-29 12:00:00',timezone='UTC')]
        row = core.preview(base.recipe(steps),[self.source])[0]
        self.assertIn('cannot retain',row.problems[0])
        operations = [step('image.convert',format='avif'),step('image.compress'),
                      step('metadata.set_capture',datetime='2024-02-29 12:34:56',timezone='+05:30'),step('metadata.creator',value='Author')]
        output = self.execute(operations)
        self.assertEqual(self.cmd('exiftool','-s3','-EXIF:DateTimeOriginal',output).strip(),b'2024:02:29 12:34:56')
        self.assertEqual(self.cmd('exiftool','-s3','-OffsetTimeOriginal',output).strip(),b'+05:30')
        self.assertEqual(self.cmd('exiftool','-s3','-XMP-dc:Creator',output).strip(),b'Author')

    def test_ordered_strip_set_adjust_and_missing_date_remedy(self):
        date = step('metadata.set_capture',datetime='2024-02-29 12:00:00.987',timezone='unknown')
        output = self.execute([{'op':'metadata.strip_all'},date,step('metadata.shift_capture',seconds=86400)])
        self.assertEqual(self.cmd('exiftool','-s3','-EXIF:DateTimeOriginal',output).strip(),b'2024:03:01 12:00:00')
        self.assertEqual(self.cmd('exiftool','-s3','-EXIF:SubSecTimeOriginal',output).strip(),b'')
        output = self.execute([date,{'op':'metadata.strip_all'}])
        self.assertFalse(self.cmd('exiftool','-s3','-DateTimeOriginal',output).strip())
        for operations, expected in [([step('metadata.shift_capture')],'Add Set Capture Date'),([date,{'op':'metadata.strip_all'},step('metadata.shift_capture')],'Step 2 removes capture metadata before Step 3')]:
            row = core.preview(base.recipe(operations),[self.source])[0]
            self.assertIn(expected,row.problems[0])
        operations = [date,step('metadata.shift_capture',enabled=False),{'op':'metadata.strip_all'},step('metadata.shift_capture')]
        self.assertIn('Step 3 removes capture metadata before Step 4',core.preview(base.recipe(operations),[self.source])[0].problems[0])

    def test_embedded_date_and_file_mtime_are_explicit_sources(self):
        source = self.root/'dated.jpg'
        self.cmd('magick',self.source,source)
        self.cmd('exiftool','-overwrite_original','-DateTimeOriginal=2020:01:02 03:04:05','-OffsetTimeOriginal=+02:00','-SubSecTimeOriginal=001234567',source)
        output = self.execute([step('metadata.set_capture',mode='embedded',timezone='embedded'),step('metadata.shift_capture',seconds=-86400)],source)
        self.assertEqual(self.cmd('exiftool','-s3','-DateTimeOriginal',output).strip(),b'2020:01:01 03:04:05')
        self.assertEqual(self.cmd('exiftool','-s3','-SubSecTimeOriginal',output).strip(),b'001234567')
        output = self.execute([step('metadata.set_capture',mode='file_mtime',timezone='UTC')])
        self.assertTrue(self.cmd('exiftool','-s3','-DateTimeOriginal',output).strip())
        row = core.preview(base.recipe([step('metadata.set_capture',mode='file_mtime',timezone='unknown')]),[self.source])[0]
        self.assertIn('Choose UTC',row.problems[0])
        xmp_source = self.root/'xmp-only.png';self.cmd('magick',self.source,xmp_source)
        self.cmd('exiftool','-overwrite_original','-XMP-exif:DateTimeOriginal=2020:01:02 03:04:05.123456789+02:00',xmp_source)
        output = self.execute([step('metadata.set_capture',mode='embedded',timezone='embedded')],xmp_source)
        self.assertEqual(self.cmd('exiftool','-s3','-EXIF:SubSecTimeOriginal',output).strip(),b'123456789')
        self.assertEqual(self.cmd('exiftool','-s3','-EXIF:OffsetTimeOriginal',output).strip(),b'+02:00')
        self.cmd('exiftool','-overwrite_original','-XMP-exif:DateTimeOriginal=2022:01:02 03:04:05',source)
        row = core.preview(base.recipe([step('metadata.set_capture',mode='embedded',timezone='embedded')]),[source])[0]
        self.assertTrue(any('disagree' in warning for warning in row.warnings))

    def test_escaped_date_pattern_needs_no_capture_and_numbers_collisions(self):
        occupied = self.root / '{date}.png'
        occupied.write_bytes(b'occupied')
        output = self.execute([{'op': 'file.rename_output', 'pattern': '{{date}}'}])
        self.assertEqual(output.name, '{date}_1.png')
        self.assertEqual(occupied.read_bytes(), b'occupied')
        self.assertFalse(list(self.root.rglob('.kim6-stage.*')))

    def test_real_date_token_requires_capture_before_publication(self):
        for pattern in ('{date}', '{{date}}_{date}'):
            with self.subTest(pattern=pattern):
                operations = [{'op': 'file.rename_output', 'pattern': pattern}]
                row = core.preview(base.recipe(operations), [self.source])[0]
                self.assertTrue(any('needs a capture date' in p for p in row.problems), row)
                before = set(self.root.iterdir())
                result = core.execute(base.recipe(operations), [self.source])[0]
                self.assertFalse(result['ok'], result)
                self.assertIn('needs a capture date', result['error'])
                self.assertEqual(set(self.root.iterdir()), before)
        output = self.execute([
            step('metadata.set_capture', datetime='2024-02-29 12:00:00', timezone='unknown'),
            {'op': 'file.rename_output', 'pattern': '{{date}}_{date}'}])
        self.assertEqual(output.name, '{date}_20240229_120000.png')

    def test_set_all_then_shift_all_uses_the_working_dates(self):
        source = self.root / 'ordered-dates.jpg'
        self.cmd('magick', self.source, source)
        # Remove container-generated dates as well as descriptive metadata.
        self.cmd('exiftool', '-overwrite_original', '-all=', source)
        before = (source.read_bytes(), source.stat().st_mtime_ns)
        operations = [
            step('metadata.set_capture', datetime='2024-02-29 12:00:00',
                 timezone='UTC', fields='all'),
            step('metadata.shift_capture', seconds=86400, fields='all'),
        ]
        try:
            result = core.execute(base.recipe(operations), [source])[0]
            self.assertTrue(result['ok'], result)
            tags = __import__('json').loads(self.cmd(
                'exiftool', '-json', '-G1', '-DateTimeOriginal', '-CreateDate',
                '-ModifyDate', result['output']))[0]
            expected = {
                'ExifIFD:DateTimeOriginal': '2024:03:01 12:00:00',
                'ExifIFD:CreateDate': '2024:03:01 12:00:00',
                'IFD0:ModifyDate': '2024:03:01 12:00:00',
                'XMP-exif:DateTimeOriginal': '2024:03:01 12:00:00+00:00',
                'XMP-xmp:CreateDate': '2024:03:01 12:00:00+00:00',
                'XMP-xmp:ModifyDate': '2024:03:01 12:00:00+00:00',
            }
            self.assertEqual({tag: tags.get(tag) for tag in expected}, expected)
        finally:
            self.assertEqual((source.read_bytes(), source.stat().st_mtime_ns), before)
            self.assertFalse(list(self.root.rglob('.kim6-stage.*')))

    def test_shift_all_retains_distinct_exif_and_xmp_clock_precision(self):
        source = self.root / 'mirrored-dates.jpg'
        self.cmd('magick', self.source, source)
        self.cmd('exiftool', '-overwrite_original', '-all=', source)
        self.cmd('exiftool', '-overwrite_original',
                 '-EXIF:DateTimeOriginal=2020:01:02 03:04:05',
                 '-EXIF:OffsetTimeOriginal=+02:00', '-EXIF:SubSecTimeOriginal=123456789',
                 '-EXIF:CreateDate=2019:12:30 04:05:06',
                 '-EXIF:OffsetTimeDigitized=-04:00', '-EXIF:SubSecTimeDigitized=001',
                 '-EXIF:ModifyDate=2021:02:03 05:06:07',
                 '-EXIF:OffsetTime=+05:30', '-EXIF:SubSecTime=987654321',
                 '-XMP-exif:DateTimeOriginal=2020:01:02 03:04:05.123456789+02:00',
                 '-XMP-xmp:CreateDate=2019:12:30 04:05:06.001-04:00',
                 '-XMP-xmp:ModifyDate=2021:02:03 05:06:07.987654321+05:30', source)
        before = (source.read_bytes(), source.stat().st_mtime_ns)
        try:
            result = core.execute(base.recipe([
                step('metadata.shift_capture', seconds=86400, fields='all')]), [source])[0]
            self.assertTrue(result['ok'], result)
            tags = __import__('json').loads(self.cmd(
                'exiftool', '-json', '-G1', '-DateTimeOriginal', '-CreateDate',
                '-ModifyDate', '-SubSecTimeOriginal', '-SubSecTimeDigitized',
                '-SubSecTime', '-OffsetTimeOriginal', '-OffsetTimeDigitized',
                '-OffsetTime', result['output']))[0]
            expected = {
                'ExifIFD:DateTimeOriginal': '2020:01:03 03:04:05',
                'ExifIFD:CreateDate': '2019:12:31 04:05:06',
                'IFD0:ModifyDate': '2021:02:04 05:06:07',
                'XMP-exif:DateTimeOriginal': '2020:01:03 03:04:05.123456789+02:00',
                'XMP-xmp:CreateDate': '2019:12:31 04:05:06.001-04:00',
                'XMP-xmp:ModifyDate': '2021:02:04 05:06:07.987654321+05:30',
                'ExifIFD:SubSecTimeOriginal': '123456789',
                'ExifIFD:SubSecTimeDigitized': '001',
                'ExifIFD:SubSecTime': '987654321',
                'ExifIFD:OffsetTimeOriginal': '+02:00',
                'ExifIFD:OffsetTimeDigitized': '-04:00',
                'ExifIFD:OffsetTime': '+05:30',
            }
            # ExifTool JSON emits digit-only values without leading zeroes as
            # numbers. Check exact text too, retaining the leading-zero case.
            for tag in ('SubSecTimeOriginal', 'SubSecTimeDigitized', 'SubSecTime'):
                self.assertEqual(self.cmd('exiftool', '-s3', '-EXIF:' + tag,
                                          result['output']).strip().decode(), expected['ExifIFD:' + tag])
            self.assertEqual({tag: str(tags[tag]) if tag.startswith('ExifIFD:SubSecTime') and tag in tags
                              else tags.get(tag) for tag in expected}, expected)
        finally:
            self.assertEqual((source.read_bytes(), source.stat().st_mtime_ns), before)
            self.assertFalse(list(self.root.rglob('.kim6-stage.*')))

    def test_repeated_shifts_keep_independent_group_clocks_and_unknown_zones(self):
        source = self.root / 'independent.jpg'
        self.cmd('magick', self.source, source)
        self.cmd('exiftool', '-overwrite_original', '-all=', source)
        clocks = {
            'EXIF:DateTimeOriginal': '2020:01:02 03:04:05',
            'EXIF:CreateDate': '2018:02:03 04:05:06',
            'EXIF:ModifyDate': '2017:03:04 05:06:07',
            'XMP-exif:DateTimeOriginal': '2022:04:05 06:07:08.000123456-04:00',
            'XMP-photoshop:DateCreated': '2021:05:06 07:08:09.001+05:30',
            'XMP-xmp:CreateDate': '2016:06:07 08:09:10.987654321+02:00',
            'XMP-xmp:ModifyDate': '2015:07:08 09:10:11.000001',
        }
        self.cmd('exiftool', '-overwrite_original',
                 *['-' + tag + '=' + value for tag, value in clocks.items()],
                 '-EXIF:SubSecTimeOriginal=000123456', source)
        before = (source.read_bytes(), source.stat().st_mtime_ns)
        try:
            # A capture-only shift followed by all-fields shift must compose;
            # creation/modification move once, capture and its mirrors twice.
            output = self.execute([step('metadata.shift_capture', seconds=3600),
                                   step('metadata.shift_capture', seconds=-7200, fields='all')], source)
            expected = {
                'EXIF:DateTimeOriginal': '2020:01:02 02:04:05',
                'EXIF:CreateDate': '2018:02:03 02:05:06',
                'EXIF:ModifyDate': '2017:03:04 03:06:07',
                'XMP-exif:DateTimeOriginal': '2022:04:05 05:07:08.000123456-04:00',
                'XMP-photoshop:DateCreated': '2021:05:06 06:08:09.001+05:30',
                'XMP-xmp:CreateDate': '2016:06:07 06:09:10.987654321+02:00',
                'XMP-xmp:ModifyDate': '2015:07:08 07:10:11.000001',
                'EXIF:SubSecTimeOriginal': '000123456',
                'EXIF:OffsetTimeOriginal': '',
                'EXIF:OffsetTimeDigitized': '',
                'EXIF:OffsetTime': '',
            }
            for tag, value in expected.items():
                self.assertEqual(self.cmd('exiftool', '-s3', '-' + tag, output).strip().decode(), value, tag)
        finally:
            self.assertEqual((source.read_bytes(), source.stat().st_mtime_ns), before)
            self.assertFalse(list(self.root.rglob('.kim6-stage.*')))

    def test_compress_presets_use_one_encoder_and_keep_icc(self):
        import kim_recipe_image as image
        real = image.run
        for fmt in ('jpeg','png','webp','avif'):
            for preset in ('recommended','maximum','custom'):
                with self.subTest(fmt=fmt,preset=preset):
                    calls = []
                    def trace(args,**kw):
                        if args[0] == 'magick' and args[-1].startswith(fmt.upper()+':'): calls.append(args)
                        return real(args,**kw)
                    operations = [step('image.convert',format=fmt),step('image.compress',preset=preset,quality=43,png_level=3,jpeg_optimize=True)]
                    with patch.object(image,'run',side_effect=trace): output = self.execute(operations)
                    self.assertEqual(len(calls),1)
                    self.assertEqual(self.cmd('exiftool','-b','-ICC_Profile',output),self.cmd('exiftool','-b','-ICC_Profile',self.source))
                    settings = calls[0]
                    if fmt == 'png': self.assertIn('png:compression-level='+str({'recommended':6,'maximum':9,'custom':3}[preset]),settings)
                    else: self.assertEqual(settings[settings.index('-quality')+1],str({'recommended':85,'maximum':70,'custom':43}[preset]))

    def test_duplicate_conversion_compression_and_order_reject_precisely(self):
        convert,compress = step('image.convert'),step('image.compress')
        for operations,expected in [([convert,convert],'Multiple Convert Format'),([convert,compress,compress],'one compression'),([step('image.convert',format='tiff'),compress],'supports JPEG')]:
            row = core.preview(base.recipe(operations),[self.source])[0]
            self.assertIn(expected,row.problems[0])

        self.assertFalse(core.preview(base.recipe([compress,convert]),[self.source])[0].problems)

    def test_quality_inheritance_stays_a_reference_and_confirmation_binds_it(self):
        from kim_recipe_run import confirmation_snapshot
        recipe = base.recipe([step('image.convert',quality=None)])
        path = self.root/'recipes.json';core.save_users([recipe],path)
        self.assertIsNone(core.read_recipes(path)[0]['steps'][0]['quality'])
        with patch.dict(os.environ,KIM_WEB_QUALITY_JPEG='81'):
            self.assertEqual(core.preview(recipe,[self.source])[0].properties['quality'],81)
            snapshot,error = confirmation_snapshot(recipe)
            self.assertIsNone(error);self.assertEqual(snapshot['steps'][0]['quality'],81)
        with patch.dict(os.environ,KIM_WEB_QUALITY_JPEG='64'):
            self.assertEqual(core.preview(recipe,[self.source])[0].properties['quality'],64)
            self.assertEqual(core.preview(snapshot,[self.source])[0].properties['quality'],81)
        with patch.dict(os.environ,KIM_WEB_QUALITY_JPEG='invalid'):
            self.assertIn('Correct Settings',core.preview(recipe,[self.source])[0].problems[0])

    def test_collage_publication_numbers_actual_occupied_names(self):
        from support import Workspace
        from kim_collage_dialog import collision_message
        w = Workspace();self.addCleanup(w.close);w.use_real_gallery_collage()
        w.env['KIM6_CREATE_PICK_MORE']='0'
        source = w.ppm('source/photo.ppm');before = w.observe(source)
        w.path('out').mkdir();output=w.path('out/collage.png')
        for name in ('collage.png','collage_1.png','collage_2.png'):
            w.path('out/'+name).write_bytes(b'occupied')
        w.path('out/collage_3.png').symlink_to(w.path('out/missing'))
        self.assertIn('collage_4.png',collision_message(str(output)))
        result=w.dispatch('collage','--layout','grid','--canvas','120x100','--gap','4','--fit','fit','--frame','none','--no-shadow','--output',output,'--',source)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(w.path('out/collage_4.png').is_file())
        self.assertEqual(w.observe(source),before)
        self.assertEqual(output.read_bytes(),b'occupied')

    def test_custom_geometry_rotation_names_and_metadata_retention(self):
        operations = [step('image.resize_long_edge',pixels=20),step('image.rotate',degrees=45.5),step('image.resize_geometry',geometry='17x23!'),step('image.convert',format='png'),step('metadata.strip_descriptive'),step('metadata.copyright',creator='Author',notice='Copyright {YEAR}',rights='',year='2024'),step('file.name_transform',method='sequential',value='Photo_',start=7,padding=4),{'op':'file.preserve_date'}]
        output = self.execute(operations)
        self.assertEqual(output.name,'Photo_0007.png')
        self.assertEqual(self.cmd('magick','identify','-format','%w|%h',output),b'17|23')
        self.assertEqual(output.stat().st_mtime_ns,self.before[1])
        self.assertEqual(self.cmd('exiftool','-s3','-EXIF:Copyright',output).strip(),b'Copyright 2024')
        self.assertTrue(self.cmd('exiftool','-b','-ICC_Profile',output))
        area_output = self.execute([step('image.resize_geometry',geometry='500@>')])
        w,h = map(int,self.cmd('magick','identify','-format','%w %h',area_output).split())
        self.assertLessEqual(w*h,500)

    def test_digest_advisory_requires_exact_text_success_and_valid_profile(self):
        warning = b'Warning: IPTCDigest is not current. XMP may be out of sync - /tmp/stage.tiff\n'
        for status,stderr,success in [(0,warning,True),(1,warning,False),(0,warning+b'Warning: Bad ICC_Profile - /tmp/stage.tiff\n',False),(0,b'Warning: Unknown metadata problem\n',False)]:
            with self.subTest(status=status,stderr=stderr):
                result = subprocess.CompletedProcess(['exiftool'],status,b'profile',stderr)
                with patch.object(psd,'run_process',return_value=result),psd.source_session():
                    if success:
                        self.assertEqual(psd.command(['exiftool','-b','-ICC_Profile','/tmp/stage.tiff']),b'profile')
                        self.assertIn(psd.DIGEST_WARNING,psd.session_warnings())
                    else:
                        with self.assertRaises(psd.PSDError): psd.command(['exiftool','-b','-ICC_Profile','/tmp/stage.tiff'])

    def test_psd_admission_then_preflight_decodes_once(self):
        from kim_recipe_run import AddFilesWorker
        source=self.root/'admitted.psd';self.cmd('magick',self.source,source)
        actual=psd.command;decodes=[]
        def trace(args,**kwargs):
            if 'psd:-[0]' in args: decodes.append(args)
            return actual(args,**kwargs)
        with patch.object(psd,'command',side_effect=trace):
            admission=AddFilesWorker([str(source)],[],1);admission.run()
            self.assertEqual(admission.accepted,[str(source)])
            self.assertEqual(len(decodes),0)
            row=core.preview(base.recipe([step('image.convert')]),admission.accepted)[0]
            self.assertFalse(row.problems,row.problems)
            self.assertEqual(len(decodes),1)

    def test_psd_raw_metadata_survives_and_unsupported_xmp_edits_fail_preflight(self):
        source = self.root/'layer.psd'; self.cmd('magick',self.source,source)
        packet = self.root/'packet.xmp'
        packet.write_text('<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description xmlns:xmpMM="http://ns.adobe.com/xap/1.0/mm/"><xmpMM:Manifest><rdf:Seq/></xmpMM:Manifest></rdf:Description></rdf:RDF></x:xmpmeta>')
        self.cmd('exiftool','-overwrite_original','-XMP<='+str(packet),'-IPTC:City=Test',source)
        output = self.execute([step('image.convert')],source)
        for tag in ('XMP','IPTC'):
            self.assertEqual(self.cmd('exiftool','-b','-'+tag,source),self.cmd('exiftool','-b','-'+tag,output))
        date = step('metadata.set_capture',datetime='2024-02-29 12:00:00',timezone='UTC')
        row = core.preview(base.recipe([step('image.convert'),date]),[source])[0]
        self.assertIn('Manifest',row.problems[0])
        self.execute([step('image.convert'),{'op':'metadata.strip_descriptive'},date],source)

    def test_single_still_gif_and_jp2_inputs_and_animated_png_rejection(self):
        for fmt in ('gif','jp2'):
            source = self.root/('still.'+fmt);self.cmd('magick',self.source,source)
            self.execute([step('image.convert',format='png')],source)
        if not shutil.which('ffmpeg'): self.skipTest('FFmpeg unavailable for actual APNG')
        source = self.root/'animated.png'
        self.cmd('ffmpeg','-v','error','-f','lavfi','-i','color=red:s=32x24:r=2','-frames:v','2','-plays','0','-f','apng',source)
        self.assertIn('Animated PNG',core.preview(base.recipe([step('image.convert')]),[source])[0].problems[0])


class CorrectnessGuiTests(unittest.TestCase):
    run_gui = base.RecipeGuiTests.run_gui

    def test_date_picker_compress_search_roundtrip_and_async_stale_preview(self):
        self.run_gui('''
import copy,time,tempfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QDate,QTime,QTimer,QEventLoop
from kim_recipe_core import PreviewRow,RecipeLibrary,save_library,load_library
from kim_recipe_image import ImageHandler
from kim_recipe_dialog import RecipeWidget,OperationPicker,CaptureDateInput
app=QApplication([])
def wait_until(test):
    end=time.monotonic()+5
    while not test() and time.monotonic()<end:
        app.processEvents();time.sleep(.005)
    assert test()
picker=OperationPicker(ImageHandler().operation_definitions());picker.search.setText('compress')
assert picker.operation_id=='image.compress'
for i in range(picker.tree.topLevelItemCount()):
    group=picker.tree.topLevelItem(i);labels=[group.child(j).text(0) for j in range(group.childCount())]
    assert labels==sorted(labels,key=str.casefold)
date=CaptureDateInput();values=[];date.changed.connect(values.append)
date.date.setDate(QDate(2024,2,29));assert values[-1]=='2024-02-29 00:00:00'
date.time.setTime(QTime(12,34,56));date.update_value()
assert values[-1]=='2024-02-29 12:34:56'
calls=[]
def preview(recipe,files,**kw):
    time.sleep(.15);calls.append(files[0])
    return [PreviewRow(files[0],'/tmp/'+recipe['id']+'.jpg','image','jpeg')]
with patch('kim_recipe_dialog.preview',side_effect=preview):
    w=RecipeWidget(['/tmp/first.psd']);w.show();ticks=[]
    timer=QTimer();timer.timeout.connect(lambda:ticks.append(1));timer.start(5)
    w.set_examples(['/tmp/second.psd'])
    wait_until(lambda:w.preview_worker is None)
    assert len(ticks)>10
    text=' '.join(w.table.item(r,1).text() for r in range(w.table.rowCount()))
    assert 'first.psd' not in text and 'second.psd' in text
    w.duplicate();w.add_step('image.compress');w.recipe['steps'][-1]['enabled']=False
    w.add_step('metadata.set_capture');r=len(w.recipe['steps'])-1
    widget=w.parameter_widgets['datetime'];widget.date.setDate(QDate(2024,2,29));widget.time.setTime(QTime(12,34,56))
    w.parameter(r,'timezone','unknown');wait_until(lambda:w.preview_worker is None)
    assert w.save();saved=load_library().recipes[0]
    assert saved['steps'][-1]['datetime']=='2024-02-29 12:34:56'
    assert saved['steps'][-2]['op']=='image.compress' and saved['steps'][-2]['enabled'] is False
    w.steps.setCurrentRow(3);w.reset_to_settings(3,'quality')
    assert w.recipe['steps'][3]['quality'] is None
    assert 'Inherited from KIM6 Settings' in w.parameter_modes['quality'].text()
    w.parameter_widgets['quality'].setValue(72);assert w.recipe['steps'][3]['quality']==72
    w.update_preview();w.stop_preview();wait_until(lambda:w.preview_worker is None)
    timer.stop();w.close()
''')

    def test_collage_live_collision_and_safe_final_numbering_helper(self):
        self.run_gui('''
import tempfile
from pathlib import Path
from PySide6.QtWidgets import QApplication,QDialog,QLineEdit,QLabel
from unittest.mock import patch
import kim_collage_dialog as collage
app=QApplication([])
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);source=root/'input.png';source.touch()
    for name in ('collage.png','collage_1.png','collage_2.png'): (root/name).write_bytes(b'occupied')
    (root/'collage_3.png').symlink_to(root/'missing')
    def inspect(dialog):
        output=next(w for w in dialog.findChildren(QLineEdit) if w.text().endswith('collage.png'))
        label=next(w for w in dialog.findChildren(QLabel) if w.accessibleName()=='Planned collage filename collision')
        assert 'collage_4.png' in label.text()
        output.setText(str(root/'another.png'));assert label.isHidden()
        output.setText(str(root/'collage'));assert 'collage_4.png' in label.text()
        return QDialog.Rejected
    with patch.object(collage.sys,'argv',['collage',str(root/'options'),str(source)]),patch.object(QDialog,'exec',inspect):
        assert collage.main()==1
    assert (root/'collage.png').read_bytes()==b'occupied'
''')
