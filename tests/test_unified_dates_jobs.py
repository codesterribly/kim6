"""Date menu, source integrity, real lifecycle and grouped-warning regressions."""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src/bin')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QDate,QTime
from PySide6.QtWidgets import QApplication
import kim_recipe_core as core
import kim_recipe_image as image
from kim_recipe_dates import epoch_ns
from kim_date_tools import resolve
from kim_job import JobStatus,grouped_warnings
from kim_psd_source import WARNING,DIGEST_WARNING,inspection_context
from support import Workspace
import test_recipes as base
from test_recipe_correctness import step

ROOT=Path(__file__).resolve().parents[1]


def wait_qt(app,predicate):
    end=time.monotonic()+10
    while not predicate() and time.monotonic()<end: app.processEvents(); time.sleep(.01)
    if not predicate(): raise AssertionError('Qt worker did not finish')


class DateDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.source=Path(self.tmp.name)/'undated.png'
        subprocess.run(['magick','-size','12x8','xc:red',str(self.source)],check=True)

    def dialog(self,kind):
        from kim_date_dialog import PhotoDateDialog
        d=PhotoDateDialog(kind,[self.source]); wait_qt(self.app,lambda:d.worker is None)
        self.addCleanup(lambda: (d.reject(),self.app.processEvents()))
        return d

    def test_no_invalid_apply_and_direct_set_action(self):
        d=self.dialog('exif-to-file'); self.assertFalse(d.apply.isEnabled())
        self.assertIn('No photo capture date was found',d.details.toPlainText())
        d.fix.click(); wait_qt(self.app,lambda:d.worker is None)
        self.assertEqual(d.kind,'set'); self.assertFalse(d.apply.isEnabled())
        d.capture.date.setDate(QDate(2024,2,29)); wait_qt(self.app,lambda:d.worker is None)
        self.assertTrue(d.apply.isEnabled()); self.assertEqual(d.capture.time.text(),'00:00:00')
        d.capture.time.setTime(QTime(0,0)); d.zone.setCurrentIndex(d.zone.findData('unknown'))
        wait_qt(self.app,lambda:d.worker is None)
        self.assertTrue(d.apply.isEnabled()); self.assertEqual(d.config()['timezone'],'unknown')
        self.assertIn('File Modification Date',d.explanation.text())

    def test_dated_capture_without_offset_needs_explicit_zone_for_file_date(self):
        subprocess.run(['exiftool','-overwrite_original','-DateTimeOriginal=2024:02:29 12:34:56',str(self.source)],capture_output=True,check=True)
        d=self.dialog('exif-to-file'); self.assertFalse(d.apply.isEnabled()); self.assertIn('timezone is unknown',d.details.toPlainText())
        d.zone.setCurrentIndex(d.zone.findData('UTC')); wait_qt(self.app,lambda:d.worker is None); self.assertTrue(d.apply.isEnabled())

    def test_multifile_explicit_and_empty_save_reload(self):
        from kim_date_dialog import PhotoDateDialog
        d=PhotoDateDialog('set',[self.source,self.source]); wait_qt(self.app,lambda:d.worker is None)
        self.assertIn('same entered date',d.explanation.text()); self.assertFalse(d.apply.isEnabled()); d.reject()
        r=base.recipe([step('metadata.set_capture')]); storage=Path(self.tmp.name)/'recipes.json'
        core.save_users([r],storage); saved=core.read_recipes(storage)[0]
        self.assertEqual(saved['steps'][0]['datetime'],''); self.assertEqual(saved['steps'][0]['timezone'],'unknown')
        row=core.preview(saved,[self.source])[0]; self.assertIn('Choose a capture date and time',row.problems[0])

    def test_genuine_apng_is_refused_without_a_date_write(self):
        if not shutil.which('ffmpeg'): self.skipTest('FFmpeg required for genuine APNG fixture')
        animated=self.source.with_name('animated.png')
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=red:s=16x16:r=2','-frames:v','2','-plays','0','-f','apng',str(animated)],check=True,capture_output=True)
        before=(animated.read_bytes(),animated.stat().st_mtime_ns)
        with self.assertRaisesRegex(ValueError,'Animated images are not supported'):
            resolve(animated,dict(kind='set',datetime='2024-02-29 12:34:56',timezone='unknown'))
        self.assertEqual((animated.read_bytes(),animated.stat().st_mtime_ns),before)

    def test_action_dialogs_presets_rename_collisions_and_settings_reset(self):
        from kim_action_dialog import ActionDialog
        r=ActionDialog('rotate',[self.source]); r.rotation.buttons['90° Left'].click(); r.refresh(); self.assertEqual(r.values,['-90']); r.reject()
        with patch.dict(os.environ,KIM_COPYRIGHT_CREATOR='Settings Creator'):
            d=ActionDialog('copyright',[self.source]); wait_qt(self.app,lambda:d.worker is None); self.assertEqual(d.fields['creator'].text(),'Settings Creator')
            d.fields['creator'].setText('Override'); d.reset_setting('creator'); self.assertEqual(d.fields['creator'].text(),'Settings Creator'); d.reject()
        d=ActionDialog('rename',[self.source]); wait_qt(self.app,lambda:d.worker is None)
        d.fields['value'].setText('photo_'); (self.source.parent/'photo_001.png').write_bytes(b'occupied'); d.refresh()
        self.assertEqual(d.rename_table.item(0,1).text(),'photo_002.png'); d.reject()
        d=ActionDialog('resize',[self.source]); wait_qt(self.app,lambda:d.worker is None)
        # Geometry completion can schedule the current value; wait for Apply.
        wait_qt(self.app,lambda:d.worker is None and d.apply.isEnabled())
        self.assertIn('12 × 8 → 12 × 8',d.preview.toPlainText()); self.assertEqual(d.values,['1600x1600>']); d.reject()


class DateExecutionTests(unittest.TestCase):
    def setUp(self):
        self.w=Workspace(); self.addCleanup(self.w.close)
        # Real codecs/metadata with only KDialog/D-Bus replaced. No source write
        # is authorized by this harness unless a test explicitly chooses policy.
        for name in ('python3','magick','identify','exiftool','stat'):
            path=self.w.bin/name
            if path.exists(): path.unlink()
            path.symlink_to(sys.executable if name=='python3' else shutil.which(name))
        self.w.use_real_metadata_tools()
        self.w.env['PATH']+=os.pathsep+os.defpath; self.w.env['KIM_POLICY']='create'
        self.source=self.w.path('input/photo.png'); self.source.parent.mkdir()
        subprocess.run(['magick','-size','12x8','gradient:red-blue','-profile','/usr/share/color/icc/sRGB.icc',str(self.source)],check=True)
        os.utime(self.source,ns=(1700000000000000001,1700000000123456789)); self.before=self.w.observe(self.source)

    def dispatch(self,*args):
        result=subprocess.run([str(self.w.dispatcher),*map(str,args)],env=self.w.env,cwd=self.w.root,capture_output=True,text=True,timeout=40)
        return result

    def test_set_multifile_date_preserves_source_pixels_icc_and_nanos(self):
        other=self.w.path('input/other.jpg'); subprocess.run(['magick',str(self.source),str(other)],check=True)
        result=self.dispatch('capturedate','--datetime','2024-02-29 12:34:56.123456789','--timezone','unknown','--',self.source,other)
        self.assertEqual(result.returncode,0,result.stderr); outputs=[self.source.with_name('photo_dated.png'),other.with_name('other_dated.jpg')]
        for path in outputs:
            self.assertTrue(path.is_file()); capture,fraction,fmt=__import__('kim_date_tools').source_date(path)
            self.assertIsNone(capture.tzinfo); self.assertEqual(fraction,'')
            self.assertEqual(path.stat().st_mtime_ns,1700000000123456789 if path.suffix=='.png' else other.stat().st_mtime_ns)
        self.assertEqual(self.w.observe(self.source),self.before)
        profile=lambda p:subprocess.check_output(['exiftool','-b','-ICC_Profile',str(p)])
        self.assertEqual(profile(self.source),profile(outputs[0]))
        calls=[json.loads(l) for l in self.w.log.read_text().splitlines()]
        labels=[c['argv'][-1] for c in calls if c['tool']=='qdbus' and 'setLabelText' in c['argv']]
        self.assertTrue(any('file 2 of 2' in label for label in labels)); self.assertTrue(any('Updating metadata' in label for label in labels))

    def test_contextual_rename_parameters_publish_numbered_copies_and_date_styles(self):
        for method,value,name in [('addprefix','photo_','photo_photo.png'),('addsuffix','_photo','photo_photo.png')]:
            occupied=self.source.with_name(name); occupied.write_bytes(b'occupied')
            result=self.dispatch('rename',method,'--parameters',value,'','1','3','--',self.source)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(occupied.read_bytes(),b'occupied')
            outputs=list(self.source.parent.glob('photo_photo_*.png'))
            self.assertTrue(outputs)
            for output in outputs:
                self.assertEqual(output.read_bytes(),self.source.read_bytes())
                self.assertEqual(output.stat().st_mtime_ns,self.before.mtime_ns)
            self.assertEqual(self.w.observe(self.source),self.before)
        result=self.dispatch('capturedate','--datetime','2024-02-29 12:34:56','--timezone','unknown','--',self.source)
        self.assertEqual(result.returncode,0,result.stderr)
        dated=self.source.with_name('photo_dated.png'); before=self.w.observe(dated)
        result=self.dispatch('rename','exifdate','--parameters','iso','','1','3','--',dated)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertTrue(dated.with_name('2024-02-29_12-34-56.png').exists())
        self.assertEqual(self.w.observe(dated),before)

    def test_standalone_copyright_webp_uses_supported_fields(self):
        self.w.env['KIM_JPEG_WEBP_ENGINE']='native'
        source=self.w.path('input/web.webp');subprocess.run(['magick',str(self.source),str(source)],check=True)
        planned=resolve(source,dict(kind='set',datetime='2024-02-29 12:34:56',timezone='unknown'))
        self.assertFalse(any(arg.startswith('-IPTC:') for arg in planned['args']))
        result=self.dispatch('copyright','--creator','Photographer','--notice','Copyright Example','--',source)
        self.assertEqual(result.returncode,0,result.stderr)
        output=source.with_name('web_copyright.webp');self.assertTrue(output.exists())
        tags=subprocess.check_output(['exiftool','-s3','-EXIF:Artist','-XMP-dc:Creator','-IPTC:all',str(output)]).decode().splitlines()
        self.assertEqual(tags,['Photographer','Photographer'])

    def test_missing_date_fails_before_policy_without_affirmative(self):
        result=self.dispatch('capturedate','--mode','exif-to-file','--',self.source)
        self.assertNotEqual(result.returncode,0); self.assertEqual(self.w.observe(self.source),self.before)
        calls=[json.loads(l) for l in self.w.log.read_text().splitlines()]
        self.assertFalse(any('--yesno' in c['argv'] or '--warningyesno' in c['argv'] or '--radiolist' in c['argv'] for c in calls))

    def test_file_date_and_capture_date_directions_do_not_guess_zone(self):
        with self.assertRaisesRegex(ValueError,'Choose'): resolve(self.source,dict(kind='file-to-exif',timezone='unknown'))
        result=self.dispatch('capturedate','--mode','file-to-exif','--timezone','+05:30','--',self.source)
        self.assertEqual(result.returncode,0,result.stderr); output=self.source.with_name('photo_dated.png')
        capture,fraction,_=__import__('kim_date_tools').source_date(output)
        self.assertEqual(epoch_ns(capture,fraction),self.before.mtime_ns)
        result=self.dispatch('capturedate','--mode','exif-to-file','--',output)
        self.assertEqual(result.returncode,0,result.stderr)
        dated=output.with_name('photo_dated_dated.png'); self.assertEqual(dated.stat().st_mtime_ns,self.before.mtime_ns)
        self.assertEqual(hashlib.sha256(output.read_bytes()).digest(),hashlib.sha256(dated.read_bytes()).digest())

    def test_no_publication_after_midfile_cancel(self):
        self.w.respond_to('qdbus','wasCancelled',[{'stdout':'false\n'}]*3+[{'stdout':'true\n'}])
        result=self.dispatch('capturedate','--datetime','2024-01-01 12:00:00','--timezone','UTC','--',self.source)
        self.assertFalse(self.source.with_name('photo_dated.png').exists()); self.assertEqual(self.w.observe(self.source),self.before)
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))


class JobTests(unittest.TestCase):
    def test_counts_and_source_warning_categories(self):
        status=JobStatus('Convert',3); status.start('/tmp/photo.png',2); status.stage='Encoding image';status.finish({'ok':True});status.finish({'ok':False})
        self.assertEqual(status.counts(),(1,1,0,0,1));self.assertIn('file 2 of 3',status.label()); status.cancelling=True; self.assertIn('Cancelling current operation',status.label())
        rows=[core.PreviewRow('/tmp/a.psd',warnings=[WARNING,DIGEST_WARNING]),core.PreviewRow('/tmp/a.psd',warnings=[WARNING,DIGEST_WARNING]),core.PreviewRow('/tmp/b.psd',warnings=[WARNING]),core.PreviewRow('/tmp/c.png')]
        groups=grouped_warnings(rows); self.assertEqual(len(groups),2); self.assertTrue(groups[0][0].startswith('2 PSD'));self.assertTrue(groups[1][0].startswith('1 source'))
        self.assertEqual(groups[1][1].count('/tmp/a.psd'),1); self.assertNotIn('Unprofiled',WARNING)

    def test_warning_disclosure_collapses_and_copies(self):
        app=QApplication.instance() or QApplication([])
        from kim_recipe_run import WarningView,JobProgressDialog
        view=WarningView(); view.set_rows([core.PreviewRow('/tmp/a.psd',warnings=[WARNING])]);view.show();app.processEvents()
        self.assertTrue(view.details.isHidden()); view.expand.click(); self.assertFalse(view.details.isHidden());view.copy.click();self.assertIn('/tmp/a.psd',app.clipboard().text());view.close()
        d=JobProgressDialog('Running','Cancel All',0,2);cancelled=[];d.canceled.connect(lambda:cancelled.append(True));d.show();d.close();app.processEvents()
        self.assertTrue(cancelled);self.assertTrue(d.isVisible());d.complete();self.assertFalse(d.isVisible())

    def test_recipe_cancel_at_publication_keeps_first_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'image.png';subprocess.run(['magick','-size','12x8','xc:red',str(source)],check=True)
            cancel=threading.Event(); stages=[]; successful=core.execute(base.recipe([step('image.rotate')]),[source])[0];self.assertTrue(successful['ok'])
            def stage(message):
                stages.append(message)
                if message=='Writing / publishing output': cancel.set()
            with inspection_context(stage,cancel.is_set): results=core.execute(base.recipe([step('image.rotate')]),[source,source])
            self.assertEqual(len(results),1);self.assertTrue(results[0]['cancelled']);self.assertTrue(Path(successful['output']).exists())
            self.assertEqual(len(list(Path(tmp).glob('*recipe*.png'))),1);self.assertFalse(list(Path(tmp).glob('.kim6-stage.*')))

    def test_owned_process_cancel_and_dialog_disappearance(self):
        for vanished in (False,True):
            with self.subTest(vanished=vanished),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);(root/'job.ref').write_text('org.kde.test /ProgressDialog');(root/'job.label').write_text('Convert — file 1 of 2: photo.psd')
                bus=root/'qdbus';bus.write_text('#!'+sys.executable+'\nimport sys\nfrom pathlib import Path\np=Path(__file__).parent\nif "wasCancelled" in sys.argv:\n if (p/"cancel").exists():\n  '+('sys.exit(1)' if vanished else 'print("true")')+'\n else: print("false")\n') ;bus.chmod(0o700)
                command=[sys.executable,'-c','import os,time;from pathlib import Path;Path('+repr(str(root/'pid'))+').write_text(str(os.getpid()));time.sleep(30)']
                env=dict(os.environ,PATH=str(root)+os.pathsep+os.defpath)
                job=subprocess.Popen([sys.executable,str(ROOT/'src/bin/kim_job_process.py'),str(root),*command],env=env)
                end=time.monotonic()+5
                while not (root/'pid').exists() and time.monotonic()<end:time.sleep(.01)
                self.assertTrue((root/'pid').exists());pid=int((root/'pid').read_text());(root/'cancel').touch()
                self.assertEqual(job.wait(timeout=5),130);self.assertTrue((root/'job.cancelled').exists())
                with self.assertRaises(ProcessLookupError):os.kill(pid,0)

    def test_filesystem_timestamp_precision_loss_is_refused_before_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'image.png';subprocess.run(['magick','-size','12x8','xc:red',str(source)],check=True)
            before=(source.read_bytes(),source.stat().st_mtime_ns); real=os.utime
            def clamped(path,*args,**kw):
                if Path(path).name.startswith('output.') and 'ns' in kw: kw['ns']=(kw['ns'][0],1000000000)
                return real(path,*args,**kw)
            with patch.object(image.os,'utime',side_effect=clamped):
                result=core.execute(base.recipe([{'op':'file.preserve_date'}]),[source])[0]
            self.assertFalse(result['ok']);self.assertIn('filesystem cannot store',result['error'])
            self.assertEqual((source.read_bytes(),source.stat().st_mtime_ns),before)
            self.assertEqual(list(Path(tmp).glob('*recipe*')),[])

    def test_rotation_pixels_direction_and_recipe_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'pattern.png';subprocess.run(['magick','-size','3x2','xc:black','-fill','red','-draw','point 0,0',str(source)],check=True)
            for angle,point in [(-90,'0,2'),(90,'1,0'),(180,'2,1')]:
                r=base.recipe([step('image.rotate',degrees=angle)]);self.assertEqual(core.validate(json.loads(json.dumps(r))),r)
                result=core.execute(r,[source])[0];self.assertTrue(result['ok'],result)
                pixel=subprocess.check_output(['magick',result['output'],'-format','%[pixel:p{'+point+'}]','info:'])
                self.assertIn(pixel,(b'srgb(255,0,0)',b'srgb(100%,0%,0%)'))


if __name__=='__main__':unittest.main()
