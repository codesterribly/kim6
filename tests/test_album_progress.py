"""Real PDF album pipeline with desktop feedback and owned-child probes."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import unittest

from support import Workspace

ROOT = Path(__file__).resolve().parents[1]
NOTE = ('Originals are never overwritten. KIM6 saves new files and adds a number when names collide, '
        'so nothing gets clobbered. Finished results stay put if you cancel or something fails.')

CODEC_PROBE = r'''
import json, os, signal, subprocess, sys, time
from pathlib import Path
control = Path(os.environ['ALBUM_CONTROL'])
tool = Path(sys.argv[0]).name
args = sys.argv[1:]
calls = [json.loads(line) for line in (control/'calls.jsonl').read_text().splitlines()]
opens = [c['argv'] for c in calls if c['tool']=='kdialog' and '--progressbar' in c['argv']]
labels = [c['argv'][-1] for c in calls if c['tool']=='qdbus' and 'setLabelText' in c['argv']]
maxima = [int(c['argv'][-1]) for c in calls if c['tool']=='qdbus' and c['argv'][-2]=='maximum']
record = {'tool':tool,'args':args,'pid':os.getpid(),'label':labels[-1] if labels else '',
          'maximum':maxima[-1] if maxima else int(opens[-1][-1]) if opens else None,
          'progress_open':any(c['tool']=='kdialog' and '--progressbar' in c['argv'] for c in calls)}
with (control/'album-events.jsonl').open('a') as log: log.write(json.dumps(record)+'\n')
stage = ('render' if tool=='magick' and args and args[0]=='montage' else
         'prepare' if tool=='magick' and 'psd:-[0]' in args else
         'verify' if tool=='identify' and any(a.endswith('.pdf') for a in args) else '')
if stage and os.environ.get('ALBUM_FAIL_STAGE')==stage: sys.exit(17)
if stage=='render' and os.environ.get('ALBUM_INVALID_PDF'):
    Path(args[-1]).write_bytes(b'invalid PDF'); sys.exit(0)
if stage and os.environ.get('ALBUM_HOLD_STAGE')==stage:
    child=subprocess.Popen(['/bin/sleep','60'])
    (control/'owned-child').write_text(str(child.pid))
    (control/'held-stage').write_text(stage)
    def stopped(*_):
        child.terminate()
        child.wait(timeout=3)
        sys.exit(143)
    signal.signal(signal.SIGTERM,stopped)
    while not (control/'release-stage').exists(): time.sleep(.05)
    child.terminate(); child.wait()
os.execv(json.loads(os.environ['ALBUM_REAL_TOOLS'])[tool], [tool,*args])
'''


class AlbumProgressTests(unittest.TestCase):
    def setUp(self):
        required = ('magick','identify','exiftool','pdfinfo','setsid')
        self.real = {tool:shutil.which(tool) for tool in required}
        if not all(self.real.values()): self.skipTest('ImageMagick, ExifTool, PDF tools and setsid required')
        self.w=Workspace(); self.addCleanup(self.w.close)
        self.w.env.update(KIM_POLICY='create',KIM6_CREATE_PICK_MORE='0',MAGICK_THREAD_LIMIT='1',
                          ALBUM_CONTROL=str(self.w.control),ALBUM_REAL_TOOLS=json.dumps(self.real))
        self.w.env['PATH'] += os.pathsep+os.defpath
        self.probe = self.w.control/'album-codec.py'
        self.probe.write_text('#!'+sys.executable+'\n'+CODEC_PROBE); self.probe.chmod(0o700)
        for tool in ('magick','identify','exiftool'):
            (self.w.bin/tool).unlink(); (self.w.bin/tool).symlink_to(self.probe)
        (self.w.bin/'setsid').unlink(); (self.w.bin/'setsid').symlink_to(self.real['setsid'])
        self.w.path('out').mkdir(); self.w.path('in').mkdir()
        self.jpg=self.w.path('in/photo 雪.jpg'); self.psd=self.w.path('in/layered.psd')
        self.encode('-size','32x24','xc:red',self.jpg)
        self.encode('-size','32x24','xc:red','-size','32x24','xc:blue',self.psd)
        self.output=self.w.path('out/album.pdf')
        self.w.env['ALBUM_OUTPUT']=str(self.output)
        (self.w.control/'kim_album_dialog.py').write_text(
            "import os,sys\nopen(sys.argv[1],'wb').write(('1\\0'+os.environ['ALBUM_OUTPUT']+'\\0').encode())\n")
        self.before=[self.w.observe(p) for p in (self.jpg,self.psd)]
        self.process=None
        self.addCleanup(self.stop_job)

    def encode(self,*args):
        subprocess.run([self.real['magick'],*map(str,args)],check=True,capture_output=True,timeout=10)

    def start(self,files=None):
        self.process=subprocess.Popen([str(self.w.dispatcher),'album',str(self.w.root),
                                       *map(str,files if files is not None else [self.psd,self.jpg])],
                                      env=self.w.env,cwd=self.w.root,stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE,start_new_session=True)

    def finish(self,success=True,closed=True):
        stdout,stderr=self.process.communicate(timeout=30)
        if success: self.assertEqual(self.process.returncode,0,stderr.decode())
        else: self.assertNotEqual(self.process.returncode,0,stderr.decode())
        self.assertEqual([self.w.observe(p) for p in (self.jpg,self.psd)],self.before)
        self.assertFalse(list(self.w.root.rglob('.kim6-stage.*')))
        self.assertEqual(list((self.w.control/'tmp').iterdir()),[])
        if closed: self.assertTrue(any(c['tool']=='qdbus' and c['argv'][-1]=='close' for c in self.calls()))
        return stdout,stderr

    def stop_job(self):
        if self.process is not None and self.process.poll() is None:
            # Let the real EXIT/signal cleanup stop its separately owned codec
            # group first. Never signal an already reaped/reusable job PID.
            self.process.terminate()
            try:
                self.process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.process.pid,signal.SIGKILL)
                self.process.communicate()

    def calls(self):
        return [json.loads(line) for line in self.w.log.read_text().splitlines()]

    def events(self):
        path=self.w.control/'album-events.jsonl'
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_progress_opens_before_psd_decode_and_source_inspection(self):
        self.start(); self.finish()
        self.assertTrue(self.events())
        self.assertTrue(all(e['progress_open'] for e in self.events()),
                        'Source inspection / PSD decoding ran before any progress window existed')

    def assert_pdf(self,path=None,pages=2):
        info=subprocess.run([self.real['pdfinfo'],str(path or self.output)],check=True,capture_output=True,text=True).stdout
        self.assertIn('Pages:           '+str(pages),info)
        self.assertIn('595 x 842',info)

    def wait_for_stage(self):
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            if (self.w.control/'held-stage').exists(): return
            if self.process.poll() is not None: break
            time.sleep(.02)
        self.fail('Owned codec did not enter the held stage: '+repr(self.events()))

    def assert_child_gone(self):
        pid=int((self.w.control/'owned-child').read_text())
        path=Path('/proc')/str(pid)/'stat'
        self.assertTrue(not path.exists() or path.read_text().split()[2]=='Z', 'Owned child survived cancellation')

    def assert_error(self,text):
        self.assertTrue(any(c['tool']=='kdialog' and '--error' in c['argv'] and
                            text in c['argv'][-1] for c in self.calls()),self.calls())

    def test_jpeg_psd_and_mixed_stages_use_real_counts_and_busy_rendering(self):
        for files in ([self.jpg],[self.psd],[self.psd,self.jpg]):
            with self.subTest(inputs=[p.suffix for p in files]):
                self.w.log.write_text(''); (self.w.control/'album-events.jsonl').unlink(missing_ok=True)
                self.output.unlink(missing_ok=True)
                self.start(files); self.finish(); self.assert_pdf(pages=len(files))
                calls=self.calls()
                opened=next(c['argv'] for c in calls if c['tool']=='kdialog' and '--progressbar' in c['argv'])
                self.assertEqual(opened[-1],str(len(files)))
                labels=[c['argv'][-1] for c in calls if c['tool']=='qdbus' and 'setLabelText' in c['argv']]
                positions=[next(i for i,label in enumerate(labels) if stage in label)
                           for stage in ('Preparing PDF output','Rendering PDF','Verifying resulting PDF','Publishing completed PDF')]
                self.assertEqual(positions,sorted(positions))
                for index,source in enumerate(files,1):
                    self.assertTrue(any(f'{index} / {len(files)}: {source.name}' in label for label in labels))
                for event in self.events():
                    if 'montage' in event['args'] or (event['tool']=='identify' and any(a.endswith('.pdf') for a in event['args'])):
                        self.assertEqual(event['maximum'],0,event)
                self.assertFalse(any('percent' in label.casefold() for label in labels))

    def test_slow_render_remains_visible_and_cancellable_then_completes(self):
        self.w.env['ALBUM_HOLD_STAGE']='render'; self.start(); self.wait_for_stage()
        self.assertIsNone(self.process.poll())
        event=next(e for e in self.events() if e['tool']=='magick' and e['args'][0]=='montage')
        self.assertTrue(event['progress_open']); self.assertEqual(event['maximum'],0)
        self.assertIn('Rendering PDF document',event['label'])
        before=len([c for c in self.calls() if 'wasCancelled' in c['argv']])
        time.sleep(.35)
        self.assertGreater(len([c for c in self.calls() if 'wasCancelled' in c['argv']]),before)
        self.assertFalse(self.output.exists())
        (self.w.control/'release-stage').touch(); self.finish(); self.assert_pdf(); self.assert_child_gone()

    def cancel_stage(self,stage,ui_failure=False,signal_job=False):
        unrelated=subprocess.Popen(['/bin/sleep','60'])
        self.addCleanup(lambda: (unrelated.terminate(),unrelated.wait()))
        self.w.env['ALBUM_HOLD_STAGE']=stage; self.start(); self.wait_for_stage()
        started=time.monotonic()
        if signal_job: self.process.send_signal(signal.SIGTERM)
        elif ui_failure: self.w.respond_to('qdbus','wasCancelled',{'status':7})
        else: self.w.respond_to('qdbus','wasCancelled',{'stdout':'true\n'})
        self.finish(False); self.assertLess(time.monotonic()-started,5)
        self.assertFalse(self.output.exists()); self.assert_child_gone()
        self.assertIsNone(unrelated.poll(),'An unrelated process was affected')
        if stage=='prepare': self.assertFalse(any(e['args'] and e['args'][0]=='montage' for e in self.events()))
        if ui_failure: self.assert_error('Cannot check progress cancellation')

    def test_cancel_during_source_preparation_before_rendering(self): self.cancel_stage('prepare')
    def test_cancel_during_rendering_stops_only_owned_group(self): self.cancel_stage('render')
    def test_cancel_during_pdf_verification(self): self.cancel_stage('verify')
    def test_progress_query_failure_stops_owned_renderer(self): self.cancel_stage('render',ui_failure=True)
    def test_signal_during_rendering_cleans_owned_children(self): self.cancel_stage('render',signal_job=True)

    def test_cancel_before_source_work(self):
        self.w.respond_to('qdbus','wasCancelled',{'stdout':'true\n'})
        self.start(); self.finish(False)
        self.assertFalse(self.events()); self.assertFalse(self.output.exists())

    def test_source_render_and_verification_failure_never_publish(self):
        for stage in ('prepare','render','verify'):
            with self.subTest(stage=stage):
                self.w.env['ALBUM_FAIL_STAGE']=stage
                self.start(); self.finish(False)
                self.assertFalse(self.output.exists())
        self.w.env.pop('ALBUM_FAIL_STAGE')
        self.w.env['ALBUM_INVALID_PDF']='1'; self.start(); self.finish(False)
        self.assertFalse(self.output.exists()); self.assert_error('invalid PDF')

    def test_destination_collision_is_numbered(self):
        self.output.write_bytes(b'unrelated destination')
        before=self.w.observe(self.output)
        self.start(); self.finish()
        self.assertEqual(self.w.observe(self.output),before)
        self.assert_pdf(self.output.with_stem('album_1'))

    def test_progress_initialization_failure_stops_before_codecs(self):
        self.w.respond_to('kdialog','--progressbar',{'status':1,'stdout':''})
        self.start(); self.finish(False,closed=False)
        self.assertFalse(self.events()); self.assertFalse(self.output.exists())
        self.assert_error('invalid progress reference')

    def test_busy_range_failure_stops_before_rendering(self):
        self.w.respond_to('qdbus','maximum',{'status':1})
        self.start(); self.finish(False)
        self.assertFalse(any(e['args'] and e['args'][0]=='montage' for e in self.events()))
        self.assert_error('progress range'); self.assertFalse(self.output.exists())

    def test_failed_close_reports_saved_result_and_retries_cleanup(self):
        self.w.respond_to('qdbus','close',[{'status':1},{'status':0}])
        self.start(); self.finish(False); self.assert_pdf()
        self.assert_error('Album saved, but its progress window could not be closed')
        self.assertEqual(len([c for c in self.calls() if c['tool']=='qdbus' and c['argv'][-1]=='close']),2)


class RunNoteTests(unittest.TestCase):
    def test_exact_copy_and_native_qt_wrapping(self):
        import test_recipes
        test_recipes.RecipeGuiTests.run_gui(self,'''
from PySide6.QtWidgets import QApplication,QLabel
from PySide6.QtGui import QFontMetrics
from kim_recipe_run import RunRecipeDialog
from kim_recipe_core import builtins
app=QApplication([])
w=RunRecipeDialog(builtins()[0],[])
note=next(label for label in w.findChildren(QLabel) if label.text()==''' + repr(NOTE) + ''')
assert note.wordWrap() and note.font()==app.font()
w.show(); app.processEvents()
heights=[]
for width in (1120,800):
    w.resize(width,720); app.processEvents()
    required=note.heightForWidth(note.width())
    assert note.height()>=required,(note.height(),required)
    assert note.height()<=4*QFontMetrics(note.font()).lineSpacing()
    assert note.geometry().bottom()<w.height()
    heights.append(required)
assert heights[1]>heights[0],heights
w.grab().save('/tmp/kim6-run-note-verified.png')
w.reject()
''')
