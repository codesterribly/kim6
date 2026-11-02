"""Opt-in acceptance using a user-provided, read-only Photoshop PSD fixture.

KIM6_REAL_PSD=1 KIM6_REAL_PSD_PATH=/path/to/fixture.psd PYTHONPATH=src/bin:tests python3 -m unittest test_real_photoshop
Only desktop interaction is adapted. Codecs, metadata and publication are real.
Outputs and a small diagnostic report remain under /tmp for manual inspection.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

import kim_recipe_core as core
import kim_psd_source as psd
from support import Workspace
import test_recipes as base

SOURCE = Path(os.environ['KIM6_REAL_PSD_PATH']) if os.environ.get('KIM6_REAL_PSD_PATH') else None


@unittest.skipUnless(os.environ.get('KIM6_REAL_PSD') == '1' and os.environ.get('KIM6_REAL_PSD_PATH'), 'real-PSD acceptance requires opt-in and KIM6_REAL_PSD_PATH')
class RealPhotoshopTests(unittest.TestCase):
    def cmd(self,*args):
        return subprocess.run(list(map(str,args)),capture_output=True,check=True,timeout=120).stdout

    def assert_metadata_blocks(self,output):
        for tag in ('IPTC','XMP'):
            original = self.cmd('exiftool','-b','-'+tag,SOURCE)
            actual = self.cmd('exiftool','-b','-'+tag,output)
            padded = original + b'\0' * (-len(original) % 4) if tag == 'IPTC' else original
            self.assertTrue(actual in (original,padded),tag + ' content changed beyond TIFF word padding')
        original = json.loads(self.cmd('exiftool','-json','-IPTC:all',SOURCE))[0]
        actual = json.loads(self.cmd('exiftool','-json','-IPTC:all',output))[0]
        original.pop('SourceFile');actual.pop('SourceFile')
        self.assertEqual(original,actual)

    def test_real_standalone_recipe_metadata_dates_and_original_identity(self):
        self.assertTrue(SOURCE.is_file(),str(SOURCE))
        initial = (hashlib.sha256(SOURCE.read_bytes()).hexdigest(),SOURCE.stat().st_mtime_ns,SOURCE.stat().st_size)
        root = Path(tempfile.mkdtemp(prefix='kim6-real-final-'))
        report = {'fixture':str(SOURCE),'before':initial,'outputs':{},'checks':{}}
        print('\nReal Photoshop evidence:',root,flush=True)
        w = Workspace(); self.addCleanup(w.close)
        # File utilities must be real too: the general adapter deliberately
        # refuses access to paths outside its synthetic fixture workspace.
        ui = {'kdialog','qdbus','qdbus6','kreadconfig6','gettext','kmail','thunderbird','xdg-email','xdg-open','okular'}
        for tool in w.tools - ui:
            real = shutil.which(tool)
            if real: (w.bin/tool).unlink(); (w.bin/tool).symlink_to(real)
        w.env['PATH'] += os.pathsep + os.defpath
        w.env.update(KIM_POLICY='create',KIM6_CREATE_PICK_MORE='0',MAGICK_THREAD_LIMIT='2')
        try:
            for fmt in ('jpg','pdf'):
                occupied = root/(SOURCE.stem+'.'+fmt); occupied.write_bytes(b'occupied result')
                args = [str(w.dispatcher),'convert','--format',fmt,'--output-dir',str(root)]
                if fmt == 'pdf': args.append('--strip-metadata')
                result = subprocess.run(args+['--',str(SOURCE)],env=w.env,cwd=w.root,capture_output=True,text=True,timeout=120)
                self.assertEqual(result.returncode,0,result.stderr+w.log.read_text()[-2000:])
                output = root/(SOURCE.stem+'_1.'+fmt)
                self.assertTrue(output.is_file(),str(output))
                self.assertEqual(occupied.read_bytes(),b'occupied result')
                self.assertEqual(self.cmd('magick','identify','-format','%n|%w|%h',output),b'1|6629|1969')
                if fmt == 'pdf':
                    self.assertIn(b'Pages:           1',self.cmd('pdfinfo',output))
                    report['checks']['pdf_images'] = self.cmd('pdfimages','-list',output).decode()
                else:
                    self.assertEqual(self.cmd('exiftool','-b','-ICC_Profile',output),Path(psd.srgb()).read_bytes())
                    self.assert_metadata_blocks(output)
                report['outputs']['standalone_'+fmt] = str(output)
            r = core.builtins()[0]
            r['destination'] = {'mode':'directory','ask':False,'path':str(root)}
            row = core.preview(r,[SOURCE])[0]
            self.assertFalse(row.problems,row.problems)
            self.assertEqual((row.properties['width'],row.properties['height']),(1600,475))
            report['checks']['preview_warnings'] = row.warnings
            for iteration in range(2):
                result = core.execute(r,[SOURCE])[0]; self.assertTrue(result['ok'],result)
                self.assertEqual(self.cmd('magick','identify','-format','%m|%n|%w|%h',result['output']),b'JPEG|1|1600|475')
                stripped = json.loads(self.cmd('exiftool','-json','-EXIF:all','-IPTC:all','-XMP:all','-ICC_Profile:all',result['output']))[0]
                self.assertEqual(set(stripped),{'SourceFile'})
                report['outputs']['web_'+str(iteration)] = result['output']
            self.assertNotEqual(report['outputs']['web_0'],report['outputs']['web_1'])
            r['steps'] = [{'op':'image.convert','format':'jpeg','quality':90}]
            result = core.execute(r,[SOURCE])[0];self.assertTrue(result['ok'],result)
            output = Path(result['output']);report['outputs']['recipe_metadata_kept'] = str(output)
            self.assert_metadata_blocks(output)
            self.assertEqual(self.cmd('exiftool','-b','-ICC_Profile',output),Path(psd.srgb()).read_bytes())
            date = {'op':'metadata.set_capture','mode':'specific','datetime':'2024-02-29 06:07:08.123','timezone':'unknown','fields':'capture'}
            # Keeping a nonstandard Manifest is safe; editing unrelated XMP
            # would force a repair, so it must be an actionable preflight error.
            blocked = core.preview(dict(r,steps=r['steps']+[date]),[SOURCE])[0]
            self.assertIn('Manifest',blocked.problems[0])
            r['steps'] += [{'op':'metadata.strip_all'},date]
            result = core.execute(r,[SOURCE])[0];self.assertTrue(result['ok'],result)
            self.assertEqual(self.cmd('exiftool','-s3','-EXIF:DateTimeOriginal',result['output']).strip(),b'2024:02:29 06:07:08')
            self.assertFalse(self.cmd('exiftool','-s3','-OffsetTimeOriginal','-IPTC:TimeCreated',result['output']).strip())
            report['outputs']['recipe_set_date_after_strip'] = result['output']
            self.assertFalse(list(root.glob('.kim6-stage.*')))
            report['checks']['metadata_preserved_except_required_tiff_iptc_padding'] = True
        finally:
            report['after'] = (hashlib.sha256(SOURCE.read_bytes()).hexdigest(),SOURCE.stat().st_mtime_ns,SOURCE.stat().st_size)
            (root/'acceptance.json').write_text(json.dumps(report,indent=2))
            self.assertEqual(initial,report['after'],'PRIVATE SOURCE CHANGED')

    def test_real_psd_qt_editor_and_run_remain_responsive(self):
        base.RecipeGuiTests.run_gui(self,'''
import time,tempfile,os
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from kim_recipe_dialog import RecipeWidget
from kim_recipe_run import RunRecipeDialog
from kim_recipe_core import builtins
app=QApplication([])
source=os.environ['KIM6_REAL_PSD_PATH']
ticks=[];stages=[]
timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(1));timer.start()
def settle(test):
    end=time.monotonic()+20
    while not test() and time.monotonic()<end:
        app.processEvents();time.sleep(.003)
    assert test(),'PSD worker did not finish'
w=RecipeWidget([source]);w.show()
if w.preview_worker: w.preview_worker.stage_changed.connect(stages.append)
settle(lambda:w.preview_worker is None)
assert len(ticks)>50 and any('composite' in s for s in stages),stages
w.set_examples([source]);w.stop_preview();settle(lambda:w.preview_worker is None)
w.close()
recipe=builtins()[0];recipe['destination']={'mode':'directory','ask':False,'path':tempfile.mkdtemp(prefix='kim6-real-qt-')}
dialog=RunRecipeDialog(recipe,[source]);dialog.show()
settle(lambda:dialog.preflight_worker is None)
assert dialog.run_button.isEnabled() and not dialog.rows[0].problems, (dialog.summary.text(),{i:r.problems for i,r in dialog.rows.items()})
dialog.start_preflight();dialog.invalidate_preflight()
settle(lambda:dialog.preflight_worker is None)
assert not dialog.run_button.isEnabled(),'stale preflight enabled Run'
assert len(ticks)>100
dialog.reject();timer.stop()
''')
