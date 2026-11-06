#!/usr/bin/env python3
"""One standalone date confirmation; collect data only, never write sources."""
import json
import sys
from pathlib import Path
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QStyle,
    QCheckBox, QTableWidgetItem)
from kim_ui import CaptureDateInput, CaptureAdjustment, CaptureDateOptions

TITLES = {'set':'Set Image Capture Date', 'shift':'Adjust Image Capture Date',
          'exif-to-file':'Set File Date from Image Capture Date', 'file-to-exif':'Set Image Capture Date'}


class PhotoDateDialog(QDialog):
    def __init__(self, kind, files, policy, seeds, parent=None):
        super().__init__(parent); self.kind, self.files = kind,list(files); self.worker=None; self.pending=False; self.closing=False
        self.policy,self.seeds,self.plan=policy,seeds,None
        self.form=None
        self.setWindowTitle('KIM6 — ' + TITLES[kind]); self.resize(1050,620)
        layout=QVBoxLayout(self); form=QFormLayout(); self.form=form; layout.addLayout(form)
        # Both capture-date sources use the same preview and publisher.
        self.source_choice = None

        if kind == 'set':
            self.source_choice = QComboBox()
            self.source_choice.addItem(
                'Enter date and time', 'set'
            )
            self.source_choice.addItem(
                'Use each image file modification date', 'file-to-exif'
            )
            form.addRow('Image Capture Date source', self.source_choice)

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
                       'Set the image capture date you want in image metadata. Original files are preserved; new copies are created.')
        self.explanation=QLabel(explanation + (f' The same entered date will apply to all {len(files)} selected files.' if kind=='set' and len(files)>1 else f' {len(files)} selected file(s); each source is calculated separately.'))
        self.explanation.setWordWrap(True); layout.addWidget(self.explanation)
        from kim_preview import qt_classes
        self.details=qt_classes()[0](self); layout.addWidget(QLabel('Preview Changes')); layout.addWidget(self.details)
        self.metadata_toggle = QCheckBox('Show metadata details')
        self.metadata_toggle.setChecked(False)
        self.metadata_toggle.toggled.connect(
            self.render_date_preview
        )
        layout.addWidget(self.metadata_toggle)

        self.fix=QPushButton('Set Image Capture Date…'); self.fix.clicked.connect(self.use_set); layout.addWidget(self.fix); self.fix.setVisible(kind!='set')
        button_row = QHBoxLayout()
        button_row.addStretch(1)

        self.apply = QPushButton(
            QIcon.fromTheme('dialog-ok-apply', self.style().standardIcon(QStyle.SP_DialogApplyButton)),
            'Apply Changes'
        )
        self.apply.setEnabled(False)
        self.apply.clicked.connect(self.accept)
        button_row.addWidget(self.apply)

        self.cancel_button = QPushButton(
            QIcon.fromTheme('dialog-cancel', self.style().standardIcon(QStyle.SP_DialogCancelButton)),
            'Cancel'
        )
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_button)

        layout.addLayout(button_row)
        if self.source_choice is not None:
            self.source_choice.currentIndexChanged.connect(
                self.capture_source_changed
            )

        self.capture.changed.connect(self.refresh); self.adjust.changed.connect(self.refresh)
        self.zone.currentIndexChanged.connect(self.refresh); self.offset.textChanged.connect(self.refresh); self.fields.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def capture_source_changed(self, *_):
        # Changing sources invalidates the previous approval.
        self.kind = self.source_choice.currentData()
        manual = self.kind == 'set'

        self.form.setRowVisible(self.capture, manual)
        self.fields.setEnabled(True)

        if manual:
            self.advanced.set_zone('unknown')
            self.advanced.toggle.setChecked(False)
            self.explanation.setText(
                'The entered image capture date applies to every selected image. '
                'File modification dates are preserved.'
            )
        else:
            self.advanced.set_zone('UTC')
            self.advanced.toggle.setChecked(True)
            self.explanation.setText(
                'Each image receives its own file modification date '
                'as its embedded image capture date. '
                'File modification dates are preserved.'
            )

        self.refresh()


    @staticmethod
    def readable_timestamp(value):
        """Human-readable clock without changing metadata precision."""
        import re

        value = str(value or '').strip()

        if not value:
            return 'Not set'

        match = re.match(
            r'^(\\d{4}):(\\d{2}):(\\d{2})[ T]'
            r'(\\d{2}:\\d{2}:\\d{2})(.*)$',
            value
        )

        if match:
            year, month, day, clock, remainder = match.groups()
            return f'{year}-{month}-{day} {clock}{remainder}'

        return value

    def render_date_preview(self, *_):
        """One default row per image; preserve full metadata inspection."""
        if not self.plan:
            return

        if self.metadata_toggle.isChecked():
            self.details.show_plan(self.plan)
            self.details.summary.setText(
                self.details.summary.text()
                .replace('Set Photo Capture Date from File Date',
                         'Set Image Capture Date')
                .replace('Set Photo Capture Date', 'Set Image Capture Date')
                .replace('Adjust Photo Capture Date', 'Adjust Image Capture Date')
            )
            return

        # Build the technical view first so its existing summary and
        # approval calculation remain authoritative.
        self.details.show_plan(self.plan)
        summary = self.details.summary.text()

        summary = (
            summary
            .replace('Set Photo Capture Date from File Date',
                     'Set Image Capture Date')
            .replace('Set Photo Capture Date', 'Set Image Capture Date')
            .replace('Adjust Photo Capture Date', 'Adjust Image Capture Date')
            .replace('Set File Date from Photo Capture Date',
                     'Set File Date from Image Capture Date')
        )

        self.details.summary.setText(summary)

        table = self.details.table

        table.setColumnCount(4)
        table.setHorizontalHeaderLabels([
            'Image',
            'Current',
            'Proposed',
            'Status',
        ])

        entries = self.plan.get('entries', [])
        table.setRowCount(len(entries))

        for index, entry in enumerate(entries):
            result = entry.get('date_result') or {}
            current_tags = result.get('current') or {}

            current = (
                current_tags.get('ExifIFD:DateTimeOriginal')
                or current_tags.get('XMP-exif:DateTimeOriginal')
                or current_tags.get('XMP-photoshop:DateCreated')
                or ''
            )

            proposed = result.get('preview') or ''

            status = entry.get('status', 'error')

            if status == 'change':
                status_label = 'Ready'
            elif status == 'skip':
                status_label = 'Unchanged'
            else:
                status_label = 'Blocked'

            warnings = entry.get('warnings') or []

            # The detailed metadata rows are retained in the plan.
            # This table is presentation only.
            values = [
                Path(entry['source']).name,
                self.readable_timestamp(current),
                self.readable_timestamp(proposed),
                status_label,
            ]

            # Show only relevant information on hover. The complete
            # metadata remains available through Show metadata details.
            status_details = '\n'.join(
                str(message) for message in (
                    entry.get('error'), entry.get('skip_reason'), *warnings
                ) if message
            )
            tooltips = (
                str(entry['source']),
                str(values[1]),
                str(values[2]),
                status_details or status_label,
            )

            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(tooltips[column])
                table.setItem(index, column, item)

        # The compact Status column needs only enough room for
        # Ready, Unchanged or Blocked, not the old review width.
        table.resizeColumnToContents(3)

    def config(self):
        zone=self.offset.text() if self.zone.currentData()=='custom' else self.zone.currentData()
        return {'kind':self.kind,'datetime':self.capture.value(),'timezone':zone,'seconds':self.adjust.value(),'fields':self.fields.currentData()}

    def use_set(self):
        if self.source_choice is not None:
            self.source_choice.setCurrentIndex(0)
        self.kind='set'; self.setWindowTitle('KIM6 — '+TITLES['set']); self.form.setRowVisible(self.capture,True); self.form.setRowVisible(self.adjust,False); self.fix.hide()
        self.advanced.set_zone('unknown'); self.fields.setEnabled(True); self.advanced.toggle.setChecked(False)
        embedded=self.zone.findData('embedded')
        if embedded >= 0: self.zone.model().item(embedded).setEnabled(False)
        self.explanation.setText(f'Changes embedded Image Capture Date metadata in {len(self.files)} selected file(s). The same entered date applies to all. File Modification Dates are preserved.')
        self.refresh()

    def refresh(self,*_):
        self.apply.setEnabled(False)
        if self.worker:
            self.pending=True; self.worker.requestInterruption(); return
        self.pending=False

        # An empty capture-date form is incomplete, not an error.
        if self.kind == 'set' and not self.capture.value():
            self.plan = None
            self.details.summary.setText(
                'Choose an image capture date and time to preview the changes.'
            )
            self.details.table.setRowCount(0)
            self.apply.setEnabled(False)
            return

        self.details.summary.setText('Checking selected image dates…')
        from kim_preview import qt_classes
        worker=qt_classes()[1]('date',self.policy,self.files,self.config(),self.seeds,self); self.worker=worker
        worker.progress.connect(lambda i,n,p:self.details.summary.setText(f'Inspecting image {i+1} of {n}: {Path(p).name}'))
        worker.finished.connect(self.finished_preview); worker.start()

    def finished_preview(self):
        worker,self.worker=self.worker,None
        if self.closing: worker.deleteLater(); super().reject(); return
        if self.pending: worker.deleteLater(); self.refresh(); return
        if worker.error: self.details.summary.setText(worker.error)
        else:
            self.plan=worker.plan
            permitted=self.details.show_plan(worker.plan)
            self.render_date_preview()
            self.apply.setEnabled(permitted)
        worker.deleteLater()

    def accept(self):
        if not self.apply.isEnabled() or self.worker: return
        from kim_preview import verify_plan
        try: verify_plan(self.plan)
        except Exception as exc:
            self.details.summary.setText(str(exc)+' Review a fresh plan.'); self.apply.setEnabled(False); return
        super().accept()

    def reject(self):
        if self.worker:
            self.closing=True; self.worker.requestInterruption(); self.apply.setEnabled(False); return
        super().reject()

    def closeEvent(self,event):
        if self.worker: self.reject(); event.ignore()
        else: event.accept()


def main():
    kind,result,policy,seeds_path,*files=sys.argv[1:]
    seeds=Path(seeds_path).read_bytes().decode().split("\0")[:-1]
    app=QApplication(sys.argv[:1]); dialog=PhotoDateDialog(kind,files,policy,seeds)
    if dialog.exec()!=QDialog.Accepted: return 130
    from kim_preview import save_plan
    save_plan(result+'.approved',dialog.plan)
    Path(result).write_text(json.dumps(dialog.config())); return 0


if __name__=='__main__': raise SystemExit(main())
