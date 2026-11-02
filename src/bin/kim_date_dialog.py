#!/usr/bin/env python3
"""One standalone date confirmation; collect data only, never write sources."""
import json
import sys
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QFormLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QDialogButtonBox, QPlainTextEdit)
from kim_ui import CaptureDateInput, CaptureAdjustment, CaptureDateOptions
from kim_date_tools import resolve

TITLES = {'set':'Set Photo Capture Date', 'shift':'Adjust Photo Capture Date',
          'exif-to-file':'Set File Date from Photo Capture Date', 'file-to-exif':'Set Photo Capture Date from File Date'}


class DatePreview(QThread):
    def __init__(self, files, config, parent):
        super().__init__(parent); self.files, self.config = files, config; self.rows=[]; self.valid=True

    def run(self):
        from kim_psd_source import inspection_context
        for path in self.files:
            if self.isInterruptionRequested(): self.valid=False; break
            try:
                with inspection_context(cancelled=self.isInterruptionRequested): value = resolve(path,self.config)['preview']
            except Exception as exc: value=str(exc); self.valid=False
            self.rows.append(Path(path).name + ': ' + value)


class PhotoDateDialog(QDialog):
    def __init__(self, kind, files, parent=None):
        super().__init__(parent); self.kind, self.files = kind,list(files); self.worker=None; self.pending=False; self.closing=False
        self.form=None
        self.setWindowTitle('KIM6 — ' + TITLES[kind]); self.resize(650,390)
        layout=QVBoxLayout(self); form=QFormLayout(); self.form=form; layout.addLayout(form)
        self.capture=CaptureDateInput(); form.addRow(self.capture)
        form.setRowVisible(self.capture,kind=='set')
        self.adjust=CaptureAdjustment(); form.addRow('Adjustment',self.adjust); form.setRowVisible(self.adjust,kind=='shift')
        self.advanced=CaptureDateOptions('embedded' if kind in ('shift','exif-to-file') else 'unknown',embedded=kind!='set')
        self.zone,self.offset,self.fields=self.advanced.zone,self.advanced.offset,self.advanced.fields
        form.addRow(self.advanced); self.fields.setEnabled(kind!='exif-to-file')
        # A filesystem instant requires an informed timezone choice, unlike
        # assigning an unknown-zone camera clock. Show that required choice.
        if kind in ('file-to-exif','exif-to-file'): self.advanced.toggle.setChecked(True)
        explanation = ('Changes the File Modification Date only; embedded metadata stays unchanged.' if kind=='exif-to-file' else
                       'Changes embedded Photo Capture Date metadata; the File Modification Date is preserved.')
        self.explanation=QLabel(explanation + (f' The same entered date will apply to all {len(files)} selected files.' if kind=='set' and len(files)>1 else f' {len(files)} selected file(s); each source is calculated separately.'))
        self.explanation.setWordWrap(True); layout.addWidget(self.explanation)
        self.details=QPlainTextEdit(); self.details.setReadOnly(True); layout.addWidget(self.details)
        self.fix=QPushButton('Set Photo Capture Date…'); self.fix.clicked.connect(self.use_set); layout.addWidget(self.fix); self.fix.setVisible(kind!='set')
        self.buttons=QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Cancel)
        self.apply=self.buttons.button(QDialogButtonBox.Apply); self.apply.setEnabled(False); self.apply.clicked.connect(self.accept)
        self.buttons.rejected.connect(self.reject); layout.addWidget(self.buttons)
        self.capture.changed.connect(self.refresh); self.adjust.changed.connect(self.refresh)
        self.zone.currentIndexChanged.connect(self.refresh); self.offset.textChanged.connect(self.refresh); self.fields.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def config(self):
        zone=self.offset.text() if self.zone.currentData()=='custom' else self.zone.currentData()
        return {'kind':self.kind,'datetime':self.capture.value(),'timezone':zone,'seconds':self.adjust.value(),'fields':self.fields.currentData()}

    def use_set(self):
        self.kind='set'; self.setWindowTitle('KIM6 — '+TITLES['set']); self.form.setRowVisible(self.capture,True); self.form.setRowVisible(self.adjust,False); self.fix.hide()
        self.advanced.set_zone('unknown'); self.fields.setEnabled(True); self.advanced.toggle.setChecked(False)
        embedded=self.zone.findData('embedded')
        if embedded >= 0: self.zone.model().item(embedded).setEnabled(False)
        self.explanation.setText(f'Changes embedded Photo Capture Date metadata in {len(self.files)} selected file(s). The same entered date applies to all. File Modification Dates are preserved.')
        self.refresh()

    def refresh(self,*_):
        self.apply.setEnabled(False)
        if self.worker:
            self.pending=True; self.worker.requestInterruption(); return
        self.pending=False; self.details.setPlainText('Checking selected photo dates…')
        worker=DatePreview(self.files,self.config(),self); self.worker=worker
        worker.finished.connect(self.finished_preview); worker.start()

    def finished_preview(self):
        worker,self.worker=self.worker,None
        if self.closing: worker.deleteLater(); super().reject(); return
        if self.pending: worker.deleteLater(); self.refresh(); return
        self.details.setPlainText('\n'.join(worker.rows)); self.apply.setEnabled(worker.valid and bool(worker.rows)); worker.deleteLater()

    def reject(self):
        if self.worker:
            self.closing=True; self.worker.requestInterruption(); self.apply.setEnabled(False); return
        super().reject()

    def closeEvent(self,event):
        if self.worker: self.reject(); event.ignore()
        else: event.accept()


def main():
    kind,result,*files=sys.argv[1:]
    app=QApplication(sys.argv[:1]); dialog=PhotoDateDialog(kind,files)
    if dialog.exec()!=QDialog.Accepted: return 1
    Path(result).write_text(json.dumps(dialog.config())); return 0


if __name__=='__main__': raise SystemExit(main())
