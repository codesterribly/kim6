"""Image location tools over the existing approved-plan engine."""
from kim_dialog_buttons import style_button, style_button_box
from decimal import Decimal, InvalidOperation
from pathlib import Path
import sys
import json
import os

from PySide6.QtCore import QThread, Signal, QTimer, Qt, QSize, QUrl
from PySide6.QtGui import QDesktopServices, QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGridLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QComboBox,
    QDialogButtonBox, QStyle, QFileDialog, QWidget, QScrollArea,
    QButtonGroup, QRadioButton,
    QSplitter,
    QStackedWidget, QGroupBox, QMessageBox, QSizePolicy, QToolButton, QTabWidget)

from kim_location import (build_manual_proposal, proposal_problem, inspect_editor_gps, editor_gps_description,
    TITLES, build_plan, coordinate, number, source_info, summarize, optional_gps, optional_gps_record, MAX_FILES)
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


class ProposalWorker(QThread):
    """Cancellable protected inspection, with no publication planner."""
    def __init__(self, path, config, parent):
        super().__init__(parent)
        self.path = path; self.config = config; self.proposal = None; self.error = ''

    def run(self):
        try:
            self.proposal = build_manual_proposal(self.path, self.config, cancelled=self.isInterruptionRequested)
        except Exception as exc:
            self.error = str(exc)


class GPSInspectionWorker(QThread):
    """Share protected asynchronous GPS inspection between Editor and dialog."""
    def __init__(self, path, parent):
        super().__init__(parent)
        self.path = path; self.snapshot = None

    def run(self):
        try:
            self.snapshot = inspect_editor_gps(self.path, cancelled=self.isInterruptionRequested)
        except Exception as exc:
            self.snapshot = dict(source=self.path, existing=None, sidecars=[], blocked=[str(exc)])


class LocationDialog(QDialog):
    def __init__(self, kind, files, policy, seeds, initial=None):
        super().__init__()
        self.proposal_only = policy == 'proposal'
        if self.proposal_only and len(files) != 1:
            raise ValueError('Select exactly one image for a GPS proposal')
        self.kind, self.files, self.policy, self.seeds = kind, [absolute(p) for p in files], policy, seeds
        self.selection_only = policy == 'select'
        self.launched_from_report = bool(
            initial and initial.get('launched_from_report')
        )
        if self.selection_only: self.policy = 'create'
        self.worker = None; self.thumbnail_worker = None; self.thumbnail_queue = []
        self.pending = False; self.closing = False; self.accept_after_thumbnails = False; self.completed_report = False
        self.plan = None; self.cache = {}; self.track_cache = {}; self.inputs = {}; self.display_entries = []
        self.initial_reference_checked = bool(initial); self.reference = ''; self.map_position = None; self.altitude_metres = ''
        self.image_drafts = {}
        self.draft_selection_path = ''
        self.unit_preference = unit_preference(); self.units = preferred_units(self.unit_preference)
        self.apply_button = None; self.candidate_items = {}; self.thumbnail_stamps = {}; self.thumbnail_icons = {}
        self.visual_source = ''; self.usable_reference_paths = []
        self.pending_reference_choice = ''
        self.setWindowTitle('KIMng - ' + TITLES[kind].rstrip('…'))
        available = self.screen().availableGeometry()
        self.resize(min(1120, available.width()*9//10), min(760, available.height()*9//10))
        layout = QVBoxLayout(self)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(350)
        self.timer.timeout.connect(self.start_plan)
        top = QHBoxLayout()
        title = QLabel(('Edit GPS location' if initial else 'Add GPS location') if self.proposal_only else 'View GPS metadata' if kind == 'report' else TITLES[kind].rstrip('…'))
        self.title_label = title
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
        for form in self.controls.findChildren(QFormLayout):
            form.setRowWrapPolicy(QFormLayout.WrapLongRows if self.proposal_only else QFormLayout.WrapAllRows)
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
            if kind == 'apply' and self.selection_only:
                self.destination_splitter.setSizes([480, 120])
                self.destination_splitter.setStretchFactor(0, 4)
                self.destination_splitter.setStretchFactor(1, 0)
            else:
                self.destination_splitter.setSizes([300, 220])
                self.destination_splitter.setStretchFactor(0, 1)
                self.destination_splitter.setStretchFactor(1, 1)
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

        self.report_edit_handler = None
        self.report_edit_process = None
        self.report_edit_busy = False
        self.report_edit = None

        if kind == 'report':
            from kim_metadata_gps_actions import configure_gps_location_button
            self.report_edit = QPushButton()
            self.report_edit.setObjectName('reportEditGpsLocation')
            configure_gps_location_button(self.report_edit, False)
            self.report_edit.setEnabled(False)
            self.report_edit.clicked.connect(self.edit_report_location)
            action_row.addWidget(self.report_edit)

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
        self.location_map = LocationMap(self, units=self.units, interactive=True, persistent=False) if self.proposal_only else LocationMap(self, units=self.units)
        map_layout.addWidget(self.location_map, 1)
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
        if self.selection_only:
            self.output_policy_group = QButtonGroup(self)
            self.output_create = QRadioButton(
                'Create new files (originals untouched)'
            )
            self.output_overwrite = QRadioButton(
                'Overwrite originals (confirmation required)'
            )

            self.output_policy_group.addButton(
                self.output_create
            )
            self.output_policy_group.addButton(
                self.output_overwrite
            )
            self.output_create.setChecked(True)

            output_row = QHBoxLayout()
            output_row.addWidget(QLabel('Save images:'))
            output_row.addWidget(self.output_create)
            output_row.addWidget(self.output_overwrite)
            output_row.addStretch(1)
            layout.addLayout(output_row)

        buttons_row = QHBoxLayout()
        self.refresh_button = QPushButton(QIcon.fromTheme('view-refresh'), '&Refresh'); self.refresh_button.clicked.connect(self.schedule_plan)
        buttons_row.addWidget(self.refresh_button)

        if self.selection_only and self.launched_from_report:
            self.settings_back = QPushButton('Back')
            style_button(self.settings_back, 'back')
            self.settings_back.setAutoDefault(False)
            self.settings_back.clicked.connect(self.reject)
            buttons_row.insertWidget(0, self.settings_back)

        buttons_row.addStretch()
        if kind == 'report':
            self.buttons = QDialogButtonBox(QDialogButtonBox.Close)
            style_button_box(self.buttons)
            self.buttons.rejected.connect(self.reject)
            buttons_row.addWidget(self.buttons)
        else:

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
        if self.report_edit is not None:
            self.setTabOrder(self.report_map, self.report_edit)
            self.setTabOrder(self.report_edit, self.location_map.online)
        else:
            self.setTabOrder(self.report_map, self.location_map.online)
        self.setTabOrder(self.location_map.online, self.location_map.canvas)
        self.unit_choice.currentIndexChanged.connect(self.change_units)
        # PNG cannot scale during Qt decoding. Allow ordinary camera-sized
        # images (e.g. 3840 × 2560 RGB32 needs 37.5 MiB), retaining a finite cap.
        QImageReader.setAllocationLimit(64)
        if self.proposal_only:
            self._init_proposal(files, initial)
            return
        if not initial and self.kind == 'apply' and self.selection_only:
            initial = dict(
                method='map',
                latitude='',
                longitude='',
                open_map_on_start=False,
            )
            self.initial_reference_checked = True

        if initial:
            self.restore_input(initial)
            if self.selection_only:
                self.output_overwrite.setChecked(
                    initial.get('output_policy') == 'overwrite'
                )
                self.output_create.setChecked(
                    initial.get('output_policy') != 'overwrite'
                )
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
        if self.proposal_only:
            self.source_form = QFormLayout()
            layout.addLayout(self.source_form)
            page = self.build_manual_page()
            layout.addWidget(page)
            return
        form = QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.FieldsStayAtSizeHint)
        self.source_form = form
        self.method = QComboBox()
        for title, key in [('Another Image', 'photo'), ('Point on Map', 'map'), ('Manual Coordinates', 'manual'), ('GPX Track', 'gpx')]: self.method.addItem(title, key)
        source_row = QWidget()
        source_actions = QHBoxLayout(source_row)
        source_actions.setContentsMargins(0, 0, 0, 0)
        source_actions.setSpacing(8)

        source_actions.addWidget(self.method)

        self.map_button = QPushButton('Choose on Map…')
        self.map_button.setAutoDefault(False)
        self.map_button.setToolTip(
            'Choose a new location for the selected image.'
        )
        self.map_button.clicked.connect(self.open_map)
        source_actions.addWidget(self.map_button)

        self.map_source_actions = source_actions
        self.map_button.hide()

        form.addRow('&Location source', source_row)
        layout.addLayout(form)
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
        map_page = QWidget()
        map_page.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Maximum
        )
        map_layout = QVBoxLayout(map_page)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(4)
        map_layout.setAlignment(Qt.AlignTop)

        self.map_label = self.label('No location change selected.')
        self.map_label.setWordWrap(False)
        self.map_label.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Fixed
        )
        map_layout.addWidget(self.map_label)

        self.build_advanced_gps_controls(map_layout)


        self.method_pages.addWidget(map_page)
        self.add_source_page(self.build_manual_page())
        gpx_page = QWidget(); gpx_layout = QVBoxLayout(gpx_page)
        manual_inputs, self.inputs = self.inputs, {}
        self.build_gpx_controls(gpx_layout)
        self.gpx_inputs, self.inputs = self.inputs, manual_inputs
        self.add_source_page(gpx_page)
        self.method.currentIndexChanged.connect(self.change_method)
        self.method.activated.connect(self.open_selected_map)
        for i in range(self.method_pages.count()):
            self.method_pages.widget(i).setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred if i == 0 else QSizePolicy.Ignored)
        self.fit_method_page()

    def build_manual_page(self):
        if self.proposal_only:
            page = QWidget()
            page.setMaximumWidth(600)
            grid = QGridLayout(page)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(12)
            self.altitude_label = QLabel('Altitude (optional, ft)' if self.units == 'imperial' else 'Altitude (optional, m)')
            fields = (
                ('latitude', QLabel('Latitude'), '−90 to +90; north is positive'),
                ('longitude', QLabel('Longitude'), '−180 to +180; east is positive'),
                ('altitude', self.altitude_label, 'Optional; blank removes old altitude'),
                ('direction', QLabel('Image direction (optional, degrees)'), '0 to less than 360; true north'),
            )
            for index, (key, label, hint) in enumerate(fields):
                field = self.add_text(key, hint)
                field.setMinimumWidth(130)
                field.setMaximumWidth(230)
                label.setBuddy(field)
                grid.addWidget(label, (index // 2) * 2, index % 2)
                grid.addWidget(field, (index // 2) * 2 + 1, index % 2)
                if key in ('latitude', 'longitude'):
                    field.textChanged.connect(self.update_coordinate_readout)
                elif key == 'altitude':
                    field.textChanged.connect(self.capture_altitude)
            self.coordinate_readout = self.label('Enter decimal coordinates.')
            grid.addWidget(self.coordinate_readout, 4, 0, 1, 2)
            return page
        manual_page = QWidget(); manual_form = QFormLayout(manual_page); manual_form.setRowWrapPolicy(QFormLayout.WrapAllRows)
        for key, label, hint in [('latitude', 'Latitude (−90 to +90)', 'Signed decimal degrees; north is positive'), ('longitude', 'Longitude (−180 to +180)', 'Signed decimal degrees; east is positive')]:
            field = self.add_text(key, hint); field.textChanged.connect(self.update_coordinate_readout); manual_form.addRow(label, field)
        self.coordinate_readout = self.label('Enter decimal coordinates.'); manual_form.addRow(self.coordinate_readout)
        self.altitude_label = QLabel('Altitude (optional, ft)' if self.units == 'imperial' else 'Altitude (optional, m)')
        altitude = self.add_text('altitude', 'Blank removes old altitude'); altitude.textChanged.connect(self.capture_altitude); manual_form.addRow(self.altitude_label, altitude)
        manual_form.addRow('Image direction (optional, degrees)', self.add_text('direction', '0 to less than 360; from true north'))
        if not self.proposal_only:
            map_here = QPushButton('Choose on Map at These Coordinates…'); map_here.clicked.connect(self.open_manual_map); manual_form.addRow(map_here)
        return manual_page

    def _init_proposal(self, files, initial):
        self.proposal = None; self.gps_snapshot = None; self._proposal_touched = False
        self._proposal_initial = initial
        self.setWindowTitle('Edit GPS location' if initial else 'Add GPS location')
        self.sidebar.hide(); self.refresh_button.hide()
        self.report_copy.hide(); self.report_map.hide()
        self.selected_image.setText(Path(self.files[0]).name)
        self.selected_image.setToolTip(self.files[0])
        self.selected_location.setText('Checking GPS location…')
        self.summary.setParent(self.controls)
        self.controls.layout().addWidget(self.summary)
        self.controls.layout().insertWidget(0, self.label('Choose a point on the map or enter coordinates.'))
        self.layout().insertWidget(self.layout().count() - 1, self.label(
            'This location will be included in Review changes.\nYour image will not be modified.'))
        self.summary.setText('Choose a point on the map or enter coordinates.')
        self.summary.show()
        self.apply_button.setText('Use this location')
        self.timer.timeout.disconnect(self.start_plan)
        self.timer.timeout.connect(self._start_proposal)
        self.location_map.position_changed.connect(self._proposal_map_selected)
        for field in self.inputs.values(): field.textEdited.connect(self._proposal_edited)
        if initial and initial.get('latitude') and initial.get('longitude'):
            self.location_map.canvas.zoom = 13
        for key in ('latitude', 'longitude', 'direction'):
            self.inputs[key].setText(str((initial or {}).get(key, '')))
        self.altitude_metres = (initial or {}).get('altitude', '')
        self.inputs['altitude'].blockSignals(True)
        self.inputs['altitude'].setText(altitude_from_metres(self.altitude_metres, self.units) if self.altitude_metres != '' else '')
        self.inputs['altitude'].blockSignals(False)
        self.photo_preview.set_path(self.files[0])
        self.inspection_worker = None
        QTimer.singleShot(0, self._inspect_proposal_source)

    def _inspect_proposal_source(self):
        if self.closing: return
        self.inspection_worker = GPSInspectionWorker(self.files[0], self)
        self.inspection_worker.finished.connect(self._proposal_inspected)
        self.inspection_worker.start()

    def _proposal_edited(self, *_):
        self._proposal_touched = True

    def _proposal_map_selected(self, point):
        if point is None: return
        self._proposal_touched = True
        self.inputs['latitude'].setText(f'{point[0]:.12f}')
        self.inputs['longitude'].setText(f'{point[1]:.12f}')
        self.schedule_plan()

    def _proposal_inspected(self):
        worker, self.inspection_worker = self.inspection_worker, None
        worker.wait()
        self.gps_snapshot = worker.snapshot
        worker.deleteLater()
        if self.closing: self.finish_close_when_idle(); return
        self.selected_location.setText(editor_gps_description(self.gps_snapshot))
        existing = self.gps_snapshot.get('existing')
        title = 'Edit GPS location' if self._proposal_initial or (existing and existing['position'] is not None) else 'Add GPS location'
        self.setWindowTitle(title)
        self.title_label.setText(title)
        if not self._proposal_initial and not self._proposal_touched and not any(f.text() for f in self.inputs.values()):
            initial = self.gps_snapshot.get('initial', {})
            if initial: self.location_map.canvas.zoom = 13
            for key in ('latitude', 'longitude', 'direction'):
                self.inputs[key].setText(initial.get(key, ''))
            self.altitude_metres = initial.get('altitude', '')
            field = self.inputs['altitude']; field.blockSignals(True)
            field.setText(altitude_from_metres(self.altitude_metres, self.units) if self.altitude_metres != '' else '')
            field.blockSignals(False)
        self.schedule_plan()

    def _proposal_config(self):
        return dict(method='manual', latitude=self.inputs['latitude'].text().strip(),
                    longitude=self.inputs['longitude'].text().strip(),
                    altitude=self.altitude_metres if self.altitude_metres is not None else 'invalid altitude',
                    direction=self.inputs['direction'].text().strip())

    def _start_proposal(self):
        if self.closing: return
        if self.worker:
            self.pending = True; self.worker.requestInterruption(); return
        self.pending = False
        if getattr(self, 'inspection_worker', None): return
        if self.gps_snapshot and self.gps_snapshot['blocked']:
            self.summary.setText('; '.join(self.gps_snapshot['blocked'])); return
        if not self.inputs['latitude'].text().strip() or not self.inputs['longitude'].text().strip():
            self.summary.setText('Enter latitude and longitude or click the map to choose a location.')
            return
        self.worker = ProposalWorker(self.files[0], self._proposal_config(), self)
        self.worker.finished.connect(self._proposal_ready); self.worker.start()

    def _proposal_ready(self):
        worker, self.worker = self.worker, None
        worker.wait()
        if self.closing:
            worker.deleteLater(); self.finish_close_when_idle(); return
        if self.pending or self.timer.isActive() or worker.config != self._proposal_config():
            worker.deleteLater(); self.timer.stop(); self._start_proposal(); return
        self.proposal = worker.proposal
        blocked = self.proposal.get('blocked', []) if self.proposal else [worker.error]
        self.summary.setText('; '.join(blocked) if blocked else
                             'No GPS changes required.' if self.proposal['noop'] else
                             'Location is ready for Review changes.')
        self.apply_button.setEnabled(bool(self.proposal) and not blocked)
        worker.deleteLater()

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
        if (
            self.selection_only
            and self.image_drafts
            and self.method.currentData() != 'map'
        ):
            answer = QMessageBox.question(
                self,
                'Change location source',
                'Discard all pending individual GPS changes '
                'and switch location source?',
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )

            if answer != QMessageBox.Yes:
                self.method.blockSignals(True)
                self.method.setCurrentIndex(
                    self.method.findData('map')
                )
                self.method.blockSignals(False)
                return

            self.image_drafts.clear()

        self.method_pages.setCurrentIndex(index)

        map_mode = self.method.currentData() == 'map'
        self.map_button.setVisible(map_mode)
        self.advanced_toggle.setVisible(map_mode)

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

        if hasattr(self, 'advanced_panel'):
            self.refresh_advanced_gps_controls()

        try:
            if not self.proposal_only: persist_units(preference)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, 'Measurement preference was not saved', 'The units changed for this session, but could not be saved:\n' + str(exc))
        self.schedule_plan()

    def manual_position(self):
        return [coordinate(self.inputs['latitude'].text().strip(), None, True), coordinate(self.inputs['longitude'].text().strip(), None, False)]

    def update_coordinate_readout(self):
        if self.proposal_only and (not self.inputs['latitude'].text().strip() or not self.inputs['longitude'].text().strip()):
            self.coordinate_readout.setText('Enter signed decimal coordinates or click the map.')
            return
        try: text = position_text(self.manual_position())
        except ValueError as exc: text = str(exc)
        self.coordinate_readout.setText(text)

    def open_manual_map(self):
        try: initial = self.manual_position()
        except ValueError as exc: QMessageBox.information(self, 'Check coordinates', str(exc)); return
        self.open_map(initial=initial, into_manual=True)

    def open_selected_map(self, *_):
        if self.closing or self.proposal_only:
            return

        if self.kind != 'apply' or not self.selection_only:
            return

        if self.method.currentData() != 'map':
            return

        self.open_map()

    def open_map(self, checked=False, initial=None, into_manual=False):
        from kim_location_map import choose_location
        from kim_location import same_position

        individual = (
            self.selection_only
            and self.individual_map_mode()
            and not into_manual
        )

        path = self.image_list.current_path()
        entry = next(
            (
                item for item in self.display_entries
                if item['source'] == path
            ),
            None,
        )

        if individual:
            if not path or not entry or not self.plan:
                QMessageBox.information(
                    self, 'Choose an image',
                    'Select an inspected image first.'
                )
                return

            blocked = blocked_destination(entry, True)

            if blocked:
                QMessageBox.information(
                    self, 'GPS editing unavailable', blocked
                )
                return

            info = entry.get('location_before') or {}
            recorded = info.get('position')

            if initial is None:
                initial = self.draft_position(path)

            if initial is None:
                initial = recorded

            point = choose_location(self, initial, self.units)

            if point is None:
                return

            # The picker may return its initial coordinates.
            # An unchanged location is not a new GPS edit.
            previous = self.draft_position(path)

            if previous is not None and same_position(previous, point):
                pass
            elif recorded is not None and same_position(recorded, point):
                self.image_drafts.pop(path, None)
            else:
                self.image_drafts[path] = dict(
                    latitude=f'{point[0]:.12f}',
                    longitude=f'{point[1]:.12f}',
                    altitude='',
                    direction='',
                    direction_ref='T',
                )

            self.refresh_draft_controls()
            self.schedule_plan()
            self.update_visual()
            return

        if initial is None:
            try:
                initial = self.manual_position()
            except ValueError:
                pass

        if initial is None and entry:
            initial = (
                entry.get('location_before') or {}
            ).get('position')

        point = choose_location(self, initial, self.units)

        if point is None:
            return

        if into_manual:
            self.inputs['latitude'].setText(f'{point[0]:.12f}')
            self.inputs['longitude'].setText(f'{point[1]:.12f}')

        self.schedule_plan()
        self.update_visual()

    def config(self):
        result = {'units': self.units}
        if self.kind == 'apply':
            method = self.method.currentData(); result['method'] = method
            if method == 'photo':
                result.update(reference=self.reference, altitude=self.copy_altitude.isChecked(), direction=self.copy_direction.isChecked())
            elif method == 'map':
                result.update(
                    image_drafts={
                        path: dict(draft)
                        for path, draft in self.image_drafts.items()
                        if path in self.files
                    }
                )
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
        # A selected image containing GPS is not implicitly
        # a reference. Only explicit user selection assigns
        # this role and excludes it from the destinations.
        return False

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
        self.image_drafts.pop(path, None)
        if path in self.candidate_items:
            item = self.candidate_items.pop(path); self.candidates.removeItem(item.row())
        self.schedule_plan()

    def schedule_plan(self, *_):
        if self.proposal_only:
            if self.closing or not hasattr(self, 'timer'): return
            self.proposal = None; self.apply_button.setEnabled(False)
            try: position = self.manual_position()
            except ValueError: position = None
            self.location_map.set_position(position)
            if self.worker: self.pending = True; self.worker.requestInterruption()
            self.timer.start(); return
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

            if getattr(self, 'dedicated_review', False):
                preparing = getattr(self, 'review_preparing', None)

                if preparing is not None:
                    preparing.hide()

                QMessageBox.warning(
                    None,
                    'GPS Review Changes',
                    worker.error,
                )

                worker.deleteLater()
                self.reject()
                return
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

        if getattr(self, 'dedicated_review', False):
            QTimer.singleShot(0, self.open_dedicated_review)

    def open_dedicated_review(self):
        if self.closing or self.worker or not self.plan:
            return

        if getattr(self, '_dedicated_review_open', False):
            return

        self._dedicated_review_open = True

        preparing = getattr(self, 'review_preparing', None)

        if preparing is not None:
            preparing.hide()

        review = GPSReviewDialog(self)
        result = review.exec()
        review.deleteLater()

        self._dedicated_review_open = False

        if result == GPSReviewDialog.BACK:
            self.review_back = True
            self.reject()
            return

        if result != QDialog.Accepted:
            self.reject()
            return

        self.accept()

    def show_selected_details(self, *_):
        self.refresh_draft_controls()
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
        if self.kind == 'report':
            self.refresh_report_edit_action()
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

    def set_report_edit_handler(self, handler):
        """Route report editing through the originating application."""
        if self.kind != 'report':
            raise ValueError('Editing callbacks belong to GPS reports.')
        if not callable(handler):
            raise TypeError('A GPS editing callback is required.')
        self.report_edit_handler = handler
        self.refresh_report_edit_action()

    def report_edit_target(self):
        """Resolve the active image without reading or modifying its bytes."""
        if self.kind != 'report' or self.closing:
            return None, None, 'The GPS report is unavailable.'

        path = self.image_list.current_path()
        if not path or path not in self.files:
            return None, None, 'Select an image first.'

        entry = next(
            (item for item in self.display_entries
             if item['source'] == path),
            None
        )

        if entry is None:
            return path, None, 'Waiting for GPS inspection.'

        if not self.plan:
            return path, None, 'Waiting for GPS inspection.'

        if entry.get('error'):
            return path, None, str(entry['error'])

        info = entry.get('location_before')
        if not info:
            return path, None, 'GPS inspection is unavailable.'

        position = info.get('position')

        camera = info.get('categories', {}).get('camera', {})
        if camera.get('issues'):
            return (
                path, position,
                'Camera GPS is incomplete or ambiguous. '
                'Inspect its metadata before editing.'
            )

        from kim_location import FORMATS

        supported = {
            suffix
            for extensions in FORMATS.values()
            for suffix in extensions
        }

        if Path(path).suffix.lower() not in supported:
            return (
                path, position,
                'GPS editing is unavailable for this image format.'
            )

        return path, position, ''

    def refresh_report_edit_action(self):
        if self.report_edit is None:
            return

        from kim_metadata_gps_actions import configure_gps_location_button

        path, position, reason = self.report_edit_target()
        editing = position is not None

        label = (
            'Edit GPS location…' if editing
            else 'Add GPS location…'
        )

        if self.report_edit.text() != label:
            configure_gps_location_button(
                self.report_edit, editing
            )

        self.report_edit.setEnabled(
            bool(path) and not reason and not self.report_edit_busy
        )

        self.report_edit.setToolTip(
            reason or (
                'Edit the GPS location of the selected image.'
                if editing else
                'Add a GPS location to the selected image.'
            )
        )

    def edit_report_location(self):
        if self.kind != 'report' or self.report_edit_busy:
            return

        path, position, reason = self.report_edit_target()

        if not path or reason:
            self.refresh_report_edit_action()
            return

        self.report_edit_busy = True
        self.refresh_report_edit_action()

        if self.report_edit_handler is not None:
            try:
                self.report_edit_handler(path, position)
            finally:
                self.report_edit_busy = False
                self.refresh_report_edit_action()
            return

        # Standalone GPS reports use the normal KIMng
        # GPS editing entry point, including its existing
        # review and publication protections.
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QApplication

        dispatcher = Path(__file__).resolve().with_name('kim_all')

        if not dispatcher.is_file():
            self.report_edit_busy = False
            self.refresh_report_edit_action()
            QMessageBox.warning(
                self, 'Edit GPS location',
                'The KIMng GPS editing dispatcher is unavailable.'
            )
            return

        # Keep the process independent of the report's
        # window lifetime. Closing a report must not kill
        # an active GPS review or publication operation.
        process = None
        config_directory = None
        try:
            process = QProcess(QApplication.instance())
            self.report_edit_process = process
            process.setProgram(str(dispatcher))
            process.setArguments([
                'location-apply', '--', *self.files
            ])

            # Editing the report's selected image must not treat
            # that image as an unchanged GPS reference.
            import tempfile
            from PySide6.QtCore import QProcessEnvironment

            initial = dict(
                method='map',
                image_drafts={},
                launched_from_report=True,
                open_map_on_start=False,
            )

            config_directory = tempfile.TemporaryDirectory(
                prefix='kimng-gps-edit-'
            )
            config_path = Path(config_directory.name) / 'initial.json'
            config_path.write_text(json.dumps(initial), encoding='utf-8')

            environment = QProcessEnvironment.systemEnvironment()
            environment.insert('KIM_LOCATION_CONFIG', str(config_path))
            process.setProcessEnvironment(environment)

            # The configuration belongs to the launched process,
            # including when the original report closes first.
            process._kimng_config_directory = config_directory
            process.finished.connect(
                lambda *_: config_directory.cleanup()
            )
            process.destroyed.connect(
                lambda *_: config_directory.cleanup()
            )

            process.finished.connect(self.report_edit_finished)
            process.finished.connect(process.deleteLater)
            process.errorOccurred.connect(self.report_edit_error)

            process.start()
        except Exception as exc:
            self.report_edit_process = None
            self.report_edit_busy = False

            if process is not None:
                process.deleteLater()

            if config_directory is not None:
                config_directory.cleanup()

            self.refresh_report_edit_action()
            QMessageBox.warning(
                self,
                'Edit GPS location',
                'Could not open the GPS editing workflow:\n'
                + str(exc)
            )

    def report_edit_finished(self, *_):
        self.report_edit_process = None
        self.report_edit_busy = False

        if self.closing:
            return

        # The standalone editor may have replaced an original
        # or published a separate derivative. Reinspect only
        # the existing report selection; never silently switch
        # the report to a newly created output.
        #
        # Refresh even after a nonzero exit because a partially
        # completed operation may have changed an original.
        self.refresh_report_sources()

    def refresh_report_sources(self):
        if self.kind != 'report' or self.closing:
            return

        self.completed_report = False

        # Do not mutate a cache while an inspection worker
        # may still be using it. Replace the cache object
        # and let the existing cancellation lifecycle retire
        # any previous inspection.
        self.cache = {}

        self.display_entries = [
            dict(source=path, status='pending')
            for path in self.files
        ]

        self.schedule_plan()
        self.summary.setText('Refreshing GPS locations…')
        self.selected_location.setText('Refreshing GPS location…')
        self.report_copy.setEnabled(False)
        self.report_map.setEnabled(False)
        self.details_copy.setEnabled(False)
        self.details_browser.setEnabled(False)
        self.refresh_report_edit_action()

    def report_edit_error(self, error):
        from PySide6.QtCore import QProcess

        if error != QProcess.FailedToStart:
            return

        process = self.report_edit_process
        self.report_edit_process = None
        self.report_edit_busy = False

        if process is not None:
            process.deleteLater()

        if not self.closing:
            self.refresh_report_edit_action()
            QMessageBox.warning(
                self, 'Edit GPS location',
                'Could not open the KIMng GPS editing workflow.'
            )

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

        if self.individual_map_mode():
            return bool(self.image_drafts)

        try:
            method = config.get('method')

            if method == 'manual' and len(self.files) != 1:
                self.context.setText(
                    'Manual coordinates require a single image. '
                    'Use Point on Map to edit images individually.'
                )
                self.context.show()
                return False

            if method == 'photo':
                data = source_info(self.reference, self.cache) if self.reference else None
                if not data or data.get('error') or summarize(data['raw'])['position'] is None: return False
                for enabled, name, low, high in [(config.get('altitude'), 'GPSAltitude', -12000, 100000),
                                                (config.get('direction'), 'GPSImgDirection', 0, 359.999999)]:
                    if enabled and optional_gps(data['raw'], name, low, high) is None: return False
            elif method == 'gpx':
                return bool(config.get('gpx') and self.plan and not self.plan.get('pending_input') and self.track_cache.get('track'))
            else:
                if (
                    not config.get('latitude')
                    or not config.get('longitude')
                ):
                    return False

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
            self.map_position = None
            self.image_drafts = {
                path: dict(draft)
                for path, draft in config.get('image_drafts', {}).items()
                if path in self.files
            }
            self.refresh_draft_controls()

        else:
            for key in ('latitude', 'longitude', 'direction'): self.inputs[key].setText(config.get(key, ''))
            self.altitude_metres = config.get('altitude', '')
            self.inputs['altitude'].blockSignals(True)
            self.inputs['altitude'].setText(altitude_from_metres(self.altitude_metres, self.units) if self.altitude_metres else '')
            self.inputs['altitude'].blockSignals(False)

    def accept(self):
        if self.proposal_only:
            if self.closing or self.worker or self.inspection_worker or self.timer.isActive() or not self.proposal: return
            if self.proposal['input'] != self._proposal_config(): self.schedule_plan(); return
            problem = proposal_problem(self.proposal)
            if problem:
                self.summary.setText(problem); self.apply_button.setEnabled(False); return
            if self.proposal['status'] in ('valid', 'noop'):
                if self.photo_preview.worker or self.inspection_worker:
                    self.accept_after_thumbnails = True
                    return
                self.location_map.stop_requests(); self.photo_preview.stop(); super().accept()
            return
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

        if self.policy == 'overwrite':
            confirmation = QMessageBox.warning(
                self,
                'Confirm overwriting originals',
                'Replace the selected original images with '
                'the reviewed GPS changes?',
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if confirmation != QMessageBox.Yes:
                return

        # Stop outstanding read-only thumbnails before the dialog is destroyed.
        if self.thumbnail_worker or self.photo_preview.worker:
            self.accept_after_thumbnails = True
            self.thumbnail_queue.clear()
            if self.thumbnail_worker: self.thumbnail_worker.requestInterruption()
            if self.photo_preview.worker: self.photo_preview.worker.requestInterruption()
            return
        self.location_map.stop_requests(); self.photo_preview.stop(); super().accept()

    def finish_close_when_idle(self):
        if not self.worker and not getattr(self, 'inspection_worker', None) and not self.thumbnail_worker and not self.photo_preview.worker: super().reject()

    def reject(self):
        if self.proposal_only:
            self.closing = True; self.proposal = None; self.timer.stop()
            self.location_map.stop_requests(); self.photo_preview.stop()
            self.apply_button.setEnabled(False)
            if self.worker: self.worker.requestInterruption()
            if self.inspection_worker: self.inspection_worker.requestInterruption()
            self.finish_close_when_idle()
            return
        self.closing = True; self.accept_after_thumbnails = False; self.timer.stop(); self.thumbnail_queue.clear()
        self.location_map.stop_requests(); self.photo_preview.stop()
        if self.apply_button: self.apply_button.setEnabled(False)
        if self.worker: self.worker.requestInterruption()
        if self.thumbnail_worker: self.thumbnail_worker.requestInterruption()
        if self.worker or self.thumbnail_worker or self.photo_preview.worker: self.summary.setText('Cancelling image inspection…')
        self.finish_close_when_idle()

    def closeEvent(self, event):
        if self.proposal_only:
            self.reject()
            if self.worker or self.inspection_worker or self.photo_preview.worker: event.ignore()
            else: event.accept()
            return
        self.reject()
        if self.worker or self.thumbnail_worker or self.photo_preview.worker: event.ignore()
        else: event.accept()

    def uses_reference(self):
        return not self.proposal_only and self.kind == 'apply' and self.method.currentData() == 'photo'

    def reference_info(self):
        data = source_info(self.reference, self.cache) if self.reference and not self.worker else None
        try: return summarize(data['raw']) if data and not data.get('error') else None
        except ValueError: return None

    def render_image_list(self):
        rows = []; reference_info = self.reference_info() if self.uses_reference() else None
        proposed = reference_info['position'] if reference_info else None

        if proposed is None:
            proposed = self.selected_input_position()

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
                row_proposed = (
                    self.draft_position(entry['source'])
                    if self.individual_map_mode()
                    else proposed
                )

                caption = destination_status(
                    entry,
                    approved['position'] if approved else row_proposed,
                    inspecting,
                ) if self.plan or blocked else 'Reading GPS location…'

                if (
                    self.selection_only
                    and self.individual_map_mode()
                    and not blocked
                    and row_proposed is not None
                ):
                    caption = 'GPS change pending'
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
            if (
                self.selection_only
                and self.kind == 'apply'
                and self.method.currentData() == 'map'
            ):
                count = len(self.image_drafts)

                lines = [
                    f'{count} pending GPS changes'
                    if count
                    else 'No changes selected',
                    f'{max(0, len(rows) - count - blocked_count)} unchanged',
                ]
            elif inspecting or not self.plan:
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


    def build_advanced_gps_controls(self, layout):
        from PySide6.QtWidgets import QDoubleSpinBox

        self.advanced_refreshing = False

        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setText('Advanced GPS settings')
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setChecked(False)
        self.advanced_toggle.setArrowType(Qt.RightArrow)
        self.advanced_toggle.setToolButtonStyle(
            Qt.ToolButtonTextBesideIcon
        )
        self.advanced_toggle.setSizePolicy(
            QSizePolicy.Fixed, QSizePolicy.Fixed
        )

        self.map_source_actions.addWidget(
            self.advanced_toggle
        )
        self.map_source_actions.addStretch(1)
        self.advanced_toggle.hide()

        self.advanced_panel = QWidget()
        self.advanced_panel.setSizePolicy(
            QSizePolicy.Preferred, QSizePolicy.Fixed
        )
        form = QGridLayout(self.advanced_panel)
        form.setContentsMargins(18, 0, 0, 0)
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(4)

        self.advanced_altitude_enabled = QCheckBox(
            'Specify altitude'
        )

        self.advanced_altitude = QDoubleSpinBox()
        self.advanced_altitude.setDecimals(3)
        self.advanced_altitude.setKeyboardTracking(False)
        self.advanced_altitude.setToolTip(
            'Signed altitude relative to the WGS84 ellipsoid. '
            'Negative values are below the reference surface.'
        )

        self.advanced_direction_enabled = QCheckBox(
            'Specify image direction'
        )

        self.advanced_direction = QDoubleSpinBox()
        self.advanced_direction.setDecimals(6)
        self.advanced_direction.setRange(0, 359.999999)
        self.advanced_direction.setSuffix('°')
        self.advanced_direction.setKeyboardTracking(False)

        self.advanced_direction_ref = QComboBox()
        self.advanced_direction_ref.addItem(
            'True north', 'T'
        )
        self.advanced_direction_ref.addItem(
            'Magnetic north', 'M'
        )

        form.addWidget(
            self.advanced_altitude_enabled, 0, 0
        )
        form.addWidget(
            self.advanced_altitude, 0, 1
        )

        form.addWidget(
            self.advanced_direction_enabled, 0, 2
        )
        form.addWidget(
            self.advanced_direction, 0, 3
        )
        form.addWidget(
            self.advanced_direction_ref, 0, 4
        )

        self.advanced_toggle.setToolTip(
            'Optional GPS fix details for the selected image. '
            'Unspecified fix details are removed when '
            'assigning a different location.'
        )
        form.setColumnStretch(5, 1)

        layout.addWidget(self.advanced_panel)
        self.advanced_panel.hide()

        self.advanced_toggle.toggled.connect(
            self.toggle_advanced_gps
        )

        self.advanced_altitude_enabled.toggled.connect(
            self.capture_advanced_gps
        )
        self.advanced_direction_enabled.toggled.connect(
            self.capture_advanced_gps
        )

        self.advanced_altitude.valueChanged.connect(
            self.capture_advanced_gps
        )
        self.advanced_direction.valueChanged.connect(
            self.capture_advanced_gps
        )
        self.advanced_direction_ref.currentIndexChanged.connect(
            self.capture_advanced_gps
        )

        self.advanced_altitude.setEnabled(False)
        self.advanced_direction.setEnabled(False)
        self.advanced_direction_ref.setEnabled(False)
        self.advanced_toggle.setEnabled(False)

    def toggle_advanced_gps(self, expanded):
        self.advanced_toggle.setArrowType(
            Qt.DownArrow if expanded else Qt.RightArrow
        )
        self.advanced_panel.setVisible(expanded)
        self.advanced_panel.updateGeometry()

        QTimer.singleShot(0, self.fit_method_page)

    def refresh_advanced_gps_controls(self):
        if not hasattr(self, 'advanced_panel'):
            return

        if not hasattr(self, 'image_list'):
            return

        path = self.image_list.current_path()
        draft = self.image_drafts.get(path)

        self.advanced_refreshing = True

        try:
            self.advanced_toggle.setEnabled(
                self.selection_only and bool(draft)
            )

            self.advanced_panel.setEnabled(bool(draft))

            if self.units == 'imperial':
                self.advanced_altitude.setSuffix(' ft')

                # Conservative bounds at three decimal places.
                self.advanced_altitude.setRange(
                    -39370.078, 328083.989
                )
            else:
                self.advanced_altitude.setSuffix(' m')
                self.advanced_altitude.setRange(
                    -12000, 100000
                )

            altitude = (
                draft.get('altitude', '')
                if draft else ''
            )

            direction = (
                draft.get('direction', '')
                if draft else ''
            )

            self.advanced_altitude_enabled.setChecked(
                altitude != ''
            )

            self.advanced_direction_enabled.setChecked(
                direction != ''
            )

            self.advanced_altitude.setValue(
                float(
                    altitude_from_metres(
                        altitude, self.units
                    )
                )
                if altitude != '' else 0
            )

            self.advanced_direction.setValue(
                float(direction)
                if direction != '' else 0
            )

            reference = (
                draft.get('direction_ref', 'T')
                if draft else 'T'
            )

            self.advanced_direction_ref.setCurrentIndex(
                self.advanced_direction_ref.findData(
                    reference
                )
            )

            self.advanced_altitude.setEnabled(
                bool(draft) and altitude != ''
            )
            self.advanced_direction.setEnabled(
                bool(draft) and direction != ''
            )
            self.advanced_direction_ref.setEnabled(
                bool(draft) and direction != ''
            )

        finally:
            self.advanced_refreshing = False

    def capture_advanced_gps(self, *_):
        if self.advanced_refreshing:
            return

        if not self.selection_only:
            return

        if not self.individual_map_mode():
            return

        path = self.image_list.current_path()
        draft = self.image_drafts.get(path)

        if not draft:
            return

        altitude_enabled = (
            self.advanced_altitude_enabled.isChecked()
        )
        direction_enabled = (
            self.advanced_direction_enabled.isChecked()
        )

        self.advanced_altitude.setEnabled(
            altitude_enabled
        )

        self.advanced_direction.setEnabled(
            direction_enabled
        )

        self.advanced_direction_ref.setEnabled(
            direction_enabled
        )

        sender = self.sender()

        # Only recalculate an altitude when that field
        # or its checkbox changes. Navigating images,
        # changing units or editing direction must not
        # introduce altitude rounding errors.

        if sender in (
            self.advanced_altitude,
            self.advanced_altitude_enabled,
        ):
            draft['altitude'] = (
                altitude_to_metres(
                    str(self.advanced_altitude.value()),
                    self.units,
                )
                if altitude_enabled else ''
            )

        if sender in (
            self.advanced_direction,
            self.advanced_direction_enabled,
            self.advanced_direction_ref,
        ):
            draft['direction'] = (
                f'{self.advanced_direction.value():.6f}'
                if direction_enabled else ''
            )

            draft['direction_ref'] = (
                self.advanced_direction_ref.currentData()
                if direction_enabled else 'T'
            )

        # Advanced values do not change source inspection.
        # The final planner will consume this updated draft.
        # No source metadata is written here.

        self.refresh_inspector()

    def individual_map_mode(self):
        return (
            self.kind == 'apply'
            and not self.proposal_only
            and self.method.currentData() == 'map'
        )

    def draft_position(self, path):
        draft = self.image_drafts.get(path)
        if not draft:
            return None

        return [
            coordinate(draft['latitude'], None, True),
            coordinate(draft['longitude'], None, False),
        ]

    def refresh_draft_controls(self):
        if not self.individual_map_mode():
            return

        path = self.image_list.current_path()
        point = self.draft_position(path)

        self.map_label.setText(
            'Proposed location: ' + position_text(point)
            if point is not None
            else 'No location change selected.'
        )

        self.refresh_advanced_gps_controls()

    def selected_input_position(self, path=None):
        if self.kind != 'apply' or self.proposal_only:
            return None

        if not self.selection_only:
            return None

        if self.individual_map_mode():
            return self.draft_position(
                path or self.image_list.current_path()
            )

        if self.method.currentData() == 'manual':
            try:
                return self.manual_position()
            except ValueError:
                return None

        return None

    def update_visual(self, *_):
        if not hasattr(self, 'location_map'): return
        if self.proposal_only: return
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

        proposed_position = (
            approved['position'] if approved else None
        )

        if (
            proposed_position is None
            and path
            and not reference
            and not (entry and entry.get('error'))
        ):
            proposed_position = self.selected_input_position(path)

        pending = path and not data and (not entry or self.worker)
        if proposed_position is not None:
            self.selected_location.setText(
                'Selected location: '
                + position_text(proposed_position)
            )
        elif position is not None:
            self.selected_location.setText(
                position_text(position)
            )
        else:
            self.selected_location.setText(
                'Reading GPS location…' if pending
                else camera_status(info) if path else ''
            )
        recorded_available = (
            position is not None
            and proposed_position is None
        )
        self.report_copy.setEnabled(recorded_available)
        self.report_map.setEnabled(recorded_available)
        self.report_copy.setVisible(proposed_position is None)
        self.report_map.setVisible(proposed_position is None)
        self.report_copy.setToolTip('Copy exact signed camera latitude and longitude' if position is not None else 'Requires valid, unambiguous camera coordinates.')
        self.report_map.setToolTip('Open the camera coordinates in your browser. This explicitly shares the position with OpenStreetMap.' if position is not None else 'Requires valid, unambiguous camera coordinates.')
        has_proposed = proposed_position is not None

        self.map_subject.hide()
        self.map_subject.setEnabled(False)

        if has_proposed:
            position = proposed_position

        self.map_heading.setText(
            'GPS source location' if reference
            else 'GPS Location'
        )
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
    dialog.setWindowTitle('KIMng - Location results'); dialog.setTextFormat(Qt.PlainText)
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



class GPSReviewDialog(QDialog):
    """Read-only review of the exact GPS publication plan."""

    BACK = 132

    def __init__(self, owner):
        super().__init__(owner)
        from PySide6.QtWidgets import (
            QTableWidget, QTableWidgetItem, QHeaderView,
            QAbstractItemView, QPlainTextEdit,
        )

        self.owner = owner
        self.entries = owner.plan['entries']
        self.setWindowTitle(
            'KIMng - Edit GPS metadata - Review Changes'
        )
        available = self.screen().availableGeometry()
        self.resize(
            min(1100, available.width() * 9 // 10),
            min(800, available.height() * 9 // 10),
        )
        self.setSizeGripEnabled(True)

        layout = QVBoxLayout(self)

        heading = QLabel('Review the planned GPS metadata changes.')
        layout.addWidget(heading)

        self.table = QTableWidget(len(self.entries), 3)
        self.table.setHorizontalHeaderLabels(
            ['Image', 'Action', 'Status']
        )
        self.table.setEditTriggers(
            QAbstractItemView.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Interactive)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        header.setMinimumSectionSize(90)
        self.table.setColumnWidth(1, 220)
        self.table.setColumnWidth(2, 100)

        self.table.verticalHeader().setDefaultSectionSize(28)

        for row, entry in enumerate(self.entries):
            status = entry['status']
            action = (
                destination_status(
                    entry,
                    entry.get('approved_location', {}).get('position'),
                )
            )
            if status == 'skip' and entry.get('skip_reason'):
                action = 'No changes'

            values = (
                Path(entry['source']).name,
                action,
                {
                    'change': 'Ready',
                    'skip': 'Unchanged',
                    'error': 'Blocked',
                }.get(status, status)
            )

            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(
                    entry.get('error', '')
                    or entry['source']
                )
                self.table.setItem(row, column, item)

        table_height = (
            header.sizeHint().height()
            + min(max(len(self.entries), 1), 4) * 28
            + 8
        )

        self.table.setFixedHeight(table_height)
        layout.addWidget(self.table)

        maps = QSplitter(Qt.Horizontal)

        self.map_panels = []

        for title in ('Current', 'Proposed'):
            panel = QWidget()
            column = QVBoxLayout(panel)
            column.setContentsMargins(0, 0, 0, 0)

            label = QLabel(title)
            font = label.font()
            font.setBold(True)
            label.setFont(font)
            column.addWidget(label)

            # Both panels use the existing map implementation,
            # including online-map consent and attribution.
            location_map = LocationMap(
                panel,
                units=owner.units,
                persistent=False,
                compact=True,
            )
            column.addWidget(location_map, 1)

            coordinates = QLabel()
            coordinates.setTextFormat(Qt.PlainText)
            coordinates.setWordWrap(True)
            column.addWidget(coordinates)

            maps.addWidget(panel)
            self.map_panels.append(
                (location_map, coordinates)
            )

        maps.setSizes([480, 480])
        layout.addWidget(maps, 1)

        changes_heading = QLabel('Additional changes')
        font = changes_heading.font()
        font.setBold(True)
        changes_heading.setFont(font)
        layout.addWidget(changes_heading)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setMaximumHeight(80)
        self.details.setMinimumHeight(48)
        layout.addWidget(self.details)

        output = QFormLayout()

        self.filename = QLineEdit()
        self.filename.setReadOnly(True)
        output.addRow('Filename', self.filename)

        layout.addLayout(output)

        self.policy_notice = QLabel(
            'Originals are not being changed.'
            if owner.policy == 'create'
            else 'The selected originals will be replaced.'
        )
        layout.addWidget(self.policy_notice)

        layout.addWidget(QLabel('Destination'))

        destination_row = QHBoxLayout()

        self.destination = QLineEdit()
        self.destination.setReadOnly(True)
        self.destination.setPlaceholderText(
            'Beside each source'
        )
        destination_row.addWidget(self.destination, 1)

        change = QPushButton('Change Destination…')
        change.setEnabled(owner.policy == 'create')
        change.clicked.connect(self.change_destination)
        destination_row.addWidget(change)

        layout.addLayout(destination_row)

        buttons = QHBoxLayout()

        back = QPushButton('Back')
        style_button(back, 'back')
        back.clicked.connect(
            lambda: self.done(self.BACK)
        )
        buttons.addWidget(back)
        buttons.addStretch()

        apply = QPushButton('Apply Changes')
        style_button(apply, 'apply')
        apply.setEnabled(
            any(e['status'] == 'change' for e in self.entries)
            and not any(
                e['status'] == 'error'
                for e in self.entries
            )
        )
        apply.clicked.connect(self.accept)
        buttons.addWidget(apply)

        cancel = QPushButton('Cancel')
        style_button(cancel, 'cancel')
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)

        for button in (back, apply, cancel):
            button.setAutoDefault(False)

        layout.addLayout(buttons)

        self.table.currentCellChanged.connect(
            self.show_entry
        )

        self.table.selectRow(0)
        self.show_entry(0)

    def show_entry(self, row, *_):
        if not 0 <= row < len(self.entries):
            return

        entry = self.entries[row]
        info = entry.get('location_before') or {}
        approved = entry.get('approved_location') or {}

        positions = (
            info.get('position'),
            (
                info.get('position')
                if entry['status'] == 'skip'
                else approved.get('position')
            ),
        )

        for (location_map, label), position in zip(
            self.map_panels, positions
        ):
            location_map.set_position(
                position,
                'No GPS data'
            )
            label.setText(
                position_text(position)
                if position is not None
                else 'No GPS data'
            )

        target = entry.get('target')

        self.filename.setText(
            Path(target).name
            if target and entry['status'] == 'change'
            else ''
        )

        if target:
            parent = Path(target).parent
            original_parent = Path(entry['source']).parent

            self.destination.setText(
                str(parent)
                if parent != original_parent
                else ''
            )
        else:
            self.destination.clear()

        display = next(
            (
                item for item in self.owner.display_entries
                if item['source'] == entry['source']
            ),
            entry,
        )

        rows = gps_summary_changes(display)

        details = [
            line for line in rows
            if line not in (
                'Set camera GPS coordinates',
                'Replace camera coordinates',
            )
        ]

        if entry['status'] == 'change':
            altitude = approved.get('altitude')

            if altitude is not None:
                units = self.owner.units
                suffix = ' ft' if units == 'imperial' else ' m'

                details.append(
                    'Planned altitude: '
                    + altitude_from_metres(altitude, units)
                    + suffix
                    + ' (WGS84)'
                )

            direction = approved.get('direction')

            if direction is not None:
                reference = (
                    'magnetic north'
                    if approved.get('direction_ref') == 'M'
                    else 'true north'
                )

                details.append(
                    f'Planned image direction: {direction:g}° '
                    + 'from ' + reference
                )

        details.extend(entry.get('warnings', []))

        if entry.get('error'):
            details.append(entry['error'])

        if entry['status'] == 'skip':
            details = [
                entry.get(
                    'skip_reason',
                    'No changes required. No output will be created.'
                )
            ]
            details.extend(entry.get('warnings', []))

        self.details.setPlainText(
            '\n'.join(dict.fromkeys(details))
            or 'No additional GPS metadata changes.'
        )

    def change_destination(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            'Choose destination',
            str(Path(
                self.entries[0]['source']
            ).parent),
        )

        if not folder:
            return

        from kim_preview import allocate, finish_entry
        from kim_location import approval_digest
        import copy

        try:
            plan = copy.deepcopy(self.owner.plan)
            reserved = set()

            for entry in plan['entries']:
                if entry['status'] != 'change':
                    continue

                candidate = str(
                    Path(folder) / Path(entry['target']).name
                )

                target = allocate(
                    entry['source'],
                    candidate,
                    'create',
                    reserved,
                    '-',
                )

                finish_entry(entry, target, 'create')

                for row in entry['rows']:
                    if row[1] == 'Output policy / destination':
                        row[3] = Path(target).name
                        row[4] = str(Path(target).parent)

            plan['approval_digest'] = approval_digest(plan)
            verify_plan(plan)

        except Exception as exc:
            QMessageBox.warning(
                self,
                'Change Destination',
                str(exc),
            )
            return

        # The changed destination is part of the exact plan
        # shown by this review and subsequently executed.
        self.owner.plan = plan
        self.entries = plan['entries']
        self.show_entry(self.table.currentRow())

    def done(self, result):
        for location_map, _label in self.map_panels:
            location_map.stop_requests()
        super().done(result)


def main():
    check_graphical_session()
    if sys.argv[1:2] == ['--result']:
        app = QApplication(sys.argv[:1]); app.setApplicationName('KIMng')
        show_location_result(*sys.argv[2:]); return 0
    kind, result, policy, seeds_path, *files = sys.argv[1:]
    if kind not in TITLES: raise ValueError('Unknown location operation')
    seeds = Path(seeds_path).read_bytes().decode().split('\0')[:-1] if seeds_path != '-' else None
    app = QApplication(sys.argv[:1]); app.setApplicationName('KIMng')
    initial_path = os.environ.get('KIM_LOCATION_CONFIG')
    initial = json.loads(Path(initial_path).read_text()) if initial_path else None
    if kind == 'gpx' and not initial: initial = {'method': 'gpx'}
    if kind in ('copy', 'gpx'): kind = 'apply'
    dialog = LocationDialog(kind, files, policy, seeds, initial)

    if kind == 'apply' and policy in ('create', 'overwrite'):
        dialog.dedicated_review = True
        dialog.review_back = False
        dialog.setAttribute(Qt.WA_DontShowOnScreen, True)

    preparing = None

    if getattr(dialog, 'dedicated_review', False):
        from PySide6.QtWidgets import QProgressDialog

        preparing = QProgressDialog(
            'Preparing GPS changes…',
            'Cancel',
            0, 0,
        )

        preparing.setWindowTitle(
            'KIMng - Edit GPS metadata - Review Changes'
        )
        preparing.setMinimumDuration(0)
        preparing.setAutoClose(False)
        preparing.setAutoReset(False)
        preparing.canceled.connect(dialog.reject)

        dialog.review_preparing = preparing
        preparing.resize(460, 120)
        preparing.show()

    status = dialog.exec()

    if preparing is not None:
        preparing.hide()
        preparing.deleteLater()

    if getattr(dialog, 'review_back', False):
        return 132
    if kind == 'report': return 0 if dialog.completed_report else 130
    if status != QDialog.Accepted: return 130
    if policy == 'select':
        requested_policy = (
            'create'
            if dialog.output_create.isChecked()
            else 'overwrite'
        )
        Path(result).write_text(json.dumps(dict(
            dialog.config(),
            files=dialog.files,
            output_policy=requested_policy,
            launched_from_report=dialog.launched_from_report,
        )))
    else:
        save_plan(result, dialog.plan)
    return 0


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception as exc: print('Image Location Tools: ' + str(exc), file=sys.stderr); raise SystemExit(1)
