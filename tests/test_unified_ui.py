"""Shared controls and final-encoding regression contracts (Qt offscreen)."""
import copy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'src/bin')]
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QDate, QTime, Qt, QEvent, QPointF
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication
from kim_ui import CaptureDateInput, RotationInput, HelpButton, HELP
from kim_recipe_dates import specific, assignments
from kim_recipe_core import RecipeError
import test_recipes as base
from test_recipe_correctness import step
import kim_recipe_core as core


class WidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def test_empty_page_never_commits_calendar_navigation(self):
        w=CaptureDateInput(); self.assertEqual(w.value(),''); self.assertEqual(w.time.time(),QTime(0,0))
        w.date.open_calendar(); self.app.processEvents()
        cal=w.date.calendarWidget(); now=QDate.currentDate()
        self.assertEqual((cal.yearShown(),cal.monthShown()),(now.year(),now.month()))
        cal.showPreviousYear(); self.assertEqual(w.value(),'')
        w.date.popup.reject(); self.app.processEvents(); self.assertEqual(w.value(),'')
        w.date.open_calendar(); cal.activated.emit(QDate(4,2,29)); self.app.processEvents()
        self.assertEqual(w.date.edit.text(),'0004-02-29'); self.assertEqual(w.value(),'0004-02-29 00:00:00')
        w.date.clear(); self.assertEqual(w.value(),'')

    def test_empty_calendar_keyboard_navigation_and_explicit_commit(self):
        w=CaptureDateInput(); w.date.open_calendar(); self.app.processEvents()
        calendar=w.date.calendarWidget()
        QApplication.sendEvent(calendar.focusProxy(),QKeyEvent(QEvent.KeyPress,Qt.Key_Right,Qt.NoModifier))
        self.assertEqual(w.value(),''); self.assertEqual(w.date.edit.text(),'')
        expected=calendar.selectedDate().toString('yyyy-MM-dd')
        QApplication.sendEvent(calendar.focusProxy(),QKeyEvent(QEvent.KeyPress,Qt.Key_Return,Qt.NoModifier));self.app.processEvents()
        self.assertEqual(w.date.edit.text(),expected); self.assertEqual(w.value(),expected+' 00:00:00'); self.assertEqual(w.time.text(),'00:00:00')

    def test_empty_calendar_mouse_click_commits_only_the_chosen_day(self):
        w=CaptureDateInput(); w.date.open_calendar(); self.app.processEvents()
        view=w.date.calendarWidget().focusProxy()
        point=QPointF(view.visualRect(view.model().index(2,1)).center())
        for kind,buttons in ((QEvent.MouseButtonPress,Qt.LeftButton),(QEvent.MouseButtonRelease,Qt.NoButton)):
            QApplication.sendEvent(view.viewport(),QMouseEvent(kind,point,point,Qt.LeftButton,buttons,Qt.NoModifier));self.app.processEvents()
        self.assertTrue(w.date.date().isValid());self.assertEqual(w.value(),w.date.edit.text()+' 00:00:00');self.assertEqual(w.time.text(),'00:00:00')

    def test_date_round_trip_historical_leap_and_precision(self):
        for value in ('0004-02-29 01:02:03.001234567','0100-01-01 12:13:14','2024-02-29 00:00:00'):
            widget=CaptureDateInput(value); self.assertEqual(widget.value(),value[:19])
            date,fraction=specific(value,'unknown'); self.assertIsNone(date.tzinfo)
            self.assertIn('-EXIF:DateTimeOriginal='+value[:19].replace('-',':'),assignments(date,fraction))
        for value in ('','2023-02-29 12:00:00','2024-02-29','2024-02-29 00:00:00.abc'):
            with self.assertRaises(RecipeError): specific(value,'unknown')
        with self.assertRaisesRegex(RecipeError,'Choose a capture date and time'): specific('','')

    def test_ten_help_topics_click_only_and_dismissible(self):
        self.assertEqual(len(HELP),10)
        for topic in HELP:
            button=HelpButton(topic); self.assertEqual(button.toolTip(),''); self.assertEqual(button.focusPolicy(),Qt.StrongFocus)
            QApplication.sendEvent(button,QEvent(QEvent.Enter)); self.app.processEvents(); self.assertIsNone(button.help_dialog)
            button.click(); self.app.processEvents(); self.assertIsNotNone(button.help_dialog)
            self.assertTrue(button.accessibleName())
            QApplication.sendEvent(button.help_dialog,QKeyEvent(QEvent.KeyPress,Qt.Key_Escape,Qt.NoModifier));self.app.processEvents();self.assertIsNone(button.help_dialog)
            button.show();button.setFocus();self.app.processEvents()
            for kind in (QEvent.KeyPress,QEvent.KeyRelease): QApplication.sendEvent(button,QKeyEvent(kind,Qt.Key_Space,Qt.NoModifier))
            self.app.processEvents();self.assertIsNotNone(button.help_dialog)
            button.help_dialog.reject();self.app.processEvents();button.close()

    def test_rotation_presets_and_custom(self):
        w=RotationInput(12.5); self.assertTrue(w.buttons['Custom'].isChecked())
        for label,value in [('90° Left',-90),('90° Right',90),('180°',180)]:
            w.buttons[label].click(); self.assertEqual(w.degrees.value(),value); self.assertTrue(w.buttons[label].isChecked())
        w.degrees.setValue(-23.125); self.assertTrue(w.buttons['Custom'].isChecked())


class EncodingTests(unittest.TestCase):
    def test_convert_compress_rotate_one_lossy_encode_and_precedence(self):
        import kim_recipe_image as image
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.png'
            subprocess.run(['magick','-size','12x8','gradient:red-blue',str(source)],check=True)
            before=(source.read_bytes(),source.stat().st_mtime_ns)
            operations=[step('image.convert',quality=91),step('image.compress',preset='custom',quality=42),step('image.rotate',degrees=90)]
            r=base.recipe(operations); calls=[]; real=image.run
            def trace(args,**kw):
                if args[0]=='magick' and args[-1].startswith('JPEG:'): calls.append(args)
                return real(args,**kw)
            with patch.object(image,'run',side_effect=trace): result=core.execute(r,[source])[0]
            self.assertTrue(result['ok'],result); self.assertEqual(len(calls),1)
            self.assertEqual(calls[0][calls[0].index('-quality')+1],'42')
            self.assertEqual(subprocess.check_output(['magick','identify','-format','%w %h %[quality]',result['output']]),b'8 12 42')
            r['steps'][1]['enabled']=False
            self.assertEqual(core.preview(r,[source])[0].properties['quality'],91)
            r['steps']=[dict(operations[1],enabled=True),operations[0],operations[2]]
            self.assertEqual(core.preview(r,[source])[0].properties['quality'],42)
            self.assertEqual((source.read_bytes(),source.stat().st_mtime_ns),before)
            self.assertEqual(core.validate(copy.deepcopy(r)),r)

    def test_compression_ignores_inactive_conversion_quality_reference(self):
        from kim_recipe_run import confirmation_snapshot
        r=base.recipe([step('image.convert',quality=None),step('image.compress',preset='custom',quality=42)])
        with patch.dict(os.environ,KIM_WEB_QUALITY_JPEG='invalid'):
            snapshot,error=confirmation_snapshot(r);self.assertIsNone(error)
            self.assertIsNone(snapshot['steps'][0]['quality'])
            r['steps'][1]['enabled']=False
            snapshot,error=confirmation_snapshot(r);self.assertIn('Correct Settings',error)


if __name__=='__main__': unittest.main()
