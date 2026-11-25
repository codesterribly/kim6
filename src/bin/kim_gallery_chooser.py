#!/usr/bin/env python3
"""KIMng graphical choice between image gallery and photo story.

Uses the existing protected image-thumbnail reader. The chooser itself
does not modify images, save story data, or publish output.
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QRectF, Signal
from PySide6.QtGui import (
    QColor, QFont, QIcon, QImage, QLinearGradient,
    QPainter, QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFrame,
    QHBoxLayout, QLabel, QStyle, QVBoxLayout,
)

from kim_dialog_buttons import style_button, style_button_box
from kim_photo_selection import ThumbnailWorker


ART_WIDTH = 560
ART_HEIGHT = 290


def rectangle(x, y, width, height):
    return QRectF(x, y, width, height)


def cover_image(painter, image, target):
    """Draw an image as a centered cover crop."""
    if image is None or image.isNull():
        gradient = QLinearGradient(
            target.topLeft(), target.bottomRight()
        )
        gradient.setColorAt(0, QColor('#536d83'))
        gradient.setColorAt(0.5, QColor('#879a9c'))
        gradient.setColorAt(1, QColor('#253d55'))
        painter.fillRect(target, gradient)
        return

    source_width = image.width()
    source_height = image.height()

    wanted_ratio = target.width() / target.height()
    source_ratio = source_width / source_height

    if source_ratio > wanted_ratio:
        crop_width = source_height * wanted_ratio
        crop_height = source_height
    else:
        crop_width = source_width
        crop_height = source_width / wanted_ratio

    source_rect = rectangle(
        (source_width - crop_width) / 2,
        (source_height - crop_height) / 2,
        crop_width,
        crop_height,
    )

    painter.drawImage(target, image, source_rect)


def artwork(kind, pictures):
    canvas = QImage(
        ART_WIDTH, ART_HEIGHT,
        QImage.Format_ARGB32_Premultiplied,
    )
    canvas.fill(QColor('#ffffff'))

    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

    clip = QPainterPath()
    clip.addRoundedRect(
        QRectF(0, 0, ART_WIDTH, ART_HEIGHT), 16, 16
    )
    painter.setClipPath(clip)

    if kind == 'gallery':
        painter.fillRect(canvas.rect(), QColor('#fafafa'))
        painter.fillRect(
            rectangle(0, 0, ART_WIDTH, 35),
            QColor('#ffffff'),
        )

        painter.setPen(QColor('#303741'))
        font = QFont('Noto Sans', 10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            rectangle(18, 3, 190, 29),
            Qt.AlignVCenter,
            'YOUR COLLECTION',
        )

        font.setPointSize(7)
        font.setBold(False)
        painter.setFont(font)
        painter.drawText(
            rectangle(310, 3, 235, 29),
            Qt.AlignVCenter | Qt.AlignRight,
            'GALLERY    STORIES    ABOUT',
        )

        tiles = (
            (12, 47, 174, 220),
            (193, 47, 172, 220),
            (372, 47, 176, 105),
            (372, 159, 176, 108),
        )

        for index, geometry in enumerate(tiles):
            tile = rectangle(*geometry)
            image = (
                pictures[index % len(pictures)]
                if pictures else None
            )
            cover_image(painter, image, tile)

        painter.fillRect(
            rectangle(0, 277, ART_WIDTH, 13),
            QColor('#ffffff'),
        )

    else:
        hero = rectangle(0, 0, ART_WIDTH, ART_HEIGHT)
        cover_image(
            painter,
            pictures[0] if pictures else None,
            hero,
        )

        overlay = QLinearGradient(0, 95, 0, ART_HEIGHT)
        overlay.setColorAt(0, QColor(0, 0, 0, 0))
        overlay.setColorAt(0.55, QColor(0, 0, 0, 105))
        overlay.setColorAt(1, QColor(0, 0, 0, 210))
        painter.fillRect(hero, overlay)

        painter.setPen(QColor('#ffffff'))

        font = QFont('Noto Sans', 9)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 2)
        painter.setFont(font)
        painter.drawText(
            rectangle(29, 22, 490, 24),
            Qt.AlignLeft | Qt.AlignVCenter,
            'A PHOTO STORY',
        )

        font = QFont('Noto Serif', 26)
        font.setBold(True)
        painter.setFont(font)
        headline = 'Your story.\nBeautifully told.'
        headline_rect = rectangle(29, 119, 510, 119)
        painter.drawText(
            headline_rect,
            Qt.AlignLeft | Qt.AlignVCenter | Qt.TextWordWrap,
            headline,
        )

        font = QFont('Noto Sans', 10)
        painter.setFont(font)
        painter.setPen(QColor('#eeeeee'))
        painter.drawText(
            rectangle(31, 245, 490, 30),
            Qt.AlignLeft | Qt.AlignVCenter,
            'Images, moments, and the words between them.',
        )

    painter.end()
    return canvas


class GalleryCard(QFrame):
    selected = Signal(str)

    def __init__(self, key, title, description, parent=None):
        super().__init__(parent)

        self.key = key
        self.active = False
        self.setObjectName('galleryChoiceCard')
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName(title)
        self.setAccessibleDescription(description)
        self.setMinimumWidth(330)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 15)
        layout.setSpacing(10)

        self.art = QLabel()
        self.art.setAlignment(Qt.AlignCenter)
        self.art.setFixedHeight(238)
        self.art.setScaledContents(True)
        self.art.setAccessibleName(title + ' example')
        layout.addWidget(self.art)

        self.name = QLabel(title)
        self.name.setObjectName('galleryCardTitle')
        layout.addWidget(self.name)

        self.description = QLabel(description)
        self.description.setWordWrap(True)
        self.description.setObjectName('galleryCardDescription')
        layout.addWidget(self.description)



        self.set_art([])

        self.set_selected(False)

    def set_art(self, images):
        self.art.setPixmap(
            QPixmap.fromImage(artwork(self.key, images))
        )

    def set_selected(self, enabled):
        self.active = enabled
        border = '#40a9f4' if enabled else '#444b55'
        background = '#192637' if enabled else '#17191e'

        self.setStyleSheet(
            'QFrame#galleryChoiceCard {'
            f'background: {background};'
            f'border: 2px solid {border};'
            'border-radius: 15px;'
            '}'
            'QFrame#galleryChoiceCard QLabel {'
            'border: none; background: transparent;'
            '}'
            'QLabel#galleryCardTitle {'
            'font-size: 20px; font-weight: bold; color: #ffffff;'
            '}'
            'QLabel#galleryCardDescription {'
            'font-size: 13px; color: #d6dce5;'
            '}'
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.key)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.selected.emit(self.key)
            event.accept()
        else:
            super().keyPressEvent(event)


class GalleryChooser(QDialog):
    def __init__(self, paths):
        super().__init__()

        self.paths = paths
        self.choice = None
        self.images = {}
        self.worker = None
        self.pending_result = None

        self.setWindowTitle('KIMng - Create a gallery')
        self.resize(1080, 610)
        self.setMinimumSize(850, 560)

        self.setStyleSheet(
            'QDialog { background: #101216; color: #f5f6f8; }'
            'QDialog QLabel { color: #f5f6f8; }'
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 20, 22, 18)
        outer.setSpacing(14)

        title = QLabel('Create a gallery')
        title_font = QFont('Noto Sans', 22)
        title_font.setBold(True)
        title.setFont(title_font)
        outer.addWidget(title)

        subtitle = QLabel(
            'How would you like to present your images?'
        )
        subtitle.setStyleSheet(
            'font-size: 15px; color: #c8d0da;'
        )
        outer.addWidget(subtitle)

        cards = QHBoxLayout()
        cards.setSpacing(16)

        self.gallery_card = GalleryCard(
            'gallery',
            'Image gallery',
            'A visually rich collection of your images, '
            'beautifully arranged for browsing and sharing.',
            self,
        )

        self.story_card = GalleryCard(
            'story',
            'Photo story',
            'Tell a story through images, headings, captions, '
            'and written passages.',
            self,
        )

        cards.addWidget(self.gallery_card, 1)
        cards.addWidget(self.story_card, 1)
        outer.addLayout(cards)

        self.gallery_card.selected.connect(self.select_choice)
        self.story_card.selected.connect(self.select_choice)

        self.selection_summary = QLabel(
            'Select the kind of gallery you want to create.'
        )
        self.selection_summary.setWordWrap(True)
        outer.addWidget(self.selection_summary)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        style_button_box(buttons)

        self.continue_button = buttons.button(QDialogButtonBox.Ok)
        self.continue_button.setText('Continue')
        self.continue_button.setEnabled(False)

        style_button(self.continue_button, 'review')

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.begin_thumbnails()

    def select_choice(self, key):
        if key not in ('gallery', 'story'):
            return

        self.choice = key

        self.gallery_card.set_selected(key == 'gallery')
        self.story_card.set_selected(key == 'story')

        if key == 'gallery':
            self.selection_summary.setText(
                'Image gallery selected. Arrange and share a '
                'beautiful collection of images.'
            )
        else:
            self.selection_summary.setText(
                'Photo story selected. Create a visual narrative '
                'with images and your own words.'
            )

        self.continue_button.setEnabled(True)

    def begin_thumbnails(self):
        paths = list(dict.fromkeys(self.paths))[:6]
        if not paths:
            return

        self.worker = ThumbnailWorker(
            paths, QSize(850, 650), self
        )
        self.worker.thumbnail_ready.connect(
            self.thumbnail_received
        )
        self.worker.finished.connect(
            self.thumbnails_finished
        )
        self.worker.start()

    def thumbnail_received(self, path, image, stamp):
        if image is None or image.isNull():
            return

        self.images[path] = image

        available = [
            self.images[path]
            for path in self.paths
            if path in self.images
        ]

        if available:
            self.gallery_card.set_art(available)
            self.story_card.set_art(available)

    def thumbnails_finished(self):
        worker = self.worker
        self.worker = None

        if worker is not None:
            worker.deleteLater()

        if self.pending_result is not None:
            result = self.pending_result
            self.pending_result = None
            super().done(result)

    def accept(self):
        if self.choice is None:
            return
        super().accept()

    def done(self, result):
        if self.worker is not None and self.worker.isRunning():
            self.pending_result = result
            self.worker.requestInterruption()
            self.setEnabled(False)
            return
        super().done(result)


def main():
    paths = [
        str(Path(path).absolute())
        for path in sys.argv[1:]
        if Path(path).is_file()
    ]

    app = QApplication(sys.argv[:1])
    dialog = GalleryChooser(paths)

    result = dialog.exec()

    if result != QDialog.Accepted:
        return 130

    if dialog.choice == 'gallery':
        return 10

    if dialog.choice == 'story':
        return 11

    return 125


if __name__ == '__main__':
    sys.exit(main())
