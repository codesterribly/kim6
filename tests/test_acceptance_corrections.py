"""Focused final acceptance interactions; real codecs, isolated files and Qt UI."""
import copy
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'src/bin')]
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import QDate, QTime, QTimer, Qt, QEvent
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QFileDialog, QLineEdit, QCalendarWidget
import kim_recipe_core as core
import kim_recipe_image as image
import kim_recipe_run as run
from kim_process import inspection_context, stage, run_process
from kim_ui import CaptureDateInput, CaptureDateOptions
from kim_date_dialog import PhotoDateDialog
from kim_date_tools import resolve, source_date
from kim_action_dialog import ActionDialog
from test_recipe_correctness import step
from test_recipes import recipe


def wait(app, predicate, timeout=15):
    until = time.monotonic() + timeout
    while not predicate() and time.monotonic() < until:
        app.processEvents(); time.sleep(.005)
    app.processEvents()
    if not predicate(): raise AssertionError('Qt work did not finish')


class AcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.environment = patch.dict(os.environ, XDG_CONFIG_HOME=str(self.root/'config'))
        self.environment.start(); self.addCleanup(self.environment.stop)
        self.source = self.root/'picture.png'
        subprocess.run(['magick','-size','12x8','gradient:red-blue',str(self.source)],check=True)
        os.utime(self.source,ns=(1700000000000000001,1700000000123456789))
        self.original = (self.source.read_bytes(),self.source.stat().st_mtime_ns)

    def test_calendar_selection_enables_apply_without_touching_time(self):
        d=PhotoDateDialog('set',[self.source,self.source]); d.show()
        wait(self.app,lambda:d.worker is None)
        self.assertFalse(d.apply.isEnabled()); self.assertEqual(d.capture.value(),'')
        self.assertEqual(d.config()['timezone'],'unknown'); self.assertFalse(d.advanced.content.isVisible())
        self.assertIn('same entered date',d.explanation.text())
        d.capture.date.open_calendar(); self.app.processEvents()
        calendar=d.capture.date.calendarWidget(); today=QDate.currentDate()
        self.assertEqual((calendar.yearShown(),calendar.monthShown()),(today.year(),today.month()))
        calendar.showPreviousMonth(); self.assertEqual(d.capture.value(),'')
        calendar.setCurrentPage(2024,2)
        # Keyboard activation exercises the real calendar editor, with no time edit.
        calendar.setSelectionMode(QCalendarWidget.SingleSelection); calendar.setSelectedDate(QDate(2024,2,29))
        QApplication.sendEvent(calendar.focusProxy(),QKeyEvent(QEvent.KeyPress,Qt.Key_Return,Qt.NoModifier))
        wait(self.app,lambda:d.worker is None)
        self.assertEqual(d.capture.value(),'2024-02-29 00:00:00')
        self.assertTrue(d.apply.isEnabled()); self.assertIn('00:00:00',d.details.toPlainText())
        self.assertFalse(hasattr(d.capture,'fraction')); self.assertFalse(hasattr(d.capture,'time_supplied'))
        d.capture.date.clear(); wait(self.app,lambda:d.worker is None)
        self.assertFalse(d.apply.isEnabled()); d.reject()

    def test_advanced_timezone_only_exposes_relevant_offset(self):
        w=CaptureDateOptions(); w.show(); self.app.processEvents()
        self.assertFalse(w.content.isVisible()); self.assertEqual(w.zone_value(),'unknown')
        w.toggle.click(); self.assertTrue(w.content.isVisible()); self.assertFalse(w.offset.isVisible())
        w.zone.setCurrentIndex(w.zone.findData('custom')); self.assertTrue(w.offset.isVisible())
        w.offset.setText('+05:30'); self.assertEqual(w.zone_value(),'+05:30')
        w.zone.setCurrentIndex(w.zone.findData('UTC')); self.assertFalse(w.offset.isVisible())
        self.assertEqual(w.zone_value(),'UTC'); w.close()

    def test_recipe_uses_same_date_widget_and_midnight_survives_reload(self):
        from kim_recipe_dialog import RecipeWidget
        with patch('kim_recipe_dialog.preview',return_value=[]):
            w=RecipeWidget(); w.duplicate(); w.add_step('metadata.set_capture'); w.show()
            date=w.parameter_widgets['datetime']; self.assertIsInstance(date,CaptureDateInput)
            self.assertEqual(w.recipe['steps'][-1]['timezone'],'unknown')
            self.assertFalse(w.capture_options.content.isVisible())
            date.date.setDate(QDate(4,2,29))
            self.assertEqual(w.recipe['steps'][-1]['datetime'],'0004-02-29 00:00:00')
            storage=self.root/'draft.json'; core.save_users([w.recipe],storage)
            restored=core.read_recipes(storage)[0]['steps'][-1]
            self.assertEqual(restored['datetime'],'0004-02-29 00:00:00')
            self.assertEqual(restored['timezone'],'unknown')
            row=w.steps.currentRow(); w.parameter_widgets['mode'].setCurrentIndex(w.parameter_widgets['mode'].findData('embedded'))
            self.assertFalse(date.isVisible())
            w.stop_preview(); wait(self.app,lambda:w.preview_worker is None); w.close()

    def test_explicit_whole_seconds_clear_only_selected_stale_companions(self):
        subprocess.run(['exiftool','-overwrite_original','-DateTimeOriginal=2020:01:02 03:04:05',
            '-SubSecTimeOriginal=123456789','-OffsetTimeOriginal=+02:00',
            '-CreateDate=2019:04:05 06:07:08','-SubSecTimeDigitized=987','-OffsetTimeDigitized=-04:00',
            '-Artist=Keep Creator',str(self.source)],check=True,capture_output=True)
        before=(self.source.read_bytes(),self.source.stat().st_mtime_ns)
        config=dict(kind='set',datetime='2024-02-29 00:00:00',timezone='unknown',fields='capture')
        result=resolve(self.source,config)
        self.assertIn('-EXIF:SubSecTimeOriginal=',result['args']); self.assertIn('-EXIF:OffsetTimeOriginal=',result['args'])
        output=core.execute(recipe([step('metadata.set_capture',datetime=config['datetime'],timezone='unknown'),{'op':'file.preserve_date'}]),[self.source])[0]
        self.assertTrue(output['ok'],output)
        tags=subprocess.check_output(['exiftool','-json','-s','-DateTimeOriginal','-SubSecTimeOriginal','-OffsetTimeOriginal',
            '-CreateDate','-SubSecTimeDigitized','-OffsetTimeDigitized','-Artist',output['output']])
        import json
        tags=json.loads(tags)[0]
        self.assertEqual(tags['DateTimeOriginal'],'2024:02:29 00:00:00'); self.assertNotIn('SubSecTimeOriginal',tags)
        self.assertNotIn('OffsetTimeOriginal',tags); self.assertEqual(str(tags['SubSecTimeDigitized']),'987')
        self.assertEqual(tags['OffsetTimeDigitized'],'-04:00'); self.assertEqual(tags['Artist'],'Keep Creator')
        self.assertEqual(Path(output['output']).stat().st_mtime_ns,before[1])
        self.assertEqual((self.source.read_bytes(),self.source.stat().st_mtime_ns),before)

    def rename_dialog(self):
        d=ActionDialog('rename',[self.source]); d.show(); wait(self.app,lambda:d.worker is None)
        return d

    def test_all_rename_methods_expose_only_applicable_fields(self):
        d=self.rename_dialog()
        expected={'sequential':{'value','start','padding'},'exifdate':{'date_format'},
            'addprefix':{'value'},'addsuffix':{'value'},'overwrite':{'value','replacement'},
            'uppercase':set(),'lowercase':set(),'spacestodash':set(),'spacestounderscore':set(),
            'underscorestospace':set(),'dashestospace':set()}
        for method,visible in expected.items():
            with self.subTest(method=method):
                d.fields['method'].setCurrentIndex(d.fields['method'].findData(method)); self.app.processEvents()
                for key in ('value','replacement','start','padding','date_format'):
                    self.assertEqual(d.fields[key].isVisible(),key in visible,(method,key))
                if method=='exifdate': self.assertIn('Set Photo Capture Date first',d.preview.toPlainText())
                elif method=='overwrite': self.assertFalse(d.apply.isEnabled())
                else: self.assertTrue(d.apply.isEnabled(),d.preview.toPlainText())
        d.reject()

    def test_prefix_suffix_defaults_custom_state_and_collision_table(self):
        d=self.rename_dialog()
        for method,target in (('addprefix','photo_picture.png'),('addsuffix','picture_photo.png')):
            d.fields['method'].setCurrentIndex(d.fields['method'].findData(method))
            self.assertEqual(d.rename_table.item(0,1).text(),target)
        d.fields['value'].setText('CUSTOM'); d.refresh()
        self.assertEqual(d.rename_table.item(0,1).text(),'pictureCUSTOM.png')
        d.fields['method'].setCurrentIndex(d.fields['method'].findData('addprefix')); d.fields['value'].setText('MY')
        d.fields['method'].setCurrentIndex(d.fields['method'].findData('addsuffix'))
        self.assertEqual(d.fields['value'].text(),'CUSTOM')
        (self.root/'pictureCUSTOM.png').write_bytes(b'occupied'); d.refresh()
        self.assertEqual(d.rename_table.item(0,0).text(),'picture.png')
        self.assertEqual(d.rename_table.item(0,1).text(),'pictureCUSTOM_1.png')
        self.assertEqual(d.rename_table.item(0,2).text(),str(self.root)); self.assertFalse(d.rename_table.wordWrap())
        self.assertEqual((self.source.read_bytes(),self.source.stat().st_mtime_ns),self.original); d.reject()

    def test_date_rename_formats_and_method_state(self):
        subprocess.run(['exiftool','-overwrite_original','-DateTimeOriginal=2024:02:29 12:34:56',str(self.source)],check=True,capture_output=True)
        d=self.rename_dialog(); d.fields['method'].setCurrentIndex(d.fields['method'].findData('exifdate'))
        for value,target in [('compact','20240229_123456.png'),('iso','2024-02-29_12-34-56.png'),
                             ('day_first','2024-29-02_12-34-56.png'),('camera','IMG-20240229_123456.png')]:
            d.fields['date_format'].setCurrentIndex(d.fields['date_format'].findData(value)); d.refresh()
            self.assertEqual(d.rename_table.item(0,1).text(),target); self.assertEqual(d.values[2],value)
        d.fields['method'].setCurrentIndex(d.fields['method'].findData('uppercase'))
        d.fields['method'].setCurrentIndex(d.fields['method'].findData('exifdate'))
        self.assertEqual(d.fields['date_format'].currentData(),'camera'); d.reject()

    def test_filters_use_readable_inputs_not_writers(self):
        listing='JPEG* JPEG r-- description\nPNG* PNG rw- description\nPSD* PSD r-- description\nJXL JXL -w- description\nHEIC HEIC rw+ description\nHEIF HEIC rw+ description\n'
        image._input_name_filters.cache_clear()
        try:
            with patch.object(image,'run',return_value=listing) as command:
                filters=image.input_name_filters(); image.input_name_filters(); self.assertEqual(command.call_count,1)
            self.assertTrue(filters[0].startswith('All Supported Images ('))
            self.assertIn('JPEG Images (*.jpg *.jpeg *.jpe *.jfif)',filters)
            self.assertIn('Photoshop Documents (*.psd)',filters); self.assertEqual(filters[-1],'All Files (*)')
            self.assertFalse(any('*.jxl' in f or '*.psb' in f for f in filters))
        finally: image._input_name_filters.cache_clear()

    def test_advertised_input_groups_pass_actual_content_inspection(self):
        import shutil
        filters=' '.join(image.input_name_filters())
        extensions=('jpg','png','webp','avif','tif','heic','heif','bmp','gif','jp2','ppm','pnm')
        for ext in extensions:
            if '*.'+ext not in filters: continue
            with self.subTest(extension=ext):
                path=self.root/('supported.'+ext)
                subprocess.run(['magick','-size','4x2','xc:red',str(path)],check=True,capture_output=True)
                with inspection_context(): info,fmt,width,height=image.inspect(path)
                self.assertEqual((width,height),(4,2))
        jpeg=self.root/'supported.jpg'
        for ext in ('jpeg','jpe','jfif'):
            path=self.root/('alternate.'+ext); shutil.copyfile(jpeg,path)
            self.assertEqual(image.inspect(path)[1],'jpeg')

    def test_real_qfiledialog_filter_switch_preserves_recipe_queue(self):
        with patch('kim_recipe_run.preview',return_value=[core.PreviewRow(str(self.source))]):
            d=run.RunRecipeDialog(recipe(),[str(self.source)]); wait(self.app,lambda:d.preflight_worker is None)
            filters=image.input_name_filters(); calls=[]
            def choose(parent,title,start,filter_text,selected):
                picker=QFileDialog(parent,title,start); picker.setOption(QFileDialog.DontUseNativeDialog)
                picker.setFileMode(QFileDialog.ExistingFiles); picker.setNameFilters(filter_text.split(';;')); picker.selectNameFilter(selected)
                self.assertEqual(picker.nameFilters(),filters); self.assertEqual(picker.selectedNameFilter(),filters[0])
                for f in filters: picker.selectNameFilter(f); self.assertEqual(d.files,[str(self.source)])
                self.assertEqual(picker.fileMode(),QFileDialog.ExistingFiles)
                calls.append(1); picker.reject(); return [],picker.selectedNameFilter()
            with patch.object(QFileDialog,'getOpenFileNames',side_effect=choose): d.pick_files()
            self.assertEqual(calls,[1]); self.assertEqual(d.files,[str(self.source)]); d.reject()

    def test_all_files_filter_does_not_admit_unsupported_content(self):
        unsupported=self.root/'pretend.jpg'; unsupported.write_text('Not an image')
        worker=run.AddFilesWorker([str(unsupported)],[],0); worker.start(); wait(self.app,lambda:worker.isFinished())
        self.assertEqual(worker.accepted,[]); self.assertEqual(len(worker.rejected),1)

    def test_preflight_stages_indices_states_and_responsive_event_loop(self):
        sources=[str(self.source),str(self.root/'large.psd'),str(self.root/'last.png')]; seen=[]; ticks=[]
        def preview(r,files,chosen,start_index):
            for label in ('Reading Photoshop document','Preparing Photoshop composite','Planning output filename'):
                stage(label); run_process([sys.executable,'-c','import time; time.sleep(.07)'])
            return [core.PreviewRow(files[0],str(self.root/(str(start_index)+'.jpg')))]
        with patch('kim_recipe_run.preview',side_effect=preview):
            d=run.RunRecipeDialog(recipe(),sources); d.show()
            timer=QTimer(); timer.setInterval(10)
            def tick():
                ticks.append(1); seen.append((d.summary.text(),[d.inputs.topLevelItem(i).text(1) for i in range(3)]))
            timer.timeout.connect(tick); timer.start()
            wait(self.app,lambda:d.preflight_worker is None); timer.stop()
            self.assertGreater(len(ticks),20)
            self.assertTrue(any('Inspecting 2 of 3: large.psd' in text and 'Preparing Photoshop composite' in text for text,_ in seen))
            self.assertTrue(any(states[0]=='Ready' and states[1].startswith('Inspecting') and states[2]=='Queued' for _,states in seen))
            self.assertEqual([d.inputs.topLevelItem(i).text(1) for i in range(3)],['Ready']*3)
            self.assertTrue(d.run_button.isEnabled()); self.assertFalse(d.preflight_busy.isVisible()); d.reject()

    def test_cancel_stops_owned_process_and_remaining_queue_without_publication(self):
        started=threading.Event(); calls=[]; pidfile=self.root/'pid'
        def preview(r,files,chosen,start_index):
            calls.append(files[0]); stage('Preparing Photoshop composite'); started.set()
            run_process([sys.executable,'-c',f'import os,time; open({str(pidfile)!r},"w").write(str(os.getpid())); time.sleep(20)'])
            return [core.PreviewRow(files[0])]
        with patch('kim_recipe_run.preview',side_effect=preview), patch('kim_recipe_run.execute') as execute:
            d=run.RunRecipeDialog(recipe(),['large.psd','queued.png']); d.show()
            wait(self.app,lambda:started.is_set() and pidfile.exists() and bool(pidfile.read_text()))
            pid=int(pidfile.read_text()); d.cancel_button.click()
            self.assertFalse(d.run_button.isEnabled()); self.assertIn('Cancelling',d.summary.text())
            wait(self.app,lambda:d.preflight_worker is None)
            self.assertEqual(calls,['large.psd']); execute.assert_not_called()
            self.assertEqual(d.inputs.topLevelItem(0).text(1),'Cancelled'); self.assertEqual(d.inputs.topLevelItem(1).text(1),'Skipped')
            with self.assertRaises(ProcessLookupError): os.kill(pid,0)
            self.assertEqual((self.source.read_bytes(),self.source.stat().st_mtime_ns),self.original)
            d.close()

    def test_stale_stages_and_results_do_not_enable_new_preflight(self):
        entered=threading.Event(); release=threading.Event(); calls=[]
        def preview(r,files,chosen,start_index):
            calls.append(files[0])
            if len(calls)==1:
                entered.set(); release.wait(5)
                # Bypass checkpoint deliberately to simulate already queued stale events.
                worker=d.preflight_worker
                worker.stage_changed.emit('OLD STALE STAGE')
            return [core.PreviewRow(files[0],'/tmp/planned.jpg')]
        with patch('kim_recipe_run.preview',side_effect=preview):
            d=run.RunRecipeDialog(recipe(),['old.psd']); wait(self.app,entered.is_set)
            d.replace_files(['new.png']); self.assertFalse(d.run_button.isEnabled()); release.set()
            wait(self.app,lambda:d.preflight_worker is None)
            self.assertEqual(d.files,['new.png']); self.assertEqual(d.rows[0].source,'new.png')
            self.assertNotIn('OLD STALE',d.summary.text()); self.assertTrue(d.run_button.isEnabled()); d.reject()

    def test_exact_recommended_encoder_precedence_and_restoration(self):
        r=recipe([step('image.convert',format='jpeg',quality=90),step('image.compress',preset='recommended'),step('image.rotate',degrees=90)])
        calls=[]; original=image.run
        def trace(args,**kwargs):
            if args[0]=='magick' and args[-1].startswith('JPEG:'): calls.append(args)
            return original(args,**kwargs)
        for enabled,quality in ((True,85),(False,90)):
            r['steps'][1]['enabled']=enabled; calls.clear()
            with patch.object(image,'run',side_effect=trace): result=core.execute(r,[self.source])[0]
            self.assertTrue(result['ok'],result); self.assertEqual(len(calls),1)
            self.assertEqual(subprocess.check_output(['magick','identify','-format','%w %h %[quality]',result['output']]),f'8 12 {quality}'.encode())
        self.assertEqual((self.source.read_bytes(),self.source.stat().st_mtime_ns),self.original)

    @unittest.skipUnless(os.environ.get('KIM_ACCEPT_REAL_PSD') and os.environ.get('KIM6_REAL_PSD_PATH'), 'opt-in real PSD inspection requires KIM6_REAL_PSD_PATH')
    def test_real_psd_queue_reports_stages_with_one_decode_and_source_integrity(self):
        source=Path(os.environ['KIM6_REAL_PSD_PATH'])
        def integrity(): return (hashlib.sha256(source.read_bytes()).hexdigest(),source.stat().st_size,source.stat().st_mtime_ns)
        before=integrity(); seen=[]; decodes=[]
        import kim_psd_source as psd
        command=psd.command
        def trace(args,**kwargs):
            if 'psd:-[0]' in args: decodes.append(1)
            return command(args,**kwargs)
        try:
            with patch.object(psd,'command',side_effect=trace):
                r=recipe([step('image.convert',format='jpeg',quality=85)])
                r['destination']={'mode':'directory','ask':False,'path':str(self.root)}
                d=run.RunRecipeDialog(r,[str(self.source),str(source)])
                d.show(); timer=QTimer(); timer.setInterval(20); timer.timeout.connect(lambda:seen.append(d.summary.text())); timer.start()
                wait(self.app,lambda:d.preflight_worker is None,timeout=180); timer.stop()
                self.assertEqual(len(decodes),1); self.assertFalse(d.rows[1].problems,d.rows[1].problems)
                self.assertTrue(any('Inspecting 2 of 2: '+source.name in text for text in seen))
                self.assertTrue(any('Preparing Photoshop composite' in text for text in seen))
                self.assertTrue(d.run_button.isEnabled()); d.reject()
                print('REAL_PSD_STAGES:',sorted({text.splitlines()[1].split('…')[0] for text in seen if len(text.splitlines())>1}))
        finally:
            self.assertEqual(integrity(),before)
            print('REAL_PSD_INTEGRITY:',before)


if __name__=='__main__': unittest.main()
