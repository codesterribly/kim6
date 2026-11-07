"""Shared job state and source-based diagnostic grouping, independent of Qt."""
from dataclasses import dataclass, field
import os
from pathlib import Path


@dataclass
class JobStatus:
    action: str
    total: int
    index: int = 0
    source: str = ''
    stage: str = 'Inspecting source'
    results: list = field(default_factory=list)
    cancelling: bool = False

    def start(self, source, index):
        self.source, self.index = str(source), index

    def __post_init__(self):
        self._succeeded = sum(r.get('ok', False) for r in self.results)
        self._cancelled = sum(r.get('cancelled', False) for r in self.results)
        self._skipped = sum(r.get('skipped', False) for r in self.results)

    def finish(self, result):
        self.results.append(result)
        self._succeeded += result.get('ok', False)
        self._cancelled += result.get('cancelled', False)
        self._skipped += result.get('skipped', False)

    def counts(self):
        succeeded, cancelled, skipped = self._succeeded, self._cancelled, self._skipped
        failed=len(self.results)-succeeded-cancelled-skipped
        return succeeded,failed,cancelled,skipped,max(0,self.total-len(self.results))

    def label(self):
        ok,failed,cancelled,skipped,remaining=self.counts()
        stage='Cancelling current operation…' if self.cancelling else self.stage
        return (f'{self.action}: file {self.index} of {self.total}: {Path(self.source).name}\n'
                f'{self.source}\n{stage}\nSucceeded: {ok}; failed: {failed}; cancelled: {cancelled}; skipped: {skipped}; remaining: {remaining}')


def warning_category(warning):
    if warning.startswith('PSD compatibility:'): return 'psd'
    if 'IPTC digest' in warning or 'IPTCDigest' in warning: return 'digest'
    if warning.startswith('Unprofiled RGB/grayscale'): return 'unprofiled'
    return warning


class WarningGroups:
    """Presentation observations, scoped to one result generation."""
    def __init__(self): self.categories = {}

    def add(self, row):
        if not row.warnings: return
        source = os.path.realpath(row.source)
        identity = getattr(row, 'identity', None)
        if identity is None:
            try:
                st = os.stat(source); identity = (st.st_dev, st.st_ino)
            except OSError: identity = source
        else: identity = tuple(identity[:2])
        for warning in row.warnings:
            files = self.categories.setdefault(warning_category(warning), {})
            entry = files.setdefault(identity, {'source': source, 'details': []})
            if warning not in entry['details']: entry['details'].append(warning)

    def captions(self):
        for category, files in self.categories.items():
            n = len(files)
            yield {'psd': f'{n} PSD file(s) used Photoshop composites / best-effort reconstruction',
                   'digest': f'{n} source file(s) emitted an IPTC staging digest notice',
                   'unprofiled': f'{n} unprofiled RGB/grayscale source file(s) assumed sRGB'}.get(category, f'{n} source file(s): {category}')

    def groups(self):
        return [(caption, '\n\n'.join(entry['source']+'\n'+'\n'.join(entry['details']) for entry in files.values()))
                for caption, files in zip(self.captions(), self.categories.values())]


def grouped_warnings(rows):
    """Deduplicate by original source identity, never by a derived/staging path."""
    groups = WarningGroups()
    for row in rows: groups.add(row)
    return groups.groups()


def shell_warning_rows(directory):
    import json
    from types import SimpleNamespace
    path=Path(directory)/'warnings.jsonl'
    if not path.exists(): return []
    return [SimpleNamespace(source=entry['source'],identity=entry.get('identity'),warnings=[entry['warning']])
            for line in path.read_text().splitlines() if line.strip()
            for entry in [json.loads(line)]]


def completion_dialog(action, outputs, groups):
    """One modeless result window. Advisory details open only on an explicit click."""
    from PySide6.QtCore import QUrl, Qt
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QPlainTextEdit,QLayout,QSizePolicy)
    dialog=QDialog(); dialog.setWindowTitle('KIM6 - '+action)
    dialog.setModal(False); layout=QVBoxLayout(dialog)
    # Hidden diagnostics must contribute no initial size. Qt's intrinsic layout
    # then gives the same compact geometry before and after every expansion.
    layout.setSizeConstraint(QLayout.SetFixedSize)
    dialog.result_label=QLabel(action+' created successfully'); dialog.result_label.setWordWrap(True)
    layout.addWidget(dialog.result_label)
    saved=QLabel('Saved as: '+'\n'.join(outputs)); saved.setTextFormat(Qt.PlainText)
    saved.setWordWrap(True); saved.setMinimumWidth(0)
    saved.setSizePolicy(QSizePolicy.Preferred,QSizePolicy.Preferred)
    saved.setMaximumWidth(dialog.screen().availableGeometry().width()*3//4)
    saved.setTextInteractionFlags(Qt.TextSelectableByMouse|Qt.TextSelectableByKeyboard)
    layout.addWidget(saved); dialog.saved_label=saved
    dialog.details=QPlainTextEdit(); dialog.details.setReadOnly(True)
    dialog.details.setPlainText('\n\n'.join(caption+'\n'+details for caption,details in groups))
    dialog.details.hide(); layout.addWidget(dialog.details)
    dialog.copy=QPushButton('Copy Details'); dialog.copy.hide(); layout.addWidget(dialog.copy)
    dialog.details_button=QPushButton(f'Details ({len(groups)})'); dialog.details_button.setCheckable(True)
    dialog.details_button.setAccessibleName(f'Details ({len(groups)})')
    dialog.details_button.setVisible(bool(groups))
    def expand(opened):
        dialog.details.setVisible(opened); dialog.copy.setVisible(opened)
        layout.invalidate(); layout.activate(); dialog.adjustSize()
    dialog.details_button.toggled.connect(expand)
    from PySide6.QtWidgets import QApplication
    dialog.copy.clicked.connect(lambda:QApplication.clipboard().setText(dialog.details.toPlainText()))
    buttons=QHBoxLayout(); folder=QPushButton('Open folder'); dialog.done_button=QPushButton('Done')
    folder.clicked.connect(lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(outputs[0]).parent))))
    buttons.addWidget(folder); buttons.addStretch(1); buttons.addWidget(dialog.details_button); buttons.addWidget(dialog.done_button); layout.addLayout(buttons)
    dialog.done_button.clicked.connect(dialog.accept); dialog.done_button.setDefault(True)
    dialog.ensurePolished(); layout.activate(); dialog.adjustSize()
    return dialog


def publication_result(directory, action, outputs, status, graphical=None):
    rows=shell_warning_rows(directory)
    if status=='success' and outputs:
        from kim_source_advisories import undisclosed_warning_rows
        rows=undisclosed_warning_rows(directory,rows)
    groups=grouped_warnings(rows)
    import sys
    # Only a successful, validated publication is a success. Failures retain
    # their existing action error UI; the EXIT adapter never adds a notice modal.
    if status!='success' or not outputs:
        if outputs: print('Saved results retained: '+'; '.join(outputs),file=sys.stderr)
        for caption,details in groups: print(caption+'\n'+details,file=sys.stderr)
        return None
    if graphical is None: graphical=bool(os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'))
    # Successful publications return quietly unless source advisories need attention.
    if not groups: return None
    if not graphical:
        print(action+' created successfully\nSaved as: '+'; '.join(outputs),file=sys.stderr)
        for caption,details in groups: print(caption+'\n'+details,file=sys.stderr)
        return None
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    dialog=completion_dialog(action,outputs,groups); dialog.show()
    app.exec()
    return dialog


def show_shell_warnings(directory, disclosed=None):
    rows = shell_warning_rows(directory)

    if disclosed:
        import json
        disclosed_pairs = set()

        try:
            for line in Path(disclosed).read_text().splitlines():
                if not line.strip():
                    continue
                item = json.loads(line)
                disclosed_pairs.add((
                    os.path.realpath(item["source"]),
                    item["category"],
                ))
        except (OSError, ValueError, KeyError, TypeError):
            # On corrupt disclosure state, retain every warning.
            disclosed_pairs.clear()

        rows = [
            row for row in rows
            if (
                os.path.realpath(row.source),
                warning_category(row.warnings[0])
            ) not in disclosed_pairs
        ]

    groups = grouped_warnings(rows)
    if not groups: return
    if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        import sys
        for caption,details in groups: print(caption+'\n'+details,file=sys.stderr)
        return
    from PySide6.QtWidgets import QApplication,QDialog,QVBoxLayout,QDialogButtonBox
    from kim_recipe_run import WarningView
    app=QApplication.instance() or QApplication([]); dialog=QDialog(); dialog.setWindowTitle('KIM6 - Source notices')
    layout=QVBoxLayout(dialog); view=WarningView(); view.set_rows(rows); layout.addWidget(view)
    buttons=QDialogButtonBox(QDialogButtonBox.Close); buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    dialog.resize(660,220); dialog.exec()


def compression_result(path):
    """Consume private job accounting; one result for success, failure or cancellation."""
    import gettext
    import sys
    tr = gettext.translation('kim6', localedir=os.environ.get('TEXTDOMAINDIR') or
                             Path(__file__).resolve().parent.parent/'locale', fallback=True).gettext
    fields = Path(path).read_bytes().decode('utf-8', errors='replace').split('\0')
    ok, failed, cancelled, skipped, original, output, measured = map(int, fields[:7])
    settings, stopped = fields[7:9]
    if stopped == 'true' or cancelled:
        heading = tr('Compression cancelled. Successfully saved results were kept')
    elif failed and not ok:
        heading = tr('Compression failed')
    elif failed or skipped:
        heading = tr('Compression partially completed')
    else:
        heading = tr('Compression completed')
    lines = [heading, '', tr('Files successfully processed:') + f' {ok}',
             tr('Files failed:') + f' {failed}']
    if cancelled or skipped or stopped == 'true':
        lines += [tr('Files cancelled:') + f' {cancelled}', tr('Files skipped:') + f' {skipped}']
    if measured == ok:
        factor, unit = 1, 'B'
        for candidate in ('KiB', 'MiB', 'GiB', 'TiB', 'PiB'):
            if max(original, output) < factor * 1024: break
            factor *= 1024
            unit = candidate
        def size(value): return f'{value / factor:,.2f} {unit} ({value:,} ' + tr('bytes') + ')'
        saved = original - output
        lines += ['', tr('Original total size:') + ' ' + size(original),
                  tr('Output total size:') + ' ' + size(output),
                  (tr('Size increase:') if saved < 0 else tr('Bytes saved:')) + ' ' + size(abs(saved))]
        percent = f'{abs(saved) * 100 / original:.2f}%' if original and ok else tr('Not applicable (zero original size)')
        lines.append((tr('Percentage increased:') if saved < 0 else tr('Percentage saved:')) + ' ' + percent)
    elif ok:
        lines += ['', tr('Size statistics unavailable: a published output size could not be read.')]
    if not ok:
        lines += ['', tr('No outputs were successfully published; size savings are not applicable.')]
    if settings: lines += ['', tr('Compression settings:'), settings]
    message = '\n'.join(lines)
    details = '\n'.join(fields[9:-1])
    if not (os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY')):
        print(message + ('\n\n' + details if details else ''), file=sys.stderr)
        return
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    dialog = QMessageBox()
    dialog.setWindowTitle(tr('KIM6 - Compression results'))
    dialog.setTextFormat(Qt.PlainText)
    dialog.setText(message)
    if details: dialog.setDetailedText(details)
    dialog.setIcon(QMessageBox.Warning if failed or cancelled or stopped == 'true' else QMessageBox.Information)
    dialog.exec()

if __name__=='__main__':
    import sys
    if sys.argv[1:2] == ['--webexport-disclosed']:
        if len(sys.argv) != 4:
            raise SystemExit(2)
        show_shell_warnings(sys.argv[2], sys.argv[3])
    elif sys.argv[1:2] == ['--compression']:
        compression_result(sys.argv[2])
    elif len(sys.argv)>2 and sys.argv[2]=='--publication':
        directory,_,action,status,manifest=sys.argv[1:]
        path=Path(manifest)
        outputs=[os.fsdecode(name) for name in path.read_bytes().split(b'\0') if name] if path.exists() else []
        publication_result(directory,action,outputs,status)
    else: show_shell_warnings(sys.argv[1])
