#!/usr/bin/env python3
"""KIM6 persistent settings and About dialog."""

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFormLayout, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QSpinBox, QTabWidget, QTextEdit, QTextBrowser, QLineEdit,
    QVBoxLayout, QWidget,
)

DEFAULTS = {
    "KIM_POLICY": "prompt",
    "KIM_NAME_AFFIX_POSITION": "suffix",
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
    return base / "kim6" / "settings.conf"


def load_settings(path):
    settings = DEFAULTS.copy()

    if not path.exists():
        return settings

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
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
        elif key == "KIM_NAME_AFFIX_POSITION" and value in VALID_AFFIXES:
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
        "# KIM6 user preferences\n"
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


def main():
    if len(sys.argv) != 2:
        return 2

    app = QApplication(sys.argv)
    path = config_path()
    values = load_settings(path)

    dialog = QDialog()
    dialog.setWindowTitle("KIM6 — Settings / About")
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

    explanation = QLabel(
        "Overwriting originals always requires explicit confirmation. "
        "Creation-only operations never overwrite their input images."
    )
    explanation.setWordWrap(True)
    settings_layout.addWidget(explanation)

    affix = combo(
        "Filename affix:",
        [
            ("Suffix (photo_web.jpg)", "suffix"),
            ("Prefix (web_photo.jpg)", "prefix"),
        ],
        values["KIM_NAME_AFFIX_POSITION"],
    )

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

    png_info = QLabel(
        "PNG exports use lossless compression. "
        "There is no lossy quality percentage to configure."
    )
    png_info.setWordWrap(True)
    settings_layout.addWidget(png_info)


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

    about_tab = QWidget()
    about_layout = QVBoxLayout(about_tab)
    about_text = QTextEdit()
    about_text.setReadOnly(True)
    about_text.setPlainText(
        Path(sys.argv[1]).read_text(encoding="utf-8")
    )
    about_layout.addWidget(about_text)
    tabs.addTab(about_tab, "About")


    # License and manual tabs supplement the existing menu actions.
    resource_dir = Path(sys.argv[1]).resolve().parent

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

    if manual_path.is_file():
        manual_view = None

        try:
            if any(os.environ.get(key) for key in (
                "SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY"
            )):
                raise ImportError("Prefer Markdown under SSH forwarding")

            from PySide6.QtWebEngineWidgets import QWebEngineView
            manual_view = QWebEngineView()
            manual_view.setUrl(QUrl.fromLocalFile(str(manual_path)))
            manual_status.setText("HTML user manual.")
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
                "NOTE: Full HTML rendering is unavailable in this viewer session, so KIM6 is displaying the Markdown version of the README. Use Open in Browser for the complete illustrated manual."
            )

        manual_layout.addWidget(manual_view)
    else:
        manual_status.setText("Installed HTML manual not found.")

    manual_controls = QHBoxLayout()
    manual_controls.addStretch()

    open_browser = QPushButton("Open in Browser…")
    open_browser.setEnabled(manual_path.is_file())

    def launch_manual_browser():
        if not QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(manual_path))
        ):
            QMessageBox.warning(
                dialog,
                "KIM6 Manual",
                "Could not launch a browser.",
            )

    open_browser.clicked.connect(launch_manual_browser)
    manual_controls.addWidget(open_browser)
    manual_layout.addLayout(manual_controls)

    tabs.addTab(manual_tab, "KIM6 Manual")

    def resize_for_tab(index):
        if tabs.tabText(index) in ("License", "KIM6 Manual"):
            dialog.resize(max(dialog.width(), 1000), 740)

    tabs.currentChanged.connect(resize_for_tab)

    footer = QHBoxLayout()
    restore = QPushButton("Restore Defaults")
    footer.addWidget(restore)
    footer.addStretch()

    buttons = QDialogButtonBox(
        QDialogButtonBox.Save | QDialogButtonBox.Cancel
    )
    footer.addWidget(buttons)
    outer.addLayout(footer)

    def restore_defaults():
        policy.setCurrentIndex(
            policy.findData(DEFAULTS["KIM_POLICY"])
        )
        affix.setCurrentIndex(
            affix.findData(DEFAULTS["KIM_NAME_AFFIX_POSITION"])
        )
        for key, widget in quality.items():
            widget.setValue(int(DEFAULTS[key]))

        for key, widget in copyright_widgets.items():
            widget.setText(DEFAULTS[key])

    restore.clicked.connect(restore_defaults)

    def save():
        updated = {
            "KIM_POLICY": policy.currentData(),
            "KIM_NAME_AFFIX_POSITION": affix.currentData(),
        }
        for key, widget in quality.items():
            updated[key] = str(widget.value())

        for key, widget in copyright_widgets.items():
            updated[key] = (
                widget.text()
                .replace("\n", " ")
                .replace("\r", " ")
            )

        try:
            save_settings(path, updated)
        except (OSError, ValueError) as error:
            QMessageBox.critical(
                dialog, "Unable to save KIM6 settings", str(error)
            )
            return

        dialog.accept()

    buttons.accepted.connect(save)
    buttons.rejected.connect(dialog.reject)

    # Save, Cancel, and Restore Defaults apply only to Settings.
    # About, License, and Manual are read-only tabs.
    def update_settings_buttons(index):
        is_settings = tabs.tabText(index) == "Settings"
        restore.setVisible(is_settings)
        buttons.setVisible(is_settings)

    tabs.currentChanged.connect(update_settings_buttons)
    update_settings_buttons(tabs.currentIndex())

    return 0 if dialog.exec() == QDialog.Accepted else 1


if __name__ == "__main__":
    sys.exit(main())
