"""Shared KDE/Breeze action-button presentation.

Presentation only. Does not alter button roles, signals,
approval gates, or publication behavior.
"""

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QDialogButtonBox, QStyle


_ICONS = {
    "back": ("go-previous", QStyle.SP_ArrowLeft),
    "review": ("dialog-ok-apply", QStyle.SP_DialogApplyButton),
    "apply": ("dialog-ok-apply", QStyle.SP_DialogApplyButton),
    "cancel": ("dialog-cancel", QStyle.SP_DialogCancelButton),
}


def button_kind(label):
    value = str(label).strip().casefold()
    value = value.replace("...", "…")

    if value in ("back", "back to options"):
        return "back"

    if value in (
        "review changes…",
        "review changes",
        "review outputs…",
        "continue to review",
    ):
        return "review"

    if value in ("apply changes", "apply"):
        return "apply"

    if value == "cancel":
        return "cancel"

    return None


def style_button(button, kind=None):
    """Set an action icon without modifying text or behavior."""
    if button is None:
        return

    kind = kind or button_kind(button.text())
    entry = _ICONS.get(kind)

    if entry is None:
        return

    theme_name, fallback = entry
    icon = QIcon.fromTheme(theme_name)

    if icon.isNull():
        icon = button.style().standardIcon(fallback)

    if not icon.isNull():
        button.setIcon(icon)


def style_button_box(box):
    """Style standard roles already present in a button box."""
    for standard in (
        QDialogButtonBox.Ok,
        QDialogButtonBox.Apply,
        QDialogButtonBox.Cancel,
        QDialogButtonBox.Close,
    ):
        button = box.button(standard)
        if button is not None:
            style_button(button)
