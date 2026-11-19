"""Small native review display helpers. These never change processing plans."""
from PySide6.QtWidgets import QApplication, QLabel, QLineEdit


def exact_field(layout, caption):
    label = QLabel(caption)
    field = QLineEdit()
    field.setReadOnly(True)
    field.setAccessibleName(caption)
    label.setBuddy(field)
    layout.addWidget(label)
    layout.addWidget(field)
    return field


def set_exact(field, value):
    field.setText(value)
    field.setToolTip(value)
    field.setCursorPosition(0)


def restore_review_geometry(dialog, settings, default_size):
    geometry = settings.value('geometry')
    if geometry:
        dialog.restoreGeometry(geometry)
    else:
        dialog.resize(*default_size)
    clamp_review_geometry(dialog)


def clamp_review_geometry(dialog):
    screen = dialog.screen() or QApplication.primaryScreen()
    available = screen.availableGeometry().adjusted(12, 28, -12, -12)
    dialog.resize(min(dialog.width(), available.width()),
                  min(dialog.height(), available.height()))
    position = dialog.pos()
    dialog.move(max(available.left(), min(position.x(), available.right() - dialog.width() + 1)),
                max(available.top(), min(position.y(), available.bottom() - dialog.height() + 1)))


def restore_splitter(splitter, settings, key, defaults):
    try:
        sizes = [max(1, min(10000, int(n))) for n in settings.value(key, defaults)]
        if len(sizes) != splitter.count():
            sizes = defaults
    except (TypeError, ValueError):
        sizes = defaults
    # Qt scales these proportions to the actual available pane space.
    splitter.setSizes(sizes)
