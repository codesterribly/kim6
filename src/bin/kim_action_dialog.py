#!/usr/bin/env python3
"""Parameter-only standalone retrofits; Bash retains policy and publication."""
import sys
from pathlib import Path
from PySide6.QtCore import QTimer, QThread, Qt, QSize
from PySide6.QtWidgets import (QApplication,QDialog,QVBoxLayout,QFormLayout,QLabel,
    QDialogButtonBox,QComboBox,QSpinBox,QLineEdit,QCheckBox,QPushButton,QFileDialog,QPlainTextEdit,
    QTableWidget,QTableWidgetItem,QHeaderView,QAbstractItemView,QLayout,QHBoxLayout,QWidget)
from kim_ui import RotationInput, with_help
from PySide6.QtGui import QPixmap, QTransform
from kim_recipe_image import copyright_settings
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon, QPixmap, QTransform
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QScrollArea,
    QDoubleSpinBox, QFrame, QButtonGroup
)


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
        self.setWindowTitle('KIM6 — '+{'rotate':'Rotate','resize':'Resize to Custom Size','percent':'Resize by Percentage',
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
            self.rotate_exif = preset == 'EXIF'
            starting_angle = (
                0 if self.rotate_exif else
                45 if preset == 'custom' else float(preset)
            )

            self.rotation = RotationInput(starting_angle)
            self.form.addRow('Rotation', self.rotation)

            self.condition = QComboBox()
            self.condition.addItem('All selected images', '')

            self.form.setRowVisible(
                self.rotation, not self.rotate_exif
            )

            self.rotate_selector = QComboBox()
            for filename in self.files:
                self.rotate_selector.addItem(
                    Path(filename).name, filename
                )
            self.form.addRow('Preview image', self.rotate_selector)

            panel = QWidget()
            image_row = QHBoxLayout(panel)
            image_row.setContentsMargins(0, 0, 0, 0)
            image_row.setSpacing(10)

            self.before_picture = QLabel('Loading source preview…')
            self.after_picture = QLabel('Loading rotated preview…')

            for label in (
                self.before_picture,
                self.after_picture
            ):
                label.setAlignment(Qt.AlignCenter)
                label.setMinimumSize(230, 190)
                label.setWordWrap(True)

            image_row.addWidget(self.before_picture)
            image_row.addWidget(self.after_picture)

            self.layout.insertWidget(self.layout.indexOf(self.message), panel, 0)
            # The images are the preview. Remove the empty text area.
            self.preview.hide()
            self.message.hide()

            self.before_picture.setMinimumSize(290, 250)
            self.after_picture.setMinimumSize(290, 250)

            self.resize(790, 490)

            self.message.setText(
                'Left: original image. Right: proposed rotation. '
                'Review the result before applying.'
            )

            self.rotate_selector.currentIndexChanged.connect(
                self.update_rotation_preview
            )
            self.rotation.degrees.valueChanged.connect(
                self.update_rotation_preview
            )
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
            self.format_profile_note = QLabel()
            self.format_profile_note.setWordWrap(True)
            self.form.addRow('Color profile', self.format_profile_note)

            self.format_quality_note = QLabel()
            self.format_quality_note.setWordWrap(True)
            self.form.addRow('Encoder quality', self.format_quality_note)

            self.message.setText('')

            self.convert_selector = QComboBox()

            for filename in self.files:
                self.convert_selector.addItem(
                    Path(filename).name,
                    filename
                )

            self.form.addRow(
                'Source image',
                self.convert_selector
            )

            self.convert_picture = QLabel(
                'Source image preview'
            )
            self.convert_picture.setAlignment(Qt.AlignCenter)
            self.convert_picture.setMinimumHeight(180)
            self.convert_picture.setMaximumHeight(280)
            self.convert_picture.setWordWrap(True)

            self.layout.insertWidget(
                self.layout.indexOf(self.buttons),
                self.convert_picture,
                1
            )

            # The source image replaces the generic text preview.
            self.preview.hide()
            self.resize(760, 490)

            self.convert_selector.currentIndexChanged.connect(
                self.update_convert_preview
            )

            # Initialize after Qt has constructed the full dialog.
            QTimer.singleShot(
                0,
                self.update_convert_preview
            )

        elif kind=='compress':
            self.spin('quality','JPEG / WebP / AVIF quality',1,100,70 if preset=='maximum' else 85)
            self.spin('png','Compression level',0,9,9 if preset=='maximum' else 6)
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



    def update_convert_preview(self, *_):
        """Display a bounded source thumbnail without altering pixels."""
        if self.kind != 'convert':
            return

        filename = self.convert_selector.currentData()

        if not filename:
            self.convert_picture.clear()
            self.convert_picture.setText('No image selected')
            return

        try:
            from kim_photo_selection import read_thumbnail

            image, _identity = read_thumbnail(
                filename,
                QSize(460, 270)
            )

            if image.isNull():
                raise ValueError('No thumbnail decoder')

            pixmap = QPixmap.fromImage(image)

            self.convert_picture.setPixmap(
                pixmap.scaled(
                    460,
                    270,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )

            self.convert_picture.setToolTip(
                'Source image: ' + Path(filename).name
            )

        except Exception as exc:
            self.convert_picture.clear()
            self.convert_picture.setText(
                'Source preview unavailable for this format'
            )
            self.convert_picture.setToolTip(str(exc))

    def update_rotation_preview(self, *_):
        """Inspect only bounded thumbnails. Never write source pixels."""
        if self.kind != 'rotate':
            return True

        selected = self.rotate_selector.currentData()

        if not selected:
            self.before_picture.setText('No image selected')
            self.after_picture.setText('No image selected')
            return False

        from kim_photo_selection import read_thumbnail

        try:
            original, stamp = read_thumbnail(
                selected, QSize(360, 260), auto_orient=False
            )

            if self.rotate_exif:
                rotated, second_stamp = read_thumbnail(
                    selected, QSize(360, 260), auto_orient=True
                )
                if stamp != second_stamp:
                    raise ValueError('Image changed during inspection')
            else:
                angle = self.rotation.degrees.value()
                rotated = original.transformed(
                    QTransform().rotate(angle),
                    Qt.SmoothTransformation
                )

            if original.isNull() or rotated.isNull():
                raise ValueError('Preview decoder unavailable')

            left = QPixmap.fromImage(original)
            right = QPixmap.fromImage(rotated)

            self.before_picture.setPixmap(
                left.scaled(
                    340, 245,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )

            self.after_picture.setPixmap(
                right.scaled(
                    340, 245,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )
            )

            self.before_picture.setToolTip('Before rotation')
            self.after_picture.setToolTip('After rotation')
            return True

        except Exception as exc:
            self.before_picture.setText(
                'Preview unavailable: ' + str(exc)
            )
            self.after_picture.setText(
                'No verified preview available'
            )
            return False

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
                self.values = (
                    ['EXIF'] if self.rotate_exif else
                    [
                        f'{self.rotation.degrees.value():g}'
                        + self.condition.currentData()
                    ]
                )

                if not self.update_rotation_preview():
                    raise ValueError(
                        'Cannot safely preview the selected image.'
                    )

                lines = []
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
                for key in ('progressive','optimize'):
                    self.form.setRowVisible(self.fields[key],fmt=='jpeg')

                descriptions = {
                    'jpeg': 'JPEG uses lossy compression and does not support transparency.',
                    'png': 'PNG preserves full-color pixels and transparency using lossless encoding.',
                    'webp': 'WebP supports modern image compression and transparency.',
                    'avif': 'AVIF supports high-efficiency image compression and transparency.',
                    'heic': 'HEIC output depends on the installed HEIF encoder. Unsupported metadata or profiles will be reported.',
                    'bmp': 'BMP creates a widely compatible, typically uncompressed raster image.',
                    'gif': 'GIF uses a limited color palette and supports binary transparency.',
                    'pdf': 'PDF creates a document containing the converted image.',
                    'tiff': 'TIFF supports high-quality raster storage and metadata.',
                    'jp2': 'JPEG 2000 supports lossless and lossy encoding.',
                    'jxl': 'JPEG XL is a modern image format with lossless and lossy capabilities.',
                }

                profile_notes = {
                    'jpeg': 'Preserve the compatible source ICC profile.',
                    'png': 'Preserve the compatible source ICC profile.',
                    'webp': 'Preserve the compatible source ICC profile.',
                    'avif': 'Verify compatible ICC/profile handling.',
                    'heic': 'Verify compatible ICC/profile handling.',
                    'bmp': 'Color-profile support is restricted for this output.',
                    'gif': 'Color and palette limitations apply.',
                    'pdf': 'Color handling depends on the generated PDF.',
                    'tiff': 'Preserve the compatible source ICC profile.',
                    'jp2': 'Verify compatible JPEG 2000 color-profile handling.',
                    'jxl': 'Verify compatible JPEG XL color-profile handling.',
                }

                self.format_profile_note.setText(profile_notes[fmt])
                self.format_quality_note.setText(
                    'JPEG 2000 lossy quality applies only in Lossy mode.'
                    if fmt == 'jp2' and
                       self.fields['jp2_mode'].currentData() == 'lossy'
                    else 'Lossless mode does not expose a quality setting.'
                    if fmt == 'jp2' else ''
                )
                self.form.setRowVisible(
                    self.format_quality_note, fmt == 'jp2'
                )

                self.message.setText(descriptions[fmt])

                self.values=[fmt,self.fields['jp2_mode'].currentData(),str(self.fields['jp2_quality'].value()),'Plane' if self.fields['progressive'].isChecked() else 'None','true' if self.fields['optimize'].isChecked() else 'false','true' if self.fields['strip'].isChecked() else 'false']
                lines = [descriptions[fmt]]
                if fmt in ('jpeg', 'bmp', 'pdf'):
                    lines.append(
                        'Transparent source areas use an opaque background.'
                    )
                elif fmt == 'gif':
                    lines.append(
                        'Transparency is limited by GIF palette encoding.'
                    )
                else:
                    lines.append(
                        'Transparency is retained where the selected encoder supports it.'
                    )
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
                if 'PNG' in formats: info.append('PNG compression is lossless. No image data is lost by compressing.')
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



class RotateBatchDialog(QDialog):
    """Review one independent rotation per image before publication."""

    CHOICES = (
        ('90° CCW', '270', 'object-rotate-left'),
        ('90° CW', '90', 'object-rotate-right'),
        ('180°', '180', 'object-flip-vertical'),
        ('Custom', 'custom', 'transform-rotate'),
        ('EXIF', 'EXIF', 'transform-rotate'),
        ('Skip', 'SKIP', 'process-stop'),
    )

    def __init__(self, files, preset):
        super().__init__()

        self.setWindowTitle('KIM6 — Rotate Images')
        self.resize(970, 630)
        self.setMinimumWidth(790)

        self.rows = []
        self.pending = []

        outer = QVBoxLayout(self)

        headline = QLabel(
            f'{len(files)} selected image(s). '
            'Choose a rotation for each image.'
        )
        outer.addWidget(headline)

        # Toolbar for assigning the same rotation to every image.
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel('Apply to all:'))

        for caption, mode, icon_name in self.CHOICES:
            button = QPushButton(caption)
            icon = QIcon.fromTheme(icon_name)

            if not icon.isNull():
                button.setIcon(icon)

            button.clicked.connect(
                lambda _checked=False, value=mode:
                self.set_all(value)
            )
            toolbar.addWidget(button)

        toolbar.addStretch(1)
        outer.addLayout(toolbar)

        headers = QHBoxLayout()

        for text, width in (
            ('Source', 265),
            ('Rotation', 385),
            ('Result', 160),
        ):
            label = QLabel(text)
            label.setMinimumWidth(width)
            headers.addWidget(label)

        headers.addStretch(1)
        outer.addLayout(headers)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        self.list_layout = QVBoxLayout(container)
        self.list_layout.setSpacing(5)
        self.list_layout.setContentsMargins(4, 4, 4, 4)

        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        for path in files:
            self.add_row(path, preset)

        self.list_layout.addStretch(1)

        self.status = QLabel('Loading source previews…')
        outer.addWidget(self.status)

        controls = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        self.apply = controls.button(QDialogButtonBox.Ok)
        self.apply.setText('Apply Changes')
        self.apply.setEnabled(False)

        controls.accepted.connect(self.accept)
        controls.rejected.connect(self.reject)

        outer.addWidget(controls)

        # Process one thumbnail per event-loop turn, keeping the
        # dialog responsive while reviewing a larger selection.
        self.pending = list(self.rows)
        QTimer.singleShot(0, self.load_next)

    def add_row(self, path, preset):
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)

        line = QHBoxLayout(frame)
        line.setContentsMargins(6, 6, 6, 6)
        line.setSpacing(7)

        original = QLabel('Loading…')
        result = QLabel('Loading…')

        for label in (original, result):
            label.setFixedSize(145, 112)
            label.setAlignment(Qt.AlignCenter)
            label.setWordWrap(True)

        name = QLabel(Path(path).name)
        name.setToolTip(path)
        name.setWordWrap(True)
        name.setMaximumWidth(125)
        name.setMinimumWidth(110)

        left = QHBoxLayout()
        left.addWidget(original)
        left.addWidget(name, 1)
        line.addLayout(left, 3)

        center = QVBoxLayout()
        buttons = QHBoxLayout()
        button_group = QButtonGroup(self)

        row = {
            'path': path,
            'mode': preset,
            'original': original,
            'result': result,
            'source': None,
            'oriented': None,
            'stamp': None,
            'error': None,
            'result_error': None,
            'controls': {},
            'custom': None,
        }

        for caption, mode, icon_name in self.CHOICES:
            button = QPushButton(caption)
            button.setCheckable(True)
            button.setMinimumHeight(29)
            button.setToolTip(caption)

            icon = QIcon.fromTheme(icon_name)

            if not icon.isNull():
                button.setIcon(icon)

            button_group.addButton(button)
            row['controls'][mode] = button

            button.clicked.connect(
                lambda _checked=False, current=row, value=mode:
                self.set_mode(current, value)
            )

            buttons.addWidget(button)

        center.addLayout(buttons)

        degrees = QDoubleSpinBox()
        degrees.setDecimals(3)
        degrees.setRange(-360, 360)
        degrees.setSuffix('°')
        degrees.setValue(45)
        degrees.setSingleStep(1)

        degrees.valueChanged.connect(
            lambda _value, current=row:
            self.update_result(current)
        )

        center.addWidget(degrees)
        row['custom'] = degrees

        line.addLayout(center, 5)
        line.addWidget(result, 2)

        self.list_layout.addWidget(frame)
        self.rows.append(row)

        self.set_mode(row, preset)

    def set_all(self, mode):
        for row in self.rows:
            self.set_mode(row, mode)

    def set_mode(self, row, mode):
        row['mode'] = mode

        for key, button in row['controls'].items():
            button.setChecked(key == mode)

        row['custom'].setVisible(mode == 'custom')
        self.update_result(row)

    def selected_angle(self, row):
        if row['mode'] == 'custom':
            return f"{row['custom'].value():g}"

        return row['mode']

    def planned_angles(self):
        return [
            self.selected_angle(row)
            for row in self.rows
        ]

    def load_next(self):
        if not self.pending:
            self.update_state()
            return

        row = self.pending.pop(0)

        try:
            from kim_photo_selection import read_thumbnail

            source, stamp = read_thumbnail(
                row['path'],
                QSize(150, 112),
                auto_orient=False
            )

            if source.isNull():
                raise ValueError(
                    'No supported source thumbnail decoder'
                )

            row['source'] = source
            row['stamp'] = stamp

            self.display_image(
                row['original'],
                source
            )

            self.update_result(row)

        except Exception as exc:
            row['error'] = str(exc)
            row['original'].setText(
                'Preview unavailable'
            )
            row['original'].setToolTip(str(exc))
            row['result'].setText(
                'Cannot verify result'
            )

        self.update_state()

        if self.pending:
            QTimer.singleShot(0, self.load_next)

    @staticmethod
    def display_image(label, image):
        pixmap = QPixmap.fromImage(image)

        label.setPixmap(
            pixmap.scaled(
                label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
        )

    def update_result(self, row):
        if row['source'] is None:
            self.update_state()
            return

        if row['error']:
            self.update_state()
            return

        row['result_error'] = None

        try:
            mode = row['mode']

            if mode == 'EXIF':
                if row['oriented'] is None:
                    from kim_photo_selection import read_thumbnail

                    oriented, stamp = read_thumbnail(
                        row['path'],
                        QSize(150, 112),
                        auto_orient=True
                    )

                    if stamp != row['stamp'] or oriented.isNull():
                        raise ValueError(
                            'Image changed or EXIF preview unavailable'
                        )

                    row['oriented'] = oriented

                output = row['oriented']

            elif mode == 'SKIP':
                output = row['source']

            else:
                angle = float(
                    self.selected_angle(row)
                )

                output = row['source'].transformed(
                    QTransform().rotate(angle),
                    Qt.SmoothTransformation
                )

            self.display_image(
                row['result'],
                output
            )

            row['result'].setToolTip(
                'No change' if mode == 'SKIP'
                else f'Rotation: {self.selected_angle(row)}'
            )

        except Exception as exc:
            row['result_error'] = str(exc)
            row['result'].clear()
            row['result'].setText(
                'Preview unavailable'
            )
            row['result'].setToolTip(str(exc))

        self.update_state()

    def update_state(self):
        if not hasattr(self, 'apply'):
            return

        active = [
            row for row in self.rows
            if row['mode'] != 'SKIP'
        ]

        blocked = [
            row for row in active
            if row['error']
            or row['result_error']
            or row['source'] is None
        ]

        self.apply.setEnabled(
            bool(active)
            and not blocked
            and not self.pending
        )

        self.status.setText(
            f'{len(active)} image(s) to rotate, '
            f'{len(self.rows) - len(active)} skipped'
            + (
                f', {len(blocked)} preview(s) unavailable'
                if blocked else ''
            )
        )

    def accept(self):
        self.update_state()

        if self.apply.isEnabled():
            super().accept()


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == 'rotatebatch':
        _, _, output, *arguments = sys.argv

        if arguments[:1] != ['--preset'] or len(arguments) < 3:
            raise ValueError(
                'Rotation batch needs a preset and selected images'
            )

        preset, files = arguments[1], arguments[2:]

        if preset not in ('90', '270', '180', 'custom', 'EXIF'):
            raise ValueError('Unrecognized rotation preset')

        app = QApplication(sys.argv[:1])
        dialog = RotateBatchDialog(files, preset)

        if dialog.exec() != QDialog.Accepted:
            return 130

        Path(output).write_bytes(
            b''.join(
                value.encode('ascii') + b'\0'
                for value in dialog.planned_angles()
            )
        )

        return 0
    kind,result,*files=sys.argv[1:]; initial=None; policy='create'; preset='custom'
    if kind=='compress' and files[:1]==['--preset']:
        _,preset,*files=files
        if preset not in ('recommended','maximum','custom'): raise ValueError('Invalid compression preset')
    if kind=='rename' and files and files[0] in ('create','overwrite'): policy=files.pop(0)
    if kind=='strip' and files and files[0] in ('all','gps','ai'): initial=files.pop(0)
    if kind=='rotate' and files[:1]==['--preset']:
        _,preset,*files=files
        if preset not in ('90','270','180','custom','EXIF'):
            raise ValueError('Invalid rotation preset')
    app=QApplication(sys.argv[:1]); dialog=ActionDialog(kind,files,policy=policy,preset=preset)
    if initial is not None: dialog.fields['mode'].setCurrentIndex(dialog.fields['mode'].findData(initial)); dialog.refresh()
    if dialog.exec()!=QDialog.Accepted: return 130 if kind in ('convert','copyright','strip','rename','rotate') else 1
    if kind=='rename':
        from kim_preview import save_plan
        save_plan(result+'.approved',dialog.rename_approved)
    Path(result).write_bytes(b''.join(v.encode()+b'\0' for v in dialog.values)); return 0


if __name__=='__main__': raise SystemExit(main())
