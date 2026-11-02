"""Recipe waiting/repair interactions and publication completion advisories."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src/bin'))
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from shiboken6 import isValid
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QMessageBox
import kim_recipe_core as core
import kim_recipe_image as image
import kim_recipe_run as run
import kim_recipe_dialog as editor
import kim_job as job
from kim_psd_source import stage, run_process, WARNING, DIGEST_WARNING
from test_recipe_correctness import step
from test_recipes import recipe


def wait(app,predicate,timeout=20):
    end=time.monotonic()+timeout
    while not predicate() and time.monotonic()<end:
        app.processEvents(); time.sleep(.005)
    app.processEvents()
    if not predicate(): raise AssertionError('Qt did not finish the requested interaction')


class RecipeDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name); self.out=self.root/'out'; self.out.mkdir()
        env=patch.dict(os.environ,XDG_CONFIG_HOME=str(self.root/'config')); env.start(); self.addCleanup(env.stop)
        self.jpg=self.root/'photo.jpg'; self.psd=self.root/'photo.psd'; self.other=self.root/'photo_web.jpg'
        for path in (self.jpg,self.other): self.cmd('magick','-size','8x6','xc:red',path)
        self.cmd('magick','-size','8x6','xc:red','-size','8x6','xc:blue',self.psd)
        self.files=list(map(str,(self.jpg,self.psd,self.other)))
        self.before=[(p.read_bytes(),p.stat().st_mtime_ns) for p in (self.jpg,self.psd,self.other)]
        self.r=recipe([{'op':'file.rename_output','pattern':'{stem}_recipe'}])
        self.r.update(id='user-rename',folder='work')
        self.r['destination']={'mode':'directory','ask':False,'path':str(self.out)}
        core.save_library(core.RecipeLibrary([self.r],[{'id':'work','name':'Work'}]))
        self.dialogs=[]; self.addCleanup(self.close_dialogs)

    def cmd(self,*args): return subprocess.run(list(map(str,args)),check=True,capture_output=True,timeout=30).stdout

    def close_dialogs(self):
        for d in reversed(self.dialogs):
            if not isValid(d): continue  # Parent-editor deletion owns its child Run dialogs.
            with patch.object(QMessageBox,'question',return_value=QMessageBox.Discard): d.reject()
            wait(self.app,lambda:d.preflight_worker is None and d.editor_dialog is None)
            d.close()

    def dialog(self,r=None,files=None):
        d=run.RunRecipeDialog(r,self.files if files is None else files); self.dialogs.append(d); d.show()
        wait(self.app,lambda:d.preflight_worker is None); return d

    def settled(self,d): wait(self.app,lambda:d.editor_dialog is None and d.preflight_worker is None)

    def assert_sources(self):
        self.assertEqual([(p.read_bytes(),p.stat().st_mtime_ns) for p in (self.jpg,self.psd,self.other)],self.before)
        self.assertEqual(list(self.out.iterdir()),[])

    def test_no_recipe_waits_without_inspection_and_file_actions_still_work(self):
        with patch('kim_recipe_run.preview') as preview:
            d=self.dialog()
            self.assertTrue(d.selection_hint.isVisible()); self.assertIn('Choose a recipe to check',d.selection_hint.text())
            self.assertEqual(d.summary.text(),'Waiting for recipe selection')
            self.assertEqual([d.inputs.topLevelItem(i).text(1) for i in range(3)],['Waiting for recipe']*3)
            self.assertFalse(d.preflight_clock.isActive()); self.assertFalse(d.preflight_busy.isVisible())
            self.assertFalse(d.run_button.isEnabled()); self.assertTrue(d.add_photos.isEnabled())
            d.inputs.clearSelection(); d.inputs.topLevelItem(1).setSelected(True); d.remove_files()
            self.assertEqual(d.files,[self.files[0],self.files[2]])
            def confirm_clear():
                box=self.app.activeModalWidget(); self.assertIsInstance(box,QMessageBox)
                box.button(QMessageBox.Yes).click()
            QTimer.singleShot(0,confirm_clear); d.clear_list.click(); self.assertEqual(d.files,[])
            # PSD admission checks its header, without recipe-specific decoding.
            with patch.object(image,'inspect') as inspect:
                d.add_files([str(self.psd)]); wait(self.app,lambda:d.add_worker is None)
                inspect.assert_not_called()
            self.assertEqual(d.inputs.topLevelItem(0).text(1),'Waiting for recipe')
            preview.assert_not_called(); self.assert_sources()

    def test_select_then_clear_recipe_retires_stages_and_results(self):
        entered=threading.Event(); release=threading.Event(); calls=[]
        def preview(r,files,*args,**kw):
            calls.append(files[0]); stage('Reading Photoshop document'); entered.set(); release.wait(5)
            # Deliberately simulate stale, already queued data after cancellation.
            return [core.PreviewRow(files[0],'/old/preview.jpg')]
        with patch('kim_recipe_run.preview',side_effect=preview):
            d=self.dialog(files=[str(self.psd),str(self.other)])
            d.selector.setCurrentIndex(d.selector.findData(self.r['id']))
            wait(self.app,lambda:entered.is_set() and d.preflight_active is not None)
            self.assertIn('Inspecting 1 of 2: photo.psd',d.summary.text())
            self.assertIn('Reading Photoshop document',d.summary.text())
            self.assertEqual(d.inputs.topLevelItem(1).text(1),'Queued')
            self.assertTrue(d.preflight_busy.isVisible()); self.assertTrue(d.preflight_clock.isActive())
            d.selector.setCurrentIndex(-1)
            self.assertIsNone(d.recipe); self.assertFalse(d.run_button.isEnabled())
            self.assertEqual(d.summary.text(),'Waiting for recipe selection')
            self.assertFalse(d.preflight_busy.isVisible()); self.assertFalse(d.preflight_clock.isActive())
            self.assertEqual(d.cancel_button.text(),'Cancel')
            self.assertEqual(d.inputs.topLevelItem(0).text(1),'Waiting for recipe')
            release.set(); wait(self.app,lambda:d.preflight_worker is None)
            self.assertEqual(d.rows,{}); self.assertNotIn('old',d.summary.text())
            self.assertEqual(len(calls),1); self.assertFalse(d.run_button.isEnabled())

    def test_mixed_real_inputs_offer_only_the_specific_psd_repair(self):
        d=self.dialog(self.r)
        self.assertEqual([d.inputs.topLevelItem(i).text(1) for i in range(3)],['Ready','Problem','Ready'])
        self.assertFalse(d.run_button.isEnabled()); self.assertTrue(d.fix_recipe_button.isVisible())
        self.assertEqual(d.rows[1].properties['_repair'],'add_convert_format')
        diagnostic=d.diagnostics.toPlainText()
        self.assertIn('photo.psd',diagnostic); self.assertIn('cannot save new PSD files',diagnostic)
        self.assertIn('Convert Format',diagnostic); self.assertIn('original PSD will remain unchanged',diagnostic)
        self.assertNotIn('explicit supported output format',diagnostic); self.assert_sources()

    def test_cancel_repair_keeps_recipe_files_and_problem(self):
        d=self.dialog(self.r); d.fix_recipe_button.click(); child=d.editor_dialog
        self.assertEqual(child.widget.recipe,self.r); self.assertIn('Convert Format',child.repair_hint.text())
        self.assertTrue(child.isVisible()); self.assertFalse(d.run_button.isEnabled())
        d.open_editor(repair=True); self.assertIs(d.editor_dialog,child)
        child.reject(); self.settled(d)
        self.assertEqual(core.lookup_recipe(self.r['id']),self.r); self.assertEqual(d.files,self.files)
        self.assertTrue(d.fix_recipe_button.isVisible()); self.assertFalse(d.run_button.isEnabled()); self.assert_sources()

    def test_saved_repair_reloads_library_and_preflights_without_publishing(self):
        d=self.dialog(self.r); generation=d.generation
        d.fix_recipe_button.click(); child=d.editor_dialog; w=child.widget
        w.add_step('image.convert'); row=w.steps.currentRow()
        w.parameter_widgets['format'].setCurrentIndex(w.parameter_widgets['format'].findData('png'))
        self.assertTrue(w.save()); child.accept(); self.settled(d)
        self.assertEqual(d.selected_id,self.r['id']); self.assertEqual(d.recipe['folder'],'work')
        self.assertEqual(d.recipe['steps'][0],self.r['steps'][0]); self.assertEqual(d.recipe['steps'][-1]['format'],'png')
        self.assertEqual(d.files,self.files); self.assertGreater(d.generation,generation)
        self.assertTrue(d.run_button.isEnabled(),d.diagnostics.toPlainText())
        self.assertFalse(d.fix_recipe_button.isVisible()); self.assertEqual([x.format for x in d.rows.values()],['png']*3)
        self.assert_sources()

    def test_discarded_unsaved_repair_does_not_save(self):
        d=self.dialog(self.r); d.fix_recipe_button.click(); child=d.editor_dialog
        child.widget.add_step('image.convert')
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Cancel): child.reject()
        self.assertIs(d.editor_dialog,child); self.assertTrue(child.widget.is_dirty())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.Discard): child.reject()
        self.settled(d); self.assertEqual(core.lookup_recipe(self.r['id']),self.r)
        self.assertFalse(d.run_button.isEnabled()); self.assert_sources()

    def test_builtin_repair_requires_explicit_duplicate_and_keeps_original(self):
        shipped=copy.deepcopy(self.r); shipped.pop('folder'); shipped['id']='shipped-rename'
        with patch.object(core,'builtins',return_value=[shipped]), patch.object(run,'builtins',return_value=[shipped]), patch.object(editor,'builtins',return_value=[shipped]):
            d=self.dialog(shipped); d.fix_recipe_button.click(); child=d.editor_dialog; w=child.widget
            self.assertTrue(w.immutable); self.assertFalse(w.management_buttons['Save'].isEnabled())
            w.management_buttons['Duplicate to Edit'].click(); self.assertFalse(w.immutable)
            self.assertNotEqual(w.recipe['id'],shipped['id']); w.add_step('image.convert')
            self.assertTrue(w.save()); new_id=w.recipe['id']; child.accept(); self.settled(d)
            self.assertEqual(core.builtins(),[shipped]); self.assertEqual(d.selected_id,new_id)
            self.assertTrue(d.run_button.isEnabled(),d.diagnostics.toPlainText()); self.assert_sources()

    def test_missing_encoder_is_not_misdiagnosed_as_missing_convert(self):
        r=copy.deepcopy(self.r); r['steps'].append(step('image.convert',format='jxl',quality=90))
        real=image.run
        def no_encoder(args,**kw): return '' if args==['magick','-list','format'] else real(args,**kw)
        with patch.object(image,'run',side_effect=no_encoder): d=self.dialog(r)
        self.assertIn('JXL writer unavailable',d.diagnostics.toPlainText())
        self.assertFalse(d.fix_recipe_button.isVisible()); self.assertTrue(all('_repair' not in row.properties for row in d.rows.values()))
        self.assertFalse(d.run_button.isEnabled()); self.assert_sources()

    def test_invalid_saved_selection_restores_waiting_without_stale_preview(self):
        d=self.dialog(self.r); core.save_library(core.RecipeLibrary([],[]))
        d.select_recipe(d.selector.findData(self.r['id']))
        self.assertIsNone(d.recipe); self.assertEqual(d.summary.text(),'Waiting for recipe selection')
        self.assertIn('Unknown saved recipe',d.diagnostics.toPlainText()); self.assertEqual(d.rows,{})
        self.assertFalse(d.preflight_busy.isVisible()); self.assertFalse(d.run_button.isEnabled())

    def test_search_keeps_active_recipe_explicit_instead_of_showing_placeholder(self):
        d=self.dialog(self.r); d.search.setText('no matching recipe')
        self.assertEqual(d.selector.currentData(),self.r['id'])
        self.assertIn('current recipe',d.selector.currentText())
        self.assertEqual(d.recipe,self.r); self.assertFalse(d.selection_hint.isVisible())
        d.selector.setCurrentIndex(-1)
        self.assertIsNone(d.recipe); self.assertEqual(d.summary.text(),'Waiting for recipe selection')
        self.assertFalse(d.run_button.isEnabled())

    def test_editor_launch_failure_returns_to_waiting_and_keeps_files(self):
        d=self.dialog(self.r)
        with patch.object(editor,'make_editor_dialog',side_effect=core.RecipeError('Cannot read recipe library')):
            d.fix_recipe_button.click()
        self.assertIsNone(d.editor_dialog); self.assertIsNone(d.recipe)
        self.assertIn('Cannot open Recipe Editor',d.diagnostics.toPlainText())
        self.assertEqual(d.files,self.files); self.assertFalse(d.run_button.isEnabled())
        self.assertFalse(d.preflight_busy.isVisible()); self.assertTrue(d.create_button.isEnabled())

    def test_repair_reuses_editor_that_launched_run(self):
        outer=editor.make_editor_dialog(recipe=self.r); owner=outer.widget; outer.show()
        d=run.RunRecipeDialog(self.r,self.files,parent=owner); owner.run_dialog=d; self.dialogs.append(d)
        d.show(); wait(self.app,lambda:d.preflight_worker is None)
        with patch.object(editor,'make_editor_dialog',side_effect=AssertionError('Must reuse the owner')):
            d.fix_recipe_button.click()
        wait(self.app,lambda:d.preflight_worker is None)
        self.assertIsNone(d.editor_dialog); self.assertEqual(owner.repair_inputs[0],self.files)
        self.assertTrue(owner.repair_return.isVisible()); self.assertEqual(owner.recipe,self.r)
        owner.run_dialog=None
        owner.add_step('image.convert'); self.assertTrue(owner.save())
        resumed=[]
        def inspect_resumed(fresh):
            resumed.append(fresh); self.dialogs.append(fresh)
            wait(self.app,lambda:fresh.preflight_worker is None)
            self.assertEqual(fresh.files,self.files); self.assertTrue(fresh.run_button.isEnabled())
            fresh.reject(); return 0
        with patch.object(run.RunRecipeDialog,'exec',inspect_resumed): owner.repair_return.click()
        self.assertEqual(len(resumed),1); self.assertIsNone(owner.run_dialog); self.assertIsNone(owner.repair_inputs)
        owner.stop_preview(); wait(self.app,lambda:owner.preview_worker is None)
        outer.reject(); self.assert_sources()


class CompletionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def test_success_is_primary_details_are_click_only_and_keyboard_accessible(self):
        groups=[('2 PSD files used composites','source.psd\n'+WARNING),('1 staging notice','source.psd\n'+DIGEST_WARNING)]
        d=job.completion_dialog('PDF Album',['/photos/album.pdf'],groups); d.show(); self.app.processEvents()
        self.assertEqual(d.result_label.text(),'PDF Album created successfully'); self.assertFalse(d.isModal())
        self.assertEqual(d.details_button.text(),'Details (2)'); self.assertIn('/photos/album.pdf',d.saved_label.text())
        self.assertFalse(d.details.isVisible()); self.assertEqual(d.details_button.toolTip(),'')
        QApplication.sendEvent(d.details_button,QEvent(QEvent.Enter)); self.assertFalse(d.details.isVisible())
        d.details_button.setFocus()
        for event in (QEvent.KeyPress,QEvent.KeyRelease): QApplication.sendEvent(d.details_button,QKeyEvent(event,Qt.Key_Space,Qt.NoModifier))
        self.assertTrue(d.details.isVisible()); self.assertIn('not synchronized or repaired',d.details.toPlainText())
        d.copy.click(); self.assertEqual(self.app.clipboard().text(),d.details.toPlainText())
        d.details_button.click(); self.assertFalse(d.details.isVisible())
        d.done_button.click(); self.assertFalse(d.isVisible())

    def test_no_notices_has_no_empty_details_ui(self):
        d=job.completion_dialog('PDF Album',['/photos/album.pdf'],[]); d.show(); self.app.processEvents()
        self.assertFalse(d.details_button.isVisible()); self.assertFalse(d.details.isVisible())
        self.assertEqual(d.result_label.text(),'PDF Album created successfully'); d.reject()

    def test_failure_cancel_and_missing_commit_never_create_success_window(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(job,'completion_dialog') as dialog:
            for status,outputs in [('failed',[]),('cancelled',[]),('failed',['/photos/already-saved.pdf']),('success',[])]:
                output=io.StringIO()
                with contextlib.redirect_stderr(output): job.publication_result(directory,'PDF Album',outputs,status,graphical=True)
                self.assertNotIn('created successfully',output.getvalue())
                if outputs: self.assertIn(outputs[0],output.getvalue())
            dialog.assert_not_called()

    def test_grouping_deduplicates_physical_sources_without_inventing_profile_warning(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); source=root/'profiled-cmyk.psd'; source.write_bytes(b'fixture identity')
            alias=root/'alias.psd'; os.link(source,alias)
            entries=[{'source':str(path),'warning':warning} for path in (source,alias,source) for warning in (WARNING,DIGEST_WARNING)]
            (root/'warnings.jsonl').write_text('\n'.join(map(json.dumps,entries)))
            groups=job.grouped_warnings(job.shell_warning_rows(root))
            self.assertEqual(len(groups),2); self.assertTrue(all(caption.startswith('1 ') for caption,_ in groups))
            self.assertFalse(any('unprofiled' in caption.lower() for caption,_ in groups))
            self.assertEqual(groups[0][1].count(str(source)),1)
            output=io.StringIO()
            with contextlib.redirect_stderr(output): job.publication_result(root,'PDF Album',['/photos/album.pdf'],'success',graphical=False)
            self.assertIn('PDF Album created successfully',output.getvalue()); self.assertNotIn('Source notices',output.getvalue())


class PublicationIntegrationTests(unittest.TestCase):
    def setUp(self):
        import test_album_progress
        self.h=test_album_progress.AlbumProgressTests('test_destination_collision_is_numbered')
        self.h.setUp(); self.addCleanup(self.h.doCleanups)

    def test_real_pdf_mixed_sources_has_one_primary_result_and_grouped_notices(self):
        h=self.h; h.start(); stdout,stderr=h.finish(); h.assert_pdf()
        text=stderr.decode(); self.assertIn('PDF Album created successfully',text); self.assertIn(str(h.output),text)
        self.assertEqual(text.count('1 PSD file(s)'),1); self.assertEqual(text.count('1 unprofiled RGB/grayscale'),1)
        self.assertFalse(any('Source notices' in ' '.join(call['argv']) for call in h.calls()))

    def test_real_pdf_without_notices_keeps_success_and_no_empty_warning(self):
        h=self.h; h.start([h.jpg]); stdout,stderr=h.finish(); h.assert_pdf(pages=1)
        self.assertIn('PDF Album created successfully',stderr.decode()); self.assertNotIn('source file(s)',stderr.decode())
        self.assertFalse(any('Source notices' in ' '.join(call['argv']) for call in h.calls()))

    def test_real_render_failure_and_invalid_output_never_claim_success(self):
        h=self.h
        for mode in ('ALBUM_FAIL_STAGE','ALBUM_INVALID_PDF'):
            h.w.env[mode]='render' if mode=='ALBUM_FAIL_STAGE' else '1'
            h.start(); stdout,stderr=h.finish(False)
            self.assertFalse(h.output.exists()); self.assertNotIn('created successfully',stderr.decode())
            h.w.env.pop(mode)

    def test_cancelled_render_keeps_no_incomplete_output_or_success(self):
        h=self.h; h.w.env['ALBUM_HOLD_STAGE']='render'; h.start(); h.wait_for_stage()
        h.w.respond_to('qdbus','wasCancelled',{'stdout':'true\n'})
        stdout,stderr=h.finish(False); h.assert_child_gone()
        self.assertFalse(h.output.exists()); self.assertNotIn('created successfully',stderr.decode())

    def test_shared_publication_exit_routes_reuse_compact_result(self):
        # Exercise the actual shell adapter functions and Python CLI for each
        # shared path without repeating every already validated renderer.
        source=Path(__file__).resolve().parents[1]/'src/bin/kim_all'
        text=source.read_text(); functions=text[text.index('job_show_warnings() {'):text.index('job_cleanup() {')]
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); original=root/'source.psd'; original.write_bytes(b'source identity')
            cache=root/'psd'; cache.mkdir()
            (cache/'warnings.jsonl').write_text(json.dumps({'source':str(original),'warning':WARNING})+'\n')
            actions={'album':'PDF Album','contactsheet':'Contact Sheet','collage':'Collage','print':'Print PDF',
                     'tiffjoin':'TIFF Document','animate':'Animated GIF','gallery':'Web Gallery','slideshow':'Slideshow','convert':'PDF files'}
            env=os.environ.copy(); env.pop('DISPLAY',None); env.pop('WAYLAND_DISPLAY',None)
            env.update(KIMDIR=str(root),KIM_PSD_CACHE=str(cache),DISPATCHER_DIR=str(source.parent),REPORT_FAIL='0',REPORT_CANCELLED='0')
            for action,label in actions.items():
                with self.subTest(action=action):
                    manifest=root/'published.outputs'
                    if manifest.exists(): manifest.unlink()
                    script=functions+'\ncmd="$1"; publication_record_output "$2"; job_show_warnings 0'
                    result=subprocess.run(['bash','-c',script,'publication-test',action,str(root/'saved.pdf')],env=env,capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertIn(label+' created successfully',result.stderr); self.assertNotIn('Source notices',result.stderr)
            env['REPORT_FAIL']='1'
            result=subprocess.run(['bash','-c',functions+'\ncmd=gallery; job_show_warnings 0'],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr); self.assertNotIn('created successfully',result.stderr)
            self.assertIn(str(root/'saved.pdf'),result.stderr)

    def test_published_result_is_named_even_if_progress_close_fails(self):
        h=self.h; h.w.respond_to('qdbus','close',[{'status':1},{'status':0}]); h.start()
        stdout,stderr=h.finish(False); h.assert_pdf()
        self.assertIn(str(h.output),stderr.decode()); self.assertNotIn('created successfully',stderr.decode())
        h.assert_error('Album saved, but its progress window could not be closed')


if __name__=='__main__': unittest.main()
