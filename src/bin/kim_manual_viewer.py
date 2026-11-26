#!/usr/bin/env python3
"""Display the installed KIMng HTML User Guide in a standalone Qt window."""
from kim_dialog_buttons import style_button, style_button_box

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
)


def add_history_controls(layout, viewer):
    """Add navigation buttons that follow the embedded page history."""
    from PySide6.QtWebEngineCore import QWebEnginePage

    page = viewer.page()
    back_action = page.action(QWebEnginePage.WebAction.Back)
    forward_action = page.action(QWebEnginePage.WebAction.Forward)

    back = QPushButton(QIcon.fromTheme("go-previous"), "Back")
    forward = QPushButton(QIcon.fromTheme("go-next"), "Forward")

    back.setObjectName("manualBack")
    forward.setObjectName("manualForward")

    back.setToolTip("Return to the previous page")
    forward.setToolTip("Go to the next page in browsing history")

    back.setAutoDefault(False)
    forward.setAutoDefault(False)

    back.clicked.connect(viewer.back)
    forward.clicked.connect(viewer.forward)

    def update_history_controls():
        back.setEnabled(back_action.isEnabled())
        forward.setEnabled(forward_action.isEnabled())

    back_action.changed.connect(update_history_controls)
    forward_action.changed.connect(update_history_controls)

    viewer.urlChanged.connect(update_history_controls)
    viewer.loadFinished.connect(update_history_controls)

    update_history_controls()

    layout.addWidget(back)
    layout.addWidget(forward)

    return back, forward


def current_guide_url(viewer, fallback):
    """Return the current HTML page, or the installed guide fallback."""
    if viewer is not None and callable(getattr(viewer, "url", None)):
        current = viewer.url()
        if current.isValid() and not current.isEmpty():
            if current.scheme() != "about":
                return current

    return fallback


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
    add_history_controls(controls, viewer)
    controls.addStretch()

    open_browser = QPushButton("Open in browser…")
    open_browser.setObjectName("manualOpenBrowser")
    open_browser.setAutoDefault(False)

    def launch_browser():
        if not QDesktopServices.openUrl(current_guide_url(viewer, url)):
            QMessageBox.warning(
                dialog,
                "KIMng User Guide",
                "Could not launch a browser.",
            )

    open_browser.clicked.connect(launch_browser)
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
