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
    """Inspect individual sources without losing a mixed selection."""

    def __init__(self, files, parent):
        super().__init__(parent)
        self.files = list(files)
        self.headers = {}
        self.stamps = {}
        self.problems = {}
        self.error = None
        self.tolerant = getattr(parent, 'kind', None) == 'compress'
        self.compression_inspection = (
            getattr(parent, 'kind', None) == 'compress'
        )

    def run(self):
        if self.compression_inspection:
            self.inspect_compression_sources()
            return
        import json
        import stat

        from kim_process import run_process, inspection_context
        from kim_recipe_image import (
            capture_date,
            canonical_file_type,
        )

        def stamp(item):
            return (
                item.st_dev,
                item.st_ino,
                item.st_size,
                item.st_mtime_ns,
                item.st_ctime_ns,
            )

        try:
            with inspection_context(
                cancelled=self.isInterruptionRequested
            ):
                for filename in self.files:
                    if self.isInterruptionRequested():
                        break

                    path = str(filename)

                    try:
                        info = Path(path).lstat()

                        if (
                            not stat.S_ISREG(info.st_mode)
                            or info.st_nlink != 1
                        ):
                            raise ValueError(
                                'Source must be an independent regular image'
                            )

                        result = run_process([
                            'exiftool',
                            '-json',
                            '-G1',
                            '-ImageWidth',
                            '-ImageHeight',
                            '-FileType',
                            '-DateTimeOriginal',
                            '-OffsetTimeOriginal',
                            path,
                        ], text=True)

                        if result.returncode:
                            raise ValueError(
                                'ExifTool could not inspect this image'
                            )

                        records = json.loads(result.stdout)

                        if (
                            not records
                            or not isinstance(records[0], dict)
                        ):
                            raise ValueError(
                                'ExifTool returned no usable image record'
                            )

                        record = records[0]

                        if any(
                            key.endswith(':Error')
                            for key in record
                        ):
                            raise ValueError(
                                'ExifTool reported a source error'
                            )

                        plain = {
                            key.split(':')[-1]: value
                            for key, value in record.items()
                        }

                        fmt = canonical_file_type(
                            plain.get('FileType')
                        )

                        if not fmt:
                            raise ValueError(
                                'Image format could not be identified'
                            )

                        # Compression needs format eligibility, not
                        # capture-date parsing. Invalid capture dates
                        # must not exclude otherwise valid photographs.
                        capture = None

                        if not self.tolerant:
                            raw = (
                                record.get(
                                    'ExifIFD:DateTimeOriginal'
                                )
                                or record.get(
                                    'XMP-exif:DateTimeOriginal'
                                )
                            )

                            try:
                                capture = capture_date({
                                    'DateTimeOriginal': raw,
                                    'OffsetTimeOriginal':
                                        record.get(
                                            'ExifIFD:OffsetTimeOriginal'
                                        ),
                                })
                            except ValueError:
                                capture = None

                        after = Path(path).lstat()

                        if stamp(info) != stamp(after):
                            raise ValueError(
                                'Source changed during inspection'
                            )

                        self.stamps[path] = stamp(after)

                        self.headers[path] = (
                            plain.get('ImageWidth'),
                            plain.get('ImageHeight'),
                            fmt,
                            capture,
                        )

                    except Exception as exc:
                        if not self.tolerant:
                            raise

                        self.problems[path] = str(exc)

        except Exception as exc:
            self.error = str(exc)

    def inspect_compression_sources(self):
        """Inspect formats independently without modifying sources."""
        import json
        import stat

        from kim_process import run_process, inspection_context
        from kim_recipe_image import canonical_file_type

        self.headers = {}
        self.stamps = {}
        self.problems = {}
        self.error = None

        def stamp(info):
            return (
                info.st_dev,
                info.st_ino,
                info.st_size,
                info.st_mtime_ns,
                info.st_ctime_ns,
            )

        try:
            with inspection_context(
                cancelled=self.isInterruptionRequested
            ):
                for filename in self.files:
                    if self.isInterruptionRequested():
                        break

                    path = str(filename)

                    try:
                        before = Path(path).lstat()

                        if (
                            not stat.S_ISREG(before.st_mode)
                            or before.st_nlink != 1
                        ):
                            raise ValueError(
                                'Not an independent regular file'
                            )

                        result = run_process(
                            [
                                'exiftool',
                                '-json',
                                '-G1',
                                '-FileType',
                                path,
                            ],
                            text=True,
                            timeout=30,
                        )

                        if result.returncode:
                            raise ValueError(
                                'ExifTool could not read the file type'
                            )

                        records = json.loads(
                            result.stdout
                        )

                        if (
                            not records
                            or not isinstance(records[0], dict)
                        ):
                            raise ValueError(
                                'Missing image-format information'
                            )

                        record = records[0]

                        if any(
                            key.endswith(':Error')
                            for key in record
                        ):
                            raise ValueError(
                                'ExifTool reported an invalid source'
                            )

                        raw_type = next(
                            (
                                value
                                for key, value in record.items()
                                if key.split(':')[-1] == 'FileType'
                            ),
                            None,
                        )

                        fmt = canonical_file_type(
                            raw_type
                        )

                        if not fmt:
                            raise ValueError(
                                'Unrecognized image format'
                            )

                        after = Path(path).lstat()

                        if stamp(before) != stamp(after):
                            raise ValueError(
                                'Source changed during inspection'
                            )

                        self.headers[path] = (
                            None,
                            None,
                            fmt,
                            None,
                        )

                        self.stamps[path] = stamp(after)

                    except Exception as exc:
                        # One failed source does not erase results
                        # already collected for other images.
                        self.problems[path] = str(exc)

        except Exception as exc:
            self.error = str(exc)




class GeometryPlan(QThread):
    def __init__(self,files,headers,geometry,parent):
        super().__init__(parent); self.files,self.headers,self.geometry=files,headers,geometry; self.lines=[]; self.rows=[]; self.error=None

    def run(self):
        from kim_process import run_process, inspection_context
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
                        cache[w,h]=(width,height)
                    width,height=cache[w,h]
                    self.rows.append((str(path), int(w), int(h), int(width), int(height)))
                    self.lines.append(f'{Path(path).name}: {w} × {h} → {width} × {height}')
        except Exception as exc: self.error=str(exc)


class ActionDialog(QDialog):
    def __init__(self, kind, files=(), parent=None, policy='create', preset='custom'):
        super().__init__(parent); self.policy=policy; self.kind=kind; self.files=list(files); self.values=[]; self.fields={}
        self.compression_preset=preset
        if kind == 'compress' and not self.files:
            raise ValueError(
                'Compress received no selected files from Dolphin'
            )
        self.worker=None; self.headers={}; self.header_stamps={}; self.compress_eligible=[]; self.header_error=None; self.closing=False; self.geometry_cache={}
        self.setWindowTitle('KIM6 - '+{'rotate':'Rotate','resize':'Resize Images','percent':'Resize by Percentage',
            'convert':'Convert Format','compress':'Compress Custom','copyright':'Set Creator and Copyright','strip':'Remove Metadata','rename':'Rename Images'}[kind])
        self.layout=QVBoxLayout(self)
        if kind=='compress':
            self.setWindowTitle('KIM6 - Compress '+preset.title())
            if preset!='custom':
                notice=QLabel({'recommended':'Starting with Recommended settings. You can adjust the settings before applying.',
                              'maximum':'Starting with Maximum compression settings. You can adjust the settings before applying.'}[preset])
                notice.setWordWrap(True); self.layout.addWidget(notice)
        self.form=QFormLayout(); self.layout.addLayout(self.form)
        if kind=='compress':
            self.setMinimumWidth(560)
        else: self.resize(660,270 if kind=='rotate' else 460)
        self.message=QLabel(); self.message.setWordWrap(True); self.layout.addWidget(self.message)
        if kind=='compress':
            self.preview=QLabel(); self.preview.setWordWrap(True); self.preview.setTextFormat(Qt.PlainText)
            self.preview.setTextInteractionFlags(Qt.TextSelectableByMouse|Qt.TextSelectableByKeyboard)
        else:
            self.preview=QPlainTextEdit(); self.preview.setReadOnly(True)
        self.layout.addWidget(self.preview)
        if kind == 'resize':
            self.resize_rows = []
            self.resize_heading = QLabel('Preview changes')
            self.layout.addWidget(self.resize_heading)
            self.resize_table = QTableWidget(0, 3, self)
            self.resize_table.setHorizontalHeaderLabels(
                ['Image', 'Original Dimensions', 'Planned Dimensions']
            )
            self.resize_table.setEditTriggers(
                QAbstractItemView.NoEditTriggers
            )
            self.resize_table.setSelectionBehavior(
                QAbstractItemView.SelectRows
            )
            self.resize_table.setAlternatingRowColors(True)
            self.resize_table.verticalHeader().hide()

            header = self.resize_table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.Stretch)
            header.setSectionResizeMode(1, QHeaderView.Interactive)
            header.setSectionResizeMode(2, QHeaderView.Interactive)
            self.resize_table.setColumnWidth(1, 170)
            self.resize_table.setColumnWidth(2, 195)

            visible_rows = min(len(self.files), 10)
            table_height = min(
                340, max(145, 38 + visible_rows * 29)
            )
            self.resize_table.setFixedHeight(table_height)
            self.layout.addWidget(self.resize_table)

            self.resize_summary = QLabel()
            self.resize_summary.setWordWrap(True)
            self.layout.addWidget(self.resize_summary)
            self.preview.setMaximumHeight(100)
            self.resize_table.hide()
            self.resize(
                850,
                min(600, max(350, 220 + len(self.files) * 30))
            )
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
        elif kind == 'resize':
            self.setWindowTitle('KIM6 - Resize images')
            self.choice('method', 'Sizing', [
                ('Resize to Fit', 'fit'),
                ('Exact Dimensions', 'exact'),
                ('Percentage', 'percent'),
            ])
            sizes = [
                300, 600, 800, 1024, 1280, 1400,
                1600, 1920, 2048, 2560, 3440, 3840
            ]
            presets = self.choice(
                'preset', 'Common sizes',
                [('Custom dimensions', '')]
                + [(f'{s} × {s}', str(s)) for s in sizes]
            )
            self.spin('width', 'Width (pixels)', 1, 100000, 1600)
            self.spin('height', 'Height (pixels)', 1, 100000, 1600)
            self.spin('percent', 'Percentage (%)', 1, 1000, 50)

            self.fields['upscale'] = QCheckBox('Allow enlargement')
            self.form.addRow(self.fields['upscale'])
            self.resize_help_label = QLabel()
            self.resize_help_label.setWordWrap(True)
            self.form.addRow(self.resize_help_label)

            presets.currentIndexChanged.connect(self.size_preset)
            self.fields['method'].currentIndexChanged.connect(
                self.update_resize_controls
            )
            self.apply.setText('Review changes…')
            self.update_resize_controls()
        elif kind=='convert':
            self.apply.setText('Review changes…')
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
            base_quality=70 if preset=='maximum' else 85
            self.compression_type=QComboBox()
            self.form.addRow('Image type',self.compression_type)
            self.compression_type.currentIndexChanged.connect(self.refresh)
            for codec,label in (('jpeg','JPEG'),('webp','WebP'),('avif','AVIF')):
                self.spin(codec+'_quality',label+' quality',1,100,base_quality)
            self.spin('png','Compression level',0,9,9 if preset=='maximum' else 6)
            self.fields['progressive']=QCheckBox('Progressive JPEG'); self.fields['progressive'].setChecked(True)
            self.fields['optimize']=QCheckBox('Optimize JPEG Huffman coding')
            self.jpeg_help_rows={key:with_help(self.fields[key],key) for key in ('progressive','optimize')}
            for row in self.jpeg_help_rows.values(): self.form.addRow(row); self.form.setRowVisible(row,False)
            for key in ('jpeg_quality','webp_quality','avif_quality','png'): self.form.setRowVisible(self.fields[key],False)
            self.message.setText('Inspecting selected image formats…')

            self.compress_table=QTableWidget(0,3)
            self.compress_table.setHorizontalHeaderLabels(
                ('Image / filename','Format','Status')
            )
            self.compress_table.setEditTriggers(
                QAbstractItemView.NoEditTriggers
            )
            self.compress_table.setSelectionBehavior(
                QAbstractItemView.SelectRows
            )
            self.compress_table.setIconSize(QSize(84,64))
            header=self.compress_table.horizontalHeader()
            header.setSectionResizeMode(0,QHeaderView.Stretch)
            header.setSectionResizeMode(1,QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2,QHeaderView.ResizeToContents)
            self.compress_table.setFixedHeight(160)
            self.layout.insertWidget(
                self.layout.indexOf(self.buttons),
                self.compress_table,1
            )
            self.compress_pending=[]
            self.resize(640,380)
        elif kind=='copyright':
            self.apply.setText('Review changes…')
            self.inherited=copyright_settings()
            for field,label in [('creator','Creator / Artist'),('notice','Copyright Notice'),('rights','Usage Rights')]:
                self.fields[field]=QLineEdit(self.inherited[field]); self.form.addRow(label,self.fields[field])
                button=QPushButton('Reset from Settings'); button.clicked.connect(lambda checked=False,k=field:self.reset_setting(k))
                self.form.addRow('',with_help(button,'settings',context='batch'))
            self.message.setText('Blank fields stay unchanged. Effective Settings values are shown; edit to override for this batch. Preview changes shows existing values and resolved assignments for every image before you apply them.')
        elif kind=='strip':
            self.choice('mode','Remove',[('Descriptive Metadata (keep color and orientation)','all'),('GPS Location','gps'),('Recognized AI Metadata','ai')])
            self.form.addRow('Full removal in Recipes',with_help(QLabel('Recipes also offers Remove All Metadata, including ICC.'),'strip'))
        elif kind=='rename':
            self.choice('method','Method',[(label,value) for label,value in [('Sequential numbering','sequential'),('Rename using Image Capture Date','exifdate'),('Lowercase','lowercase'),('Uppercase','uppercase'),('Spaces to dashes','spacestodash'),('Spaces to underscores','spacestounderscore'),('Underscores to spaces','underscorestospace'),('Dashes to spaces','dashestospace'),('Add prefix','addprefix'),('Add suffix','addsuffix'),('Replace text','overwrite')]])
            for field,label,default in [('value','Base name','photo_'),('replacement','Replace with','')]:
                self.fields[field]=QLineEdit(default); self.form.addRow(label,self.fields[field])
            self.spin('start','Starting number',0,1000000000,1); self.spin('padding','Minimum digits',1,18,3)
            self.choice('date_format','Date format',[('YYYYMMDD_HHMMSS','compact'),('YYYY-MM-DD_HH-MM-SS','iso'),('YYYY-DD-MM_HH-MM-SS','day_first'),('IMG-YYYYMMDD_HHMMSS','camera')])
            self.rename_method='sequential'; self.rename_states={}
            self.fields['method'].currentIndexChanged.connect(self.rename_method_changed)
            from kim_preview import qt_classes
            self.layout.insertWidget(self.layout.indexOf(self.preview),QLabel('Preview changes'))
            self.rename_view=qt_classes()[0](self)
            self.rename_table=self.rename_view.table
            self.layout.insertWidget(self.layout.indexOf(self.preview),self.rename_view,1)
            self.resize(1050,650)
            self.apply.setText('Apply changes')
            self.rename_approved=None; self.rename_pending=False
            self.preview.setMaximumHeight(75)
            self.preview.hide()
            self.update_rename_controls()
            self.fields['directory']=QLineEdit(); self.fields['directory'].setPlaceholderText('Beside each source'); self.form.addRow('Destination directory',self.fields['directory'])
            browse=QPushButton('Choose Directory…'); browse.clicked.connect(self.browse); self.form.addRow(browse)
            self.message.setText('Before → after updates as you edit. '+('New copies protect original files.' if self.policy=='create' else 'You explicitly approved renaming originals; their old names will be removed after publication.')+' Names are checked again when saving.')
        self.timer=QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(100); self.timer.timeout.connect(self.refresh)
        for widget in self.fields.values():
            signal=widget.textChanged if isinstance(widget,QLineEdit) else widget.currentIndexChanged if isinstance(widget,QComboBox) else widget.toggled if isinstance(widget,QCheckBox) else widget.valueChanged
            signal.connect(lambda *_: self.timer.start())
        if kind in ('resize','percent','compress') and self.files:
            self.worker=SourceHeaders(self.files,self); self.worker.finished.connect(self.headers_finished); self.worker.start()
        self.refresh()
        if kind == 'compress':
            self.populate_compression_table()



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

    def populate_compression_types(self):
        from collections import Counter
        counts=Counter(record[2] for record in self.headers.values())
        previous=self.compression_type.currentData()
        self.compression_type.blockSignals(True)
        self.compression_type.clear()
        for kind in ('JPEG','PNG','WEBP','AVIF'):
            if counts[kind]:
                self.compression_type.addItem(f'{kind} ({counts[kind]} images)',kind)
        if previous is not None:
            index=self.compression_type.findData(previous)
            if index>=0: self.compression_type.setCurrentIndex(index)
        self.compression_type.blockSignals(False)

    def populate_compression_table(self):
        """Display every selected file, including failed inspections."""
        from kim_preview import (
            fit_review_table,
            review_row_style,
        )

        self.compress_table.setRowCount(
            len(self.files)
        )

        self.compress_pending = []

        problems = getattr(
            self,
            'header_errors',
            {},
        )

        inspected = self.worker is None

        for index, filename in enumerate(self.files):
            path = str(filename)
            record = self.headers.get(path)

            fmt = (
                str(record[2])
                if record
                else 'Unknown'
            )

            issue = problems.get(path)

            if not inspected and not record and not issue:
                status = 'Inspecting…'
                explanation = (
                    'Checking the selected image format'
                )

            elif issue:
                status = 'Blocked'
                explanation = issue

            elif path in self.compress_eligible:
                status = 'Ready'
                explanation = (
                    'Eligible for format-specific compression'
                )

            elif record:
                status = 'Skipped'
                explanation = (
                    'Compression supports JPEG, PNG, '
                    'WebP and AVIF'
                )

            else:
                status = 'Blocked'
                explanation = (
                    'No verified image-format result'
                )

            values = (
                Path(path).name,
                fmt,
                status,
            )

            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))

                item.setToolTip(
                    path + '\\n' + explanation
                )

                self.compress_table.setItem(
                    index,
                    column,
                    item,
                )

            self.compress_table.setRowHeight(
                index,
                74,
            )

            review_row_style(
                self.compress_table,
                index,
                status == 'Skipped',
            )

            if inspected:
                self.compress_pending.append(
                    (index, path)
                )

        table_height = fit_review_table(
            self.compress_table
        )

        self.resize(
            640,
            min(
                760,
                max(320, table_height + 240),
            ),
        )

        if self.compress_pending:
            QTimer.singleShot(
                0,
                self.load_compression_thumbnail,
            )



    def load_compression_thumbnail(self):
        if not self.compress_pending or self.closing:
            return

        index,path=self.compress_pending.pop(0)
        item=self.compress_table.item(index,0)

        if item is not None:
            try:
                from kim_photo_selection import read_thumbnail

                image,_stamp=read_thumbnail(
                    path,QSize(84,64)
                )
                if not image.isNull():
                    from kim_preview import review_icon
                    item.setIcon(review_icon(image,path not in self.compress_eligible))
            except Exception as exc:
                item.setToolTip(
                    item.toolTip()+'\\nThumbnail unavailable: '+str(exc)
                )

        if self.compress_pending:
            QTimer.singleShot(0,self.load_compression_thumbnail)

    def headers_finished(self):
        worker, self.worker = self.worker, None

        self.headers = dict(worker.headers)
        self.header_stamps = dict(worker.stamps)
        self.header_error = worker.error

        self.header_errors = dict(
            getattr(worker, 'problems', {})
        )

        worker.deleteLater()

        if self.closing:
            super().reject()
            return

        if self.kind != 'compress':
            self.refresh()
            return

        if self.header_error:
            for filename in self.files:
                if filename not in self.headers:
                    self.header_errors.setdefault(
                        filename,
                        self.header_error,
                    )

        for filename in self.files:
            if filename not in self.headers:
                self.header_errors.setdefault(
                    filename,
                    'Image inspection did not complete',
                )

        self.populate_compression_types()
        self.refresh()
        self.populate_compression_table()

        if self.header_errors:
            self.apply.setEnabled(False)

            problems = '; '.join(
                Path(filename).name + ': ' + reason
                for filename, reason
                in self.header_errors.items()
            )

            self.message.setText(
                'Inspection blocked: ' + problems
            )



    def geometry_finished(self):
        worker,self.worker=self.worker,None
        self.geometry_cache[worker.geometry]=(worker.lines,worker.error,worker.rows); worker.deleteLater()
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

    def update_resize_controls(self, *_):
        """Show only controls used by the selected sizing method."""
        method = self.fields['method'].currentData()
        dimensions = method in ('fit', 'exact')

        for key in ('preset', 'width', 'height'):
            self.form.setRowVisible(
                self.fields[key], dimensions
            )

        self.form.setRowVisible(
            self.fields['upscale'], method == 'fit'
        )
        self.form.setRowVisible(
            self.fields['percent'], method == 'percent'
        )

        descriptions = {
            'fit': (
                'Fits images within the specified dimensions '
                'without changing their proportions.'
            ),
            'exact': (
                'Forces the specified width and height. '
                'Images may appear stretched.'
            ),
            'percent': (
                '50% halves both dimensions. '
                '100% keeps them unchanged. '
                '200% doubles them.'
            ),
        }

        self.resize_help_label.setText(
            descriptions[method]
        )

        # This label is used elsewhere for inspection feedback.
        # Do not remove it from the dialog.
        if not self.header_error:
            self.message.clear()

    def size_preset(self):
        value=self.fields['preset'].currentData()
        if value:
            for key in ('width','height'): self.fields[key].setValue(int(value))

    def show_resize_table(self):
        rows = self.resize_rows
        self.resize_table.setRowCount(len(rows))
        unchanged = 0

        for index, (filename, w, h, new_w, new_h) in enumerate(rows):
            same = (w, h) == (new_w, new_h)
            unchanged += int(same)

            values = (
                Path(filename).name,
                f'{w} × {h}',
                f'{new_w} × {new_h}'
                + (' (unchanged)' if same else '')
            )

            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setToolTip(filename)
                self.resize_table.setItem(index, column, item)

        self.resize_heading.setText(
            f'Preview changes: {len(rows)} selected images'
        )
        self.resize_summary.setText(
            f'{unchanged} unchanged, '
            f'{len(rows) - unchanged} resized. '
            'No changes applied yet.'
        )

        self.preview.hide()
        self.resize_table.show()

    def set_preview_text(self, text):
        if self.kind == 'resize':
            self.resize_table.hide()
            self.resize_table.setRowCount(0)
            self.resize_summary.clear()
            self.preview.show()
        if self.kind == 'compress':
            self.preview.setText(text)
            self.preview.setVisible(bool(text))
        else:
            self.preview.setPlainText(text)

            if self.kind == 'rename':
                normal = (
                    text.startswith(
                        'Preparing changes'
                    )
                    or text.startswith(
                        'Preview changes: final'
                    )
                )

                # Keep errors visible, not the redundant
                # successful-plan explanation.
                self.preview.setVisible(
                    bool(text) and not normal
                )



    def refresh(self):
        if self.kind == 'resize':
            self.resize_rows = []
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
            elif self.kind == 'resize':
                method = self.fields['method'].currentData()

                if method == 'percent':
                    geometry = str(
                        self.fields['percent'].value()
                    ) + '%'
                else:
                    geometry = (
                        f"{self.fields['width'].value()}x"
                        f"{self.fields['height'].value()}"
                        + ('!' if method == 'exact' else '')
                    )
                    if (
                        method == 'fit'
                        and not self.fields['upscale'].isChecked()
                    ):
                        geometry += '>'

                from kim_recipe_image import ImageHandler
                if not geometry.endswith('%'):
                    ImageHandler().validate_step({
                        'op': 'image.resize_geometry',
                        'geometry': geometry
                    })

                self.values = [geometry]
                lines = ['Planned geometry: ' + geometry]

                if self.files and geometry not in self.geometry_cache:
                    self.worker = GeometryPlan(
                        self.files, self.headers, geometry, self
                    )
                    self.worker.finished.connect(
                        self.geometry_finished
                    )
                    self.worker.start()
                    self.set_preview_text('Planning dimensions…')
                    self.apply.setEnabled(False)
                    return

                planned, error, rows = self.geometry_cache.get(
                    geometry, ([], None, [])
                )
                if error:
                    raise ValueError(error)

                self.resize_rows = rows
                lines += planned
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
                if not self.files:
                    raise ValueError(
                        'No selected file paths were received from Dolphin.'
                    )

                if getattr(self, 'header_errors', {}):
                    raise ValueError(
                        'Inspection failed for: '
                        + ', '.join(
                            Path(path).name
                            for path in self.header_errors
                        )
                    )
                formats={path:record[2] for path,record in self.headers.items()}
                allowed=('JPEG','PNG','WEBP','AVIF')
                counts={kind:sum(fmt==kind for fmt in formats.values()) for kind in allowed}
                self.compress_eligible=[path for path in self.files
                    if formats.get(path) in allowed]
                chosen=self.compression_type.currentData()
                field={'JPEG':'jpeg_quality','WEBP':'webp_quality',
                       'AVIF':'avif_quality','PNG':'png'}.get(chosen)
                for key in ('jpeg_quality','webp_quality','avif_quality','png'):
                    self.form.setRowVisible(self.fields[key],key==field)
                for key,row in self.jpeg_help_rows.items():
                    self.form.setRowVisible(row,chosen=='JPEG')
                baseline_q,baseline_png=(70,9) if self.compression_preset=='maximum' else (85,6)
                adjusted=(any(counts[kind] and self.fields[key].value()!=baseline_q
                    for kind,key in (('JPEG','jpeg_quality'),('WEBP','webp_quality'),
                                     ('AVIF','avif_quality')))
                    or counts['PNG'] and self.fields['png'].value()!=baseline_png
                    or counts['JPEG'] and (not self.fields['progressive'].isChecked()
                        or self.fields['optimize'].isChecked()))
                self.values=[str(self.fields[key].value()) for key in
                    ('jpeg_quality','webp_quality','avif_quality','png')]
                self.values += ['Plane' if self.fields['progressive'].isChecked() else 'None',
                    'true' if self.fields['optimize'].isChecked() else 'false',
                    'true' if adjusted else 'false']
                if chosen=='PNG':
                    self.message.setText('PNG compression is lossless. Higher levels may take longer.')
                else:
                    self.message.clear()
                if not self.compress_eligible:
                    raise ValueError('No JPEG, PNG, WebP or AVIF images are eligible.')
                lines=[f'{len(self.compress_eligible)} eligible, '
                       f'{len(self.files)-len(self.compress_eligible)} skipped. '
                       'Each file retains its original format; EXIF and ICC are preserved.']
            elif self.kind=='copyright':
                self.values=[self.fields[k].text() for k in ('creator','notice','rights')]
                if not any(self.values): raise ValueError('Enter at least one creator, copyright or usage-rights value, or reset from Settings.')
                lines=['Values are resolved for each selected image in Preview changes. {YEAR} in Copyright Notice uses its capture year, or the current year when missing. Blank fields preserve existing values.']
            elif self.kind=='strip':
                value=self.fields['mode'].currentData(); self.values=[value]
                lines=[{'all':'Removes descriptive EXIF, IPTC, XMP and comments. Keeps ICC color profiles and orientation. File Modification Dates and encoded image data are preserved.',
                        'gps':'Removes recognized GPS and location coordinates. Keeps other metadata, ICC, orientation and file dates.',
                        'ai':'Removes recognized AI-generation fields. Unrecognized provenance and signed Content Credentials may remain. Keeps ICC, orientation and file dates.'}[value]]
            if (
                self.kind == 'resize'
                and self.files
                and len(self.resize_rows) == len(self.files)
            ):
                self.show_resize_table()
            else:
                self.set_preview_text('\n'.join(lines))
            self.apply.setEnabled(True)
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
        self.worker.progress.connect(lambda i,n,p:self.rename_view.summary.setText(f'Preview changes: inspecting image {i+1} of {n}: {Path(p).name}'))
        self.worker.finished.connect(self.rename_finished); self.worker.start()
        self.set_preview_text('Preparing output filenames…')

    def rename_finished(self):
        worker,self.worker=self.worker,None
        if self.closing: worker.deleteLater(); super().reject(); return
        if self.rename_pending: worker.deleteLater(); self.start_rename_plan(); return
        if worker.error: self.set_preview_text(worker.error)
        else:
            self.rename_approved=worker.plan
            self.apply.setEnabled(self.rename_view.show_plan(worker.plan))
            self.resize(1050,min(790,max(370,self.rename_table.height()+265)))
            self.set_preview_text('Preview changes: final paths are available in each row’s tooltip. Changed sources or destinations require a fresh review.')
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

        self.setWindowTitle('KIM6 - Rotate images')
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
        self.apply.setText('Apply changes')
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
        result_column=QVBoxLayout()
        result_column.addWidget(result)
        row['caption']=QLabel('')
        row['caption'].setAlignment(Qt.AlignCenter)
        result_column.addWidget(row['caption'])
        line.addLayout(result_column,2)

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
        value=(
            f"{row['custom'].value():g}"
            if row['mode']=='custom'
            else row['mode']
        )

        if value not in ('SKIP','EXIF') and float(value)%360==0:
            return 'SKIP'

        return value

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

            elif self.selected_angle(row) == 'SKIP':
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

            angle=self.selected_angle(row)
            row['caption'].setText('No change (0°)' if mode=='custom' and angle=='SKIP'
                else 'Skipped' if angle=='SKIP'
                else 'EXIF orientation' if mode=='EXIF' else 'Rotate '+angle+'°')
            row['result'].setToolTip(
                'No change' if self.selected_angle(row) == 'SKIP'
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
            if self.selected_angle(row) != 'SKIP'
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



class FlipReviewDialog(QDialog):
    """Review a batch flip using bounded, read-only thumbnails."""

    def __init__(self, files, operation):
        super().__init__()

        if operation not in ('flip', 'flop') or not files:
            raise ValueError('Invalid Flip review selection')

        self.operation = operation
        self.rows = []
        self.pending = []

        self.setWindowTitle('KIM6 - Flip images')
        # Match the initial height to the batch rather than
        # reserving a large, mostly empty scroll area.
        # Four or more images use a bounded scrolling window.
        visible_rows = min(len(files), 4)
        self.resize(
            830,
            min(740, 195 + 165 * visible_rows)
        )

        outer = QVBoxLayout(self)

        description = (
            'Flip Vertically (top to bottom)'
            if operation == 'flip'
            else 'Flip Horizontally (left to right)'
        )

        heading = QLabel(
            f'{len(files)} selected image(s). '
            f'Planned operation: {description}. '
            'Image dimensions remain unchanged.'
        )
        heading.setWordWrap(True)
        outer.addWidget(heading)

        note = QLabel(
            'Review the original and resulting images below. '
            'After approval, KIM6 applies its configured output policy.'
        )
        note.setWordWrap(True)
        outer.addWidget(note)

        headings = QHBoxLayout()
        headings.addWidget(QLabel('Image'), 2)
        headings.addWidget(QLabel('Original'), 3, Qt.AlignCenter)
        headings.addWidget(QLabel('Planned result'), 3, Qt.AlignCenter)
        outer.addLayout(headings)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)

        container = QWidget()
        listing = QVBoxLayout(container)
        listing.setContentsMargins(5, 5, 5, 5)

        for path in files:
            panel = QFrame()
            panel.setFrameShape(QFrame.StyledPanel)

            line = QHBoxLayout(panel)

            name = QLabel(Path(path).name)
            name.setToolTip(path)
            name.setWordWrap(True)
            name.setMinimumWidth(175)
            name.setMaximumWidth(240)

            original = QLabel('Inspecting…')
            result = QLabel('Inspecting…')

            for widget in (original, result):
                widget.setFixedSize(180, 130)
                widget.setAlignment(Qt.AlignCenter)

            line.addWidget(name, 2)
            line.addWidget(original, 3)
            line.addWidget(result, 3)

            listing.addWidget(panel)

            self.rows.append({
                'path': path,
                'original': original,
                'result': result,
                'stamp': None,
                'ready': False,
                'error': None,
            })

        # Keep rows at the top. The scroll area itself manages
        # any remaining space when the dialog is resized.
        listing.setAlignment(Qt.AlignTop)
        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        self.status = QLabel('Inspecting selected images…')
        outer.addWidget(self.status)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )

        self.apply = buttons.button(QDialogButtonBox.Ok)
        self.apply.setText('Apply changes')
        self.apply.setEnabled(False)

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        outer.addWidget(buttons)

        self.pending = list(self.rows)
        QTimer.singleShot(0, self.load_next)

    def load_next(self):
        if not self.pending:
            self.update_state()
            return

        row = self.pending.pop(0)

        try:
            from kim_photo_selection import read_thumbnail

            image, stamp = read_thumbnail(
                row['path'],
                QSize(180, 130),
                auto_orient=False
            )

            if image.isNull():
                raise ValueError(
                    'No supported source thumbnail decoder'
                )

            result = image.mirrored(
                self.operation == 'flop',
                self.operation == 'flip'
            )

            for label, value in (
                (row['original'], image),
                (row['result'], result),
            ):
                pixmap = QPixmap.fromImage(value)
                label.setPixmap(
                    pixmap.scaled(
                        label.size(),
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation
                    )
                )

            row['stamp'] = stamp
            row['ready'] = True

        except Exception as exc:
            row['error'] = str(exc)
            row['original'].setText('Preview unavailable')
            row['result'].setText('Blocked')
            row['result'].setToolTip(str(exc))

        self.update_state()

        if self.pending:
            QTimer.singleShot(0, self.load_next)

    def update_state(self):
        ready = sum(row['ready'] for row in self.rows)
        blocked = sum(bool(row['error']) for row in self.rows)

        self.apply.setEnabled(
            bool(self.rows)
            and ready == len(self.rows)
            and not blocked
            and not self.pending
        )

        self.status.setText(
            f'{ready} ready, {blocked} blocked, '
            f'{len(self.pending)} awaiting inspection. '
            'No files have been modified.'
        )

    def accept(self):
        # Reject approval if a source changed after its preview.
        from kim_preview import identity

        for row in self.rows:
            if row['ready'] and not row['error']:
                try:
                    if identity(row['path']) != row['stamp']:
                        raise ValueError(
                            'Image changed since preview'
                        )
                except Exception as exc:
                    row['error'] = str(exc)
                    row['result'].setToolTip(str(exc))

        self.update_state()

        if self.apply.isEnabled():
            super().accept()


def resize_output_review(
    plan_path, request_path, destination, policy, geometry
):
    """Review exact Resize output paths before publication."""
    import os

    payload = plan_path.read_bytes()

    if not payload.endswith(b"\0"):
        raise ValueError("Incomplete Resize output plan")

    parts = payload[:-1].split(b"\0")
    if not parts or len(parts) % 4:
        raise ValueError("Invalid Resize output plan")

    records = [
        [os.fsdecode(value) for value in parts[i:i + 4]]
        for i in range(0, len(parts), 4)
    ]

    if policy not in ("create", "overwrite"):
        raise ValueError("Invalid Resize output policy")

    app = QApplication.instance() or QApplication(sys.argv)
    dialog = QDialog()
    dialog.setWindowTitle("KIM6 - Review resize outputs")

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(6)

    layout.addWidget(QLabel(
        f"{len(records)} selected image(s) | "
        f"Resize geometry: {geometry}"
    ))

    destination_choice = QComboBox()
    destination_choice.addItem(
        "Beside originals", "beside"
    )
    destination_choice.addItem(
        "Different directory", "directory"
    )

    destination_choice.setCurrentIndex(
        1 if destination else 0
    )

    destination_row = QHBoxLayout()
    destination_row.addWidget(
        QLabel("Save copies:")
    )
    destination_row.addWidget(
        destination_choice, 1
    )

    if policy == "create":
        layout.addLayout(destination_row)
    else:
        layout.addWidget(
            QLabel("Destination: Replace selected originals")
        )

    directory_field = QLineEdit(destination)
    directory_field.setPlaceholderText(
        "Enter an existing destination directory"
    )
    directory_field.setAccessibleName(
        "Output directory"
    )

    browse_button = QPushButton("Browse…")
    update_button = QPushButton("Update preview")

    directory_row = QHBoxLayout()
    directory_row.addWidget(directory_field, 1)
    directory_row.addWidget(browse_button)
    directory_row.addWidget(update_button)

    if policy == "create":
        layout.addLayout(directory_row)

    def show_directory_controls():
        different = (
            destination_choice.currentData() == "directory"
        )
        directory_field.setVisible(different)
        browse_button.setVisible(different)
        update_button.setVisible(different)

    show_directory_controls()

    table = QTableWidget(len(records), 4)
    table.setHorizontalHeaderLabels([
        "Source image",
        "Output filename",
        "Destination",
        "Status",
    ])
    table.setSelectionBehavior(
        QAbstractItemView.SelectRows
    )
    table.setSelectionMode(
        QAbstractItemView.SingleSelection
    )
    table.setEditTriggers(
        QAbstractItemView.NoEditTriggers
    )
    table.verticalHeader().setVisible(False)

    widths = (270, 270, 330, 95)
    for column, width in enumerate(widths):
        table.setColumnWidth(column, width)

    for row, (source, target, status, note) in enumerate(records):
        values = (
            os.path.basename(source),
            os.path.basename(target) if target else "None",
            os.path.dirname(target) if target else "None",
            status,
        )

        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(
                source if column == 0
                else target if column in (1, 2)
                else note
            )
            table.setItem(row, column, item)

    visible_rows = min(len(records), 8)
    table.setFixedHeight(48 + 32 * visible_rows)
    layout.addWidget(table)

    details = QLabel()
    details.setWordWrap(True)
    details.setMinimumHeight(35)
    layout.addWidget(details)

    def update_details():
        row = table.currentRow()
        if row >= 0:
            source, _, status, note = records[row]
            details.setText(
                f"{os.path.basename(source)}: {status}. {note}"
            )

    table.itemSelectionChanged.connect(update_details)
    table.selectRow(0)
    update_details()

    ready = sum(record[2] == "Ready" for record in records)
    blocked = len(records) - ready

    if policy == "overwrite":
        summary_text = (
            f"{ready} ready, {blocked} blocked. "
            "The selected originals will be replaced. "
            "This operation cannot be undone."
        )
    else:
        summary_text = (
            f"{ready} ready, {blocked} blocked. "
            "Original images are never modified. "
            "Images requiring no size change may be skipped."
        )

    summary = QLabel(summary_text)
    summary.setWordWrap(True)
    layout.addWidget(summary)

    buttons = QHBoxLayout()
    buttons.addStretch(1)

    apply_button = QPushButton("Apply changes")
    apply_button.setEnabled(
        ready > 0 and blocked == 0
    )
    buttons.addWidget(apply_button)

    back_button = QPushButton("Back")
    buttons.addWidget(back_button)

    apply_button.clicked.connect(dialog.accept)
    # 131 requests a return to the resize editor.
    # Closing the review window remains cancellation (130).
    back_button.clicked.connect(lambda: dialog.done(131))

    layout.addLayout(buttons)

    def request_destination(directory):
        try:
            request_path.write_bytes(
                os.fsencode(directory) + b"\0"
            )
        except OSError as error:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                dialog, "Cannot change destination", str(error)
            )
            return
        dialog.reject()

    def choose_directory():
        entered = directory_field.text().strip()
        initial = (
            entered if os.path.isdir(entered)
            else destination
            or os.path.dirname(records[0][0])
        )
        selected = QFileDialog.getExistingDirectory(
            dialog, "Choose Resize destination", initial
        )
        if selected:
            directory_field.setText(selected)

    def update_destination():
        entered = directory_field.text().strip()

        if (
            not entered
            or not os.path.isabs(entered)
            or not os.path.isdir(entered)
            or os.path.islink(entered)
            or not os.access(
                entered, os.W_OK | os.X_OK
            )
        ):
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                dialog,
                "Invalid output directory",
                "Enter an existing, writable, "
                "absolute directory.",
            )
            return

        request_destination(os.path.realpath(entered))

    def selection_changed(*_):
        if destination_choice.currentData() == "beside":
            if destination:
                request_destination("")
            else:
                show_directory_controls()
        else:
            show_directory_controls()
            # The previous output plan remains visible until
            # Update Preview explicitly recalculates it.
            apply_button.setEnabled(False)

    def directory_edited(*_):
        # Never approve a plan based on an obsolete directory.
        if (
            policy == "create"
            and destination_choice.currentData() == "directory"
            and directory_field.text().strip() != destination
        ):
            apply_button.setEnabled(False)

    if policy == "create":
        destination_choice.currentIndexChanged.connect(
            selection_changed
        )
        directory_field.textChanged.connect(
            directory_edited
        )
        browse_button.clicked.connect(choose_directory)
        update_button.clicked.connect(update_destination)

    dialog.resize(
        1090,
        min(780, 285 + 32 * visible_rows)
    )

    # Qt-owned children must be destroyed before QApplication
    # teardown, as verified during the Set Dates crash fix.
    import shiboken6

    try:
        review_result = dialog.exec()
        if review_result == QDialog.Accepted:
            return 0
        if review_result == 131:
            return 131
        return 130
    finally:
        shiboken6.delete(dialog)
        dialog = None
        if QApplication.instance() is app:
            shiboken6.delete(app)


def email_options_review(output_path, initial_size, sources):
    """Choose email resizing bounds with a source-size preview."""
    import os
    import re
    import shutil
    import subprocess

    from PySide6.QtWidgets import (
        QAbstractItemView, QHBoxLayout, QMessageBox,
    )

    if not sources:
        raise ValueError("Email needs selected files")

    app = QApplication.instance() or QApplication(sys.argv)
    dialog = QDialog()
    dialog.setWindowTitle("KIM6 - Prepare email images")

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(7)

    layout.addWidget(QLabel(
        f"{len(sources)} selected image(s) | Prepare attachments"
    ))

    options = QComboBox()
    presets = [
        ("Standard (1600 × 1600)", "1600x1600"),
        ("Compact (1200 × 1200)", "1200x1200"),
        ("Small (800 × 800)", "800x800"),
        ("Very Small (600 × 600)", "600x600"),
        ("Full size (no resizing)", "full"),
        ("Custom dimensions", "custom"),
    ]

    for label, value in presets:
        options.addItem(label, value)

    preset_values = [value for _, value in presets]
    initial_index = (
        preset_values.index(initial_size)
        if initial_size in preset_values
        else 5
    )
    options.setCurrentIndex(initial_index)

    layout.addWidget(QLabel("Resize for:"))
    layout.addWidget(options)

    # Discover supported clients on the machine running the dialog.
    # Prefer Thunderbird when installed, not the xdg-email wrapper.
    mail_clients = QComboBox()

    if shutil.which("thunderbird"):
        mail_clients.addItem("Thunderbird", "thunderbird")

    if shutil.which("flatpak"):
        probe = subprocess.run(
            ["flatpak", "info", "org.mozilla.Thunderbird"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        if probe.returncode == 0:
            mail_clients.addItem(
                "Thunderbird (Flatpak)", "thunderbird-flatpak"
            )

    if shutil.which("kmail"):
        mail_clients.addItem("KMail", "kmail")

    if shutil.which("xdg-email"):
        mail_clients.addItem(
            "System Default (xdg-email)", "xdg-email"
        )

    if mail_clients.count() == 0:
        mail_clients.addItem(
            "No supported mail client detected", ""
        )

    layout.addWidget(QLabel("Mail client:"))
    layout.addWidget(mail_clients)

    custom = QHBoxLayout()
    custom.addWidget(QLabel("Maximum width:"))
    width = QSpinBox()
    width.setRange(1, 100000)
    width.setValue(1600)
    custom.addWidget(width)
    custom.addWidget(QLabel("Maximum height:"))
    height = QSpinBox()
    height.setRange(1, 100000)
    height.setValue(1600)
    custom.addWidget(height)

    match = re.fullmatch(r"([0-9]+)x([0-9]+)", initial_size)
    if initial_index == 5 and match:
        width.setValue(min(100000, int(match.group(1))))
        height.setValue(min(100000, int(match.group(2))))

    layout.addLayout(custom)

    table = QTableWidget(len(sources), 2)
    table.setHorizontalHeaderLabels([
        "Source image", "Original size"
    ])
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.verticalHeader().setVisible(False)
    table.setColumnWidth(0, 370)
    table.setColumnWidth(1, 160)
    table.setFixedHeight(48 + 31 * min(len(sources), 8))

    total = 0
    for row, source in enumerate(sources):
        size = os.stat(source).st_size
        total += size

        name = QTableWidgetItem(os.path.basename(source))
        name.setToolTip(source)
        table.setItem(row, 0, name)
        table.setItem(
            row, 1,
            QTableWidgetItem(f"{size / (1024 * 1024):.2f} MiB")
        )

    layout.addWidget(table)

    summary = QLabel()
    summary.setWordWrap(True)
    layout.addWidget(summary)

    note = QLabel(
        "Images are resized to fit, preserving proportions. "
        "Actual attachment sizes are checked after encoding, "
        "before opening the mail client."
    )
    note.setWordWrap(True)
    layout.addWidget(note)

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )
    proceed = buttons.button(QDialogButtonBox.Ok)
    proceed.setText("Continue to review")

    def refresh():
        choice = options.currentData()
        is_custom = choice == "custom"

        for index in range(custom.count()):
            widget = custom.itemAt(index).widget()
            if widget:
                widget.setVisible(is_custom)

        full = choice == "full"
        blocked = full and total > 25 * 1024 * 1024

        if full:
            summary.setText(
                f"Original total: {total / 1048576:.2f} MiB. "
                + (
                    "Over the 25 MiB attachment ceiling. "
                    "Choose a resizing preset."
                    if blocked else
                    "These images will be copied without resizing."
                )
            )
        else:
            summary.setText(
                f"Original total: {total / 1048576:.2f} MiB. "
                "Final encoded attachment sizes are not yet known."
            )

        proceed.setEnabled(not blocked and bool(mail_clients.currentData()))

    options.currentIndexChanged.connect(refresh)
    refresh()

    def accept_options():
        choice = options.currentData()

        if choice == "custom":
            choice = f"{width.value()}x{height.value()}"

        if (
            choice != "full"
            and not re.fullmatch(
                r"[1-9][0-9]*x[1-9][0-9]*", choice
            )
        ):
            QMessageBox.warning(
                dialog, "Invalid resize setting",
                "Select valid maximum dimensions."
            )
            return

        selected_client = mail_clients.currentData()
        if not selected_client:
            QMessageBox.warning(
                dialog,
                "No mail client",
                "Install or configure a supported mail client."
            )
            return

        try:
            output_path.write_bytes(
                choice.encode("ascii") + b"\0"
                + selected_client.encode("ascii") + b"\0"
            )
        except OSError as error:
            QMessageBox.critical(
                dialog, "Cannot save options", str(error)
            )
            return

        dialog.accept()

    buttons.accepted.connect(accept_options)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    dialog.resize(600, min(700, 300 + 31 * min(len(sources), 8)))
    return 0 if dialog.exec() == QDialog.Accepted else 130


def email_ready_review(plan_path, mail_client):
    """Review actual prepared attachment sizes before mail handoff."""
    import os

    payload = plan_path.read_bytes()
    if not payload.endswith(b"\0"):
        raise ValueError("Incomplete email attachment plan")

    parts = payload[:-1].split(b"\0")
    if not parts or len(parts) % 2:
        raise ValueError("Invalid email attachment plan")

    records = [
        (os.fsdecode(parts[i]), os.fsdecode(parts[i + 1]))
        for i in range(0, len(parts), 2)
    ]

    app = QApplication.instance() or QApplication(sys.argv)
    dialog = QDialog()
    dialog.setWindowTitle("KIM6 - Review email attachments")

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(12, 10, 12, 10)
    layout.setSpacing(7)

    layout.addWidget(QLabel(
        f"{len(records)} prepared attachment(s) | Final size review"
    ))

    client_names = {
        "thunderbird": "Thunderbird",
        "thunderbird-flatpak": "Thunderbird (Flatpak)",
        "kmail": "KMail",
        "xdg-email": "System Default",
    }
    if mail_client not in client_names:
        raise ValueError("Invalid selected mail client")

    layout.addWidget(QLabel(
        "Mail client: " + client_names[mail_client]
    ))

    table = QTableWidget(len(records), 3)
    table.setHorizontalHeaderLabels([
        "Source image", "Attachment filename", "Actual size"
    ])
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.verticalHeader().setVisible(False)

    for column, width in enumerate((265, 265, 130)):
        table.setColumnWidth(column, width)

    table.setFixedHeight(48 + 31 * min(len(records), 8))

    total = 0

    for row, (source, output) in enumerate(records):
        size = os.stat(output).st_size
        total += size

        for column, value in enumerate((
            os.path.basename(source),
            os.path.basename(output),
            f"{size / 1048576:.2f} MiB",
        )):
            item = QTableWidgetItem(value)
            item.setToolTip(output if column else source)
            table.setItem(row, column, item)

    layout.addWidget(table)

    recommended = 18 * 1024 * 1024
    maximum = 25 * 1024 * 1024
    blocked = total > maximum

    if blocked:
        status = (
            "BLOCKED: The attachments exceed 25 MiB. "
            "Cancel and choose smaller resize dimensions."
        )
    elif total > recommended:
        status = (
            "WARNING: Above the recommended 18 MiB target. "
            "Email encoding and recipient limits may prevent delivery."
        )
    else:
        status = (
            "Within the recommended 18 MiB attachment target."
        )

    summary = QLabel(
        f"Combined attachment size: "
        f"{total / 1048576:.2f} MiB.\n{status}"
    )
    summary.setWordWrap(True)
    layout.addWidget(summary)

    storage_base = (
        Path(os.environ.get(
            "XDG_DATA_HOME",
            str(Path.home() / ".local/share")
        ))
        / "kim6/email-attachments"
    )

    note = QLabel(
        "Prepared attachments are retained under:\\n"
        + str(storage_base)
        + "\\nDelete them when no longer needed. "
        "Opening the mail client does not send the message."
    )
    note.setWordWrap(True)
    layout.addWidget(note)

    buttons = QDialogButtonBox(
        QDialogButtonBox.Ok | QDialogButtonBox.Cancel
    )
    handoff = buttons.button(QDialogButtonBox.Ok)
    handoff.setText(
        "Open in " + client_names[mail_client]
    )
    handoff.setEnabled(not blocked)

    back_button = buttons.addButton(
        "Back to Options",
        QDialogButtonBox.ActionRole
    )

    def back_to_options():
        try:
            Path(str(plan_path) + ".back").write_text(
                "back", encoding="utf-8"
            )
        except OSError as error:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                dialog,
                "Cannot return to options",
                str(error)
            )
            return

        dialog.reject()

    back_button.clicked.connect(back_to_options)

    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    dialog.resize(710, min(700, 255 + 31 * min(len(records), 8)))
    return 0 if dialog.exec() == QDialog.Accepted else 130


def main():
    if (
        len(sys.argv) >= 5
        and sys.argv[1] == "email-options"
    ):
        return email_options_review(
            Path(sys.argv[2]),
            sys.argv[3],
            sys.argv[4:],
        )

    if (
        len(sys.argv) == 4
        and sys.argv[1] == "email-ready-review"
    ):
        return email_ready_review(
            Path(sys.argv[2]), sys.argv[3]
        )
    if (
        len(sys.argv) == 7
        and sys.argv[1] == "resize-output-review"
    ):
        return resize_output_review(
            Path(sys.argv[2]),
            Path(sys.argv[3]),
            sys.argv[4],
            sys.argv[5],
            sys.argv[6],
        )
    if len(sys.argv) >= 4 and sys.argv[1] == 'flipreview':
        _, _, operation, *files = sys.argv

        if operation not in ('flip', 'flop') or not files:
            raise ValueError('Invalid Flip review arguments')

        app = QApplication(sys.argv[:1])
        dialog = FlipReviewDialog(files, operation)

        return 0 if dialog.exec() == QDialog.Accepted else 130

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

    if kind == 'percent':
        kind = 'resize'
        files = ['--preset-percent', '50', *files]

    resize_percent = None
    if kind == 'resize' and files[:1] == ['--preset-percent']:
        if len(files) < 3:
            raise ValueError('Percentage resize needs selected images')
        resize_percent = files[1]
        files = files[2:]
    resize_preset = None
    if kind == 'resize' and files[:1] == ['--preset']:
        if len(files) < 3:
            raise ValueError('Resize preset needs a value and selected images')
        resize_preset = files[1]
        files = files[2:]
    resize_resume = None
    if kind == 'resize' and files[:1] == ['--resume-geometry']:
        if len(files) < 3:
            raise ValueError(
                'Resume needs a geometry and selected images'
            )
        resize_resume = files[1]
        files = files[2:]

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
    if resize_preset is not None:
        import re
        dimensions = re.fullmatch(
            r'([1-9][0-9]*)x([1-9][0-9]*)', resize_preset
        )
        if not dimensions:
            raise ValueError('Resize preset must be WIDTHxHEIGHT')
        width, height = map(int, dimensions.groups())
        if not (1 <= width <= 100000 and 1 <= height <= 100000):
            raise ValueError('Resize preset dimensions are out of range')
        dialog.fields['width'].setValue(width)
        dialog.fields['height'].setValue(height)
        if width == height:
            index = dialog.fields['preset'].findData(str(width))
            if index >= 0:
                dialog.fields['preset'].setCurrentIndex(index)
        dialog.refresh()
    if resize_percent is not None:
        import re

        if not re.fullmatch(r'[0-9]{1,4}', resize_percent):
            raise ValueError('Invalid percentage value')

        value = int(resize_percent)
        if not 1 <= value <= 1000:
            raise ValueError(
                'Percentage must be between 1 and 1000'
            )

        dialog.fields['method'].setCurrentIndex(
            dialog.fields['method'].findData('percent')
        )
        dialog.fields['percent'].setValue(value)
        dialog.refresh()

    if resize_resume is not None:
        import re

        percentage = re.fullmatch(
            r'([0-9]{1,4})%', resize_resume
        )
        dimensions = re.fullmatch(
            r'([1-9][0-9]*)x([1-9][0-9]*)([!>]?)',
            resize_resume,
        )

        if percentage:
            value = int(percentage.group(1))
            if not 1 <= value <= 1000:
                raise ValueError(
                    'Invalid saved Resize percentage'
                )

            dialog.fields['method'].setCurrentIndex(
                dialog.fields['method'].findData('percent')
            )
            dialog.fields['percent'].setValue(value)

        elif dimensions:
            width = int(dimensions.group(1))
            height = int(dimensions.group(2))
            suffix = dimensions.group(3)

            if not (
                1 <= width <= 100000
                and 1 <= height <= 100000
            ):
                raise ValueError(
                    'Invalid saved Resize dimensions'
                )

            method = 'exact' if suffix == '!' else 'fit'

            dialog.fields['method'].setCurrentIndex(
                dialog.fields['method'].findData(method)
            )
            dialog.fields['width'].setValue(width)
            dialog.fields['height'].setValue(height)

            if method == 'fit':
                dialog.fields['upscale'].setChecked(
                    suffix != '>'
                )
        else:
            raise ValueError(
                'Unsupported saved Resize geometry'
            )

        dialog.refresh()

    if initial is not None: dialog.fields['mode'].setCurrentIndex(dialog.fields['mode'].findData(initial)); dialog.refresh()
    if dialog.exec()!=QDialog.Accepted: return 130 if kind in ('convert','copyright','strip','rename','rotate') else 1
    if kind=='compress':
        import os
        approved=[]

        for path in dialog.compress_eligible:
            info=os.lstat(path)
            stamp=(
                info.st_dev,info.st_ino,info.st_size,
                info.st_mtime_ns,info.st_ctime_ns
            )
            if stamp!=dialog.header_stamps[path]:
                raise ValueError(
                    'Image changed after compression review: '
                    +Path(path).name
                )
            approved.extend((
                path,':'.join(map(str,stamp))
            ))

        dialog.values.extend(approved)

    if kind=='rename':
        from kim_preview import save_plan
        save_plan(result+'.approved',dialog.rename_approved)
    Path(result).write_bytes(b''.join(v.encode()+b'\0' for v in dialog.values)); return 0


if __name__=='__main__': raise SystemExit(main())
