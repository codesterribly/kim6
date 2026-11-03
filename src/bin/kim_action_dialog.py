#!/usr/bin/env python3
"""Parameter-only standalone retrofits; Bash retains policy and publication."""
import sys
from pathlib import Path
from PySide6.QtCore import QTimer, QThread, Qt
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QFormLayout,QLabel,
    QDialogButtonBox,QComboBox,QSpinBox,QLineEdit,QCheckBox,QPushButton,QFileDialog,QPlainTextEdit,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QLayout)
from kim_ui import RotationInput, with_help
from kim_recipe_image import copyright_settings


class SourceHeaders(QThread):
    def __init__(self,files,parent):
        super().__init__(parent); self.files=files; self.headers={}; self.error=None

    def run(self):
        import json
        from kim_psd_source import run_process, inspection_context
        from kim_recipe_image import capture_date, canonical_file_type
        try:
            with inspection_context(cancelled=self.isInterruptionRequested):
                for path in self.files:
                    if self.isInterruptionRequested(): break
                    import stat
                    info=Path(path).lstat()
                    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:
                        raise ValueError('Select an unlinked, regular local image: '+Path(path).name)
                    result=run_process(['exiftool','-json','-G1','-ImageWidth','-ImageHeight','-FileType','-DateTimeOriginal','-OffsetTimeOriginal',str(path)],text=True)
                    if result.returncode: raise ValueError('Cannot inspect selected image: '+Path(path).name)
                    record=json.loads(result.stdout)[0]; plain={k.split(':')[-1]:v for k,v in record.items()}
                    raw=record.get('ExifIFD:DateTimeOriginal') or record.get('XMP-exif:DateTimeOriginal')
                    try: capture=capture_date({'DateTimeOriginal':raw,'OffsetTimeOriginal':record.get('ExifIFD:OffsetTimeOriginal')})
                    except ValueError: capture=None
                    self.headers[str(path)]=(plain.get('ImageWidth'),plain.get('ImageHeight'),canonical_file_type(plain.get('FileType')),capture)
        except Exception as exc: self.error=str(exc)


class GeometryPlan(QThread):
    def __init__(self,files,headers,geometry,parent):
        super().__init__(parent); self.files,self.headers,self.geometry=files,headers,geometry; self.lines=[]; self.error=None

    def run(self):
        from kim_psd_source import run_process,inspection_context
        try:
            with inspection_context(cancelled=self.isInterruptionRequested):
                cache={}
                for path in self.files:
                    w,h,*_=self.headers[str(path)]
                    if not w or not h: raise ValueError('Cannot inspect image dimensions: '+Path(path).name)
                    if w*h>100000000: raise ValueError('Source dimensions exceed the 100 megapixel safety limit.')
                    if (w,h) not in cache:
                        from kim_recipe_image import planned_geometry
                        width,height=planned_geometry(w,h,self.geometry)
                        cache[w,h]=f'{width} × {height}'
                    self.lines.append(f'{Path(path).name}: {w} × {h} → {cache[w,h]}')
        except Exception as exc: self.error=str(exc)


class ActionDialog(QDialog):
    def __init__(self, kind, files=(), parent=None, policy='create', preset='custom'):
        super().__init__(parent); self.policy=policy; self.kind=kind; self.files=list(files); self.values=[]; self.fields={}
        self.compression_preset=preset
        self.worker=None; self.headers={}; self.header_error=None; self.closing=False; self.geometry_cache={}
        self.setWindowTitle('KIM6 — '+{'rotate':'Rotate by Custom Angle','resize':'Resize to Custom Size','percent':'Resize by Percentage',
            'convert':'Convert Format','compress':'Compress Custom','copyright':'Set Creator and Copyright','strip':'Remove Metadata','rename':'Rename Images'}[kind])
        self.layout=QVBoxLayout(self)
        if kind=='compress':
            self.setWindowTitle('KIM6 — Compress '+preset.title())
            if preset!='custom':
                notice=QLabel({'recommended':'Starting with Recommended settings. You can adjust the settings before applying.',
                              'maximum':'Starting with Maximum compression settings. You can adjust the settings before applying.'}[preset])
                notice.setWordWrap(True); self.layout.addWidget(notice)
        self.form=QFormLayout(); self.layout.addLayout(self.form)
        if kind=='compress':
            self.setMinimumWidth(520); self.layout.setSizeConstraint(QLayout.SetFixedSize)
        else: self.resize(660,270 if kind=='rotate' else 460)
        self.message=QLabel(); self.message.setWordWrap(True); self.layout.addWidget(self.message)
        if kind=='compress':
            self.preview=QLabel(); self.preview.setWordWrap(True); self.preview.setTextFormat(Qt.PlainText)
            self.preview.setTextInteractionFlags(Qt.TextSelectableByMouse|Qt.TextSelectableByKeyboard)
        else:
            self.preview=QPlainTextEdit(); self.preview.setReadOnly(True)
        self.layout.addWidget(self.preview)
        self.buttons=QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        self.apply=self.buttons.button(QDialogButtonBox.Ok); self.apply.setText('Apply')
        self.buttons.accepted.connect(self.accept); self.buttons.rejected.connect(self.reject); self.layout.addWidget(self.buttons)
        if kind=='rotate':
            self.rotation=RotationInput(45); self.form.addRow('Rotation',self.rotation)
            self.condition=self.choice('condition','Apply to',[('All images',''),('Landscape images','>'),('Portrait images','<')])
            self.message.setText('Positive angles turn right. The angle acts on stored pixels; use Auto-Rotate Using EXIF first when needed. Signed and fractional angles are supported.')
        elif kind in ('resize','percent'):
            if kind=='percent': self.spin('percent','Percentage',1,1000,50)
            else:
                sizes=[300,600,800,1024,1280,1400,1600,1920,2048,2560,3440,3840]
                presets=self.choice('preset','Common sizes',[('Custom bounds','')]+[(f'{s} × {s}',str(s)) for s in sizes])
                self.spin('width','Width (pixels)',1,100000,1600); self.spin('height','Height (pixels)',1,100000,1600)
                self.choice('method','Sizing',[('Resize to Fit','fit'),('Exact Dimensions','exact'),('Custom Geometry','geometry')])
                self.fields['geometry']=QLineEdit('1600x1600>'); self.form.addRow('Custom geometry',self.fields['geometry'])
                self.fields['upscale']=QCheckBox('Allow enlargement'); self.form.addRow(self.fields['upscale'])
                presets.currentIndexChanged.connect(self.size_preset)
                self.form.addRow('Proportions and dimensions',with_help(QLabel('Fit keeps proportions; exact dimensions may stretch.'),'resize'))
                self.message.setText('Custom geometry examples: 1600x1200> (fit without enlargement), 1600x, x1200, 1600x1200! (exact).')
        elif kind=='convert':
            self.apply.setText('Preview Changes…')
            self.choice('format','Output format',[(f.upper(),f) for f in ('jpeg','png','webp','avif','heic','bmp','gif','pdf','tiff','jp2','jxl')])
            self.choice('jp2_mode','JPEG 2000',[('Lossless','lossless'),('Lossy','lossy')]); self.spin('jp2_quality','JPEG 2000 lossy quality',1,100,75)
            self.fields['progressive']=QCheckBox('Progressive JPEG'); self.form.addRow(self.fields['progressive'])
            self.fields['optimize']=QCheckBox('Optimize JPEG Huffman coding'); self.form.addRow(self.fields['optimize'])
            self.fields['strip']=QCheckBox('Explicitly remove metadata for formats that cannot retain it'); self.form.addRow(self.fields['strip'])
            self.form.addRow('Color profile',with_help(QLabel('Source ICC safety is verified before publication.'),'color'))
            self.form.addRow('Encoder quality',with_help(QLabel('JPEG 2000 lossy mode exposes quality.'),'quality'))
            self.message.setText('Format options apply at encoding. Unsupported metadata or ICC preservation stops the affected file with an explanation. Fixed-format menu shortcuts keep their existing behavior.')
        elif kind=='compress':
            self.spin('quality','JPEG / WebP / AVIF quality',1,100,70 if preset=='maximum' else 85)
            self.spin('png','PNG lossless compression level',0,9,9 if preset=='maximum' else 6)
            self.fields['progressive']=QCheckBox('Progressive JPEG'); self.fields['progressive'].setChecked(True)
            self.fields['optimize']=QCheckBox('Optimize JPEG Huffman coding')
            self.jpeg_help_rows={key:with_help(self.fields[key],key) for key in ('progressive','optimize')}
            for row in self.jpeg_help_rows.values(): self.form.addRow(row); self.form.setRowVisible(row,False)
            for key in ('quality','png'): self.form.setRowVisible(self.fields[key],False)
            self.message.setText('Inspecting selected image formats…')
        elif kind=='copyright':
            self.apply.setText('Preview Changes…')
            self.inherited=copyright_settings()
            for field,label in [('creator','Creator / Artist'),('notice','Copyright Notice'),('rights','Usage Rights')]:
                self.fields[field]=QLineEdit(self.inherited[field]); self.form.addRow(label,self.fields[field])
                button=QPushButton('Reset from Settings'); button.clicked.connect(lambda checked=False,k=field:self.reset_setting(k))
                self.form.addRow('',with_help(button,'settings',context='batch'))
            self.message.setText('Blank fields stay unchanged. Effective Settings values are shown; edit to override for this batch. Preview Changes shows existing values and resolved assignments for every image before you apply them.')
        elif kind=='strip':
            self.choice('mode','Remove',[('Descriptive Metadata (keep color and orientation)','all'),('GPS Location','gps'),('Recognized AI Metadata','ai')])
            self.form.addRow('Full removal in Recipes',with_help(QLabel('Recipes also offers Remove All Metadata, including ICC.'),'strip'))
        elif kind=='rename':
            self.choice('method','Method',[(label,value) for label,value in [('Sequential numbering','sequential'),('Rename using Photo Capture Date','exifdate'),('Lowercase','lowercase'),('Uppercase','uppercase'),('Spaces to dashes','spacestodash'),('Spaces to underscores','spacestounderscore'),('Underscores to spaces','underscorestospace'),('Dashes to spaces','dashestospace'),('Add prefix','addprefix'),('Add suffix','addsuffix'),('Replace text','overwrite')]])
            for field,label,default in [('value','Base name','photo_'),('replacement','Replace with','')]:
                self.fields[field]=QLineEdit(default); self.form.addRow(label,self.fields[field])
            self.spin('start','Starting number',0,1000000000,1); self.spin('padding','Minimum digits',1,18,3)
            self.choice('date_format','Date format',[('YYYYMMDD_HHMMSS','compact'),('YYYY-MM-DD_HH-MM-SS','iso'),('YYYY-DD-MM_HH-MM-SS','day_first'),('IMG-YYYYMMDD_HHMMSS','camera')])
            self.rename_method='sequential'; self.rename_states={}
            self.fields['method'].currentIndexChanged.connect(self.rename_method_changed)
            from kim_preview import qt_classes
            self.layout.insertWidget(self.layout.indexOf(self.preview),QLabel('Preview Changes'))
            self.rename_view=qt_classes()[0](self)
            self.rename_table=self.rename_view.table
            self.layout.insertWidget(self.layout.indexOf(self.preview),self.rename_view,1)
            self.resize(1050,650)
            self.apply.setText('Apply Changes')
            self.rename_approved=None; self.rename_pending=False
            self.preview.setMaximumHeight(75)
            self.update_rename_controls()
            self.fields['directory']=QLineEdit(); self.fields['directory'].setPlaceholderText('Beside each source'); self.form.addRow('Destination directory',self.fields['directory'])
            browse=QPushButton('Choose Directory…'); browse.clicked.connect(self.browse); self.form.addRow(browse)
            self.form.addRow('Output filenames',with_help(QLabel('Create renamed copies' if self.policy=='create' else 'Rename selected originals'),'output'))
            self.message.setText('Before → after updates as you edit. '+('New copies protect original files.' if self.policy=='create' else 'You explicitly approved renaming originals; their old names will be removed after publication.')+' Names are checked again when saving.')
        self.timer=QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(100); self.timer.timeout.connect(self.refresh)
        for widget in self.fields.values():
            signal=widget.textChanged if isinstance(widget,QLineEdit) else widget.currentIndexChanged if isinstance(widget,QComboBox) else widget.toggled if isinstance(widget,QCheckBox) else widget.valueChanged
            signal.connect(lambda *_: self.timer.start())
        if kind in ('resize','percent','compress') and self.files:
            self.worker=SourceHeaders(self.files,self); self.worker.finished.connect(self.headers_finished); self.worker.start()
        self.refresh()

    def headers_finished(self):
        worker,self.worker=self.worker,None; self.headers=worker.headers; self.header_error=worker.error; worker.deleteLater()
        if self.closing: super().reject()
        else: self.refresh()

    def geometry_finished(self):
        worker,self.worker=self.worker,None
        self.geometry_cache[worker.geometry]=(worker.lines,worker.error); worker.deleteLater()
        if self.closing: super().reject()
        else: self.refresh()

    def reject(self):
        if self.worker:
            self.closing=True; self.worker.requestInterruption(); self.apply.setEnabled(False)
        else: super().reject()

    def closeEvent(self,event):
        if self.worker: self.reject(); event.ignore()
        else: event.accept()

    def spin(self,key,label,low,high,value):
        w=QSpinBox(); w.setRange(low,high); w.setValue(value); self.fields[key]=w; self.form.addRow(label,w); return w

    def choice(self,key,label,values):
        w=QComboBox()
        for caption,value in values: w.addItem(caption,value)
        self.fields[key]=w; self.form.addRow(label,w); return w

    def rename_method_changed(self,*_):
        # Values belong to a method, so switching through unrelated forms never
        # erases a custom suffix, search string or numbering configuration.
        keys=('value','replacement','start','padding')
        self.rename_states[self.rename_method]=[self.fields[k].text() if isinstance(self.fields[k],QLineEdit) else self.fields[k].value() for k in keys]
        self.rename_method=self.fields['method'].currentData()
        defaults=['_photo' if self.rename_method=='addsuffix' else 'photo_' if self.rename_method in ('addprefix','sequential') else '', '', 1, 3]
        for key,value in zip(keys,self.rename_states.get(self.rename_method,defaults)):
            widget=self.fields[key]
            if isinstance(widget,QLineEdit): widget.setText(value)
            else: widget.setValue(value)
        self.update_rename_controls()
        self.refresh()

    def update_rename_controls(self):
        method=self.fields['method'].currentData()
        labels={'sequential':'Base name','addprefix':'Prefix','addsuffix':'Suffix','overwrite':'Find'}
        if method in labels: self.form.labelForField(self.fields['value']).setText(labels[method])
        for key,visible in {'value':method in labels,'replacement':method=='overwrite',
                            'start':method=='sequential','padding':method=='sequential','date_format':method=='exifdate'}.items():
            self.form.setRowVisible(self.fields[key],visible)

    def reset_setting(self,key): self.fields[key].setText(copyright_settings()[key])

    def browse(self):
        directory=QFileDialog.getExistingDirectory(self,'Rename destination')
        if directory: self.fields['directory'].setText(directory)

    def size_preset(self):
        value=self.fields['preset'].currentData()
        if value:
            for key in ('width','height'): self.fields[key].setValue(int(value))

    def set_preview_text(self,text):
        if self.kind=='compress':
            self.preview.setText(text); self.preview.setVisible(bool(text))
        else: self.preview.setPlainText(text)

    def refresh(self):
        if self.kind=='rename':
            self.start_rename_plan(); return
        if self.worker:
            self.set_preview_text('Inspecting selected files…' if self.kind=='compress' else 'Inspecting selected files / planning dimensions…'); self.apply.setEnabled(False); return
        try:
            if self.header_error: raise ValueError(self.header_error)
            if self.kind=='rotate':
                self.values=[f'{self.rotation.degrees.value():g}'+self.condition.currentData()]
                lines=['90° Left = −90°; 90° Right = +90°; 180° = half turn.']
            elif self.kind in ('resize','percent'):
                if self.kind=='percent': geometry=str(self.fields['percent'].value())+'%'
                else:
                    method=self.fields['method'].currentData()
                    geometry=(self.fields['geometry'].text() if method=='geometry' else
                              f"{self.fields['width'].value()}x{self.fields['height'].value()}"+('!' if method=='exact' else ''))
                    if method!='geometry' and not self.fields['upscale'].isChecked(): geometry+='>'
                from kim_recipe_image import ImageHandler
                if not geometry.endswith('%'): ImageHandler().validate_step({'op':'image.resize_geometry','geometry':geometry})
                self.values=[geometry]; lines=['Planned geometry: '+geometry,'Original proportions are retained unless ! (Exact Dimensions) is used.']
                if self.files and geometry not in self.geometry_cache:
                    self.worker=GeometryPlan(self.files,self.headers,geometry,self)
                    self.worker.finished.connect(self.geometry_finished); self.worker.start()
                    self.set_preview_text('Planning dimensions…'); self.apply.setEnabled(False); return
                planned,error=self.geometry_cache.get(geometry,([],None))
                if error: raise ValueError(error)
                lines+=planned
            elif self.kind=='convert':
                fmt=self.fields['format'].currentData()
                self.form.setRowVisible(self.fields['jp2_mode'],fmt=='jp2'); self.form.setRowVisible(self.fields['jp2_quality'],fmt=='jp2' and self.fields['jp2_mode'].currentData()=='lossy')
                for key in ('progressive','optimize'): self.form.setRowVisible(self.fields[key],fmt=='jpeg')
                self.values=[fmt,self.fields['jp2_mode'].currentData(),str(self.fields['jp2_quality'].value()),'Plane' if self.fields['progressive'].isChecked() else 'None','true' if self.fields['optimize'].isChecked() else 'false','true' if self.fields['strip'].isChecked() else 'false']
                lines=[('JPEG/BMP/PDF use an opaque background. PSD inputs are explicitly flattened onto white by their shared source adapter.' if fmt in ('jpeg','bmp','pdf') else
                        'Transparency is retained where supported; GIF uses palette transparency.'),
                       'ICC profiles are preserved where the encoder can carry them; incompatible outputs are refused rather than silently losing the profile.']
            elif self.kind=='compress':
                self.values=[str(self.fields['quality'].value()),str(self.fields['png'].value()),'Plane' if self.fields['progressive'].isChecked() else 'None','true' if self.fields['optimize'].isChecked() else 'false']
                formats={record[2] for record in self.headers.values()}
                # Only applicable, approved encoder values determine adjustment.
                baseline_quality,baseline_png=(70,9) if self.compression_preset=='maximum' else (85,6)
                adjusted=(bool(formats & {'JPEG','WEBP','AVIF'}) and self.fields['quality'].value()!=baseline_quality or
                          'PNG' in formats and self.fields['png'].value()!=baseline_png or
                          'JPEG' in formats and (not self.fields['progressive'].isChecked() or self.fields['optimize'].isChecked()))
                self.values.append('true' if adjusted else 'false')
                lossy=[name for fmt,name in (('JPEG','JPEG'),('WEBP','WebP'),('AVIF','AVIF')) if fmt in formats]
                self.form.setRowVisible(self.fields['quality'],bool(lossy))
                self.form.setRowVisible(self.fields['png'],'PNG' in formats)
                for row in self.jpeg_help_rows.values(): self.form.setRowVisible(row,'JPEG' in formats)
                self.form.labelForField(self.fields['quality']).setText(' / '.join(lossy)+(' quality' if lossy==['JPEG'] else ' lossy quality'))
                info=[]
                if 'PNG' in formats: info.append('PNG compression is lossless.')
                if lossy: info.append(' / '.join(lossy)+' quality controls lossy compression.')
                info.append('Each file keeps its format.')
                self.message.setText(' '.join(info))
                unsupported=[Path(path).name for path,record in self.headers.items() if record[2] not in ('JPEG','PNG','WEBP','AVIF')]
                if unsupported: raise ValueError('Compression supports JPEG, PNG, WebP and AVIF. Convert these files first: '+', '.join(unsupported))
                lines=['Re-encoding does not guarantee a smaller file. EXIF metadata and ICC color profiles are preserved, but other descriptive metadata may be removed.']
            elif self.kind=='copyright':
                self.values=[self.fields[k].text() for k in ('creator','notice','rights')]
                if not any(self.values): raise ValueError('Enter at least one creator, copyright or usage-rights value, or reset from Settings.')
                lines=['Values are resolved for each selected image in Preview Changes. {YEAR} in Copyright Notice uses its capture year, or the current year when missing. Blank fields preserve existing values.']
            elif self.kind=='strip':
                value=self.fields['mode'].currentData(); self.values=[value]
                lines=[{'all':'Removes descriptive EXIF, IPTC, XMP and comments. Keeps ICC color profiles and orientation. File Modification Dates and encoded image data are preserved.',
                        'gps':'Removes recognized GPS and location coordinates. Keeps other metadata, ICC, orientation and file dates.',
                        'ai':'Removes recognized AI-generation fields. Unrecognized provenance and signed Content Credentials may remain. Keeps ICC, orientation and file dates.'}[value]]
            self.set_preview_text('\n'.join(lines)); self.apply.setEnabled(True)
        except Exception as exc:
            self.set_preview_text(str(exc)); self.apply.setEnabled(False)
            if self.kind=='rename': self.rename_table.setRowCount(0)

    def start_rename_plan(self):
        self.apply.setEnabled(False)
        if self.worker:
            self.rename_pending=True; self.worker.requestInterruption(); return
        self.rename_pending=False
        method=self.fields['method'].currentData()
        value=self.fields['date_format'].currentData() if method=='exifdate' else self.fields['value'].text()
        config=dict(method=method,value=value,replacement=self.fields['replacement'].text(),
                    start=self.fields['start'].value(),padding=self.fields['padding'].value(),directory=self.fields['directory'].text())
        self.values=[method,'--parameters',value,config['replacement'],str(config['start']),str(config['padding'])]
        if config['directory']: self.values+=['--output-dir',config['directory']]
        from kim_preview import qt_classes
        self.worker=qt_classes()[1]('rename',self.policy,self.files,config,None,self)
        self.worker.progress.connect(lambda i,n,p:self.rename_view.summary.setText(f'Preview Changes — inspecting image {i+1} of {n}: {Path(p).name}'))
        self.worker.finished.connect(self.rename_finished); self.worker.start()
        self.set_preview_text('Preview Changes — planning filenames…')

    def rename_finished(self):
        worker,self.worker=self.worker,None
        if self.closing: worker.deleteLater(); super().reject(); return
        if self.rename_pending: worker.deleteLater(); self.start_rename_plan(); return
        if worker.error: self.set_preview_text(worker.error)
        else:
            self.rename_approved=worker.plan
            self.apply.setEnabled(self.rename_view.show_plan(worker.plan))
            self.set_preview_text('Preview Changes — final paths are available in each row’s tooltip. Changed sources or destinations require a fresh review.')
        worker.deleteLater()

    def accept(self):
        if self.kind=='rename':
            if self.timer.isActive(): self.timer.stop(); self.start_rename_plan(); return
            if not self.apply.isEnabled(): return
            from kim_preview import verify_plan
            try: verify_plan(self.rename_approved)
            except Exception as exc:
                self.set_preview_text(str(exc)+' Review the updated plan before applying.'); self.start_rename_plan(); return
        else: self.refresh()
        if self.apply.isEnabled(): super().accept()


def main():
    kind,result,*files=sys.argv[1:]; initial=None; policy='create'; preset='custom'
    if kind=='compress' and files[:1]==['--preset']:
        _,preset,*files=files
        if preset not in ('recommended','maximum','custom'): raise ValueError('Invalid compression preset')
    if kind=='rename' and files and files[0] in ('create','overwrite'): policy=files.pop(0)
    if kind=='strip' and files and files[0] in ('all','gps','ai'): initial=files.pop(0)
    app=QApplication(sys.argv[:1]); dialog=ActionDialog(kind,files,policy=policy,preset=preset)
    if initial is not None: dialog.fields['mode'].setCurrentIndex(dialog.fields['mode'].findData(initial)); dialog.refresh()
    if dialog.exec()!=QDialog.Accepted: return 130 if kind in ('convert','copyright','strip','rename') else 1
    if kind=='rename':
        from kim_preview import save_plan
        save_plan(result+'.approved',dialog.rename_approved)
    Path(result).write_bytes(b''.join(v.encode()+b'\0' for v in dialog.values)); return 0


if __name__=='__main__': raise SystemExit(main())
