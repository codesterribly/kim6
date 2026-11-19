#!/usr/bin/env python3
"""Photo Story editor foundation.

This development-stage UI retains edits in memory only.
It does not publish files or alter source images.
"""

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QCheckBox,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from kim_create_dialog import CreationImages, OrderedImageDialog
from kim_dialog_buttons import style_button_box


class StoryImages(CreationImages):
    """Photo Story's expanding, optionally numbered-only image list."""

    def __init__(self, parent, title):
        self.show_filenames = True
        super().__init__(parent, title)

    def refresh_item(self, path):
        super().refresh_item(path)
        if not self.show_filenames:
            item = self.items[path]
            status = self.state(path)[0]
            item.setText(
                f"{self.images.row(item) + 1}. Image\n{status}"
            )

    def resize_image_list(self):
        self.images.setMinimumHeight(220)
        self.images.setMaximumHeight(16777215)
        self.images.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self.resized.emit()


class PhotoStoryDialog(OrderedImageDialog):
    """Three-panel, native Qt story editor."""

    def __init__(self, paths=()):
        super().__init__()

        self.setWindowTitle("KIMng - Create a photo story")
        self.resize(1250, 780)
        self.setMinimumSize(900, 570)

        self.entries = {}
        self.active_path = None

        outer = QVBoxLayout(self)

        heading = QLabel("Create a photo story")
        heading_font = heading.font()
        heading_font.setPointSize(
            heading_font.pointSize() + 3
        )
        heading_font.setBold(True)
        heading.setFont(heading_font)
        outer.addWidget(heading)

        explanation = QLabel(
            "Arrange images, add your words, and watch your story take shape."
        )
        explanation.setWordWrap(True)
        outer.addWidget(explanation)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        outer.addWidget(self.splitter, 1)

        self.build_image_panel()
        self.build_editor_panel()
        self.build_preview_panel()

        self.splitter.setSizes([380, 440, 430])

        self.status = QLabel(
            "Add images to begin your story. Preview only for now."
        )
        self.status.setWordWrap(True)
        outer.addWidget(self.status)

        self.add_source_notice(outer)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Close
        )
        style_button_box(buttons)

        self.create = buttons.button(
            QDialogButtonBox.Close
        )
        self.create.setText("Close")
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        self.ordered.changed.connect(self.selection_changed)
        self.ordered.thumbnail_changed.connect(
            self.refresh_preview
        )
        self.ordered.images.currentRowChanged.connect(
            self.selection_changed
        )

        self.image_heading.textChanged.connect(
            self.store_current_entry
        )
        self.image_caption.textChanged.connect(
            self.store_current_entry
        )
        self.story_title.textChanged.connect(
            self.refresh_preview
        )
        self.introduction.textChanged.connect(
            self.refresh_preview
        )

        self.theme_selector.currentIndexChanged.connect(
            self.apply_theme
        )

        self.ordered.add_paths(paths)
        self.selection_changed()
        self.apply_theme()

    def build_image_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        label = QLabel("Story order")
        label_font = label.font()
        label_font.setBold(True)
        label.setFont(label_font)
        layout.addWidget(label)

        hint = QLabel(
            "Drag images to rearrange them, or use "
            "Move up and Move down."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.show_filenames = QCheckBox(
            "Hide filenames in story"
        )
        self.show_filenames.setChecked(False)
        self.show_filenames.setToolTip(
            "Hide automatic filename headings in the story. "
            "Filenames remain visible in the editor."
        )
        layout.addWidget(self.show_filenames)

        self.ordered = StoryImages(
            self, "Photo Story"
        )
        layout.addWidget(self.ordered, 1)

        self.show_filenames.toggled.connect(
            self.toggle_filenames
        )
        self.splitter.addWidget(panel)

    def build_editor_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        story_group = QGroupBox("Story details")
        story_form = QFormLayout(story_group)

        self.story_title = QLineEdit()
        self.story_title.setPlaceholderText(
            "Give your story a title"
        )
        story_form.addRow("Title:", self.story_title)

        self.introduction = QPlainTextEdit()
        self.introduction.setPlaceholderText(
            "Set the scene. What is this story about?"
        )
        self.introduction.setMaximumHeight(110)
        story_form.addRow(
            "Introduction:", self.introduction
        )

        layout.addWidget(story_group)

        image_group = QGroupBox("Selected image")
        image_form = QFormLayout(image_group)

        self.editing_file = QLabel("No image selected")
        self.editing_file.setWordWrap(True)
        self.editing_file.setTextFormat(Qt.PlainText)
        self.editing_file.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        image_form.addRow("Image:", self.editing_file)

        self.image_heading = QLineEdit()
        self.image_heading.setPlaceholderText(
            "Optional heading for this image"
        )
        image_form.addRow(
            "Heading:", self.image_heading
        )

        self.image_caption = QPlainTextEdit()
        self.image_caption.setPlaceholderText(
            "Write a caption, observation, or short passage."
        )
        image_form.addRow(
            "Caption:", self.image_caption
        )

        layout.addWidget(image_group, 1)

        navigation = QHBoxLayout()

        self.previous_button = QPushButton("Previous image")
        self.next_button = QPushButton("Next image")

        self.previous_button.clicked.connect(
            lambda: self.select_relative_image(-1)
        )
        self.next_button.clicked.connect(
            lambda: self.select_relative_image(1)
        )

        navigation.addWidget(self.previous_button)
        navigation.addWidget(self.next_button)
        layout.addLayout(navigation)

        self.splitter.addWidget(panel)

    def build_preview_panel(self):
        panel = QWidget()
        outer = QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(9)

        heading = QLabel("Story preview")
        heading_font = heading.font()
        heading_font.setBold(True)
        heading.setFont(heading_font)
        outer.addWidget(heading)

        theme_row = QHBoxLayout()
        theme_row.addWidget(QLabel("Style:"))

        self.theme_selector = QComboBox()
        self.theme_selector.setAccessibleName(
            "Photo Story presentation style"
        )

        for name, key in (
            ("Clean editorial", "editorial"),
            ("Cinematic dark", "cinematic"),
            ("Travel journal", "journal"),
            ("Photo essay", "essay"),
            ("Black and white", "monochrome"),
            ("Museum exhibit", "museum"),
            ("Vintage postcard", "postcard"),
            ("Modern bold", "bold"),
            ("Midnight blue", "midnight"),
            ("Golden hour", "golden"),
        ):
            self.theme_selector.addItem(name, key)

        theme_row.addWidget(self.theme_selector, 1)
        outer.addLayout(theme_row)

        self.theme_description = QLabel()
        self.theme_description.setWordWrap(True)
        outer.addWidget(self.theme_description)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setFrameShape(QFrame.NoFrame)
        self.preview_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )
        self.preview_scroll.setAccessibleName(
            "Scrollable Photo Story page preview"
        )

        outer.addWidget(self.preview_scroll, 1)

        self.story_page = QFrame()
        self.story_page.setObjectName(
            "photoStoryPreviewPanel"
        )

        page_layout = QVBoxLayout(self.story_page)
        page_layout.setContentsMargins(18, 22, 18, 22)
        page_layout.setSpacing(13)

        self.preview_eyebrow = QLabel("PHOTO STORY")
        self.preview_eyebrow.setObjectName(
            "photoStoryPreviewEyebrow"
        )
        page_layout.addWidget(self.preview_eyebrow)

        self.preview_title = QLabel("Untitled story")
        self.preview_title.setObjectName(
            "photoStoryPreviewTitle"
        )
        self.preview_title.setTextFormat(Qt.PlainText)
        self.preview_title.setWordWrap(True)
        page_layout.addWidget(self.preview_title)

        self.preview_intro = QLabel()
        self.preview_intro.setObjectName(
            "photoStoryPreviewIntro"
        )
        self.preview_intro.setTextFormat(Qt.PlainText)
        self.preview_intro.setWordWrap(True)
        self.preview_intro.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        page_layout.addWidget(self.preview_intro)

        self.preview_divider = QFrame()
        self.preview_divider.setObjectName(
            "photoStoryPreviewDivider"
        )
        self.preview_divider.setFrameShape(QFrame.HLine)
        page_layout.addWidget(self.preview_divider)

        self.preview_position = QLabel()
        self.preview_position.setObjectName(
            "photoStoryPreviewPosition"
        )
        page_layout.addWidget(self.preview_position)

        self.preview_image = QLabel("Select an image")
        self.preview_image.setObjectName(
            "photoStorySelectedImage"
        )
        self.preview_image.setAlignment(Qt.AlignCenter)
        self.preview_image.setFixedHeight(280)
        self.preview_image.setFrameShape(QFrame.StyledPanel)
        self.preview_image.setAccessibleName(
            "Selected image in story page"
        )
        page_layout.addWidget(self.preview_image)

        self.preview_heading = QLabel()
        self.preview_heading.setObjectName(
            "photoStoryImageHeading"
        )
        self.preview_heading.setTextFormat(Qt.PlainText)
        self.preview_heading.setWordWrap(True)
        page_layout.addWidget(self.preview_heading)

        self.preview_caption = QLabel()
        self.preview_caption.setObjectName(
            "photoStoryImageCaption"
        )
        self.preview_caption.setTextFormat(Qt.PlainText)
        self.preview_caption.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        self.preview_caption.setWordWrap(True)
        page_layout.addWidget(self.preview_caption)

        self.preview_footer = QLabel("KIMng  |  PHOTO STORY")
        self.preview_footer.setObjectName(
            "photoStoryPreviewFooter"
        )
        self.preview_footer.setAlignment(Qt.AlignCenter)
        page_layout.addSpacing(18)
        page_layout.addWidget(self.preview_footer)

        page_layout.addStretch(1)

        self.preview_scroll.setWidget(self.story_page)
        self.preview_panel = self.story_page

        self.splitter.addWidget(panel)

    def apply_theme(self, *_):
        """Update only the preview appearance, never story content."""

        themes = {
            "editorial": (
                "#ffffff", "#20242a", "#68717a",
                "#b7bec6", "#f0f2f4", "Noto Serif",
                24, "THE STORY", "Bright, elegant editorial presentation.",
                1, 3, 8
            ),
            "cinematic": (
                "#111318", "#f6f1e9", "#b8b4ad",
                "#d1a56a", "#090b0e", "Noto Serif",
                28, "CINEMA JOURNAL", "Dramatic photographs and warm gold accents.",
                1, 2, 4
            ),
            "journal": (
                "#f5ead4", "#463729", "#75644e",
                "#b38b59", "#e3d2b3", "DejaVu Serif",
                25, "FIELD NOTES", "Paper tones and a personal travel-journal feel.",
                1, 4, 3
            ),
            "essay": (
                "#edf1f3", "#182532", "#596874",
                "#527e94", "#dce3e7", "Noto Sans",
                23, "PHOTO ESSAY", "Clean documentary presentation.",
                1, 2, 2
            ),
            "monochrome": (
                "#f3f3f1", "#171717", "#555555",
                "#222222", "#dadad8", "DejaVu Serif",
                27, "BLACK / WHITE", "Monochrome photography and strong typography.",
                2, 0, 0
            ),
            "museum": (
                "#f6f4ee", "#292b2d", "#65635e",
                "#a68a59", "#e7e3d8", "DejaVu Serif",
                27, "THE COLLECTION", "Quiet gallery walls and exhibition-style labels.",
                1, 1, 0
            ),
            "postcard": (
                "#f3dfc5", "#5a352c", "#89624f",
                "#bd6954", "#ead0ab", "DejaVu Serif",
                26, "POSTCARDS", "Vintage warmth and nostalgic framing.",
                3, 4, 9
            ),
            "bold": (
                "#f7f6f1", "#10151e", "#424b58",
                "#ed613b", "#e1e4e8", "Noto Sans",
                29, "THE BIG PICTURE", "Large typography and energetic contrast.",
                3, 2, 2
            ),
            "midnight": (
                "#101f35", "#f0f5ff", "#b2c6dd",
                "#6ebedb", "#0b182a", "Noto Serif",
                27, "AFTER DARK", "Deep blue, luminous accents, and atmosphere.",
                1, 2, 5
            ),
            "golden": (
                "#fff3df", "#4a3324", "#8a6247",
                "#d99045", "#ead4b3", "DejaVu Serif",
                26, "GOLDEN HOUR", "Soft cream, amber highlights, and warmth.",
                1, 3, 7
            ),
        }

        key = self.theme_selector.currentData()
        theme = themes.get(key, themes["editorial"])

        (
            paper, ink, muted, accent, image_bg,
            font_family, title_size, eyebrow, description,
            border_width, image_border, radius
        ) = theme

        self.theme_description.setText(description)
        self.preview_eyebrow.setText(eyebrow)

        self.story_page.setStyleSheet(
            "QFrame#photoStoryPreviewPanel {"
            f"background-color: {paper};"
            f"border: {border_width}px solid {accent};"
            f"border-radius: {radius}px;"
            "}"
            "QFrame#photoStoryPreviewPanel QLabel {"
            f"color: {ink};"
            "border: none;"
            "}"
            "QLabel#photoStoryPreviewEyebrow {"
            f"color: {accent};"
            "font-size: 11px;"
            "font-weight: bold;"
            "}"
            "QFrame#photoStoryPreviewDivider {"
            f"border: none; border-top: 2px solid {accent};"
            "}"
            "QLabel#photoStoryPreviewTitle {"
            f"font-family: '{font_family}';"
            f"font-size: {title_size}px;"
            "font-weight: bold;"
            "}"
            "QLabel#photoStoryPreviewIntro {"
            f"color: {muted};"
            f"font-family: '{font_family}';"
            "}"
            "QLabel#photoStorySelectedImage {"
            f"background-color: {image_bg};"
            f"border: {image_border}px solid {accent};"
            f"border-radius: {radius}px;"
            "}"
        )

        self.preview_heading.setStyleSheet(
            f"font-family: '{font_family}';"
            f"font-size: {max(17, title_size - 5)}px;"
            f"font-weight: bold; color: {ink};"
        )

        self.preview_caption.setStyleSheet(
            f"font-family: '{font_family}';"
            f"font-size: 13px; color: {ink};"
        )

        self.preview_position.setStyleSheet(
            f"font-size: 11px; font-weight: bold;"
            f"color: {accent};"
        )

        self.preview_footer.setStyleSheet(
            f"font-size: 10px; color: {muted};"
        )

        self.refresh_preview()

    def toggle_filenames(self, checked):
        # Filenames remain available for identifying source images.
        # Only automatic headings in the story are affected.
        self.refresh_preview()

    def current_path(self):
        item = self.ordered.images.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def entry(self, path):
        return self.entries.setdefault(
            path, {"heading": "", "caption": ""}
        )

    def selection_changed(self, *_):
        paths = self.ordered.ordered_paths()

        for path in tuple(self.entries):
            if path not in paths:
                del self.entries[path]

        current = self.current_path()

        if current is None and paths:
            self.ordered.images.setCurrentRow(0)
            return

        if current != self.active_path:
            self.active_path = current
            values = (
                self.entry(current)
                if current else
                {"heading": "", "caption": ""}
            )

            self.image_heading.blockSignals(True)
            self.image_caption.blockSignals(True)

            self.image_heading.setText(
                values["heading"]
            )
            self.image_caption.setPlainText(
                values["caption"]
            )

            self.image_heading.blockSignals(False)
            self.image_caption.blockSignals(False)

        self.image_heading.setEnabled(
            current is not None
        )
        self.image_caption.setEnabled(
            current is not None
        )

        position = (
            paths.index(current)
            if current in paths else -1
        )

        self.previous_button.setEnabled(position > 0)
        self.next_button.setEnabled(
            0 <= position < len(paths) - 1
        )

        self.editing_file.setText(
            Path(current).name
            if current else "No image selected"
        )
        self.editing_file.setToolTip(current or "")

        if current:
            self.status.setText(
                f"{len(paths)} image{'s' if len(paths) != 1 else ''} "
                f"in your story. Editing image {position + 1}. "
                "Preview only for now."
            )
        else:
            self.status.setText(
                "Add images to begin your story. "
                "Preview only for now."
            )

        self.refresh_preview()

    def select_relative_image(self, direction):
        """Navigate the ordered images without modifying their order."""
        paths = self.ordered.ordered_paths()
        current = self.ordered.images.currentRow()
        next_row = current + direction

        if 0 <= next_row < len(paths):
            self.ordered.images.setCurrentRow(next_row)

    def store_current_entry(self, *_):
        path = self.active_path
        if path is None:
            return

        values = self.entry(path)
        values["heading"] = self.image_heading.text()
        values["caption"] = (
            self.image_caption.toPlainText()
        )
        self.refresh_preview()

    def refresh_preview(self, *_):
        paths = self.ordered.ordered_paths()
        path = self.current_path()

        title = self.story_title.text().strip()
        introduction = self.introduction.toPlainText().strip()

        self.preview_title.setText(
            title or "Untitled story"
        )
        self.preview_intro.setText(introduction)
        self.preview_intro.setVisible(bool(introduction))

        self.preview_heading.setText("")
        self.preview_caption.setText("")

        if not path or path not in paths:
            self.preview_image.setPixmap(QPixmap())
            self.preview_image.setText(
                "Add images to begin your story"
            )
            self.preview_position.setText(
                "No images selected"
            )
            return

        position = paths.index(path) + 1
        values = self.entry(path)

        self.preview_position.setText(
            f"Image {position} of {len(paths)}"
        )

        self.preview_heading.setText(
            values["heading"]
            or (
                Path(path).stem
                if not self.show_filenames.isChecked()
                else ""
            )
        )
        self.preview_caption.setText(
            values["caption"]
        )

        thumbnail = self.ordered.thumbnails.get(
            path
        )

        if thumbnail is not None and not thumbnail.isNull():
            image = QPixmap.fromImage(thumbnail)

            self.preview_image.setPixmap(
                image.scaled(
                    QSize(
                        max(180, self.preview_image.width() - 16),
                        max(180, self.preview_image.height() - 16),
                    ),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
            self.preview_image.setText("")
        else:
            self.preview_image.setPixmap(QPixmap())

            if path in self.ordered.unavailable:
                self.preview_image.setText(
                    "Preview unavailable"
                )
            else:
                self.preview_image.setText(
                    "Loading preview…"
                )
                self.ordered.request_preview(path)


def main(argv=None):
    paths = list(
        sys.argv[1:] if argv is None else argv
    )

    app = QApplication(sys.argv[:1])
    app.setApplicationName(
        "KIMng Photo Story"
    )
    app.setOrganizationName("KIMng")

    dialog = PhotoStoryDialog(paths)
    return dialog.exec()


if __name__ == "__main__":
    raise SystemExit(main())
