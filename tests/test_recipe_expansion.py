"""Focused regression coverage for the Recipes correctness/format expansion."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import test_psd_sources as fixtures
import test_recipes as base
import kim_recipe_core as core
import kim_psd_source as psd
from kim_recipe_image import ImageHandler


class ConvertDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.PSDDispatcherTests('test_mixed_convert_web_and_opaque_background')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.w=self.fixture.w

    def test_broken_psd_never_reports_an_apng_failure(self):
        source=self.fixture.inputs[0]
        source.write_bytes(source.read_bytes()[:100])
        before=self.w.observe(source)
        result=subprocess.run([str(self.w.dispatcher),'convert','--format','jpg','--',str(source)],
                              cwd=self.w.root,env=self.w.env,capture_output=True,text=True,timeout=30)
        calls=[json.loads(line) for line in self.w.log.read_text().splitlines()]
        messages='\n'.join(c['argv'][-1] for c in calls if c['tool']=='kdialog' and '--error' in c['argv'])
        self.assertNotIn('APNG',messages)
        self.assertIn('PSD',messages)
        self.assertEqual(self.w.observe(source),before)
        self.assertFalse(source.with_suffix('.jpg').exists())

    def test_large_psd_jpeg_pdf_and_real_png_are_not_apng(self):
        source=self.fixture.inputs[0]
        subprocess.run(['magick','-size','6000x4000','gradient:red-blue','-depth','16',str(source)],check=True,capture_output=True)
        self.fixture.before=[self.w.observe(p) for p in self.fixture.inputs]
        for fmt in ('jpg','pdf'):
            self.fixture.dispatch('convert','--format',fmt,*(['--strip-metadata'] if fmt=='pdf' else []),'--',source)
            self.assertTrue(source.with_suffix('.'+fmt).exists())
        self.fixture.dispatch('convert','--format','jpg','--',self.fixture.inputs[2])
        messages='\n'.join(c['argv'][-1] for c in [json.loads(l) for l in self.w.log.read_text().splitlines()] if c['tool']=='kdialog' and '--error' in c['argv'])
        self.assertNotIn('APNG',messages)

    def test_actual_apng_probe_failure_remains_specific(self):
        if not shutil.which('ffmpeg'): self.skipTest('FFmpeg unavailable')
        source=self.w.path('input/animation.png')
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:s=32x24:r=2','-frames:v','2','-plays','0','-f','apng',str(source)],check=True,capture_output=True)
        (self.w.bin/'ffprobe').unlink()
        (self.w.bin/'ffprobe').symlink_to('/bin/false')
        subprocess.run([str(self.w.dispatcher),'convert','--format','jpg','--',str(source)],cwd=self.w.root,env=self.w.env,capture_output=True,timeout=30)
        messages='\n'.join(c['argv'][-1] for c in [json.loads(l) for l in self.w.log.read_text().splitlines()] if c['tool']=='kdialog' and '--error' in c['argv'])
        self.assertIn('APNG animation could not be safely inspected',messages)
        self.assertFalse(source.with_suffix('.jpg').exists())

    def test_resource_and_unsupported_decode_diagnostics(self):
        probe=self.w.control/'failed-identify'
        for message, expected in (('cache resources exhausted','resource or security-policy limit'),('no decode delegate for this image format','unsupported image format')):
            probe.write_text('#!/bin/sh\necho '+repr(message)+' >&2\nexit 1\n');probe.chmod(0o700)
            (self.w.bin/'identify').unlink();(self.w.bin/'identify').symlink_to(probe)
            self.w.log.write_text('')
            subprocess.run([str(self.w.dispatcher),'convert','--format','jpg','--',str(self.fixture.inputs[2])],cwd=self.w.root,env=self.w.env,capture_output=True,timeout=30)
            messages='\n'.join(c['argv'][-1] for c in [json.loads(l) for l in self.w.log.read_text().splitlines()] if c['tool']=='kdialog' and '--error' in c['argv'])
            self.assertIn(expected,messages);self.assertNotIn('APNG',messages)


class RecipeFormatTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='kim6-recipe-format-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.source=self.root/'source 雪.png'
        self.cmd('magick','-size','40x30','gradient:red-blue','-profile','/usr/share/color/icc/sRGB.icc',self.source)
        self.before=(self.source.read_bytes(),self.source.stat().st_mtime_ns)

    def cmd(self,*args):
        return subprocess.run(list(map(str,args)),check=True,capture_output=True,timeout=30).stdout

    def test_each_available_writer_single_output_icc_alpha_and_numbering(self):
        from kim_recipe_image import FORMATS,CODERS
        formats=self.cmd('magick','-list','format').decode()
        for fmt in FORMATS:
            with self.subTest(format=fmt):
                r=base.recipe([{'op':'image.convert','format':fmt,'quality':75}])
                result=core.execute(r,[self.source])[0]
                available=any(len(p:=line.split())>=3 and p[0].rstrip('*')==CODERS[fmt] and 'w' in p[2] for line in formats.splitlines())
                if not available:
                    self.assertFalse(result['ok']);self.assertIn('writer unavailable',result['error']);continue
                self.assertTrue(result['ok'],result)
                output=Path(result['output'])
                self.assertEqual(self.cmd('magick','identify','-format','%n|%w|%h',output),b'1|40|30')
                numbered=core.execute(r,[self.source])[0]
                self.assertTrue(numbered['ok'],numbered);self.assertNotEqual(numbered['output'],str(output))
        self.assertEqual((self.source.read_bytes(),self.source.stat().st_mtime_ns),self.before)

    def test_options_persist_lossless_lossy_depth_and_metadata_policy(self):
        for fmt,options in (('jp2',{'jp2_mode':'lossless','depth':'16'}),('jp2',{'jp2_mode':'lossy'}),
                            ('tiff',{'tiff_compression':'lzw','depth':'16'}),('jpeg',{'jpeg_progressive':True})):
            r=base.recipe([{'op':'image.convert','format':fmt,'quality':81,**options}])
            self.assertEqual(core.validate(json.loads(json.dumps(r))),r)
            result=core.execute(r,[self.source])[0];self.assertTrue(result['ok'],result)
            if options.get('depth')=='16': self.assertEqual(self.cmd('magick','identify','-format','%z',result['output']),b'16')
        self.cmd('exiftool','-overwrite_original','-EXIF:Artist=Source Artist',self.source)
        for fmt in ('bmp','gif','pdf'):
            r=base.recipe([{'op':'image.convert','format':fmt,'quality':90}])
            result=core.execute(r,[self.source])[0];self.assertFalse(result['ok']);self.assertIn('Remove All Metadata',result['error'])
            r['steps'].append({'op':'metadata.strip_all'})
            result=core.execute(r,[self.source])[0];self.assertTrue(result['ok'],result)
            self.assertFalse(self.cmd('exiftool','-s3','-EXIF:all','-XMP:all','-IPTC:all',result['output']))
        for fmt in ('jpeg','png','webp','avif','tiff','heic','heif','jp2'):
            r=base.recipe([{'op':'image.auto_orient'},{'op':'image.convert','format':fmt,'quality':90}, {'op':'metadata.creator','value':'Recipe Author'}])
            result=core.execute(r,[self.source])[0];self.assertTrue(result['ok'],result)
            self.assertEqual(self.cmd('exiftool','-s3','-XMP-dc:Creator',result['output']).strip(),b'Recipe Author')
        self.cmd('exiftool','-overwrite_original','-IPTC:By-line=Legacy',self.source)
        for fmt in ('webp','avif','heic','heif'):
            steps=[{'op':'image.convert','format':fmt,'quality':90}]
            result=core.execute(base.recipe(steps),[self.source])[0]
            self.assertFalse(result['ok']); self.assertIn('legacy IPTC',result['error'])
            steps += [{'op':'metadata.strip_all'},{'op':'metadata.creator','value':'New Author'}]
            result=core.execute(base.recipe(steps),[self.source])[0];self.assertTrue(result['ok'],result)
            self.assertEqual(self.cmd('exiftool','-s3','-XMP-dc:Creator',result['output']).strip(),b'New Author')
            self.assertFalse(self.cmd('exiftool','-s3','-IPTC:all',result['output']))


    def test_grayscale_and_cmyk_use_valid_source_profiles(self):
        srgb='/usr/share/color/icc/sRGB.icc'; cmyk='/usr/share/color/icc/ISOcoated_v2_bas.ICC'
        self.cmd('magick','-size','40x30','gradient:black-white','-colorspace','Gray','-depth','16',self.source)
        r=base.recipe([{'op':'image.color','mode':'srgb'},{'op':'image.convert','format':'png','quality':90,'depth':'16'}])
        result=core.execute(r,[self.source])[0];self.assertTrue(result['ok'],result)
        self.assertEqual(self.cmd('exiftool','-s3','-ICC_Profile:ColorSpaceData',result['output']).strip(),b'RGB')
        self.assertEqual(self.cmd('magick','identify','-format','%z',result['output']),b'16')
        source=self.root/'cmyk.tiff'
        self.cmd('magick','-size','40x30','gradient:red-blue','-colorspace','CMYK',source)
        result=core.execute(r,[source])[0];self.assertFalse(result['ok']);self.assertIn('Unprofiled CMYK',result['error'])
        if not Path(cmyk).exists(): self.skipTest('CMYK reference profile unavailable')
        self.cmd('magick','-size','40x30','gradient:red-blue','-profile',srgb,'-profile',cmyk,source)
        result=core.execute(r,[source])[0];self.assertTrue(result['ok'],result)
        reference=self.root/'reference.png';self.cmd('magick',source,'-profile',srgb,reference)
        difference=self.cmd('magick',reference,result['output'],'-compose','difference','-composite','-format','%[fx:mean]','info:')
        self.assertLess(float(difference),.001)

    def test_geometry_file_date_blank_override_and_alpha_rules(self):
        self.cmd('magick','-size','40x30','xc:none','-depth','16',self.source)
        expected_ns = 1234567890*1_000_000_000 + 123456789
        os.utime(self.source,ns=(expected_ns,expected_ns))
        for fmt in ('png','tiff','webp','avif','jp2','gif','jpeg','bmp','pdf'):
            steps=[{'op':'image.resize_exact','width':17,'height':23}, {'op':'image.convert','format':fmt,'quality':90}, {'op':'file.preserve_date'}]
            result=core.execute(base.recipe(steps),[self.source])[0];self.assertTrue(result['ok'],result)
            if fmt == 'pdf':
                self.assertIn(b'17 x 23 pts',self.cmd('pdfinfo',result['output']))
            else: self.assertEqual(self.cmd('magick','identify','-format','%w|%h',result['output']),b'17|23')
            self.assertEqual(Path(result['output']).stat().st_mtime_ns,expected_ns)
            if fmt in ('jpeg','bmp','pdf'): self.assertEqual(self.cmd('magick',*(['-density','144'] if fmt=='pdf' else []),result['output'],'-format','%[fx:mean]','info:'),b'1')
            else: self.assertEqual(self.cmd('magick',result['output'],'-format','%[fx:p{0,0}.a]','info:'),b'0')
        self.cmd('exiftool','-overwrite_original','-Artist=Existing',self.source)
        r=base.recipe([{'op':'metadata.creator','value':''}])
        result=core.execute(r,[self.source])[0];self.assertTrue(result['ok'],result)
        self.assertEqual(self.cmd('exiftool','-s3','-Artist',result['output']).strip(),b'Existing')


class SourceLifetimeTests(unittest.TestCase):
    setUp=RecipeFormatTests.setUp
    cmd=RecipeFormatTests.cmd
    # Keep these independent of the format-matrix tests inherited above.
    def test_psd_decodes_once_per_preview_and_execution_and_cleans_lifetime(self):
        source=self.root/'layers.psd';self.cmd('magick',self.source,source)
        actual=psd.command
        decodes=[]
        def spy(args,**kwargs):
            if 'psd:-[0]' in args: decodes.append(Path(args[-1][5:]).parent)
            return actual(args,**kwargs)
        with patch('kim_psd_source.command',side_effect=spy):
            self.assertFalse(core.preview(core.builtins()[0],[source])[0].problems)
            self.assertEqual(len(decodes),1)
            self.assertTrue(core.execute(core.builtins()[0],[source])[0]['ok'])
            self.assertEqual(len(decodes),2)
            self.assertFalse(core.preview(core.builtins()[0],[source])[0].problems)
            self.assertEqual(len(decodes),3)
        self.assertTrue(all(not directory.exists() for directory in decodes))

    def test_cache_fingerprint_changes_and_policy_isolation(self):
        source=self.root/'layers.psd';self.cmd('magick',self.source,source)
        with psd.source_session():
            with psd.prepared(['magick',str(source),'null:']) as args: first=Path(args[1])
            with psd.prepared(['magick',str(source),'null:'],rgb=True) as args: policy=Path(args[1])
            self.cmd('magick','-size','40x30','xc:blue',source)
            with psd.prepared(['magick',str(source),'null:']) as args: changed=Path(args[1])
            self.assertEqual(len({first,policy,changed}),3)
            self.assertTrue(all(p.exists() for p in (first,policy,changed)))
        self.assertTrue(all(not p.exists() for p in (first,policy,changed)))

    def test_tool_timeout_reaps_owned_delegate(self):
        import kim_recipe_image as image
        script=self.root/'delegate.py';pidfile=self.root/'delegate.pid'
        script.write_text("import subprocess,sys,time,signal\nfrom pathlib import Path\nchild=subprocess.Popen(['/bin/sleep','60'])\nPath(sys.argv[1]).write_text(str(child.pid))\ndef stop(*args):\n child.terminate();child.wait();sys.exit(143)\nsignal.signal(signal.SIGTERM,stop)\ntime.sleep(60)\n")
        with patch('kim_recipe_image.TOOL_TIMEOUT',.4), self.assertRaises(core.RecipeError):
            image.run([sys.executable,str(script),str(pidfile)])
        self.assertTrue(pidfile.exists())
        path=Path('/proc')/pidfile.read_text()/'stat'
        self.assertTrue(not path.exists() or path.read_text().split()[2]=='Z')

    def test_psd_resource_header_is_rejected_before_snapshot_copy(self):
        import struct
        source=self.root/'oversized.psd';self.cmd('magick',self.source,source)
        data=bytearray(source.read_bytes());data[14:22]=struct.pack('>II',30000,30000);source.write_bytes(data)
        with patch('shutil.copyfileobj',side_effect=AssertionError('Oversized PSD must not be copied')):
            result=core.execute(core.builtins()[0],[source])[0]
        self.assertFalse(result['ok']);self.assertIn('safety limit',result['error'])
        self.assertEqual(source.read_bytes(),data)
        self.assertFalse(list(self.root.rglob('.kim6-stage.*')))

    def test_resource_boundary_counts_new_tiff_once(self):
        source=self.root/'layers.psd';self.cmd('magick',self.source,source)
        for cached,success in ((600,True),(1300,False)):
            cache=self.root/str(cached);cache.mkdir()
            with (cache/'previous.tiff').open('wb') as stream: stream.truncate(cached*1024**2)
            def sized(args,**kwargs):
                if 'psd:-[0]' in args:
                    with open(args[-1][5:],'wb') as stream: stream.truncate(800*1024**2)
                if args[:2]==['magick','identify']: return b'40|30|8|sRGB\n'
                if '-ICC_Profile' in args: return b'profile-present'
                return b''
            with patch('kim_psd_source.command',side_effect=sized):
                if success: self.assertTrue(Path(psd.normalize(source,cache)).exists())
                else:
                    with self.assertRaisesRegex(psd.PSDError,'2 GiB'): psd.normalize(source,cache)


class ExpansionGuiTests(unittest.TestCase):
    run_gui=base.RecipeGuiTests.run_gui

    def test_grouped_search_keyboard_settings_and_parameter_roundtrip(self):
        self.run_gui('''
import os
from pathlib import Path
from PySide6.QtCore import Qt,QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication,QDialog
from kim_recipe_dialog import RecipeWidget,OperationPicker
from kim_recipe_image import ImageHandler
from kim_recipe_core import config_path,validate
from kim_recipe_run import confirmation_snapshot
app=QApplication([])
p=config_path().with_name('settings.conf');p.parent.mkdir(parents=True,exist_ok=True)
p.write_text('KIM_COPYRIGHT_CREATOR=Global Creator\\nKIM_COPYRIGHT_NOTICE=Global Notice\\nKIM_COPYRIGHT_USAGE_RIGHTS=Global Rights\\n')
for key in ('KIM_COPYRIGHT_CREATOR','KIM_COPYRIGHT_NOTICE','KIM_COPYRIGHT_USAGE_RIGHTS'): os.environ.pop(key,None)
original=p.read_bytes();w=RecipeWidget();w.new();w.add_step('metadata.copyright')
step=w.recipe['steps'][-1];row=len(w.recipe['steps'])-1
for key,value in [('creator','Global Creator'),('notice','Global Notice'),('rights','Global Rights')]:
    assert step[key] is None and w.parameter_widgets[key].text()==value
    assert 'Inherited' in w.parameter_modes[key].text()
w.parameter_widgets['creator'].setText('Custom');w.parameter_widgets['creator'].textEdited.emit('Custom')
assert step['creator']=='Custom' and 'override' in w.parameter_modes['creator'].text()
w.parameter_widgets['creator'].setText('');w.parameter_widgets['creator'].textEdited.emit('')
assert step['creator']=='' and 'Blank' in w.parameter_modes['creator'].text()
w.reset_to_settings(row,'creator');assert step.get('creator') is None
snapshot,error=confirmation_snapshot(w.recipe);assert not error
assert snapshot['steps'][-1]['creator']=='Global Creator' and step.get('creator') is None
assert p.read_bytes()==original
picker=OperationPicker(ImageHandler().operation_definitions());picker.show();app.processEvents()
ids=[]
for index in range(picker.tree.topLevelItemCount()):
    group=picker.tree.topLevelItem(index);names=[group.child(i).text(0) for i in range(group.childCount())]
    assert names==sorted(names,key=str.casefold)
    ids.extend(group.child(i).data(0,Qt.UserRole) for i in range(group.childCount()))
assert len(ids)==len(set(ids))==len(ImageHandler().operation_definitions())
picker.search.setText('mirror');assert picker.operation_id=='image.flip'
QApplication.sendEvent(picker.search,QKeyEvent(QEvent.KeyPress,Qt.Key_Down,Qt.NoModifier));app.processEvents()
assert picker.tree.hasFocus()
picker.choose();assert picker.result()==QDialog.Accepted
w.add_step('image.convert');r=len(w.recipe['steps'])-1
w.parameter(r,'format','jp2');w.parameter(r,'jp2_mode','lossy');w.parameter(r,'quality',71)
w.reset_step_defaults();assert w.recipe['steps'][r]['format']=='jpeg' and w.recipe['steps'][r]['quality']==90
w.close()
''')

    def test_async_additions_keep_gui_responsive_and_reject_stale_results(self):
        from test_recipe_workflow import WAIT
        self.run_gui('''
import threading,time,subprocess
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtWidgets import QApplication
from kim_recipe_core import builtins,config_path
from kim_recipe_run import RunRecipeDialog
import kim_recipe_image
app=QApplication([])
'''+WAIT+'''
base=config_path().parent;base.mkdir(parents=True,exist_ok=True)
a=base/'one.jpg';b=base/'two.psd'
for path in (a,b):subprocess.run(['magick','-size','30x20','xc:red',str(path)],check=True)
w=RunRecipeDialog(builtins()[0],[]);ticks=[]
timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(1));timer.start()
inspect=kim_recipe_image.inspect
entered=threading.Event();release=threading.Event()
def slow(path): entered.set();release.wait(5);return inspect(path)
with patch('kim_recipe_image.inspect',side_effect=slow):
    w.add_files([str(b)])
    assert not w.files and not w.run_button.isEnabled()
    loop=QEventLoop();QTimer.singleShot(120,loop.quit);loop.exec()
    assert entered.is_set() and len(ticks)>2
    w.replace_files([]);release.set();settle(w)
    assert not w.files and not w.rows and not w.run_button.isEnabled()
w.add_files([str(a)]);w.add_files([str(b)]);settle(w)
assert w.files==[str(a),str(b)] and w.run_button.isEnabled()
c=base/'three.png';subprocess.run(['magick','-size','30x20','xc:red',str(c)],check=True)
with patch('kim_recipe_image.inspect',side_effect=RuntimeError('decoder problem')), patch('kim_recipe_run.QMessageBox.warning') as warning:
    w.add_files([str(c)]);settle(w)
    assert warning.called and 'Image inspection failed' in warning.call_args.args[2]
    assert w.files==[str(a),str(b)]
w.start_preflight();settle(w);assert w.run_button.isEnabled()
w.reject();timer.stop()
''')


class PublicationProgressExpansionTests(unittest.TestCase):
    def fixture(self,action):
        import test_album_progress as album
        f=album.AlbumProgressTests('test_progress_opens_before_psd_decode_and_source_inspection')
        f.setUp();self.addCleanup(f.doCleanups)
        code=f.probe.read_text()
        code=code.replace("'render' if tool=='magick' and args and args[0]=='montage'", "'render' if tool=='magick' and args and (args[0]=='montage' or (args[0]=='--' and args[-1].endswith(('.gif','.tiff'))))")
        f.probe.write_text(code)
        extension={'contactsheet':'pdf','print':'pdf','tiffjoin':'tiff','animate':'gif'}[action]
        f.output=f.w.path('out/result.'+extension)
        files=[str(f.psd),str(f.jpg)]
        if action=='contactsheet': args=[action,'--dpi','150','--output',str(f.output),'--',*files]
        elif action=='print':
            f.w.respond_to('kdialog','Kim - Select print layout:',{'stdout':'1\n'})
            f.w.respond_to('kdialog','--getsavefilename',{'stdout':str(f.output)+'\n'})
            args=[action,str(f.w.root),*files]
        elif action=='animate': args=[action,'--delay','25','--loop','0','--output',str(f.output),'--',*files]
        else: args=[action,'--output',str(f.output),'--',*files]
        return f,args

    def start(self,f,args):
        f.process=subprocess.Popen([str(f.w.dispatcher),*args],cwd=f.w.root,env=f.w.env,
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)

    def test_each_existing_action_opens_early_and_publishes_valid_output(self):
        for action in ('contactsheet','print','tiffjoin','animate'):
            with self.subTest(action=action):
                f,args=self.fixture(action);self.start(f,args);f.finish()
                self.assertTrue(f.output.is_file())
                self.assertTrue(all(e['progress_open'] for e in f.events()))
                labels=[c['argv'][-1] for c in f.calls() if c['tool']=='qdbus' and 'setLabelText' in c['argv']]
                self.assertTrue(any('2 / 2:' in label for label in labels))
                self.assertTrue(any('Verifying' in label for label in labels))
                self.assertTrue(any('Publishing' in label for label in labels))
                if action in ('animate','tiffjoin'):
                    self.assertEqual(subprocess.run(['magick','identify','-format','%n\n',str(f.output)],capture_output=True,check=True).stdout.splitlines(),[b'2',b'2'])

    def test_each_existing_action_cancels_owned_rendering_without_publication(self):
        for action in ('contactsheet','print','tiffjoin','animate'):
            with self.subTest(action=action):
                f,args=self.fixture(action);f.w.env['ALBUM_HOLD_STAGE']='render'
                self.start(f,args);f.wait_for_stage()
                f.w.respond_to('qdbus','wasCancelled',{'stdout':'true\n'})
                f.finish(False);f.assert_child_gone();self.assertFalse(f.output.exists())
