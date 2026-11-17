#!/usr/bin/env python3
"""KIMng compression review. No processing occurs here."""
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QAbstractItemView, QButtonGroup,
    QDialog, QDialogButtonBox, QFileDialog,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QRadioButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout,
)


def load_plan(filename):
    data = Path(filename).read_bytes()
    if not data.endswith(b"\0"):
        raise ValueError("Incomplete compression plan")
    values = data[:-1].split(b"\0")
    if not values or len(values) % 4:
        raise ValueError("Invalid compression plan")
    return [
        tuple(os.fsdecode(v) for v in values[i:i + 4])
        for i in range(0, len(values), 4)
    ]


def review(plan_path, request_path, policy, destination):
    if policy not in ("create", "overwrite"):
        raise ValueError("Invalid compression policy")

    records = load_plan(plan_path)
    app = QApplication.instance() or QApplication(sys.argv[:1])

    dialog = QDialog()
    dialog.setWindowTitle("KIMng - Review compression changes")
    dialog.resize(1000, 460)

    layout = QVBoxLayout(dialog)
    layout.setContentsMargins(12, 12, 12, 12)
    layout.setSpacing(10)

    layout.addWidget(QLabel(
        f"Selected images: {len(records)}"
    ))
    layout.addWidget(QLabel("Save compressed images:"))

    create = QRadioButton(
        "Create new files (originals untouched)"
    )
    overwrite = QRadioButton(
        "Overwrite originals (confirmation required)"
    )
    group = QButtonGroup(dialog)
    group.addButton(create)
    group.addButton(overwrite)

    policy_row = QHBoxLayout()
    policy_row.addWidget(create)
    policy_row.addWidget(overwrite)
    policy_row.addStretch()
    layout.addLayout(policy_row)

    create.setChecked(policy == "create")
    overwrite.setChecked(policy == "overwrite")

    destination_row = QHBoxLayout()
    description = (
        "Destination: Replace selected originals"
        if policy == "overwrite"
        else "Destination: " + (
            destination or "Beside each source"
        )
    )

    destination_label = QLabel(description)
    destination_label.setWordWrap(True)
    destination_row.addWidget(destination_label, 1)

    change = QPushButton("Change destination…")
    beside = QPushButton("Beside each source")

    if policy == "create":
        destination_row.addWidget(change)
        if destination:
            destination_row.addWidget(beside)
    layout.addLayout(destination_row)

    table = QTableWidget(len(records), 4)
    table.setHorizontalHeaderLabels([
        "Source image", "Output filename",
        "Destination", "Status",
    ])
    table.setEditTriggers(
        QAbstractItemView.NoEditTriggers
    )
    table.setSelectionBehavior(
        QAbstractItemView.SelectRows
    )
    table.verticalHeader().hide()

    header = table.horizontalHeader()
    for column in range(3):
        header.setSectionResizeMode(
            column, QHeaderView.Stretch
        )
    header.setSectionResizeMode(
        3, QHeaderView.ResizeToContents
    )

    for index, (source, target, status, note) in enumerate(records):
        values = (
            Path(source).name,
            Path(target).name if target else "",
            str(Path(target).parent) if target else "",
            status,
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(note)
            table.setItem(index, column, item)

    layout.addWidget(table, 1)

    details = QLabel()
    details.setWordWrap(True)
    layout.addWidget(details)

    def update_details():
        row = table.currentRow()
        if row >= 0:
            source, target, status, note = records[row]
            details.setText(
                f"{Path(source).name}: {status}. {note}"
            )

    table.itemSelectionChanged.connect(update_details)
    if records:
        table.selectRow(0)

    blocked = sum(
        status != "Ready"
        for _, _, status, _ in records
    )
    summary = QLabel(
        f"{len(records) - blocked} ready, {blocked} blocked. "
        + (
            "Original images will be replaced."
            if policy == "overwrite"
            else "Original images will remain unchanged."
        )
    )
    layout.addWidget(summary)

    row = QHBoxLayout()
    back = QPushButton("Back")
    row.addWidget(back)
    row.addStretch()

    buttons = QDialogButtonBox(
        QDialogButtonBox.Apply | QDialogButtonBox.Cancel
    )
    apply = buttons.button(QDialogButtonBox.Apply)
    apply.setText("Apply changes")
    apply.setEnabled(bool(records) and not blocked)
    row.addWidget(buttons)
    layout.addLayout(row)

    request = Path(request_path)

    def request_change(value, code):
        try:
            request.write_bytes(
                os.fsencode(value) + b"\0"
            )
        except OSError as error:
            QMessageBox.critical(
                dialog, "Cannot update review", str(error)
            )
            return
        dialog.done(code)

    create.toggled.connect(
        lambda checked: (
            request_change("policy:create", 132)
            if checked and policy != "create" else None
        )
    )
    overwrite.toggled.connect(
        lambda checked: (
            request_change("policy:overwrite", 132)
            if checked and policy != "overwrite" else None
        )
    )

    def change_directory():
        initial = destination or str(Path(records[0][0]).parent)
        selected = QFileDialog.getExistingDirectory(
            dialog, "Choose compression destination", initial
        )
        if selected:
            request_change("directory:" + selected, 130)

    change.clicked.connect(change_directory)
    beside.clicked.connect(
        lambda: request_change("directory:", 130)
    )
    back.clicked.connect(lambda: dialog.done(131))

    def approve():
        if blocked:
            return
        if policy == "overwrite":
            answer = QMessageBox.warning(
                dialog,
                "Confirm overwriting originals",
                "Replace the selected original images?\n\n"
                "This cannot be undone.",
                QMessageBox.Yes | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if answer != QMessageBox.Yes:
                return
        dialog.accept()

    apply.clicked.connect(approve)
    buttons.rejected.connect(dialog.reject)

    result = dialog.exec()
    if result == QDialog.Accepted:
        return 0
    if result in (130, 131, 132):
        return result
    return 129


def main():
    if len(sys.argv) != 6 or sys.argv[1] != "review":
        raise ValueError("Invalid compression review arguments")
    return review(*sys.argv[2:])


if __name__ == "__main__":
    raise SystemExit(main())
