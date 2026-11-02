#!/usr/bin/env python3
"""Parameter-only standalone retrofits; Bash retains policy and publication."""
import sys
from pathlib import Path
from PySide6.QtCore import QTimer, QThread
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QFormLayout,QLabel,
    QDialogButtonBox,QComboBox,QSpinBox,QLineEdit,QCheckBox,QPushButton,QFileDialog,QPlainTextEdit,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView)
from kim_ui import RotationInput, with_help
from kim_recipe_image import copyright_settings, COPYRIGHT_TAGS


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
    def __init__(self, kind, files=(), parent=None, policy='create'):
        super().__init__(parent); self.policy=policy; self.kind=kind; self.files=list(files); self.values=[]; self.fields={}
        self.worker=None; self.headers={}; self.header_error=None; self.closing=False; self.geometry_cache={}
        self.setWindowTitle('KIM6 — '+{'rotate':'Rotate by Custom Angle','resize':'Resize to Custom Size','percent':'Resize by Percentage',
            'convert':'Convert Format','compress':'Compress Custom','copyright':'Set Creator and Copyright','strip':'Remove Metadata','rename':'Rename Images'}[kind])
        self.resize(660,270 if kind=='rotate' else 460); self.layout=QVBoxLayout(self); self.form=QFormLayout(); self.layout.addLayout(self.form)
        self.message=QLabel(); self.message.setWordWrap(True); self.layout.addWidget(self.message)
        self.preview=QPlainTextEdit(); self.preview.setReadOnly(True); self.layout.addWidget(self.preview)
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
            self.choice('format','Output format',[(f.upper(),f) for f in ('jpeg','png','webp','avif','heic','bmp','gif','pdf','tiff','jp2','jxl')])
            self.choice('jp2_mode','JPEG 2000',[('Lossless','lossless'),('Lossy','lossy')]); self.spin('jp2_quality','JPEG 2000 lossy quality',1,100,75)
            self.fields['progressive']=QCheckBox('Progressive JPEG'); self.form.addRow(self.fields['progressive'])
            self.fields['optimize']=QCheckBox('Optimize JPEG Huffman coding'); self.form.addRow(self.fields['optimize'])
            self.fields['strip']=QCheckBox('Explicitly remove metadata for formats that cannot retain it'); self.form.addRow(self.fields['strip'])
            self.form.addRow('Color profile',with_help(QLabel('Source ICC safety is verified before publication.'),'color'))
            self.form.addRow('Encoder quality',with_help(QLabel('JPEG 2000 lossy mode exposes quality.'),'quality'))
            self.message.setText('Format options apply at encoding. Unsupported metadata or ICC preservation stops the affected file with an explanation. Fixed-format menu shortcuts keep their existing behavior.')
        elif kind=='compress':
            self.spin('quality','JPEG / WebP / AVIF quality',1,100,85); self.spin('png','PNG lossless level',0,9,6)
            self.fields['progressive']=QCheckBox('Progressive JPEG'); self.fields['progressive'].setChecked(True); self.form.addRow(self.fields['progressive'])
            self.fields['optimize']=QCheckBox('Optimize JPEG Huffman coding'); self.form.addRow(self.fields['optimize'])
            self.form.addRow('Compression quality',with_help(QLabel('Each file keeps its supported format.'),'quality'))
            self.form.addRow('Color profile',with_help(QLabel('Embedded ICC profiles are retained.'),'color'))
            self.message.setText('JPEG, PNG, WebP and AVIF only. PNG compression is lossless; quality applies to lossy formats. Transparency stays supported in PNG/WebP/AVIF. Compression may not make a smaller file. Descriptive fields other than EXIF may be removed by this standalone compressor.')
        elif kind=='copyright':
            self.inherited=copyright_settings()
            for field,label in [('creator','Creator / Artist'),('notice','Copyright Notice'),('rights','Usage Rights')]:
                self.fields[field]=QLineEdit(self.inherited[field]); self.form.addRow(label,self.fields[field])
                button=QPushButton('Reset from Settings'); button.clicked.connect(lambda checked=False,k=field:self.reset_setting(k))
                self.form.addRow('',with_help(button,'settings',context='batch'))
            self.message.setText('Blank fields stay unchanged. This updates embedded creator/copyright fields only, preserving file dates, pixels and color profiles. Effective Settings values are shown; edit to override for this batch.')
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
            self.rename_table=QTableWidget(0,4)
            self.rename_table.setHorizontalHeaderLabels(['Source filename','→ Planned filename','Destination directory','Source directory'])
            self.rename_table.setWordWrap(False); self.rename_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            self.rename_table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            self.rename_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
            self.layout.insertWidget(self.layout.indexOf(self.preview),self.rename_table,1)
            self.preview.setMaximumHeight(75)
            self.update_rename_controls()
            self.fields['directory']=QLineEdit(); self.fields['directory'].setPlaceholderText('Beside each source'); self.form.addRow('Destination directory',self.fields['directory'])
            browse=QPushButton('Choose Directory…'); browse.clicked.connect(self.browse); self.form.addRow(browse)
            self.form.addRow('Output filenames',with_help(QLabel('Preview uses new copies with numbered collisions.'),'output'))
            self.message.setText('Before → after updates as you edit. '+('New copies protect original files.' if self.policy=='create' else 'You explicitly approved renaming originals; their old names will be removed after publication.')+' Names are checked again when saving.')
        self.timer=QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(100); self.timer.timeout.connect(self.refresh)
        for widget in self.fields.values():
            signal=widget.textChanged if isinstance(widget,QLineEdit) else widget.currentIndexChanged if isinstance(widget,QComboBox) else widget.toggled if isinstance(widget,QCheckBox) else widget.valueChanged
            signal.connect(lambda *_: self.timer.start())
        if kind in ('resize','percent','compress','rename','copyright') and self.files:
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

    def refresh(self):
        if self.worker:
            self.preview.setPlainText('Inspecting selected files / planning dimensions…'); self.apply.setEnabled(False); return
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
                    self.preview.setPlainText('Planning dimensions…'); self.apply.setEnabled(False); return
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
                if formats:
                    self.fields['quality'].setEnabled(bool(formats & {'JPEG','WEBP','AVIF'}))
                    self.fields['png'].setEnabled('PNG' in formats)
                    for key in ('progressive','optimize'): self.fields[key].setEnabled('JPEG' in formats)
                unsupported=[Path(path).name for path,record in self.headers.items() if record[2] not in ('JPEG','PNG','WEBP','AVIF')]
                if unsupported: raise ValueError('Compress Custom supports JPEG, PNG, WebP and AVIF. Convert these files first: '+', '.join(unsupported))
                lines=['One encoder per file; source format is retained.']
            elif self.kind=='copyright':
                self.values=[self.fields[k].text() for k in ('creator','notice','rights')]
                if not any(self.values): raise ValueError('Enter at least one creator, copyright or usage-rights value, or reset from Settings.')
                from kim_recipe_image import NO_LEGACY_IPTC
                unsupported=[Path(p).name for p,info in self.headers.items() if info[2] not in ('JPEG','PNG','TIFF','WEBP','HEIC','HEIF','AVIF','JXL','JP2','PSD')]
                if unsupported: raise ValueError('These files cannot safely store the selected rights fields. Use JPEG, PNG or TIFF: '+', '.join(unsupported))
                formats={info[2].lower() for info in self.headers.values()} or {'jpeg'}
                lines=[fmt.upper()+': '+tag+' → '+self.fields[field].text() for fmt in sorted(formats) for field,tags in COPYRIGHT_TAGS.items() if self.fields[field].text() for tag in tags if not (fmt in NO_LEGACY_IPTC and tag.startswith('IPTC:'))]
            elif self.kind=='strip':
                value=self.fields['mode'].currentData(); self.values=[value]
                lines=[{'all':'Removes descriptive EXIF, IPTC, XMP and comments. Keeps ICC color profiles and orientation. File Modification Dates and encoded image data are preserved.',
                        'gps':'Removes recognized GPS and location coordinates. Keeps other metadata, ICC, orientation and file dates.',
                        'ai':'Removes recognized AI-generation fields. Unrecognized provenance and signed Content Credentials may remain. Keeps ICC, orientation and file dates.'}[value]]
            else:
                self.values,lines=self.rename_plan()
                self.rename_table.setRowCount(len(self.rename_rows))
                for row,values in enumerate(self.rename_rows):
                    for column,value in enumerate(values): self.rename_table.setItem(row,column,QTableWidgetItem(value))
            self.preview.setPlainText('\n'.join(lines)); self.apply.setEnabled(True)
        except Exception as exc:
            self.preview.setPlainText(str(exc)); self.apply.setEnabled(False)
            if self.kind=='rename': self.rename_table.setRowCount(0)

    def rename_plan(self):
        method=self.fields['method'].currentData(); value=self.fields['value'].text(); replacement=self.fields['replacement'].text()
        start=self.fields['start'].value(); padding=self.fields['padding'].value(); directory=self.fields['directory'].text()
        if directory and (not Path(directory).is_absolute() or not Path(directory).is_dir()): raise ValueError('Choose an existing absolute destination directory.')
        if method=='exifdate': value=self.fields['date_format'].currentData()
        options=[method,'--parameters',value,replacement,str(start),str(padding)]
        if directory: options+=['--output-dir',directory]
        reserved=set(); lines=[]; number=start; self.rename_rows=[]
        for path in map(Path,self.files):
            if method=='exifdate':
                capture=self.headers[str(path)][3]
                if capture is None: raise ValueError('No Photo Capture Date found in '+path.name+'. Set Photo Capture Date first.')
                from kim_filename import DATE_FORMATS
                name=capture.strftime(DATE_FORMATS[value])
            else:
                from kim_filename import standalone
                name=standalone(path.stem,method,value,replacement,number,padding)
            if not name or name in ('.','..') or '/' in name or '\n' in name or '\r' in name: raise ValueError('Enter a filename without slashes or line breaks.')
            parent=Path(directory) if directory else path.parent; target=parent/(name+path.suffix); n=0
            while target.exists() or target.is_symlink() or str(target) in reserved:
                if self.policy=='overwrite' and target==path: break
                if self.policy=='overwrite' and method not in ('sequential','exifdate'):
                    raise ValueError('The planned name is occupied: '+str(target)+'. Choose another filename or create copies instead.')
                n+=1
                if method=='sequential': number+=1; target=parent/(value+str(number).zfill(padding)+path.suffix)
                else: target=parent/(name+'_'+str(n)+path.suffix)
            reserved.add(str(target)); lines.append(path.name+' → '+str(target))
            self.rename_rows.append((path.name,target.name,str(target.parent),str(path.parent))); number+=1
        lines=['Planned copies: '+str(len(self.rename_rows))+'. Occupied names receive a number; names are checked again when saving.']
        return options,lines

    def accept(self):
        self.refresh()
        if self.apply.isEnabled(): super().accept()


def main():
    kind,result,*files=sys.argv[1:]; initial=None; policy='create'
    if kind=='rename' and files and files[0] in ('create','overwrite'): policy=files.pop(0)
    if kind=='strip' and files and files[0] in ('all','gps','ai'): initial=files.pop(0)
    app=QApplication(sys.argv[:1]); dialog=ActionDialog(kind,files,policy=policy)
    if initial is not None: dialog.fields['mode'].setCurrentIndex(dialog.fields['mode'].findData(initial)); dialog.refresh()
    if dialog.exec()!=QDialog.Accepted: return 1
    Path(result).write_bytes(b''.join(v.encode()+b'\0' for v in dialog.values)); return 0


if __name__=='__main__': raise SystemExit(main())
