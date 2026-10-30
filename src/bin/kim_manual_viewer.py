#!/usr/bin/env python3
"""KIM6 offline HTML User Guide viewer.

Uses the installed documentation without requiring a web browser.
Relative HTML links and images resolve from the installed User Guide.
"""

import sys
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QMessageBox,
    QTextBrowser,
    QVBoxLayout,
)


def main():
    if len(sys.argv) != 2:
        return 2

    manual = Path(sys.argv[1]).resolve()

    if not manual.is_file():
        print(
            f"KIM6 User Guide not found: {manual}",
            file=sys.stderr,
        )
        return 1

    app = QApplication(sys.argv)

    dialog = QDialog()
    dialog.setWindowTitle("KIM6 — User Guide")
    dialog.resize(1000, 760)

    layout = QVBoxLayout(dialog)

    browser = QTextBrowser()
    browser.setOpenExternalLinks(True)
    browser.setSearchPaths([str(manual.parent)])
    # QTextBrowser cannot faithfully render the full HTML User Guide.
    # Use the installed Markdown guide for a readable fallback.
    markdown = manual.parent.parent / "README.md"

    browser.setSearchPaths([
        str(markdown.parent),
        str(markdown.parent / "docs"),
    ])
    browser.setStyleSheet(
        "QTextBrowser { font-size: 14px; padding: 20px 28px; }"
    )

    if markdown.is_file():
        browser.setMarkdown(
            markdown.read_text(
                encoding="utf-8", errors="replace"
            )
        )
    else:
        browser.setPlainText(
            "The installed Markdown guide could not be found."
        )

    layout.addWidget(browser)

    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if not browser.toPlainText().strip():
        QMessageBox.critical(
            dialog,
            "KIM6 User Guide",
            "The User Guide could not be displayed.",
        )
        return 1

    dialog.exec()
    return 0


if __name__ == "__main__":
    sys.exit(main())
