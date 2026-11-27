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
    QProgressDialog, QHeaderView, QGroupBox, QSplitter, QSizePolicy, QToolButton, QTreeWidget, QTreeWidgetItem, QDialogButtonBox, QMenu, QScrollArea, QStyle,
    QDateEdit, QTimeEdit, QDoubleSpinBox, QTextEdit)
from kim_recipe_core import (folder_label, folder_path, builtin_category, RecipeError, builtins,
                             save_users, load_users, load_library, save_library, read_portable_recipe, write_portable_recipe, read_recipe_bundle, write_recipe_bundle, merge_recipe_bundle, RecipeLibrary, library_groups, recipe_title, validate, preview, execute, handler, format_output_pattern, display_output_pattern)


from kim_recipe_run import RunRecipeDialog, RecipeWorker, PropertyView, property_fields, WarningView


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


class OperationPicker(QDialog):
    """One view of the handler's definitions; IDs and parameter data stay shared."""
    def __init__(self, definitions, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Add Operation'); self.resize(570, 480)
        self.definitions = definitions; self.operation_id = None
        layout = QVBoxLayout(self)
        self.search = QLineEdit(); self.search.setPlaceholderText('Search operations…')
        self.search.setAccessibleName('Search operations by name or keyword'); layout.addWidget(self.search)
        self.tree = QTreeWidget(); self.tree.setHeaderHidden(True)
        self.tree.setAccessibleName('Operations grouped by category'); layout.addWidget(self.tree, 1)
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
                          all(word in (category+' '+d['label']+' '+d.get('keywords','')+' '+d.get('description','')).casefold() for word in query)]
            if not operations: continue
            group = QTreeWidgetItem([category]); group.setFlags(group.flags() & ~Qt.ItemIsSelectable)
            self.tree.addTopLevelItem(group)
            for op, definition in sorted(operations, key=lambda item:item[1]['label'].casefold()):
                item = QTreeWidgetItem([definition['label']]); item.setData(0,Qt.UserRole,op)
                item.setToolTip(0,definition.get('description',definition['label'])); group.addChild(item)
                if first is None: first = item
            group.setExpanded(True)
        self.tree.setCurrentItem(first); self.selection_changed()

    def selection_changed(self,*_):
        item = self.tree.currentItem()
        self.operation_id = item.data(0,Qt.UserRole) if item else None
        self.add.setEnabled(bool(self.operation_id))

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



class RecipeWidget(QWidget):
    """Embeddable manager; files are optional and preview is always text-only."""
    def __init__(self, files=(), parent=None, from_run=False):
        super().__init__(parent)
        self.files = list(files)
        self.from_run = from_run
        self.draft_ids = set()
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
        self.checked_inputs = {}
        self.loading = False
        root = QVBoxLayout(self)
        self.editor = QWidget(self)
        root.addWidget(self.editor)
        layout = QVBoxLayout(self.editor)
        # Three-panel Recipe Editor:
        # navigation | steps and settings | read-only preview.
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        layout.addWidget(self.splitter)

        navigation = QGroupBox('Recipes')
        center = QWidget()
        right = QGroupBox('Preview')

        navigation.setMinimumWidth(235)
        center.setMinimumWidth(350)
        right.setMinimumWidth(280)

        self.splitter.addWidget(navigation)
        self.splitter.addWidget(center)
        self.splitter.addWidget(right)

        self.splitter.setStretchFactor(0, 2)
        self.splitter.setStretchFactor(1, 4)
        self.splitter.setStretchFactor(2, 3)

        navigation_layout = QVBoxLayout(navigation)
        controls = QVBoxLayout(center)
        controls.setContentsMargins(6, 0, 6, 0)

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

        # Creation actions belong below the Recipe tree.
        creation = QHBoxLayout()
        creation.setSpacing(8)

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

        self.shortcut_legend = QLabel(
            "★  Available in Dolphin's right-click menu"
        )
        self.shortcut_legend.setToolTip(
            'Starred recipes have a saved shortcut in '
            "Dolphin's KIMng Recipes menu."
        )

        navigation_layout.addWidget(self.shortcut_legend)
        navigation_layout.addLayout(creation)

        # Selected-item actions belong below the tree.
        navigation_layout.addSpacing(8)

        self.tree_action_label = QLabel('Selected Recipe')
        navigation_layout.addWidget(self.tree_action_label)

        duplicate = QPushButton(
            QIcon.fromTheme('edit-copy'), 'Duplicate Recipe'
        )
        duplicate.clicked.connect(self.duplicate)
        duplicate.setToolTip('Create an editable Recipe copy')
        navigation_layout.addWidget(duplicate)
        self.management_buttons['Duplicate to Edit'] = duplicate

        self.move_recipe_button = QPushButton(
            QIcon.fromTheme('folder-move'),
            'Move to Folder…'
        )
        self.move_recipe_button.setToolTip(
            'Move the selected Recipe into another folder'
        )
        self.move_recipe_button.clicked.connect(
            lambda checked=False: self.choose_recipe_destination()
        )
        navigation_layout.addWidget(self.move_recipe_button)

        selected_actions = QHBoxLayout()
        selected_actions.setSpacing(8)

        rename = QPushButton(
            QIcon.fromTheme('edit-rename'), 'Rename'
        )
        rename.clicked.connect(
            lambda checked=False: self.rename_selected_tree_item()
        )
        selected_actions.addWidget(rename, 1)
        self.management_buttons['Rename'] = rename

        delete = QPushButton(
            QIcon.fromTheme('edit-delete'), 'Delete'
        )
        delete.clicked.connect(
            lambda checked=False: self.delete_selected_tree_item()
        )
        selected_actions.addWidget(delete, 1)
        self.management_buttons['Delete'] = delete

        navigation_layout.addLayout(selected_actions)

        # Library import/export sits below selected-Recipe actions.
        navigation_layout.addSpacing(10)
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

        # Keep Recipe persistence with the library management controls.
        save = QPushButton(
            QIcon.fromTheme('document-save'), 'Save'
        )
        save.clicked.connect(self.save)
        self.management_buttons['Save'] = save

        name_form = QFormLayout()
        self.name = QLineEdit(); self.name.textEdited.connect(self.changed)
        name_row = QWidget(); name_layout = QHBoxLayout(name_row)
        name_layout.setContentsMargins(0, 0, 0, 0); name_layout.addWidget(self.name, 1)
        self.reset_builtin = QPushButton(QIcon.fromTheme('edit-undo'), 'Reset to Defaults')
        self.reset_builtin.clicked.connect(self.reset_builtin_defaults)
        name_layout.addWidget(self.reset_builtin)
        name_form.addRow('Recipe name', name_row)
        self.library_folder = QComboBox()
        self.library_folder.currentIndexChanged.connect(self.folder_changed)
        name_form.addRow('Recipe folder', self.library_folder)
        self.shortcut_checkbox = QCheckBox(
            "Show in Dolphin's right-click menu"
        )
        self.shortcut_checkbox.setToolTip(
            'When enabled and saved, this recipe appears under '
            'KIMng > Recipes when you right-click selected images '
            'in Dolphin.'
        )
        self.shortcut_checkbox.toggled.connect(self.shortcut_changed)
        name_form.addRow('', self.shortcut_checkbox)
        controls.addLayout(name_form)

        self.description = QTextEdit()
        self.description.setPlaceholderText(
            'Describe what this Recipe does and when to use it.'
        )
        self.description.setAcceptRichText(False)
        self.description.setMinimumHeight(60)
        self.description.setMaximumHeight(95)
        self.description.setAccessibleName('Recipe description')
        self.description.textChanged.connect(self.changed)

        description_label = QLabel('Description')
        description_label.setBuddy(self.description)
        controls.addWidget(description_label)
        controls.addWidget(self.description)

        navigation_layout.insertWidget(
            navigation_layout.indexOf(self.transfer_button),
            self.management_buttons['Save']
        )
        self.recipe_guidance = QLabel(
            'Built-in Recipe. Duplicate to create an editable copy.'
        )
        self.recipe_guidance.setWordWrap(True)
        controls.addWidget(self.recipe_guidance)
        # Keep destination outside the resizable editing workspace.
        # Steps and selected-step settings can now be sized independently.
        self.edit_splitter = QSplitter(Qt.Vertical)
        self.edit_splitter.setChildrenCollapsible(False)
        controls.addWidget(self.edit_splitter, 1)

        steps_section = QWidget()
        steps_section.setMinimumHeight(130)
        steps_layout = QVBoxLayout(steps_section)
        steps_layout.setContentsMargins(0, 0, 0, 0)

        heading = QHBoxLayout()
        heading.addWidget(QLabel('Recipe steps'))
        heading.addStretch(1)
        self.step_count = QLabel()
        heading.addWidget(self.step_count)
        steps_layout.addLayout(heading)

        self.edit_splitter.addWidget(steps_section)

        self.steps = QListWidget()
        self.steps.setAccessibleName('Ordered recipe steps; check to enable')
        self.steps.currentRowChanged.connect(self.edit_step)
        self.steps.itemChanged.connect(self.toggle_step)
        bar = QHBoxLayout()
        self.operation = QPushButton(QIcon.fromTheme('list-add'), 'Add Operation…')
        self.operation.clicked.connect(self.add_step); bar.addWidget(self.operation, 1)
        self.step_buttons = []
        button = QPushButton(QIcon.fromTheme('list-remove'), 'Remove')
        button.clicked.connect(self.remove_step); bar.addWidget(button); self.step_buttons.append(button)
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

        self.parameter_scroll = QScrollArea()
        self.parameter_scroll.setWidgetResizable(True)
        self.parameter_scroll.setFrameShape(QScrollArea.NoFrame)
        self.parameter_scroll.setMinimumHeight(115)
        self.parameter_scroll.setWidget(self.parameters)
        self.edit_splitter.addWidget(self.parameter_scroll)

        self.edit_splitter.setStretchFactor(0, 3)
        self.edit_splitter.setStretchFactor(1, 2)

        self.edit_splitter_settings = None
        self.edit_splitter.setSizes([330, 220])
        self.destination_group = QGroupBox('Destination')
        self.destinations = QFormLayout(self.destination_group)
        self.mode = QComboBox()
        for label, mode in [('Same directory as each original', 'beside'), ('Beside each original', 'subfolder'), ('One directory', 'directory')]:
            self.mode.addItem(label, mode)
        self.folder = QLineEdit(); self.path = QLineEdit()
        self.ask = QCheckBox('Ask for directory on every run')
        self.directory_row = QWidget()
        directory_layout = QHBoxLayout(self.directory_row); directory_layout.setContentsMargins(0, 0, 0, 0)
        directory_layout.addWidget(self.path)
        browse = QPushButton(QIcon.fromTheme('folder-open'), 'Choose…')
        browse.clicked.connect(self.browse); directory_layout.addWidget(browse)
        self.destinations.addRow('Directory', self.mode)
        self.destinations.addRow('Subfolder', self.folder)
        self.destinations.addRow('', self.ask)
        self.destinations.addRow('Directory', self.directory_row)
        controls.addWidget(self.destination_group)
        self.mode.currentIndexChanged.connect(self.changed)
        for widget in (self.folder, self.path):
            widget.textEdited.connect(self.changed)
        self.ask.toggled.connect(self.changed)
        preview_layout = QVBoxLayout(right)
        self.example_selector = QComboBox()
        self.example_selector.setMinimumWidth(0)
        self.example_selector.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.example_selector.currentIndexChanged.connect(self.update_preview)
        preview_layout.addWidget(self.example_selector)
        self.choose_example_button = QPushButton(
            QIcon.fromTheme('document-open'),
            'Choose images for preview…'
        )
        self.choose_example_button.clicked.connect(self.choose_examples)
        preview_layout.addWidget(self.choose_example_button)
        self.reset_examples = QPushButton(QIcon.fromTheme('edit-undo'), 'Reset to Selected Images')
        self.reset_examples.clicked.connect(lambda: self.set_examples(None))
        self.reset_examples.setVisible(False)
        preview_layout.addWidget(self.reset_examples)
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
        safety = QLabel('Originals are not being changed. Outputs are being created as new files.')
        safety.setWordWrap(True); safety.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        preview_layout.addWidget(safety)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.setInterval(300)
        self.timer.timeout.connect(self.update_preview)
        self.selector.currentIndexChanged.connect(lambda i: self.select_id(self.selector.itemData(i)))
        self.selector.activated.connect(lambda i: self.reselect_builtin(self.active_index))
        self.refresh_examples()
        self.refresh()

        # Remember the three independent panel widths.
        self.panel_settings = QSettings('KIMng', 'RecipeEditor')
        saved = self.panel_settings.value('three_panel_sizes')
        sizes = [270, 382, 468]
        if isinstance(saved, (list, tuple)) and len(saved) == 3:
            try:
                candidate = [int(value) for value in saved]
                if all(value > 0 for value in candidate):
                    sizes = candidate
            except (TypeError, ValueError):
                pass
        self.splitter.setSizes(sizes)
        self.splitter.splitterMoved.connect(self.save_panel_sizes)

        stored_inner = self.panel_settings.value(
            'step_settings_splitter', [330, 220]
        )
        try:
            inner_sizes = [int(value) for value in stored_inner]
            if (
                len(inner_sizes) != 2
                or any(value <= 0 for value in inner_sizes)
            ):
                inner_sizes = [330, 220]
        except (TypeError, ValueError):
            inner_sizes = [330, 220]

        self.edit_splitter.setSizes(inner_sizes)
        self.edit_splitter.splitterMoved.connect(
            self.save_step_settings_sizes
        )

    def save_panel_sizes(self, *_):
        self.panel_settings.setValue(
            'three_panel_sizes', self.splitter.sizes()
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
            item.setIcon(0, recipe_icon)
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
            item.setToolTip(
                0,
                recipe['name'] +
                ('\n\n' + recipe['description']
                 if recipe['description'] else '')
            )
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
            'Everyday', 'Hiker', 'Digital asset manager'
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
        if not hasattr(self, 'tree_action_label'):
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
            self.tree_action_label.setText('Selected Folder')
            duplicate.setVisible(False)
            self.move_recipe_button.setVisible(False)

            editable_folder = folder_id not in (
                None, ''
            )

            rename.setText('Rename Folder')
            delete.setText('Delete Folder')
            rename.setEnabled(editable_folder)
            delete.setEnabled(editable_folder)
        else:
            self.tree_action_label.setText('Selected Recipe')
            duplicate.setVisible(True)
            duplicate.setEnabled(self.recipe is not None)
            self.move_recipe_button.setVisible(True)
            self.move_recipe_button.setEnabled(
                self.recipe is not None
                and not self.immutable
            )

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

            imported = validate(imported)

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
            'step_settings_splitter',
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
        self.recipe_guidance.setVisible(self.immutable)
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
        self.mode.setCurrentIndex(self.mode.findData(dest['mode'])); self.folder.setText(dest.get('folder', 'Recipes'))
        self.path.setText(dest.get('path', '')); self.ask.setChecked(dest.get('ask', False))
        self.destination_group.setEnabled(not self.immutable)
        self.operation.setEnabled(not self.immutable)
        for button in self.step_buttons:
            button.setEnabled(not self.immutable)
        for label in ('Rename', 'Delete', 'Save'):
            self.management_buttons[label].setEnabled(not self.immutable)
        self.update_destination_controls()
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
        for step in state['steps']:
            step.setdefault('enabled', True)
            for key, spec in self.definitions[step['op']]['parameters'].items():
                step.setdefault(key, copy.deepcopy(spec['default']))
        return state

    def is_dirty(self):
        return self.recipe is not None and (self.recipe['id'] in self.draft_ids or self.comparable(self.recipe) != self.comparable(self.baseline))

    @staticmethod
    def recipe_tree_label(recipe, dirty=False):
        prefix = '★ ' if recipe.get('dolphin_shortcut') else ''
        suffix = ' *' if dirty else ''
        return prefix + recipe['name'] + suffix

    def update_modified(self):
        dirty = self.is_dirty()
        label = recipe_title(self.recipe, self.folders)
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
        self.management_buttons['Save'].setEnabled(not self.immutable and dirty)
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

    def style_step_item(self, item, enabled):
        # Unchecked steps remain selectable, and must be readable.
        item.setForeground(self.palette().brush(QPalette.Active, QPalette.Text))
        font = item.font()
        font.setItalic(not enabled)
        item.setFont(font)
        item.setToolTip('Enabled in recipe' if enabled else 'Disabled: check this step to include it in the recipe')

    def reload_steps(self, row=0):
        self.steps.blockSignals(True)
        self.steps.clear()
        for step in self.recipe['steps']:
            item = QListWidgetItem(self.media_handler.step_label(step))
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if step.get('enabled', True) else Qt.Unchecked)
            self.style_step_item(item, step.get('enabled', True))
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
        self.recipe['steps'][row]['enabled'] = enabled
        self.steps.blockSignals(True)
        self.style_step_item(item, enabled)
        self.steps.blockSignals(False)
        self.update_modified()
        self.timer.start()

    def edit_step(self, row):
        self.update_move_buttons()
        self.parameter_widgets = {}
        self.filename_example = None
        self.parameter_resets = {}
        self.parameter_modes = {}
        self.step_defaults_button = None
        while self.form.rowCount():
            self.form.removeRow(0)
        if self.recipe is None or not 0 <= row < len(self.recipe['steps']):
            return
        step = self.recipe['steps'][row]
        definition = self.definitions[step['op']]
        self.parameters.setTitle(
            'Step settings: ' + definition.get('label', 'Operation')
        )
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
            configure = QPushButton('Configure with image preview…')
            configure.clicked.connect(lambda checked=False, r=row: self.configure_image_operation(r))
            self.form.addRow(configure)
            reset = QPushButton('Reset step defaults'); reset.clicked.connect(self.reset_step_defaults)
            self.form.addRow(reset)
            return
        if step['op'] == 'image.resize':
            sizes = (300,600,800,1024,1280,1400,1600,1920,2048,2560,3440,3840)
            presets = QComboBox(); presets.addItem('Custom bounds',None)
            for size in sizes: presets.addItem(f'{size} × {size}',size)
            presets.setCurrentIndex(presets.findData(step['max_width']) if step['max_width'] == step['max_height'] and step['max_width'] in sizes else 0)
            presets.currentIndexChanged.connect(lambda i,r=row,w=presets:self.resize_preset(r,w.itemData(i)))
            self.form.addRow('Common sizes',presets)
        for key, spec in definitions.items():
            if step['op'] == 'metadata.set_capture' and key in ('timezone','fields'): continue
            try:
                value = self.media_handler.parameter_value(step, key)
            except (OSError, RecipeError) as exc:
                value = spec['default'] if spec['type'] in ('integer','number') else ''
                self.status.setText(str(exc))
            if step['op']=='file.rename_output' and key=='pattern': value=display_output_pattern(value)
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
                widget.textEdited.connect(lambda v, k=key, r=row: self.parameter(r, k, v))
            self.parameter_widgets[key] = widget
            if spec.get('settings_key'):
                field_row = QWidget(); field_layout = QHBoxLayout(field_row)
                field_layout.setContentsMargins(0, 0, 0, 0); field_layout.addWidget(widget, 1)
                reset = QPushButton('Reset from Settings')
                reset.clicked.connect(lambda checked=False, r=row, k=key: self.reset_to_settings(r, k))
                field_layout.addWidget(reset); field_layout.addWidget(HelpButton('settings')); self.parameter_resets[key] = reset
                self.form.addRow(spec.get('label', key), field_row)
                mode = QLabel('')
                self.parameter_modes[key] = mode
                self.form.addRow('', mode)
            else:
                if spec['type'] == 'capture_datetime': self.form.addRow(widget)
                else: self.form.addRow(spec.get('label', key.replace('_', ' ')), widget)
            if step['op']=='file.rename_output' and key=='pattern':
                self.filename_example=QLabel(); self.filename_example.setTextFormat(Qt.PlainText); self.filename_example.setWordWrap(True)
                self.form.addRow('',self.filename_example)
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
        dialog = ImageOperationDialog(self.recipe['steps'][row], files, self,
                                      recipe=self.recipe, row=row)
        sample = self.example_selector.currentData()
        if sample and dialog.images.findData(sample) >= 0:
            dialog.images.setCurrentIndex(dialog.images.findData(sample))
        if dialog.exec() != QDialog.Accepted: return
        replacement = copy.deepcopy(dialog.step)
        if 'enabled' in self.recipe['steps'][row]:
            replacement['enabled'] = self.recipe['steps'][row]['enabled']
        self.recipe['steps'][row] = replacement
        self.reload_steps(row); self.update_modified(); self.update_preview()

    def update_filename_example(self,*_):
        if self.filename_example is None: return
        from kim_recipe_image import FORMATS
        sample=self.example_selector.currentData()
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
        if step['op'] == 'metadata.set_capture':
            self.form.setRowVisible(self.parameter_widgets['datetime'],step['mode'] == 'specific')
            embedded = self.capture_options.zone.findData('embedded')
            self.capture_options.zone.model().item(embedded).setEnabled(step['mode'] == 'embedded')
            if step['mode'] == 'file_mtime': self.capture_options.toggle.setChecked(True)
        if step['op'] == 'image.compress':
            for key in ('quality','png_level'):
                self.parameter_widgets[key].setEnabled(step['preset'] == 'custom')
        if step['op'] != 'image.convert' or row != self.steps.currentRow(): return
        fmt = step['format']
        for key, formats in {'jpeg_progressive':('jpeg',), 'jpeg_optimize':('jpeg',), 'jp2_mode':('jp2',), 'tiff_compression':('tiff',), 'depth':('png','jp2','tiff')}.items():
            if key in self.parameter_widgets: self.form.setRowVisible(self.parameter_widgets[key], fmt in formats)
        self.parameter_widgets['quality'].setEnabled(fmt in ('jpeg','webp','avif','heic','heif','jxl') or (fmt=='jp2' and step.get('jp2_mode','lossless')=='lossy'))
        self.parameter_resets['quality'].setVisible(fmt in ('jpeg','webp','avif'))

    def update_parameter_modes(self, row):
        if row < 0: return
        step = self.recipe['steps'][row]
        for key, label in self.parameter_modes.items():
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
        self.steps.item(row).setText(self.media_handler.step_label(self.recipe['steps'][row]))
        self.steps.blockSignals(False)
        self.update_parameter_modes(row)
        self.update_conversion_controls(row)
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
            self.update_modified()
            self.timer.start()

    def update_destination_controls(self):
        mode = self.mode.currentData()
        self.destinations.setRowVisible(self.folder, mode == 'subfolder')
        self.destinations.setRowVisible(self.ask, mode == 'directory')
        self.destinations.setRowVisible(self.directory_row, mode == 'directory' and not self.ask.isChecked())

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
        message = QMessageBox(self); message.setWindowTitle('Delete recipe folder'); message.setTextFormat(Qt.PlainText)
        message.setText('Delete folder “' + folder['name'] + '”? Its recipes will move to Unfiled; no recipes or images are deleted.')
        message.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel); message.setDefaultButton(QMessageBox.Cancel)
        if message.exec() == QMessageBox.Yes:
            self.change_folders(lambda library: library.delete_folder(folder['id']))

    def new(self):
        if not self.protect_unsaved(): return
        self.append_recipe({'schema': 3, 'id': 'user-' + uuid.uuid4().hex, 'name': 'New Recipe', 'description': '', 'dolphin_shortcut': False,
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
        users = self.users[:]; del users[index]
        try:
            self.store_users(users); self.users = users; self.refresh()
        except (OSError, RecipeError) as exc: self.error(exc)

    def save(self):
        if not self.writable(): return False
        if not self.is_dirty():
            self.status.setText('No unsaved changes.')
            return True
        try:
            recipe = validate(self.recipe)
            index = self.active_index - len(self.shipped)
            users = self.users[:]; users[index] = recipe
            is_new = recipe['id'] in self.draft_ids
            self.draft_ids.discard(recipe['id'])
            try:
                self.store_users(users)
            except Exception:
                if is_new: self.draft_ids.add(recipe['id'])
                raise
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
            del self.recipe['steps'][row]; self.reload_steps(row); self.update_modified(); self.timer.start()

    def move(self, delta):
        if not self.writable(): return
        row = self.steps.currentRow(); target = row + delta
        if 0 <= target < len(self.recipe['steps']):
            steps = self.recipe['steps']; steps[row], steps[target] = steps[target], steps[row]
            self.reload_steps(target); self.update_modified(); self.timer.start()

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
            if not sample:
                validate(self.recipe)
                self.refresh_inherited_parameters()
                self.media_handler.validate_context(self.recipe['steps'])
                self.status.clear()
                self.show_preview_fields(fields + [('Originals', 'Not being changed')])
                return
            index = self.files.index(sample) + 1 if sample in self.files else 1
            self.refresh_inherited_parameters()
            worker = ExamplePreviewWorker(self.recipe,sample,index,self.preview_generation,self,
                                          checked_inputs=self.checked_inputs)
            self.preview_worker = worker
            self.status.setText('Validating recipe…'); self.show_preview_fields(fields)
            self.cancel_preview.setVisible(True)
            worker.stage_changed.connect(self.preview_stage)
            worker.finished.connect(self.preview_finished)
            worker.start()
        except (OSError, RecipeError, UnicodeError) as exc:
            self.status.setText(str(exc))
            self.show_preview_fields(fields + [('Validation problem', str(exc)), ('Originals', 'Not being changed')])

    def preview_stage(self, message):
        worker = self.sender()
        if worker.generation == self.preview_generation and worker.recipe == self.recipe:
            self.status.setText(message + '…')

    def preview_finished(self):
        worker = self.preview_worker; self.preview_worker = None
        self.cancel_preview.setVisible(False)
        current = (worker.generation == self.preview_generation and worker.recipe == self.recipe
                   and worker.sample == self.example_selector.currentData())
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
            QTimer.singleShot(0,self.window().close)
        elif self.preview_pending:
            self.preview_pending = False; self.update_preview()

    def stop_preview(self):
        self.preview_generation += 1; self.preview_pending = False
        if self.preview_worker is not None: self.preview_worker.requestInterruption()
        self.status.setText('Preview cancelled. Change a step or example image to retry.')

    def error(self, exc):
        QMessageBox.warning(self, 'Recipes', str(exc))

    def load_photos_and_run(self, files=None):
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
                list(files)
            )

            dialog.accept()
            return

        try:
            self.run_dialog = RunRecipeDialog(snapshot, files, self.folders, self)
            self.run_dialog.exec()
            self.run_dialog = None
        except (OSError, RecipeError) as exc:
            self.error(exc)

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
    def accept(self):
        if self.widget.prepare_close():
            super().accept()

    def reject(self):
        if self.widget.prepare_close():
            super().reject()

    def closeEvent(self, event):
        if self.widget.prepare_close():
            event.accept()
        else:
            event.ignore()


def make_editor_dialog(parent=None, from_run=False, files=(), recipe=None, repair=False):
    dialog = RecipeDialog(parent); dialog.setWindowTitle('KIMng - Recipe Editor'); dialog.resize(1150, 850)
    layout = QVBoxLayout(dialog)
    if repair:
        hint=QLabel('Photoshop files need Convert Format. Add it and choose an output format. '
                    'For a built-in recipe, choose Duplicate to Edit first. Original PSDs stay unchanged.')
        hint.setWordWrap(True); layout.addWidget(hint); dialog.repair_hint=hint
    widget = RecipeWidget(files, dialog, from_run=from_run); dialog.widget = widget; layout.addWidget(widget)
    if recipe is not None:
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

    buttons.addStretch(1)

    # Keep the original Dolphin selection separate from the
    # example-image dropdown used only for preview.
    selected_images = list(widget.files)

    if selected_images:
        choose_other = QPushButton('Choose other images && run…')
        style_button(choose_other, 'review')
        choose_other.clicked.connect(lambda checked=False: widget.load_photos_and_run())
        buttons.addWidget(choose_other)

        count = len(selected_images)
        selected_label = (
            f'Run with {count} selected image'
            + ('' if count == 1 else 's')
        )
        run_selected = QPushButton(selected_label)
        style_button(run_selected, 'apply')
        run_selected.clicked.connect(
            lambda checked=False: widget.load_photos_and_run(
                selected_images
            )
        )
        buttons.addWidget(run_selected)

    else:
        choose = QPushButton('Choose images && run…')
        style_button(choose, 'apply')
        choose.clicked.connect(lambda checked=False: widget.load_photos_and_run())
        buttons.addWidget(choose)

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
