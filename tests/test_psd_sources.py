"""Real PSD coder, dispatcher publication and Recipe integration on owned files.

The missing-merged fixture is a structurally edited ImageMagick PSD with a
VersionInfo resource declaring no merged image and no merged pixel payload.
It exercises the actual coder fallback, but is not a Photoshop fidelity sample.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

from support import Workspace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/bin'))
from kim_psd_source import normalize, header, PSDError, WARNING
import kim_recipe_core as core
import test_recipes as recipes_test
recipe = recipes_test.recipe
from test_recipe_workflow import WAIT


def run(*args):
    return subprocess.run(list(map(str, args)), check=True, capture_output=True, timeout=40).stdout


def missing_merged(data, no_layers=False):
    u32 = lambda n: struct.pack('>I', n)
    pos = 26 + 4 + struct.unpack_from('>I', data, 26)[0]
    size = struct.unpack_from('>I', data, pos)[0]
    end = pos + 4 + size
    payload = u32(1) + b'\0' + u32(0) + u32(0) + u32(1)
    resource = b'8BIM' + struct.pack('>H', 1057) + b'\0\0' + u32(len(payload)) + payload + b'\0'
    layer_end = end + 4 + struct.unpack_from('>I', data, end)[0]
    layers = u32(0) if no_layers else data[end:layer_end]
    return data[:pos] + u32(size + len(resource)) + data[pos+4:end] + resource + layers + b'\0\0'


@unittest.skipUnless(shutil.which('magick') and shutil.which('exiftool'), 'ImageMagick and ExifTool required')
class PSDSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='kim-psd-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / 'cache'
        self.source = self.root / 'layers 雪 [draft].psd'
        # Saved composite is red; the editable layer is blue.
        run('magick', '-size', '40x30', 'xc:red', '-size', '40x30', 'xc:blue', self.source)
        self.before = (self.source.read_bytes(), self.source.stat().st_mtime_ns)

    def assert_original(self):
        self.assertEqual((self.source.read_bytes(), self.source.stat().st_mtime_ns), self.before)

    def test_embedded_and_missing_composite_are_single_canvas_images(self):
        for missing, expected in ((False, '255,0,0'), (True, '0,0,255')):
            path = self.source
            if missing:
                path = self.root / 'missing.psd'
                path.write_bytes(missing_merged(self.source.read_bytes()))
            output = normalize(path, self.cache)
            info = run('magick', output, '-format', '%n|%w|%h|%[pixel:p{0,0}]', 'info:').decode()
            self.assertTrue(info.startswith('1|40|30|'), info)
            self.assertIn(expected, info)
        self.assertIn('best-effort', WARNING)
        self.assert_original()

    def test_absent_layers_corruption_psb_and_resource_limit_fail_closed(self):
        variants = [missing_merged(self.source.read_bytes(), no_layers=True), self.source.read_bytes()[:100]]
        psb = bytearray(self.source.read_bytes()); psb[4:6] = b'\0\2'; variants.append(psb)
        huge = bytearray(self.source.read_bytes()); huge[14:22] = struct.pack('>II', 30000, 30000); variants.append(huge)
        data = self.source.read_bytes()
        pos = 30 + struct.unpack_from('>I', data, 26)[0]
        size = struct.unpack_from('>I', data, pos)[0]; end = pos + 4 + size
        bad_icc = b'8BIM' + struct.pack('>H', 1039) + b'\0\0' + struct.pack('>I', 128) + b'x'*128
        variants.append(data[:pos] + struct.pack('>I', size+len(bad_icc)) + data[pos+4:end] + bad_icc + data[end:])
        for index, data in enumerate(variants):
            path = self.root / f'invalid-{index}.psd'; path.write_bytes(data)
            with self.subTest(index=index), self.assertRaises(PSDError): normalize(path, self.cache)
        self.assert_original()

    def test_profiles_cmyk_grayscale_alpha_and_sixteen_bit(self):
        srgb = '/usr/share/color/icc/sRGB.icc'
        cmyk = '/usr/share/color/icc/ISOcoated_v2_bas.ICC'
        gray = '/usr/share/color/icc/sGrey-v2-micro.icc'
        for name, options in (
            ('rgb', ['-profile', srgb]),
            ('cmyk', ['-profile', srgb, '-profile', cmyk]),
            ('unprofiled-cmyk', ['-colorspace', 'CMYK']),
            ('gray', ['-colorspace', 'Gray', '-profile', gray]),
            ('unprofiled-gray', ['-colorspace', 'Gray']),
            ('alpha16', ['-alpha', 'set', '-channel', 'A', '-evaluate', 'set', '50%', '+channel', '-depth', '16'])):
            if any(arg.endswith(('.icc', '.ICC')) and not Path(arg).exists() for arg in options):
                self.skipTest('required test ICC fixtures unavailable')
            path = self.root / (name + '.psd')
            run('magick', '-size', '40x30', 'gradient:red-blue', *options, path)
            with self.subTest(mode=name):
                if name == 'unprofiled-cmyk':
                    with self.assertRaisesRegex(PSDError, 'Unprofiled CMYK'): normalize(path, self.cache)
                    continue
                output = normalize(path, self.cache)
                self.assertEqual(run('magick', 'identify', '-format', '%n|%w|%h', output), b'1|40|30')
                self.assertTrue(run('exiftool', '-b', '-ICC_Profile', output))
                if name == 'alpha16':
                    self.assertEqual(run('magick', 'identify', '-format', '%z', output), b'16')
                    alpha = float(run('magick', output, '-format', '%[fx:p{0,0}.a]', 'info:'))
                    self.assertAlmostEqual(alpha, .5, places=3)
                    for target, expected_depth in (('png', b'16'), ('jpeg', b'8')):
                        r = recipe([{'op':'image.convert','format':target,'quality':90}])
                        results = core.execute(r, [path])
                        self.assertTrue(results[0]['ok'], results)
                        self.assertEqual(run('magick','identify','-format','%z',results[0]['output']),expected_depth)
                if name == 'cmyk':
                    reference = self.root / 'reference.png'
                    run('magick', str(path)+'[0]', '-profile', srgb, reference)
                    metric = run('magick', output, reference, '-compose', 'difference', '-composite',
                                 '-format', '%[fx:mean]', 'info:')
                    self.assertLess(float(metric), .001)
        self.assert_original()

    def test_recipes_web_export_inheritance_multi_input_and_numbering(self):
        jpg = self.root / 'other.jpg'; png = self.root / 'other.png'
        for path in (jpg, png): run('magick', '-size', '30x20', 'xc:green', path)
        inputs = [self.source, jpg, png]
        hashes = [hashlib.sha256(p.read_bytes()).digest() for p in inputs]
        r = core.builtins()[0]
        rows = core.preview(r, inputs)
        self.assertFalse(any(row.problems for row in rows), rows)
        self.assertTrue(rows[0].warnings)
        self.assertFalse((self.root / 'Web').exists(), 'preflight created a directory')
        seen_outputs = set()
        for iteration in range(2):
            results = core.execute(r, inputs)
            self.assertTrue(all(result['ok'] for result in results), results)
            for result in results:
                output = Path(result['output'])
                self.assertEqual(run('magick', 'identify', '-format', '%m|%n', output), b'JPEG|1')
                self.assertFalse(run('exiftool', '-b', '-ICC_Profile', output))
                self.assertNotIn(str(output), seen_outputs)
                seen_outputs.add(str(output))
        inherited = recipe([{'op':'image.convert','format':'png','quality':90}, {'op':'metadata.creator'}])
        with unittest.mock.patch.dict(os.environ, KIM_COPYRIGHT_CREATOR='PSD Author'):
            results = core.execute(inherited, [self.source])
        self.assertTrue(results[0]['ok'], results)
        self.assertEqual(run('exiftool', '-s3', '-XMP-dc:Creator', results[0]['output']).strip(), b'PSD Author')
        self.assertEqual(hashes, [hashlib.sha256(p.read_bytes()).digest() for p in inputs])
        self.assert_original()


class PSDDispatcherTests(unittest.TestCase):
    def setUp(self):
        self.w = Workspace(); self.addCleanup(self.w.close)
        # Real codecs and validators; only desktop dialogs/mail/progress are adapters.
        for tool in ('magick','identify','exiftool','ffmpeg','ffprobe','pdfinfo','pdftoppm','setsid'):
            executable = shutil.which(tool)
            if not executable: self.skipTest(tool + ' unavailable')
            (self.w.bin/tool).unlink(); (self.w.bin/tool).symlink_to(executable)
        self.w.env['PATH'] += os.pathsep + os.defpath
        self.w.env.update(KIM_POLICY='create', KIM6_CREATE_PICK_MORE='0', MAGICK_THREAD_LIMIT='1')
        self.w.path('out').mkdir()
        self.inputs = [self.w.path('input/document 雪.psd'), self.w.path('input/photo.jpg'), self.w.path('input/transparent.png')]
        self.inputs[0].parent.mkdir()
        run('magick','-size','40x30','xc:red','-size','40x30','xc:blue',self.inputs[0])
        for path in self.inputs[1:]: run('magick','-size','40x30','xc:green',path)
        self.before = [self.w.observe(p) for p in self.inputs]
        # Replace modal settings selection only; the real dispatcher plans,
        # processes, validates and publishes every image below.
        (self.w.control/'kim_album_dialog.py').write_text("import sys,os\nopen(sys.argv[1],'wb').write(('1\\0'+os.environ['PSD_TEST_OUTPUT']+'\\0').encode())\n")
        (self.w.control/'kim_create_dialog.py').write_text("import sys,os\nopen(sys.argv[2],'wb').write('\\0'.join(['PSD Gallery','Author','3','dark','1920',os.environ['PSD_TEST_OUTPUT'],'']).encode())\n")

    def dispatch(self, *args):
        result = subprocess.run([str(self.w.dispatcher), *map(str,args)], cwd=self.w.root,
                                env=self.w.env, capture_output=True, text=True, timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr + '\n' + self.w.log.read_text()[-5000:])
        self.assertEqual([self.w.observe(p) for p in self.inputs], self.before)
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))
        return result

    def test_mixed_convert_web_and_opaque_background(self):
        self.dispatch('convert','--format','png','--',*self.inputs)
        self.assertEqual(run('magick','identify','-format','%m|%n|%w|%h',self.inputs[0].with_suffix('.png')),b'PNG|1|40|30')
        self.w.path('out/web').mkdir()
        self.dispatch('webexport','--output-dir',self.w.path('out/web'),'--format','jpg','--size','20x20','--',*self.inputs)
        self.assertEqual(len(list(self.w.path('out/web').glob('*.jpg'))),3)
        # A transparent source must become intentional white in an opaque target.
        run('magick','-size','40x30','xc:none',self.inputs[0])
        self.before = [self.w.observe(p) for p in self.inputs]
        self.dispatch('convert','--format','jpg','--',self.inputs[0])
        self.assertEqual(run('magick',self.inputs[0].with_suffix('.jpg'),'-format','%[fx:mean]','info:'), b'1')

    def test_mixed_collage_contactsheet_album_print_gif_tiff_gallery(self):
        for action, extension in (('collage','png'),('contactsheet','pdf'),('album','pdf'),('print','pdf'),('animate','gif'),('tiffjoin','tiff'),('gallery','html')):
            with self.subTest(action=action):
                output = self.w.path('out/'+action+'.'+extension)
                self.w.env['PSD_TEST_OUTPUT'] = str(output if action != 'gallery' else self.w.path('out/gallery'))
                if action == 'collage':
                    self.dispatch(action,'--layout','grid','--canvas','400x300','--gap','8','--frame','none','--no-shadow','--output',output,'--',*self.inputs)
                elif action == 'contactsheet':
                    self.dispatch(action,'--dpi','150','--output',output,'--',*self.inputs)
                elif action == 'album': self.dispatch(action,self.w.root,*self.inputs)
                elif action == 'print':
                    self.w.respond_to('kdialog','Kim - Select print layout:',{'stdout':'1\n'})
                    self.w.respond_to('kdialog','--getsavefilename',{'stdout':str(output)+'\n'})
                    self.dispatch(action,self.w.root,*self.inputs)
                elif action == 'animate': self.dispatch(action,'--delay','25','--loop','0','--output',output,'--',*self.inputs)
                elif action == 'tiffjoin': self.dispatch(action,'--output',output,'--',*self.inputs)
                else:
                    self.w.path('out/gallery').mkdir()
                    self.dispatch(action,self.w.root,*self.inputs)
                    images=list(self.w.path('out/gallery').rglob('images/*'))
                    self.assertEqual(len(images),3)
                    self.assertTrue(any(p.suffix == '.png' for p in images))
                    continue
                self.assertTrue(output.is_file())
                if extension in ('gif','tiff'):
                    frames = run('magick','identify','-format','%w|%h\n',output).splitlines()
                    self.assertEqual(len(frames),3)

    def test_existing_conversion_targets_receive_one_psd_image(self):
        formats = run('magick','-list','format').decode()
        for extension, coder in (('avif','AVIF'),('bmp','BMP'),('gif','GIF'),('heic','HEIC'),
                                 ('jp2','JP2'),('jpg','JPEG'),('jxl','JXL'),('pdf','PDF'),
                                 ('png','PNG'),('tiff','TIFF'),('webp','WEBP')):
            with self.subTest(format=extension):
                writable = any(len(fields := line.split()) >= 3 and fields[0].rstrip('*') == coder and 'w' in fields[2]
                               for line in formats.splitlines())
                options = ['--format',extension]
                if extension == 'pdf': options += ['--strip-metadata']
                if extension == 'bmp': options += ['--bmp5']
                if extension == 'jp2': options += ['--jp2-mode','lossless']
                if not writable:
                    result = subprocess.run([str(self.w.dispatcher),'convert',*options,'--',str(self.inputs[0])],
                                            cwd=self.w.root,env=self.w.env,capture_output=True,text=True,timeout=60)
                    self.assertNotEqual(result.returncode,0)
                    self.assertFalse(self.inputs[0].with_suffix('.'+extension).exists())
                    continue
                self.dispatch('convert',*options,'--',self.inputs[0])
                output = self.inputs[0].with_suffix('.'+extension)
                if extension == 'pdf':
                    info=run('pdfinfo',output).decode()
                    self.assertIn('Pages:           1',info)
                else:
                    self.assertEqual(run('magick','identify','-format','%n|%w|%h',output),b'1|40|30')

    def test_profiled_rgb_and_cmyk_dispatch_transform_matches_reference(self):
        srgb='/usr/share/color/icc/sRGB.icc'
        for index, profile in enumerate(('/usr/share/color/icc/AdobeCompat-v2.icc','/usr/share/color/icc/ISOcoated_v2_bas.ICC')):
            if not Path(profile).exists(): self.skipTest('test source profile unavailable')
            run('magick','-size','40x30','gradient:red-blue','-profile',srgb,'-profile',profile,self.inputs[0])
            self.before=[self.w.observe(p) for p in self.inputs]
            reference=self.w.path('out/reference.png')
            run('magick',str(self.inputs[0])+'[0]','-profile',srgb,reference)
            self.dispatch('convert','--format','png','--',self.inputs[0])
            output=self.inputs[0].with_suffix('.png')
            if index: output=output.with_stem(output.stem+'_1')
            difference=run('magick',reference,output,'-compose','difference','-composite','-format','%[fx:mean]','info:')
            self.assertLess(float(difference),.001)
            self.assertEqual(run('exiftool','-b','-ICC_Profile',output),Path(srgb).read_bytes())

    def test_psd_occupied_destination_cancellation_and_partial_failure(self):
        occupied = self.inputs[0].with_suffix('.png'); occupied.write_bytes(b'unrelated destination')
        self.w.approve_overwrite()
        self.dispatch('convert','--format','png','--',self.inputs[0])
        self.assertEqual(occupied.read_bytes(), b'unrelated destination')
        self.assertEqual(run('magick','identify','-format','%m|%n',occupied.with_stem(occupied.stem+'_1')), b'PNG|1')
        broken = self.w.path('input/broken.psd'); broken.write_bytes(self.inputs[0].read_bytes()[:100])
        result = subprocess.run([str(self.w.dispatcher),'convert','--format','webp','--',str(broken),str(self.inputs[1])],
                                cwd=self.w.root,env=self.w.env,capture_output=True,text=True,timeout=60)
        self.assertTrue(self.inputs[1].with_suffix('.webp').is_file(), result.stderr)
        self.assertFalse(broken.with_suffix('.webp').exists())
        self.assertEqual([self.w.observe(p) for p in self.inputs],self.before)
        # Cancel at the existing progress boundary before any source processing.
        self.w.respond_to('qdbus','wasCancelled',{'stdout':'true\n'})
        result = subprocess.run([str(self.w.dispatcher),'convert','--format','tiff','--',str(self.inputs[0])],
                                cwd=self.w.root,env=self.w.env,capture_output=True,text=True,timeout=60)
        self.assertFalse(self.inputs[0].with_suffix('.tiff').exists())
        self.assertEqual([self.w.observe(p) for p in self.inputs],self.before)

    def test_mixed_slideshow_and_email_full_and_resized(self):
        output = self.w.path('out/slides.mp4')
        self.dispatch('slideshow','--seconds-per-photo','1','--size','160x120','--fps','1','--output',output,'--',*self.inputs)
        duration=float(run('ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',output))
        self.assertAlmostEqual(duration,3,places=1)
        for size in ('full','20x20'):
            self.dispatch('resizeandsend','--size',size,'--',*self.inputs)
        attachments=list(self.w.path('.control/data').rglob('*.tiff'))
        self.assertTrue(attachments)
        for path in attachments: self.assertEqual(run('magick','identify','-format','%n',path), b'1')


class FileManagementGuiTests(unittest.TestCase):
    run_gui = recipes_test.RecipeGuiTests.run_gui

    def test_zero_append_picker_rejection_remove_clear_and_destination(self):
        self.run_gui('''
from pathlib import Path
import subprocess
from unittest.mock import patch
from PySide6.QtCore import QEventLoop, QTimer, QUrl, QMimeData, QPointF, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QMessageBox, QLabel
from kim_recipe_core import builtins, config_path
from kim_recipe_run import RunRecipeDialog
app=QApplication([])
''' + WAIT + '''
base=config_path().parent; base.mkdir(parents=True,exist_ok=True)
a=base/'one.jpg'; b=base/'two.psd'
for p in (a,b): subprocess.run(['magick','-size','20x10','xc:red',str(p)],check=True)
w=RunRecipeDialog(builtins()[0],[]); assert not w.run_button.isEnabled()
assert not w.clear_list.isEnabled() and not w.remove_selected.isEnabled()
w.chosen=str(base/'chosen')
from kim_recipe_image import input_name_filters
input_name_filters()  # This picker mock exercises the already-discovered filter path.
with patch('kim_recipe_run.QFileDialog.getOpenFileNames',return_value=([str(a),str(b)],'')) as picker:
    w.pick_files(); assert picker.call_args.args[0] == w
assert not w.run_button.isEnabled()
settle(w); assert w.files==[str(a),str(b)]
assert w.run_button.isEnabled() and '2 Files' in w.run_button.text()
with patch('kim_recipe_run.QMessageBox.warning') as warning:
    w.add_files([str(a.parent/'.'/a.name),str(base),str(base/'missing'), 'https://example.com/a.png']); settle(w)
    assert warning.called and len(w.files)==2
# Exercise the actual drop-event handler with mixed local and remote URLs.
mime=QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(a)),QUrl('https://example.com/no.png')])
event=QDropEvent(QPointF(2,2),Qt.CopyAction,mime,Qt.LeftButton,Qt.NoModifier)
with patch('kim_recipe_run.QMessageBox.warning') as warning:
    w.inputs.dropEvent(event); settle(w); assert warning.called and len(w.files)==2
w.inputs.clearSelection(); w.inputs.topLevelItem(0).setSelected(True); w.remove_files()
assert w.files==[str(b)] and not w.run_button.isEnabled(); settle(w)
assert w.run_button.text()=='Run Recipe on 1 File' and w.chosen==str(base/'chosen')
with patch('kim_recipe_run.QMessageBox.question',return_value=QMessageBox.No): w.clear_files()
assert w.files==[str(b)]
with patch('kim_recipe_run.QMessageBox.question',return_value=QMessageBox.Yes): w.clear_files()
assert not w.files and not w.run_button.isEnabled() and not w.properties.rowCount()
settle(w); assert not w.run_button.isEnabled()
assert any(label.text()=='Originals are never overwritten. KIM6 saves new files and adds a number when names collide, so nothing gets clobbered. Finished results stay put if you cancel or something fails.' for label in w.findChildren(QLabel))
assert a.exists() and b.exists(); w.reject()
''')

    def test_file_changes_and_recipe_switch_ignore_late_worker(self):
        self.run_gui('''
import threading
from unittest.mock import patch
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtWidgets import QApplication
from kim_recipe_core import builtins, PreviewRow
from kim_recipe_run import RunRecipeDialog
app=QApplication([])
''' + WAIT + '''
entered=threading.Event(); release=threading.Event(); calls=[]
def slow(recipe,files,*args,**kwargs):
    calls.append((recipe['id'],list(files)))
    if len(calls)==1: entered.set(); release.wait(5)
    return [PreviewRow(files[0],'/planned/'+files[0]+'.jpg')]
with patch('kim_recipe_run.preview',side_effect=slow):
    r=builtins()[0]; w=RunRecipeDialog(r,['old']); w.chosen='/chosen'
    loop=QEventLoop(); timer=QTimer(); timer.setInterval(10)
    def change():
        if not entered.is_set(): return
        timer.stop(); w.replace_files(['new','other']); w.replace_files([])
        w.replace_files(['final']); changed=dict(w.recipe,id='changed',name='Changed'); w.apply_recipe(changed)
        assert not w.run_button.isEnabled() and not w.rows
        release.set(); loop.quit()
    timer.timeout.connect(change);timer.start();QTimer.singleShot(6000,loop.quit);loop.exec();settle(w)
    assert w.files==['final'] and w.recipe['id']=='changed' and w.chosen=='/chosen'
    assert w.rows[0].source=='final' and w.rows[0].output=='/planned/final.jpg'
    assert w.run_button.isEnabled() and calls[-1]==('changed',['final'])
    w.reject()
''')
