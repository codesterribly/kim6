#!/usr/bin/env python3
"""KIMng persistent settings and About dialog."""
from kim_dialog_buttons import style_button, style_button_box
from kim_manual_viewer import add_history_controls, current_guide_url

import os
import re
import sys
import tempfile
from pathlib import Path
from kim_settings_file import read_settings
from kim_metadata_sources import MetadataSourcePreferences, SOURCE_PRIORITY_DEFAULT

from PySide6.QtCore import QLocale, QSettings, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSpinBox, QTabWidget, QTextEdit, QTextBrowser, QLineEdit, QCheckBox, QGroupBox,
    QVBoxLayout, QWidget, QScrollArea, QListWidget,
)

# Logical action label, Settings description, preview extension, separator.
AFFIX_ITEMS = (
    ('compressed', 'Compression', 'jpg', '_'),
    ('resized', 'Resize', 'jpg', '_'),
    ('web', 'Web export', 'jpg', '_'),
    ('rotated', 'Rotate', 'jpg', '_'),
    ('auto_rotated', 'Auto-rotate', 'jpg', '_'),
    ('flipped_horizontal', 'Flip horizontally', 'jpg', '_'),
    ('flipped_vertical', 'Flip vertically', 'jpg', '_'),
    ('stripped', 'Remove all metadata', 'jpg', '_'),
    ('gps', 'Remove GPS metadata', 'jpg', '_'),
    ('ai', 'Remove AI metadata', 'jpg', '_'),
    ('copyright', 'Copyright information', 'jpg', '_'),
    ('timeshift', 'Shift image capture time', 'jpg', '_'),
    ('datesync', 'Synchronize dates', 'jpg', '_'),
    ('transcoded', 'Video transcode', 'mp4', '-'),
    ('frame', 'Extract video frame', 'png', '_'),
    ('thumbnail', 'Video thumbnail', 'jpg', '_'),
    ('contact-sheet', 'Video contact sheet', 'jpg', '_'),
    ('audio', 'Extract audio', 'mp3', '-'),
    ('muted', 'Remove video audio', 'mp4', '-'),
    ('animated', 'GIF from video', 'gif', '_'),
    ('slideshow', 'Slideshow from images', 'mp4', '_'),
)
AFFIX_DEFAULTS = {
    "KIM_AFFIX_" + tag.upper().replace("-", "_"): tag
    for tag, _description, _extension, _separator in AFFIX_ITEMS
}
AFFIX_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,31}\Z")


def system_location_units():
    # Qt follows the desktop's regional measurement setting.
    try:
        if QLocale.system().measurementSystem() in (QLocale.ImperialUSSystem, QLocale.ImperialUKSystem):
            return 'imperial'
    except (AttributeError, RuntimeError): pass
    return 'metric'


def location_unit_choices():
    system = system_location_units()
    other = 'metric' if system == 'imperial' else 'imperial'
    return [('System (' + system.title() + ')', 'system'), (other.title(), other)]


def location_unit_selection(value):
    # A legacy explicit choice equal to today's system becomes Follow System.
    return 'system' if value == system_location_units() else value


DEFAULTS = {
    "KIM_POLICY": "prompt",
    "KIM_LOCATION_UNITS": "system",
    "KIM_LOCATION_ONLINE_MAPS": "no",
    "KIM_NAME_AFFIX_POSITION": "suffix",
    **AFFIX_DEFAULTS,
    "KIM_WEB_QUALITY_JPEG": "95",
    "KIM_WEB_QUALITY_WEBP": "95",
    "KIM_WEB_QUALITY_AVIF": "95",
    "KIM_COPYRIGHT_CREATOR": "",
    "KIM_COPYRIGHT_NOTICE": "",
    "KIM_COPYRIGHT_USAGE_RIGHTS": "",
}

VALID_POLICIES = {"prompt", "create"}
VALID_AFFIXES = {"prefix", "suffix"}


def config_path():
    base = Path(
        os.environ.get("XDG_CONFIG_HOME")
        or str(Path.home() / ".config")
    )
    return base / "kimng" / "settings.conf"


def load_settings(path):
    settings = DEFAULTS.copy()

    for key, value in read_settings(path):
        if key not in settings:
            continue

        if key.startswith("KIM_COPYRIGHT_"):
            if len(value) <= 500 and not any(
                char in value for char in ("\r", "\n", "\x00")
            ):
                settings[key] = value
            continue
        if key == "KIM_POLICY" and value in VALID_POLICIES:
            settings[key] = value
        elif key == "KIM_LOCATION_UNITS" and value in {"system", "imperial", "metric"}:
            settings[key] = value
        elif key == "KIM_LOCATION_ONLINE_MAPS" and value in {"yes", "no"}:
            settings[key] = value
        elif key == "KIM_NAME_AFFIX_POSITION" and value in VALID_AFFIXES:
            settings[key] = value
        elif key in AFFIX_DEFAULTS and AFFIX_PATTERN.fullmatch(value):
            settings[key] = value
        elif key.startswith("KIM_WEB_QUALITY_"):
            if value.isascii() and value.isdecimal():
                number = int(value)
                if 1 <= number <= 100:
                    settings[key] = str(number)
    return settings


def save_settings(path, settings):
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_symlink():
        raise ValueError("Refusing a symbolic-link settings file.")

    payload = (
        "# KIMng user preferences\n"
        "# Environment variables take precedence.\n"
        + "".join(
            f"{key}={settings[key]}\n"
            for key in DEFAULTS
        )
    )

    fd, temporary = tempfile.mkstemp(
        prefix=".settings-",
        dir=str(path.parent),
    )

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())

        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class MetadataSettingsTab(QWidget):
    """Pending controls for the existing shared metadata preferences."""

    def __init__(self, preferences, parent=None):
        super().__init__(parent)
        self.preferences = preferences
        layout = QVBoxLayout(self)
        description = QLabel(
            "Metadata reading priority, highest first. The first available "
            "supported source supplies the preferred value in Browser and Editor."
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        self.sources = QListWidget()
        self.sources.setAccessibleName("Metadata reading priority")
        self.sources.addItems(preferences.priority)
        self.sources.setCurrentRow(0)
        layout.addWidget(self.sources)
        controls = QHBoxLayout()
        up = QPushButton("Move up")
        down = QPushButton("Move down")
        controls.addWidget(up)
        controls.addWidget(down)
        controls.addStretch()
        layout.addLayout(controls)
        up.clicked.connect(lambda: self.move_source(-1))
        down.clicked.connect(lambda: self.move_source(1))

        def update_moves():
            row = self.sources.currentRow()
            up.setEnabled(row > 0)
            down.setEnabled(0 <= row < self.sources.count() - 1)

        self.sources.currentRowChanged.connect(update_moves)
        update_moves()
        self.sync_default = QCheckBox("Sync IPTC and XMP by default")
        self.sync_default.setChecked(preferences.sync_default)
        layout.addWidget(self.sync_default)
        note = QLabel(
            "Sets the default for metadata edit plans only. Synchronization is "
            "off by default. The Metadata Editor remains a read-only planner; "
            "this setting does not enable metadata writing."
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        pins = QLabel(
            "Pinned fields are shared by Browser and Editor. Use Configure "
            "fields in either application's overview, or Configure overview "
            "fields in the Editor's All fields tab, to manage the selection."
        )
        pins.setWordWrap(True)
        layout.addWidget(pins)
        layout.addStretch()

    def move_source(self, delta):
        row = self.sources.currentRow()
        target = row + delta
        if 0 <= row < self.sources.count() and 0 <= target < self.sources.count():
            item = self.sources.takeItem(row)
            self.sources.insertItem(target, item)
            self.sources.setCurrentRow(target)

    def restore_defaults(self):
        self.sources.clear()
        self.sources.addItems(SOURCE_PRIORITY_DEFAULT)
        self.sources.setCurrentRow(0)
        self.sync_default.setChecked(False)

    def snapshot(self):
        return (tuple(self.sources.item(i).text() for i in range(self.sources.count())),
                self.sync_default.isChecked())


def create_dialog(about_path, path=None, metadata_preferences=None):
    path = config_path() if path is None else path
    values = load_settings(path)
    preferences = metadata_preferences if metadata_preferences is not None else MetadataSourcePreferences()
    original_metadata = preferences.snapshot()
    general_defaults_requested = False

    dialog = QDialog()
    dialog.setWindowTitle("KIMng - Settings and about")
    dialog.setMinimumWidth(510)

    outer = QVBoxLayout(dialog)
    tabs = QTabWidget()
    outer.addWidget(tabs)

    settings_tab = QWidget()
    settings_layout = QVBoxLayout(settings_tab)
    form = QFormLayout()
    settings_layout.addLayout(form)

    def combo(label, entries, selected):
        widget = QComboBox()
        for text, value in entries:
            widget.addItem(text, value)
        index = widget.findData(selected)
        widget.setCurrentIndex(max(0, index))
        form.addRow(label, widget)
        return widget

    policy = combo(
        "Output policy:",
        [
            ("Always prompt for create / overwrite", "prompt"),
            ("Always create new files, without prompting", "create"),
        ],
        values["KIM_POLICY"],
    )

    location_units = combo(
        "Image location units:",
        location_unit_choices(),
        location_unit_selection(values["KIM_LOCATION_UNITS"]),
    )
    original_location_selection = location_units.currentData()

    explanation = QLabel(
        "Overwriting originals always requires explicit confirmation. "
        "Creation-only operations never overwrite their input images."
    )
    explanation.setWordWrap(True)
    settings_layout.addWidget(explanation)

    maps = QGroupBox("Maps")
    maps_layout = QVBoxLayout(maps)
    online_maps = QCheckBox("Load maps automatically")
    online_maps.setChecked(values["KIM_LOCATION_ONLINE_MAPS"] == "yes")
    maps_layout.addWidget(online_maps)
    online_maps.setToolTip(
        "Load OpenStreetMap tiles automatically when displaying maps."
    )
    settings_layout.addWidget(maps)

    quality = {}

    for key, label in (
        ("KIM_WEB_QUALITY_JPEG", "JPEG export quality:"),
        ("KIM_WEB_QUALITY_WEBP", "WebP export quality:"),
        ("KIM_WEB_QUALITY_AVIF", "AVIF export quality:"),
    ):
        widget = QSpinBox()
        widget.setRange(1, 100)
        widget.setValue(int(values[key]))
        form.addRow(label, widget)
        quality[key] = widget



    copyright_widgets = {}

    for key, label in (
        ("KIM_COPYRIGHT_CREATOR", "Creator / Artist:"),
        ("KIM_COPYRIGHT_NOTICE", "Copyright notice:"),
        ("KIM_COPYRIGHT_USAGE_RIGHTS", "Usage rights:"),
    ):
        widget = QLineEdit(values[key])
        widget.setMaxLength(500)
        form.addRow(label, widget)
        copyright_widgets[key] = widget

    settings_layout.addStretch()
    tabs.addTab(settings_tab, "Settings")

    # Keep general preferences separate from output filename customization.
    names_tab = QWidget()
    names_layout = QVBoxLayout(names_tab)
    names_intro = QLabel(
        "Customize the labels KIMng adds to filenames automatically. "
        "Filenames you choose yourself are not changed."
    )
    names_intro.setWordWrap(True)
    names_layout.addWidget(names_intro)

    affix = QComboBox()
    affix.addItem("Suffix (image_web.jpg)", "suffix")
    affix.addItem("Prefix (web_image.jpg)", "prefix")
    affix.setCurrentIndex(
        max(0, affix.findData(values["KIM_NAME_AFFIX_POSITION"]))
    )
    names_layout.addWidget(QLabel("Label position:"))
    names_layout.addWidget(affix)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    content = QWidget()
    names_form = QFormLayout(content)
    affix_widgets = {}
    affix_previews = {}

    for tag, description, extension, separator in AFFIX_ITEMS:
        key = "KIM_AFFIX_" + tag.upper().replace("-", "_")
        label_widget = QLineEdit(values[key])
        label_widget.setMaxLength(32)
        label_widget.setToolTip(
            "1–32 characters: letters, numbers, _ and -"
        )

        preview = QLabel()
        preview.setWordWrap(True)

        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(label_widget)
        row_layout.addWidget(preview)

        names_form.addRow(description + ":", row)
        affix_widgets[key] = label_widget
        affix_previews[key] = (preview, extension, separator, tag)

    scroll.setWidget(content)
    names_layout.addWidget(scroll)

    def update_filename_previews(*_unused):
        prefix = affix.currentData() == "prefix"

        for key, widget in affix_widgets.items():
            preview, extension, separator, tag = affix_previews[key]
            value = widget.text()

            if not AFFIX_PATTERN.fullmatch(value):
                preview.setText(
                    "Invalid label: use 1–32 letters, digits, _ or -"
                )
                continue

            sample = "video" if tag in {
                "transcoded", "frame", "thumbnail", "contact-sheet",
                "audio", "muted", "animated",
            } else "image"

            if tag == "frame":
                value += "-00-01-30"

            filename = (
                f"{value}{separator}{sample}.{extension}"
                if prefix else
                f"{sample}{separator}{value}.{extension}"
            )
            preview.setText("Example: " + filename)

    affix.currentIndexChanged.connect(update_filename_previews)
    for widget in affix_widgets.values():
        widget.textChanged.connect(update_filename_previews)

    update_filename_previews()
    tabs.addTab(names_tab, "Output Filenames")

    metadata_tab = MetadataSettingsTab(preferences)
    tabs.addTab(metadata_tab, "Metadata")

    about_tab = QWidget()
    about_layout = QVBoxLayout(about_tab)
    about_text = QTextEdit()
    about_text.setReadOnly(True)
    about_text.setPlainText(
        Path(about_path).read_text(encoding="utf-8")
    )
    about_layout.addWidget(about_text)
    tabs.addTab(about_tab, "About")


    # License and manual tabs supplement the existing menu actions.
    resource_dir = Path(about_path).resolve().parent

    def find_resource(relative):
        candidates = [
            resource_dir / relative,
            resource_dir.parent / relative,
            resource_dir.parent.parent / relative,
        ]
        return next(
            (p for p in candidates if p.is_file()),
            candidates[0],
        )

    license_path = find_resource("LICENSE.md")
    manual_path = find_resource("docs/index.html")

    license_tab = QWidget()
    license_layout = QVBoxLayout(license_tab)
    license_view = QTextEdit()
    license_view.setReadOnly(True)

    if license_path.is_file():
        license_view.setPlainText(
            license_path.read_text(encoding="utf-8", errors="replace")
        )
    else:
        license_view.setPlainText("Installed license not found.")

    license_layout.addWidget(license_view)
    tabs.addTab(license_tab, "License")

    manual_tab = QWidget()
    manual_layout = QVBoxLayout(manual_tab)
    manual_status = QLabel()
    manual_status.setWordWrap(True)
    manual_layout.addWidget(manual_status)

    manual_view = None
    manual_web_view = None

    if manual_path.is_file():
        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            manual_view = QWebEngineView()
            manual_view.setUrl(QUrl.fromLocalFile(str(manual_path)))
            manual_web_view = manual_view
            manual_status.hide()
        except (ImportError, RuntimeError):
            manual_view = QTextBrowser()
            manual_view.setOpenExternalLinks(True)
            markdown_path = find_resource("README.md")
            manual_view.setSearchPaths([
                str(markdown_path.parent),
                str(markdown_path.parent / "docs"),
            ])
            manual_view.setStyleSheet(
                "QTextBrowser { font-size: 14px; "
                "padding: 20px 28px; }"
            )
            if markdown_path.is_file():
                manual_view.setMarkdown(
                    markdown_path.read_text(
                        encoding="utf-8", errors="replace"
                    )
                )
            else:
                manual_view.setPlainText(
                    "The installed Markdown guide is unavailable."
                )
            manual_status.setText(
                "NOTE: Full HTML rendering is unavailable in this viewer session, so KIMng is displaying the Markdown version of the README. Use Open in Browser for the complete illustrated User Guide."
            )

        manual_layout.addWidget(manual_view, 1)
    else:
        manual_status.setText("Installed HTML User Guide not found.")

    manual_controls = QHBoxLayout()
    if manual_web_view is not None:
        add_history_controls(manual_controls, manual_web_view)
    manual_controls.addStretch()

    open_browser = QPushButton("Open in browser…")
    open_browser.setObjectName("manualOpenBrowser")
    open_browser.setAutoDefault(False)
    open_browser.setEnabled(manual_path.is_file())

    def launch_manual_browser():
        if not QDesktopServices.openUrl(
            current_guide_url(
                manual_web_view,
                QUrl.fromLocalFile(str(manual_path)),
            )
        ):
            QMessageBox.warning(
                dialog,
                "KIMng User Guide",
                "Could not launch a browser.",
            )

    open_browser.clicked.connect(launch_manual_browser)
    manual_controls.addWidget(open_browser)
    manual_layout.addLayout(manual_controls)

    tabs.addTab(manual_tab, "KIMng User Guide")

    def resize_for_tab(index):
        if tabs.tabText(index) in ("License", "KIMng User Guide"):
            dialog.resize(max(dialog.width(), 1000), 740)

    tabs.currentChanged.connect(resize_for_tab)

    footer = QHBoxLayout()
    restore = QPushButton("Restore Defaults")
    footer.addWidget(restore)
    footer.addStretch()

    buttons = QDialogButtonBox(
        QDialogButtonBox.Save | QDialogButtonBox.Cancel
    )
    style_button_box(buttons)
    footer.addWidget(buttons)
    outer.addLayout(footer)

    def restore_defaults():
        nonlocal general_defaults_requested
        if tabs.currentWidget() is metadata_tab:
            metadata_tab.restore_defaults()
            return
        general_defaults_requested = True
        online_maps.setChecked(DEFAULTS["KIM_LOCATION_ONLINE_MAPS"] == "yes")
        location_units.setCurrentIndex(location_units.findData(DEFAULTS["KIM_LOCATION_UNITS"]))
        policy.setCurrentIndex(
            policy.findData(DEFAULTS["KIM_POLICY"])
        )
        affix.setCurrentIndex(
            affix.findData(DEFAULTS["KIM_NAME_AFFIX_POSITION"])
        )
        for key, widget in affix_widgets.items():
            widget.setText(DEFAULTS[key])
        for key, widget in quality.items():
            widget.setValue(int(DEFAULTS[key]))

        for key, widget in copyright_widgets.items():
            widget.setText(DEFAULTS[key])

    restore.clicked.connect(restore_defaults)

    def save():
        updated = {
            "KIM_LOCATION_ONLINE_MAPS": "yes" if online_maps.isChecked() else "no",
            "KIM_LOCATION_UNITS": (values["KIM_LOCATION_UNITS"]
                                   if not general_defaults_requested and location_units.currentData() == original_location_selection
                                   else location_units.currentData()),
            "KIM_POLICY": policy.currentData(),
            "KIM_NAME_AFFIX_POSITION": affix.currentData(),
        }
        for key, widget in affix_widgets.items():
            value = widget.text()
            if not AFFIX_PATTERN.fullmatch(value):
                tabs.setCurrentWidget(names_tab)
                QMessageBox.warning(
                    dialog, "Invalid output filename label",
                    "Each label must contain 1–32 ASCII letters, numbers, "
                    "underscores or hyphens.",
                )
                widget.setFocus()
                return
            updated[key] = value

        for key, widget in quality.items():
            updated[key] = str(widget.value())

        for key, widget in copyright_widgets.items():
            updated[key] = (
                widget.text()
                .replace("\n", " ")
                .replace("\r", " ")
            )

        metadata_changed = metadata_tab.snapshot() != original_metadata
        try:
            if metadata_changed:
                preferences.save(*metadata_tab.snapshot())
                if preferences.settings.status() != QSettings.NoError:
                    raise OSError(
                        "Could not save metadata preferences to "
                        f"{preferences.settings.fileName()}. Check the directory's "
                        "write permissions and available disk space, then retry Save."
                    )
        except (OSError, ValueError) as error:
            tabs.setCurrentWidget(metadata_tab)
            QMessageBox.critical(
                dialog, "Unable to save metadata settings", str(error)
            )
            return

        try:
            if updated != values:
                save_settings(path, updated)
        except (OSError, ValueError) as error:
            detail = str(error)
            if metadata_changed:
                detail += "\nMetadata preferences were saved. General settings were not saved."
            detail += "\nCheck the settings file's directory and retry Save."
            QMessageBox.critical(
                dialog, "Unable to save KIMng settings", detail
            )
            return

        dialog.accept()

    buttons.accepted.connect(save)
    buttons.rejected.connect(dialog.reject)

    # Save and Cancel apply to all editable tabs.
    # About, License, and Manual are read-only tabs.
    def update_settings_buttons(index):
        is_settings = tabs.tabText(index) in ("Settings", "Output Filenames", "Metadata")
        restore.setVisible(is_settings)
        buttons.setVisible(is_settings)

    tabs.currentChanged.connect(update_settings_buttons)
    update_settings_buttons(tabs.currentIndex())

    return dialog


def main():
    if len(sys.argv) != 2:
        return 2

    app = QApplication(sys.argv)
    dialog = create_dialog(sys.argv[1])
    return 0 if dialog.exec() == QDialog.Accepted else 1


if __name__ == "__main__":
    sys.exit(main())
