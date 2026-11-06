"""November GUI corrections: measured loading, filename aliases and natural sizing."""
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src/bin')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QApplication,QFileDialog,QLabel,QMessageBox
from shiboken6 import isValid
import kim_recipe_run as run
import kim_recipe_image as image
import kim_recipe_core as core
import kim_recipe_dialog as editor
from kim_job import completion_dialog
from kim_process import inspection_context, run_process


def wait(app,predicate,timeout=15):
    end=time.monotonic()+timeout
    while not predicate() and time.monotonic()<end:
        app.processEvents();time.sleep(.003)
    app.processEvents()
    if not predicate(): raise AssertionError('Qt worker did not finish')


class GuiAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);env=patch.dict(os.environ,XDG_CONFIG_HOME=str(self.root/'config'))
        env.start();self.addCleanup(env.stop)
        self.jpg=self.root/'vacation.jpg';self.psd=self.root/'layered.psd'
        subprocess.run(['magick','-size','8x6','xc:red',str(self.jpg)],check=True)
        subprocess.run(['magick','-size','8x6','xc:red','-size','8x6','xc:blue',str(self.psd)],check=True)
        self.before=[(p.read_bytes(),p.stat().st_mtime_ns) for p in (self.jpg,self.psd)]
        self.windows=[];self.addCleanup(self.close_windows)

    def close_windows(self):
        for w in reversed(self.windows):
            if not isValid(w):continue
            with patch.object(QMessageBox,'question',return_value=QMessageBox.Discard):w.close()
            if isinstance(w,run.RunRecipeDialog):wait(self.app,lambda:w.add_worker is None and w.preflight_worker is None and w.filters_worker is None)
            if isinstance(w,editor.RecipeWidget):wait(self.app,lambda:w.preview_worker is None)
        self.assertEqual([(p.read_bytes(),p.stat().st_mtime_ns) for p in (self.jpg,self.psd)],self.before)

    def recipe(self,pattern='{filename}_recipe'):
        return dict(schema=1,id='test',name='Test',media='image',steps=[{'op':'file.rename_output','pattern':pattern}],destination={'mode':'beside'})

    def window(self,recipe=None,files=()):
        w=run.RunRecipeDialog(recipe,list(map(str,files)));self.windows.append(w);w.show();self.app.processEvents();return w

    def test_slow_cold_format_probe_does_not_block_gui_or_poison_cache_on_cancel(self):
        image._input_name_filters.cache_clear();self.addCleanup(image._input_name_filters.cache_clear)
        main=threading.get_ident();calls=[];ticks=[];real=image.run
        def slow(args,**kw):
            if args==['magick','-list','format']:
                calls.append(threading.get_ident())
                run_process([sys.executable,'-c','import time;time.sleep(.45)'])
            return real(args,**kw)
        w=self.window();timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(time.monotonic()));timer.start()
        with patch.object(image,'run',side_effect=slow),patch.object(QFileDialog,'getOpenFileNames',return_value=([],'')) as picker:
            started=time.monotonic();w.pick_files();self.assertLess(time.monotonic()-started,.1)
            self.assertFalse(w.run_button.isEnabled());wait(self.app,lambda:w.filters_worker is None)
            self.assertTrue(picker.called)
        timer.stop();self.assertGreater(len(ticks),30);self.assertLess(max(b-a for a,b in zip(ticks,ticks[1:])),.15)
        self.assertTrue(calls);self.assertTrue(all(t!=main for t in calls))
        # Cancel a genuinely running owned delegate, then allow a new probe.
        image._input_name_filters.cache_clear();entered=threading.Event();w._input_filters=None
        def held(args,**kw):
            if args==['magick','-list','format']:
                entered.set();run_process([sys.executable,'-c','import time;time.sleep(20)'])
            return real(args,**kw)
        with patch.object(image,'run',side_effect=held),patch.object(QFileDialog,'getOpenFileNames') as picker:
            w.pick_files();wait(self.app,entered.is_set);w.close();wait(self.app,lambda:w.filters_worker is None)
            picker.assert_not_called()
        self.assertEqual(image._input_name_filters.cache_info().currsize,0)

    def test_late_filter_probe_does_not_open_picker_over_recipe_editor(self):
        image._input_name_filters.cache_clear();self.addCleanup(image._input_name_filters.cache_clear)
        w=self.window();real=image.run
        def slow(args,**kw):
            if args==['magick','-list','format']:run_process([sys.executable,'-c','import time;time.sleep(.2)'])
            return real(args,**kw)
        with patch.object(image,'run',side_effect=slow),patch.object(QFileDialog,'getOpenFileNames') as picker:
            w.pick_files();w.create_recipe();self.assertIsNotNone(w.editor_dialog)
            wait(self.app,lambda:w.filters_worker is None);picker.assert_not_called()
            w.editor_dialog.reject();wait(self.app,lambda:w.editor_dialog is None)
            picker.assert_not_called();self.assertFalse(w._pending_picker)

    def test_names_appear_before_slow_admission_and_stale_rows_cannot_return(self):
        w=self.window();entered=threading.Event();release=threading.Event();real=image.inspect;ticks=[]
        def slow(path,*a,**kw): entered.set();release.wait(4);return real(path,*a,**kw)
        timer=QTimer();timer.setInterval(5);timer.timeout.connect(lambda:ticks.append(1));timer.start()
        with patch.object(image,'inspect',side_effect=slow):
            started=time.monotonic();w.add_files([str(self.jpg),str(self.psd)])
            self.assertLess(time.monotonic()-started,.1)
            self.assertEqual(w.inputs.topLevelItemCount(),2)
            self.assertEqual(w.inputs.topLevelItem(0).text(0),'vacation.jpg')
            self.assertFalse(w.run_button.isEnabled());wait(self.app,entered.is_set)
            deadline=time.monotonic()+.12
            wait(self.app,lambda:time.monotonic()>deadline)
            self.assertGreater(len(ticks),10)
            w.replace_files([]);release.set();wait(self.app,lambda:w.add_worker is None)
            self.assertEqual(w.files,[]);self.assertEqual(w.inputs.topLevelItemCount(),0);self.assertFalse(w.run_button.isEnabled())
        timer.stop()

    def test_mixed_admission_preflight_reuses_headers_but_psd_decodes_once(self):
        w=self.window(self.recipe());calls=[];main=threading.get_ident();real=image.inspect_open_path
        import kim_psd_source as psd
        command=psd.command;decodes=[]
        def trace(path,*a,**kw):
            calls.append((os.readlink(path),threading.get_ident()));return real(path,*a,**kw)
        def decode(args,**kw):
            if 'psd:-[0]' in args:decodes.append(1)
            return command(args,**kw)
        with patch.object(image,'inspect_open_path',side_effect=trace),patch.object(psd,'command',side_effect=decode):
            w.add_files([str(self.jpg),str(self.psd)])
            wait(self.app,lambda:w.add_worker is None and w.preflight_worker is None)
        self.assertEqual(sum(path==str(self.jpg) for path,_ in calls),1)
        self.assertTrue(all(t!=main for _,t in calls));self.assertEqual(len(decodes),1)
        self.assertEqual([w.inputs.topLevelItem(i).text(1) for i in range(2)],['Ready','Problem'])
        self.assertTrue(w.fix_recipe_button.isVisible());self.assertFalse(w.run_button.isEnabled())

    def test_header_cache_invalidates_when_mtime_is_restored(self):
        cache={};real=image.inspect_open_path
        with patch.object(image,'inspect_open_path',wraps=real) as inspect, image.checked_input_headers(cache),inspection_context():
            image.inspect(self.jpg);image.inspect(self.jpg);self.assertEqual(inspect.call_count,1)
            stat=self.jpg.stat()
            # A disposable copy exercises ctime invalidation without touching originals.
            copy_path=self.root/'copy.jpg';copy_path.write_bytes(self.jpg.read_bytes())
            image.inspect(copy_path);first=copy_path.stat()
            subprocess.run(['exiftool','-overwrite_original','-Artist=Changed',str(copy_path)],check=True,capture_output=True)
            os.utime(copy_path,ns=(first.st_atime_ns,first.st_mtime_ns));image.inspect(copy_path)
            self.assertEqual(inspect.call_count,3)

    def test_queued_additions_do_not_restart_intermediate_preflight(self):
        w=self.window(self.recipe());entered=threading.Event();release=threading.Event();real=image.inspect
        def slow(path,*a,**kw):
            if str(path)==str(self.jpg):entered.set();release.wait(4)
            return real(path,*a,**kw)
        with patch.object(image,'inspect',side_effect=slow),patch.object(run,'preview',return_value=[core.PreviewRow(str(self.jpg))]) as preview:
            w.add_files([str(self.jpg)]);wait(self.app,entered.is_set)
            w.add_files([str(self.psd)]);self.assertEqual(w.inputs.topLevelItemCount(),2);release.set()
            wait(self.app,lambda:w.add_worker is None and w.preflight_worker is None and not w._addition_queue)
        self.assertEqual(len(preview.call_args_list),2);self.assertEqual(w.files,[str(self.jpg),str(self.psd)])
        self.assertTrue(w.run_button.isEnabled())

    def test_filename_and_legacy_patterns_produce_same_bytes_and_numbered_output(self):
        occupied=self.root/'vacation_recipe.jpg';occupied.write_bytes(b'occupied')
        for token,number in (('filename',1),('stem',2)):
            r=self.recipe('{'+token+'}_recipe');saved=self.root/(token+'.json')
            core.save_users([r],saved);loaded=core.read_recipes(saved)[0]
            self.assertEqual(loaded['steps'][0]['pattern'],r['steps'][0]['pattern'])
            row=core.preview(loaded,[self.jpg])[0];self.assertEqual(Path(row.output).name,f'vacation_recipe_{number}.jpg')
            result=core.execute(loaded,[self.jpg])[0];self.assertTrue(result['ok'],result)
            out=Path(result['output']);self.assertEqual(out.name,f'vacation_recipe_{number}.jpg');self.assertEqual(out.read_bytes(),self.jpg.read_bytes())
        self.assertEqual(occupied.read_bytes(),b'occupied')
        for bad in ('{filename.ext}','{filename!r}','{filename:20}','{unknown}','../{filename}'):
            with self.assertRaises(core.RecipeError):core.pattern(bad)
        for value in ('{filename}_{index}','{stem}_{date}','{{stem}}_{stem}','{{{stem}}}'):
            core.pattern(value)
            self.assertEqual(core.format_output_pattern(value,'vacation'),core.format_output_pattern(core.display_output_pattern(value),'vacation'))

    def test_admission_rejects_same_inode_but_accepts_identical_independent_copy(self):
        hardlink = self.root / 'hardlink.jpg'
        os.link(self.jpg, hardlink)
        independent = self.root / 'independent.jpg'
        independent.write_bytes(self.jpg.read_bytes())
        symlink = self.root / 'symlink.jpg'
        symlink.symlink_to(independent)
        w = self.window()
        with patch.object(QMessageBox, 'warning') as warning:
            w.add_files([str(self.jpg), str(self.jpg), str(hardlink),
                         str(independent), str(symlink)])
            wait(self.app, lambda: w.add_worker is None)
        self.assertEqual(w.files, [str(self.jpg), str(independent)])
        self.assertEqual(w.inputs.topLevelItemCount(), 2)
        self.assertFalse(w.run_button.isEnabled())
        self.assertTrue(all(w.inputs.topLevelItem(i).text(1) == 'Waiting for recipe'
                            for i in range(2)))
        warning.assert_called_once()
        self.assertEqual(warning.call_args.args[2].count('Already in the list'), 3)
        self.assertEqual(independent.read_bytes(), self.before[0][0])
        self.assertTrue(symlink.is_symlink())
        self.assertFalse(list(self.root.rglob('.kim6-stage.*')))

    def test_editor_uses_filename_label_example_and_preserves_legacy_storage(self):
        w=editor.RecipeWidget();self.windows.append(w);w.new();w.show();self.app.processEvents()
        field=w.parameter_widgets['pattern']
        self.assertEqual(field.text(),'{filename}_recipe')
        self.assertEqual(w.form.labelForField(field).text(),'Output filename pattern')
        self.assertEqual(w.filename_example.text(),'Example output: vacation_recipe.jpg')
        w.example_selector.addItem(str(self.jpg),str(self.jpg));w.example_selector.setCurrentIndex(w.example_selector.count()-1)
        field.setText('{filename}_small');self.assertEqual(w.filename_example.text(),'Example output: vacation_small.jpg')
        r=copy.deepcopy(w.recipe);r['steps'][0]['pattern']='{stem}_recipe'
        w.users[w.active_index-len(w.shipped)]=r;w.select(w.active_index,force=True)
        self.assertEqual(w.parameter_widgets['pattern'].text(),'{filename}_recipe')
        self.assertEqual(w.recipe,r)
        self.assertEqual(core.builtins()[0]['steps'][-1]['pattern'],'{filename}_web')

    def test_details_count_and_compact_initial_geometry_repeat_exactly(self):
        d=completion_dialog('PDF Album',['/photos/album.pdf'],[('Photoshop','source.psd\n'+('Technical details\n'*100)),('Color profiles','source.psd\nProfile details')])
        self.windows.append(d);d.show();self.app.processEvents();initial=d.size()
        self.assertFalse(d.isModal());self.assertEqual(d.details_button.text(),'Details (2)')
        self.assertFalse(any('processing notices' in label.text() for label in d.findChildren(QLabel)))
        self.assertFalse(d.details.isVisible());self.assertFalse(d.copy.isVisible())
        for _ in range(3):
            d.details_button.click();self.app.processEvents();self.assertGreater(d.height(),initial.height())
            self.assertGreater(d.details.verticalScrollBar().maximum(),0)
            d.copy.click();self.assertIn('Technical details',self.app.clipboard().text())
            d.details_button.click();self.app.processEvents();self.assertEqual(d.size(),initial)
        self.assertLess(initial.height(),6*QFontMetrics(self.app.font()).lineSpacing()+d.done_button.sizeHint().height())
        d.done_button.click();self.assertFalse(d.isVisible())

    def test_zero_details_and_long_paths_use_natural_wrapping(self):
        for path in ('/photos/album.pdf','/photos/'+'long-album-name-'*20+'.pdf'):
            d=completion_dialog('PDF Album',[path],[]);self.windows.append(d);d.show();self.app.processEvents()
            self.assertFalse(d.details_button.isVisible());self.assertFalse(d.details.isVisible())
            self.assertGreaterEqual(d.saved_label.height(),d.saved_label.heightForWidth(d.saved_label.width()))
            self.assertLessEqual(d.width(),d.screen().availableGeometry().width());self.assertIn(path,d.saved_label.text());d.reject()


if __name__=='__main__':unittest.main()
