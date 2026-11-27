#!/usr/bin/env python3
"""Reusable recipe manager/builder widget and independent Dolphin launcher."""
from kim_dialog_buttons import style_button, style_button_box
import copy
import os
import re
import sys
import uuid
from pathlib import Path
from kim_photo_selection import choose_images, RECIPE_IMAGE_EXTENSIONS
from PySide6.QtCore import QTimer, Qt, QThread, Signal, Slot, QDate, QTime, QSettings
from PySide6.QtGui import QIcon, QPalette, QKeySequence
from PySide6.QtWidgets import (QApplication, QWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QFormLayout, QGridLayout, QLabel, QPushButton, QComboBox, QLineEdit, QListWidget, QListWidgetItem, QSpinBox,
    QCheckBox, QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog, QInputDialog,
    QProgressDialog, QHeaderView, QGroupBox, QSplitter, QSizePolicy, QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem, QDialogButtonBox, QMenu, QScrollArea, QStyle,
    QDateEdit, QTimeEdit, QDoubleSpinBox, QTextEdit, QFrame)
from kim_recipe_core import (AUTHORED_SCHEMA, folder_label, folder_path, builtin_category, RecipeError, builtins,
                             save_users, load_users, load_library, save_library, read_portable_recipe, write_portable_recipe, read_recipe_bundle, write_recipe_bundle, merge_recipe_bundle, RecipeLibrary, library_groups, recipe_title, validate, preview, execute, handler, format_output_pattern, display_output_pattern, load_remembered_values, clear_remembered_values)


from kim_recipe_run import RunRecipeDialog, RecipeWorker, PropertyView, property_fields, WarningView
from kim_recipe_params import (
    can_reorder_parameter,
    compatible_parameters_for_field,
    compatible_parameters_for_template,
    evaluate_parameters,
    generate_parameter_id,
    has_parameter_references,
    is_bindable_field,
    is_parameterized,
    parameter_from_field,
    parameter_references,
    parse_template,
    preview_output_example,
    resolve_recipe,
    summarize_condition,
    validate_authored,
)
from kim_recipe_param_ui import PreviewSettingsDialog
from kim_recipe_author_ui import (
    ParameterEditorDialog,
    ParametersSectionWidget,
    StepActivationDialog,
    make_field_source_button,
    make_insert_variable_button,
)

from kim_ui import CaptureDateInput, CaptureDateOptions, CaptureAdjustment, RotationInput, HelpButton, with_help


class ExamplePreviewWorker(QThread):
    stage_changed = Signal(str)

    def __init__(self, recipe, sample, index, generation, parent, checked_inputs=None):
        super().__init__(parent)
        self.recipe, self.sample, self.index = copy.deepcopy(recipe), sample, index
        self.generation, self.row = generation, None
        # Workers own their cache copies; never share mutable Qt worker state.
        self.checked_inputs = copy.deepcopy(checked_inputs or {})

    def run(self):
        from kim_process import inspection_context
        from kim_recipe_core import PreviewRow
        from kim_recipe_image import checked_input_headers
        try:
            with inspection_context(self.stage_changed.emit,self.isInterruptionRequested), checked_input_headers(self.checked_inputs):
                self.row = preview(
                    self.recipe,
                    [self.sample],
                    start_index=self.index,
                    number_collisions=True
                )[0]
        except Exception as exc:
            self.row = PreviewRow(str(self.sample),problems=[str(exc)])


_PARAMETERS_TAB_TOOLTIP = (
    'Let a Recipe ask for different settings each time it runs, '
    'such as a project name, image dimensions or JPEG quality.'
)


def _display_op_label(op, definitions=None):
    """Standardize visible operation presentation without changing stored IDs or schemas."""
    if op == 'image.auto_orient':
        return 'Auto-orient'
    if op == 'metadata.strip_gps':
        return 'Remove GPS metadata'
    if definitions and op in definitions:
        return definitions[op].get('label', op)
    return op


class OperationPicker(QDialog):
    """One view of the handler's definitions; IDs and parameter data stay shared."""
    def __init__(self, definitions, parent=None):
        super().__init__(parent)
        self.setWindowTitle('KIMng - Add Operation'); self.resize(540, 390)
        self.definitions = definitions; self.operation_id = None
        layout = QVBoxLayout(self)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search operations…')
        self.search.setAccessibleName('Search operations by name or keyword'); layout.addWidget(self.search)
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName('Operations grouped by category'); layout.addWidget(self.tree, 1)
        self.description_frame = QFrame(self)
        self.description_frame.setFrameShape(QFrame.StyledPanel)
        desc_layout = QVBoxLayout(self.description_frame)
        desc_layout.setContentsMargins(8, 6, 8, 6)
        self.description_label = QLabel(self.description_frame)
        self.description_label.setTextFormat(Qt.PlainText)
        self.description_label.setWordWrap(True)
        self.description_label.setMinimumHeight(34)
        self.description_label.setAccessibleName('Selected operation description')
        desc_layout.addWidget(self.description_label)
        layout.addWidget(self.description_frame)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        style_button_box(buttons)
        self.add = buttons.button(QDialogButtonBox.Ok); self.add.setText('Add'); self.add.setEnabled(False)
        buttons.accepted.connect(self.choose); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.search.textChanged.connect(self.refresh)
        self.search.returnPressed.connect(self.choose)
        self.tree.currentItemChanged.connect(self.selection_changed)
        self.tree.itemDoubleClicked.connect(lambda *_: self.choose())
        self.refresh(); self.search.setFocus()

    def refresh(self):
        from kim_recipe_image import CATEGORIES
        query = self.search.text().casefold().split(); self.tree.clear()
        first = None
        for category in CATEGORIES:
            operations = [(op,d) for op,d in self.definitions.items() if d.get('category', CATEGORIES[3]) == category and
                          all(word in (category+' '+_display_op_label(op, self.definitions)+' '+d.get('keywords','')+' '+d.get('description','')).casefold() for word in query)]
            if not operations: continue
            group = QTreeWidgetItem([category]); group.setFlags(group.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(group)
            for op, definition in sorted(operations, key=lambda item:_display_op_label(item[0], self.definitions).casefold()):
                display_name = _display_op_label(op, self.definitions)
                item = QTreeWidgetItem([display_name]); item.setData(0,Qt.UserRole,op)
                item.setToolTip(0,definition.get('description',display_name)); group.addChild(item)
                if first is None: first = item
            group.setExpanded(True)
        self.tree.setCurrentItem(first); self.selection_changed()

    def selection_changed(self,*_):
        item = self.tree.currentItem()
        self.operation_id = item.data(0,Qt.UserRole) if item else None
        self.add.setEnabled(bool(self.operation_id))
        if self.operation_id and self.operation_id in self.definitions:
            desc = self.definitions[self.operation_id].get('description', '')
            self.description_label.setText(desc or _display_op_label(self.operation_id, self.definitions))
        else:
            self.description_label.setText('Select an operation to see what it does.')

    def choose(self):
        if self.operation_id: self.accept()

    def keyPressEvent(self,event):
        if event.key() == Qt.Key_Down and self.search.hasFocus():
            self.tree.setFocus(); event.accept(); return
        super().keyPressEvent(event)



class RecipePreviewTree(QTreeWidget):
    """Read-only grouping of the existing Recipe planner properties."""

    GROUPS = (
        "Files",
        "Image details",
        "Metadata",
        "Publication details",
    )

    FILE_FIELDS = {
        "source filename", "source folder", "source image",
        "output filename", "output folder", "output directory",
    }

    PUBLICATION_FIELDS = {
        "publication", "originals", "output plan",
        "validation problem", "warning", "warnings",
    }

    METADATA_TERMS = (
        "metadata", "exif", "iptc", "xmp", "gps",
        "capture date", "capture time", "file modified",
        "copyright", "creator", "artist", "rights",
        "keywords", "headline", "caption", "description",
        "ai fields", "provenance", "sidecar",
        "date created", "date original",
    )

    def __init__(self, parent=None):
        super().__init__(parent)

        from PySide6.QtCore import QSettings

        self.setColumnCount(2)
        self.setHeaderLabels(["Property", "Planned value"])
        self.setHeaderHidden(True)
        self.setRootIsDecorated(True)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.setEditTriggers(QTreeWidget.NoEditTriggers)
        self.setAccessibleName("Grouped Recipe preview properties")

        header = self.header()
        header.setSectionResizeMode(0, QHeaderView.Interactive)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.setColumnWidth(0, 195)

        self.settings = QSettings("KIMng", "RecipeEditor")
        self._populating = False
        self.groups = {}

        self.expanded_preferences = {
            name: self.settings.value(
                "preview_group_" + name.lower().replace(" ", "_"),
                name in ("Files", "Image details"),
                type=bool,
            )
            for name in self.GROUPS
        }

        self.itemExpanded.connect(self.remember_expansion)
        self.itemCollapsed.connect(self.remember_expansion)

        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_copy_menu)

    @classmethod
    def category(cls, name):
        lower = name.casefold()

        if lower in cls.FILE_FIELDS:
            return "Files"

        if lower in cls.PUBLICATION_FIELDS:
            return "Publication details"

        if any(term in lower for term in cls.METADATA_TERMS):
            return "Metadata"

        # New and unfamiliar planner fields must remain visible.
        return "Image details"

    @staticmethod
    def display_value(name, value):
        value = str(value)

        if name == "Output dimensions":
            value = value.replace(" pixels (planned)", "")
            value = value.replace(" (planned)", "")

        if name == "Originals" and value == "Always unchanged":
            value = "Not being changed"

        return value

    def set_fields(self, fields):
        grouped = {name: [] for name in self.GROUPS}

        for name, value in fields:
            name = str(name)
            grouped[self.category(name)].append(
                (name, self.display_value(name, value))
            )

        # Presentation order only. All planner fields are preserved.
        # Python's stable sort retains the original relative order
        # of fields that are not explicitly prioritized.
        priorities = {
            "Files": (
                "source filename",
                "output filename",
                "source folder",
                "output folder",
            ),
            "Image details": (
                "original dimensions",
                "output dimensions",
                "source format",
                "final format",
                "quality",
                "orientation",
                "icc",
                "sample precision",
            ),
        }

        for category, names in priorities.items():
            rank = {
                name: index
                for index, name in enumerate(names)
            }
            grouped[category].sort(
                key=lambda field: rank.get(
                    field[0].casefold(), len(rank)
                )
            )

        has_problem = any(
            name == "Validation problem"
            for name, _ in grouped["Publication details"]
        )

        icons = {
            "Files": "folder-documents",
            "Image details": "image-x-generic",
            "Metadata": "document-properties",
            "Publication details": "document-save",
        }

        self._populating = True
        self.setUpdatesEnabled(False)

        try:
            self.clear()
            self.groups.clear()

            for title in self.GROUPS:
                group = QTreeWidgetItem([title, ""])
                group.setData(0, Qt.UserRole, title)
                group.setFlags(
                    group.flags() & ~Qt.ItemIsSelectable
                )

                icon_name = (
                    "dialog-warning"
                    if title == "Publication details" and has_problem
                    else icons[title]
                )

                icon = QIcon.fromTheme(icon_name)
                if not icon.isNull():
                    group.setIcon(0, icon)

                font = group.font(0)
                font.setBold(True)
                group.setFont(0, font)

                self.addTopLevelItem(group)
                self.groups[title] = group

                for name, value in grouped[title]:
                    item = QTreeWidgetItem([name, value])
                    item.setToolTip(0, name)
                    item.setToolTip(1, value)
                    group.addChild(item)

                expanded = self.expanded_preferences[title]

                if title == "Publication details" and has_problem:
                    expanded = True

                group.setExpanded(expanded)

        finally:
            self.setUpdatesEnabled(True)
            self._populating = False

        # Leave sufficient room for filenames and metadata values.
        names = [
            group.child(index).text(0)
            for group in self.groups.values()
            for index in range(group.childCount())
        ]

        preferred = max(
            (
                self.fontMetrics().horizontalAdvance(name)
                + self.indentation() * 2 + 14
                for name in names
            ),
            default=195,
        )

        available = self.viewport().width()

        if available > 100:
            self.setColumnWidth(
                0, min(max(155, preferred), int(available * 0.46))
            )

    def remember_expansion(self, item):
        if self._populating:
            return

        title = item.data(0, Qt.UserRole)

        if title not in self.GROUPS:
            return

        expanded = item.isExpanded()
        self.expanded_preferences[title] = expanded

        key = "preview_group_" + title.lower().replace(" ", "_")
        self.settings.setValue(key, expanded)

    def copy_selected_rows(self):
        lines = []

        for item in self.selectedItems():
            if item.parent() is None:
                continue

            lines.append(
                item.text(0) + "\t" + item.text(1)
            )

        if lines:
            QApplication.clipboard().setText(
                "\n".join(lines)
            )

    def show_copy_menu(self, position):
        item = self.itemAt(position)
        menu = QMenu(self)

        copy_value = menu.addAction("Copy value")
        copy_value.setEnabled(
            item is not None and item.parent() is not None
        )

        copy_rows = menu.addAction("Copy selected rows")
        copy_rows.setEnabled(
            any(
                selected.parent() is not None
                for selected in self.selectedItems()
            )
        )

        action = menu.exec(
            self.viewport().mapToGlobal(position)
        )

        if action == copy_value and item is not None:
            QApplication.clipboard().setText(item.text(1))

        elif action == copy_rows:
            self.copy_selected_rows()

    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self.copy_selected_rows()
            event.accept()
            return

        super().keyPressEvent(event)



from PySide6.QtCore import QMimeData
from PySide6.QtGui import QDrag


class RecipeLibraryTree(QTreeWidget):
    """Folder-only drops, with native Move feedback."""

    MIME = 'application/x-kimng-recipe-id'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.move_handler = None
        self._hover_item = None
        self._hover_background = None
        self._hover_foreground = None

        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)

        # We highlight the destination folder rather than display
        # insertion lines suggesting that Recipes can be reordered.
        self.setDropIndicatorShown(False)
        self.setAutoExpandDelay(700)

    def supportedDropActions(self):
        return Qt.MoveAction

    def startDrag(self, supported_actions):
        item = self.currentItem()
        if (
            item is None
            or item.data(0, Qt.UserRole + 1) != 'recipe'
            or not (item.flags() & Qt.ItemIsDragEnabled)
        ):
            return

        recipe_id = item.data(0, Qt.UserRole)
        if not isinstance(recipe_id, str):
            return

        mime = QMimeData()
        mime.setData(self.MIME, recipe_id.encode('utf-8'))

        drag = QDrag(self)
        drag.setMimeData(mime)

        icon = item.icon(0)
        if not icon.isNull():
            drag.setPixmap(icon.pixmap(24, 24))

        # Advertise Move as both the only supported action and the
        # preferred action. Never request Copy or Link.
        try:
            drag.exec(Qt.MoveAction, Qt.MoveAction)
        finally:
            self.clear_drop_highlight()

    def valid_drop_item(self, event):
        if (
            event.source() is not self
            or not event.mimeData().hasFormat(self.MIME)
        ):
            return None

        item = self.itemAt(event.position().toPoint())
        if (
            item is None
            or item.data(0, Qt.UserRole + 1) != 'folder'
            or not (item.flags() & Qt.ItemIsDropEnabled)
        ):
            return None

        # Root and Unfiled are valid. Top-level category headings
        # have no destination identifier and remain prohibited.
        if item.data(0, Qt.UserRole + 2) is None:
            return None

        return item

    def clear_drop_highlight(self):
        if self._hover_item is not None:
            self._hover_item.setBackground(
                0, self._hover_background
            )
            self._hover_item.setForeground(
                0, self._hover_foreground
            )
        self._hover_item = None
        self._hover_background = None
        self._hover_foreground = None

    def highlight_drop_target(self, item):
        if item is self._hover_item:
            return

        self.clear_drop_highlight()

        if item is None:
            return

        self._hover_item = item
        self._hover_background = item.background(0)
        self._hover_foreground = item.foreground(0)

        palette = self.palette()
        item.setBackground(
            0, palette.brush(QPalette.Active, QPalette.Highlight)
        )
        item.setForeground(
            0, palette.brush(
                QPalette.Active, QPalette.HighlightedText
            )
        )

    def dragEnterEvent(self, event):
        if (
            event.source() is self
            and event.mimeData().hasFormat(self.MIME)
        ):
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        item = self.valid_drop_item(event)
        self.highlight_drop_target(item)

        if item is None:
            event.ignore()
            return

        # Qt must receive a valid action during hover, not only
        # when dropEvent runs.
        event.setDropAction(Qt.MoveAction)
        event.accept()

    def dragLeaveEvent(self, event):
        self.clear_drop_highlight()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        item = self.valid_drop_item(event)

        if item is None:
            self.clear_drop_highlight()
            event.ignore()
            return

        destination = item.data(0, Qt.UserRole + 2)

        try:
            recipe_id = bytes(
                event.mimeData().data(self.MIME)
            ).decode('utf-8')
        except UnicodeError:
            self.clear_drop_highlight()
            event.ignore()
            return

        self.clear_drop_highlight()

        if not callable(self.move_handler):
            event.ignore()
            return

        # Keep the established validated, persistent library move.
        # Never invoke the default QTreeWidget drop implementation.
        if self.move_handler(recipe_id, destination):
            event.setDropAction(Qt.MoveAction)
            event.accept()
        else:
            event.ignore()



class _MenuActionProxy:
    """Thin adapter exposing button-like helpers over a consolidated QAction."""

    def __init__(self, action, menu_button):
        self._action = action
        self._menu_button = menu_button

    def click(self):
        if self._action.isEnabled():
            self._action.trigger()

    def setFocus(self):
        self._menu_button.setFocus()

    def isEnabled(self):
        return self._action.isEnabled()

    def setEnabled(self, enabled):
        self._action.setEnabled(bool(enabled))

    def isVisible(self):
        return self._action.isVisible()

    def setVisible(self, visible):
        self._action.setVisible(bool(visible))

    def setText(self, text):
        self._action.setText(text)

    def text(self):
        return self._action.text()


class RecipeWidget(QWidget):
    """Embeddable manager; files are optional and preview is always text-only."""
    def __init__(self, files=(), parent=None, from_run=False, allow_dev_draft_run=False):
        super().__init__(parent)
        self.files = list(files)
        self.from_run = from_run
        self.allow_dev_draft_run = bool(allow_dev_draft_run)
        self.draft_ids = set()
        self.dev_draft_ids = set()
        self.saved_new_recipe_id = None
        self.saved_recipe_id = None
        self.example_files = None
        self.run_dialog = None
        self.repair_inputs = None
        self.active_index = -1
        self.baseline = None
        self.shipped = builtins()
        library = load_library()
        self.users, self.folders = library.recipes, library.folders
        self.recipe = None
        self.preview_worker = None; self.preview_generation = 0; self.preview_pending = False; self.preview_closing = False
        self._preview_values_by_recipe = {}
        self._preview_expected_snapshot = None
        self._preview_step_active = {}
        self.checked_inputs = {}
        self.loading = False
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.editor = QWidget(self)
        root.addWidget(self.editor)
        layout = QVBoxLayout(self.editor)
        layout.setContentsMargins(0, 0, 0, 0)
        # Two-pane Recipe Editor:
        # left Recipe library (~25%) | right tabbed editing workspace (~75%).
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter)

        navigation = QGroupBox('Recipes')
        workspace = QWidget()

        navigation.setMinimumWidth(220)
        workspace.setMinimumWidth(620)

        self.splitter.addWidget(navigation)
        self.splitter.addWidget(workspace)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 3)

        navigation_layout = QVBoxLayout(navigation)
        navigation_layout.setContentsMargins(8, 8, 8, 8)
        navigation_layout.setSpacing(6)

        controls = QVBoxLayout(workspace)
        controls.setContentsMargins(8, 0, 0, 0)
        controls.setSpacing(4)

        # Preserve the existing selector as an internal compatibility
        # control. The visible navigation is the native Recipe tree.
        self.selector = QComboBox()
        self.selector.hide()
        navigation_layout.addWidget(self.selector)

        self.recipe_search = QLineEdit()
        self.recipe_search.setPlaceholderText('Search recipes…')
        self.recipe_search.setClearButtonEnabled(True)
        self.recipe_search.setAccessibleName('Search recipes')
        navigation_layout.addWidget(self.recipe_search)

        self.recipe_tree = RecipeLibraryTree()
        self.recipe_tree.setHeaderHidden(True)
        self.recipe_tree.setRootIsDecorated(True)
        self.recipe_tree.setUniformRowHeights(True)
        self.recipe_tree.setAnimated(True)
        self.recipe_tree.setAccessibleName(
            'Built-in Recipes and user Recipe folders'
        )
        navigation_layout.addWidget(self.recipe_tree, 1)

        self.recipe_search.textChanged.connect(
            self.refresh_recipe_tree
        )
        self.recipe_tree.currentItemChanged.connect(
            self.recipe_tree_selection_changed
        )
        self.recipe_tree.move_handler = self.move_recipe_to_folder
        self.recipe_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.recipe_tree.customContextMenuRequested.connect(
            self.show_recipe_tree_menu
        )
        self.recipe_tree.itemExpanded.connect(
            self.save_recipe_tree_expansion
        )
        self.recipe_tree.itemCollapsed.connect(
            self.save_recipe_tree_expansion
        )

        self.shortcut_legend = QLabel(
            "★  Available in Dolphin's right-click menu"
        )
        self.shortcut_legend.setToolTip(
            'Starred recipes have a saved shortcut in '
            "Dolphin's KIMng Recipes menu."
        )
        navigation_layout.addWidget(self.shortcut_legend)

        # Creation actions remain directly accessible below the Recipe tree.
        creation = QHBoxLayout()
        creation.setSpacing(6)

        self.management_buttons = {}

        new_recipe = QPushButton(
            QIcon.fromTheme('document-new'), 'New Recipe'
        )
        new_recipe.setToolTip('Create a new Recipe')
        new_recipe.clicked.connect(
            lambda checked=False: self.create_recipe_from_tree()
        )
        self.management_buttons['New'] = new_recipe
        creation.addWidget(new_recipe, 1)

        new_folder = QPushButton(
            QIcon.fromTheme('folder-new'), 'New Folder'
        )
        new_folder.setToolTip('Create a Recipe folder')
        new_folder.clicked.connect(self.create_folder)
        creation.addWidget(new_folder, 1)
        navigation_layout.addLayout(creation)

        # Consolidated native menu for selected-Recipe / selected-Folder actions.
        self.selected_recipe_button = QToolButton()
        self.selected_recipe_button.setText('Selected Recipe')
        self.selected_recipe_button.setIcon(
            QIcon.fromTheme('document-properties')
        )
        self.selected_recipe_button.setToolButtonStyle(
            Qt.ToolButtonTextBesideIcon
        )
        self.selected_recipe_button.setPopupMode(
            QToolButton.InstantPopup
        )
        self.selected_recipe_button.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self.selected_recipe_button.setAccessibleName(
            'Selected Recipe actions'
        )

        self.selected_recipe_menu = QMenu(self.selected_recipe_button)

        self.duplicate_action = self.selected_recipe_menu.addAction(
            QIcon.fromTheme('edit-copy'), 'Duplicate Recipe'
        )
        self.duplicate_action.setToolTip('Create an editable Recipe copy')
        self.duplicate_action.triggered.connect(lambda checked=False: self.duplicate())

        self.move_recipe_action = self.selected_recipe_menu.addAction(
            QIcon.fromTheme('folder-move'), 'Move to Folder…'
        )
        self.move_recipe_action.setToolTip('Move the selected Recipe into another folder')
        self.move_recipe_action.triggered.connect(
            lambda checked=False: self.choose_recipe_destination()
        )

        self.selected_recipe_separator = self.selected_recipe_menu.addSeparator()

        self.rename_action = self.selected_recipe_menu.addAction(
            QIcon.fromTheme('edit-rename'), 'Rename'
        )
        self.rename_action.triggered.connect(
            lambda checked=False: self.rename_selected_tree_item()
        )

        self.delete_action = self.selected_recipe_menu.addAction(
            QIcon.fromTheme('edit-delete'), 'Delete'
        )
        self.delete_action.triggered.connect(
            lambda checked=False: self.delete_selected_tree_item()
        )

        self.selected_recipe_button.setMenu(self.selected_recipe_menu)
        navigation_layout.addWidget(self.selected_recipe_button)

        self.management_buttons['Duplicate to Edit'] = _MenuActionProxy(
            self.duplicate_action, self.selected_recipe_button
        )
        self.management_buttons['Rename'] = _MenuActionProxy(
            self.rename_action, self.selected_recipe_button
        )
        self.management_buttons['Delete'] = _MenuActionProxy(
            self.delete_action, self.selected_recipe_button
        )
        self.move_recipe_button = _MenuActionProxy(
            self.move_recipe_action, self.selected_recipe_button
        )

        # One native menu for individual and bundle transfers.
        self.transfer_button = QToolButton()
        self.transfer_button.setText('Import/Export')
        self.transfer_button.setIcon(
            QIcon.fromTheme('document-open')
        )
        self.transfer_button.setToolButtonStyle(
            Qt.ToolButtonTextBesideIcon
        )
        self.transfer_button.setPopupMode(
            QToolButton.InstantPopup
        )
        self.transfer_button.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self.transfer_button.setAccessibleName(
            'Import and export Recipes and bundles'
        )

        self.transfer_menu = QMenu(self.transfer_button)

        self.import_recipe_button = self.transfer_menu.addAction(
            'Import Recipe…'
        )
        self.import_recipe_button.triggered.connect(
            lambda checked=False: self.import_recipe_file()
        )

        self.export_recipe_button = self.transfer_menu.addAction(
            'Export Recipe…'
        )
        self.export_recipe_button.triggered.connect(
            lambda checked=False: self.export_recipe_file()
        )

        self.transfer_menu.addSeparator()

        self.import_bundle_button = self.transfer_menu.addAction(
            'Import Recipe bundle…'
        )
        self.import_bundle_button.triggered.connect(
            lambda checked=False: self.import_bundle_file()
        )

        self.export_bundle_button = self.transfer_menu.addAction(
            'Export Recipe bundle…'
        )
        self.export_bundle_button.triggered.connect(
            lambda checked=False: self.export_bundle_file()
        )

        self.transfer_button.setMenu(self.transfer_menu)
        navigation_layout.addWidget(self.transfer_button)

        # Save Recipe belongs with library management actions in the left pane.
        save = QPushButton(
            QIcon.fromTheme('document-save'), 'Save Recipe'
        )
        save.setShortcut(QKeySequence.Save)
        save.setToolTip('Save changes to the selected Recipe (Ctrl+S)')
        save.clicked.connect(self.save)
        self.management_buttons['Save'] = save
        navigation_layout.addWidget(save)

        # 1. Shared Recipe details (compact, always visible above workspace tabs).
        details_top = QHBoxLayout()
        details_top.setContentsMargins(0, 0, 0, 0)
        details_top.setSpacing(8)
        name_label = QLabel('Recipe name:')
        self.name = QLineEdit(); self.name.textEdited.connect(self.changed)
        name_label.setBuddy(self.name)
        self.reset_builtin = QPushButton(QIcon.fromTheme('edit-undo'), 'Reset to Defaults')
        self.reset_builtin.clicked.connect(self.reset_builtin_defaults)
        folder_label_w = QLabel('Folder:')
        self.library_folder = QComboBox()
        self.library_folder.setMinimumWidth(140)
        self.library_folder.currentIndexChanged.connect(self.folder_changed)
        folder_label_w.setBuddy(self.library_folder)
        details_top.addWidget(name_label)
        details_top.addWidget(self.name, 2)
        details_top.addWidget(self.reset_builtin)
        details_top.addWidget(folder_label_w)
        details_top.addWidget(self.library_folder, 1)
        controls.addLayout(details_top)

        shortcut_row = QHBoxLayout()
        shortcut_row.setContentsMargins(0, 0, 0, 0)
        shortcut_row.setSpacing(8)
        self.shortcut_checkbox = QCheckBox(
            "Show in Dolphin's right-click menu"
        )
        self.shortcut_checkbox.setToolTip(
            'When enabled and saved, this recipe appears under '
            'KIMng > Recipes when you right-click selected images '
            'in Dolphin.'
        )
        self.shortcut_checkbox.toggled.connect(self.shortcut_changed)
        shortcut_row.addWidget(self.shortcut_checkbox)
        shortcut_row.addStretch(1)
        controls.addLayout(shortcut_row)

        description_label = QLabel('Description:')
        controls.addWidget(description_label)

        self.description = QTextEdit()
        self.description.setPlaceholderText(
            'Describe what this Recipe does and when to use it.'
        )
        self.description.setAcceptRichText(False)
        self.description.setMinimumHeight(34)
        self.description.setMaximumHeight(44)
        self.description.setAccessibleName('Recipe description')
        self.description.textChanged.connect(self.changed)
        description_label.setBuddy(self.description)
        controls.addWidget(self.description)

        self.recipe_guidance = QLabel(
            'Built-in Recipe. Duplicate to create an editable copy.'
        )
        self.recipe_guidance.setWordWrap(True)
        controls.addWidget(self.recipe_guidance)

        # 2. Native QTabWidget with Operations, Parameters, and Preview tabs.
        self.workspace_tabs = QTabWidget()
        controls.addWidget(self.workspace_tabs, 1)

        # --- Tab 0: Operations ---
        operations_tab = QWidget()
        ops_tab_layout = QVBoxLayout(operations_tab)
        ops_tab_layout.setContentsMargins(6, 6, 6, 6)
        ops_tab_layout.setSpacing(4)

        self.edit_splitter = QSplitter(Qt.Vertical)
        self.edit_splitter.setChildrenCollapsible(False)
        ops_tab_layout.addWidget(self.edit_splitter, 1)

        steps_section = QWidget()
        steps_section.setMinimumHeight(148)
        steps_layout = QVBoxLayout(steps_section)
        steps_layout.setContentsMargins(0, 0, 0, 0)
        steps_layout.setSpacing(4)

        self.edit_splitter.addWidget(steps_section)

        self.steps = QListWidget()
        self.steps.setMinimumHeight(124)
        self.steps.setAccessibleName('Ordered recipe steps; check to enable')
        self.steps.currentRowChanged.connect(self.edit_step)
        self.steps.itemChanged.connect(self.toggle_step)
        self.steps.setContextMenuPolicy(Qt.CustomContextMenu)
        self.steps.customContextMenuRequested.connect(self.show_step_context_menu)
        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.setSpacing(6)
        bar.addWidget(QLabel('Recipe steps'))
        self.operation = QPushButton(QIcon.fromTheme('list-add'), 'Add Operation…')
        self.operation.clicked.connect(self.add_step); bar.addWidget(self.operation)
        self.step_buttons = []
        button = QPushButton(QIcon.fromTheme('list-remove'), 'Remove')
        button.clicked.connect(self.remove_step); bar.addWidget(button); self.step_buttons.append(button)
        bar.addStretch(1)
        self.step_count = QLabel()
        bar.addWidget(self.step_count)
        self.operation_bar = bar
        steps_layout.addLayout(bar)
        self.steps_row = QHBoxLayout()
        self.steps_row.addWidget(self.steps, 1)
        self.move_controls = QWidget()
        moves = QVBoxLayout(self.move_controls); moves.setContentsMargins(0, 0, 0, 0)
        self.move_up = QToolButton(); self.move_down = QToolButton()
        for button, icon_name, arrow, delta, shortcut in (
            (self.move_up, 'go-up', Qt.UpArrow, -1, 'Alt+Up'),
            (self.move_down, 'go-down', Qt.DownArrow, 1, 'Alt+Down')):
            icon = QIcon.fromTheme(icon_name)
            if icon.isNull():
                button.setArrowType(arrow)
            else:
                button.setIcon(icon)
            button.setToolTip(('Move step up' if delta < 0 else 'Move step down') + ' (' + shortcut + ')')
            button.setAccessibleName('Move step up' if delta < 0 else 'Move step down')
            button.setShortcut(QKeySequence(shortcut))
            button.clicked.connect(lambda checked=False, d=delta: self.move(d))
            moves.addWidget(button)
        moves.addStretch(1)
        self.steps_row.addWidget(self.move_controls)
        steps_layout.addLayout(self.steps_row, 1)

        self.parameters = QGroupBox('Step settings')
        self.form = QFormLayout(self.parameters)
        self.form.setContentsMargins(8, 4, 8, 4)
        self.form.setVerticalSpacing(4)

        self.parameter_scroll = QScrollArea()
        self.parameter_scroll.setWidgetResizable(True)
        self.parameter_scroll.setFrameShape(QScrollArea.NoFrame)
        self.parameter_scroll.setMinimumHeight(96)
        self.parameter_scroll.setWidget(self.parameters)
        self.edit_splitter.addWidget(self.parameter_scroll)

        self.edit_splitter.setStretchFactor(0, 2)
        self.edit_splitter.setStretchFactor(1, 1)
        self.edit_splitter.setSizes([250, 140])

        self.workspace_tabs.addTab(operations_tab, 'Operations')

        # --- Tab 1: Parameters ---
        self.parameters_section = ParametersSectionWidget()
        self.parameters_section.add_requested.connect(self.add_parameter)
        self.parameters_section.edit_requested.connect(self.edit_parameter)
        self.parameters_section.remove_requested.connect(self.remove_parameter)
        self.parameters_section.move_requested.connect(self.move_parameter)
        self.workspace_tabs.addTab(self.parameters_section, 'Parameters')
        self.workspace_tabs.setTabToolTip(1, _PARAMETERS_TAB_TOOLTIP)

        # --- Tab 2: Preview ---
        preview_tab = QWidget()
        preview_layout = QVBoxLayout(preview_tab)
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.setSpacing(6)

        preview_controls = QHBoxLayout()
        preview_controls.setContentsMargins(0, 0, 0, 0)
        preview_controls.setSpacing(6)
        preview_controls.addWidget(QLabel('Example image:'))
        self.example_selector = QComboBox()
        self.example_selector.setMinimumWidth(160)
        self.example_selector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.example_selector.currentIndexChanged.connect(self.update_preview)
        preview_controls.addWidget(self.example_selector, 1)
        self.choose_example_button = QPushButton(
            QIcon.fromTheme('document-open'),
            'Choose images for preview…'
        )
        self.choose_example_button.clicked.connect(self.choose_examples)
        preview_controls.addWidget(self.choose_example_button)
        self.reset_examples = QPushButton(QIcon.fromTheme('edit-undo'), 'Reset to Selected Images')
        self.reset_examples.clicked.connect(lambda: self.set_examples(None))
        self.reset_examples.setVisible(False)
        preview_controls.addWidget(self.reset_examples)
        self.preview_settings_button = QPushButton(
            QIcon.fromTheme('configure'),
            'Set example values…',
        )
        self.preview_settings_button.setToolTip(
            'Try example answers to see what this Recipe will produce'
        )
        self.preview_settings_button.clicked.connect(self.open_preview_settings)
        self.preview_settings_button.hide()
        preview_controls.addWidget(self.preview_settings_button)
        preview_layout.addLayout(preview_controls)

        self.status = QLabel(); self.status.setWordWrap(True)
        self.status.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        preview_layout.addWidget(self.status)

        self.cancel_preview = QPushButton('Cancel preview'); self.cancel_preview.setVisible(False)
        self.cancel_preview.clicked.connect(self.stop_preview); preview_layout.addWidget(self.cancel_preview)
        self.table = RecipePreviewTree(self)

        self.preview_tools = QWidget()
        preview_tools_layout = QHBoxLayout(self.preview_tools)
        preview_tools_layout.setContentsMargins(0, 0, 0, 0)
        preview_tools_layout.addStretch(1)

        self.expand_preview = QPushButton('Expand all')
        self.collapse_preview = QPushButton('Collapse all')

        self.expand_preview.clicked.connect(self.table.expandAll)
        self.collapse_preview.clicked.connect(self.table.collapseAll)

        preview_tools_layout.addWidget(self.expand_preview)
        preview_tools_layout.addWidget(self.collapse_preview)

        preview_layout.addWidget(self.preview_tools)
        self.preview_tools.hide()

        preview_layout.addWidget(self.table, 1)

        # Single neutral guidance state when a valid parameterized Recipe awaits example values.
        self.preview_guidance_panel = QWidget()
        guidance_layout = QVBoxLayout(self.preview_guidance_panel)
        guidance_layout.setContentsMargins(16, 24, 16, 24)
        guidance_layout.setSpacing(10)
        guidance_layout.addStretch(1)
        self.preview_guidance_label = QLabel(
            'Set example values to preview this Recipe.'
        )
        self.preview_guidance_label.setTextFormat(Qt.PlainText)
        self.preview_guidance_label.setWordWrap(True)
        self.preview_guidance_label.setAlignment(Qt.AlignCenter)
        guidance_layout.addWidget(self.preview_guidance_label)
        self.preview_guidance_button = QPushButton(
            QIcon.fromTheme('configure'),
            'Set example values…',
        )
        self.preview_guidance_button.clicked.connect(self.open_preview_settings)
        guidance_layout.addWidget(self.preview_guidance_button, 0, Qt.AlignCenter)
        guidance_layout.addStretch(1)
        preview_layout.addWidget(self.preview_guidance_panel, 1)
        self.preview_guidance_panel.hide()

        from PySide6.QtCore import QSize

        self.empty_preview = QWidget()
        empty_layout = QVBoxLayout(self.empty_preview)

        empty_layout.addStretch(1)

        empty_title = QLabel('Choose an image to preview')
        empty_title.setAlignment(Qt.AlignCenter)
        empty_title.setWordWrap(True)

        font = empty_title.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 3)
        empty_title.setFont(font)

        empty_layout.addWidget(empty_title)
        empty_layout.addSpacing(12)

        preview_icon = QIcon.fromTheme('image-x-generic')

        if preview_icon.isNull():
            preview_icon = self.style().standardIcon(
                QStyle.StandardPixmap.SP_DialogOpenButton
            )

        self.empty_preview_button = QPushButton(
            preview_icon, 'Choose images…'
        )
        self.empty_preview_button.setIconSize(QSize(32, 32))
        self.empty_preview_button.setMinimumSize(200, 58)
        self.empty_preview_button.setCursor(Qt.PointingHandCursor)
        self.empty_preview_button.clicked.connect(self.choose_examples)

        empty_layout.addWidget(
            self.empty_preview_button,
            0, Qt.AlignCenter
        )

        empty_layout.addStretch(1)

        preview_layout.addWidget(self.empty_preview, 1)
        self.empty_preview.hide()
        self.warning_view=WarningView(); self.warning_view.hide(); preview_layout.addWidget(self.warning_view)
        self.workspace_tabs.addTab(preview_tab, 'Preview')
        self.workspace_tabs.setCurrentIndex(0)

        # 3. Shared Destination controls (below tabs, visible from every tab).
        self.destination_group = QGroupBox('Destination')
        self.destinations = QFormLayout(self.destination_group)
        self.destinations.setContentsMargins(8, 4, 8, 4)
        self.destinations.setVerticalSpacing(3)
        self.mode = QComboBox()
        for label, mode in [('Same directory as each original', 'beside'), ('Beside each original', 'subfolder'), ('One directory', 'directory')]:
            self.mode.addItem(label, mode)
        self.mode.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.mode.setMinimumWidth(240)
        mode_row = QWidget()
        mode_layout = QHBoxLayout(mode_row)
        mode_layout.setContentsMargins(0, 0, 0, 0)
        mode_layout.addWidget(self.mode)
        mode_layout.addStretch(1)

        self.folder = QLineEdit(); self.path = QLineEdit()
        self.subfolder_row = QWidget()
        subfolder_layout = QHBoxLayout(self.subfolder_row)
        subfolder_layout.setContentsMargins(0, 0, 0, 0)
        subfolder_layout.setSpacing(6)

        self.subfolder_mode = QComboBox(self.subfolder_row)
        for label, smode in (
            ('No subfolder', 'none'),
            ('Use a fixed name', 'fixed'),
            ('Ask when running', 'ask'),
            ('Use an advanced pattern', 'advanced'),
        ):
            self.subfolder_mode.addItem(label, smode)
        self.subfolder_mode.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        subfolder_layout.addWidget(self.subfolder_mode)

        self.folder_row = QWidget(self.subfolder_row)
        folder_layout = QHBoxLayout(self.folder_row); folder_layout.setContentsMargins(0, 0, 0, 0); folder_layout.setSpacing(4)
        folder_layout.addWidget(self.folder, 1)
        self.folder_insert_button = make_insert_variable_button(self.folder_row)
        self.folder_insert_menu = QMenu(self.folder_insert_button)
        self.folder_insert_menu.aboutToShow.connect(self._populate_subfolder_insert_menu)
        self.folder_insert_button.setMenu(self.folder_insert_menu)
        folder_layout.addWidget(self.folder_insert_button)
        subfolder_layout.addWidget(self.folder_row, 1)

        self.subfolder_ask_row = QWidget(self.subfolder_row)
        ask_sub_layout = QHBoxLayout(self.subfolder_ask_row)
        ask_sub_layout.setContentsMargins(0, 0, 0, 0)
        ask_sub_layout.setSpacing(4)
        self.subfolder_param_combo = QComboBox(self.subfolder_ask_row)
        self.subfolder_param_combo.setMinimumWidth(180)
        self.subfolder_edit_param_btn = QPushButton('Edit…', self.subfolder_ask_row)
        self.subfolder_edit_param_btn.setToolTip('Edit the subfolder question')
        self.subfolder_edit_param_btn.clicked.connect(self._edit_subfolder_question)
        ask_sub_layout.addWidget(self.subfolder_param_combo, 1)
        ask_sub_layout.addWidget(self.subfolder_edit_param_btn)
        subfolder_layout.addWidget(self.subfolder_ask_row, 1)
        self.subfolder_ask_row.hide()
        self._last_subfolder_mode = 'none'
        self._last_subfolder_param = None

        self.destination_summary = QLabel('')
        self.destination_summary.setTextFormat(Qt.PlainText)
        self.destination_summary.setWordWrap(True)
        self.destination_summary.hide()
        self.ask = QCheckBox('Ask for directory on every run')
        self.directory_row = QWidget()
        directory_layout = QHBoxLayout(self.directory_row); directory_layout.setContentsMargins(0, 0, 0, 0)
        directory_layout.addWidget(self.path)
        browse = QPushButton(QIcon.fromTheme('folder-open'), 'Choose…')
        browse.clicked.connect(self.browse); directory_layout.addWidget(browse)
        self.destinations.addRow('Directory:', mode_row)
        self.destinations.addRow('Subfolder:', self.subfolder_row)
        self.destinations.addRow('', self.destination_summary)
        self.destinations.addRow('', self.ask)
        self.destinations.addRow('Directory:', self.directory_row)
        controls.addWidget(self.destination_group)
        self.mode.currentIndexChanged.connect(self._on_directory_mode_changed)
        self.subfolder_mode.currentIndexChanged.connect(self._on_subfolder_mode_changed)
        self.subfolder_param_combo.currentIndexChanged.connect(self._on_subfolder_param_changed)
        for widget in (self.folder, self.path):
            widget.textEdited.connect(self.changed)
        self.ask.toggled.connect(self.changed)

        self.safety_notice = QLabel('Originals are not being changed. Outputs are being created as new files.')
        self.safety_notice.setWordWrap(True); self.safety_notice.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        controls.addWidget(self.safety_notice)

        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(300)
        self.timer.timeout.connect(self.update_preview)
        self.selector.currentIndexChanged.connect(lambda i: self.select_id(self.selector.itemData(i)))
        self.selector.activated.connect(lambda i: self.reselect_builtin(self.active_index))
        self.refresh_examples()
        self.refresh()

        # Remember the two-pane splitter widths separately from legacy three-pane keys.
        self.panel_settings = QSettings('KIMng', 'RecipeEditor')
        saved = self.panel_settings.value('two_pane_sizes')
        sizes = [275, 855]
        if isinstance(saved, (list, tuple)) and len(saved) == 2:
            try:
                candidate = [int(value) for value in saved]
                if all(value > 0 for value in candidate):
                    sizes = candidate
            except (TypeError, ValueError):
                pass
        self.splitter.setSizes(sizes)
        self.splitter.splitterMoved.connect(self.save_panel_sizes)

        stored_inner = self.panel_settings.value(
            'operations_vertical_splitter', [250, 140]
        )
        try:
            inner_sizes = [int(value) for value in stored_inner]
            if (
                len(inner_sizes) != 2
                or any(value <= 0 for value in inner_sizes)
            ):
                inner_sizes = [250, 140]
        except (TypeError, ValueError):
            inner_sizes = [250, 140]

        self.edit_splitter.setSizes(inner_sizes)
        self.edit_splitter.splitterMoved.connect(
            self.save_step_settings_sizes
        )

    def save_panel_sizes(self, *_):
        self.panel_settings.setValue(
            'two_pane_sizes', self.splitter.sizes()
        )

    def refresh_recipe_tree(self, *_):
        if not hasattr(self, 'recipe_tree'):
            return

        tree = self.recipe_tree
        query = self.recipe_search.text().casefold().split()
        previous = (
            self.recipe['id'] if self.recipe is not None else None
        )

        expanded = getattr(self, '_recipe_expanded', None)
        if expanded is None:
            from PySide6.QtCore import QSettings
            settings = QSettings('KIMng', 'RecipeEditor')
            expanded = settings.value('expanded_recipe_folders', None)
            if not isinstance(expanded, list):
                expanded = None

        tree.blockSignals(True)
        tree.clear()
        self.recipe_tree_items = {}

        folder_icon = QIcon.fromTheme('folder')
        if folder_icon.isNull():
            folder_icon = QApplication.style().standardIcon(
                QStyle.SP_DirIcon
            )

        recipe_icon = QIcon.fromTheme('text-x-generic')
        if recipe_icon.isNull():
            recipe_icon = QApplication.style().standardIcon(
                QStyle.SP_FileIcon
            )
        param_recipe_icon = QIcon.fromTheme('configure')
        if param_recipe_icon.isNull():
            param_recipe_icon = recipe_icon

        def group(title, parent=None, folder_id=None):
            item = QTreeWidgetItem([title])
            item.setIcon(0, folder_icon)
            item.setData(0, Qt.UserRole + 1, 'folder')
            item.setData(0, Qt.UserRole + 2, folder_id)

            # Only real destination folders accept Recipe drops.
            if folder_id is None:
                item.setFlags(
                    item.flags() & ~Qt.ItemIsDropEnabled
                )
            else:
                item.setFlags(
                    item.flags() | Qt.ItemIsDropEnabled
                )

            if parent is None:
                item.setFlags(
                    item.flags() & ~Qt.ItemIsSelectable
                )
            if parent is None:
                tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            return item

        def add_recipe(parent, recipe):
            item = QTreeWidgetItem([recipe['name']])
            parameterized = is_parameterized(recipe)
            item.setIcon(0, param_recipe_icon if parameterized else recipe_icon)
            item.setData(0, Qt.UserRole, recipe['id'])
            item.setData(0, Qt.UserRole + 1, 'recipe')

            movable = (
                any(user['id'] == recipe['id'] for user in self.users)
            )
            if movable:
                item.setFlags(
                    item.flags() | Qt.ItemIsDragEnabled
                )
            else:
                item.setFlags(
                    item.flags() & ~Qt.ItemIsDragEnabled
                )
            tip = (
                recipe['name'] +
                ('\n\n' + recipe['description']
                 if recipe['description'] else '')
            )
            if parameterized:
                tip += '\nAsks for settings when running.'
            item.setToolTip(0, tip)
            parent.addChild(item)
            self.recipe_tree_items[recipe['id']] = item

        def matches(recipe, folder_name=''):
            haystack = (
                recipe['name'] + ' ' +
                recipe['description'] + ' ' + folder_name
            ).casefold()
            return all(word in haystack for word in query)

        builtin = group('Built-ins')
        categories = {}

        for category in (
            'Common', 'Adventure', 'Asset Management'
        ):
            categories[category] = group(category, builtin)

        for recipe in sorted(
            self.shipped, key=lambda r: r['name'].casefold()
        ):
            category = builtin_category(recipe)
            if matches(recipe, 'Built-ins / ' + category):
                add_recipe(categories[category], recipe)

        mine = group('User')
        mine.setFlags(
            mine.flags() | Qt.ItemIsSelectable | Qt.ItemIsDropEnabled
        )
        mine.setData(0, Qt.UserRole + 2, '')
        unfiled = group('Unfiled', mine, '')

        folders = {}

        def add_folder(definition):
            folder_id = definition['id']
            if folder_id in folders:
                return folders[folder_id]

            parent_id = definition['parent_id']
            parent = mine

            if parent_id is not None:
                parent_definition = next(
                    f for f in self.folders if f['id'] == parent_id
                )
                parent = add_folder(parent_definition)

            item = group(definition['name'], parent, folder_id)
            folders[folder_id] = item
            return item

        for definition in sorted(
            self.folders,
            key=lambda f: folder_path(
                f['id'], self.folders
            ).casefold(),
        ):
            add_folder(definition)

        for recipe in sorted(
            self.users, key=lambda r: r['name'].casefold()
        ):
            folder_id = recipe.get('folder')
            parent = folders.get(folder_id, unfiled)
            label = (
                folder_path(folder_id, self.folders)
                if folder_id else 'Unfiled'
            )

            if matches(recipe, 'User / ' + label):
                add_recipe(parent, recipe)

                if recipe.get('dolphin_shortcut', False):
                    item = self.recipe_tree_items[recipe['id']]
                    item.setText(
                        0, self.recipe_tree_label(recipe)
                    )
                    item.setToolTip(
                        0, item.toolTip(0) + '\nShown in Dolphin menu'
                    )

        if query:
            def filter_branch(item):
                if item.data(0, Qt.UserRole + 1) == 'recipe':
                    return True
                visible = any([
                    filter_branch(item.child(i))
                    for i in range(item.childCount())
                ])
                item.setHidden(not visible)
                return visible

            filter_branch(builtin)
            filter_branch(mine)

        groups = {
            'built-in': builtin,
            'my-recipes': mine,
            'unfiled': unfiled,
        }

        groups.update({
            'category:' + category: item
            for category, item in categories.items()
        })

        groups.update({
            'folder:' + folder_id: item
            for folder_id, item in folders.items()
        })


        if expanded is None:
            expanded = list(groups)

        if query:
            for item in groups.values():
                item.setExpanded(True)
        else:
            for key, item in groups.items():
                item.setExpanded(key in expanded)

        self._recipe_tree_groups = groups
        self._recipe_expanded = list(expanded)

        if previous in self.recipe_tree_items:
            tree.setCurrentItem(
                self.recipe_tree_items[previous]
            )

        tree.blockSignals(False)
        self.update_tree_management()

    def save_recipe_tree_expansion(self, *_):
        if self.recipe_search.text().strip():
            return

        groups = getattr(self, '_recipe_tree_groups', {})
        expanded = [
            key for key, item in groups.items()
            if item.isExpanded()
        ]

        self._recipe_expanded = expanded
        from PySide6.QtCore import QSettings
        QSettings('KIMng', 'RecipeEditor').setValue(
            'expanded_recipe_folders', expanded
        )

    def show_recipe_tree_menu(self, position):
        item = self.recipe_tree.itemAt(position)
        if item is None:
            return

        kind = item.data(0, Qt.UserRole + 1)
        menu = QMenu(self.recipe_tree)

        if kind == 'recipe':
            recipe_id = item.data(0, Qt.UserRole)
            index = next(
                (i for i, recipe in enumerate(self.shipped + self.users)
                 if recipe['id'] == recipe_id), -1
            )
            if index < 0:
                return

            menu.addAction(
                'Duplicate to Edit',
                lambda: self.select_id(recipe_id) or self.duplicate()
            )

            if index >= len(self.shipped):
                menu.addSeparator()
                move_action = menu.addAction(
                    'Move to Folder…',
                    lambda rid=recipe_id:
                        self.choose_recipe_destination(rid)
                )
                move_action.setEnabled(True)
                menu.addAction(
                    'Rename…',
                    lambda: self.select_id(recipe_id) or self.rename()
                )
                menu.addAction(
                    'Delete…',
                    lambda: self.select_id(recipe_id) or self.remove()
                )

        elif kind == 'folder':
            folder_id = item.data(0, Qt.UserRole + 2)
            ancestor = item
            while ancestor.parent() is not None:
                ancestor = ancestor.parent()
            if ancestor is self.recipe_tree.topLevelItem(0):
                return

            menu.addAction(
                'New Recipe here',
                lambda: self.new_recipe_in_folder(folder_id)
            )

            menu.addAction(
                'New Folder…',
                lambda: self.create_folder_in(folder_id)
            )

            if folder_id not in (None, ''):
                menu.addSeparator()
                menu.addAction(
                    'Move folder…',
                    lambda: self.move_tree_folder(folder_id)
                )
                menu.addAction(
                    'Rename folder…',
                    lambda: self.rename_tree_folder(folder_id)
                )
                menu.addAction(
                    'Delete folder…',
                    lambda: self.delete_tree_folder(folder_id)
                )

        if not menu.isEmpty():
            menu.exec(
                self.recipe_tree.viewport().mapToGlobal(position)
            )

    def new_recipe_in_folder(self, folder_id):
        before = len(self.users)
        self.new()
        if len(self.users) == before:
            return
        target = folder_id
        if target == '':
            target = None
        self.library_folder.setCurrentIndex(
            self.library_folder.findData(target)
        )

    def rename_tree_folder(self, folder_id):
        folder = next(
            (item for item in self.folders if item['id'] == folder_id),
            None
        )
        if folder is None:
            return
        name, ok = QInputDialog.getText(
            self, 'Rename Recipe folder', 'New name',
            text=folder['name']
        )
        if ok:
            self.change_folders(
                lambda library: library.rename_folder(folder_id, name)
            )

    def delete_tree_folder(self, folder_id):
        folder = next(
            (item for item in self.folders if item['id'] == folder_id),
            None
        )
        if folder is None:
            return
        answer = QMessageBox.question(
            self, 'Delete Recipe folder',
            'Delete folder “' + folder['name'] + '”? '
            'All descendant folders will be removed. Their Recipes will move to Unfiled.',
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel
        )
        if answer == QMessageBox.Yes:
            self.change_folders(
                lambda library: library.delete_folder(folder_id)
            )

    def choose_recipe_destination(self, recipe_id=None):
        if recipe_id is None:
            if self.recipe is None:
                return
            recipe_id = self.recipe['id']

        recipe = next(
            (r for r in self.users if r['id'] == recipe_id),
            None
        )
        if recipe is None:
            return

        destinations = [
            ('User / Unfiled', None),
        ]
        destinations.extend(
            (folder_path(folder['id'], self.folders), folder['id'])
            for folder in sorted(
                self.folders,
                key=lambda f: f['name'].casefold()
            )
        )

        names = [name for name, _ in destinations]
        current = recipe.get('folder')

        current_index = next(
            (i for i, (_, folder_id) in enumerate(destinations)
             if folder_id == current),
            0
        )

        chosen, accepted = QInputDialog.getItem(
            self, 'Move Recipe', 'Destination folder',
            names, current_index, False
        )
        if not accepted:
            return

        destination = destinations[names.index(chosen)][1]
        self.move_recipe_to_folder(recipe_id, destination)

    def move_recipe_to_folder(self, recipe_id, folder_id):
        recipe = next(
            (r for r in self.users if r['id'] == recipe_id),
            None
        )
        if recipe is None:
            return False

        # Unfiled is represented by no folder assignment.
        if folder_id == '':
            folder_id = None

        if folder_id is not None and not any(
            folder['id'] == folder_id for folder in self.folders
        ):
            return False

        if recipe.get('folder') == folder_id:
            return True

        if self.recipe is None or self.recipe['id'] != recipe_id:
            self.select_id(recipe_id)
            if (
                self.recipe is None
                or self.recipe['id'] != recipe_id
            ):
                return False

        if recipe_id in self.draft_ids:
            for candidate in (recipe, self.recipe):
                if folder_id is None:
                    candidate.pop('folder', None)
                else:
                    candidate['folder'] = folder_id

            self.library_folder.blockSignals(True)
            self.library_folder.setCurrentIndex(
                self.library_folder.findData(folder_id)
            )
            self.library_folder.blockSignals(False)

            self.refresh_recipe_tree()
            self.update_modified()
            succeeded = True
        else:
            succeeded = self.change_folders(
                lambda library: library.move_recipe(
                    recipe_id, folder_id
                )
            )
        if not succeeded:
            return False

        # A search filter must not make the moved Recipe
        # appear to have vanished from the library.
        if self.recipe_search.text():
            self.recipe_search.clear()

        item = self.recipe_tree_items.get(recipe_id)
        if item is None:
            self.refresh_recipe_tree()
            item = self.recipe_tree_items.get(recipe_id)

        if item is not None:
            parent = item.parent()
            while parent is not None:
                parent.setHidden(False)
                parent.setExpanded(True)
                parent = parent.parent()

            self.recipe_tree.blockSignals(True)
            self.recipe_tree.setCurrentItem(item)
            self.recipe_tree.blockSignals(False)
            self.recipe_tree.scrollToItem(item)

        self.update_tree_management()
        return True

    def selected_tree_folder_id(self):
        item = self.recipe_tree.currentItem()
        if item is None:
            return None, False
        if item.data(0, Qt.UserRole + 1) != 'folder':
            return None, False

        return item.data(0, Qt.UserRole + 2), True

    def update_tree_management(self):
        if not hasattr(self, 'selected_recipe_button'):
            return

        folder_id, is_folder = self.selected_tree_folder_id()

        selected = self.recipe_tree.currentItem()
        selected_id = (
            selected.data(0, Qt.UserRole)
            if selected is not None
            and selected.data(0, Qt.UserRole + 1) == 'recipe'
            else None
        )
        self.export_recipe_button.setEnabled(
            selected_id is not None
            and selected_id not in self.draft_ids
        )

        duplicate = self.management_buttons['Duplicate to Edit']
        rename = self.management_buttons['Rename']
        delete = self.management_buttons['Delete']

        if is_folder:
            self.selected_recipe_button.setText('Selected Folder')
            duplicate.setVisible(False)
            self.move_recipe_button.setVisible(False)
            self.selected_recipe_separator.setVisible(False)

            editable_folder = folder_id not in (
                None, ''
            )

            rename.setText('Rename Folder')
            delete.setText('Delete Folder')
            rename.setEnabled(editable_folder)
            delete.setEnabled(editable_folder)
        else:
            self.selected_recipe_button.setText('Selected Recipe')
            duplicate.setVisible(True)
            duplicate.setEnabled(self.recipe is not None)
            self.move_recipe_button.setVisible(True)
            self.move_recipe_button.setEnabled(
                self.recipe is not None
                and not self.immutable
            )
            self.selected_recipe_separator.setVisible(True)

            rename.setText('Rename')
            delete.setText('Delete')

            editable = (
                self.recipe is not None
                and not self.immutable
            )
            rename.setEnabled(editable)
            delete.setEnabled(editable)

    def import_bundle_file(self):
        if not self.protect_unsaved():
            return

        if self.recipe is not None and self.is_dirty():
            self.select(self.active_index, force=True)

        filename, _ = QFileDialog.getOpenFileName(
            self, 'Import Recipe bundle', str(Path.home()),
            'KIMng Recipe bundles (*.json);;JSON files (*.json)'
        )
        if not filename:
            return

        try:
            bundle = read_recipe_bundle(filename)
            current = load_library()
            combined, added_ids = merge_recipe_bundle(
                current, bundle, self.shipped
            )

            new_folders = len(combined.folders) - len(current.folders)
            count = len(added_ids)

            summary = (
                f'Import {count} Recipes and '
                f'{new_folders} new folders?\n\n'
                'Existing Recipes will not be replaced. '
                'Conflicting Recipe names will receive an '
                'imported suffix. Imported folders retain their hierarchy. '
                'Imported Recipes will not create Dolphin shortcuts.'
            )

            if QMessageBox.question(
                self, 'Import Recipe bundle', summary,
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel
            ) != QMessageBox.Yes:
                return

            # Recheck against the current on-disk library before saving.
            # Nothing is persisted until the complete bundle is valid.
            current = load_library()
            combined, added_ids = merge_recipe_bundle(
                current, bundle, self.shipped
            )

            warning = save_library(combined)
            self.users, self.folders = (
                combined.recipes, combined.folders
            )

            self.recipe_search.clear()
            selected_id = added_ids[0]
            index = next(
                i for i, recipe in enumerate(
                    self.shipped + self.users
                ) if recipe['id'] == selected_id
            )
            self.refresh(index)

            if warning:
                self.error(warning)
            else:
                self.status.setText(
                    f'Imported {len(added_ids)} Recipes.'
                )

        except (OSError, RecipeError, ValueError) as exc:
            self.error(exc)

    def export_bundle_file(self):
        if not self.protect_unsaved():
            return

        if self.recipe is not None and self.is_dirty():
            self.select(self.active_index, force=True)

        try:
            library = load_library()
        except (OSError, RecipeError) as exc:
            self.error(exc)
            return

        if not library.recipes:
            self.error('There are no saved user Recipes to export.')
            return

        filename, _ = QFileDialog.getSaveFileName(
            self, 'Export Recipe bundle',
            str(Path.home() / 'KIMng-recipes-bundle.json'),
            'KIMng Recipe bundle (*.json)'
        )
        if not filename:
            return

        if not filename.lower().endswith('.json'):
            filename += '.json'

        try:
            write_recipe_bundle(library, filename)
            self.status.setText(
                f'Exported {len(library.recipes)} Recipes.'
            )
        except FileExistsError:
            self.error(
                'That bundle file already exists. '
                'Choose another filename.'
            )
        except (OSError, RecipeError, ValueError) as exc:
            self.error(exc)

    def import_recipe_file(self):
        if not self.protect_unsaved():
            return

        folder_id, is_folder = self.selected_tree_folder_id()
        target = folder_id if is_folder else None
        if target == '':
            target = None

        filename, _ = QFileDialog.getOpenFileName(
            self, 'Import Recipe', str(Path.home()),
            'KIMng Recipes (*.json);;JSON files (*.json)'
        )
        if not filename:
            return

        try:
            imported = read_portable_recipe(filename)
            existing = {
                recipe['name'].casefold()
                for recipe in self.shipped + self.users
            }

            if imported['name'].casefold() in existing:
                suggestion = imported['name'] + ' (imported)'
                name, accepted = QInputDialog.getText(
                    self, 'Recipe name already exists',
                    'Name for imported Recipe', text=suggestion
                )
                if not accepted:
                    return
                imported['name'] = name

            # Never import another machine's identity or overwrite
            # a user Recipe, even when the names are different.
            imported['id'] = 'user-' + uuid.uuid4().hex
            imported['dolphin_shortcut'] = False

            if target is not None:
                imported['folder'] = target

            imported = validate_authored(imported)

            users = [
                recipe for recipe in self.users
                if recipe['id'] not in self.draft_ids
            ]
            library = RecipeLibrary(
                copy.deepcopy(users + [imported]),
                copy.deepcopy(self.folders),
            )
            warning = save_library(library)

            self.users, self.folders = (
                library.recipes, library.folders
            )
            self.recipe_search.clear()
            selected_index = len(self.shipped) + len(self.users) - 1
            self.refresh(selected_index)

            if warning:
                self.error(warning)
            else:
                self.status.setText('Recipe imported.')

        except (OSError, RecipeError, ValueError) as exc:
            self.error(exc)

    def export_recipe_file(self):
        selected = self.recipe_tree.currentItem()
        if selected is None:
            return

        recipe_id = selected.data(0, Qt.UserRole)
        if not isinstance(recipe_id, str):
            return

        if recipe_id in self.draft_ids:
            self.error('Save this Recipe before exporting it.')
            return

        # An active Recipe may contain unsaved edits. Respect the
        # established Save/Discard/Cancel decision.
        if (
            self.recipe is not None
            and self.recipe['id'] == recipe_id
            and not self.protect_unsaved()
        ):
            return

        saved = next(
            (
                recipe for recipe in self.shipped + self.users
                if recipe['id'] == recipe_id
            ),
            None
        )
        if saved is None:
            return

        # Human-readable, stable, per-Recipe export filename.
        safe_name = (
            re.sub(r'[^\w.-]+', '-', saved['name'], flags=re.UNICODE)
            .strip('.-') or 'recipe'
        )
        safe_name += '-' + saved['id'].removeprefix('user-')[:8]

        filename, _ = QFileDialog.getSaveFileName(
            self, 'Export Recipe',
            str(Path.home() / (safe_name + '.json')),
            'KIMng Recipe (*.json)'
        )
        if not filename:
            return

        if not filename.lower().endswith('.json'):
            filename += '.json'

        try:
            write_portable_recipe(saved, filename)
            self.status.setText('Recipe exported.')
        except FileExistsError:
            self.error(
                'That file already exists. Choose another filename.'
            )
        except (OSError, RecipeError, ValueError) as exc:
            self.error(exc)

    def create_recipe_from_tree(self):
        folder_id, is_folder = self.selected_tree_folder_id()
        if is_folder:
            self.new_recipe_in_folder(folder_id)
        else:
            self.new()

    def rename_selected_tree_item(self):
        folder_id, is_folder = self.selected_tree_folder_id()
        if is_folder:
            if folder_id not in (None, ''):
                self.rename_tree_folder(folder_id)
        else:
            self.rename()

    def delete_selected_tree_item(self):
        folder_id, is_folder = self.selected_tree_folder_id()
        if is_folder:
            if folder_id not in (None, ''):
                self.delete_tree_folder(folder_id)
        else:
            self.remove()

    def recipe_tree_selection_changed(self, current, previous):
        if current is None:
            return

        recipe_id = current.data(0, Qt.UserRole)
        if recipe_id is None:
            self.update_tree_management()
            return

        if self.recipe is not None and (
            recipe_id == self.recipe['id']
        ):
            self.update_tree_management()
            return

        self.select_id(recipe_id)

        # Restore the visible selection if Save/Discard/Cancel
        # prevented switching away from the current Recipe.
        active = (
            self.recipe['id'] if self.recipe is not None else None
        )
        item = self.recipe_tree_items.get(active)
        if item is not None and item is not current:
            self.recipe_tree.blockSignals(True)
            self.recipe_tree.setCurrentItem(item)
            self.recipe_tree.blockSignals(False)
        self.update_tree_management()

    def save_step_settings_sizes(self, *_):
        self.panel_settings.setValue(
            'operations_vertical_splitter',
            self.edit_splitter.sizes()
        )

    def refresh(self, selected=0):
        self.selector.blockSignals(True); self.selector.clear()
        recipes = self.shipped + self.users
        for folder_id, name, grouped in library_groups(RecipeLibrary(self.users, self.folders), self.shipped):
            for r in grouped:
                self.selector.addItem(name + ' / ' + r['name'], r['id'])
        self.selector.setCurrentIndex(
            self.selector.findData(recipes[selected]['id'])
        )
        self.selector.blockSignals(False)
        self.select(selected, force=True)
        self.refresh_recipe_tree()

    def select_id(self, recipe_id):
        index = next((i for i, r in enumerate(self.shipped + self.users) if r['id'] == recipe_id), -1)
        if index >= 0: self.select(index)

    def select(self, index, force=False):
        recipes = self.shipped + self.users
        if not 0 <= index < len(recipes):
            return
        if not force and index != self.active_index and not self.protect_unsaved():
            self.selector.blockSignals(True)
            self.selector.setCurrentIndex(self.selector.findData(self.recipe['id']))
            self.selector.blockSignals(False)
            return
        self.loading = True
        self.active_index = index
        self.recipe = copy.deepcopy(recipes[index])
        self.baseline = copy.deepcopy(self.recipe)
        self.media_handler = handler(self.recipe['media'])
        self.definitions = self.media_handler.operation_definitions()
        self.immutable = index < len(self.shipped)
        is_dev = self.recipe['id'] in self.dev_draft_ids
        if self.immutable:
            self.recipe_guidance.setText('Built-in Recipe. Duplicate to create an editable copy.')
            self.recipe_guidance.setVisible(True)
        elif is_dev:
            self.recipe_guidance.setText(
                'Temporary development draft. Preview or run it through Settings and '
                'Review Changes; saving to the live library is disabled.'
            )
            self.recipe_guidance.setVisible(True)
        else:
            self.recipe_guidance.setVisible(False)
        self.name.setText(self.recipe['name']); self.name.setReadOnly(self.immutable)
        self.description.setPlainText(self.recipe['description'])
        self.description.setReadOnly(self.immutable)
        self.library_folder.blockSignals(True); self.library_folder.clear(); self.library_folder.addItem('Unfiled', None)
        for folder in sorted(
            self.folders,
            key=lambda f: folder_path(
                f['id'], self.folders
            ).casefold(),
        ):
            self.library_folder.addItem(
                folder_path(folder['id'], self.folders), folder['id']
            )
        self.library_folder.setCurrentIndex(self.library_folder.findData(self.recipe.get('folder')))
        self.library_folder.setEnabled(not self.immutable); self.library_folder.blockSignals(False)

        self.shortcut_checkbox.blockSignals(True)
        self.shortcut_checkbox.setChecked(
            self.recipe.get('dolphin_shortcut', False)
        )
        self.shortcut_checkbox.setEnabled(not self.immutable)
        self.shortcut_checkbox.setVisible(not self.immutable)
        self.shortcut_checkbox.blockSignals(False)

        dest = self.recipe['destination']
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(self.mode.findData(dest['mode']))
        self.mode.blockSignals(False)
        self.folder.setText(dest.get('folder', 'Recipes'))
        self.path.setText(dest.get('path', '')); self.ask.setChecked(dest.get('ask', False))
        self.destination_group.setEnabled(not self.immutable)
        self.operation.setEnabled(not self.immutable)
        for button in self.step_buttons:
            button.setEnabled(not self.immutable)
        for label in ('Rename', 'Delete', 'Save'):
            self.management_buttons[label].setEnabled(not self.immutable)
        self._preview_step_active = {}
        self._sync_subfolder_widgets_from_recipe()
        self.update_destination_controls()
        self._refresh_parameters_section()
        self.reload_steps()
        self.loading = False
        self.update_modified()
        if hasattr(self, 'recipe_tree_items'):
            item = self.recipe_tree_items.get(self.recipe['id'])
            if item is not None:
                self.recipe_tree.blockSignals(True)
                self.recipe_tree.setCurrentItem(item)
                self.recipe_tree.blockSignals(False)
        self.update_preview()
        self.update_tree_management()

    def reselect_builtin(self, index):
        if self.immutable and index == self.active_index and self.is_dirty():
            self.select(index, force=True)

    def comparable(self, recipe):
        state = copy.deepcopy(recipe)
        if not state.get('parameters'):
            state.pop('parameters', None)
        for step in state['steps']:
            step.setdefault('enabled', True)
            if not step.get('bindings'):
                step.pop('bindings', None)
            if step.get('enabled_when') is None:
                step.pop('enabled_when', None)
            for key, spec in self.definitions[step['op']]['parameters'].items():
                step.setdefault(key, copy.deepcopy(spec['default']))
        return state

    def is_dirty(self):
        if self.recipe is None:
            return False
        if self.recipe['id'] in self.dev_draft_ids:
            return self.comparable(self.recipe) != self.comparable(self.baseline)
        return self.recipe['id'] in self.draft_ids or self.comparable(self.recipe) != self.comparable(self.baseline)

    @staticmethod
    def recipe_tree_label(recipe, dirty=False):
        prefix = '★ ' if recipe.get('dolphin_shortcut') else ''
        suffix = ' *' if dirty else ''
        return prefix + recipe['name'] + suffix

    def update_modified(self):
        dirty = self.is_dirty()
        try:
            label = recipe_title(self.recipe, self.folders)
        except RecipeError:
            label = self.recipe.get('name', '')
        if self.immutable:
            label += ' [modified for this run]' if dirty else ' [built-in]'
        elif dirty:
            label += ' *'
        self.selector.setItemText(
            self.selector.findData(self.recipe['id']), label
        )
        if hasattr(self, 'recipe_tree_items'):
            item = self.recipe_tree_items.get(self.recipe['id'])
            if item is not None:
                display_recipe = dict(self.recipe)

                display_recipe['dolphin_shortcut'] = bool(
                    self.recipe['id'] not in self.draft_ids
                    and self.baseline.get('dolphin_shortcut', False)
                )

                item.setText(
                    0,
                    self.recipe_tree_label(
                        display_recipe,
                        dirty and not self.immutable
                    )
                )
        parameterized = is_parameterized(self.recipe)
        is_dev = self.recipe['id'] in self.dev_draft_ids
        if hasattr(self, 'preview_settings_button'):
            self.preview_settings_button.setVisible(parameterized)
        if not self.immutable:
            if is_dev:
                self.shortcut_checkbox.blockSignals(True)
                self.shortcut_checkbox.setChecked(False)
                self.shortcut_checkbox.setEnabled(False)
                self.shortcut_checkbox.setToolTip(
                    'Dolphin shortcuts are disabled for temporary development drafts.'
                )
                self.shortcut_checkbox.blockSignals(False)
            else:
                self.shortcut_checkbox.setEnabled(True)
                self.shortcut_checkbox.setToolTip(
                    'When enabled and saved, this recipe appears under '
                    'KIMng > Recipes when you right-click selected images '
                    'in Dolphin.'
                )
        can_save = not self.immutable and dirty and not is_dev
        self.management_buttons['Save'].setEnabled(can_save)
        self.management_buttons['Save'].setToolTip(
            'Saving temporary development drafts is disabled.'
            if is_dev and not self.immutable
            else 'Save changes to this Recipe'
        )
        self.reset_builtin.setVisible(self.immutable)
        self.reset_builtin.setEnabled(self.immutable and dirty)
        self.update_move_buttons()

    def update_move_buttons(self):
        row = self.steps.currentRow()
        self.move_up.setEnabled(not self.immutable and row > 0)
        self.move_down.setEnabled(not self.immutable and 0 <= row < self.steps.count() - 1)

    def reset_builtin_defaults(self):
        if self.immutable:
            self.select(self.active_index, force=True)

    def _template_uses_summary(self, template_text, *, allow_source_tokens):
        """Return a human-readable summary of template variables when parameters are referenced."""
        if not isinstance(template_text, str) or not has_parameter_references(template_text):
            return ''
        try:
            tokens = parse_template(template_text, allow_source_tokens=allow_source_tokens)
        except RecipeError:
            return ''
        params_by_id = (
            {p['id']: p for p in self.recipe.get('parameters', ())}
            if self.recipe is not None
            else {}
        )
        source_labels = {
            'filename': 'Original filename',
            'date': 'Image capture date',
            'index': 'Sequence number',
        }
        names = []
        seen = set()
        for kind, value in tokens:
            if kind == 'param':
                label = params_by_id.get(value, {}).get('label', value)
            elif kind == 'source':
                label = source_labels.get(value, value)
            else:
                continue
            if label not in seen:
                seen.add(label)
                names.append(label)
        return ', '.join(names)

    def _step_display_text(self, step):
        op = step.get('op', '')
        label = _display_op_label(op, self.definitions)
        bindings = step.get('bindings') or {}
        params_by_id = (
            {p['id']: p for p in self.recipe.get('parameters', ())}
            if self.recipe is not None
            else {}
        )

        def param_label(pid):
            return params_by_id.get(pid, {}).get('label', pid)

        text = None
        if bindings:
            if op == 'image.resize':
                w_pid = bindings.get('max_width')
                h_pid = bindings.get('max_height')
                if w_pid and w_pid == h_pid:
                    text = f'{label}: {param_label(w_pid)}'
                else:
                    w_txt = param_label(w_pid) if w_pid else str(step.get('max_width', ''))
                    h_txt = param_label(h_pid) if h_pid else str(step.get('max_height', ''))
                    text = f'{label}: {w_txt} × {h_txt}'
            elif op == 'image.convert':
                fmt = step.get('format', '')
                fmt_txt = param_label(bindings['format']) if 'format' in bindings else str(fmt).upper()
                if 'quality' in bindings:
                    text = f'{label}: {fmt_txt}, ask for quality'
                elif 'format' in bindings:
                    text = f'{label}: {fmt_txt}'
            elif op == 'image.resize_percent' and 'percent' in bindings:
                text = f"{label}: {param_label(bindings['percent'])}"
            elif op == 'image.compress' and 'preset' in bindings:
                text = f"{label}: {param_label(bindings['preset'])}"
            elif op == 'image.color' and 'mode' in bindings:
                text = f"{label}: {param_label(bindings['mode'])}"
            if text is None:
                bound_labels = list(dict.fromkeys(param_label(pid) for pid in bindings.values()))
                text = f"{label}: uses {', '.join(bound_labels)}"
        elif op == 'file.rename_output' and has_parameter_references(step.get('pattern', '')):
            try:
                tokens = parse_template(step.get('pattern', ''), allow_source_tokens=True)
            except RecipeError:
                tokens = ()
            pids = list(dict.fromkeys(val for kind, val in tokens if kind == 'param'))
            if pids:
                text = f"{label}: uses {', '.join(param_label(pid) for pid in pids)}"

        if text is None:
            try:
                text = self.media_handler.step_label(step)
            except (OSError, RecipeError):
                text = label
            if op == 'image.auto_orient' and text == 'Auto-Orient':
                text = 'Auto-orient'
            elif op == 'metadata.strip_gps' and text == 'Remove GPS Location':
                text = 'Remove GPS metadata'

        if step.get('enabled', True) is not False and step.get('enabled_when') is not None:
            text += ' (conditional)'
        return text

    def style_step_item(self, item, enabled, step=None, row=None):
        # Unchecked steps remain selectable, and must be readable.
        item.setForeground(self.palette().brush(QPalette.Active, QPalette.Text))
        font = item.font()
        font.setItalic(not enabled)
        item.setFont(font)
        if enabled and step is not None and step.get('enabled_when') is not None:
            params_by_id = {p['id']: p for p in self.recipe.get('parameters', ())}
            prose = summarize_condition(step['enabled_when'], params_by_id)
            preview_state = self._preview_step_active.get(row)
            if preview_state is True:
                p_line = 'Current preview: active'
            elif preview_state is False:
                p_line = 'Current preview: inactive'
            else:
                p_line = 'Current preview: waiting for example values'
            item.setToolTip(f'Run when {prose}.\n{p_line}')
        else:
            item.setToolTip('Enabled in recipe' if enabled else 'Disabled: check this step to include it in the recipe')

    def _refresh_step_tooltips(self):
        if self.recipe is None:
            return
        self.steps.blockSignals(True)
        for idx, step in enumerate(self.recipe['steps']):
            item = self.steps.item(idx)
            if item is not None:
                item.setText(self._step_display_text(step))
                self.style_step_item(item, step.get('enabled', True), step=step, row=idx)
        self.steps.blockSignals(False)

    def reload_steps(self, row=0):
        self.steps.blockSignals(True)
        self.steps.clear()
        for idx, step in enumerate(self.recipe['steps']):
            item = QListWidgetItem(self._step_display_text(step))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if step.get('enabled', True) else Qt.Unchecked)
            self.style_step_item(item, step.get('enabled', True), step=step, row=idx)
            self.steps.addItem(item)
        self.steps.blockSignals(False)
        self.step_count.setText(
            f"{len(self.recipe['steps'])} operations"
        )
        self.steps.setCurrentRow(min(row, len(self.recipe['steps']) - 1))
        if not self.recipe['steps']:
            self.edit_step(-1)

    def toggle_step(self, item):
        row = self.steps.row(item)
        enabled = item.checkState() == Qt.Checked
        step = self.recipe['steps'][row]
        step['enabled'] = enabled
        self.steps.blockSignals(True)
        item.setText(self._step_display_text(step))
        self.style_step_item(item, enabled, step=step, row=row)
        self.steps.blockSignals(False)
        if row == self.steps.currentRow():
            self.edit_step(row)
        self.update_modified()
        self.timer.start()

    @staticmethod
    def _simple_boolean_condition_pid(step, params_by_id):
        """Return parameter ID when enabled_when is a simple boolean 'is Yes' check."""
        if step.get('enabled', True) is False:
            return None
        cond = step.get('enabled_when')
        if not isinstance(cond, dict) or set(cond.keys()) != {'param', 'equals'}:
            return None
        if cond.get('equals') is not True:
            return None
        pid = cond.get('param')
        param = params_by_id.get(pid)
        if param and param.get('type') == 'boolean':
            return pid
        return None

    def edit_step(self, row):
        self.update_move_buttons()
        self.parameter_widgets = {}
        self.field_row_widgets = {}
        self.field_source_buttons = {}
        self.filename_example = None
        self.pattern_summary = None
        self.pattern_insert_button = None
        self.step_activation_control = None
        self.step_run_mode_combo = None
        self.step_run_question_combo = None
        self.step_run_default_combo = None
        self.shared_resize_check = None
        self.shared_resize_note = None
        self.parameter_resets = {}
        self.parameter_modes = {}
        self.step_defaults_button = None
        while self.form.rowCount():
            self.form.removeRow(0)
        if self.recipe is None or not 0 <= row < len(self.recipe['steps']):
            return
        step = self.recipe['steps'][row]
        definition = self.definitions[step['op']]
        params_by_id = {p['id']: p for p in self.recipe.get('parameters', ())}
        bound_fields = step.get('bindings') or {}
        op_display = _display_op_label(step['op'], self.definitions)
        self.parameters.setTitle('Step settings: ' + op_display)

        if not self.immutable or step.get('enabled_when') is not None:
            p_state = self._preview_step_active.get(row)
            p_suffix = (
                ' (active in preview)' if p_state is True
                else ' (inactive in preview)' if p_state is False
                else ''
            )
            simple_pid = self._simple_boolean_condition_pid(step, params_by_id)
            if self.immutable:
                if step.get('enabled', True) is False:
                    act_text = 'Never'
                elif step.get('enabled_when') is not None:
                    prose = summarize_condition(step['enabled_when'], params_by_id)
                    act_text = f'Run when {prose}{p_suffix}.'
                else:
                    act_text = 'Always'
                act_label = QLabel(act_text)
                act_label.setTextFormat(Qt.PlainText)
                act_label.setWordWrap(True)
                self.form.addRow('Run this operation:', act_label)
            else:
                act_container = QWidget()
                act_vbox = QVBoxLayout(act_container)
                act_vbox.setContentsMargins(0, 0, 0, 0)
                act_vbox.setSpacing(3)

                act_top = QHBoxLayout()
                act_top.setContentsMargins(0, 0, 0, 0)
                act_top.setSpacing(6)

                mode_combo = QComboBox(act_container)
                mode_combo.addItem('Always', 'always')
                mode_combo.addItem('Never', 'never')
                mode_combo.addItem('Ask when running', 'ask')
                mode_combo.addItem('Only when a condition is met…', 'condition')
                mode_combo.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                if step.get('enabled', True) is False:
                    cur_mode = 'never'
                elif simple_pid is not None:
                    cur_mode = 'ask'
                elif step.get('enabled_when') is not None:
                    cur_mode = 'condition'
                else:
                    cur_mode = 'always'
                mode_combo.setCurrentIndex(mode_combo.findData(cur_mode))
                mode_combo.currentIndexChanged.connect(
                    lambda _i, r=row, c=mode_combo: self._on_step_run_mode_changed(r, c.currentData())
                )
                self.step_run_mode_combo = mode_combo
                self.step_activation_control = mode_combo
                act_top.addWidget(mode_combo)

                if cur_mode == 'ask' and simple_pid is not None:
                    bool_params = [
                        p for p in self.recipe.get('parameters', ())
                        if p.get('type') == 'boolean'
                    ]
                    q_combo = QComboBox(act_container)
                    for bp in bool_params:
                        q_combo.addItem(bp['label'], bp['id'])
                    q_combo.addItem('New question…', '__new__')
                    q_combo.setCurrentIndex(q_combo.findData(simple_pid))
                    q_combo.currentIndexChanged.connect(
                        lambda _i, r=row, c=q_combo: self._on_step_run_question_changed(r, c.currentData())
                    )
                    self.step_run_question_combo = q_combo
                    act_top.addWidget(q_combo, 1)

                    bp = params_by_id[simple_pid]
                    if 'default_source' not in bp:
                        d_combo = QComboBox(act_container)
                        d_combo.addItem('Default: Yes', True)
                        d_combo.addItem('Default: No', False)
                        d_combo.addItem('Ask each time', None)
                        d_val = bp.get('default', None) if 'default' in bp else None
                        d_combo.setCurrentIndex(d_combo.findData(d_val))
                        d_combo.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                        d_combo.currentIndexChanged.connect(
                            lambda _i, pid=simple_pid, c=d_combo: self._on_step_run_default_changed(pid, c.currentData())
                        )
                        self.step_run_default_combo = d_combo
                        act_top.addWidget(d_combo)

                    edit_q = QPushButton('Edit…', act_container)
                    edit_q.setToolTip('Edit this question')
                    edit_q.clicked.connect(lambda checked=False, pid=simple_pid: self.edit_parameter(pid))
                    act_top.addWidget(edit_q)
                elif cur_mode == 'condition':
                    edit_c = QPushButton('Edit condition…', act_container)
                    edit_c.clicked.connect(lambda checked=False, r=row: self.configure_step_activation(r))
                    act_top.addWidget(edit_c)
                    act_top.addStretch(1)
                else:
                    act_top.addStretch(1)

                act_vbox.addLayout(act_top)

                if step.get('enabled', True) is not False and step.get('enabled_when') is not None:
                    prose = summarize_condition(step['enabled_when'], params_by_id)
                    cond_summary = QLabel(f'Run when {prose}{p_suffix}.', act_container)
                    cond_summary.setTextFormat(Qt.PlainText)
                    cond_summary.setWordWrap(True)
                    act_vbox.addWidget(cond_summary)

                self.form.addRow('Run this operation:', act_container)

        if definition.get('description'):
            hint = QLabel(definition['description'])
            hint.setWordWrap(True)
            self.form.addRow(hint)
        definitions = definition['parameters']
        if (
            not definitions
            and definition.get('editor') != 'image_ops'
            and not definition.get('description')
        ):
            self.form.addRow(
                QLabel('This operation has no additional settings.')
            )
        if definition.get('editor') == 'image_ops':
            from kim_image_ops import step_details
            for title, value in step_details(step):
                label = QLabel(value); label.setTextFormat(Qt.PlainText); label.setWordWrap(True)
                self.form.addRow(title, label)
            if bound_fields:
                bound_summary = ', '.join(
                    f"{definitions.get(f, {}).get('label', f)} → {params_by_id.get(pid, {}).get('label', pid)}"
                    for f, pid in bound_fields.items()
                )
                b_lbl = QLabel(bound_summary)
                b_lbl.setTextFormat(Qt.PlainText)
                b_lbl.setWordWrap(True)
                self.form.addRow('Run-time questions', b_lbl)
            action_row = QWidget()
            action_layout = QHBoxLayout(action_row)
            action_layout.setContentsMargins(0, 0, 0, 0)
            action_layout.setSpacing(6)
            configure = QPushButton('Configure with image preview…')
            configure.clicked.connect(lambda checked=False, r=row: self.configure_image_operation(r))
            action_layout.addWidget(configure, 1)
            if not self.immutable:
                bind_btn = QToolButton()
                bind_btn.setText('Field questions')
                bind_btn.setPopupMode(QToolButton.InstantPopup)
                bind_menu = QMenu(bind_btn)
                bind_menu.aboutToShow.connect(
                    lambda r=row, m=bind_menu: self._populate_image_ops_binding_menu(r, m)
                )
                bind_btn.setMenu(bind_menu)
                action_layout.addWidget(bind_btn)
            self.form.addRow(action_row)
            reset = QPushButton('Reset step defaults'); reset.clicked.connect(self.reset_step_defaults)
            self.form.addRow(reset)
            return
        if step['op'] == 'image.resize':
            w_pid = bound_fields.get('max_width')
            h_pid = bound_fields.get('max_height')
            is_shared = bool(w_pid and w_pid == h_pid)
            has_conflict = (bool(w_pid) != bool(h_pid)) or (bool(w_pid) and bool(h_pid) and w_pid != h_pid)

            shared_box = QWidget()
            shared_v = QVBoxLayout(shared_box)
            shared_v.setContentsMargins(0, 0, 0, 0)
            shared_v.setSpacing(2)

            shared_top = QHBoxLayout()
            shared_top.setContentsMargins(0, 0, 0, 0)
            shared_top.setSpacing(6)
            shared_cb = QCheckBox('Ask for the maximum image dimension when running', shared_box)
            shared_cb.setChecked(is_shared)
            shared_cb.setEnabled(not self.immutable and not has_conflict)
            shared_cb.toggled.connect(
                lambda checked, r=row: self._toggle_shared_resize(r, checked)
            )
            self.shared_resize_check = shared_cb
            shared_top.addWidget(shared_cb)
            if is_shared and not self.immutable:
                edit_shared = QPushButton('Edit…', shared_box)
                edit_shared.setToolTip('Edit the maximum image dimension question')
                edit_shared.clicked.connect(lambda checked=False, pid=w_pid: self.edit_parameter(pid))
                shared_top.addWidget(edit_shared)
            shared_top.addStretch(1)
            shared_v.addLayout(shared_top)

            if has_conflict:
                note = QLabel(
                    'Maximum width and height currently use separate settings. '
                    'Reset them to fixed values to use one shared dimension.',
                    shared_box,
                )
                note.setTextFormat(Qt.PlainText)
                note.setWordWrap(True)
                self.shared_resize_note = note
                shared_v.addWidget(note)
            elif is_shared:
                sp = params_by_id.get(w_pid, {})
                d_txt = f"default: {sp['default']} px" if 'default' in sp else 'ask each time'
                note = QLabel(
                    f"Controls both maximum width and maximum height ({sp.get('label', w_pid)}, {d_txt}).",
                    shared_box,
                )
                note.setTextFormat(Qt.PlainText)
                note.setWordWrap(True)
                self.shared_resize_note = note
                shared_v.addWidget(note)

            self.form.addRow('', shared_box)

            sizes = (300,600,800,1024,1280,1400,1600,1920,2048,2560,3440,3840)
            presets = QComboBox(); presets.addItem('Custom bounds',None)
            for size in sizes: presets.addItem(f'{size} × {size}',size)
            presets.setCurrentIndex(presets.findData(step['max_width']) if step['max_width'] == step['max_height'] and step['max_width'] in sizes else 0)
            presets.currentIndexChanged.connect(lambda i,r=row,w=presets:self.resize_preset(r,w.itemData(i)))
            if 'max_width' in bound_fields or 'max_height' in bound_fields:
                presets.setEnabled(False)
                presets.setToolTip('Turn off run-time dimension questions to use fixed size presets.')
            self.form.addRow('Common sizes',presets)
        for key, spec in definitions.items():
            if step['op'] == 'metadata.set_capture' and key in ('timezone','fields'): continue
            try:
                value = self.media_handler.parameter_value(step, key)
            except (OSError, RecipeError) as exc:
                value = spec['default'] if spec['type'] in ('integer','number') else ''
                self.status.setText(str(exc))
            if step['op']=='file.rename_output' and key=='pattern' and not has_parameter_references(value):
                value = display_output_pattern(value)
            if key == 'degrees' and step['op'] == 'image.rotate':
                widget = RotationInput(value)
                widget.changed.connect(lambda v,k=key,r=row:self.parameter(r,k,v))
            elif spec['type'] == 'capture_datetime':
                widget = CaptureDateInput(value)
                widget.changed.connect(lambda v,k=key,r=row:self.parameter(r,k,v))
            elif key == 'seconds' and step['op'] == 'metadata.shift_capture':
                widget = CaptureAdjustment(value)
                widget.changed.connect(lambda v,k=key,r=row:self.parameter(r,k,v))
            elif 'choices' in spec:
                widget = QComboBox()
                for choice in spec['choices']:
                    labels = {'specific':'Enter a specific date/time','embedded':'Use embedded image capture date if available' if key == 'mode' else 'Keep embedded timezone (or unknown)',
                              'file_mtime':'Use source file modification time', 'unknown':'Unknown camera timezone (no offset)',
                              '':'Choose timezone…','UTC':'UTC (+00:00)','custom':'Enter ±HH:MM offset',
                              'capture':'Image capture date only','all':'Image capture, creation and modification dates'} if step['op'] == 'metadata.set_capture' or key == 'fields' else {}
                    widget.addItem(labels.get(choice,str(choice).replace('_',' ').capitalize()), choice)
                if key == 'timezone':
                    widget.setEditable(True)
                    if widget.findData(value) < 0: widget.addItem(value,value)
                widget.setCurrentIndex(widget.findData(value))
                if key == 'timezone':
                    widget.currentTextChanged.connect(lambda v,k=key,r=row,w=widget:self.parameter(r,k,w.itemData(w.findText(v)) if w.findText(v) >= 0 else v))
                else: widget.currentIndexChanged.connect(lambda i, k=key, r=row, w=widget: self.parameter(r, k, w.itemData(i)))
            elif spec['type'] == 'boolean':
                widget = QCheckBox(); widget.setChecked(value)
                widget.toggled.connect(lambda v, k=key, r=row: self.parameter(r, k, v))
            elif spec['type'] == 'integer':
                widget = QSpinBox(); widget.setRange(spec['minimum'], spec['maximum'])
                widget.setValue(value)
                widget.valueChanged.connect(lambda v, k=key, r=row: self.parameter(r, k, v))
            elif spec['type'] == 'number':
                widget = QDoubleSpinBox(); widget.setRange(spec['minimum'],spec['maximum']); widget.setDecimals(3); widget.setValue(value)
                widget.valueChanged.connect(lambda v,k=key,r=row:self.parameter(r,k,v))
            else:
                widget = QLineEdit(value)
                widget.setCursorPosition(0)
                widget.textEdited.connect(lambda v, k=key, r=row: self.parameter(r, k, v))
            self.parameter_widgets[key] = widget

            bindable = (not self.immutable) and is_bindable_field(step['op'], key, step, self.definitions)
            bound_pid = bound_fields.get(key)
            bound_label = params_by_id.get(bound_pid, {}).get('label', bound_pid) if bound_pid else None
            is_pattern = step['op'] == 'file.rename_output' and key == 'pattern'

            source_btn = None
            if bindable:
                source_btn = make_field_source_button(bound_label)
                source_menu = QMenu(source_btn)
                source_menu.aboutToShow.connect(
                    lambda r=row, k=key, m=source_menu: self._populate_field_source_menu(r, k, m)
                )
                source_btn.setMenu(source_menu)
                self.field_source_buttons[key] = source_btn

            if bound_label:
                widget.hide()

            if spec.get('settings_key'):
                field_row = QWidget(); field_layout = QHBoxLayout(field_row)
                field_layout.setContentsMargins(0, 0, 0, 0); field_layout.setSpacing(4)
                if bound_label:
                    badge = QLabel(f'Ask when running: {bound_label}')
                    badge.setTextFormat(Qt.PlainText)
                    badge.setWordWrap(True)
                    field_layout.addWidget(badge, 1)
                field_layout.addWidget(widget, 1)
                reset = QPushButton('Reset from Settings')
                reset.clicked.connect(lambda checked=False, r=row, k=key: self.reset_to_settings(r, k))
                field_layout.addWidget(reset); field_layout.addWidget(HelpButton('settings')); self.parameter_resets[key] = reset
                if source_btn is not None:
                    field_layout.addWidget(source_btn)
                self.field_row_widgets[key] = field_row
                self.form.addRow(spec.get('label', key), field_row)
                mode = QLabel('')
                self.parameter_modes[key] = mode
                self.form.addRow('', mode)
            elif is_pattern and not self.immutable:
                field_row = QWidget(); field_layout = QHBoxLayout(field_row)
                field_layout.setContentsMargins(0, 0, 0, 0); field_layout.setSpacing(4)
                field_layout.addWidget(widget, 1)
                insert_btn = make_insert_variable_button(field_row)
                insert_menu = QMenu(insert_btn)
                insert_menu.aboutToShow.connect(
                    lambda r=row, w=widget, m=insert_menu: self._populate_pattern_insert_menu(r, w, m)
                )
                insert_btn.setMenu(insert_menu)
                self.pattern_insert_button = insert_btn
                field_layout.addWidget(insert_btn)
                self.field_row_widgets[key] = field_row
                self.form.addRow(spec.get('label', key.replace('_', ' ')), field_row)
            elif bindable or bound_label:
                field_row = QWidget(); field_layout = QHBoxLayout(field_row)
                field_layout.setContentsMargins(0, 0, 0, 0); field_layout.setSpacing(4)
                if bound_label:
                    badge = QLabel(f'Ask when running: {bound_label}')
                    badge.setTextFormat(Qt.PlainText)
                    badge.setWordWrap(True)
                    field_layout.addWidget(badge, 1)
                field_layout.addWidget(widget, 1)
                if source_btn is not None:
                    field_layout.addWidget(source_btn)
                self.field_row_widgets[key] = field_row
                if spec['type'] == 'capture_datetime':
                    self.form.addRow(field_row)
                else:
                    self.form.addRow(spec.get('label', key.replace('_', ' ')), field_row)
            else:
                self.field_row_widgets[key] = widget
                if spec['type'] == 'capture_datetime': self.form.addRow(widget)
                else: self.form.addRow(spec.get('label', key.replace('_', ' ')), widget)
            if is_pattern:
                pat_info = QWidget()
                pat_info_layout = QVBoxLayout(pat_info)
                pat_info_layout.setContentsMargins(0, 0, 0, 0)
                pat_info_layout.setSpacing(2)
                self.pattern_summary = QLabel(pat_info)
                self.pattern_summary.setTextFormat(Qt.PlainText)
                self.pattern_summary.setWordWrap(True)
                self.pattern_summary.hide()
                pat_info_layout.addWidget(self.pattern_summary)
                self.filename_example = QLabel(pat_info)
                self.filename_example.setTextFormat(Qt.PlainText)
                self.filename_example.setWordWrap(True)
                pat_info_layout.addWidget(self.filename_example)
                self.form.addRow('', pat_info)
                widget.textChanged.connect(self.update_filename_example)
                self.update_filename_example()
        if step['op'] == 'metadata.set_capture':
            # Blank was the old 'choose timezone' UI state. Unknown is now the
            # explicit, safe default for manual clocks; no local zone is used.
            if not step['timezone']: step['timezone'] = 'unknown'
            self.capture_options = CaptureDateOptions(step['timezone'],step['fields'],embedded=True)
            self.parameter_widgets['timezone'] = self.capture_options.zone
            self.parameter_widgets['fields'] = self.capture_options.fields
            self.capture_options.zone_changed.connect(lambda v,r=row:self.parameter(r,'timezone',v))
            self.capture_options.fields_changed.connect(lambda v,r=row:self.parameter(r,'fields',v))
            self.form.addRow(self.capture_options)
        topics = {'metadata.set_capture':(), 'metadata.shift_capture':('capture','dates'),
                  'image.convert':('quality','color'), 'image.compress':('quality',), 'image.color':('color',),
                  'image.resize':('resize',), 'image.resize_exact':('resize',), 'image.resize_geometry':('resize',),
                  'metadata.strip_all':('strip',), 'file.rename_output':(), 'file.name_transform':('output',)}
        for topic in topics.get(step['op'],()):
            from kim_ui import HELP
            self.form.addRow(HELP[topic][0], HelpButton(topic))
        if definitions:
            self.step_defaults_button = QPushButton(QIcon.fromTheme('edit-undo'), 'Reset step defaults')
            self.step_defaults_button.clicked.connect(self.reset_step_defaults)
            self.form.addRow(self.step_defaults_button)
        self.update_parameter_modes(row)
        self.update_conversion_controls(row)

    def configure_image_operation(self, row):
        from kim_image_ops_dialog import ImageOperationDialog
        # The same modal controls configure standalone operations. The Recipe
        # destination and all preceding/succeeding steps remain authoritative.
        files = self.files if self.example_files is None else self.example_files
        original = self.recipe['steps'][row]
        if is_parameterized(self.recipe):
            try:
                concrete, state_kind, _ = self._compile_preview_snapshot()
            except (OSError, RecipeError) as exc:
                self.error(exc)
                return
            if state_kind == 'incomplete' or concrete is None:
                answer = QMessageBox.question(
                    self,
                    'KIMng - Example Values Required',
                    'Set example values before opening visual configuration '
                    'for this parameterized Recipe. Open Preview Settings now?',
                    QMessageBox.Yes | QMessageBox.Cancel,
                    QMessageBox.Yes,
                )
                if answer == QMessageBox.Yes and self.open_preview_settings():
                    try:
                        concrete, state_kind, _ = self._compile_preview_snapshot()
                    except (OSError, RecipeError) as exc:
                        self.error(exc)
                        return
                if state_kind != 'ready' or concrete is None:
                    return
            dialog_recipe = concrete
            dialog_step = copy.deepcopy(concrete['steps'][row])
        else:
            try:
                authored = validate_authored(self.recipe)
                dialog_recipe = resolve_recipe(authored, {}, validated=True)
            except (OSError, RecipeError) as exc:
                self.error(exc)
                return
            dialog_step = copy.deepcopy(dialog_recipe['steps'][row])

        dialog = ImageOperationDialog(dialog_step, files, self,
                                      recipe=dialog_recipe, row=row)
        sample = self.example_selector.currentData()
        if sample and dialog.images.findData(sample) >= 0:
            dialog.images.setCurrentIndex(dialog.images.findData(sample))
        if dialog.exec() != QDialog.Accepted: return
        replacement = copy.deepcopy(dialog.step)
        if 'enabled' in original:
            replacement['enabled'] = original['enabled']
        if 'enabled_when' in original:
            replacement['enabled_when'] = copy.deepcopy(original['enabled_when'])
        if 'bindings' in original:
            replacement['bindings'] = copy.deepcopy(original['bindings'])
            # Preserve authored literal fallback values for bound fields unless the
            # user explicitly edited that field away from the resolved preview value.
            for field in original['bindings']:
                if replacement.get(field) == dialog_step.get(field):
                    if field in original:
                        replacement[field] = copy.deepcopy(original[field])
                    if (
                        original['op'] == 'image.overlay'
                        and field == 'value'
                        and original.get('text_fields') is not None
                        and replacement.get('text_fields') is not None
                    ):
                        replacement['text_fields']['custom'] = copy.deepcopy(
                            original['text_fields'].get('custom', {'selected': False, 'value': ''})
                        )
        self.recipe['steps'][row] = replacement
        self._refresh_parameters_section()
        self.reload_steps(row); self.update_modified(); self.update_preview()

    def update_filename_example(self,*_):
        if self.pattern_summary is not None and 'pattern' in self.parameter_widgets:
            pattern_text = self.parameter_widgets['pattern'].text()
            summary = self._template_uses_summary(pattern_text, allow_source_tokens=True)
            if summary:
                self.pattern_summary.setText('Pattern uses: ' + summary)
                self.pattern_summary.setVisible(True)
                self.parameter_widgets['pattern'].setToolTip('Pattern uses: ' + summary)
            else:
                self.pattern_summary.setText('')
                self.pattern_summary.setVisible(False)
                self.parameter_widgets['pattern'].setToolTip('')
        if self.filename_example is None: return
        sample = self.example_selector.currentData()
        if is_parameterized(self.recipe):
            try:
                ex = preview_output_example(
                    self.recipe,
                    self.current_preview_values(),
                    source_name=sample,
                )
            except RecipeError:
                self.filename_example.setText('Example output: enter a valid filename pattern.')
                return
            if not ex['available']:
                self.filename_example.setText('')
                return
            if not ex['complete']:
                self.filename_example.setText(
                    'Example output: set example values to preview.'
                )
                return
            if ex['filename']:
                self.filename_example.setText('Example output: ' + ex['filename'])
            elif ex['note']:
                self.filename_example.setText('Example output: ' + ex['note'])
            else:
                self.filename_example.setText('Example output: confirmed during Review Changes.')
            return

        from kim_recipe_image import FORMATS
        source=Path(sample) if sample else Path('vacation.jpg')
        suffix=source.suffix.lower().lstrip('.')
        fmt={'jpg':'jpeg','jpe':'jpeg','jfif':'jpeg','tif':'tiff','heif':'heic'}.get(suffix,suffix)
        for step in self.recipe['steps']:
            if step['op']=='image.convert' and step.get('enabled',True): fmt=step['format']
        if fmt not in FORMATS:
            self.filename_example.setText('Example output: choose Convert Format for this image.'); return
        try:
            value=self.parameter_widgets['pattern'].text()
            name=format_output_pattern(value,source.stem,'[image capture date]',1)
            self.filename_example.setText('Example output: '+name+'.'+FORMATS[fmt])
        except (KeyError,ValueError): self.filename_example.setText('Example output: enter a valid filename pattern.')

    def resize_preset(self,row,size):
        if size is None: return
        for key in ('max_width','max_height'):
            self.parameter_widgets[key].setValue(size)

    def update_conversion_controls(self, row):
        step = self.recipe['steps'][row]
        if row != self.steps.currentRow(): return
        bound_fields = step.get('bindings') or {}
        if step['op'] == 'metadata.set_capture':
            dt_row = self.field_row_widgets.get('datetime', self.parameter_widgets['datetime'])
            self.form.setRowVisible(dt_row, step['mode'] == 'specific')
            embedded = self.capture_options.zone.findData('embedded')
            self.capture_options.zone.model().item(embedded).setEnabled(step['mode'] == 'embedded')
            if step['mode'] == 'file_mtime': self.capture_options.toggle.setChecked(True)
        if step['op'] == 'image.compress':
            for key in ('quality','png_level'):
                self.parameter_widgets[key].setEnabled(step['preset'] == 'custom')
        if step['op'] != 'image.convert' or row != self.steps.currentRow(): return
        fmt = step['format']
        for key, formats in {'jpeg_progressive':('jpeg',), 'jpeg_optimize':('jpeg',), 'jp2_mode':('jp2',), 'tiff_compression':('tiff',), 'depth':('png','jp2','tiff')}.items():
            if key in self.parameter_widgets:
                row_widget = self.field_row_widgets.get(key, self.parameter_widgets[key])
                self.form.setRowVisible(row_widget, fmt in formats)
        self.parameter_widgets['quality'].setEnabled(fmt in ('jpeg','webp','avif','heic','heif','jxl') or (fmt=='jp2' and step.get('jp2_mode','lossless')=='lossy'))
        self.parameter_resets['quality'].setVisible(
            fmt in ('jpeg','webp','avif') and 'quality' not in bound_fields
        )

    def update_parameter_modes(self, row):
        if row < 0: return
        step = self.recipe['steps'][row]
        bound_fields = step.get('bindings') or {}
        params_by_id = {p['id']: p for p in self.recipe.get('parameters', ())}
        for key, label in self.parameter_modes.items():
            if key in bound_fields:
                self.parameter_resets[key].setEnabled(False)
                self.parameter_resets[key].setVisible(False)
                pid = bound_fields[key]
                p_label = params_by_id.get(pid, {}).get('label', pid)
                label.setText(f'Provided at run time by “{p_label}”')
                label.setWordWrap(True)
                label.setVisible(True)
                continue
            self.parameter_resets[key].setVisible(True)
            inherited = step.get(key) is None
            self.parameter_resets[key].setEnabled(not inherited)
            if inherited:
                try: value = self.media_handler.parameter_value(step,key)
                except (OSError,RecipeError) as exc:
                    value = self.definitions[step['op']]['parameters'][key]['default'] or ''
                    self.status.setText(str(exc))
                widget = self.parameter_widgets[key]
                widget.blockSignals(True)
                if isinstance(widget,QSpinBox): widget.setValue(value)
                else: widget.setText(value)
                widget.blockSignals(False)
                source = ''
                if step['op'] == 'image.convert':
                    from kim_recipe_image import quality_setting
                    source = ': ' + (quality_setting(step['format']) or 'quality not inherited for this format')
                label.setText('Inherited from KIMng Settings' + source + (': not set' if not value else ''))
            else:
                label.setText('Custom override' if step[key] and key != 'quality' else '' if step[key] else 'Blank override: leave this field unchanged')
            label.setWordWrap(True)
            label.setVisible(bool(label.text()))


    def parameter(self, row, key, value):
        self.recipe['steps'][row][key] = value
        self.steps.blockSignals(True)
        self.steps.item(row).setText(self._step_display_text(self.recipe['steps'][row]))
        self.steps.blockSignals(False)
        self.update_parameter_modes(row)
        self.update_conversion_controls(row)
        if self.recipe['steps'][row]['op'] == 'file.rename_output' and key == 'pattern':
            self._refresh_parameters_section()
        self.update_modified()
        self.timer.start()

    def reset_to_settings(self, row, key):
        if self.recipe['steps'][row]['op'] == 'image.convert' and key == 'quality':
            self.recipe['steps'][row][key] = None
        else: self.recipe['steps'][row].pop(key, None)
        self.edit_step(row)
        self.update_modified()
        self.update_preview()

    def reset_step_defaults(self):
        row = self.steps.currentRow()
        if row < 0:
            return
        step = self.recipe['steps'][row]
        defaults = self.definitions[step['op']]['parameters']
        replacement = {'op': step['op'], **{key: copy.deepcopy(spec['default']) for key, spec in defaults.items()}}
        if 'enabled' in step:
            replacement['enabled'] = step['enabled']
        self.recipe['steps'][row] = replacement
        self._refresh_parameters_section()
        self.reload_steps(row)
        self.update_modified()
        self.update_preview()

    def changed(self, *args):
        if not self.loading and self.recipe and not self.immutable:
            self.recipe['name'] = self.name.text()
            self.recipe['description'] = self.description.toPlainText()
            mode = self.mode.currentData()
            dest = {'mode': mode}
            if mode == 'subfolder': dest['folder'] = self.folder.text()
            if mode == 'directory':
                dest['ask'] = self.ask.isChecked()
                if self.path.text(): dest['path'] = self.path.text()
            self.recipe['destination'] = dest
            self.update_destination_controls()
            self._refresh_parameters_section()
            self.update_modified()
            self.timer.start()

    def _classify_subfolder_template(self, folder_text):
        """Classify a subfolder string into ('ask', pid), ('advanced', None), or ('fixed', None)."""
        raw = folder_text if isinstance(folder_text, str) else ''
        if not has_parameter_references(raw):
            return 'fixed', None
        try:
            tokens = parse_template(raw, allow_source_tokens=False)
        except RecipeError:
            return 'advanced', None
        params_by_id = (
            {p['id']: p for p in self.recipe.get('parameters', ())}
            if self.recipe is not None
            else {}
        )
        if len(tokens) == 1 and tokens[0][0] == 'param' and tokens[0][1] in params_by_id:
            return 'ask', tokens[0][1]
        return 'advanced', None

    def _refresh_subfolder_param_combo(self, selected_pid=None):
        combo = self.subfolder_param_combo
        combo.blockSignals(True)
        combo.clear()
        compat = (
            compatible_parameters_for_template(self.recipe, allow_source_tokens=False)
            if self.recipe is not None
            else []
        )
        for param in compat:
            combo.addItem(param['label'], param['id'])
        if selected_pid and combo.findData(selected_pid) < 0:
            params_by_id = {p['id']: p for p in (self.recipe or {}).get('parameters', ())}
            if selected_pid in params_by_id:
                combo.addItem(params_by_id[selected_pid]['label'], selected_pid)
        combo.addItem('New question…', '__new__')
        if selected_pid:
            idx = combo.findData(selected_pid)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        elif compat:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)
        cur_pid = combo.currentData()
        self.subfolder_edit_param_btn.setEnabled(
            not self.immutable and isinstance(cur_pid, str) and cur_pid != '__new__'
        )

    def _sync_subfolder_widgets_from_recipe(self):
        if self.recipe is None:
            return
        dest = self.recipe.get('destination', {'mode': 'beside'})
        dmode = dest.get('mode', 'beside')
        self.subfolder_mode.blockSignals(True)
        if dmode == 'beside':
            self.subfolder_mode.setCurrentIndex(self.subfolder_mode.findData('none'))
            self._last_subfolder_mode = 'none'
            self._last_subfolder_param = None
        elif dmode == 'subfolder':
            smode, pid = self._classify_subfolder_template(dest.get('folder', ''))
            self.subfolder_mode.setCurrentIndex(self.subfolder_mode.findData(smode))
            self._last_subfolder_mode = smode
            self._last_subfolder_param = pid
            if smode == 'ask':
                self._refresh_subfolder_param_combo(pid)
        self.subfolder_mode.blockSignals(False)

    def _on_directory_mode_changed(self, *_):
        if self.loading or self.recipe is None:
            return
        dmode = self.mode.currentData()
        self.subfolder_mode.blockSignals(True)
        if dmode == 'beside':
            self.subfolder_mode.setCurrentIndex(self.subfolder_mode.findData('none'))
            self._last_subfolder_mode = 'none'
        elif dmode == 'subfolder' and self.subfolder_mode.currentData() == 'none':
            smode, pid = self._classify_subfolder_template(self.folder.text())
            if not self.folder.text().strip():
                self.folder.setText('Recipes')
                smode, pid = 'fixed', None
            self.subfolder_mode.setCurrentIndex(self.subfolder_mode.findData(smode))
            self._last_subfolder_mode = smode
            self._last_subfolder_param = pid
            if smode == 'ask':
                self._refresh_subfolder_param_combo(pid)
        self.subfolder_mode.blockSignals(False)
        self.changed()

    def _create_subfolder_question(self):
        if not self.writable() or self.recipe is None:
            return None
        params = list(self.recipe.get('parameters') or ())
        existing_ids = {p['id'] for p in params}
        initial = {'type': 'text', 'required': True}

        def validate_sub_param(built):
            probe = copy.deepcopy(self.recipe)
            probe.setdefault('parameters', []).append(built)
            probe['destination'] = {'mode': 'subfolder', 'folder': '{param:' + built['id'] + '}'}
            validate_authored(probe)

        dialog = ParameterEditorDialog(
            param=initial,
            existing_ids=existing_ids,
            earlier_params=params,
            locked_type=False,
            validate_callback=validate_sub_param,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted or dialog.result_param is None:
            return None
        created = dialog.result_param
        self._ensure_parameters_list().append(created)
        return created

    def _on_subfolder_mode_changed(self, *_):
        if self.loading or self.recipe is None or self.immutable:
            return
        smode = self.subfolder_mode.currentData()
        prev_mode = self._last_subfolder_mode
        if smode == 'none':
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(self.mode.findData('beside'))
            self.mode.blockSignals(False)
            self._last_subfolder_mode = 'none'
            self._last_subfolder_param = None
            self.changed()
            return

        if smode == 'fixed':
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(self.mode.findData('subfolder'))
            self.mode.blockSignals(False)
            if not self.folder.text().strip() or has_parameter_references(self.folder.text()):
                self.folder.setText('Recipes')
            self._last_subfolder_mode = 'fixed'
            self._last_subfolder_param = None
            self.changed()
            return

        if smode == 'ask':
            compat = compatible_parameters_for_template(
                self.recipe, allow_source_tokens=False
            )
            chosen_pid = None
            if self._last_subfolder_param and any(p['id'] == self._last_subfolder_param for p in compat):
                chosen_pid = self._last_subfolder_param
            elif compat:
                chosen_pid = compat[0]['id']
            else:
                created = self._create_subfolder_question()
                if created is None:
                    self.subfolder_mode.blockSignals(True)
                    self.subfolder_mode.setCurrentIndex(self.subfolder_mode.findData(prev_mode))
                    self.subfolder_mode.blockSignals(False)
                    return
                chosen_pid = created['id']
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(self.mode.findData('subfolder'))
            self.mode.blockSignals(False)
            self.folder.setText('{param:' + chosen_pid + '}')
            self._last_subfolder_mode = 'ask'
            self._last_subfolder_param = chosen_pid
            self._refresh_subfolder_param_combo(chosen_pid)
            self.changed()
            return

        if smode == 'advanced':
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(self.mode.findData('subfolder'))
            self.mode.blockSignals(False)
            if not self.folder.text().strip():
                self.folder.setText('Recipes')
            self._last_subfolder_mode = 'advanced'
            self.changed()

    def _on_subfolder_param_changed(self, *_):
        if self.loading or self.recipe is None or self.immutable:
            return
        pid = self.subfolder_param_combo.currentData()
        if pid == '__new__':
            created = self._create_subfolder_question()
            if created is None:
                self._refresh_subfolder_param_combo(self._last_subfolder_param)
                return
            pid = created['id']
            self._refresh_subfolder_param_combo(pid)
        if isinstance(pid, str) and pid and pid != '__new__':
            self._last_subfolder_param = pid
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(self.mode.findData('subfolder'))
            self.mode.blockSignals(False)
            self.folder.setText('{param:' + pid + '}')
            self.changed()

    def _edit_subfolder_question(self):
        pid = self.subfolder_param_combo.currentData()
        if isinstance(pid, str) and pid and pid != '__new__':
            self.edit_parameter(pid)

    def update_destination_controls(self):
        mode = self.mode.currentData()
        is_dir = mode == 'directory'
        self.destinations.setRowVisible(self.subfolder_row, not is_dir)

        if is_dir:
            self.folder_row.setVisible(False)
            self.subfolder_ask_row.setVisible(False)
            self.destination_summary.setText('')
            self.destinations.setRowVisible(self.destination_summary, False)
        else:
            smode = self.subfolder_mode.currentData()
            if mode == 'beside':
                smode = 'none'
            if smode == 'none':
                self.folder_row.setVisible(False)
                self.subfolder_ask_row.setVisible(False)
                self.destination_summary.setText('')
                self.folder.setToolTip('')
                self.destinations.setRowVisible(self.destination_summary, False)
            elif smode == 'fixed':
                self.folder_row.setVisible(True)
                self.folder_insert_button.setVisible(False)
                self.subfolder_ask_row.setVisible(False)
                self.destination_summary.setText('')
                self.folder.setToolTip('Fixed subfolder name created beside each original')
                self.destinations.setRowVisible(self.destination_summary, False)
            elif smode == 'ask':
                self.folder_row.setVisible(False)
                self.subfolder_ask_row.setVisible(True)
                _, pid = self._classify_subfolder_template(self.folder.text())
                self._refresh_subfolder_param_combo(pid or self._last_subfolder_param)
                summary_text = ''
                if self.recipe is not None and is_parameterized(self.recipe):
                    try:
                        ex = preview_output_example(
                            self.recipe,
                            self.current_preview_values(),
                            source_name=self.example_selector.currentData(),
                        )
                    except RecipeError:
                        ex = {'complete': False, 'subfolder': None}
                    if ex.get('complete') and ex.get('subfolder'):
                        summary_text = 'Example subfolder: ' + ex['subfolder']
                if summary_text:
                    self.destination_summary.setText(summary_text)
                    self.destinations.setRowVisible(self.destination_summary, True)
                else:
                    self.destination_summary.setText('')
                    self.destinations.setRowVisible(self.destination_summary, False)
            else:
                self.folder_row.setVisible(True)
                self.folder_insert_button.setVisible(not self.immutable)
                self.subfolder_ask_row.setVisible(False)
                summary = self._template_uses_summary(
                    self.folder.text(), allow_source_tokens=False
                )
                if summary:
                    text = 'Subfolder uses: ' + summary
                    self.destination_summary.setText(text)
                    self.folder.setToolTip(text)
                    self.destinations.setRowVisible(self.destination_summary, True)
                else:
                    self.destination_summary.setText('')
                    self.folder.setToolTip('')
                    self.destinations.setRowVisible(self.destination_summary, False)

        self.destinations.setRowVisible(self.ask, is_dir)
        self.destinations.setRowVisible(self.directory_row, is_dir and not self.ask.isChecked())

    def browse(self):
        if self.immutable: return
        directory = QFileDialog.getExistingDirectory(self, 'Recipe destination')
        if directory:
            self.path.setText(directory); self.changed()

    def writable(self):
        if self.immutable:
            self.status.setText('Duplicate to save a user recipe or change step order and destination. Built-in parameter edits and checkboxes apply only to this run.')
            return False
        return True

    def protect_unsaved(self):
        if self.recipe is None or self.immutable or not self.is_dirty():
            return True
        if self.allow_dev_draft_run and self.recipe['id'] in self.dev_draft_ids:
            answer = QMessageBox.question(
                self,
                'Temporary development draft',
                'Discard unsaved changes to this temporary development draft?',
                QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Discard,
            )
            return answer == QMessageBox.Discard
        answer = QMessageBox.question(self, 'Unsaved recipe', 'Save changes to this recipe?',
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer == QMessageBox.Save:
            return self.save()
        return answer == QMessageBox.Discard

    def append_recipe(self, recipe):
        # Drafts live only in this widget until Save succeeds.
        self.draft_ids.add(recipe['id'])
        self.users.append(recipe)
        self.refresh(len(self.shipped) + len(self.users) - 1)

    def store_users(self, users):
        warning = save_library(RecipeLibrary([r for r in users if r['id'] not in self.draft_ids], self.folders))
        if warning: self.error(warning)

    def shortcut_changed(self, checked):
        if self.loading or self.recipe is None or self.immutable:
            return
        self.recipe['dolphin_shortcut'] = bool(checked)
        self.update_modified()

    def folder_changed(self):
        if self.loading or self.immutable:
            return
        folder_id = self.library_folder.currentData()
        if folder_id is None:
            self.recipe.pop('folder', None)
        else:
            self.recipe['folder'] = folder_id
        self.update_modified()

    def change_folders(self, change):
        if not self.protect_unsaved():
            return False

        if not self.immutable and self.is_dirty():
            self.select(self.active_index, force=True)

        snapshot = (
            copy.deepcopy(self.recipe)
            if self.immutable else None
        )
        selected_id = self.recipe['id']

        library = RecipeLibrary(
            copy.deepcopy([
                r for r in self.users
                if r['id'] not in self.draft_ids
            ]),
            copy.deepcopy(self.folders),
        )

        try:
            change(library)
            warning = save_library(library)

            # The library has been saved. Refresh the UI before
            # displaying any ancillary shortcut-sync warning.
            self.users, self.folders = (
                library.recipes, library.folders
            )

            index = next(
                (
                    i for i, recipe in enumerate(
                        self.shipped + self.users
                    )
                    if recipe['id'] == selected_id
                ),
                0
            )
            self.refresh(index)

            if snapshot is not None:
                self.recipe = snapshot
                self.reload_steps()
                self.update_modified()
                self.update_preview()

            if warning:
                self.error(warning)

            return True

        except (OSError, RecipeError) as exc:
            self.error(exc)
            return False

    def create_folder(self):
        folder_id, selected = self.selected_tree_folder_id()

        if not selected:
            folder_id = (
                self.recipe.get('folder')
                if self.recipe is not None and not self.immutable
                else None
            )

        self.create_folder_in(folder_id)

    def create_folder_in(self, parent_id=None):
        if parent_id == '':
            parent_id = None

        name, ok = QInputDialog.getText(
            self, 'Create Recipe folder', 'Folder name'
        )

        if ok:
            self.change_folders(
                lambda library: library.create_folder(name, parent_id)
            )

    def move_tree_folder(self, folder_id):
        library = RecipeLibrary(self.users, self.folders)
        excluded = library.descendants(folder_id)

        destinations = [('User', None)]
        destinations.extend(
            (folder_path(f['id'], self.folders), f['id'])
            for f in self.folders if f['id'] not in excluded
        )

        names = [name for name, _ in destinations]

        choice, accepted = QInputDialog.getItem(
            self, 'Move Recipe folder', 'Parent folder',
            names, 0, False
        )

        if accepted:
            destination = destinations[names.index(choice)][1]
            self.change_folders(
                lambda lib: lib.move_folder(folder_id, destination)
            )


    def choose_folder(self, title):
        if not self.folders:
            self.status.setText('There are no user recipe folders.'); return None
        folders = sorted(self.folders, key=lambda f: f['name'].casefold())
        name, ok = QInputDialog.getItem(self, title, 'Recipe folder', [f['name'] for f in folders], editable=False)
        return next((f for f in folders if f['name'] == name), None) if ok else None

    def rename_folder(self):
        folder = self.choose_folder('Rename Recipe Folder')
        if folder is None: return
        name, ok = QInputDialog.getText(self, 'Rename Recipe Folder', 'New name', text=folder['name'])
        if ok: self.change_folders(lambda library: library.rename_folder(folder['id'], name))

    def delete_folder(self):
        folder = self.choose_folder('Delete recipe folder')
        if folder is None: return
        message = QMessageBox(self); message.setWindowTitle('KIMng - Delete Recipe Folder'); message.setTextFormat(Qt.PlainText)
        message.setText('Delete folder “' + folder['name'] + '”? Its recipes will move to Unfiled; no recipes or images are deleted.')
        message.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel); message.setDefaultButton(QMessageBox.Cancel)
        if message.exec() == QMessageBox.Yes:
            self.change_folders(lambda library: library.delete_folder(folder['id']))

    def new(self):
        if not self.protect_unsaved(): return
        self.append_recipe({'schema': AUTHORED_SCHEMA, 'id': 'user-' + uuid.uuid4().hex, 'name': 'New Recipe', 'description': '', 'dolphin_shortcut': False,
            'media': 'image', 'steps': [{'op': 'file.rename_output', 'pattern': '{filename}_recipe'}],
            'destination': {'mode': 'beside'}})

    def duplicate(self):
        if not self.protect_unsaved(): return
        recipe = copy.deepcopy(self.recipe if self.immutable or not self.is_dirty() else self.baseline)
        recipe['id'] = 'user-' + uuid.uuid4().hex; recipe['name'] += ' copy'
        recipe['dolphin_shortcut'] = False
        self.append_recipe(recipe)

    def rename(self):
        if not self.writable(): return
        name, ok = QInputDialog.getText(self, 'Rename recipe', 'Name', text=self.name.text())
        if ok: self.name.setText(name); self.changed()

    def remove(self):
        if not self.writable(): return
        index = self.active_index - len(self.shipped)
        answer = QMessageBox.question(self, 'Delete recipe',
            'Delete saved recipe “' + self.users[index]['name'] + '”?',
            QMessageBox.Yes | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Yes or not self.protect_unsaved():
            return
        deleted_id = self.users[index]['id']
        users = self.users[:]; del users[index]
        try:
            self.store_users(users); self.users = users
            try:
                clear_remembered_values(deleted_id)
            except (OSError, RecipeError):
                pass
            self.refresh()
        except (OSError, RecipeError) as exc: self.error(exc)

    def save(self):
        if not self.writable(): return False
        if self.recipe['id'] in self.dev_draft_ids:
            self.error(
                'Saving temporary development drafts to the live library is disabled.'
            )
            return False
        if not self.is_dirty():
            self.status.setText('No unsaved changes.')
            return True
        try:
            recipe = validate_authored(self.recipe)
            index = self.active_index - len(self.shipped)
            users = self.users[:]; users[index] = recipe
            is_new = recipe['id'] in self.draft_ids
            self.draft_ids.discard(recipe['id'])
            try:
                self.store_users(users)
            except Exception:
                if is_new: self.draft_ids.add(recipe['id'])
                raise
            try:
                remembered = load_remembered_values(recipe['id'])
                if remembered:
                    keep_remember_ids = {
                        p['id'] for p in recipe.get('parameters', ())
                        if p.get('remember', False)
                    }
                    stale = [
                        pid for pid in remembered
                        if pid not in keep_remember_ids
                    ]
                    if stale:
                        clear_remembered_values(recipe['id'], stale)
            except (OSError, RecipeError):
                pass
            self.users = users
            if is_new: self.saved_new_recipe_id = recipe['id']
            self.saved_recipe_id = recipe['id']
            self.recipe = copy.deepcopy(recipe)
            self.baseline = copy.deepcopy(recipe)
            self.refresh_recipe_tree()
            self.update_modified()
            self.status.setText('Recipe saved.')
            return True
        except (OSError, RecipeError) as exc:
            self.error(exc)
            return False

    def add_step(self, op=None):
        if not self.writable(): return
        if not isinstance(op, str):
            dialog = OperationPicker(self.definitions, self)
            if dialog.exec() != QDialog.Accepted: return
            op = dialog.operation_id
        if op not in self.definitions: return
        self.recipe['steps'].append({'op': op, **{key: copy.deepcopy(spec['default'])
            for key, spec in self.definitions[op]['parameters'].items()}})
        self.reload_steps(len(self.recipe['steps']) - 1); self.update_modified(); self.timer.start()

    def remove_step(self):
        if not self.writable(): return
        row = self.steps.currentRow()
        if row >= 0:
            del self.recipe['steps'][row]
            self._refresh_parameters_section()
            self.reload_steps(row); self.update_modified(); self.timer.start()

    def move(self, delta):
        if not self.writable(): return
        row = self.steps.currentRow(); target = row + delta
        if 0 <= target < len(self.recipe['steps']):
            steps = self.recipe['steps']; steps[row], steps[target] = steps[target], steps[row]
            self.reload_steps(target); self.update_modified(); self.timer.start()

    def _refresh_parameters_section(self, *, select_id=None):
        if not hasattr(self, 'parameters_section') or self.recipe is None:
            return
        self.parameters_section.set_recipe(
            self.recipe,
            immutable=self.immutable,
            definitions=self.definitions,
            select_id=select_id,
        )
        if hasattr(self, 'workspace_tabs'):
            count = self.parameters_section.parameter_count()
            self.workspace_tabs.setTabText(
                1, f'Parameters ({count})' if count else 'Parameters'
            )
            self.workspace_tabs.setTabToolTip(1, _PARAMETERS_TAB_TOOLTIP)

    def _ensure_parameters_list(self):
        if 'parameters' not in self.recipe or self.recipe['parameters'] is None:
            self.recipe['parameters'] = []
        return self.recipe['parameters']

    def _cleanup_empty_parameters(self):
        if 'parameters' in self.recipe and not self.recipe['parameters']:
            self.recipe.pop('parameters', None)

    def add_parameter(self, initial_param=None):
        if not self.writable() or self.recipe is None:
            return None
        params = list(self.recipe.get('parameters') or ())
        existing_ids = {p['id'] for p in params}

        def validate_new(built):
            probe = copy.deepcopy(self.recipe)
            probe.setdefault('parameters', []).append(built)
            validate_authored(probe)

        dialog = ParameterEditorDialog(
            param=initial_param,
            existing_ids=existing_ids,
            earlier_params=params,
            locked_type=False,
            validate_callback=validate_new,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted or dialog.result_param is None:
            return None
        self._ensure_parameters_list().append(dialog.result_param)
        self._refresh_parameters_section(select_id=dialog.result_param['id'])
        self.update_modified()
        self.timer.start()
        return dialog.result_param

    def edit_parameter(self, pid):
        if not self.writable() or self.recipe is None:
            return False
        params = self.recipe.get('parameters') or []
        idx = next((i for i, p in enumerate(params) if p['id'] == pid), -1)
        if idx < 0:
            return False
        refs = parameter_references(self.recipe, pid, definitions=self.definitions)

        def validate_edit(built):
            probe = copy.deepcopy(self.recipe)
            probe['parameters'][idx] = built
            validate_authored(probe)

        dialog = ParameterEditorDialog(
            param=copy.deepcopy(params[idx]),
            existing_ids={p['id'] for p in params if p['id'] != pid},
            earlier_params=params[:idx],
            locked_type=bool(refs),
            references=refs,
            recipe=self.recipe,
            validate_callback=validate_edit,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted or dialog.result_param is None:
            return False
        params[idx] = dialog.result_param
        self._refresh_parameters_section(select_id=pid)
        self.update_destination_controls()
        row = self.steps.currentRow()
        if row >= 0:
            self.edit_step(row)
        self._refresh_step_tooltips()
        self.update_modified()
        self.timer.start()
        return True

    def remove_parameter(self, pid):
        if not self.writable() or self.recipe is None:
            return False
        params = self.recipe.get('parameters') or []
        idx = next((i for i, p in enumerate(params) if p['id'] == pid), -1)
        if idx < 0:
            return False
        param = params[idx]
        refs = parameter_references(self.recipe, pid, definitions=self.definitions)
        if refs:
            lines = '\n'.join('• ' + ref['description'] for ref in refs)
            QMessageBox.warning(
                self,
                'Parameter is still in use',
                f"Cannot remove “{param['label']}” because it is still referenced by:\n\n"
                f'{lines}\n\n'
                'Remove or update those references first, then remove the parameter.',
            )
            return False
        del params[idx]
        self._cleanup_empty_parameters()
        self.current_preview_values().pop(pid, None)
        self._refresh_parameters_section()
        self.update_destination_controls()
        row = self.steps.currentRow()
        if row >= 0:
            self.edit_step(row)
        self._refresh_step_tooltips()
        self.update_modified()
        self.timer.start()
        return True

    def move_parameter(self, pid, delta):
        if not self.writable() or self.recipe is None:
            return False
        params = self.recipe.get('parameters') or []
        idx = next((i for i, p in enumerate(params) if p['id'] == pid), -1)
        if idx < 0:
            return False
        ok, reason = can_reorder_parameter(self.recipe, idx, delta)
        if not ok:
            self.error(reason)
            return False
        target = idx + delta
        params[idx], params[target] = params[target], params[idx]
        self._refresh_parameters_section(select_id=pid)
        self.update_modified()
        self.timer.start()
        return True

    def _populate_field_source_menu(self, row, key, menu):
        menu.clear()
        if self.recipe is None or not 0 <= row < len(self.recipe['steps']):
            return
        step = self.recipe['steps'][row]
        bound_pid = (step.get('bindings') or {}).get(key)

        fixed_act = menu.addAction('Use a fixed value')
        fixed_act.setCheckable(True)
        fixed_act.setChecked(bound_pid is None)
        fixed_act.triggered.connect(lambda checked=False, r=row, k=key: self.unbind_field(r, k))

        quick_ask = menu.addAction('Ask when running')
        quick_ask.triggered.connect(
            lambda checked=False, r=row, k=key: self.quick_bind_field(r, k)
        )

        custom_ask = menu.addAction('Ask when running (customize)…')
        custom_ask.triggered.connect(
            lambda checked=False, r=row, k=key: self.bind_field_to_new_parameter(r, k)
        )

        existing_menu = menu.addMenu('Use an existing question')
        compatible = compatible_parameters_for_field(
            self.recipe, row, key, definitions=self.definitions
        )
        if compatible:
            for param in compatible:
                act = existing_menu.addAction(param['label'])
                act.setCheckable(True)
                act.setChecked(param['id'] == bound_pid)
                act.triggered.connect(
                    lambda checked=False, r=row, k=key, pid=param['id']:
                        self.bind_field_to_parameter(r, k, pid)
                )
        else:
            empty_act = existing_menu.addAction('No compatible questions')
            empty_act.setEnabled(False)

        if bound_pid:
            menu.addSeparator()
            edit_act = menu.addAction('Edit question…')
            edit_act.triggered.connect(
                lambda checked=False, pid=bound_pid: self.edit_parameter(pid)
            )

    def quick_bind_field(self, row, key):
        """Create and bind a sensible question directly from an operation field without an extra modal dialog."""
        if not self.writable() or self.recipe is None or not 0 <= row < len(self.recipe['steps']):
            return None
        suggested = parameter_from_field(self.recipe, row, key, definitions=self.definitions)
        params = list(self.recipe.get('parameters') or ())
        existing_ids = {p['id'] for p in params}
        pid = generate_parameter_id(suggested['label'], existing_ids)
        built = {'id': pid, **suggested}

        probe = copy.deepcopy(self.recipe)
        probe.setdefault('parameters', []).append(built)
        bindings = dict(probe['steps'][row].get('bindings') or {})
        bindings[key] = pid
        probe['steps'][row]['bindings'] = bindings
        try:
            validate_authored(probe)
        except RecipeError:
            # Fall back to the properties dialog when manual adjustment is needed.
            return self.bind_field_to_new_parameter(row, key)

        self._ensure_parameters_list().append(built)
        self.recipe['steps'][row]['bindings'] = bindings
        self._refresh_parameters_section(select_id=pid)
        self._refresh_step_tooltips()
        self.edit_step(row)
        self.update_modified()
        self.timer.start()
        return built

    def _toggle_shared_resize(self, row, checked):
        """Bind or unbind Resize to Fit max_width and max_height together via one ordinary integer parameter."""
        if not self.writable() or self.recipe is None or not 0 <= row < len(self.recipe['steps']):
            return False
        step = self.recipe['steps'][row]
        if step.get('op') != 'image.resize':
            return False
        bound = dict(step.get('bindings') or {})
        w_pid = bound.get('max_width')
        h_pid = bound.get('max_height')

        if not checked:
            if w_pid and w_pid == h_pid:
                bound.pop('max_width', None)
                bound.pop('max_height', None)
                if bound:
                    step['bindings'] = bound
                else:
                    step.pop('bindings', None)
                self._refresh_parameters_section()
                self._refresh_step_tooltips()
                self.edit_step(row)
                self.update_modified()
                self.timer.start()
                return True
            self.edit_step(row)
            return False

        # Refuse silently replacing separate or partial bindings.
        if (bool(w_pid) != bool(h_pid)) or (w_pid and h_pid and w_pid != h_pid):
            self.edit_step(row)
            return False
        if w_pid and w_pid == h_pid:
            return True

        cur_w = int(step.get('max_width', 1600))
        cur_h = int(step.get('max_height', 1600))
        if cur_w == cur_h:
            default_dim = cur_w
        else:
            larger = max(cur_w, cur_h)
            options = [
                (f'{larger} px (larger of {cur_w} and {cur_h})', larger),
                (f'{cur_w} px (current maximum width)', cur_w),
                (f'{cur_h} px (current maximum height)', cur_h),
            ]
            labels = [lbl for lbl, _ in options]
            choice, ok = QInputDialog.getItem(
                self,
                'KIMng - Shared Maximum Dimension',
                'Maximum width and height currently differ. Choose a default maximum image dimension:',
                labels,
                0,
                False,
            )
            if not ok:
                self.edit_step(row)
                return False
            default_dim = options[labels.index(choice)][1]

        # Reuse an existing compatible "Maximum image dimension" parameter if present.
        w_compat = {p['id']: p for p in compatible_parameters_for_field(self.recipe, row, 'max_width', definitions=self.definitions)}
        h_compat = {p['id']: p for p in compatible_parameters_for_field(self.recipe, row, 'max_height', definitions=self.definitions)}
        shared_compat = [p for pid, p in w_compat.items() if pid in h_compat]
        existing = next(
            (p for p in shared_compat if p['label'].casefold() == 'maximum image dimension'),
            None,
        )

        probe = copy.deepcopy(self.recipe)
        if existing is not None:
            pid = existing['id']
            created = None
        else:
            existing_ids = {p['id'] for p in probe.get('parameters', ())}
            pid = generate_parameter_id('Maximum image dimension', existing_ids)
            created = {
                'id': pid,
                'label': 'Maximum image dimension',
                'type': 'integer',
                'minimum': 1,
                'maximum': 100000,
                'default': default_dim,
                'help': 'Fits within this limit while keeping proportions. Smaller images are not enlarged.',
            }
            probe.setdefault('parameters', []).append(created)

        probe_bindings = dict(probe['steps'][row].get('bindings') or {})
        probe_bindings['max_width'] = pid
        probe_bindings['max_height'] = pid
        probe['steps'][row]['bindings'] = probe_bindings
        try:
            validate_authored(probe)
        except RecipeError as exc:
            self.error(exc)
            self.edit_step(row)
            return False

        if created is not None:
            self._ensure_parameters_list().append(created)
        step['bindings'] = probe_bindings
        self._refresh_parameters_section(select_id=pid)
        self._refresh_step_tooltips()
        self.edit_step(row)
        self.update_modified()
        self.timer.start()
        return True

    def _populate_image_ops_binding_menu(self, row, menu):
        menu.clear()
        if self.recipe is None or not 0 <= row < len(self.recipe['steps']):
            return
        step = self.recipe['steps'][row]
        op = step['op']
        params_by_id = {p['id']: p for p in self.recipe.get('parameters', ())}
        bound_fields = step.get('bindings') or {}
        op_params = self.definitions[op]['parameters']
        added = False
        for key, spec in op_params.items():
            if not is_bindable_field(op, key, step, self.definitions):
                continue
            added = True
            label = spec.get('label', key.replace('_', ' ').capitalize())
            if key in bound_fields:
                p_label = params_by_id.get(bound_fields[key], {}).get('label', bound_fields[key])
                label = f'{label} ({p_label})'
            sub = menu.addMenu(label)
            self._populate_field_source_menu(row, key, sub)
        if not added:
            none_act = menu.addAction('No bindable fields for this configuration')
            none_act.setEnabled(False)

    def bind_field_to_new_parameter(self, row, key):
        if not self.writable() or self.recipe is None or not 0 <= row < len(self.recipe['steps']):
            return None
        initial = parameter_from_field(self.recipe, row, key, definitions=self.definitions)
        params = list(self.recipe.get('parameters') or ())
        existing_ids = {p['id'] for p in params}

        def validate_create_and_bind(built):
            probe = copy.deepcopy(self.recipe)
            probe.setdefault('parameters', []).append(built)
            bindings = dict(probe['steps'][row].get('bindings') or {})
            bindings[key] = built['id']
            probe['steps'][row]['bindings'] = bindings
            validate_authored(probe)

        dialog = ParameterEditorDialog(
            param=initial,
            existing_ids=existing_ids,
            earlier_params=params,
            locked_type=False,
            validate_callback=validate_create_and_bind,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted or dialog.result_param is None:
            return None
        created = dialog.result_param
        self._ensure_parameters_list().append(created)
        bindings = dict(self.recipe['steps'][row].get('bindings') or {})
        bindings[key] = created['id']
        self.recipe['steps'][row]['bindings'] = bindings
        self._refresh_parameters_section(select_id=created['id'])
        self._refresh_step_tooltips()
        self.edit_step(row)
        self.update_modified()
        self.timer.start()
        return created

    def bind_field_to_parameter(self, row, key, pid):
        if not self.writable() or self.recipe is None or not 0 <= row < len(self.recipe['steps']):
            return False
        probe = copy.deepcopy(self.recipe)
        bindings = dict(probe['steps'][row].get('bindings') or {})
        bindings[key] = pid
        probe['steps'][row]['bindings'] = bindings
        try:
            validate_authored(probe)
        except RecipeError as exc:
            self.error(exc)
            return False
        self.recipe['steps'][row]['bindings'] = bindings
        self._refresh_parameters_section(select_id=pid)
        self._refresh_step_tooltips()
        self.edit_step(row)
        self.update_modified()
        self.timer.start()
        return True

    def unbind_field(self, row, key):
        if not self.writable() or self.recipe is None or not 0 <= row < len(self.recipe['steps']):
            return False
        step = self.recipe['steps'][row]
        bindings = step.get('bindings')
        if not bindings or key not in bindings:
            return False
        del bindings[key]
        if not bindings:
            step.pop('bindings', None)
        self._refresh_parameters_section()
        self._refresh_step_tooltips()
        self.edit_step(row)
        self.update_modified()
        self.timer.start()
        return True

    def _insert_template_token(self, widget, token, *, is_pattern=False, row=None):
        if self.immutable or widget is None:
            return
        widget.insert(token)
        if is_pattern and row is not None:
            self.parameter(row, 'pattern', widget.text())
            self.update_filename_example()
        else:
            self.changed()

    def _populate_pattern_insert_menu(self, row, widget, menu):
        menu.clear()
        for label, token in (
            ('Original filename', '{filename}'),
            ('Image capture date', '{date}'),
            ('Sequence number', '{index}'),
        ):
            act = menu.addAction(label)
            act.triggered.connect(
                lambda checked=False, w=widget, t=token, r=row:
                    self._insert_template_token(w, t, is_pattern=True, row=r)
            )
        compat = compatible_parameters_for_template(
            self.recipe, allow_source_tokens=True, step_index=row
        )
        menu.addSeparator()
        if compat:
            for param in compat:
                token = '{param:' + param['id'] + '}'
                act = menu.addAction(param['label'])
                act.triggered.connect(
                    lambda checked=False, w=widget, t=token, r=row:
                        self._insert_template_token(w, t, is_pattern=True, row=r)
                )
        else:
            none_act = menu.addAction('No compatible questions')
            none_act.setEnabled(False)
        menu.addSeparator()
        new_q = menu.addAction('New question…')
        new_q.triggered.connect(
            lambda checked=False, w=widget, r=row: self._insert_new_pattern_question(r, w)
        )

    def _insert_new_pattern_question(self, row, widget):
        created = self.add_parameter(initial_param={'type': 'text', 'required': True})
        if created is not None:
            self._insert_template_token(
                widget, '{param:' + created['id'] + '}', is_pattern=True, row=row
            )

    def _populate_subfolder_insert_menu(self):
        menu = self.folder_insert_menu
        menu.clear()
        compat = compatible_parameters_for_template(
            self.recipe, allow_source_tokens=False
        )
        if compat:
            for param in compat:
                token = '{param:' + param['id'] + '}'
                act = menu.addAction(param['label'])
                act.triggered.connect(
                    lambda checked=False, t=token:
                        self._insert_template_token(self.folder, t, is_pattern=False)
                )
        else:
            none_act = menu.addAction('No compatible questions')
            none_act.setEnabled(False)

    def show_step_context_menu(self, position):
        if self.immutable or self.recipe is None:
            return
        item = self.steps.itemAt(position)
        if item is None:
            return
        row = self.steps.row(item)
        self.steps.setCurrentRow(row)
        menu = QMenu(self.steps)
        self._populate_step_activation_menu(menu=menu, row=row)
        if not menu.isEmpty():
            menu.exec(self.steps.viewport().mapToGlobal(position))

    def _populate_step_activation_menu(self, menu, row=None):
        menu.clear()
        if self.immutable or self.recipe is None:
            return
        row = self.steps.currentRow() if row is None else row
        if not 0 <= row < len(self.recipe['steps']):
            return
        step = self.recipe['steps'][row]
        enabled = step.get('enabled', True)
        has_cond = step.get('enabled_when') is not None
        params_by_id = {p['id']: p for p in self.recipe.get('parameters', ())}
        is_simple_ask = self._simple_boolean_condition_pid(step, params_by_id) is not None

        act_always = menu.addAction('Always')
        act_always.setCheckable(True)
        act_always.setChecked(enabled and not has_cond)
        act_always.triggered.connect(lambda checked=False, r=row: self.set_step_always_enabled(r))

        act_disabled = menu.addAction('Never')
        act_disabled.setCheckable(True)
        act_disabled.setChecked(enabled is False)
        act_disabled.triggered.connect(lambda checked=False, r=row: self.set_step_disabled(r))

        menu.addSeparator()

        act_ask = menu.addAction('Ask when running')
        act_ask.setCheckable(True)
        act_ask.setChecked(is_simple_ask)
        act_ask.triggered.connect(lambda checked=False, r=row: self.quick_ask_when_running_step(r))

        act_cond = menu.addAction('Only when a condition is met…')
        act_cond.setCheckable(True)
        act_cond.setChecked(enabled and has_cond and not is_simple_ask)
        act_cond.triggered.connect(lambda checked=False, r=row: self.configure_step_activation(r))

    def _on_step_run_mode_changed(self, row, mode):
        if self.loading or self.immutable or self.recipe is None:
            return
        if not 0 <= row < len(self.recipe['steps']):
            return
        if mode == 'always':
            self.set_step_always_enabled(row)
        elif mode == 'never':
            self.set_step_disabled(row)
        elif mode == 'ask':
            self.quick_ask_when_running_step(row)
        elif mode == 'condition':
            if not self.configure_step_activation(row):
                self.edit_step(row)

    def _on_step_run_question_changed(self, row, pid):
        if self.loading or self.immutable or self.recipe is None:
            return
        if not 0 <= row < len(self.recipe['steps']):
            return
        if pid == '__new__':
            if self.ask_when_running_step(row) is None:
                self.edit_step(row)
            return
        if not isinstance(pid, str) or not pid:
            return
        probe = copy.deepcopy(self.recipe)
        probe['steps'][row]['enabled'] = True
        probe['steps'][row]['enabled_when'] = {'param': pid, 'equals': True}
        try:
            validate_authored(probe)
        except RecipeError as exc:
            self.error(exc)
            self.edit_step(row)
            return
        self.recipe['steps'][row]['enabled'] = True
        self.recipe['steps'][row]['enabled_when'] = {'param': pid, 'equals': True}
        self._refresh_parameters_section(select_id=pid)
        self.reload_steps(row)
        self.update_modified()
        self.timer.start()

    def _on_step_run_default_changed(self, pid, default_val):
        if self.loading or self.immutable or self.recipe is None:
            return
        params = self.recipe.get('parameters') or []
        param = next((p for p in params if p['id'] == pid), None)
        if param is None:
            return
        probe = copy.deepcopy(self.recipe)
        p_copy = next(p for p in probe['parameters'] if p['id'] == pid)
        if default_val is None:
            p_copy.pop('default', None)
        else:
            p_copy['default'] = bool(default_val)
        try:
            validate_authored(probe)
        except RecipeError as exc:
            self.error(exc)
            row = self.steps.currentRow()
            if row >= 0:
                self.edit_step(row)
            return
        if default_val is None:
            param.pop('default', None)
        else:
            param['default'] = bool(default_val)
        self._refresh_parameters_section(select_id=pid)
        self.update_modified()
        self.timer.start()

    def quick_ask_when_running_step(self, row):
        """Enable simple Yes/No 'Ask when running' activation directly without the advanced condition editor."""
        if not self.writable() or not 0 <= row < len(self.recipe['steps']):
            return None
        step = self.recipe['steps'][row]
        params = list(self.recipe.get('parameters') or ())
        params_by_id = {p['id']: p for p in params}
        existing_simple = self._simple_boolean_condition_pid(step, params_by_id)
        if existing_simple is not None:
            return params_by_id[existing_simple]

        op_label = _display_op_label(step['op'], self.definitions)
        # Derive a natural sentence-case question label.
        derived_labels = {
            'metadata.strip_gps': 'Remove GPS metadata',
            'image.resize': 'Resize images to fit',
            'image.auto_orient': 'Auto-orient images',
            'metadata.strip_all': 'Remove all metadata',
        }
        q_label = derived_labels.get(step['op'], op_label)

        # Reuse an existing matching boolean parameter if one already exists.
        match = next(
            (
                p for p in params
                if p.get('type') == 'boolean'
                and p['label'].casefold() in (q_label.casefold(), op_label.casefold())
            ),
            None,
        )
        probe = copy.deepcopy(self.recipe)
        if match is not None:
            chosen = match
            created = None
        else:
            existing_ids = {p['id'] for p in params}
            created = {
                'id': generate_parameter_id(q_label, existing_ids),
                'label': q_label,
                'type': 'boolean',
                'default': True,
            }
            chosen = created
            probe.setdefault('parameters', []).append(created)

        probe['steps'][row]['enabled'] = True
        probe['steps'][row]['enabled_when'] = {'param': chosen['id'], 'equals': True}
        try:
            validate_authored(probe)
        except RecipeError as exc:
            self.error(exc)
            self.edit_step(row)
            return None

        if created is not None:
            self._ensure_parameters_list().append(created)
        step['enabled'] = True
        step['enabled_when'] = {'param': chosen['id'], 'equals': True}
        self._refresh_parameters_section(select_id=chosen['id'])
        self.reload_steps(row)
        self.update_modified()
        self.timer.start()
        return chosen

    def set_step_always_enabled(self, row):
        if not self.writable() or not 0 <= row < len(self.recipe['steps']):
            return False
        probe = copy.deepcopy(self.recipe)
        probe['steps'][row]['enabled'] = True
        probe['steps'][row].pop('enabled_when', None)
        try:
            if is_parameterized(probe):
                validate_authored(probe)
        except RecipeError as exc:
            self.error(exc)
            self.edit_step(row)
            return False
        self.recipe['steps'][row]['enabled'] = True
        self.recipe['steps'][row].pop('enabled_when', None)
        self._refresh_parameters_section()
        self.reload_steps(row)
        self.update_modified()
        self.timer.start()
        return True

    def set_step_disabled(self, row):
        if not self.writable() or not 0 <= row < len(self.recipe['steps']):
            return False
        self.recipe['steps'][row]['enabled'] = False
        self.recipe['steps'][row].pop('enabled_when', None)
        self._refresh_parameters_section()
        self.reload_steps(row)
        self.update_modified()
        self.timer.start()
        return True

    def ask_when_running_step(self, row):
        if not self.writable() or not 0 <= row < len(self.recipe['steps']):
            return None
        step = self.recipe['steps'][row]
        op_label = _display_op_label(step['op'], self.definitions)
        params = list(self.recipe.get('parameters') or ())
        existing_ids = {p['id'] for p in params}
        suggested = {
            'label': op_label,
            'type': 'boolean',
            'default': True,
        }

        def validate_cond_param(built):
            if built['type'] != 'boolean':
                raise RecipeError('Ask when running for an operation requires a Yes / No question.')
            probe = copy.deepcopy(self.recipe)
            probe.setdefault('parameters', []).append(built)
            probe['steps'][row]['enabled'] = True
            probe['steps'][row]['enabled_when'] = {'param': built['id'], 'equals': True}
            validate_authored(probe)

        dialog = ParameterEditorDialog(
            param=suggested,
            existing_ids=existing_ids,
            earlier_params=params,
            locked_type=True,
            validate_callback=validate_cond_param,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted or dialog.result_param is None:
            return None
        created = dialog.result_param
        self._ensure_parameters_list().append(created)
        step['enabled'] = True
        step['enabled_when'] = {'param': created['id'], 'equals': True}
        self._refresh_parameters_section(select_id=created['id'])
        self.reload_steps(row)
        self.update_modified()
        self.timer.start()
        return created

    def configure_step_activation(self, row):
        if not self.writable() or not 0 <= row < len(self.recipe['steps']):
            return False
        step = self.recipe['steps'][row]
        op_label = _display_op_label(step['op'], self.definitions)
        params = list(self.recipe.get('parameters') or ())

        def validate_activation(enabled, enabled_when):
            probe = copy.deepcopy(self.recipe)
            probe['steps'][row]['enabled'] = enabled
            if enabled_when is None:
                probe['steps'][row].pop('enabled_when', None)
            else:
                probe['steps'][row]['enabled_when'] = enabled_when
            if is_parameterized(probe):
                validate_authored(probe)

        dialog = StepActivationDialog(
            step_label=op_label,
            enabled=step.get('enabled', True),
            enabled_when=step.get('enabled_when'),
            available_params=params,
            validate_callback=validate_activation,
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return False
        step['enabled'] = dialog.result_enabled
        if dialog.result_enabled_when is None:
            step.pop('enabled_when', None)
        else:
            step['enabled_when'] = dialog.result_enabled_when
        self._refresh_parameters_section()
        self.reload_steps(row)
        self.update_modified()
        self.timer.start()
        return True

    def current_preview_values(self):
        if self.recipe is None:
            return {}
        return self._preview_values_by_recipe.setdefault(self.recipe['id'], {})

    def open_preview_settings(self):
        if self.recipe is None or not is_parameterized(self.recipe):
            return False
        try:
            validate_authored(self.recipe)
        except RecipeError as exc:
            self.error(exc)
            return False
        dialog = PreviewSettingsDialog(
            self.recipe,
            entered_values=self.current_preview_values(),
            parent=self,
        )
        if dialog.exec() != QDialog.Accepted:
            return False
        # Preview answers stay strictly separate from authored defaults and dirty state.
        self._preview_values_by_recipe[self.recipe['id']] = dialog.entered_values()
        self.update_preview()
        self.update_destination_controls()
        row = self.steps.currentRow()
        if row >= 0:
            self.edit_step(row)
        return True

    def _compile_preview_snapshot(self):
        authored = validate_authored(self.recipe)
        entered = self.current_preview_values()
        state = evaluate_parameters(authored, entered, validated=True)
        if state['errors']:
            return None, 'incomplete', state
        active_ids = {p['id'] for p in state['active']}
        active_entered = {
            pid: copy.deepcopy(val)
            for pid, val in entered.items()
            if pid in active_ids
        }
        concrete = resolve_recipe(authored, active_entered, validated=True)
        return concrete, 'ready', state

    def load_dev_draft(self, recipe):
        """Load an explicit temporary development draft without touching recipes.json."""
        draft = copy.deepcopy(recipe)
        if not draft.get('id', '').startswith('dev-draft-'):
            draft['id'] = 'dev-draft-' + draft.get('id', uuid.uuid4().hex[:12])
        self.dev_draft_ids.add(draft['id'])
        self.draft_ids.add(draft['id'])
        self.users.append(draft)
        self.refresh(len(self.shipped) + len(self.users) - 1)
        self.baseline = copy.deepcopy(draft)
        self.update_modified()

    def new_dev_parameterized_draft(self):
        """Create a fresh temporary parameterized draft in the development harness."""
        if not self.allow_dev_draft_run:
            return
        if not self.protect_unsaved():
            return
        draft = {
            'schema': AUTHORED_SCHEMA,
            'id': 'dev-draft-' + uuid.uuid4().hex[:12],
            'name': 'New Parameterized Draft',
            'description': 'Temporary parameterized Recipe draft created in development mode.',
            'media': 'image',
            'parameters': [],
            'steps': [
                {'op': 'image.auto_orient'},
                {'op': 'image.convert', 'format': 'jpeg', 'quality': 95},
                {'op': 'file.rename_output', 'pattern': '{filename}_export'},
            ],
            'destination': {'mode': 'beside'},
        }
        self.load_dev_draft(draft)

    def refresh_examples(self):
        previous = self.example_selector.currentData()
        samples = self.files if self.example_files is None else self.example_files
        # Bound retained headers to the currently selected example collection.
        allowed = {str(Path(sample).absolute()) for sample in samples}
        self.checked_inputs = {
            path: entry for path, entry in self.checked_inputs.items()
            if path in allowed
        }
        self.example_selector.blockSignals(True)
        self.example_selector.clear()
        for sample in samples:
            self.example_selector.addItem(Path(sample).name, sample)
        if previous in samples:
            self.example_selector.setCurrentIndex(samples.index(previous))
        self.example_selector.blockSignals(False)
        self.reset_examples.setVisible(self.example_files is not None)

    def set_examples(self, files):
        self.example_files = None if files is None else list(files)
        self.refresh_examples()
        self.update_preview()

    def choose_examples(self):
        files = choose_images(self, title='Choose Example Images',
                               extensions=RECIPE_IMAGE_EXTENSIONS, accept_label='Use Example Images')
        if files:
            self.set_examples(files)

    def show_preview_fields(self, fields):
        # Display every existing planner field exactly once.
        fields = list(fields)
        self.preview_guidance_panel.setVisible(False)
        self.table.set_fields(fields)

        empty = (
            not self.example_selector.currentData()
            and not any(
                name == 'Validation problem'
                for name, value in fields
            )
        )

        self.table.setVisible(not empty)
        self.preview_tools.setVisible(not empty)
        self.empty_preview.setVisible(empty)

    def refresh_inherited_parameters(self):
        row = self.steps.currentRow()
        if row < 0:
            return
        step = self.recipe['steps'][row]
        for key, spec in self.definitions[step['op']]['parameters'].items():
            if spec.get('settings_key') and step.get(key) is None:
                widget = self.parameter_widgets[key]
                widget.blockSignals(True)
                value = self.media_handler.parameter_value(step,key)
                if isinstance(widget,QSpinBox): widget.setValue(value)
                else: widget.setText(value)
                widget.blockSignals(False)
        self.update_parameter_modes(row)

    def update_preview(self, *args):
        self.update_filename_example()
        if self.recipe is None:
            return
        self.preview_generation += 1
        if self.preview_worker is not None:
            self.preview_pending = True
            self.preview_worker.requestInterruption()
            return
        sample = self.example_selector.currentData()
        self.warning_view.set_rows([])
        fields = [('Source image', str(sample) if sample else 'Choose an example image')]
        try:
            if is_parameterized(self.recipe):
                concrete, state_kind, _ = self._compile_preview_snapshot()
                if state_kind == 'incomplete' or concrete is None:
                    self._preview_expected_snapshot = None
                    self._preview_step_active = {}
                    self._refresh_step_tooltips()
                    self.status.clear()
                    self.table.setVisible(False)
                    self.preview_tools.setVisible(False)
                    self.empty_preview.setVisible(False)
                    self.preview_guidance_panel.setVisible(True)
                    return
                self._preview_step_active = {
                    i: step.get('enabled', True)
                    for i, step in enumerate(concrete['steps'])
                }
                self._refresh_step_tooltips()
                preview_recipe = concrete
            else:
                self._preview_step_active = {}
                authored = validate_authored(self.recipe)
                preview_recipe = resolve_recipe(authored, {}, validated=True)

            if not sample:
                validate(preview_recipe)
                self.refresh_inherited_parameters()
                self.media_handler.validate_context(preview_recipe['steps'])
                self._preview_expected_snapshot = copy.deepcopy(preview_recipe)
                self.status.clear()
                self.show_preview_fields(fields + [('Originals', 'Not being changed')])
                return
            index = self.files.index(sample) + 1 if sample in self.files else 1
            self.refresh_inherited_parameters()
            self._preview_expected_snapshot = copy.deepcopy(preview_recipe)
            worker = ExamplePreviewWorker(preview_recipe,sample,index,self.preview_generation,self,
                                          checked_inputs=self.checked_inputs)
            self.preview_worker = worker
            self.status.setText('Validating recipe…'); self.show_preview_fields(fields)
            self.cancel_preview.setVisible(True)
            worker.stage_changed.connect(self.preview_stage)
            worker.finished.connect(self.preview_finished)
            worker.start()
        except (OSError, RecipeError, UnicodeError) as exc:
            self._preview_expected_snapshot = None
            self.status.setText(str(exc))
            self.show_preview_fields(fields + [('Validation problem', str(exc)), ('Originals', 'Not being changed')])

    def preview_stage(self, message):
        worker = self.sender()
        if worker.generation == self.preview_generation and worker.recipe == self._preview_expected_snapshot:
            self.status.setText(message + '…')

    def preview_finished(self):
        worker = self.preview_worker; self.preview_worker = None
        self.cancel_preview.setVisible(False)
        if worker is None:
            return
        current = (
            worker.generation == self.preview_generation
            and worker.recipe == self._preview_expected_snapshot
            and worker.sample == self.example_selector.currentData()
        )
        if current and worker.row is not None and not worker.isInterruptionRequested():
            # Accept cache observations only from the current completed preview.
            self.checked_inputs.update(worker.checked_inputs)
            self.show_preview_fields(property_fields(worker.recipe,worker.row))
            self.warning_view.set_rows([worker.row])
            # The Planned output summary already shows the
            # blocking problem. Do not repeat it above the summary.
            self.status.setText('')
        worker.deleteLater()
        if self.preview_closing:
            dialog = self.window()
            callback = (
                dialog.accept
                if getattr(dialog, 'run_request', None) is not None
                else dialog.close
            )
            QTimer.singleShot(0, callback)
        elif self.preview_pending:
            self.preview_pending = False; self.update_preview()

    def stop_preview(self):
        self.preview_generation += 1; self.preview_pending = False
        if self.preview_worker is not None: self.preview_worker.requestInterruption()
        self.status.setText('Preview cancelled. Change a step or example image to retry.')

    def error(self, exc):
        QMessageBox.warning(self, 'Recipes', str(exc))

    def load_photos_and_run(self, files=None):
        is_dev_draft = (
            self.allow_dev_draft_run
            and self.recipe is not None
            and self.recipe['id'] in self.dev_draft_ids
        )
        if is_dev_draft:
            try:
                snapshot = copy.deepcopy(validate_authored(self.recipe))
            except (OSError, RecipeError) as exc:
                self.error(exc)
                return
            if files is None:
                files = choose_images(
                    self,
                    title='Choose images for Recipe',
                    extensions=RECIPE_IMAGE_EXTENSIONS,
                    accept_label='Use Selected Images'
                )
            else:
                files = list(files)
            if not files:
                return
            try:
                # Explicitly unsaved temporary development draft: never masquerades
                # as a saved Recipe, always enters Runner contextual Settings and
                # mandatory Review Changes before execution.
                self.run_dialog = RunRecipeDialog(
                    snapshot, files, self.folders, self
                )
                self.run_dialog.exec()
                self.run_dialog = None
            except (OSError, RecipeError) as exc:
                self.error(exc)
            return

        if not self.protect_unsaved(): return
        if not self.immutable and self.is_dirty():
            # Save clears dirty state; reaching here means Discard was selected.
            if self.recipe['id'] in self.draft_ids:
                draft_id = self.recipe['id']
                self.users = [r for r in self.users if r['id'] != draft_id]
                self.draft_ids.discard(draft_id)
                self.refresh()
            else:
                self.select(self.active_index, force=True)
        snapshot = copy.deepcopy(self.recipe)
        if files is None:
            files = choose_images(
                self,
                title='Choose images for Recipe',
                extensions=RECIPE_IMAGE_EXTENSIONS,
                accept_label='Use Selected Images'
            )
        else:
            # Preserve the image selection supplied when the Editor opened.
            files = list(files)
        if not files: return

        if self.from_run:
            dialog = self.window()

            dialog.run_request = (
                copy.deepcopy(snapshot),
                list(files),
                copy.deepcopy(self.baseline)
            )

            dialog.accept()
            return

        try:
            self.run_dialog = RunRecipeDialog(
                snapshot, files, self.folders, self,
                saved_baseline=copy.deepcopy(self.baseline)
            )
            self.run_dialog.exec()
            final_files = list(self.run_dialog.files)
            self.run_dialog = None
            self.set_selected_files(final_files)
        except (OSError, RecipeError) as exc:
            self.run_dialog = None
            self.error(exc)

    def set_selected_files(self, files):
        self.files = list(files)
        if self.example_files is None:
            self.refresh_examples()
            self.update_preview()
        dialog = self.window()
        if dialog is not None and hasattr(dialog, 'sync_selected_images'):
            dialog.sync_selected_images()

    def offer_recipe_repair(self, files, chosen):
        self.repair_inputs=(list(files),chosen)
        if not hasattr(self,'repair_return'):
            self.repair_explanation=QLabel('Photoshop files need Convert Format. Add it and choose an output format. '
                'For a built-in recipe, choose Duplicate to Edit first.')
            self.repair_explanation.setWordWrap(True)
            self.repair_return=QPushButton('Return to recipe runner')
            self.repair_return.clicked.connect(self.resume_recipe_repair)
            self.layout().insertWidget(0,self.repair_return); self.layout().insertWidget(0,self.repair_explanation)
        self.repair_return.show(); self.repair_explanation.show()

    def resume_recipe_repair(self):
        if self.repair_inputs is None or not self.protect_unsaved(): return
        if not self.immutable and self.is_dirty():
            # Discard must restore the stored recipe, just as Load Photos does.
            if self.recipe['id'] in self.draft_ids:
                self.users=[r for r in self.users if r['id']!=self.recipe['id']]
                self.draft_ids.discard(self.recipe['id']); self.refresh()
            else: self.select(self.active_index,force=True)
        files,chosen=self.repair_inputs; self.repair_inputs=None
        self.repair_return.hide(); self.repair_explanation.hide()
        self.run_dialog=RunRecipeDialog(copy.deepcopy(self.recipe),files,self.folders,self,chosen=chosen)
        self.run_dialog.exec(); self.run_dialog=None

    def prepare_close(self):
        if self.run_dialog is not None and (self.run_dialog.worker is not None or self.run_dialog.preflight_worker is not None):
            self.run_dialog.reject(); return False
        if not self.preview_closing and not self.protect_unsaved(): return False
        if self.preview_worker is not None:
            self.stop_preview(); self.preview_closing = True
            return False
        return True


class RecipeDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.run_request = None

    def accept(self):
        if self.widget.prepare_close():
            super().accept()

    def reject(self):
        self.run_request = None
        if self.widget.prepare_close():
            super().reject()

    def closeEvent(self, event):
        self.run_request = None
        if self.widget.prepare_close():
            event.accept()
        else:
            event.ignore()


def make_editor_dialog(parent=None, from_run=False, files=(), recipe=None, repair=False, *, dev_draft=None):
    dialog = RecipeDialog(parent); dialog.setWindowTitle('KIMng - Recipe Editor'); dialog.resize(1160, 700)
    layout = QVBoxLayout(dialog)
    if repair:
        hint=QLabel('Photoshop files need Convert Format. Add it and choose an output format. '
                    'For a built-in recipe, choose Duplicate to Edit first. Original PSDs stay unchanged.')
        hint.setWordWrap(True); layout.addWidget(hint); dialog.repair_hint=hint
    allow_dev = dev_draft is not None
    widget = RecipeWidget(files, dialog, from_run=from_run, allow_dev_draft_run=allow_dev); dialog.widget = widget; layout.addWidget(widget)
    if dev_draft is not None:
        widget.load_dev_draft(dev_draft)
    elif recipe is not None:
        recipes=widget.shipped+widget.users
        index=next((i for i,r in enumerate(recipes) if r['id']==recipe['id']),None)
        if index is None:
            widget.append_recipe(copy.deepcopy(recipe))
        elif index < len(widget.shipped):
            widget.select(index)
        else:
            # A Run opened from an editor can contain an unsaved snapshot.
            # Load it as dirty against the stored baseline; Save/Discard remains
            # the existing editor's responsibility, never this launch hook's.
            baseline=copy.deepcopy(recipes[index])
            widget.users[index-len(widget.shipped)]=copy.deepcopy(recipe)
            widget.refresh(index); widget.baseline=baseline; widget.update_modified()
    from kim_dialog_buttons import style_button

    buttons = QHBoxLayout()

    if from_run:
        back = QPushButton('Back')
        style_button(back, 'back')
        back.clicked.connect(dialog.accept)
        buttons.addWidget(back)

    if allow_dev:
        new_dev_btn = QPushButton(QIcon.fromTheme('document-new'), 'New temporary draft')
        new_dev_btn.setToolTip('Create a fresh temporary parameterized draft (not saved to the library)')
        new_dev_btn.clicked.connect(widget.new_dev_parameterized_draft)
        dialog.new_dev_draft_button = new_dev_btn
        buttons.addWidget(new_dev_btn)

    buttons.addStretch(1)

    # Keep the original image selection separate from the example-image dropdown
    # used only for preview, while keeping footer buttons synced if selection changes.
    dialog.choose_other_button = QPushButton('Choose other images && run…')
    style_button(dialog.choose_other_button, 'review')
    dialog.choose_other_button.clicked.connect(
        lambda checked=False: widget.load_photos_and_run()
    )
    buttons.addWidget(dialog.choose_other_button)

    dialog.run_selected_button = QPushButton()
    style_button(dialog.run_selected_button, 'apply')
    dialog.run_selected_button.clicked.connect(
        lambda checked=False: widget.load_photos_and_run(list(widget.files))
    )
    buttons.addWidget(dialog.run_selected_button)

    dialog.choose_images_button = QPushButton('Choose images && run…')
    style_button(dialog.choose_images_button, 'apply')
    dialog.choose_images_button.clicked.connect(
        lambda checked=False: widget.load_photos_and_run()
    )
    buttons.addWidget(dialog.choose_images_button)

    def sync_selected_images():
        count = len(widget.files)
        has_selected = count > 0
        dialog.choose_other_button.setVisible(has_selected)
        dialog.run_selected_button.setVisible(has_selected)
        dialog.choose_images_button.setVisible(not has_selected)
        if has_selected:
            dialog.run_selected_button.setText(
                f'Run with {count} selected image' + ('' if count == 1 else 's')
            )

    dialog.sync_selected_images = sync_selected_images
    dialog.sync_selected_images()

    if not from_run:
        close = QPushButton('Close')
        style_button(close, 'cancel')
        close.clicked.connect(dialog.accept)
        buttons.addWidget(close)

    layout.addLayout(buttons)
    return dialog


def launch(files=()):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    try:
        dialog = make_editor_dialog(files=files)
    except (OSError, RecipeError) as exc:
        QMessageBox.critical(None, 'Recipes', str(exc)); return 1
    dialog.exec()
    return 0


if __name__ == '__main__':
    raise SystemExit(launch(sys.argv[1:]))
