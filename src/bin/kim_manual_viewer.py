#!/usr/bin/env python3
"""Display the installed KIMng HTML User Guide in a standalone Qt window."""
from kim_dialog_buttons import style_button, style_button_box

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
)


def main():
    if len(sys.argv) != 2:
        return 2

    manual = Path(sys.argv[1]).resolve()
    if not manual.is_file():
        print(f"KIMng User Guide not found: {manual}", file=sys.stderr)
        return 1

    app = QApplication(sys.argv)
    url = QUrl.fromLocalFile(str(manual))

    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView
    except (ImportError, RuntimeError):
        choice = QMessageBox.question(
            None,
            "KIMng User Guide",
            "The embedded HTML viewer requires PySide6 Qt WebEngine. "
            "Open the illustrated User Guide in your browser?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if choice == QMessageBox.Yes:
            return 0 if QDesktopServices.openUrl(url) else 1
        return 1

    dialog = QDialog()
    dialog.setWindowTitle("KIMng - User Guide")
    dialog.resize(1100, 800)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(8, 8, 8, 8)
    layout.setSpacing(6)

    viewer = QWebEngineView(dialog)
    viewer.setUrl(url)
    layout.addWidget(viewer, 1)

    controls = QHBoxLayout()
    controls.addStretch()

    open_browser = QPushButton("Open in browser…")
    open_browser.clicked.connect(lambda: QDesktopServices.openUrl(url))
    controls.addWidget(open_browser)

    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    style_button_box(buttons)
    buttons.rejected.connect(dialog.reject)
    controls.addWidget(buttons)

    layout.addLayout(controls)

    dialog.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
