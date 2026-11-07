"""Image location tools over the existing approved-plan engine."""
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys
import json
import os

from PySide6.QtCore import QThread, Signal, QTimer, Qt, QSize, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox,
    QDialogButtonBox, QStyle, QFileDialog, QWidget, QScrollArea,
    QSplitter,
    QStackedWidget, QGroupBox, QMessageBox, QSizePolicy, QToolButton, QTabWidget)

from kim_location import TITLES, build_plan, coordinate, number, source_info, summarize, optional_gps, MAX_FILES
from kim_preview import verify_plan, save_plan, identity, absolute
from kim_location_ui import (preferred_units, unit_preference, persist_units, altitude_to_metres,
    altitude_from_metres, distance, position_text, reference_caption, location_unit_choices,
    open_camera_map, output_description, location_result_message, camera_status, destination_status, blocked_destination, gps_metadata_changes, gps_summary_changes,
    LocationInspector, ElidedImageLabel, operation_inspector_rows, privacy_inspector_rows)
from kim_photo_selection import choose_images, ThumbnailWorker, PhotoPreview, ImageList, photo_extensions
from kim_location_map import LocationMap, check_graphical_session


class LocationWorker(QThread):
    inspection_progress = Signal(int, int, str)

    def __init__(self, kind, policy, files, config, seeds, cache, track_cache, parent):
        super().__init__(parent)
        self.arguments = kind, policy, files, config, seeds
        self.cache = cache; self.track_cache = track_cache; self.plan = None; self.error = None

    def run(self):
        try:
            self.plan = build_plan(*self.arguments, cache=self.cache, track_cache=self.track_cache,
                                   progress=self.inspection_progress.emit, cancelled=self.isInterruptionRequested)
        except Exception as exc: self.error = str(exc)


class LocationDialog(QDialog):
    def __init__(self, kind, files, policy, seeds, initial=None):
        super().__init__()
        self.kind, self.files, self.policy, self.seeds = kind, [absolute(p) for p in files], policy, seeds
        self.selection_only = policy == 'select'
        if self.selection_only: self.policy = 'create'
        self.worker = None; self.thumbnail_worker = None; self.thumbnail_queue = []
        self.pending = False; self.closing = False; self.accept_after_thumbnails = False; self.completed_report = False
        self.plan = None; self.cache = {}; self.track_cache = {}; self.inputs = {}; self.display_entries = []
        self.initial_reference_checked = bool(initial); self.reference = ''; self.map_position = None; self.altitude_metres = ''
        self.unit_preference = unit_preference(); self.units = preferred_units(self.unit_preference)
        self.apply_button = None; self.candidate_items = {}; self.thumbnail_stamps = {}; self.thumbnail_icons = {}
        self.visual_source = ''; self.usable_reference_paths = []
        self.pending_reference_choice = ''
        self.setWindowTitle('KIM6 - ' + TITLES[kind].rstrip('…'))
        available = self.screen().availableGeometry()
        self.resize(min(1120, available.width()*9//10), min(760, available.height()*9//10))
        layout = QVBoxLayout(self)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(350)
        self.timer.timeout.connect(self.start_plan)
        top = QHBoxLayout()
        title = QLabel('Inspect location metadata - Read only' if kind == 'report' else TITLES[kind].rstrip('…'))
        font = title.font(); font.setBold(True); title.setFont(font); top.addWidget(title, 1)
        measurement_label = QLabel('&Units:'); top.addWidget(measurement_label)
        self.unit_choice = QComboBox()
        for text, value in location_unit_choices(): self.unit_choice.addItem(text, value)
        self.unit_choice.setCurrentIndex(self.unit_choice.findData(self.unit_preference))
        measurement_label.setBuddy(self.unit_choice); top.addWidget(self.unit_choice)
        self.unit_choice.setToolTip('System follows desktop units. The other choice overrides them. Stored GPS values are unchanged.')
        layout.addLayout(top)
        self.summary = self.label('Reading image locations…')
        if kind == 'report': layout.addWidget(self.summary)
        self.context = self.label(''); self.context.hide(); layout.addWidget(self.context)
        visual_region = QWidget(); visual_layout = QVBoxLayout(visual_region); visual_layout.setContentsMargins(0, 0, 0, 0)
        self.main_splitter = QSplitter(Qt.Horizontal); self.main_splitter.setChildrenCollapsible(False)
        sidebar = QWidget(); sidebar.setMinimumWidth(0)
        side_layout = QVBoxLayout(sidebar); side_layout.setContentsMargins(0, 0, 0, 0)
        self.controls = QWidget(); control_layout = QVBoxLayout(self.controls); control_layout.setContentsMargins(0, 0, 0, 0)
        self.controls.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        control_layout.setAlignment(Qt.AlignTop)
        if kind == 'apply': self.build_location_methods(control_layout)
        elif kind == 'reduce':
            self.build_reduction_controls(control_layout)
            self.controls.setSizePolicy(
                QSizePolicy.Preferred,
                QSizePolicy.Maximum,
            )
        for form in self.controls.findChildren(QFormLayout): form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        if kind == 'apply': self.source_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        if kind != 'report': visual_layout.insertWidget(0, self.controls, 0, Qt.AlignTop)
        destination_actions = QHBoxLayout()
        self.add_images = QPushButton(QIcon.fromTheme('list-add'), 'Add images…')
        self.add_images.clicked.connect(self.add_destinations); self.add_images.setVisible(self.selection_only)
        destination_actions.addWidget(self.add_images)
        self.remove_image = QPushButton(QIcon.fromTheme('list-remove'), 'Remove')
        self.remove_image.setToolTip('Remove the selected destination from this operation. The image is not deleted.')
        self.remove_image.clicked.connect(self.remove_destination); self.remove_image.setVisible(self.selection_only)
        destination_actions.addWidget(self.remove_image); side_layout.addLayout(destination_actions)
        self.images_heading = QLabel('Images' if kind == 'report' else 'Images to update')
        heading_font = self.images_heading.font(); heading_font.setBold(True); self.images_heading.setFont(heading_font)
        side_layout.addWidget(self.images_heading)
        if kind != 'report': side_layout.addWidget(self.summary)
        self.image_list = ImageList(self)
        self.inspector = LocationInspector('Location Information' if kind == 'report' else 'Selected destination', self)
        if kind == 'report':
            side_layout.addWidget(self.image_list, 1)
        else:
            self.destination_splitter = QSplitter(Qt.Vertical); self.destination_splitter.setChildrenCollapsible(False)
            self.destination_splitter.addWidget(self.image_list); self.destination_splitter.addWidget(self.inspector)
            self.destination_splitter.setSizes([300, 220])
            self.destination_splitter.setStretchFactor(0, 1); self.destination_splitter.setStretchFactor(1, 1)
            side_layout.addWidget(self.destination_splitter, 1)
        self.sidebar = sidebar; self.main_splitter.addWidget(sidebar)
        self.visual_splitter = QSplitter(Qt.Horizontal); self.visual_splitter.setChildrenCollapsible(False)
        photo_panel = QWidget(); photo_panel.setMinimumWidth(0)
        photo_container = QVBoxLayout(photo_panel); photo_container.setContentsMargins(0, 0, 0, 0)
        photo_content = QWidget(); photo_content.setMinimumWidth(0)
        photo_layout = QVBoxLayout(photo_content); photo_layout.setContentsMargins(0, 0, 0, 0)
        self.photo_stack = QSplitter(Qt.Vertical); self.photo_stack.setChildrenCollapsible(False)
        self.photo_stack.addWidget(photo_content); photo_container.addWidget(self.photo_stack, 1)
        self.visual_role = self.label('GPS source image' if self.uses_reference() else 'Selected image')
        self.visual_role.setFont(heading_font); photo_layout.addWidget(self.visual_role)
        self.photo_preview = PhotoPreview(self); photo_layout.addWidget(self.photo_preview, 1)
        self.selected_image = self.label('Select an image'); self.selected_image.setFont(heading_font); photo_layout.addWidget(self.selected_image)
        self.selected_location = self.label(''); photo_layout.addWidget(self.selected_location)
        self.selected_location.setVisible(kind != 'report')
        action_row = QHBoxLayout()
        self.report_copy = QPushButton(QIcon.fromTheme('edit-copy'), 'Copy &Coordinates')
        self.report_copy.setEnabled(False); self.report_copy.clicked.connect(self.copy_selected_coordinates); action_row.addWidget(self.report_copy)
        self.report_map = QPushButton(QIcon.fromTheme('globe'), 'Open in &Browser')
        self.report_map.setEnabled(False); self.report_map.clicked.connect(self.map_selected_coordinates); action_row.addWidget(self.report_map)
        photo_layout.addLayout(action_row)
        self.reference_options = QWidget(); options = QVBoxLayout(self.reference_options); options.setContentsMargins(0, 0, 0, 0)
        self.copy_altitude = QCheckBox('Copy altitude'); self.copy_altitude.setChecked(False)
        self.copy_direction = QCheckBox('Copy recorded image direction')
        for control in (self.copy_altitude, self.copy_direction): options.addWidget(control); control.toggled.connect(self.schedule_plan)
        self.copy_altitude.setToolTip('Unchecked: remove destination altitude. Checked: copy the GPS source altitude with its recorded height reference.')
        self.copy_direction.setToolTip('Unchecked: remove destination direction. Checked: copy the GPS source’s recorded direction and its north reference.')
        photo_layout.addWidget(self.reference_options); self.reference_options.hide()
        if kind == 'report':
            self.photo_stack.addWidget(self.inspector); self.photo_stack.setSizes([360, 240])
            self.photo_stack.setStretchFactor(0, 1); self.photo_stack.setStretchFactor(1, 1)
        self.photo_panel = photo_panel; self.visual_splitter.addWidget(photo_panel)
        map_panel = QWidget(); map_panel.setMinimumWidth(0)
        map_layout = QVBoxLayout(map_panel); map_layout.setContentsMargins(0, 0, 0, 0)
        self.map_heading = QLabel('GPS source location' if self.uses_reference() else 'GPS Location')
        self.map_heading.setFont(heading_font); map_layout.addWidget(self.map_heading)
        self.map_subject = QComboBox(); self.map_subject.addItem('Original GPS location', 'existing'); self.map_subject.addItem('New GPS location', 'proposed')
        self.map_subject.setCurrentIndex(1 if kind == 'reduce' else 0)
        self.map_subject.currentIndexChanged.connect(self.update_visual); map_layout.addWidget(self.map_subject); self.map_subject.hide()
        self.location_map = LocationMap(self, units=self.units); map_layout.addWidget(self.location_map, 1)
        self.map_panel = map_panel; self.visual_splitter.addWidget(map_panel); self.visual_splitter.setSizes([420, 420])
        visual_host = QWidget(); visual_host.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        host_layout = QVBoxLayout(visual_host); host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.addWidget(self.visual_splitter)
        self.visual_tabs = QTabWidget(); self.visual_tabs.hide(); host_layout.addWidget(self.visual_tabs); self.visual_tab_mode = False
        self.main_splitter.addWidget(visual_host); self.main_splitter.setSizes([360, 740])
        self.main_splitter.setStretchFactor(0, 1); self.main_splitter.setStretchFactor(1, 1)
        visual_layout.addWidget(self.main_splitter, 1)
        # Technical controls live in the report dialog. The compact inspector
        # summary always describes the selected destination.
        self.details_subject = QComboBox()
        self.details_subject.addItem('Selected destination metadata', 'destination')
        self.details_subject.addItem('GPS source metadata', 'reference')
        self.details_subject.setAccessibleName('Image whose full metadata is inspected')
        self.details_subject.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.details_subject.setMinimumContentsLength(12); self.details_subject.setMinimumWidth(0)
        self.details_subject.currentIndexChanged.connect(self.refresh_inspector)
        self.inspector.metadata_controls.addWidget(self.details_subject); self.details_subject.hide()
        self.details_title = ElidedImageLabel(); self.inspector.metadata_controls.addWidget(self.details_title)
        self.detail_source = ''
        detail_actions = QHBoxLayout()
        self.details_copy = QToolButton(); self.details_copy.setIcon(QIcon.fromTheme('edit-copy'))
        self.details_copy.setText('Copy coordinates'); self.details_copy.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.details_copy.setToolTip('Copy camera coordinates from the image named in Technical metadata')
        self.details_copy.setEnabled(False); self.details_copy.clicked.connect(self.copy_detail_coordinates)
        detail_actions.addWidget(self.details_copy); self.details_copy.setVisible(kind != 'report')
        self.details_browser = QToolButton(); self.details_browser.setIcon(QIcon.fromTheme('globe'))
        self.details_browser.setText('Open in Browser'); self.details_browser.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.details_browser.setToolTip('Open the camera coordinates of the image named in Technical metadata')
        self.details_browser.setEnabled(False); self.details_browser.clicked.connect(self.map_detail_coordinates)
        detail_actions.addWidget(self.details_browser); self.details_browser.setVisible(kind != 'report')
        self.inspector.metadata_controls.addLayout(detail_actions)
        self.inspector.metadata_button.clicked.connect(self.show_selected_metadata)
        layout.addWidget(visual_region, 1)
        self.image_list.path_changed.connect(self.show_selected_details)
        self.image_list.list.itemClicked.connect(self.choose_reference_from_list)
        self.image_list.list.itemActivated.connect(self.choose_reference_from_list)
        self.photo_preview.idle.connect(self.visual_idle)
        self.image_list.set_entries([dict(source=p, caption='Reading GPS location…') for p in self.files])
        buttons_row = QHBoxLayout()
        self.refresh_button = QPushButton(QIcon.fromTheme('view-refresh'), '&Refresh'); self.refresh_button.clicked.connect(self.schedule_plan)
        buttons_row.addWidget(self.refresh_button); buttons_row.addStretch()
        if kind == 'report':
            self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
            self.buttons.rejected.connect(self.reject)
            buttons_row.addWidget(self.buttons)
        else:
            policy_text = 'Choose output policy after source selection.' if self.selection_only else 'Create new images; originals unchanged.' if self.policy == 'create' else 'Replace reviewed originals: explicitly approved.'
            policy_label = self.label(policy_text); layout.addWidget(policy_label)

            self.apply_button = QPushButton(
                QIcon.fromTheme('dialog-ok-apply', self.style().standardIcon(QStyle.SP_DialogApplyButton)),
                'Review changes…' if self.selection_only else 'Apply changes'
            )
            self.apply_button.setEnabled(False)
            self.apply_button.clicked.connect(self.accept)
            buttons_row.addWidget(self.apply_button)

            self.cancel_button = QPushButton(
                QIcon.fromTheme('dialog-cancel', self.style().standardIcon(QStyle.SP_DialogCancelButton)),
                'Cancel'
            )
            self.cancel_button.clicked.connect(self.reject)
            buttons_row.addWidget(self.cancel_button)

        layout.addLayout(buttons_row)
        for button in self.findChildren(QPushButton): button.setAutoDefault(False)
        if kind == 'report': self.buttons.button(QDialogButtonBox.Close).setDefault(True)
        self.setTabOrder(self.image_list.search, self.image_list.sort); self.setTabOrder(self.image_list.sort, self.image_list.list)
        self.setTabOrder(self.image_list.list, self.report_copy); self.setTabOrder(self.report_copy, self.report_map)
        self.setTabOrder(self.report_map, self.location_map.online); self.setTabOrder(self.location_map.online, self.location_map.canvas)
        self.unit_choice.currentIndexChanged.connect(self.change_units)
        QImageReader.setAllocationLimit(32)
        if initial: self.restore_input(initial)
        self.schedule_plan()
        self.thumbnail_queue = list(dict.fromkeys([*self.files, *self.candidate_items]))
        QTimer.singleShot(0, self.start_thumbnails)

    @staticmethod
    def label(text):
        label = QLabel(text); label.setTextFormat(Qt.PlainText); label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        label.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.TextSelectableByKeyboard)
        label.setFocusPolicy(Qt.ClickFocus)
        return label

    def add_text(self, key, placeholder, value=''):
        field = QLineEdit(value); field.setPlaceholderText(placeholder); field.setClearButtonEnabled(True)
        field.setMaxLength(500); field.textChanged.connect(self.schedule_plan); self.inputs[key] = field
        return field

    def add_check(self, key, label):
        field = QCheckBox(label); field.toggled.connect(self.schedule_plan); self.inputs[key] = field
        return field

    def build_location_methods(self, layout):
        form = QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        self.source_form = form
        self.method = QComboBox()
        for title, key in [('Another Image', 'photo'), ('Point on Map', 'map'), ('Manual Coordinates', 'manual'), ('GPX Track', 'gpx')]: self.method.addItem(title, key)
        form.addRow('&Location source', self.method); layout.addLayout(form)
        self.method_pages = QStackedWidget(); self.method_pages.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum); layout.addWidget(self.method_pages)
        photo_page = QWidget(); photo_layout = QVBoxLayout(photo_page); photo_layout.setContentsMargins(0, 0, 0, 0)
        self.candidates = QComboBox(); self.candidates.setIconSize(QSize(48, 36))
        self.candidates.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon); self.candidates.setMinimumContentsLength(16)
        self.candidates.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.candidates.setPlaceholderText('Choose the GPS source image'); self.candidates.setAccessibleName('GPS source image, supplies coordinates and remains unchanged')
        self.candidates.view().setTextElideMode(Qt.ElideMiddle)
        self.placeholder_icon = QIcon.fromTheme('image-x-generic')
        for path in self.files: self.add_candidate(path)
        self.candidates.setCurrentIndex(-1); self.candidates.currentIndexChanged.connect(self.select_reference)
        reference_row = QHBoxLayout(); reference_row.addWidget(self.candidates, 1)
        browse = QPushButton(QIcon.fromTheme('document-open'), '&Browse…'); browse.clicked.connect(self.choose_reference); browse.setToolTip('Browse for GPS source image'); reference_row.addWidget(browse); photo_layout.addLayout(reference_row)
        self.candidate_help = self.label('Choose the image that supplies GPS.'); photo_layout.addWidget(self.candidate_help)
        self.method_pages.addWidget(photo_page)
        map_page = QWidget(); map_layout = QVBoxLayout(map_page); map_layout.setContentsMargins(0, 0, 0, 0)
        map_button = QPushButton('Choose on Map…'); map_button.clicked.connect(self.open_map); map_layout.addWidget(map_button)
        self.map_label = self.label('No location selected.'); map_layout.addWidget(self.map_label)
        map_layout.addWidget(self.label('Applies to all destinations. Old altitude and direction are removed.'))
        self.method_pages.addWidget(map_page)
        manual_page = QWidget(); manual_form = QFormLayout(manual_page); manual_form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        for key, label, hint in [('latitude', 'Latitude (−90 to +90)', 'Signed decimal degrees; north is positive'), ('longitude', 'Longitude (−180 to +180)', 'Signed decimal degrees; east is positive')]:
            field = self.add_text(key, hint); field.textChanged.connect(self.update_coordinate_readout); manual_form.addRow(label, field)
        self.coordinate_readout = self.label('Enter decimal coordinates.'); manual_form.addRow(self.coordinate_readout)
        self.altitude_label = QLabel('Altitude (optional, ft)' if self.units == 'imperial' else 'Altitude (optional, m)')
        altitude = self.add_text('altitude', 'Blank removes old altitude'); altitude.textChanged.connect(self.capture_altitude); manual_form.addRow(self.altitude_label, altitude)
        manual_form.addRow('Image direction (optional, degrees)', self.add_text('direction', '0 to less than 360; from true north'))
        map_here = QPushButton('Choose on Map at These Coordinates…'); map_here.clicked.connect(self.open_manual_map); manual_form.addRow(map_here)
        self.add_source_page(manual_page)
        gpx_page = QWidget(); gpx_layout = QVBoxLayout(gpx_page)
        manual_inputs, self.inputs = self.inputs, {}
        self.build_gpx_controls(gpx_layout)
        self.gpx_inputs, self.inputs = self.inputs, manual_inputs
        self.add_source_page(gpx_page)
        self.method.currentIndexChanged.connect(self.change_method)
        for i in range(self.method_pages.count()):
            self.method_pages.widget(i).setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred if i == 0 else QSizePolicy.Ignored)
        self.fit_method_page()

    def add_candidate(self, path):
        self.candidates.addItem(self.placeholder_icon, Path(path).name + ': Reading GPS coordinates…', path)
        item = self.candidates.model().item(self.candidates.count() - 1)
        item.setToolTip(path); self.candidate_items[path] = item
        return item

    def build_gpx_controls(self, layout):
        track_group = QGroupBox('GPX track'); form = QFormLayout(track_group)
        row = QHBoxLayout(); row.addWidget(self.add_text('gpx', 'Choose the GPX track recorded during this image session'), 1)
        browse = QPushButton('Choose GPX track…'); browse.clicked.connect(self.choose_gpx); row.addWidget(browse)
        form.addRow('Track file', row); self.track_label = self.label('Choose a GPX track to see its date range and number of points.'); form.addRow(self.track_label)
        layout.addWidget(track_group)
        clock = QGroupBox('Camera clock and timezone'); form = QFormLayout(clock)
        form.addRow('Camera timezone', self.add_text('timezone', 'UTC, ±HH:MM, or a timezone such as America/New_York'))
        form.addRow(self.label('Embedded camera timezone offsets take priority. Without an embedded offset, enter the camera timezone explicitly. Image capture dates stay unchanged.'))
        advanced_toggle = QCheckBox('Advanced clock calibration'); form.addRow(advanced_toggle); self.clock_advanced = advanced_toggle
        advanced = QWidget(); advanced_form = QFormLayout(advanced)
        advanced_form.addRow('Clock correction (seconds)', self.add_text('seconds', 'Signed seconds, including fractions; positive moves time later', '0'))
        self.drift = QCheckBox('Use two synchronization points to correct clock drift')
        self.drift.toggled.connect(self.schedule_plan); advanced_form.addRow(self.drift)
        self.sync_fields = []
        for index in (1, 2):
            camera = self.add_text('camera' + str(index), 'YYYY-MM-DD HH:MM:SS[.fraction][±HH:MM]')
            gps = self.add_text('gps' + str(index), 'YYYY-MM-DD HH:MM:SS[.fraction]Z (UTC)')
            advanced_form.addRow(f'Point {index}: camera time', camera); advanced_form.addRow(f'Point {index}: GPS time (UTC)', gps)
            self.sync_fields.extend([camera, gps]); camera.setEnabled(False); gps.setEnabled(False)
        self.drift.toggled.connect(self.toggle_sync_fields)
        advanced_form.addRow(self.label('Clock drift follows the line through these two pairs, then adds the clock correction. Ambiguous daylight-saving times require an explicit UTC offset.'))
        advanced.setVisible(False); advanced_toggle.toggled.connect(advanced.setVisible); form.addRow(advanced); layout.addWidget(clock)
        matching = QGroupBox('Matching options'); form = QFormLayout(matching)
        form.addRow('Maximum gap between track points (minutes)', self.add_text('gap_minutes', 'Minutes, including fractions', '5'))
        form.addRow(self.add_check('altitude', 'Include recorded track elevation when available'))
        form.addRow(self.label('Images must match a recorded track segment. Gaps and unmatched images stop Apply Changes; positions are never guessed beyond the track.'))
        layout.addWidget(matching)

    def build_reduction_controls(self, layout):
        # Give the image list, photo preview and map the available height.
        layout.setSpacing(5)

        row = QHBoxLayout()
        row.addWidget(QLabel('Reduce GPS precision to:'))

        self.grid = QComboBox()

        for value in (100, 1000, 5000, 10000):
            self.grid.addItem('', value)

        self.grid.setCurrentIndex(1)
        self.update_grid_labels()
        self.grid.currentIndexChanged.connect(self.schedule_plan)

        row.addWidget(self.grid, 1)
        layout.addLayout(row)

        note = self.label(
            'Exact coordinates are replaced by the grid center; '
            'structured place names are removed.'
        )
        note.setSizePolicy(
            QSizePolicy.Preferred,
            QSizePolicy.Maximum,
        )

        layout.addWidget(note)


    def update_grid_labels(self):
        for index in range(self.grid.count()): self.grid.setItemText(index, 'About ' + distance(self.grid.itemData(index), self.units) + ' across')

    def toggle_sync_fields(self, enabled):
        for field in self.sync_fields: field.setEnabled(enabled)

    def choose_gpx(self):
        picker = QFileDialog(self, 'Choose a local GPX track'); picker.setFileMode(QFileDialog.ExistingFile)
        picker.setSupportedSchemes(['file']); picker.setNameFilters(['GPX tracks (*.gpx *.GPX)', 'All Files (*)'])
        if picker.exec() == QDialog.Accepted and picker.selectedFiles(): self.gpx_inputs['gpx'].setText(picker.selectedFiles()[0])

    def choose_reference(self):
        paths = choose_images(self, str(Path(self.reference or self.files[0]).parent),
                              title='Choose a GPS source image', multiple=False,
                              extensions=photo_extensions(), accept_label='Choose GPS Source')
        if not paths: return
        path = absolute(paths[0])
        item = self.candidate_items.get(path)
        if item is None:
            for old in list(self.candidate_items):
                if old not in self.files:
                    old_item = self.candidate_items.pop(old)
                    self.candidates.removeItem(old_item.row())
                    self.thumbnail_stamps.pop(old, None); self.thumbnail_icons.pop(old, None)
            item = self.add_candidate(path); self.thumbnail_queue.append(path); self.start_thumbnails()
        self.candidates.setCurrentIndex(item.row())

    def select_reference(self, index):
        self.reference = self.candidates.itemData(index) if index >= 0 else ''
        self.pending_reference_choice = ''; self.initial_reference_checked = True
        self.context.clear(); self.context.hide()
        self.schedule_plan()
        if hasattr(self, 'image_list'): self.render_image_list()
        self.update_reference_preview()

    def choose_reference_from_list(self, item):
        # Only explicit mouse / keyboard activation can fill an empty reference.
        # Programmatic refresh, sorting, and selection changes never choose one.
        if not self.uses_reference() or self.reference or not item: return
        self.initial_reference_checked = True
        path = item.data(Qt.UserRole)
        if self.worker or self.timer.isActive():
            self.pending_reference_choice = path; return
        self.apply_reference_choice(path)

    def apply_reference_choice(self, path, refresh_missing=True):
        if path not in self.files: return False
        data = source_info(path, self.cache)
        if data is None and refresh_missing:
            self.pending_reference_choice = path; self.schedule_plan(); return True
        try: info = summarize(data['raw']) if data and not data.get('error') else None
        except ValueError: info = None
        if not info or info['position'] is None:
            self.context.setText('This image has no usable, unambiguous camera GPS. Choose another image or browse for a GPS source.')
            self.context.show(); return False
        item = self.candidate_items.get(path)
        if item is None: return False
        self.candidates.setCurrentIndex(item.row())
        return True

    def update_reference_preview(self):
        if hasattr(self, 'photo_preview'): self.update_visual()

    def start_thumbnails(self):
        if self.closing or self.thumbnail_worker or not self.thumbnail_queue: return
        paths, self.thumbnail_queue = self.thumbnail_queue, []
        self.thumbnail_worker = ThumbnailWorker(paths, QSize(120, 90), self)
        self.thumbnail_worker.thumbnail_ready.connect(self.receive_thumbnail)
        self.thumbnail_worker.finished.connect(self.thumbnails_finished); self.thumbnail_worker.start()

    def receive_thumbnail(self, path, image, stamp):
        try: valid = stamp is not None and identity(path) == stamp
        except (OSError, ValueError): valid = False
        if image.isNull() or not valid: return
        icon = QIcon(QPixmap.fromImage(image)); self.thumbnail_stamps[path] = stamp; self.thumbnail_icons[path] = icon
        self.image_list.set_thumbnail(path, icon)
        if path in self.candidate_items: self.candidate_items[path].setIcon(icon)

    def thumbnails_finished(self):
        worker, self.thumbnail_worker = self.thumbnail_worker, None; worker.deleteLater()
        if self.closing: self.finish_close_when_idle()
        elif self.accept_after_thumbnails:
            self.accept_after_thumbnails = False; self.accept()
        else: self.start_thumbnails()

    def fit_method_page(self):
        """Avoid reserving GPX-form height when another source page is shown."""
        page = self.method_pages.currentWidget()
        if page is None: return
        height = max(1, min(page.sizeHint().height(), page.maximumHeight()))
        if self.method_pages.maximumHeight() != height:
            self.method_pages.setMaximumHeight(height)

    def change_method(self, index):
        self.method_pages.setCurrentIndex(index)
        self.pending_reference_choice = ''
        if self.selection_only and self.method.currentData() == 'photo' and not self.reference:
            self.initial_reference_checked = False
        for i in range(self.method_pages.count()):
            self.method_pages.widget(i).setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred if i == index else QSizePolicy.Ignored)
        self.fit_method_page()
        self.schedule_plan(); self.update_visual()

    def capture_altitude(self):
        text = self.inputs['altitude'].text().strip()
        try: self.altitude_metres = altitude_to_metres(text, self.units) if text else ''
        except (InvalidOperation, ValueError): self.altitude_metres = None

    def change_units(self):
        preference = self.unit_choice.currentData(); chosen = preferred_units(preference)
        if preference == self.unit_preference: return
        # Never reinterpret an invalid, already-entered altitude under new units.
        if self.kind == 'apply' and self.altitude_metres is None:
            self.unit_choice.blockSignals(True); self.unit_choice.setCurrentIndex(self.unit_choice.findData(self.unit_preference)); self.unit_choice.blockSignals(False)
            QMessageBox.information(self, 'Check altitude', 'Correct or clear the altitude before changing measurement units.'); return
        self.units = chosen; self.unit_preference = preference; self.location_map.set_units(chosen)
        if self.kind == 'apply':
            field = self.inputs['altitude']; field.blockSignals(True)
            field.setText(altitude_from_metres(self.altitude_metres, chosen) if self.altitude_metres != '' else '')
            field.blockSignals(False); self.altitude_label.setText('Altitude (optional, ft)' if chosen == 'imperial' else 'Altitude (optional, m)')
        if self.kind == 'reduce': self.update_grid_labels()
        try: persist_units(preference)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Measurement preference was not saved', 'The units changed for this session, but could not be saved:\n' + str(exc))
        self.schedule_plan()

    def manual_position(self):
        return [coordinate(self.inputs['latitude'].text().strip(), None, True), coordinate(self.inputs['longitude'].text().strip(), None, False)]

    def update_coordinate_readout(self):
        try: text = position_text(self.manual_position())
        except ValueError as exc: text = str(exc)
        self.coordinate_readout.setText(text)

    def open_manual_map(self):
        try: initial = self.manual_position()
        except ValueError as exc: QMessageBox.information(self, 'Check coordinates', str(exc)); return
        self.open_map(initial=initial, into_manual=True)

    def open_map(self, checked=False, initial=None, into_manual=False):
        if initial is None:
            initial = self.map_position
            if initial is None:
                try: initial = self.manual_position()
                except ValueError: pass
            if initial is None and self.reference and not self.worker:
                data = source_info(self.reference, self.cache)
                if data:
                    try: initial = summarize(data['raw'])['position']
                    except ValueError: pass
        from kim_location_map import choose_location
        point = choose_location(self, initial, self.units)
        if point is None: return
        if into_manual:
            self.inputs['latitude'].setText(f'{point[0]:.12f}'); self.inputs['longitude'].setText(f'{point[1]:.12f}')
        else:
            self.map_position = point; self.map_label.setText('Selected location: ' + position_text(point))
        self.schedule_plan()

    def config(self):
        result = {'units': self.units}
        if self.kind == 'apply':
            method = self.method.currentData(); result['method'] = method
            if method == 'photo':
                result.update(reference=self.reference, altitude=self.copy_altitude.isChecked(), direction=self.copy_direction.isChecked())
            elif method == 'map':
                result.update(latitude=f'{self.map_position[0]:.12f}' if self.map_position else '', longitude=f'{self.map_position[1]:.12f}' if self.map_position else '', altitude='', direction='')
            elif method == 'gpx': result.update(self.gpx_config())
            else:
                result.update(latitude=self.inputs['latitude'].text().strip(), longitude=self.inputs['longitude'].text().strip(), altitude=self.altitude_metres if self.altitude_metres is not None else 'invalid altitude', direction=self.inputs['direction'].text().strip())
        elif self.kind == 'reduce': result['grid'] = self.grid.currentData()
        return result

    def gpx_config(self):
        result = {key: field.isChecked() if isinstance(field, QCheckBox) else field.text().strip() for key, field in self.gpx_inputs.items()}
        result['sync'] = [[result.pop('camera' + str(i)), result.pop('gps' + str(i))] for i in (1, 2)]
        if not self.drift.isChecked(): result['sync'] = []
        try: result['gap'] = str(number(result.pop('gap_minutes'), 'matching gap in minutes', 0, 1440) * 60)
        except ValueError: result['gap'] = 'invalid matching gap'
        return result

    def engine_kind(self):
        return 'gpx' if self.kind == 'apply' and self.method.currentData() == 'gpx' else self.kind

    def add_source_page(self, page):
        # Only the longer manual / GPX settings scroll. Reference selection never
        # lives inside a narrow, nested scroll area.
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setWidget(page)
        scroll.setFrameShape(QScrollArea.NoFrame); scroll.setMinimumHeight(self.fontMetrics().lineSpacing()*4)
        scroll.setMaximumHeight(self.fontMetrics().lineSpacing()*11)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff); self.method_pages.addWidget(scroll)

    def destination_count(self):
        return len(self.files) - int(self.uses_reference() and self.reference in self.files)

    def choose_initial_reference(self):
        if self.kind != 'apply' or self.initial_reference_checked: return False
        self.initial_reference_checked = True
        if not self.uses_reference() or self.reference or len(self.files) < 2: return False
        eligible = []
        for path in self.files:
            data = source_info(path, self.cache)
            if data and not data.get('error'):
                info = summarize(data['raw'])
                if info['position'] is not None: eligible.append(path)
        if len(eligible) != 1: return False
        self.candidates.setCurrentIndex(self.candidate_items[eligible[0]].row())
        return True

    def reference_instruction(self):
        if self.reference:
            if not self.destination_count(): return 'No destination images. Add images, or select destination images in Dolphin.'
            return 'The GPS source supplies coordinates; no output is created for it.'
        usable = self.usable_reference_paths
        if len(usable) > 1: return 'Several images have camera GPS. Choose which image supplies the location.'
        if len(self.files) == 1 and usable: return 'This image has GPS. Choose it as the GPS source and add destinations, or browse for another GPS source.'
        return 'Choose the GPS source image here or in the image list.'

    def add_destinations(self):
        if not self.selection_only: return
        paths = choose_images(self, str(Path(self.files[0]).parent), title='Add Destination Images',
                              extensions=photo_extensions())
        if not paths: return
        try:
            added = []
            for raw in paths:
                path = absolute(raw); identity(path)
                if path not in self.files and path not in added: added.append(path)
            if len(self.files) + len(added) > MAX_FILES: raise ValueError(f'Select at most {MAX_FILES} images.')
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Could not add images', str(exc)); return
        for path in added:
            self.files.append(path); self.add_candidate(path); self.thumbnail_queue.append(path)
        if not self.reference: self.initial_reference_checked = False
        self.schedule_plan(); self.start_thumbnails()

    def remove_destination(self):
        if not self.selection_only: return
        path = self.image_list.current_path()
        if not path or path == self.reference and self.uses_reference(): return
        if len(self.files) == 1:
            QMessageBox.information(self, 'Keep an image selected', 'Add another destination before removing this image.'); return
        self.files.remove(path)
        if path in self.candidate_items:
            item = self.candidate_items.pop(path); self.candidates.removeItem(item.row())
        self.schedule_plan()

    def schedule_plan(self, *_):
        self.accept_after_thumbnails = False; self.plan = None
        if hasattr(self, 'report_copy'):
            self.report_copy.setEnabled(False); self.report_map.setEnabled(False)
            self.location_map.set_position(None, 'Refreshing GPS location…')
        if self.apply_button: self.apply_button.setEnabled(False)
        if self.worker: self.pending = True; self.worker.requestInterruption()
        self.timer.start()
        self.refresh_inspector()

    def start_plan(self):
        if self.closing: return
        if self.worker: self.pending = True; self.worker.requestInterruption(); return
        self.pending = False; self.plan = None; self.summary.setText('Reading image locations…')
        self.context.setText(''); self.context.hide()
        config = self.config()
        if self.selection_only: config['inspect_only'] = True
        self.report_copy.setEnabled(False); self.report_map.setEnabled(False)
        self.worker = LocationWorker(self.engine_kind(), self.policy, self.files, config, self.seeds, self.cache, self.track_cache, self)
        self.worker.inspection_progress.connect(self.on_location_progress)
        self.worker.finished.connect(self.on_location_plan_ready); self.worker.start()

    def on_location_progress(self, index, total, path):
        self.summary.setText(f'Reading image locations… {min(index + 1, total)} of {total}' + (': ' + Path(path).name if Path(path).is_absolute() else ''))

    def on_location_plan_ready(self):
        worker, self.worker = self.worker, None
        if self.closing: worker.deleteLater(); self.finish_close_when_idle(); return
        if self.pending or self.timer.isActive():
            worker.deleteLater(); self.timer.stop(); self.start_plan(); return
        if worker.error:
            self.summary.setText('Could not prepare image locations. No images were changed.')
            print('Image Location Tools: ' + worker.error, file=sys.stderr)
            self.show_failure_rows(worker.error)
        else:
            if self.pending_reference_choice:
                path, self.pending_reference_choice = self.pending_reference_choice, ''
                if self.apply_reference_choice(path, refresh_missing=False):
                    worker.deleteLater(); return
            if self.choose_initial_reference():
                worker.deleteLater(); return
            self.plan = worker.plan; self.render_plan()
            if self.kind == 'report': self.completed_report = True
        if self.kind == 'apply': self.refresh_candidates()
        worker.deleteLater()

    def refresh_candidates(self):
        usable = []
        for path, item in self.candidate_items.items():
            self.validate_thumbnail(path)
            data = source_info(path, self.cache)
            try: info = summarize(data['raw']) if data and not data.get('error') else None
            except ValueError: info = None
            if info and info['position'] is not None: usable.append(path)
            caption = reference_caption(path, data, self.units)
            item.setToolTip(path + '\n' + caption)
            item.setText(Path(path).name)
        self.usable_reference_paths = usable
        self.update_visual(); self.start_thumbnails()

    def show_failure_rows(self, message):
        self.display_entries = [dict(source=path, status='error', error=message) for path in self.files]
        self.render_image_list()
        self.context.setText(message); self.context.show()
        if self.apply_button: self.apply_button.setEnabled(False)



    def render_plan(self):
        entries = self.plan['entries']; config = self.plan['config']
        self.display_entries = []
        for entry in entries:
            display = dict(entry)
            if not self.selection_only and self.kind != 'report':
                display['output_description'] = output_description(entry, config)
                data = source_info(entry['source'], self.cache)
                display['gps_change_labels'] = gps_metadata_changes(entry, data['raw'] if data and not data.get('error') else None)
            self.display_entries.append(display)
        errors = sum(e['status'] == 'error' for e in entries); changes = sum(e['status'] == 'change' for e in entries)
        if self.kind == 'report':
            gps = sum(bool(e.get('location_before') and e['location_before']['position'] is not None) for e in entries)
            review = sum(bool(e.get('location_before') and e['location_before']['categories']['camera']['issues']) for e in entries)
            self.summary.setText(f'{len(entries)} selected · GPS locations: {gps} · Needs review: {review} · Unreadable: {errors}')
        self.summary.setToolTip(self.plan['privacy_summary'])
        self.render_image_list()
        if self.engine_kind() == 'gpx' and self.track_cache.get('track'):
            track = self.track_cache['track']; self.track_label.setText(f'{track["count"]:,} track points · UTC {track["start"]} to {track["end"]}')
        if self.apply_button:
            self.apply_button.setEnabled(self.selection_ready() if self.selection_only and not self.plan.get('pending_input') else not self.selection_only and not self.plan.get('pending_input') and not errors and changes > 0 and self.destination_count() > 0)
        self.update_visual()

    def show_selected_details(self, *_):
        self.refresh_inspector()
        self.update_visual()

    def show_selected_metadata(self):
        # Each opening starts with the current selection, even after inspecting the GPS source.
        self.details_subject.setCurrentIndex(self.details_subject.findData('destination'))
        self.refresh_inspector()
        self.inspector.show_metadata()

    def refresh_inspector(self, *_):
        if not hasattr(self, 'details_subject'): return
        selected = self.image_list.current_path()
        destination = next((e for e in self.display_entries if e['source'] == selected), None)
        refreshing = not self.plan and bool(self.worker or self.timer.isActive())
        inspecting = self.selection_only or bool(self.plan and self.plan.get('pending_input'))
        planned = bool(self.plan and not inspecting)
        rows = (privacy_inspector_rows(destination, self.units) if self.kind == 'report' else
                operation_inspector_rows(destination, planned=planned, inspecting=inspecting, refreshing=refreshing))
        self.inspector.set_summary(rows, destination)
        reference_details = self.uses_reference() and self.details_subject.currentData() == 'reference'
        detail_source = self.reference if reference_details else selected
        entry = next((e for e in self.display_entries if e['source'] == detail_source), None)
        if reference_details and not entry and self.reference:
            data = source_info(self.reference, self.cache) if not self.worker else None
            entry = dict(source=self.reference, location_before=self.reference_info(), error=data.get('error', '') if data else 'Inspection unavailable')
        if entry and not self.plan:
            # Old plan rows can include obsolete filenames while a source refreshes.
            # Keep inspection evidence, but do not present obsolete executable changes.
            entry = {key: entry[key] for key in ('source', 'location_before', 'error', 'warnings') if key in entry}
        if entry and reference_details:
            entry = dict(entry, output_description='GPS source, unchanged. No output created.')
        self.detail_source = detail_source
        self.details_title.set_value(('GPS source: ' if reference_details else 'Image: ') + Path(detail_source).name if detail_source else 'No image selected', detail_source)
        self.inspector.set_metadata(entry, self.units)
        info = entry.get('location_before') if entry else None
        self.details_copy.setEnabled(bool(info and info['position'] is not None))
        self.details_browser.setEnabled(self.details_copy.isEnabled())

    def copy_camera_coordinates(self, path):
        # Clipboard uses the extracted signed floats, never the rounded display.
        data = source_info(path, self.cache) if path else None
        try:
            info = summarize(data['raw']) if data and not data.get('error') else None
            if not info or info['position'] is None: raise ValueError('Camera coordinates are unavailable or have changed. Refresh and select an image with unambiguous camera coordinates.')
            QApplication.clipboard().setText(', '.join(repr(value) for value in info['position']))
        except (ValueError, OSError) as exc:
            QMessageBox.information(self, 'Copy coordinates', str(exc)); return

    def copy_selected_coordinates(self):
        if self.visual_source: self.copy_camera_coordinates(self.visual_source)

    def copy_detail_coordinates(self):
        if self.detail_source: self.copy_camera_coordinates(self.detail_source)

    def map_camera_coordinates(self, path):
        data = source_info(path, self.cache) if path else None
        try: info = summarize(data['raw']) if data and not data.get('error') else None
        except ValueError: info = None
        open_camera_map(self, info)

    def map_selected_coordinates(self):
        if self.visual_source: self.map_camera_coordinates(self.visual_source)

    def map_detail_coordinates(self):
        if self.detail_source: self.map_camera_coordinates(self.detail_source)

    def selection_ready(self):
        config = self.config()
        if self.destination_count() == 0: return False
        try:
            method = config.get('method')
            if method == 'photo':
                data = source_info(self.reference, self.cache) if self.reference else None
                if not data or data.get('error') or summarize(data['raw'])['position'] is None: return False
                for enabled, name, low, high in [(config.get('altitude'), 'GPSAltitude', -12000, 100000),
                                                (config.get('direction'), 'GPSImgDirection', 0, 359.999999)]:
                    if enabled and optional_gps(data['raw'], name, low, high) is None: return False
            elif method == 'gpx':
                return bool(config.get('gpx') and self.plan and not self.plan.get('pending_input') and self.track_cache.get('track'))
            else:
                coordinate(config.get('latitude'), None, True); coordinate(config.get('longitude'), None, False)
                if config.get('altitude', '') != '': number(config['altitude'], 'altitude', -12000, 100000)
                if config.get('direction', '') != '': number(config['direction'], 'image direction', 0, 359.999999)
        except (ValueError, OSError) as exc:
            self.context.setText('Check the selected location input: ' + str(exc)); self.context.show(); return False
        return True

    def restore_input(self, config):
        # The dispatcher reopens the final preview after the existing output-policy
        # prompt. This selection data is never itself an approved publication plan.
        if self.kind != 'apply': return
        method = config.get('method', 'photo')
        self.method.setCurrentIndex(self.method.findData(method))
        if method == 'photo':
            path = config.get('reference', '')
            if path:
                item = self.candidate_items.get(path) or self.add_candidate(path)
                self.candidates.setCurrentIndex(item.row())
            self.copy_altitude.setChecked(bool(config.get('altitude')))
            self.copy_direction.setChecked(bool(config.get('direction')))
        elif method == 'gpx':
            for key, field in self.gpx_inputs.items():
                if key in config and key not in ('altitude',): field.setText(str(config[key]))
            self.gpx_inputs['altitude'].setChecked(bool(config.get('altitude')))
            self.gpx_inputs['gap_minutes'].setText(format(Decimal(str(config.get('gap', 300))) / Decimal(60), 'f'))
            sync = config.get('sync', []); self.drift.setChecked(bool(sync))
            for i, pair in enumerate(sync, 1):
                self.gpx_inputs['camera' + str(i)].setText(pair[0]); self.gpx_inputs['gps' + str(i)].setText(pair[1])
            self.clock_advanced.setChecked(bool(sync) or config.get('seconds', '0') != '0')
        elif method == 'map':
            self.map_position = [coordinate(config.get('latitude'), None, True), coordinate(config.get('longitude'), None, False)]
            self.map_label.setText('Selected location: ' + position_text(self.map_position))
        else:
            for key in ('latitude', 'longitude', 'direction'): self.inputs[key].setText(config.get(key, ''))
            self.altitude_metres = config.get('altitude', '')
            self.inputs['altitude'].blockSignals(True)
            self.inputs['altitude'].setText(altitude_from_metres(self.altitude_metres, self.units) if self.altitude_metres else '')
            self.inputs['altitude'].blockSignals(False)

    def accept(self):
        # The report has no approval / save route, even via keyboard or code.
        if self.kind == 'report': return
        if self.worker or self.timer.isActive() or not self.plan or not self.apply_button or not self.apply_button.isEnabled(): return
        if self.selection_only:
            if not self.selection_ready(): return
            if self.thumbnail_worker or self.photo_preview.worker:
                self.accept_after_thumbnails = True
                self.thumbnail_queue.clear()
                if self.thumbnail_worker: self.thumbnail_worker.requestInterruption()
                if self.photo_preview.worker: self.photo_preview.worker.requestInterruption()
                return
            self.location_map.stop_requests(); self.photo_preview.stop(); super().accept(); return
        if self.plan['config'] != dict(self.config(), kind=self.engine_kind()): self.schedule_plan(); return
        try: verify_plan(self.plan)
        except Exception as exc:
            self.summary.setText(str(exc) + '\nRefresh and review a fresh preview.'); self.apply_button.setEnabled(False); return
        # Stop outstanding read-only thumbnails before the dialog is destroyed.
        if self.thumbnail_worker or self.photo_preview.worker:
            self.accept_after_thumbnails = True
            self.thumbnail_queue.clear()
            if self.thumbnail_worker: self.thumbnail_worker.requestInterruption()
            if self.photo_preview.worker: self.photo_preview.worker.requestInterruption()
            return
        self.location_map.stop_requests(); self.photo_preview.stop(); super().accept()

    def finish_close_when_idle(self):
        if not self.worker and not self.thumbnail_worker and not self.photo_preview.worker: super().reject()

    def reject(self):
        self.closing = True; self.accept_after_thumbnails = False; self.timer.stop(); self.thumbnail_queue.clear()
        self.location_map.stop_requests(); self.photo_preview.stop()
        if self.apply_button: self.apply_button.setEnabled(False)
        if self.worker: self.worker.requestInterruption()
        if self.thumbnail_worker: self.thumbnail_worker.requestInterruption()
        if self.worker or self.thumbnail_worker or self.photo_preview.worker: self.summary.setText('Cancelling image inspection…')
        self.finish_close_when_idle()

    def closeEvent(self, event):
        self.reject()
        if self.worker or self.thumbnail_worker or self.photo_preview.worker: event.ignore()
        else: event.accept()

    def uses_reference(self):
        return self.kind == 'apply' and self.method.currentData() == 'photo'

    def reference_info(self):
        data = source_info(self.reference, self.cache) if self.reference and not self.worker else None
        try: return summarize(data['raw']) if data and not data.get('error') else None
        except ValueError: return None

    def render_image_list(self):
        rows = []; reference_info = self.reference_info() if self.uses_reference() else None
        proposed = reference_info['position'] if reference_info else None
        inspecting = self.selection_only or bool(self.plan and self.plan.get('pending_input'))
        refreshing = not self.plan and bool(self.worker or self.timer.isActive())
        ready = matching = blocked_count = pending = 0
        for entry in self.display_entries:
            self.validate_thumbnail(entry['source'])
            # Canonical paths identify the source; similar photographs stay separate.
            # The engine additionally excludes its protected file identity at execution.
            if self.uses_reference() and entry['source'] == self.reference: continue
            info = entry.get('location_before'); blocked = False
            if self.kind == 'report':
                caption = camera_status(info)
            else:
                approved = entry.get('approved_location') if self.plan else None
                blocked = not refreshing and bool(blocked_destination(entry, inspecting))
                caption = destination_status(entry, approved['position'] if approved else proposed, inspecting) if self.plan or blocked else 'Refreshing proposal…'
                if blocked: blocked_count += 1
                elif not self.plan or inspecting: pending += 1
                elif entry['status'] == 'change': ready += 1
                elif entry['status'] == 'skip': matching += 1
                if self.plan and not inspecting and not blocked and entry['status'] == 'change' and entry.get('target'):
                    caption += '\n' + ('New: ' if self.policy == 'create' else 'Original: ') + Path(entry['target']).name
            details = [caption, camera_status(info), *gps_summary_changes(entry)]
            if entry.get('error'): details.append(entry['error'])
            rows.append(dict(source=entry['source'], caption=caption, details='\n'.join(details), blocked=blocked))
        self.image_list.set_entries(rows)
        for path, icon in self.thumbnail_icons.items(): self.image_list.set_thumbnail(path, icon)
        heading = 'Images' if self.kind == 'report' else 'Select a GPS source image' if self.uses_reference() and not self.reference else 'Images to update'
        self.images_heading.setText(heading + f' ({len(rows)})')
        if self.kind != 'report':
            def images(n): return f'{n} ' + ('image' if n == 1 else 'images')
            if inspecting or not self.plan:
                lines = ['Preview required: ' + images(pending)]
            else:
                lines = ['Ready to update: ' + images(ready), 'No changes needed: ' + images(matching)]
            lines.append('Blocked / unsupported: ' + images(blocked_count))
            if self.uses_reference() and self.reference: lines.append('GPS source unchanged')
            self.summary.setText('\n'.join(lines))
        self.start_thumbnails()

    def validate_thumbnail(self, path):
        if path not in self.thumbnail_stamps: return
        try: valid = identity(path) == self.thumbnail_stamps[path]
        except (OSError, ValueError): valid = False
        if valid: return
        self.thumbnail_stamps.pop(path, None); self.thumbnail_icons.pop(path, None)
        icon = QIcon.fromTheme('image-x-generic'); self.image_list.set_thumbnail(path, icon)
        if path in self.candidate_items: self.candidate_items[path].setIcon(icon)
        if path not in self.thumbnail_queue: self.thumbnail_queue.append(path)

    def update_visual(self, *_):
        if not hasattr(self, 'location_map'): return
        reference = self.uses_reference()
        self.remove_image.setEnabled(self.selection_only and bool(self.image_list.current_path()))
        self.details_subject.setVisible(reference)
        self.reference_options.setVisible(reference)
        self.visual_role.setText('GPS source image' if reference else 'Selected image')
        path = self.reference if reference else self.image_list.current_path()
        self.visual_source = path
        self.photo_preview.set_path(path)
        self.selected_image.setText((Path(path).name + ('\nGPS source, unchanged' if reference else '')) if path else 'Choose a GPS source image' if reference else 'Select an image')
        self.selected_image.setToolTip(path)
        entry = next((e for e in self.display_entries if e['source'] == path), None)
        data = source_info(path, self.cache) if path and not self.worker else None
        try: info = summarize(data['raw']) if data and not data.get('error') else None
        except ValueError: info = None
        approved = entry.get('approved_location') if entry and not reference and self.plan and entry['status'] == 'change' else None
        position = info['position'] if info else None
        pending = path and not data and (not entry or self.worker)
        self.selected_location.setText('Original GPS: ' + position_text(position) if position is not None else 'Reading GPS location…' if pending else camera_status(info) if path else '')
        if approved: self.selected_location.setText(self.selected_location.text() + '\nNew GPS: ' + position_text(approved['position']))
        self.report_copy.setEnabled(position is not None); self.report_map.setEnabled(position is not None)
        self.report_copy.setToolTip('Copy exact signed camera latitude and longitude' if position is not None else 'Requires valid, unambiguous camera coordinates.')
        self.report_map.setToolTip('Open the camera coordinates in your browser. This explicitly shares the position with OpenStreetMap.' if position is not None else 'Requires valid, unambiguous camera coordinates.')
        self.map_subject.setVisible(bool(approved)); self.map_subject.setEnabled(bool(approved))
        if approved and self.map_subject.currentData() == 'proposed':
            position = approved['position']; self.map_heading.setText('New GPS location')
        else: self.map_heading.setText('GPS source location' if reference else 'GPS Location')
        empty = ('Choose a GPS source image with camera GPS.' if reference else 'Select an image to see its GPS location.') if not path else camera_status(info) + '. No camera marker can be shown.'
        self.location_map.set_position(position, empty)
        if reference:
            limitations = []
            if data and data.get('error'): limitations.append(data['error'])
            for checked, name, low, high, label in [(self.copy_altitude.isChecked(), 'GPSAltitude', -12000, 100000, 'Altitude'), (self.copy_direction.isChecked(), 'GPSImgDirection', 0, 359.999999, 'Image direction')]:
                if checked and data and not data.get('error'):
                    try:
                        if optional_gps(data['raw'], name, low, high) is None: limitations.append(label + ' is not recorded in the GPS source.')
                    except ValueError as exc: limitations.append(label + ': ' + str(exc))
            self.candidate_help.setText('\n'.join(limitations) if limitations else self.reference_instruction())

    def visual_idle(self):
        if self.closing: self.finish_close_when_idle()
        elif self.accept_after_thumbnails: self.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, 'visual_tabs'): return
        # Use native size hints rather than a fixed width. A narrow window keeps
        # both views accessible in tabs instead of forcing a huge minimum size.
        required = (self.sidebar.minimumSizeHint().width() + self.photo_panel.minimumSizeHint().width() +
                    self.map_panel.minimumSizeHint().width() + self.fontMetrics().horizontalAdvance('M') * 5)
        narrow = self.width() < required
        if narrow == self.visual_tab_mode: return
        self.visual_tab_mode = narrow
        if narrow:
            self.visual_tabs.addTab(self.photo_panel, 'Image'); self.visual_tabs.addTab(self.map_panel, 'Map')
            self.visual_splitter.hide(); self.visual_tabs.show()
        else:
            while self.visual_tabs.count(): self.visual_tabs.removeTab(0)
            self.visual_splitter.addWidget(self.photo_panel); self.visual_splitter.addWidget(self.map_panel)
            self.photo_panel.show(); self.map_panel.show()
            self.visual_tabs.hide(); self.visual_splitter.show(); self.visual_splitter.setSizes([420, 420])


def show_location_result(result_path, plan_path):
    fields = Path(result_path).read_bytes().decode('utf-8').split('\0')[:-1]
    ok, failed, cancelled, skipped, interrupted, count = map(int, fields[:6])
    plan = json.loads(Path(plan_path).read_text())
    message, incomplete = location_result_message(plan, ok, failed, cancelled, skipped,
                                                 interrupted, fields[6:6 + count])
    dialog = QMessageBox()
    dialog.setWindowTitle('KIM6 - Location results'); dialog.setTextFormat(Qt.PlainText)
    dialog.setStandardButtons(QMessageBox.Close); dialog.setDefaultButton(QMessageBox.Close)
    dialog.setText(message)
    dialog.setIcon(QMessageBox.Warning if incomplete else QMessageBox.Information)
    saved = fields[6 + count:6 + count + ok]
    details = '\n'.join(fields[6 + count + ok:])
    if saved: details += '\n\nSuccessfully saved images:\n' + '\n'.join(saved)
    if details: dialog.setDetailedText(details)
    folders = {str(Path(path).parent) for path in saved}
    if plan['policy'] == 'create' and len(folders) == 1:
        folder = folders.pop()
        open_folder = dialog.addButton('Open output folder', QMessageBox.ActionRole)
        open_folder.setIcon(QIcon.fromTheme('folder-open'))
        open_folder.setToolTip(folder)
        def reveal_output():
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(folder)):
                QMessageBox.warning(None, 'Open output folder', 'The file manager could not be opened. Open this folder manually:\n' + folder)
        open_folder.clicked.connect(reveal_output)
    dialog.exec()


def main():
    check_graphical_session()
    if sys.argv[1:2] == ['--result']:
        app = QApplication(sys.argv[:1]); app.setApplicationName('KIM6')
        show_location_result(*sys.argv[2:]); return 0
    kind, result, policy, seeds_path, *files = sys.argv[1:]
    if kind not in TITLES: raise ValueError('Unknown location operation')
    seeds = Path(seeds_path).read_bytes().decode().split('\0')[:-1] if seeds_path != '-' else None
    app = QApplication(sys.argv[:1]); app.setApplicationName('KIM6')
    initial_path = os.environ.get('KIM_LOCATION_CONFIG')
    initial = json.loads(Path(initial_path).read_text()) if initial_path else None
    if kind == 'gpx' and not initial: initial = {'method': 'gpx'}
    if kind in ('copy', 'gpx'): kind = 'apply'
    dialog = LocationDialog(kind, files, policy, seeds, initial); status = dialog.exec()
    if kind == 'report': return 0 if dialog.completed_report else 130
    if status != QDialog.Accepted: return 130
    if policy == 'select': Path(result).write_text(json.dumps(dict(dialog.config(), files=dialog.files)))
    else: save_plan(result, dialog.plan)
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc: print('Image Location Tools: ' + str(exc), file=sys.stderr); raise SystemExit(1)
