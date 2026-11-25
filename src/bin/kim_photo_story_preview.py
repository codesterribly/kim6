"""Read-only, full-story Photo Story publication preview."""

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QBoxLayout, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from kim_photo_selection import ThumbnailWorker
from kim_preview import identity


PRESENTATIONS = {
    "editorial": {
        "name": "Clean editorial", "paper": "#e9e8e4", "page": "#ffffff",
        "ink": "#20242a", "muted": "#68717a", "accent": "#748291",
        "surface": "#f3f4f4", "outline": "#d8dce0", "display_font": "Noto Serif",
        "body_font": "Noto Sans", "title_size": 58, "section_size": 33,
        "body_size": 17, "intro_size": 20, "text_width": 920, "page_width": 1320,
        "image_height": 760, "cover_height": 940, "photo_treatment": "unframed",
        "section_treatment": "editorial-rule", "passage_treatment": "open-column",
        "photo_width": 1.0, "page_gutter": 44, "pair_spacing": 22,
        "cover_layout": "masthead-first", "alternate_photos": False, "center_title": False,
    },
    "cinematic": {
        "name": "Cinematic dark", "paper": "#101216", "page": "#111318",
        "ink": "#f6f1e9", "muted": "#c2b9ac", "accent": "#d1a56a",
        "surface": "#090b0e", "outline": "#36383a", "display_font": "Noto Serif",
        "body_font": "Noto Sans", "title_size": 72, "section_size": 36,
        "body_size": 19, "intro_size": 23, "text_width": 980, "page_width": 1640,
        "image_height": 880, "cover_height": 1040, "photo_treatment": "cinema-hero",
        "section_treatment": "cinema-rule", "passage_treatment": "cinema-panel",
        "photo_width": 1.0, "page_gutter": 0, "pair_spacing": 18,
        "cover_layout": "photo-first", "alternate_photos": False, "center_title": False,
    },
    "journal": {
        "name": "Travel journal", "paper": "#e8ddc7", "page": "#f5ead4",
        "ink": "#463729", "muted": "#75644e", "accent": "#a97945",
        "surface": "#fffaf0", "outline": "#d8c5a6", "display_font": "DejaVu Serif",
        "body_font": "DejaVu Serif", "title_size": 56, "section_size": 32,
        "body_size": 18, "intro_size": 21, "text_width": 900, "page_width": 1540,
        "image_height": 780, "cover_height": 960, "photo_treatment": "journal-open",
        "section_treatment": "journal-tab", "passage_treatment": "journal-note",
        "photo_width": 1.0, "page_gutter": 30, "pair_spacing": 18,
        "cover_layout": "masthead-first", "alternate_photos": False, "center_title": False,
    },
    "essay": {
        "name": "Photo essay", "paper": "#e7ecef", "page": "#f5f7f8",
        "ink": "#182532", "muted": "#596874", "accent": "#527e94",
        "surface": "#e6edf0", "outline": "#c7d1d7", "display_font": "Noto Sans",
        "body_font": "Noto Sans", "title_size": 56, "section_size": 31,
        "body_size": 18, "intro_size": 21, "text_width": 900, "page_width": 1440,
        "image_height": 780, "cover_height": 940, "photo_treatment": "documentary",
        "section_treatment": "essay-index", "passage_treatment": "essay-column",
        "photo_width": 1.0, "page_gutter": 38, "pair_spacing": 22,
        "cover_layout": "masthead-first", "alternate_photos": False, "center_title": False,
    },
    "monochrome": {
        "name": "Black and white", "paper": "#e7e7e4", "page": "#f3f3f1",
        "ink": "#171717", "muted": "#555555", "accent": "#202020",
        "surface": "#e5e5e2", "outline": "#777777", "display_font": "DejaVu Serif",
        "body_font": "Noto Sans", "title_size": 49, "section_size": 34,
        "body_size": 18, "intro_size": 21, "page_width": 1360,
        "image_height": 760, "cover_height": 920, "photo_treatment": "monochrome-edge",
        "section_treatment": "black-rule", "passage_treatment": "black-column",
        "photo_width": 0.98, "page_gutter": 36, "pair_spacing": 18,
        "cover_layout": "masthead-first", "alternate_photos": False, "center_title": False,
    },
    "museum": {
        "name": "Museum exhibit", "paper": "#e8e6df", "page": "#f6f4ee",
        "ink": "#292b2d", "muted": "#65635e", "accent": "#a68a59",
        "surface": "#ebe8df", "outline": "#d3cdbd", "display_font": "DejaVu Serif",
        "body_font": "Noto Sans", "title_size": 43, "section_size": 29,
        "body_size": 17, "intro_size": 20, "page_width": 1220,
        "image_height": 500, "cover_height": 610, "photo_treatment": "gallery-mount",
        "section_treatment": "museum-label", "passage_treatment": "museum-card",
        "photo_width": 0.9, "page_gutter": 64, "pair_spacing": 22,
        "cover_layout": "masthead-first", "alternate_photos": False, "center_title": True,
    },
    "postcard": {
        "name": "Vintage postcard", "paper": "#ead8be", "page": "#f3dfc5",
        "ink": "#5a352c", "muted": "#89624f", "accent": "#bd6954",
        "surface": "#fff6e9", "outline": "#cfaa87", "display_font": "DejaVu Serif",
        "body_font": "DejaVu Serif", "title_size": 45, "section_size": 31,
        "body_size": 17, "intro_size": 19, "page_width": 960,
        "image_height": 540, "cover_height": 650, "photo_treatment": "postcard-frame",
        "section_treatment": "postcard-rule", "passage_treatment": "postcard-note",
        "photo_width": 0.93, "page_gutter": 46, "pair_spacing": 20,
        "cover_layout": "masthead-first", "alternate_photos": False, "center_title": True,
    },
    "bold": {
        "name": "Modern bold", "paper": "#e6e5df", "page": "#f7f6f1",
        "ink": "#10151e", "muted": "#424b58", "accent": "#ed613b",
        "surface": "#e1e4e8", "outline": "#aeb6c0", "display_font": "Noto Sans",
        "body_font": "Noto Sans", "title_size": 58, "section_size": 37,
        "body_size": 18, "intro_size": 21, "page_width": 1060,
        "image_height": 580, "cover_height": 700, "photo_treatment": "bold-frame",
        "section_treatment": "bold-rule", "passage_treatment": "bold-panel",
        "photo_width": 0.92, "page_gutter": 38, "pair_spacing": 24,
        "cover_layout": "masthead-first", "alternate_photos": True, "center_title": False,
    },
    "midnight": {
        "name": "Midnight blue", "paper": "#081426", "page": "#101f35",
        "ink": "#f0f5ff", "muted": "#b2c6dd", "accent": "#6ebedb",
        "surface": "#0b182a", "outline": "#35506c", "display_font": "Noto Serif",
        "body_font": "Noto Sans", "title_size": 48, "section_size": 34,
        "body_size": 17, "intro_size": 20, "page_width": 1000,
        "image_height": 570, "cover_height": 680, "photo_treatment": "midnight-frame",
        "section_treatment": "midnight-rule", "passage_treatment": "midnight-panel",
        "photo_width": 1.0, "page_gutter": 28, "pair_spacing": 18,
        "cover_layout": "masthead-first", "alternate_photos": False, "center_title": False,
    },
    "golden": {
        "name": "Golden hour", "paper": "#efdfc8", "page": "#fff3df",
        "ink": "#4a3324", "muted": "#8a6247", "accent": "#d99045",
        "surface": "#ead4b3", "outline": "#dfc39e", "display_font": "DejaVu Serif",
        "body_font": "Noto Sans", "title_size": 48, "section_size": 33,
        "body_size": 17, "intro_size": 20, "page_width": 1000,
        "image_height": 570, "cover_height": 680, "photo_treatment": "golden-frame",
        "section_treatment": "golden-rule", "passage_treatment": "golden-column",
        "photo_width": 0.98, "page_gutter": 30, "pair_spacing": 18,
        "cover_layout": "masthead-first", "alternate_photos": False, "center_title": False,
    },
}


@dataclass(frozen=True)
class StoryElementSnapshot:
    kind: str
    id: str
    source: str
    heading: str
    caption: str
    text: str


@dataclass(frozen=True)
class StoryComposition:
    kind: str
    element_ids: tuple[str, ...]
    treatment: str = ""


def _compatible_aspects(first, second):
    if not first or not second or first <= 0 or second <= 0:
        return False
    first_shape = "landscape" if first >= 1.15 else "portrait" if first <= 0.87 else "square"
    second_shape = "landscape" if second >= 1.15 else "portrait" if second <= 0.87 else "square"
    return first_shape == second_shape and max(first, second) / min(first, second) <= 1.28


def build_composition_plan(elements, source_aspects=None):
    """Group only adjacent compatible photos while preserving every story position."""
    aspects = source_aspects or {}
    plan = []
    first_is_cover = bool(elements and elements[0].kind == "image")
    index = 0
    image_run_index = 0

    if first_is_cover:
        plan.append(StoryComposition("cover", (elements[0].id,), "cover"))
        index = 1

    while index < len(elements):
        element = elements[index]
        if element.kind != "image":
            plan.append(StoryComposition(element.kind, (element.id,)))
            image_run_index = 0
            index += 1
            continue

        next_element = elements[index + 1] if index + 1 < len(elements) else None
        pair_is_due = image_run_index % 3 == 1
        if (pair_is_due and next_element is not None and next_element.kind == "image"
                and _compatible_aspects(aspects.get(element.source),
                                        aspects.get(next_element.source))):
            plan.append(StoryComposition("pair", (element.id, next_element.id), "paired"))
            index += 2
            image_run_index += 2
            continue

        treatment = "feature" if image_run_index % 3 == 0 else "detail"
        plan.append(StoryComposition("image", (element.id,), treatment))
        index += 1
        image_run_index += 1

    return tuple(plan)


class StoryImageView(QWidget):
    """Aspect-preserving canvas for one safely decoded, bounded story image."""

    def __init__(self, element_id, filename, parent=None, *, cover=False,
                 source_aspect=None):
        super().__init__(parent)
        self.element_id = element_id
        self.image = QImage()
        self.status = "loading"
        self.message = "Preparing photograph…"
        self.surface = "#eceff1"
        self.outline = "#c9d0d5"
        self.treatment = "unframed"
        self.radius = 0
        self.cover = cover
        self.source_aspect = source_aspect
        self.max_height = 680 if cover else 560
        self.max_width = 960
        self.setMinimumWidth(0)
        self.setMinimumHeight(300)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName(f"Story photograph: {filename}")
        self.setAccessibleDescription("Full photograph, displayed without cropping")
        self._update_height()

    @property
    def has_image(self):
        return not self.image.isNull() and self.status == "ready"

    @property
    def displayed_rect(self):
        if self.image.isNull():
            return QRectF()
        inset = 14 if self.treatment in ("postcard-frame", "gallery-mount") else 0
        area = QRectF(self.rect()).adjusted(inset, inset, -inset, -inset)
        if area.width() <= 0 or area.height() <= 0:
            return QRectF()
        factor = min(area.width() / self.image.width(), area.height() / self.image.height())
        size = QSize(round(self.image.width() * factor), round(self.image.height() * factor))
        target = QRectF(0, 0, size.width(), size.height())
        target.moveCenter(area.center())
        return target

    def set_presentation(self, spec, *, cover=False):
        self.surface = spec["surface"]
        self.outline = spec["outline"]
        self.treatment = spec["photo_treatment"]
        self.radius = 8 if self.treatment in ("cinema-frame", "postcard-frame", "bold-frame", "golden-frame") else 0
        self.max_height = spec["cover_height"] if cover else spec["image_height"]
        self.cover = cover
        self._update_height()
        self.update()

    def set_width_limit(self, width):
        self.max_width = max(200, int(width))
        self._update_height()

    def show_image(self, image):
        self.image = image
        self.status = "ready"
        self.message = ""
        self.setAccessibleDescription("Full photograph, displayed without cropping")
        self._update_height()
        self.update()

    def show_unavailable(self, reason=""):
        self.image = QImage()
        self.status = "unavailable"
        self.message = "Photograph preview unavailable"
        self.setAccessibleDescription(reason or self.message)
        self._update_height()
        self.update()

    def release_image(self):
        self.image = QImage()
        self.status = "loading"
        self.message = "Scroll to load photograph"
        self._update_height()
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_height()

    def _update_height(self):
        available_width = max(200, min(self.max_width, self.width() or self.max_width))
        if self.source_aspect and self.source_aspect > 0:
            height = round(available_width / self.source_aspect)
        else:
            ratio = 0.70 if self.cover else 0.58
            height = round(available_width * ratio)
        self.setFixedHeight(max(300, min(self.max_height, height)))

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        framed = self.treatment in ("postcard-frame", "gallery-mount")
        if framed:
            frame_rect = rect.adjusted(1, 1, -1, -1)
            painter.setBrush(QColor(self.surface))
            painter.setPen(QPen(QColor(self.outline), 1))
            painter.drawRoundedRect(frame_rect, self.radius, self.radius)
        else:
            painter.fillRect(rect, QColor(self.surface))
        if not self.image.isNull():
            painter.setPen(Qt.NoPen)
            painter.drawImage(self.displayed_rect, self.image)
        else:
            painter.setPen(QColor("#727981"))
            painter.setFont(QFont("Noto Sans", 12))
            painter.drawText(rect.adjusted(24, 20, -24, -20), Qt.AlignCenter | Qt.TextWordWrap, self.message)


class StoryPreviewWindow(QDialog):
    """Scrollable, read-only full composition with lazy protected thumbnails."""

    cache_limit = 12
    batch_limit = 3
    prefetch_viewports = 0.7

    idle = Signal()

    def __init__(self, parent=None, *, title="", introduction="", elements=(),
                 theme_key="editorial", hide_filenames=False, source_stamps=None,
                 source_aspects=None):
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("KIMng - Preview entire story")
        self.resize(1220, 880)
        self.setMinimumSize(620, 500)
        self.setWindowModality(Qt.WindowModal)
        self._closing = False
        self.stopped = False
        self.thumbnail_worker = None
        self.thumbnail_paths = []
        self.thumbnail_items = {}
        self.thumbnail_timer = QTimer(self)
        self.thumbnail_timer.setSingleShot(True)
        self.thumbnail_timer.setInterval(65)
        self.thumbnail_timer.timeout.connect(self.load_visible_images)
        self.image_cache = OrderedDict()
        self._unavailable_paths = set()
        self.source_stamps = dict(source_stamps or {})
        self.source_aspects = dict(source_aspects or {})
        self.theme_key = theme_key if theme_key in PRESENTATIONS else "editorial"
        self.presentation = PRESENTATIONS[self.theme_key]
        self.hide_filenames = bool(hide_filenames)
        self.title_text = str(title)
        self.introduction_text = str(introduction)
        self.elements = tuple(self._copy_element(element) for element in elements)
        self.element_order = tuple(element.id for element in self.elements)
        self.rendered_element_ids = ()
        self.element_widgets = {}
        self.image_views = {}
        self.caption_labels = {}
        self.heading_labels = {}
        self.section_labels = {}
        self.passage_labels = {}
        self.image_elements = {}
        self.image_view_by_path = {}
        self.image_blocks = {}
        self.image_ordinals = {}
        self.image_treatments = {}
        self.pair_containers = {}
        self._rendered = []
        self.composition_plan = build_composition_plan(self.elements, self.source_aspects)

        self._build_window()
        self.idle.connect(self._finish_close_if_ready)
        self._build_publication()
        self._apply_presentation()
        self._layout_page()

    @staticmethod
    def _copy_element(element):
        return StoryElementSnapshot(
            str(element.kind), str(element.id), str(element.source),
            str(element.heading), str(element.caption), str(element.text))

    def _build_window(self):
        self.setStyleSheet(f"QDialog {{ background: {self.presentation['paper']}; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("storyPreviewToolbar")
        bar.setFixedHeight(54)
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(22, 0, 22, 0)
        brand = QLabel("KIMng  /  PHOTO STORY")
        brand.setObjectName("storyPreviewBrand")
        self.theme_name = QLabel(self.presentation["name"])
        self.theme_name.setObjectName("storyPreviewThemeName")
        self.close_button = QPushButton("Close preview")
        self.close_button.setIcon(QIcon.fromTheme("window-close"))
        self.close_button.clicked.connect(self.reject)
        bar_layout.addWidget(brand)
        bar_layout.addSpacing(18)
        bar_layout.addWidget(self.theme_name)
        bar_layout.addStretch(1)
        bar_layout.addWidget(self.close_button)
        outer.addWidget(bar)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.setAccessibleName("Complete chronological Photo Story")
        self.stage = QWidget()
        self.stage.setObjectName("storyPreviewStage")
        self.stage_layout = QVBoxLayout(self.stage)
        self.stage_layout.setContentsMargins(0, 0, 0, 0)
        self.stage_layout.addWidget(self._make_page(), 0, Qt.AlignHCenter | Qt.AlignTop)
        self.scroll.setWidget(self.stage)
        outer.addWidget(self.scroll, 1)
        self.scroll.verticalScrollBar().valueChanged.connect(self.schedule_visible_images)
        self.scroll.viewport().installEventFilter(self)

    def _make_page(self):
        self.page = QFrame()
        self.page.setObjectName("storyPublicationPage")
        self.page.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.page_layout = QVBoxLayout(self.page)
        self.page_layout.setSpacing(0)
        self.page_layout.setAlignment(Qt.AlignTop)
        self.opening = QFrame()
        self.opening.setObjectName("storyOpening")
        self.opening_layout = QVBoxLayout(self.opening)
        self.opening_layout.setSpacing(0)
        self.opening_layout.setAlignment(Qt.AlignTop)
        self.opening_header = QFrame()
        self.opening_header.setObjectName("storyOpeningHeader")
        self.opening_header_layout = QVBoxLayout(self.opening_header)
        self.opening_header_layout.setContentsMargins(0, 0, 0, 0)
        self.opening_header_layout.setSpacing(14)
        self.eyebrow_label = QLabel("A PHOTO STORY")
        self.eyebrow_label.setObjectName("storyOpeningEyebrow")
        self.eyebrow_label.setTextFormat(Qt.PlainText)
        self.title_label = QLabel(self.title_text if self.title_text.strip() else "Untitled story")
        self.title_label.setObjectName("storyOpeningTitle")
        self.title_label.setTextFormat(Qt.PlainText)
        self.title_label.setWordWrap(True)
        self.title_label.setAccessibleName("Story title")
        self.introduction_label = QLabel(self.introduction_text)
        self.introduction_label.setObjectName("storyOpeningIntroduction")
        self.introduction_label.setTextFormat(Qt.PlainText)
        self.introduction_label.setWordWrap(True)
        self.introduction_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.introduction_label.setVisible(bool(self.introduction_text.strip()))
        self.opening_meta_row = QHBoxLayout()
        self.opening_meta_row.setContentsMargins(0, 0, 0, 0)
        self.opening_meta_row.setSpacing(36)
        self.opening_meta_row.addWidget(self.title_label, 3)
        self.opening_meta_row.addWidget(self.introduction_label, 2)
        self.opening_header_layout.addWidget(self.eyebrow_label)
        self.opening_header_layout.addLayout(self.opening_meta_row)
        self.opening_layout.addWidget(self.opening_header)
        self.page_layout.addWidget(self.opening)
        self.empty_state = QLabel("Nothing to preview yet")
        self.empty_state.setObjectName("storyPreviewEmptyState")
        self.empty_state.setAlignment(Qt.AlignCenter)
        self.empty_state.setTextFormat(Qt.PlainText)
        self.empty_state.setMinimumHeight(220)
        self.empty_state.hide()
        self.page_layout.addWidget(self.empty_state)
        self.folio = QLabel("KIMng   ·   PHOTO STORY")
        self.folio.setObjectName("storyPreviewFolio")
        self.folio.setAlignment(Qt.AlignCenter)
        self.folio.setTextFormat(Qt.PlainText)
        self.page_layout.addSpacing(72)
        self.page_layout.addWidget(self.folio)
        self.page_layout.addSpacing(44)
        return self.page

    def _build_publication(self):
        section_number = 0
        elements_by_id = {element.id: element for element in self.elements}
        has_cover = bool(self.composition_plan and self.composition_plan[0].kind == "cover")
        if has_cover:
            cover = elements_by_id[self.composition_plan[0].element_ids[0]]
            block = self._make_image_block(cover, 0, cover=True, treatment="cover")
            if self.presentation["cover_layout"] == "photo-first":
                self.opening_layout.removeWidget(self.opening_header)
                photo = self.image_views[cover.id]
                block.layout().removeWidget(photo)
                hero = QFrame()
                hero.setObjectName("storyCinematicHero")
                hero_layout = QGridLayout(hero)
                hero_layout.setContentsMargins(0, 0, 0, 0)
                hero_layout.setSpacing(0)
                hero_layout.addWidget(photo, 0, 0)
                self.opening_header.setSizePolicy(
                    QSizePolicy.Expanding, QSizePolicy.Maximum)
                hero_layout.addWidget(self.opening_header, 0, 0, Qt.AlignBottom)
                block.layout().insertWidget(0, hero)
                self.opening_layout.insertWidget(0, block)
            else:
                self.opening_layout.addWidget(block)
            self.element_widgets[cover.id] = block
            self._rendered.append(cover.id)

        for composition in self.composition_plan[1 if has_cover else 0:]:
            members = [elements_by_id[element_id] for element_id in composition.element_ids]
            if composition.kind == "pair":
                block = QFrame()
                block.setObjectName("storyPhotoPair")
                block.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                pair_layout = QHBoxLayout(block)
                pair_layout.setContentsMargins(0, 0, 0, 0)
                pair_layout.setSpacing(self.presentation["pair_spacing"])
                for element in members:
                    image_block = self._make_image_block(
                        element, len(self.image_views), cover=False, treatment="paired")
                    pair_layout.addWidget(image_block, 1)
                    self.element_widgets[element.id] = image_block
                    self.pair_containers[element.id] = block
                    self._rendered.append(element.id)
                self.page_layout.insertWidget(self.page_layout.count() - 3, block, Qt.AlignHCenter)
                continue

            element = members[0]
            if composition.kind == "image":
                block = self._make_image_block(
                    element, len(self.image_views), cover=False,
                    treatment=composition.treatment)
                alignment = self._element_alignment(element)
            elif composition.kind == "heading":
                if not element.heading.strip():
                    continue
                section_number += 1
                block = self._make_section(element, section_number)
                alignment = Qt.AlignHCenter
            elif composition.kind == "text":
                if not element.text.strip():
                    continue
                block = self._make_passage(element)
                alignment = Qt.AlignHCenter
            else:
                continue
            self.page_layout.insertWidget(self.page_layout.count() - 3, block, alignment)
            self.element_widgets[element.id] = block
            self._rendered.append(element.id)

        self.rendered_element_ids = tuple(self._rendered)
        self.empty_state.setVisible(not self._rendered)
        self._set_element_spacing()

    def _make_image_block(self, element, image_ordinal, *, cover, treatment):
        spec = self.presentation
        filename = Path(element.source).name
        block = QFrame()
        block.setObjectName("storyPhotographBlock")
        block.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        heading_text = element.heading
        authored_heading = bool(heading_text.strip())
        if not authored_heading and not self.hide_filenames:
            heading_text = Path(element.source).stem
        elif not authored_heading:
            heading_text = ""
        if heading_text and not cover:
            self._add_photo_heading(layout, element, heading_text, authored_heading)

        photo = StoryImageView(
            element.id, filename, cover=cover,
            source_aspect=self.source_aspects.get(element.source))
        photo.setObjectName(f"storyPhoto-{element.id}")
        photo.set_presentation(spec, cover=cover)
        layout.addWidget(photo)
        self.image_views[element.id] = photo
        self.image_elements[element.id] = element
        self.image_view_by_path[element.source] = photo
        self.image_blocks[element.id] = block
        self.image_ordinals[element.id] = image_ordinal
        self.image_treatments[element.id] = treatment

        if heading_text and cover:
            self._add_photo_heading(layout, element, heading_text, authored_heading)

        if element.caption.strip():
            caption = QLabel(element.caption)
            caption.setObjectName("storyPhotographCaption")
            caption.setTextFormat(Qt.PlainText)
            caption.setWordWrap(True)
            caption.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(caption)
            self.caption_labels[element.id] = caption
        return block

    def _add_photo_heading(self, layout, element, heading_text, authored_heading):
        heading = QLabel(heading_text)
        heading.setObjectName(
            "storyPhotographHeading" if authored_heading
            else "storyPhotographAutoHeading")
        heading.setTextFormat(Qt.PlainText)
        heading.setWordWrap(True)
        heading.setAccessibleName("Photograph heading")
        layout.addWidget(heading)
        self.heading_labels[element.id] = heading

    def _make_section(self, element, section_number):
        block = QFrame()
        block.setObjectName("storySectionBreak")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 8, 0, 4)
        layout.setSpacing(18)
        rule = QFrame()
        rule.setObjectName("storySectionRule")
        rule.setFixedHeight(2)
        label = QLabel(f"SECTION  {section_number:02d}")
        label.setObjectName("storySectionEyebrow")
        label.setTextFormat(Qt.PlainText)
        title = QLabel(element.heading)
        title.setObjectName("storySectionTitle")
        title.setTextFormat(Qt.PlainText)
        title.setWordWrap(True)
        title.setAccessibleName("Section heading")
        layout.addWidget(rule)
        layout.addWidget(label)
        layout.addWidget(title)
        self.section_labels[element.id] = title
        return block

    def _make_passage(self, element):
        spec = self.presentation
        block = QFrame()
        block.setObjectName("storyPassage")
        block.setMaximumWidth(spec.get("text_width", 900))
        layout = QVBoxLayout(block)
        if spec["passage_treatment"] in ("journal-note", "museum-card", "postcard-note", "bold-panel", "midnight-panel", "cinema-panel"):
            layout.setContentsMargins(28, 24, 28, 24)
        else:
            layout.setContentsMargins(24, 8, 24, 8)
        passage = QLabel(element.text)
        passage.setObjectName("storyPassageText")
        passage.setTextFormat(Qt.PlainText)
        passage.setWordWrap(True)
        passage.setTextInteractionFlags(Qt.TextSelectableByMouse)
        passage.setAccessibleName("Narrative passage")
        layout.addWidget(passage)
        self.passage_labels[element.id] = passage
        return block

    def _apply_presentation(self):
        spec = self.presentation
        self.setStyleSheet(f"QDialog {{ background-color: {spec['paper']}; }}")
        self.findChild(QFrame, "storyPreviewToolbar").setStyleSheet(
            f"QFrame#storyPreviewToolbar {{ background: {spec['page']}; border-bottom: 1px solid {spec['outline']}; }}"
            f"QLabel#storyPreviewBrand {{ color: {spec['ink']}; font-size: 10px; font-weight: 700; letter-spacing: 1px; }}"
            f"QLabel#storyPreviewThemeName {{ color: {spec['muted']}; font-size: 12px; }}"
        )
        self.close_button.setStyleSheet(
            f"QPushButton {{ color: {spec['ink']}; background: transparent; border: 1px solid {spec['outline']};"
            " border-radius: 5px; padding: 7px 14px; }"
            f"QPushButton:hover {{ background: {spec['surface']}; }}"
        )
        self.stage.setStyleSheet(f"QWidget#storyPreviewStage {{ background: {spec['paper']}; }}")
        opening_header_background = (
            "qlineargradient(x1: 0, y1: 0, x2: 0, y2: 1, "
            "stop: 0 rgba(9, 11, 15, 0), stop: 0.18 rgba(9, 11, 15, 145), "
            "stop: 1 rgba(9, 11, 15, 188))"
            if self.theme_key == "cinematic" else spec["page"]
        )
        self.page.setStyleSheet(
            f"QFrame#storyPublicationPage {{ background: {spec['page']}; color: {spec['ink']}; }}"
            f"QFrame#storyOpeningHeader {{ background: {opening_header_background}; }}"
            f"QLabel#storyOpeningEyebrow {{ color: {spec['accent']}; font-family: '{spec['body_font']}'; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}"
            f"QLabel#storyOpeningTitle {{ color: {spec['ink']}; font-family: '{spec['display_font']}'; font-size: {spec['title_size']}px; font-weight: 700; }}"
            f"QLabel#storyOpeningIntroduction {{ color: {spec['muted']}; font-family: '{spec['body_font']}'; font-size: {spec['intro_size']}px; }}"
            f"QLabel#storyPhotographHeading {{ color: {spec['ink']}; font-family: '{spec['display_font']}'; font-size: {max(20, spec['section_size'] - 6)}px; font-weight: 600; padding-top: 16px; padding-bottom: 4px; }}"
            f"QLabel#storyPhotographAutoHeading {{ color: {spec['muted']}; font-family: '{spec['body_font']}'; font-size: 10px; font-weight: 700; letter-spacing: 1px; padding-top: 12px; padding-bottom: 2px; }}"
            f"QLabel#storyPhotographCaption {{ color: {spec['muted']}; font-family: '{spec['body_font']}'; font-size: 14px; font-style: italic; padding-top: 7px; }}"
            f"QLabel#storySectionEyebrow {{ color: {spec['accent']}; font-family: '{spec['body_font']}'; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}"
            f"QLabel#storySectionTitle {{ color: {spec['ink']}; font-family: '{spec['display_font']}'; font-size: {spec['section_size']}px; font-weight: 700; }}"
            f"QFrame#storySectionRule {{ background: {spec['accent']}; border: none; }}"
            f"QFrame#storyPassage {{ background: {self._passage_surface()}; border-left: {self._passage_border()}px solid {spec['accent']}; }}"
            f"QLabel#storyPassageText {{ color: {spec['ink']}; font-family: '{spec['body_font']}'; font-size: {spec['body_size']}px; }}"
            f"QLabel#storyPreviewEmptyState {{ color: {spec['muted']}; font-family: '{spec['display_font']}'; font-size: 22px; }}"
            f"QLabel#storyPreviewFolio {{ color: {spec['muted']}; font-family: '{spec['body_font']}'; font-size: 10px; letter-spacing: 2px; }}"
        )
        self.theme_name.setText(spec["name"])
        self._apply_title_alignment()

    def _passage_surface(self):
        treatment = self.presentation["passage_treatment"]
        if treatment in ("journal-note", "postcard-note"):
            return self.presentation["surface"]
        if treatment in ("museum-card", "bold-panel", "cinema-panel", "midnight-panel"):
            return self.presentation["surface"]
        return self.presentation["page"]

    def _passage_border(self):
        return 4 if self.presentation["passage_treatment"] in ("bold-panel", "cinema-panel") else 2

    def _apply_title_alignment(self):
        alignment = Qt.AlignHCenter if self.presentation["center_title"] else Qt.AlignLeft
        self.title_label.setAlignment(alignment | Qt.AlignVCenter)
        self.introduction_label.setAlignment(alignment | Qt.AlignVCenter)
        for label in self.section_labels.values():
            label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def _set_element_spacing(self):
        spacing = 42 if self.theme_key == "cinematic" else 54
        self.page_layout.setSpacing(spacing)

    def _layout_page(self):
        if not hasattr(self, "scroll"):
            return
        width = max(0, min(self.presentation["page_width"], self.scroll.viewport().width()))
        if width:
            self.stage.setFixedWidth(self.scroll.viewport().width())
            self.page.setFixedWidth(width)
            spec = self.presentation
            gutter = spec["page_gutter"]
            if width < 820 and gutter:
                gutter = min(gutter, 22)
            self.page_layout.setContentsMargins(gutter, 0, gutter, 48)
            header_gutter = 54 if self.theme_key == "cinematic" else 0
            header_top = 30 if self.theme_key in ("cinematic", "journal") else 46
            header_bottom = 44 if self.theme_key == "cinematic" else 32
            self.opening_header_layout.setContentsMargins(
                header_gutter, header_top, header_gutter, header_bottom)
            self.opening_meta_row.setDirection(
                QBoxLayout.TopToBottom if width < 820 else QBoxLayout.LeftToRight)
            self.opening_meta_row.setSpacing(18 if width < 820 else 36)
            base_title_size = spec["title_size"]
            title_size = base_title_size if width >= 820 else max(34, round(base_title_size * width / 820))
            self.title_label.setStyleSheet(f"font-size: {title_size}px;")
            self.title_label.setAlignment(
                (Qt.AlignHCenter if spec["center_title"] else Qt.AlignLeft) | Qt.AlignVCenter)
            self.introduction_label.setAlignment(
                (Qt.AlignHCenter if spec["center_title"] else Qt.AlignLeft) | Qt.AlignVCenter)
            content_width = max(180, width - gutter * 2)
            for element_id, block in self.image_blocks.items():
                treatment = self.image_treatments[element_id]
                view = self.image_views.get(element_id)
                if view is None:
                    continue
                factor = {
                    "cover": 1.0,
                    "feature": spec["photo_width"],
                    "detail": spec["photo_width"] * 0.78,
                    "paired": 0.48,
                }.get(treatment, spec["photo_width"])
                image_width = max(200, int(content_width * factor))
                block.setMaximumWidth(image_width)
                view.set_width_limit(image_width)
                if treatment == "paired":
                    pair = self.pair_containers[element_id]
                    pair.setMaximumWidth(content_width)
                    pair_width = max(200, int((content_width - spec["pair_spacing"]) / 2))
                    block.setMaximumWidth(pair_width)
                    view.set_width_limit(pair_width)
            for element_id in self.passage_labels:
                self.element_widgets[element_id].setMaximumWidth(
                    min(content_width, spec["text_width"]))

    def _element_alignment(self, element):
        if element.kind != "image" or self.image_treatments.get(element.id) != "detail":
            return Qt.AlignHCenter
        if self.image_ordinals[element.id] % 2:
            return Qt.AlignRight
        return Qt.AlignLeft

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._layout_page)

    def eventFilter(self, watched, event):
        if watched is self.scroll.viewport() and event.type() == QEvent.Resize:
            self._layout_page()
            self.schedule_visible_images()
        return super().eventFilter(watched, event)

    def showEvent(self, event):
        super().showEvent(event)
        self.scroll.verticalScrollBar().setValue(0)
        self.schedule_visible_images()

    def schedule_visible_images(self, *_):
        if not self.stopped:
            self.thumbnail_timer.start()

    def load_visible_images(self):
        if self.stopped or self.thumbnail_worker is not None:
            return
        viewport = self.scroll.viewport()
        top = self.scroll.verticalScrollBar().value()
        height = viewport.height()
        prefetch = int(height * self.prefetch_viewports)
        visible = []
        for element_id, view in self.image_views.items():
            element = self.image_elements[element_id]
            if element.source in self.unavailable_paths:
                continue
            rect_top = view.mapTo(self.stage, QPoint(0, 0)).y()
            rect_bottom = rect_top + view.height()
            if rect_bottom >= top - prefetch and rect_top <= top + height + prefetch:
                if element.source in self.image_cache:
                    self._show_cached(element.source, view)
                else:
                    distance = max(0, rect_top - (top + height // 2))
                    visible.append((distance, element.source, element_id))
        visible.sort(key=lambda row: row[0])
        paths = []
        self.thumbnail_items = {}
        for _, path, element_id in visible:
            if path in paths:
                continue
            expected = self.source_stamps.get(path)
            try:
                valid_source = expected is not None and identity(path) == expected
            except (OSError, ValueError):
                valid_source = False
            if not valid_source:
                self._mark_unavailable(path, element_id, "Source changed or is unavailable")
                continue
            paths.append(path)
            self.thumbnail_items[path] = element_id
            if len(paths) >= self.batch_limit:
                break
        if paths:
            target_width = min(1280, max(640, int(viewport.width() * 1.25)))
            target_height = min(960, max(480, int(target_width * 0.75)))
            self.thumbnail_paths = list(paths)
            self.thumbnail_worker = ThumbnailWorker(paths, QSize(target_width, target_height), self)
            self.thumbnail_worker.thumbnail_ready.connect(self._receive_thumbnail)
            self.thumbnail_worker.finished.connect(self._thumbnail_worker_finished)
            self.thumbnail_worker.start()

    def _show_cached(self, path, view):
        cached = self.image_cache.get(path)
        if cached is None:
            return
        image, stamp = cached
        try:
            unchanged = stamp == self.source_stamps.get(path) and identity(path) == stamp
        except (OSError, ValueError):
            unchanged = False
        if not unchanged:
            self._discard_path(path)
            self._mark_unavailable(path, view.element_id, "Source changed after preview")
            return
        self.image_cache.move_to_end(path)
        view.show_image(image)

    @property
    def unavailable_paths(self):
        return self._unavailable_paths

    def _receive_thumbnail(self, path, image, stamp):
        if self.stopped or self.sender() is not self.thumbnail_worker:
            return
        element_id = self.thumbnail_items.get(path)
        view = self.image_views.get(element_id)
        expected = self.source_stamps.get(path)
        try:
            valid = (not image.isNull() and stamp is not None and stamp == expected
                     and identity(path) == expected)
        except (OSError, ValueError):
            valid = False
        if not valid:
            worker = self.thumbnail_worker
            reason = worker.errors.get(path, "Source changed or image could not be decoded")
            self._mark_unavailable(path, element_id, reason)
            return
        self.image_cache[path] = (image, stamp)
        self.image_cache.move_to_end(path)
        if view is not None:
            view.show_image(image)
        while len(self.image_cache) > self.cache_limit:
            expired, _ = self.image_cache.popitem(last=False)
            old_view = self.image_view_by_path.get(expired)
            if old_view is not None:
                old_view.release_image()
        self.schedule_visible_images()

    def _mark_unavailable(self, path, element_id, reason):
        if not hasattr(self, "_unavailable_paths"):
            self._unavailable_paths = set()
        self._unavailable_paths.add(path)
        view = self.image_views.get(element_id) if element_id else self.image_view_by_path.get(path)
        if view is not None:
            view.show_unavailable(reason)

    def _discard_path(self, path):
        self.image_cache.pop(path, None)
        self._mark_unavailable(path, None, "Source changed after preview")

    def _thumbnail_worker_finished(self):
        worker, self.thumbnail_worker = self.thumbnail_worker, None
        worker.wait()
        worker.deleteLater()
        self.thumbnail_paths = []
        self.thumbnail_items = {}
        if self.stopped:
            self.idle.emit()
        else:
            self.schedule_visible_images()

    def stop(self):
        self.stopped = True
        self.thumbnail_timer.stop()
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.requestInterruption()

    def _finish_close_if_ready(self):
        if self._closing and self.thumbnail_worker is None:
            QDialog.done(self, QDialog.Rejected)

    def reject(self):
        if self.thumbnail_worker is not None:
            self._closing = True
            self.stop()
            return
        self.stop()
        super().reject()

    def closeEvent(self, event):
        if self.thumbnail_worker is not None:
            self._closing = True
            self.stop()
            event.ignore()
        else:
            self.stop()
            event.accept()
