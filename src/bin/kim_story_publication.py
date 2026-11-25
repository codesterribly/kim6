#!/usr/bin/env python3
"""Offline Photo Story composition, rendering, and safe derivative preparation.

The public seam accepts an immutable StoryDocument. It does not depend on the
editor or a browser, and returns portable document, stylesheet, and optional
viewer assets plus deterministic image names. File reading is delegated to
KIMng's descriptor-backed image reader.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import html
import os
from pathlib import Path
from pathlib import PurePosixPath
import re
import shutil
import uuid
import zipfile


GALLERY_TYPES = ("travelogue", "photo-essay", "illustrated-story", "simple-gallery")
VISUAL_STYLES = ("classic", "modern", "dramatic", "simple-light", "simple-dark")
LEGACY_STYLES = ("cinematic", "editorial", "journal")
STYLE_ALIASES = {
    "simple-light": "journal",
    "simple-dark": "cinematic",
    "classic": "journal", "modern": "editorial", "dramatic": "cinematic",
    "cinematic": "cinematic", "editorial": "editorial", "journal": "journal",
}
PUBLICATION_TYPES = GALLERY_TYPES
IMAGE_LAYOUTS = ("one-per-section", "two-per-section", "adaptive", "justified", "masonry")
WEBSITE_STRUCTURES = ("single-page", "multiple-pages")
OUTPUT_FORMATS = ("folder", "zip")
UNASSIGNED_COLLECTION_ID = "kimng-unassigned"
TYPE_DEFAULT_LAYOUTS = {
    "simple-gallery": "one-per-section",
    "travelogue": "one-per-section",
    "photo-essay": "adaptive",
    "illustrated-story": "one-per-section",
}
DERIVATIVE_MAX_SIZE = (1800, 1800)
DERIVATIVE_QUALITY = 88


@dataclass(frozen=True)
class StoryElement:
    kind: str
    id: str
    heading: str = ""
    caption: str = ""
    text: str = ""
    output_image: str = ""
    source: str = ""
    source_identity: tuple | None = None
    image_width: int = 0
    image_height: int = 0
    blocked_reason: str = ""
    # Kept separate from the legacy short caption for old in-memory callers.
    description: str = ""


@dataclass(frozen=True)
class StoryDocument:
    title: str
    introduction: str
    publication_type: str
    style: str
    hide_filenames: bool
    elements: tuple[StoryElement, ...]
    show_captions: bool = False
    layout: str = "adaptive"
    output_format: str = "folder"
    website_structure: str = "single-page"
    collections: tuple[StoryCollection, ...] = ()


@dataclass(frozen=True)
class StoryCollection:
    id: str
    title: str
    element_ids: tuple[str, ...]
    description: str = ""
    cover_image_id: str = ""


@dataclass(frozen=True)
class CompositionBlock:
    kind: str
    elements: tuple[StoryElement, ...]


@dataclass(frozen=True)
class RenderedWebsite:
    html: str
    css: str
    viewer_css: str
    viewer_js: str
    pages: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class PreparedImage:
    element_id: str
    source: str
    source_identity: tuple
    relative_path: str
    width: int
    height: int
    byte_size: int
    sha256: str
    staged_path: str


@dataclass(frozen=True)
class BlockedImage:
    element_id: str
    source: str
    reason: str


@dataclass(frozen=True)
class PreparedPublication:
    document: StoryDocument
    workspace: str
    images: tuple[PreparedImage, ...]
    index_html: str
    style_css: str
    viewer_css: str
    viewer_js: str
    blocked: tuple[BlockedImage, ...] = ()
    warnings: tuple[str, ...] = ()
    pages: tuple[tuple[str, str], ...] = ()


def collection_page_name(collection: StoryCollection) -> str:
    if collection.id == UNASSIGNED_COLLECTION_ID:
        return "unassigned.html"
    return f"collection-{_slug(collection.title, 'collection')}.html"


def publication_collections(document: StoryDocument) -> tuple[StoryCollection, ...]:
    """Return authored sections plus a visible home for unassigned content."""
    if not document.collections and document.website_structure == "single-page":
        return ()
    assigned = {element_id for item in document.collections for element_id in item.element_ids}
    unassigned = tuple(item.id for item in document.elements if item.id not in assigned)
    sections = document.collections
    if unassigned or not sections:
        title = "Unassigned" if sections else "All images"
        sections += (StoryCollection(UNASSIGNED_COLLECTION_ID, title, unassigned),)
    return sections


def output_pages(document: StoryDocument) -> tuple[str, ...]:
    return ("index.html", *(collection_page_name(item) for item in publication_collections(document))) if document.website_structure == "multiple-pages" else ("index.html",)


def _escape(value: str) -> str:
    return html.escape(value or "", quote=True)


def _slug(value: str, fallback: str = "story") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").casefold()).strip("-")
    return (slug[:64].rstrip("-") or fallback)


def publication_slug(value: str) -> str:
    """Stable portable folder name for one reviewed website destination."""
    return _slug(value, "photo-story")


def default_layout_for_type(gallery_type: str) -> str:
    try:
        return TYPE_DEFAULT_LAYOUTS[gallery_type]
    except KeyError as exc:
        raise ValueError("Unsupported gallery type") from exc


def canonical_visual_style(style: str) -> str:
    if style in VISUAL_STYLES:
        return style
    return {"journal": "classic", "editorial": "modern", "cinematic": "dramatic"}.get(style, "")


def validate_document(document: StoryDocument) -> None:
    if document.publication_type not in PUBLICATION_TYPES:
        raise ValueError("Unsupported gallery type")
    if document.style not in (*VISUAL_STYLES, *LEGACY_STYLES):
        raise ValueError("Choose Classic, Modern, or Dramatic visual style")
    if document.layout not in IMAGE_LAYOUTS:
        raise ValueError("Choose a supported preferred image layout")
    if document.output_format not in OUTPUT_FORMATS:
        raise ValueError("Choose Gallery folder or ZIP archive output format")
    if document.website_structure not in WEBSITE_STRUCTURES:
        raise ValueError("Choose Single page or Multiple pages website structure")
    ids = set()
    outputs = set()
    for element in document.elements:
        if element.kind not in {"image", "heading", "text"}:
            raise ValueError("Unknown Photo Story element type")
        if not element.id or element.id in ids:
            raise ValueError("Story element IDs must be present and unique")
        ids.add(element.id)
        if element.kind == "image":
            if not element.source or (not element.output_image and not element.blocked_reason):
                raise ValueError("Every image needs a source and prepared output name")
            if element.output_image:
                output_path = PurePosixPath(element.output_image)
                if (output_path.is_absolute() or ".." in output_path.parts
                        or len(output_path.parts) != 2 or output_path.parts[0] != "images"
                        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*\.jpg",
                                             output_path.name)):
                    raise ValueError("Image output paths must be local to the website")
                if element.output_image in outputs:
                    raise ValueError("Every website image needs a unique output filename")
                outputs.add(element.output_image)
    if document.collections:
        collection_ids = set()
        names = set()
        pages = set()
        members = []
        images = {element.id for element in document.elements if element.kind == "image"}
        for collection in document.collections:
            if (not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", collection.id)
                    or collection.id == UNASSIGNED_COLLECTION_ID or collection.id in collection_ids):
                raise ValueError("Collection IDs must be safe and unique")
            collection_ids.add(collection.id)
            if not collection.title.strip():
                raise ValueError("Every collection needs a title")
            name = collection.title.strip().casefold()
            page = collection_page_name(collection)
            if name in names or page in pages or page in {"index.html", "style.css", "gallery-viewer.css", "gallery-viewer.js"}:
                raise ValueError("Collection names and page names must be unique")
            names.add(name)
            pages.add(page)
            members.extend(collection.element_ids)
            if collection.cover_image_id and (collection.cover_image_id not in collection.element_ids or collection.cover_image_id not in images):
                raise ValueError("A collection cover must be an image in that collection")
        if len(members) != len(set(members)) or not set(members).issubset(ids):
            raise ValueError("Story elements may belong to only one collection")


def composition_plan(document: StoryDocument) -> tuple[CompositionBlock, ...]:
    """Return deterministic editorial blocks without changing element order.

    The first image is reserved for the opening hero. Headings and text always
    terminate a spread. Pair eligibility uses approved derivative dimensions
    when present, never incidental editor-thumbnail cache state.
    """
    validate_document(document)
    elements = document.elements
    if document.layout in ("justified", "masonry"):
        result = []
        pending = []
        def flush():
            if pending:
                result.append(CompositionBlock(document.layout, tuple(pending)))
                pending.clear()
        for element in elements:
            if element.kind == "image":
                pending.append(element)
            else:
                flush()
                result.append(CompositionBlock("section" if element.kind == "heading" else "passage", (element,)))
        flush()
        return tuple(result)
    result: list[CompositionBlock] = []
    index = 0
    if elements and elements[0].kind == "image":
        result.append(CompositionBlock("hero", (elements[0],)))
        index = 1
    feature_next = False
    while index < len(elements):
        element = elements[index]
        if element.kind == "heading":
            result.append(CompositionBlock("section", (element,)))
            index += 1
        elif element.kind == "text":
            result.append(CompositionBlock("passage", (element,)))
            index += 1
        else:
            next_image = elements[index + 1] if index + 1 < len(elements) else None
            can_pair = (
                document.layout != "one-per-section"
                and next_image is not None
                and next_image.kind == "image"
                and _compatible_images(element, next_image)
            )
            if document.layout == "adaptive":
                can_pair = can_pair and not feature_next
            if can_pair:
                result.append(CompositionBlock("pair", (element, elements[index + 1])))
                index += 2
            else:
                result.append(CompositionBlock("feature", (element,)))
                index += 1
            feature_next = not feature_next if document.layout == "adaptive" else False
    return tuple(result)


def _compatible_images(first: StoryElement, second: StoryElement) -> bool:
    """Pair images with compatible known shapes; unknown pairs stay deterministic."""
    first_known = first.image_width > 0 and first.image_height > 0
    second_known = second.image_width > 0 and second.image_height > 0
    if not first_known or not second_known:
        return not first_known and not second_known
    first_ratio = first.image_width / first.image_height
    second_ratio = second.image_width / second.image_height
    if (first_ratio >= 1) != (second_ratio >= 1):
        return False
    return abs(first_ratio - second_ratio) <= 0.7


def _paragraphs(value: str) -> str:
    paragraphs = re.split(r"\n\s*\n", value or "")
    output = []
    for paragraph in paragraphs:
        if not paragraph.strip():
            continue
        output.append("<p>" + "<br>\n".join(_escape(line) for line in paragraph.splitlines()) + "</p>")
    return "\n".join(output)


def _story_image_render_width(element: StoryElement) -> str:
    """Bound story text to the responsive dimensions of its displayed image."""
    image_width = max(0, int(element.image_width))
    image_height = max(0, int(element.image_height))
    if not image_width or not image_height:
        return "100%"
    ratio = image_width / image_height
    return f"min(100%, {image_width}px, calc(83svh * {ratio:.8f}))"


def _section_id(element: StoryElement) -> str:
    token = re.sub(r"[^a-zA-Z0-9_-]+", "-", element.id).strip("-")[:48]
    suffix = hashlib.sha256(element.id.encode()).hexdigest()[:8]
    return "section-" + (token or "chapter") + "-" + suffix


def _image_figure(element: StoryElement, *, variant: str, document: StoryDocument) -> str:
    source = _escape(element.output_image)
    heading = element.heading or ""
    caption = element.caption or ""
    accessible_name = heading.strip() or (
        element.description.strip().splitlines()[0] if element.description.strip()
        else caption.strip())
    viewer_caption = (f' data-viewer-caption="{_escape(caption)}"'
                      if document.show_captions and caption.strip() else "")
    dimensions = (f' width="{element.image_width}" height="{element.image_height}"'
                  if element.image_width > 0 and element.image_height > 0 else "")
    title_markup = f'<h2 class="image-heading">{_escape(heading)}</h2>' if heading.strip() else ""
    caption_markup = (f'<figcaption>{_escape(caption)}</figcaption>'
                      if document.show_captions and caption.strip() else "")
    filename_markup = (
        f'<p class="image-filename">{_escape(Path(element.source).name)}</p>'
        if not document.hide_filenames and element.source else "")
    image_markup = (
        '<div class="unavailable-image" role="img" aria-label="Photograph unavailable">'
        '<span>Photograph unavailable</span></div>'
        if element.blocked_reason else
        f'<a class="gallery-viewer-trigger" href="{source}" '
        f'aria-label="Enlarge image: {_escape(accessible_name or "Photograph")}" '
        f'aria-haspopup="dialog"{viewer_caption}><img src="{source}" alt="{_escape(accessible_name)}"'
        f'{dimensions} loading="lazy" decoding="async"></a>'
    )
    return (
        f'<figure class="photograph {variant}">'
        f'{title_markup}{image_markup}'
        f'{caption_markup}{filename_markup}</figure>'
    )


def _image_story(element: StoryElement, document: StoryDocument, *, variant: str) -> str:
    prose = _paragraphs(element.description)
    description = (f'<div class="image-description prose" '
                   f'data-description-for="{_escape(element.id)}">{prose}</div>'
                   if prose else "")
    image_style = (
        ' style="--story-image-render-width: '
        f'{_story_image_render_width(element)}; '
        f'--image-ratio: {element.image_width / element.image_height:.8f};"'
        if element.image_width > 0 and element.image_height > 0 else ""
    )
    return (
        f'<article class="image-story-item {variant} type-image-{document.publication_type}" '
        f'data-element-id="{_escape(element.id)}"{image_style}>'
        f'{_image_figure(element, variant="story-photograph", document=document)}'
        f'{description}</article>'
    )


def render_website(document: StoryDocument, *, hero: bool = True) -> RenderedWebsite:
    """Render an offline, semantic website using only local assets."""
    validate_document(document)
    if document.collections or document.website_structure == "multiple-pages":
        return _render_collections(document)
    blocks = composition_plan(document)
    headings = [block.elements[0] for block in blocks
                if block.kind == "section" and block.elements[0].heading.strip()]
    toc = "".join(
        f'<li><a href="#{_section_id(item)}">{_escape(item.heading.strip())}</a></li>'
        for item in headings
    )
    title_value = document.title or ""
    title = _escape(title_value)
    title_markup = (f'<h1 class="story-title">{title}</h1>' if title_value.strip() else
                    '<h1 class="story-title placeholder">Untitled story</h1>')
    document_title = title if title_value.strip() else "Untitled story"
    intro = _paragraphs(document.introduction)
    gallery_type = document.publication_type
    style_key = canonical_visual_style(document.style)
    type_labels = {
        "travelogue": ("TRAVELOGUE · FIELD NOTES", "Read the journey", "Chapters", "Chapter"),
        "photo-essay": ("PHOTO ESSAY", "Explore the essay", "Sections", "Sequence"),
        "illustrated-story": ("ILLUSTRATED STORY", "Read the story", "Contents", "Part"),
        "simple-gallery": ("GALLERY", "View images", "Sections", "Section"),
    }
    masthead, reading_label, contents_label, chapter_label = type_labels[gallery_type]
    opening_image = ""
    hero_render_width = ""
    if hero and blocks and blocks[0].kind == "hero":
        hero_element = blocks[0].elements[0]
        opening_image = _image_story(hero_element, document, variant="hero-image")
        hero_render_width = _story_image_render_width(hero_element)
        blocks = blocks[1:]

    content = []
    section_positions = [(i, block.elements[0]) for i, block in enumerate(blocks)
                         if block.kind == "section" and block.elements[0].heading.strip()]
    section_by_index = {index: (item, ordinal) for ordinal, (index, item) in enumerate(section_positions)}
    for index, block in enumerate(blocks):
        if index in section_by_index:
            element, ordinal = section_by_index[index]
            section_id = _section_id(element)
            content.append(
                f'<section class="chapter chapter-{gallery_type}" id="{section_id}" data-element-id="{_escape(element.id)}">'
                f'<p class="chapter-kicker">{chapter_label} {ordinal + 1:02d}</p>'
                f'<h2>{_escape(element.heading.strip())}</h2>'
            )
            previous_element = section_positions[ordinal - 1][1] if ordinal else None
            next_element = section_positions[ordinal + 1][1] if ordinal + 1 < len(section_positions) else None
            links = ['<a href="#top">Back to opening</a>']
            if previous_element:
                links.append(f'<a href="#{_section_id(previous_element)}">Previous chapter</a>')
            if next_element:
                links.append(f'<a href="#{_section_id(next_element)}">Next chapter</a>')
            content.append('<nav class="chapter-nav" aria-label="Section navigation">' + "".join(links) + "</nav>")
            content.append("</section>")
        elif block.kind == "section":
            # Empty headings have no visible content and never create dead TOC targets.
            continue
        elif block.kind == "passage":
            element = block.elements[0]
            paragraphs = _paragraphs(element.text)
            if paragraphs:
                content.append(f'<section class="narrative narrative-{gallery_type}" data-element-id="{_escape(element.id)}"><div class="prose">{paragraphs}</div></section>')
        elif block.kind == "pair":
            stories = "".join(
                _image_story(item, document, variant="paired-image")
                for item in block.elements)
            content.append(
                f'<div class="image-pair layout-{document.layout}">{stories}</div>')
        elif block.kind in ("justified", "masonry"):
            stories = "".join(_image_story(item, document, variant="gallery-image")
                              for item in block.elements)
            if block.kind == "justified":
                stories += '<span class="justified-filler" aria-hidden="true"></span>'
            content.append(f'<div class="image-group layout-{block.kind}">{stories}</div>')
        else:
            element = block.elements[0]
            variant = "wide-image" if block.kind == "feature" else "story-image"
            content.append(
                f'<div class="image-feature layout-{document.layout}">'
                f'{_image_story(element, document, variant=variant)}</div>')

    nav = '<a class="home-link" href="#top" aria-label="Return to opening">Opening</a>'
    nav += f'<a class="read-link" href="#story">{reading_label}</a>'
    if toc:
        nav += f'<details class="contents"><summary>{contents_label}</summary><ol>{toc}</ol></details>'
    else:
        nav += '<span class="contents-hint">A visual story</span>'
    cover_class = "cover has-hero" if opening_image else "cover"
    hero_style = (f' style="--hero-image-render-width: {hero_render_width};"'
                  if hero_render_width else "")
    body_classes = " ".join((f"publication style-{document.style}",
                              f"visual-style-{style_key}", f"gallery-type-{gallery_type}"))
    from kim_gallery_viewer import gallery_viewer_assets
    viewer_assets = gallery_viewer_assets()
    html_doc = f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>{document_title}</title>
<link rel="stylesheet" href="style.css">
<link rel="stylesheet" href="gallery-viewer.css">
<script src="gallery-viewer.js" defer></script>
</head>
<body class="{body_classes}" data-publication-type="{_escape(document.publication_type)}" data-gallery-type="{gallery_type}" data-visual-style="{style_key}" data-image-layout="{document.layout}" data-output-format="{document.output_format}">
<a class="skip-link" href="#story">Skip to story</a>
<nav class="site-nav" aria-label="Publication navigation">{nav}</nav>
<header class="{cover_class}" id="top"{hero_style}>
<div class="cover-copy"><p class="masthead">{masthead}</p>{title_markup}
<div class="introduction">{intro}</div></div>
{opening_image}
</header>
<main id="story" class="story-flow">
{''.join(content)}
</main>
<footer class="story-ending"><a href="#top">Return to opening <span aria-hidden="true">↑</span></a></footer>
<dialog class="gallery-viewer" id="gallery-viewer" aria-label="Image viewer">
<div class="gallery-viewer__layout">
<div class="gallery-viewer__toolbar" aria-label="Image viewer controls">
<button type="button" data-viewer-action="close" aria-label="Close image viewer">Close</button>
<button type="button" data-viewer-action="previous" aria-label="Previous image">Previous</button>
<button type="button" data-viewer-action="zoom-out" aria-label="Zoom out">−</button>
<button type="button" data-viewer-action="fit" aria-label="Fit image to screen">Fit</button>
<button type="button" data-viewer-action="zoom-in" aria-label="Zoom in">+</button>
<button type="button" data-viewer-action="next" aria-label="Next image">Next</button>
</div>
<div class="gallery-viewer__stage" tabindex="0" aria-label="Enlarged image">
<img class="gallery-viewer__image" alt="">
</div>
<p class="gallery-viewer__caption" aria-label="Image caption"></p>
<p class="gallery-viewer__status" aria-live="polite"></p>
</div>
</dialog>
</body>
</html>'''
    return RenderedWebsite(html_doc, _stylesheet(style_key, gallery_type) + _arrangement_css(),
                           viewer_assets.stylesheet, viewer_assets.script)


def _main_content(html_text: str) -> str:
    return html_text.split('<main id="story" class="story-flow">', 1)[1].split("</main>", 1)[0]


def _render_collections(document: StoryDocument) -> RenderedWebsite:
    sections = publication_collections(document)
    by_id = {element.id: element for element in document.elements}
    children = []
    cards = []
    for collection in sections:
        members = tuple(by_id[element_id] for element_id in collection.element_ids)
        child = replace(document, title=collection.title, introduction=collection.description,
                        elements=members, collections=(), website_structure="single-page")
        rendered = render_website(child, hero=False)
        children.append(rendered)
        cover_id = collection.cover_image_id or next(
            (item.id for item in members if item.kind == "image" and item.output_image), "")
        cover = by_id.get(cover_id)
        cover_markup = (f'<img src="{_escape(cover.output_image)}" alt="" loading="lazy">'
                        if cover and cover.output_image else
                        '<span class="collection-card-empty">No cover image</span>')
        description = _paragraphs(collection.description)
        href = (collection_page_name(collection) if document.website_structure == "multiple-pages"
                else f"#collection-{collection.id}")
        cards.append(f'<a class="collection-card" href="{_escape(href)}">'
                     f'{cover_markup}<span class="collection-card-copy"><strong>{_escape(collection.title)}</strong>'
                     f'{description}</span></a>')
    landing = render_website(replace(document, elements=(), collections=(),
                                     website_structure="single-page"))
    cards_markup = '<nav class="collection-cards" aria-label="Sections">' + "".join(cards) + '</nav>'
    if document.website_structure == "single-page":
        section_markup = []
        for collection, child in zip(sections, children):
            description = _paragraphs(collection.description)
            section_markup.append(f'<section class="collection-section" id="collection-{collection.id}">'
                                  f'<header><h2>{_escape(collection.title)}</h2>{description}</header>'
                                  f'{_main_content(child.html)}</section>')
        html_text = landing.html.replace('<main id="story" class="story-flow">',
                                         '<main id="story" class="story-flow">' + cards_markup + "".join(section_markup), 1)
        return replace(landing, html=html_text)
    html_text = landing.html.replace('<main id="story" class="story-flow">',
                                     '<main id="story" class="story-flow">' + cards_markup, 1)
    pages = []
    for index, (collection, child) in enumerate(zip(sections, children)):
        links = ['<a href="index.html">All sections</a>']
        if index:
            previous = sections[index - 1]
            links.append(f'<a href="{_escape(collection_page_name(previous))}">Previous section</a>')
        if index + 1 < len(sections):
            following = sections[index + 1]
            links.append(f'<a href="{_escape(collection_page_name(following))}">Next section</a>')
        navigation = '<nav class="collection-page-nav" aria-label="Section navigation">' + "".join(links) + '</nav>'
        page_html = child.html.replace('<main id="story" class="story-flow">',
                                       navigation + '<main id="story" class="story-flow">', 1)
        pages.append((collection_page_name(collection), page_html))
    return replace(landing, html=html_text, pages=tuple(pages))


def _arrangement_css() -> str:
    return r'''
.collection-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 17rem), 1fr)); gap: 1.25rem; margin: 2rem auto 5rem; }
.collection-card { display: block; overflow: hidden; color: inherit; text-decoration: none; border: 1px solid currentColor; border-radius: .35rem; }
.collection-card img { display: block; width: 100%; height: 13rem; object-fit: contain; background: #7772; }
.collection-card-copy { display: block; padding: 1rem; }
.collection-card-copy strong { display: block; font-size: 1.25rem; }
.collection-card-copy p { margin: .5rem 0 0; }
.collection-card-empty { display: block; padding: 5rem 1rem; text-align: center; }
.collection-section { margin: 5rem 0; scroll-margin-top: 5rem; }
.collection-section > header { max-width: 50rem; margin: 0 auto 2rem; }
.collection-page-nav { display: flex; gap: 1.5rem; flex-wrap: wrap; width: min(100% - 3rem, 76rem); margin: 1rem auto; }
.image-group { width: 100%; margin: 2rem auto 4rem; }
.image-group .image-story-item { display: block; width: 100%; max-width: none; margin: 0; }
.image-group .photograph { width: 100%; margin: 0; }
.image-group .photograph img { display: block; width: 100%; height: auto; max-height: none; object-fit: contain; }
.image-group .image-description { width: 100%; max-width: none; }
.image-group.layout-justified { display: flex; flex-wrap: wrap; gap: .75rem; align-items: start; }
.layout-justified .image-story-item { flex: var(--image-ratio, 1) 1 calc(var(--image-ratio, 1) * 14rem); min-width: min(100%, 9rem); }
.layout-justified .justified-filler { flex: 1000 1 14rem; height: 0; }
.image-group.layout-masonry { columns: 3 15rem; column-gap: .9rem; }
.layout-masonry .image-story-item { break-inside: avoid; margin: 0 0 .9rem; }
@media (max-width: 700px) {
  .image-group.layout-masonry { columns: 2 10rem; }
  .layout-justified .image-story-item { flex-basis: calc(var(--image-ratio, 1) * 10rem); }
}
@media (max-width: 430px) { .image-group.layout-masonry { columns: 1; } }
'''


def _stylesheet(style: str, gallery_type: str = "photo-essay") -> str:
    theme_key = STYLE_ALIASES.get(style, style)
    return (_theme_stylesheet(theme_key) + _gallery_type_styles(gallery_type)
            + _gallery_refinement_css() + _simple_gallery_css(gallery_type)
            + _simple_gallery_accessibility_css(gallery_type))



def _gallery_refinement_css() -> str:
    """Approved gallery presentation family."""
    return r'''

/* KIMng Gallery book, After dark, and Visual magazine. */

body.publication {
    --gallery-bg: #f8fafb;
    --gallery-ink: #162534;
    --gallery-muted: #566875;
    --gallery-line: #bac9d2;
    --gallery-accent: #1769a3;
    --gallery-width: 90rem;
    --gallery-font: Georgia, "Times New Roman", serif;
    --gallery-display: Georgia, "Times New Roman", serif;
    background: var(--gallery-bg);
    color: var(--gallery-ink);
}

body.publication.visual-style-cinematic {
    --gallery-bg: #0c0f13;
    --gallery-ink: #f3f1ed;
    --gallery-muted: #b4b9bf;
    --gallery-line: #343c45;
    --gallery-accent: #c1d5db;
    --gallery-width: 95rem;
    --gallery-display: Arial, Helvetica, sans-serif;
}

body.publication.visual-style-editorial {
    --gallery-bg: #e8eef2;
    --gallery-ink: #14202b;
    --gallery-muted: #445565;
    --gallery-line: #9ab0bd;
    --gallery-accent: #0961ae;
    --gallery-width: 93rem;
    --gallery-font: Arial, Helvetica, sans-serif;
    --gallery-display: Arial, Helvetica, sans-serif;
}

/* Compact navigation shared by all three designs. */

body.publication .site-nav {
    min-height: 3.2rem;
    padding: .45rem clamp(1.2rem, 4vw, 4rem);
    background: var(--gallery-bg);
    color: var(--gallery-ink);
    border-bottom: 1px solid var(--gallery-line);
    backdrop-filter: none;
}

body.publication .contents ol {
    background: var(--gallery-bg);
    color: var(--gallery-ink);
    border: 1px solid var(--gallery-line);
}

/* Opening: typography and photograph, no oversized panel. */

body.publication .cover,
body.publication .cover.has-hero {
    display: block;
    width: 100%;
    max-width: none;
    min-height: 0;
    height: auto;
    margin: 0;
    padding: 0;
    background: transparent;
    color: var(--gallery-ink);
    overflow: visible;
}

body.publication .cover.has-hero::after {
    display: none;
    content: none;
}

body.publication .cover .cover-copy,
body.publication .cover.has-hero .cover-copy {
    position: static;
    inset: auto;
    display: block;
    width: min(calc(100% - 2.5rem), var(--gallery-width));
    max-width: none;
    margin: 0 auto;
    padding: clamp(1.6rem, 3.2vw, 3.1rem) 0
             clamp(.9rem, 1.5vw, 1.5rem);
    transform: none;
    background: transparent;
    color: var(--gallery-ink);
    z-index: auto;
}

body.publication .masthead,
body.publication .chapter-kicker {
    color: var(--gallery-accent);
    font: 750 .72rem/1.5 system-ui, sans-serif;
    letter-spacing: .18em;
}

body.publication .cover .masthead {
    margin-bottom: .6rem;
}

body.publication .cover .story-title {
    max-width: 30ch;
    margin: 0;
    color: var(--gallery-ink);
    font-family: var(--gallery-display);
    font-size: clamp(2.6rem, 5.3vw, 5.5rem);
    font-weight: 500;
    line-height: 1.04;
    letter-spacing: -.05em;
}

body.publication .cover .story-title.placeholder {
    opacity: .55;
    font-size: clamp(2rem, 3.8vw, 3.8rem);
}

body.publication .cover .introduction {
    max-width: 44rem;
    margin: .65rem 0 0;
    color: var(--gallery-muted);
    font-family: var(--gallery-font);
    font-size: clamp(1rem, 1.4vw, 1.18rem);
    line-height: 1.6;
}

body.publication .cover .introduction:empty {
    display: none;
}

/* The opening photograph occupies the available width. */

body.publication .cover.has-hero .hero-image {
    position: static;
    display: block;
    width: min(calc(100% - 2.5rem), var(--gallery-width));
    max-width: none;
    height: auto;
    min-height: 0;
    margin: 0 auto;
    padding: 0;
    background: transparent;
    grid-row: auto;
    grid-column: auto;
}

body.publication .cover.has-hero .hero-image .image-story-item,
body.publication .cover.has-hero .hero-image .photograph {
    display: block;
    width: 100%;
    margin: 0;
}

body.publication .cover.has-hero .hero-image img {
    display: block;
    width: auto;
    max-width: 100%;
    height: auto;
    max-height: 83svh;
    margin: 0 auto;
    object-fit: contain;
    outline: 0;
}

/* The scrolling story. */

body.publication .story-flow {
    width: min(calc(100% - 2.5rem), var(--gallery-width));
    max-width: none;
    margin: 0 auto;
}

body.publication .image-feature,
body.publication .image-feature:nth-of-type(odd),
body.publication .image-feature:nth-of-type(even) {
    display: block;
    width: 100%;
    max-width: none;
    margin: clamp(1.8rem, 3.4vw, 3.7rem) auto;
    padding: 0;
}

/* One image means one image, followed by its description. */

body.publication .image-feature.layout-one-per-section
.image-story-item {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 0;
    width: 100%;
    max-width: none;
    margin: 0;
    padding: 0;
}

body.publication .image-feature.layout-one-per-section .photograph,
body.publication .image-feature.layout-one-per-section:nth-of-type(even)
.photograph {
    display: block;
    order: 0;
    grid-row: auto;
    grid-column: auto;
    width: 100%;
    max-width: none;
    margin: 0;
    padding: 0;
    border: 0;
}

body.publication .image-feature.layout-one-per-section
.photograph img,
body.publication .image-feature.layout-adaptive
.photograph img {
    width: auto;
    max-width: 100%;
    height: auto;
    max-height: 83svh;
    margin: 0 auto;
    object-fit: contain;
    outline: none;
}


/* Single-image composition shares one measured image/prose width. */
body.publication .image-feature.layout-one-per-section
.image-story-item {
    width: var(--story-image-render-width, 100%);
    max-width: 100%;
    margin-inline: auto;
}

body.publication .image-feature.layout-one-per-section
.photograph img {
    margin-inline: 0;
}

body.publication .image-feature.layout-one-per-section
.image-description {
    width: 100%;
    max-width: 100%;
    margin: 1rem 0 0;
    padding: 0;
}

/* Descriptions are always underneath, with readable line lengths. */

body.publication .image-feature.layout-one-per-section
.image-description,
body.publication .cover.has-hero .image-description {
    position: static;
    display: block;
    order: 1;
    grid-row: auto;
    grid-column: auto;
    width: 100%;
    max-width: 100%;
    margin: clamp(1rem, 2vw, 1.8rem) 0 0;
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--gallery-ink);
}

/* The cover copy and hero story share the image's measured responsive width. */
body.publication .cover.has-hero > .cover-copy {
    width: min(100%, var(--hero-image-render-width, var(--gallery-width)));
    max-width: none;
    margin-inline: auto;
    padding-inline: 0;
}

body.publication .cover.has-hero > .hero-image {
    width: min(100%, var(--story-image-render-width, 100%));
    max-width: 100%;
    margin-inline: auto;
}

body.publication .cover.has-hero > .hero-image > .image-description {
    width: 100%;
    max-width: 100%;
    margin-inline: 0;
}

body.publication .image-description.prose,
body.publication .narrative .prose {
    font-family: var(--gallery-font);
    font-size: clamp(1.07rem, 1.5vw, 1.36rem);
    line-height: 1.65;
}

body.publication .image-description.prose p {
    margin: 0 0 .9em;
}

body.publication .image-description.prose p:last-child {
    margin-bottom: 0;
}

body.publication .image-description:empty {
    display: none;
}

/* Two images: balanced pairs, each retaining its own description. */

body.publication .image-pair,
body.publication .image-pair.layout-two-per-section {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    align-items: start;
    width: 100%;
    max-width: none;
    gap: clamp(.8rem, 2vw, 2rem);
    margin: clamp(1.8rem, 3.4vw, 3.7rem) auto;
}

body.publication .image-pair .paired-image,
body.publication .image-pair .paired-image:nth-child(2) {
    margin: 0;
    padding: 0;
}

body.publication .image-pair .photograph img {
    display: block;
    width: auto;
    max-width: 100%;
    height: auto;
    max-height: 72svh;
    margin: 0 auto;
    object-fit: contain;
}

body.publication .image-pair .image-description {
    width: 100%;
    max-width: none;
    margin: .9rem 0 0;
    padding: 0;
    border: 0;
    background: transparent;
    color: var(--gallery-ink);
}

/* Optional headings and captions. */

body.publication .image-heading {
    margin: 0 0 .65rem;
    color: var(--gallery-accent);
    font: 650 clamp(.94rem, 1.1vw, 1.1rem)/1.4
          system-ui, sans-serif;
}

body.publication figcaption {
    color: var(--gallery-muted);
}

/* Chapter and passage typography. */

body.publication .chapter {
    width: 100%;
    margin: clamp(2.6rem, 5vw, 5rem) auto
            clamp(1.25rem, 2.8vw, 2.5rem);
    padding: 1rem 0 0;
    border-top: 1px solid var(--gallery-line);
}

body.publication .chapter h2 {
    margin: .3rem 0 1rem;
    font-family: var(--gallery-display);
    font-size: clamp(2rem, 4vw, 4.5rem);
    line-height: 1.08;
}

body.publication .chapter-nav {
    gap: 1.4rem;
}

body.publication .narrative {
    width: 100%;
    max-width: none;
    margin: clamp(1.5rem, 3vw, 3rem) auto;
    padding: 0;
    background: transparent;
}

body.publication .narrative .prose {
    max-width: 47rem;
    margin: 0 auto;
}

body.publication .story-ending {
    padding: 2.5rem 1rem 3rem;
    border-top: 1px solid var(--gallery-line);
}

/* A. Gallery book. */

body.publication.visual-style-journal
.cover .story-title {
    font-weight: 500;
}

body.publication.visual-style-journal
.photograph img {
    box-shadow: 0 20px 40px -36px #23384870;
    outline: 0;
}

/* B. After dark. */

body.publication.visual-style-cinematic
.cover .story-title {
    font-family: Arial, Helvetica, sans-serif;
    font-weight: 800;
    font-size: clamp(2.7rem, 5.7vw, 6rem);
    text-transform: uppercase;
    letter-spacing: -.065em;
}

body.publication.visual-style-cinematic
.photograph img {
    outline: 0;
}

/* C. Visual magazine. */

body.publication.visual-style-editorial
.cover .story-title {
    font-family: Arial, Helvetica, sans-serif;
    font-weight: 850;
    font-size: clamp(2.7rem, 5.5vw, 5.8rem);
    line-height: 1;
    letter-spacing: -.063em;
    text-transform: uppercase;
}

body.publication.visual-style-editorial
.cover .masthead {
    border-left: 4px solid var(--gallery-accent);
    padding-left: .8rem;
}


/* Single-image composition shares one measured image/prose width. */
body.publication .image-feature.layout-one-per-section
.image-story-item {
    width: var(--story-image-render-width, 100%);
    max-width: 100%;
    margin-inline: auto;
}

body.publication .image-feature.layout-one-per-section
.photograph img {
    margin-inline: 0;
}

body.publication .image-feature.layout-one-per-section
.image-description {
    width: 100%;
    max-width: 100%;
    margin: 1rem 0 0;
    padding: 0;
}

/* Responsive layouts. */

@media (max-width: 800px) {
    body.publication .cover .cover-copy,
    body.publication .cover.has-hero .hero-image,
    body.publication .story-flow {
        width: min(calc(100% - 2rem), 46rem);
    }

    body.publication .cover .cover-copy {
        padding: 1.5rem 0 1rem;
    }

    body.publication .image-feature.layout-one-per-section
    .image-story-item {
        display: flex;
        flex-direction: column;
    }

    body.publication .image-pair,
    body.publication .image-pair.layout-two-per-section {
        grid-template-columns: minmax(0, 1fr);
        gap: 1.6rem;
    }

    body.publication .image-description.prose {
        font-size: 1.12rem;
    }

    body.publication .image-feature {
        margin: 1.7rem auto;
    }
}

body.publication .cover.has-hero > .cover-copy {
    width: min(100%, var(--hero-image-render-width, var(--gallery-width)));
}

body.publication .cover.has-hero > .hero-image {
    width: min(100%, var(--story-image-render-width, 100%));
}

body.publication.visual-style-modern.gallery-type-photo-essay
.cover.has-hero > .cover-copy {
    width: min(calc(100% - 2rem),
               var(--hero-image-render-width, var(--gallery-width)));
}

body.publication.visual-style-modern.gallery-type-photo-essay
.cover.has-hero > .hero-image {
    width: min(calc(100% - 2rem),
               var(--story-image-render-width, 100%));
}

'''


def _simple_gallery_css(gallery_type: str) -> str:
    """Additional styling for the simple gallery type."""
    if gallery_type != "simple-gallery":
        return ""
    return '\nbody.gallery-type-simple-gallery {\n    --simple-bg: #ffffff;\n    --simple-ink: #17212b;\n    --simple-muted: #536270;\n    --simple-rule: #d8e0e7;\n    background: var(--simple-bg);\n    color: var(--simple-ink);\n    font-family: system-ui, sans-serif;\n}\n\nbody.gallery-type-simple-gallery.visual-style-simple-dark {\n    --simple-bg: #12161c;\n    --simple-ink: #f1f4f7;\n    --simple-muted: #b4c1cc;\n    --simple-rule: #34404b;\n}\n\nbody.gallery-type-simple-gallery .site-nav {\n    min-height: 3rem;\n    padding: .6rem clamp(1rem, 3vw, 3rem);\n    background: var(--simple-bg);\n    color: var(--simple-ink);\n    border-bottom: 1px solid var(--simple-rule);\n}\n\nbody.gallery-type-simple-gallery .contents ol {\n    background: var(--simple-bg);\n    color: var(--simple-ink);\n    border: 1px solid var(--simple-rule);\n}\n\nbody.gallery-type-simple-gallery .cover,\nbody.gallery-type-simple-gallery .cover.has-hero {\n    display: block;\n    width: min(calc(100% - 2rem), 82rem);\n    min-height: 0;\n    height: auto;\n    margin: 0 auto;\n    padding: 0;\n    background: transparent;\n    color: var(--simple-ink);\n    overflow: visible;\n}\n\nbody.gallery-type-simple-gallery .cover.has-hero::after {\n    display: none;\n}\n\nbody.gallery-type-simple-gallery .cover-copy,\nbody.gallery-type-simple-gallery .cover.has-hero .cover-copy {\n    position: static;\n    inset: auto;\n    transform: none;\n    width: 100%;\n    max-width: none;\n    margin: 0;\n    padding: clamp(1.5rem, 3vw, 2.5rem) 0 1.25rem;\n    background: transparent;\n    color: var(--simple-ink);\n}\n\nbody.gallery-type-simple-gallery .story-title,\nbody.gallery-type-simple-gallery .cover .story-title {\n    max-width: none;\n    margin: 0;\n    color: var(--simple-ink);\n    font: 700 clamp(2rem, 3.5vw, 3.7rem)/1.1\n          system-ui, sans-serif;\n    letter-spacing: -.035em;\n    text-transform: none;\n}\n\nbody.gallery-type-simple-gallery .masthead {\n    color: var(--simple-muted);\n}\n\nbody.gallery-type-simple-gallery .introduction,\nbody.gallery-type-simple-gallery .cover .introduction {\n    color: var(--simple-muted);\n    max-width: 72ch;\n    margin: .75rem 0 0;\n    font: 400 1.1rem/1.65 system-ui, sans-serif;\n}\n\nbody.gallery-type-simple-gallery .hero-image,\nbody.gallery-type-simple-gallery .cover.has-hero .hero-image {\n    display: block;\n    position: static;\n    width: var(--story-image-render-width, 100%);\n    max-width: 100%;\n    height: auto;\n    min-height: 0;\n    margin: 0 auto;\n    padding: 0;\n    background: transparent;\n}\n\nbody.gallery-type-simple-gallery .hero-image img {\n    display: block;\n    width: auto;\n    max-width: 100%;\n    height: auto;\n    max-height: 83svh;\n    margin: 0;\n    object-fit: contain;\n}\n\nbody.gallery-type-simple-gallery .story-flow {\n    width: min(calc(100% - 2rem), 82rem);\n    margin: 0 auto;\n}\n\nbody.gallery-type-simple-gallery\n.image-feature.layout-one-per-section {\n    display: block;\n    width: 100%;\n    margin: clamp(1.75rem, 3vw, 3rem) auto;\n}\n\nbody.gallery-type-simple-gallery\n.image-feature.layout-one-per-section .image-story-item {\n    display: flex;\n    flex-direction: column;\n    align-items: stretch;\n    width: var(--story-image-render-width, 100%);\n    max-width: 100%;\n    margin: 0 auto;\n    padding: 0;\n    gap: 0;\n}\n\nbody.gallery-type-simple-gallery\n.image-feature.layout-one-per-section .photograph {\n    order: 0;\n    display: block;\n    width: 100%;\n    margin: 0;\n    padding: 0;\n    grid-column: auto;\n    grid-row: auto;\n}\n\nbody.gallery-type-simple-gallery\n.image-feature.layout-one-per-section .photograph img {\n    display: block;\n    width: auto;\n    max-width: 100%;\n    height: auto;\n    max-height: 83svh;\n    margin: 0;\n    object-fit: contain;\n    outline: none;\n}\n\nbody.gallery-type-simple-gallery\n.image-feature.layout-one-per-section .image-description {\n    order: 1;\n    display: block;\n    position: static;\n    width: 100%;\n    max-width: none;\n    margin: 1rem 0 0;\n    padding: 0;\n    grid-column: auto;\n    grid-row: auto;\n    background: transparent;\n    color: var(--simple-ink);\n}\n\nbody.gallery-type-simple-gallery .image-description.prose,\nbody.gallery-type-simple-gallery .narrative .prose {\n    color: var(--simple-ink);\n    font: 400 clamp(1rem, 1.25vw, 1.18rem)/1.65\n          system-ui, sans-serif;\n}\n\nbody.gallery-type-simple-gallery .image-pair {\n    display: grid;\n    grid-template-columns: repeat(2, minmax(0, 1fr));\n    gap: clamp(1rem, 2vw, 2rem);\n    align-items: start;\n}\n\nbody.gallery-type-simple-gallery .image-pair .paired-image,\nbody.gallery-type-simple-gallery\n.image-pair .paired-image:nth-child(2) {\n    margin-top: 0;\n}\n\nbody.gallery-type-simple-gallery .image-pair .image-description {\n    width: 100%;\n    margin: 1rem 0 0;\n    padding: 0;\n    background: transparent;\n    color: var(--simple-ink);\n}\n\nbody.gallery-type-simple-gallery .chapter {\n    margin: 3rem 0 1.5rem;\n    border-top: 1px solid var(--simple-rule);\n}\n\nbody.gallery-type-simple-gallery .chapter h2 {\n    color: var(--simple-ink);\n    font: 700 clamp(1.7rem, 3vw, 2.7rem)/1.2\n          system-ui, sans-serif;\n}\n\nbody.gallery-type-simple-gallery .narrative {\n    margin: 2rem auto;\n    padding: 0;\n    background: transparent;\n}\n\nbody.gallery-type-simple-gallery .story-ending {\n    border-top: 1px solid var(--simple-rule);\n    color: var(--simple-muted);\n}\n\n@media (max-width: 760px) {\n    body.gallery-type-simple-gallery .image-pair {\n        grid-template-columns: minmax(0, 1fr);\n    }\n\n    body.gallery-type-simple-gallery .cover,\n    body.gallery-type-simple-gallery .story-flow {\n        width: min(calc(100% - 1.5rem), 46rem);\n    }\n}\n'


def _simple_gallery_accessibility_css(gallery_type: str) -> str:
    """Keep shared publication colors aligned with the Simple Dark palette."""
    if gallery_type != "simple-gallery":
        return ""
    return r'''
body.gallery-type-simple-gallery.visual-style-simple-dark {
    --gallery-bg: var(--simple-bg);
    --gallery-ink: var(--simple-ink);
    --gallery-muted: var(--simple-muted);
    --gallery-line: var(--simple-rule);
    --gallery-accent: #83caff;
}
'''


def _gallery_type_styles(gallery_type: str) -> str:
    if gallery_type == "travelogue":
        return r'''
/* Travelogue pairs one generous photograph with room for the account. */
.gallery-type-travelogue .story-flow { width: min(100% - 3rem, 86rem); }
.gallery-type-travelogue .image-feature.layout-one-per-section .image-story-item { grid-template-columns: minmax(0, 1.12fr) minmax(18rem, .88fr); }
.gallery-type-travelogue .image-feature.layout-one-per-section .image-description { max-width: 39rem; }
.gallery-type-travelogue .chapter-travelogue { padding: clamp(1.5rem, 4vw, 3rem) 0; border-block: 1px solid currentColor; }
.gallery-type-travelogue .chapter-kicker { text-transform: uppercase; }
@media (max-width: 700px) { .gallery-type-travelogue .image-feature.layout-one-per-section .image-story-item { grid-template-columns: minmax(0, 1fr); } }
'''
    if gallery_type == "illustrated-story":
        return r'''
/* Illustrated story gives the prose the leading column and lets images support it. */
.gallery-type-illustrated-story .story-flow { width: min(100% - 3rem, 78rem); }
.gallery-type-illustrated-story .image-feature.layout-one-per-section .image-story-item { grid-template-columns: minmax(18rem, .82fr) minmax(0, 1.18fr); align-items: start; }
.gallery-type-illustrated-story .image-feature.layout-one-per-section .image-description { grid-column: 1; grid-row: 1; margin: 0; padding: clamp(.5rem, 2vw, 1.5rem) clamp(1rem, 3vw, 3rem) 0 0; }
.gallery-type-illustrated-story .image-feature.layout-one-per-section .photograph { grid-column: 2; grid-row: 1; }
.gallery-type-illustrated-story .image-feature.layout-one-per-section .image-description.prose { font-size: clamp(1.1rem, 1.6vw, 1.32rem); line-height: 1.86; }
.gallery-type-illustrated-story .narrative-illustrated-story { max-width: 66rem; padding: clamp(1rem, 3vw, 2.6rem) 0; }
.gallery-type-illustrated-story .narrative-illustrated-story .prose { max-width: 48rem; }
.gallery-type-illustrated-story .chapter-illustrated-story { max-width: 58rem; margin-left: 0; border-top: 2px solid currentColor; }
@media (max-width: 700px) { .gallery-type-illustrated-story .image-feature.layout-one-per-section .image-story-item { grid-template-columns: minmax(0, 1fr); } .gallery-type-illustrated-story .image-feature.layout-one-per-section .image-description, .gallery-type-illustrated-story .image-feature.layout-one-per-section .photograph { grid-column: 1; grid-row: auto; } }
'''
    return r'''
/* Photo essay lets the image sequence lead and uses commentary as a quiet counterpoint. */
.gallery-type-photo-essay .story-flow { width: min(100% - 3rem, 92rem); }
.gallery-type-photo-essay .image-feature.layout-adaptive { width: min(100%, 88rem); }
.gallery-type-photo-essay .chapter-photo-essay { max-width: 70rem; }
.gallery-type-photo-essay .narrative-photo-essay { max-width: 58rem; }
'''


def _theme_stylesheet(style: str) -> str:
    common = r'''
* { box-sizing: border-box; }
html { scroll-behavior: smooth; scroll-padding-top: 5rem; }
body { margin: 0; min-width: 0; font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
img { display: block; max-width: 100%; }
.unavailable-image { display: grid; place-items: center; width: 100%; min-height: 12rem; aspect-ratio: 3 / 2; padding: 1.5rem; border: 1px dashed currentColor; opacity: .68; font-size: .85rem; letter-spacing: .08em; text-align: center; text-transform: uppercase; }
a { color: inherit; }
a:focus-visible, summary:focus-visible { outline: 3px solid currentColor; outline-offset: 4px; }
.skip-link { position: fixed; left: 1rem; top: -5rem; z-index: 20; padding: .8rem 1rem; background: #fff; color: #111; }
.skip-link:focus { top: 1rem; }
.site-nav { position: sticky; top: 0; z-index: 10; display: flex; align-items: center; gap: 1.5rem; min-height: 3.7rem; padding: .55rem clamp(1rem, 4vw, 4rem); backdrop-filter: blur(16px); }
.site-nav a, .contents summary { text-decoration: none; font-size: .76rem; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; cursor: pointer; }
.contents { position: relative; margin-left: auto; }
.contents ol { position: absolute; right: 0; top: 1.8rem; width: min(22rem, calc(100vw - 2rem)); max-height: 65vh; overflow: auto; margin: 0; padding: .6rem; list-style: none; box-shadow: 0 1rem 3rem #0003; }
.contents li a { display: block; padding: .65rem .8rem; line-height: 1.35; text-transform: none; letter-spacing: 0; }
.cover { position: relative; min-height: min(92vh, 880px); display: grid; align-content: center; overflow: hidden; }
.cover-copy { position: relative; z-index: 2; width: min(100% - 3rem, 76rem); margin: 0 auto; padding: clamp(4rem, 10vh, 8rem) 0; }
.masthead, .chapter-kicker { margin: 0 0 1.1rem; font-size: .72rem; font-weight: 750; letter-spacing: .22em; text-transform: uppercase; }
.story-title { max-width: 15ch; margin: 0; font-size: clamp(3rem, 9vw, 8.3rem); line-height: .91; letter-spacing: -.065em; text-wrap: balance; }
.story-title, .chapter h2, figcaption, .prose { overflow-wrap: anywhere; }
.story-title.placeholder { opacity: .62; }
.introduction { max-width: 42rem; margin-top: 2rem; font-size: clamp(1.08rem, 1.8vw, 1.42rem); line-height: 1.65; }
.introduction p { margin: 0 0 1em; white-space: pre-wrap; }
.hero-image { width: min(100% - 3rem, 88rem); margin: 0 auto 3rem; }
.hero-image img { width: 100%; max-height: 73vh; object-fit: contain; }
.story-flow { width: min(100% - 3rem, 82rem); margin: 0 auto; }
.photograph { margin: 0; min-width: 0; }
.photograph img { width: 100%; height: auto; }
.image-feature { margin: clamp(3.5rem, 9vw, 9rem) 0; }
.image-story-item { min-width: 0; }
.image-description { max-width: 46rem; margin: 1.15rem auto 0; }
.image-description:empty { display: none; }
.image-description.prose { font-size: clamp(1.04rem, 1.42vw, 1.22rem); line-height: 1.78; }
.image-description.prose p { margin-bottom: 1.05em; }
.image-filename { margin: .55rem 0 0; font-size: .72rem; opacity: .64; }
.image-feature.layout-one-per-section .image-story-item { display: grid; grid-template-columns: minmax(0, 1.2fr) minmax(18rem, .8fr); align-items: center; gap: clamp(1.5rem, 4vw, 4.5rem); }
.image-feature.layout-one-per-section .photograph img { max-height: 78vh; object-fit: contain; }
.image-feature.layout-one-per-section .image-description { width: 100%; max-width: 43rem; margin: 0; }
.image-pair.layout-two-per-section { align-items: start; gap: clamp(1rem, 2.6vw, 2.8rem); }
.image-pair.layout-two-per-section .image-story-item { min-width: 0; }
.image-pair.layout-two-per-section .image-description { width: 100%; font-size: clamp(1rem, 1.25vw, 1.12rem); line-height: 1.7; }
.image-pair.layout-two-per-section .photograph img { max-height: 62vh; object-fit: contain; }
.image-feature.layout-adaptive .image-description { max-width: 49rem; }
.wide-image img { max-height: 86vh; object-fit: contain; }
.paired-image img { max-height: 72vh; object-fit: contain; }
.image-pair { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); align-items: center; gap: clamp(1rem, 3vw, 3.5rem); margin: clamp(3rem, 7vw, 7rem) 0; }
.image-heading { margin: 1rem 0 .35rem; font-size: 1.15rem; }
figcaption { max-width: 42rem; margin: .9rem auto 0; font-size: .92rem; line-height: 1.55; }
.image-heading.automatic { margin-top: .7rem; font-size: .82rem; font-weight: 500; opacity: .68; }
.chapter { position: relative; margin: clamp(6rem, 14vw, 13rem) auto clamp(3rem, 7vw, 7rem); padding-top: 1.6rem; border-top: 1px solid currentColor; }
.chapter h2 { max-width: 17ch; margin: .2rem 0 1.4rem; font-size: clamp(2.5rem, 6vw, 5.8rem); line-height: .97; letter-spacing: -.05em; text-wrap: balance; }
.chapter-nav { display: flex; flex-wrap: wrap; gap: 1.2rem; font-size: .8rem; }
.narrative { margin: clamp(3rem, 8vw, 8rem) auto; }
.prose { max-width: 43rem; margin: 0 auto; font-family: Georgia, "Times New Roman", serif; font-size: clamp(1.08rem, 1.5vw, 1.28rem); line-height: 1.85; }
.prose p { margin: 0 0 1.25em; white-space: pre-wrap; }
.story-ending { display: flex; justify-content: center; padding: 5rem 1rem 7rem; font-size: .8rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase; }
.story-ending a { text-decoration: none; }
@media (max-width: 700px) {
  .site-nav { gap: 1rem; min-height: 3.3rem; }
  .contents { margin-left: auto; }
  .cover { min-height: 0; }
  .cover-copy { width: min(100% - 2rem, 42rem); padding: 4.2rem 0 2.4rem; }
  .story-flow { width: min(100% - 2rem, 42rem); }
  .hero-image { width: 100%; margin-bottom: 2rem; }
  .hero-image img, .wide-image img { max-height: 68vh; object-fit: contain; }
  .image-pair { grid-template-columns: 1fr; gap: 2.4rem; }
  .paired-image img { max-height: 74vh; }
  .image-feature, .narrative { margin: 3.5rem auto; }
  .image-feature.layout-one-per-section .image-story-item { grid-template-columns: minmax(0, 1fr); gap: 1rem; }
  .image-feature.layout-one-per-section .image-description { width: min(100%, 43rem); margin: 0 auto; }
  .chapter { margin: 5rem auto 3.5rem; }
}
@media (prefers-reduced-motion: reduce) { html { scroll-behavior: auto; } *, *::before, *::after { animation-duration: .01ms !important; transition-duration: .01ms !important; } }
'''
    if style == "cinematic":
        return r'''
'''+common+r'''
body { background: #101114; color: #f4f0e9; }
.site-nav { color: #f7f5f2; background: #101114df; border-bottom: 1px solid #ffffff20; }
.cover { min-height: calc(100svh - 3.7rem); background: #08090b; align-content: end; }
.cover.has-hero { min-height: calc(100svh - 3.7rem); grid-template-rows: 1fr auto; }
.cover-copy { grid-row: 1; grid-column: 1; align-self: end; width: min(100% - 3rem, 88rem); padding: clamp(4rem, 13vh, 11rem) 0 3.5rem; }
.cover.has-hero .cover-copy { position: absolute; bottom: 2rem; left: 50%; width: min(100% - 3rem, 88rem); transform: translateX(-50%); }
.cover.has-hero::after { content: ""; position: absolute; inset: 0; z-index: 1; background: linear-gradient(90deg, #08090bdd 0%, #08090b68 52%, transparent 100%), linear-gradient(0deg, #08090bcb, transparent 66%); pointer-events: none; }
.cover.has-hero .hero-image { grid-row: 1; grid-column: 1; width: 100%; height: 100%; margin: 0; }
.cover.has-hero .hero-image img { width: 100%; height: auto; max-height: calc(100svh - 3.7rem); object-fit: contain; }
.masthead, .chapter-kicker { color: #c6a979; }
.introduction { color: #d2d0cb; }
.story-flow { width: min(100% - 3rem, 92rem); }
.image-feature { margin: clamp(4rem, 10vw, 10rem) 0; }
.image-feature.layout-one-per-section .image-description { border-left: 1px solid #c6a97978; padding-left: clamp(1.2rem, 3vw, 3rem); }
.photograph img { background: #08090b; }
figcaption { color: #c4c0b9; }
.chapter { border-color: #c6a97978; }
.chapter h2 { font-family: Georgia, "Times New Roman", serif; font-weight: 400; }
.narrative { max-width: 56rem; }
.prose { color: #e4e0d9; }
.image-pair { gap: clamp(1.5rem, 5vw, 6rem); }
.image-pair.layout-two-per-section .paired-image:nth-child(2) { margin-top: 3.5rem; }
.story-ending { color: #c6a979; }
.contents ol { background: #181a1e; border: 1px solid #ffffff26; }
.contents li a:hover { background: #ffffff12; }
@media (max-width: 700px) { .cover.has-hero { min-height: 80svh; } .cover.has-hero .cover-copy { bottom: 1rem; } .cover.has-hero .hero-image img { max-height: 80svh; } .cover.has-hero::after { background: linear-gradient(0deg, #08090bee 0%, #08090b60 72%, #08090b22); } }
'''
    if style == "journal":
        return common+r'''
body { background: #edf2f7; color: #152336; }
.site-nav { background: #edf2f7ed; border-bottom: 1px solid #15233624; }
.cover { width: min(100% - 3rem, 89rem); min-height: 0; grid-template-columns: minmax(0, .85fr) minmax(0, 1.15fr); align-items: center; margin: 4rem auto 6rem; }
.cover-copy { grid-column: 1; grid-row: 1; width: auto; padding: 3rem 2.5rem 3rem 0; }
.cover.has-hero .cover-copy { position: static; transform: none; }
.cover.has-hero::after { display: none; }
.cover.has-hero .hero-image { grid-column: 2; grid-row: 1; width: 100%; margin: 0; }
.cover.has-hero .hero-image img { width: 100%; max-height: 75vh; object-fit: contain; }
.masthead, .chapter-kicker { color: #2476b3; }
.story-title { font: 500 clamp(3rem, 7vw, 7.5rem)/.92 Georgia, "Times New Roman", serif; letter-spacing: -.06em; }
.introduction, .prose { font-family: Georgia, "Times New Roman", serif; }
.story-flow { width: min(100% - 3rem, 76rem); }
.image-pair { align-items: start; gap: clamp(1.5rem, 5vw, 5rem); }
.paired-image:nth-child(2) { margin-top: 5rem; }
.image-feature { width: min(100%, 70rem); margin-left: auto; }
.image-feature.layout-one-per-section .image-story-item { gap: clamp(2rem, 5vw, 5rem); }
.image-feature.layout-one-per-section .photograph img { outline-offset: .65rem; }
.image-feature.layout-one-per-section .image-description { padding: 1rem 0; }
.image-feature:nth-of-type(even) { margin-left: 0; margin-right: auto; }
.photograph img { outline: none; outline-offset: 0; }
.image-heading {
    color: #2476b3;
    font: 600 clamp(.94rem, 1.2vw, 1.1rem)/1.35 system-ui, sans-serif;
    letter-spacing: .03em;
    margin: 0 0 .85rem;
}
figcaption { font-family: Georgia, "Times New Roman", serif; color: #596979; font-style: italic; }
.chapter { border-top: 0; padding-top: 0; }
.chapter::before { content: ""; display: block; width: 4rem; border-top: 2px solid #2476b3; margin-bottom: 1.3rem; }
.chapter h2 { font: 500 clamp(2.5rem, 6vw, 5.5rem)/1 Georgia, "Times New Roman", serif; letter-spacing: -.045em; }
.prose { max-width: 40rem; font-size: clamp(1.13rem, 1.5vw, 1.35rem); }
.story-ending { border-top: 1px solid #15233624; }
.contents ol { color: #152336; background: #ffffff; border: 1px solid #1523362b; }
@media (max-width: 700px) { .cover { display: flex; flex-direction: column; align-items: stretch; width: min(100% - 2rem, 42rem); margin: 1rem auto 3.5rem; } .cover-copy { padding: 3.2rem 0 2rem; } .cover.has-hero .hero-image { width: 100%; } .paired-image:nth-child(2) { margin-top: 0; } .image-feature, .image-feature:nth-of-type(even) { margin: 3.5rem auto; } }
'''
    return common+r'''
body { background: #f8f8f6; color: #17232d; }
.site-nav { background: #f8f8f6ed; border-bottom: 1px solid #17314624; }
.cover { min-height: min(88vh, 820px); grid-template-columns: minmax(0, .8fr) minmax(0, 1.2fr); align-items: center; background: #e9eef0; }
.cover-copy { grid-column: 1; grid-row: 1; width: auto; margin-left: max(1.5rem, calc((100vw - 82rem) / 2)); padding: 5rem 2rem 5rem 0; }
.cover.has-hero .cover-copy { position: static; transform: none; }
.cover.has-hero::after { display: none; }
.cover.has-hero .hero-image { grid-column: 2; grid-row: 1; width: 100%; margin: 0; }
.cover.has-hero .hero-image img { width: 100%; max-height: min(88vh, 820px); object-fit: contain; }
.masthead, .chapter-kicker { color: #39718e; }
.story-title { font-family: Georgia, "Times New Roman", serif; font-weight: 500; }
.introduction { color: #52616c; }
.story-flow { width: min(100% - 3rem, 88rem); }
.image-feature { width: min(100%, 76rem); margin: clamp(4rem, 8vw, 8rem) auto; }
.image-feature.layout-one-per-section .image-story-item { gap: clamp(2rem, 5vw, 5rem); }
.image-feature.layout-one-per-section .image-description { max-width: 43rem; padding: clamp(1rem, 2vw, 2rem) 0; }
.image-feature:nth-of-type(odd) { margin-left: 0; }
.image-feature:nth-of-type(even) { margin-right: 0; }
.image-pair { width: min(100%, 72rem); margin-inline: auto; }
.paired-image:nth-child(2) { margin-top: 4rem; }
.chapter { border-top: 0; margin-top: 10rem; }
.chapter-kicker { letter-spacing: .25em; }
.chapter h2 { font-family: Georgia, "Times New Roman", serif; font-weight: 500; }
.narrative { max-width: 64rem; padding: clamp(1.5rem, 4vw, 3.5rem); background: #e9eef0; }
.prose { margin-left: clamp(0rem, 8vw, 8rem); }
.contents ol { color: #17232d; background: #fff; border: 1px solid #17232d20; }
@media (max-width: 700px) { .cover { display: flex; flex-direction: column; align-items: stretch; min-height: 0; } .cover-copy { width: min(100% - 2rem, 42rem); margin: auto; padding: 4rem 0 2rem; } .cover.has-hero .hero-image { width: 100%; } .image-feature:nth-of-type(odd), .image-feature:nth-of-type(even) { margin: 3.5rem auto; } .paired-image:nth-child(2) { margin-top: 0; } .narrative { width: 100%; padding: 1.2rem; } .prose { margin: 0; } }
'''


def make_document(title, introduction, elements, *, style, hide_filenames,
                  publication_type="photo-essay", source_identities=None,
                  show_captions=False, layout="adaptive", output_format="folder",
                  website_structure="single-page", collections=()):
    source_identities = source_identities or {}
    image_number = 0
    converted = []
    for element in elements:
        kind = element.kind
        source = element.source if kind == "image" else ""
        output = ""
        stamp = None
        if kind == "image":
            image_number += 1
            output = f"images/{image_number:04d}.jpg"
            stamp = source_identities.get(source)
        converted.append(StoryElement(
            kind=kind, id=str(element.id), heading=element.heading or "",
            caption=element.caption or "", text=element.text or "",
            output_image=output, source=source, source_identity=tuple(stamp) if stamp else None,
            description=getattr(element, "description", "") or "",
        ))
    doc = StoryDocument(title or "", introduction or "", publication_type,
                        style, bool(hide_filenames), tuple(converted),
                        bool(show_captions), layout, output_format,
                        website_structure, tuple(collections))
    validate_document(doc)
    return doc


def prepare_publication(document: StoryDocument, workspace: str, *,
                        cancelled=lambda: False, progress=lambda *_: None) -> PreparedPublication:
    """Decode and encode bounded derivatives via KIMng's protected reader.

    The caller supplies a private directory. Every source must have an approved
    identity. Re-encoding to JPEG ensures source EXIF/XMP/GPS blocks are not
    copied into the website.
    """
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QImage, QPainter
    from kim_photo_selection import read_thumbnail
    from kim_preview import identity

    validate_document(document)
    root = Path(workspace)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if root.is_symlink() or root.stat().st_uid != os.getuid():
        raise ValueError("Private publication workspace is not owned by this user")
    os.chmod(root, 0o700)
    image_root = root / "images"
    image_root.mkdir(mode=0o700, exist_ok=True)
    if image_root.is_symlink() or image_root.stat().st_uid != os.getuid():
        raise ValueError("Private image workspace is unsafe")
    prepared = []
    blocked = []
    rendered_dimensions = {}
    warnings = []
    image_elements = [element for element in document.elements if element.kind == "image"]
    for image_index, element in enumerate(image_elements, 1):
        if cancelled():
            raise InterruptedError("Website preparation was cancelled")
        progress(image_index - 1, len(image_elements), Path(element.source).name)
        try:
            if element.source_identity is None:
                raise ValueError("Source identity was not approved")
            if tuple(identity(element.source)) != element.source_identity:
                raise ValueError("Source changed after selection or review")
            image, read_identity = read_thumbnail(
                element.source, QSize(*DERIVATIVE_MAX_SIZE), allow_upscale=False)
            if image.isNull() or tuple(read_identity) != element.source_identity:
                raise ValueError("Image preview is unavailable or changed")
            rgb = QImage(image.size(), QImage.Format_RGB32)
            rgb.fill(Qt.white)
            painter = QPainter(rgb)
            painter.drawImage(0, 0, image)
            painter.end()
            output = root / element.output_image
            output.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            from PySide6.QtCore import QIODevice, QSaveFile
            safe_output = QSaveFile(str(output))
            safe_output.setDirectWriteFallback(False)
            if not safe_output.open(QIODevice.WriteOnly):
                raise ValueError("Could not create a safe JPEG derivative")
            if not rgb.save(safe_output, "JPEG", DERIVATIVE_QUALITY) or not safe_output.commit():
                safe_output.cancelWriting()
                raise ValueError("Could not create a safe JPEG derivative")
            os.chmod(output, 0o600)
            _verify_private_jpeg(output)
            if tuple(identity(element.source)) != element.source_identity:
                raise ValueError("Source changed while preparing")
            digest = hashlib.sha256(output.read_bytes()).hexdigest()
            prepared.append(PreparedImage(
                element.id, element.source, element.source_identity, element.output_image,
                rgb.width(), rgb.height(), output.stat().st_size, digest, str(output),
            ))
            rendered_dimensions[element.id] = replace(
                element, image_width=rgb.width(), image_height=rgb.height())
        except InterruptedError:
            raise
        except Exception as exc:
            reason = str(exc)
            blocked.append(BlockedImage(element.id, element.source, reason))
            warnings.append(f"{Path(element.source).name}: {reason}")
            rendered_dimensions[element.id] = replace(
                element, output_image="", blocked_reason=reason)
        progress(image_index, len(image_elements), Path(element.source).name)
    document = replace(
        document,
        elements=tuple(rendered_dimensions.get(element.id, element)
                       for element in document.elements),
    )
    rendered = render_website(document)
    _write_private(root / "index.html", rendered.html.encode("utf-8"))
    for page_name, page_html in rendered.pages:
        _write_private(root / page_name, page_html.encode("utf-8"))
    _write_private(root / "style.css", rendered.css.encode("utf-8"))
    _write_private(root / "gallery-viewer.css", rendered.viewer_css.encode("utf-8"))
    _write_private(root / "gallery-viewer.js", rendered.viewer_js.encode("utf-8"))
    return PreparedPublication(document, str(root), tuple(prepared), rendered.html,
                               rendered.css, rendered.viewer_css, rendered.viewer_js,
                               tuple(blocked), tuple(warnings), rendered.pages)


def _write_private(path: Path, payload: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(payload)
        stream.flush()


def _verify_private_jpeg(path: Path) -> None:
    """Reject EXIF/XMP/IPTC application segments in freshly encoded JPEGs."""
    data = path.read_bytes()
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise ValueError("JPEG derivative has an invalid signature")
    offset = 2
    while offset + 4 <= len(data):
        if data[offset] != 0xFF:
            raise ValueError("JPEG derivative has an invalid marker sequence")
        marker = data[offset + 1]
        offset += 2
        if marker in (0xD9, 0xDA):
            break
        if marker in (0x01, *range(0xD0, 0xD8)):
            continue
        if offset + 2 > len(data):
            raise ValueError("JPEG derivative has a truncated marker")
        length = int.from_bytes(data[offset:offset + 2], "big")
        if length < 2 or offset + length > len(data):
            raise ValueError("JPEG derivative has a truncated segment")
        payload = data[offset + 2:offset + length]
        if 0xE1 <= marker <= 0xEF or marker == 0xFE:
            raise ValueError("JPEG derivative unexpectedly contains source metadata")
        offset += length


def validate_prepared(prepared: PreparedPublication, *, cancelled=lambda: False) -> None:
    validate_document(prepared.document)
    if tuple(name for name, _ in prepared.pages) != output_pages(prepared.document)[1:]:
        raise ValueError("Prepared pages do not match the reviewed website structure")
    rendered = render_website(prepared.document)
    if (rendered.html != prepared.index_html or rendered.pages != prepared.pages
            or rendered.css != prepared.style_css or rendered.viewer_css != prepared.viewer_css
            or rendered.viewer_js != prepared.viewer_js):
        raise ValueError("Prepared website changed after Review Changes")
    if prepared.blocked:
        names = ", ".join(Path(image.source).name for image in prepared.blocked)
        raise ValueError("Publication is blocked by unavailable images: " + names)
    from kim_preview import identity
    for image in prepared.images:
        if cancelled():
            raise InterruptedError("Website publication was cancelled")
        if tuple(identity(image.source)) != image.source_identity:
            raise ValueError(f"Source changed after Review Changes: {Path(image.source).name}")
        path = Path(image.staged_path)
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"Prepared image is missing: {Path(image.source).name}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != image.sha256:
            raise ValueError(f"Prepared image changed after Review Changes: {Path(image.source).name}")


def publish_prepared(prepared: PreparedPublication, destination: str, *,
                     cancelled=lambda: False, progress=lambda *_: None,
                     approved_parent_identity=None) -> str:
    """Publish a complete site atomically with Linux no-replace directory rename."""
    import ctypes
    import errno
    import stat
    from kim_preview import identity

    if prepared.document.output_format != "folder":
        raise ValueError("Approved output format is ZIP archive, not Gallery folder")
    validate_prepared(prepared, cancelled=cancelled)
    target = Path(destination)
    parent = target.parent.resolve(strict=True)
    if target.name in ("", ".", "..") or "/" in target.name:
        raise ValueError("Publication destination must be a named directory")
    if target.is_symlink() or os.path.lexists(target):
        raise FileExistsError(f"Publication destination already exists: {target}")
    parent_info = parent.stat()
    if not stat.S_ISDIR(parent_info.st_mode):
        raise ValueError("Publication parent is not a directory")
    actual_parent_identity = (parent_info.st_dev, parent_info.st_ino)
    if (approved_parent_identity is not None
            and tuple(approved_parent_identity) != actual_parent_identity):
        raise ValueError("Destination parent changed after Review Changes")
    pfd = _open_directory_chain(parent)
    stage_name = f".{target.name}.kimng-stage-{uuid.uuid4().hex}"
    stage_path = parent / stage_name
    published = False
    try:
        current_parent = os.fstat(pfd)
        if (current_parent.st_dev, current_parent.st_ino) != (parent_info.st_dev, parent_info.st_ino):
            raise ValueError("Publication parent changed after Review Changes")
        os.mkdir(stage_name, mode=0o700, dir_fd=pfd)
        root_fd = os.open(stage_name, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=pfd)
        try:
            os.mkdir("images", mode=0o700, dir_fd=root_fd)
            image_fd = os.open("images", os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0), dir_fd=root_fd)
            try:
                for image_number, image in enumerate(prepared.images, 1):
                    if cancelled():
                        raise InterruptedError("Website publication was cancelled")
                    if tuple(identity(image.source)) != image.source_identity:
                        raise ValueError(f"Source changed after Review Changes: {Path(image.source).name}")
                    leaf = Path(image.relative_path).name
                    source = Path(image.staged_path)
                    payload = source.read_bytes()
                    if hashlib.sha256(payload).hexdigest() != image.sha256:
                        raise ValueError(f"Prepared image changed after Review Changes: {leaf}")
                    fd = os.open(leaf, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=image_fd)
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                    progress(image_number, len(prepared.images) + 3 + len(output_pages(prepared.document)),
                             Path(image.source).name)
                for name, payload in (("style.css", prepared.style_css.encode("utf-8")),
                                      ("gallery-viewer.css", prepared.viewer_css.encode("utf-8")),
                                      ("gallery-viewer.js", prepared.viewer_js.encode("utf-8")),
                                      ("index.html", prepared.index_html.encode("utf-8")),
                                      *((name, page.encode("utf-8")) for name, page in prepared.pages)):
                    if cancelled():
                        raise InterruptedError("Website publication was cancelled")
                    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=root_fd)
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                progress(len(prepared.images) + 3 + len(output_pages(prepared.document)),
                         len(prepared.images) + 3 + len(output_pages(prepared.document)),
                         "Verifying gallery")
            finally:
                os.close(image_fd)
        finally:
            os.close(root_fd)
        if cancelled():
            raise InterruptedError("Website publication was cancelled")
        _verify_site(stage_path, prepared, cancelled=cancelled)
        validate_prepared(prepared, cancelled=cancelled)
        # Keep staging private while incomplete. Once complete, use portable
        # static-site permissions before the atomic publication rename.
        os.chmod(stage_path / "images", 0o755, follow_symlinks=False)
        for output_file in (stage_path / "index.html", stage_path / "style.css",
                            stage_path / "gallery-viewer.css", stage_path / "gallery-viewer.js",
                            *(stage_path / name for name, _ in prepared.pages),
                            *(stage_path / image.relative_path for image in prepared.images)):
            os.chmod(output_file, 0o644, follow_symlinks=False)
        os.chmod(stage_path, 0o755, follow_symlinks=False)
        if cancelled():
            raise InterruptedError("Website publication was cancelled")
        # RENAME_NOREPLACE is a single atomic create-only publication. If the
        # syscall is unavailable, fail closed instead of check-then-rename.
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise RuntimeError("Safe no-replace website publication is unavailable on this system")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        if renameat2(pfd, os.fsencode(stage_name), pfd, os.fsencode(target.name), 1) != 0:
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise FileExistsError(f"Publication destination appeared after review: {target}")
            raise OSError(error, os.strerror(error), str(target))
        published = True
        return str(target)
    finally:
        os.close(pfd)
        if not published and stage_path.exists() and not stage_path.is_symlink():
            shutil.rmtree(stage_path)


def publish_prepared_zip(prepared: PreparedPublication, destination: str, *,
                         gallery_name: str, cancelled=lambda: False,
                         progress=lambda *_: None,
                         approved_parent_identity=None) -> str:
    """Create a portable ZIP from reviewed derivatives and publish create-only.

    No original image is opened here. The archive contains the exact HTML, CSS,
    and freshly encoded images held by the approved PreparedPublication.
    """
    import ctypes
    import errno
    import stat
    from kim_preview import identity

    if prepared.document.output_format != "zip":
        raise ValueError("Approved output format is Gallery folder, not ZIP archive")
    validate_prepared(prepared, cancelled=cancelled)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", gallery_name):
        raise ValueError("ZIP gallery folder name is unsafe")
    target = Path(destination).absolute()
    parent = target.parent.resolve(strict=True)
    if (target.name in ("", ".", "..") or target.suffix.casefold() != ".zip"
            or target.is_symlink() or os.path.lexists(target)):
        raise FileExistsError(f"ZIP destination is unavailable: {target}")
    parent_info = parent.stat()
    if not stat.S_ISDIR(parent_info.st_mode):
        raise ValueError("ZIP destination parent is not a directory")
    actual_parent_identity = (parent_info.st_dev, parent_info.st_ino)
    if (approved_parent_identity is not None
            and tuple(approved_parent_identity) != actual_parent_identity):
        raise ValueError("Destination parent changed after Review Changes")

    pfd = _open_directory_chain(parent)
    stage_dir_name = f".{target.name}.kimng-stage-{uuid.uuid4().hex}"
    stage_dir_fd = None
    stage_file_fd = None
    stage_file_name = "gallery.zip"
    stage_created = False
    published = False
    try:
        current_parent = os.fstat(pfd)
        if (current_parent.st_dev, current_parent.st_ino) != actual_parent_identity:
            raise ValueError("Publication parent changed after Review Changes")
        os.mkdir(stage_dir_name, mode=0o700, dir_fd=pfd)
        stage_created = True
        stage_dir_fd = os.open(
            stage_dir_name,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=pfd,
        )
        stage_fd = os.fstat(stage_dir_fd)
        if (not stat.S_ISDIR(stage_fd.st_mode) or stage_fd.st_uid != os.getuid()
                or stage_fd.st_mode & 0o077):
            raise ValueError("ZIP staging directory is not private")
        stage_file_fd = os.open(
            stage_file_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600, dir_fd=stage_dir_fd,
        )
        payloads = [(f"{gallery_name}/index.html", prepared.index_html.encode("utf-8")),
                    (f"{gallery_name}/style.css", prepared.style_css.encode("utf-8")),
                    (f"{gallery_name}/gallery-viewer.css", prepared.viewer_css.encode("utf-8")),
                    (f"{gallery_name}/gallery-viewer.js", prepared.viewer_js.encode("utf-8"))]
        payloads.extend((f"{gallery_name}/{name}", page.encode("utf-8"))
                        for name, page in prepared.pages)
        for image in prepared.images:
            relative = PurePosixPath(image.relative_path)
            if (relative.is_absolute() or ".." in relative.parts
                    or len(relative.parts) != 2 or relative.parts[0] != "images"
                    or relative.as_posix() != image.relative_path):
                raise ValueError("Prepared image path is unsafe for ZIP output")
            payloads.append((f"{gallery_name}/{image.relative_path}", image))

        expected_digests = {}
        with os.fdopen(stage_file_fd, "w+b", closefd=True) as stream:
            stage_file_fd = None
            with zipfile.ZipFile(stream, mode="w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=6, strict_timestamps=True) as archive:
                for index, (name, payload_source) in enumerate(payloads, 1):
                    if cancelled():
                        raise InterruptedError("ZIP publication was cancelled")
                    path = PurePosixPath(name)
                    if (path.is_absolute() or ".." in path.parts
                            or path.as_posix() != name or "\\" in name):
                        raise ValueError("ZIP archive entry path is unsafe")
                    if isinstance(payload_source, PreparedImage):
                        image = payload_source
                        if tuple(identity(image.source)) != image.source_identity:
                            raise ValueError(
                                f"Source changed after Review Changes: {Path(image.source).name}")
                        source_path = Path(image.staged_path)
                        if not source_path.is_file() or source_path.is_symlink():
                            raise ValueError(f"Prepared image is missing: {Path(image.source).name}")
                        payload = source_path.read_bytes()
                        if hashlib.sha256(payload).hexdigest() != image.sha256:
                            raise ValueError(
                                f"Prepared image changed after Review Changes: {source_path.name}")
                    else:
                        payload = payload_source
                    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = (stat.S_IFREG | 0o644) << 16
                    archive.writestr(info, payload, compress_type=zipfile.ZIP_DEFLATED,
                                     compresslevel=6)
                    expected_digests[name] = hashlib.sha256(payload).hexdigest()
                    progress(index, len(payloads), PurePosixPath(name).name)
                archive.comment = b""
            stream.flush()
            os.fsync(stream.fileno())
        _verify_zip(stage_file_name, stage_dir_fd, expected_digests, cancelled=cancelled)
        validate_prepared(prepared, cancelled=cancelled)
        if cancelled():
            raise InterruptedError("ZIP publication was cancelled")
        os.chmod(stage_file_name, 0o644, dir_fd=stage_dir_fd, follow_symlinks=False)
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is None:
            raise RuntimeError("Safe no-replace ZIP publication is unavailable on this system")
        renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                              ctypes.c_char_p, ctypes.c_uint]
        renameat2.restype = ctypes.c_int
        if renameat2(stage_dir_fd, os.fsencode(stage_file_name),
                     pfd, os.fsencode(target.name), 1) != 0:
            error = ctypes.get_errno()
            if error == errno.EEXIST:
                raise FileExistsError(f"ZIP destination appeared after review: {target}")
            raise OSError(error, os.strerror(error), str(target))
        published = True
        return str(target)
    finally:
        if stage_file_fd is not None:
            os.close(stage_file_fd)
        if stage_dir_fd is not None:
            if not published:
                try:
                    os.unlink(stage_file_name, dir_fd=stage_dir_fd)
                except FileNotFoundError:
                    pass
            os.close(stage_dir_fd)
        if stage_created:
            try:
                os.rmdir(stage_dir_name, dir_fd=pfd)
            except FileNotFoundError:
                pass
        os.close(pfd)


def _verify_zip(stage_name: str, parent_fd: int, expected_digests: dict[str, str], *,
                cancelled=lambda: False) -> None:
    """Validate archive names, regular-file entries, CRCs, and every payload."""
    import stat
    import zipfile

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(stage_name, flags, dir_fd=parent_fd)
    try:
        with os.fdopen(fd, "rb", closefd=False) as stream:
            with zipfile.ZipFile(stream, "r") as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if len(names) != len(set(names)) or set(names) != set(expected_digests):
                    raise ValueError("ZIP archive entries do not match the reviewed gallery")
                if archive.testzip() is not None:
                    raise ValueError("ZIP archive integrity verification failed")
                roots = {PurePosixPath(name).parts[0] for name in names
                         if PurePosixPath(name).parts}
                if len(roots) != 1:
                    raise ValueError("ZIP entries do not share one gallery folder")
                gallery_root = next(iter(roots))
                relative_entries = {
                    PurePosixPath(name).relative_to(gallery_root).as_posix() for name in names
                }
                index_name = f"{gallery_root}/index.html"
                required = {"index.html", "style.css", "gallery-viewer.css", "gallery-viewer.js"}
                if not required.issubset(relative_entries):
                    raise ValueError("ZIP is missing a required gallery page or local asset")
                for page_name in sorted(name for name in relative_entries if name.endswith(".html")):
                    html_text = archive.read(f"{gallery_root}/{page_name}").decode("utf-8")
                    _verify_html_references(html_text, page_name, relative_entries,
                                            lambda name: archive.read(f"{gallery_root}/{name}").decode("utf-8"))
                for info in infos:
                    if cancelled():
                        raise InterruptedError("ZIP publication was cancelled")
                    entry = PurePosixPath(info.filename)
                    mode = (info.external_attr >> 16) & 0o170000
                    if (entry.is_absolute() or ".." in entry.parts
                            or entry.as_posix() != info.filename or "\\" in info.filename
                            or mode != stat.S_IFREG):
                        raise ValueError("ZIP archive contains an unsafe entry")
                    if hashlib.sha256(archive.read(info)).hexdigest() != expected_digests[info.filename]:
                        raise ValueError("ZIP archive payload failed integrity verification")
    finally:
        os.close(fd)


def _verify_site(root: Path, prepared: PreparedPublication, *, cancelled=lambda: False) -> None:
    required = (*output_pages(prepared.document), "style.css", "gallery-viewer.css", "gallery-viewer.js")
    if any(not (root / name).is_file() or (root / name).is_symlink() for name in required):
        raise ValueError("Generated website is incomplete")
    expected_text = {"index.html": prepared.index_html, "style.css": prepared.style_css,
                     "gallery-viewer.css": prepared.viewer_css,
                     "gallery-viewer.js": prepared.viewer_js, **dict(prepared.pages)}
    expected_files = set(expected_text) | {image.relative_path for image in prepared.images}
    actual_entries = {path.relative_to(root).as_posix(): path for path in root.rglob("*")}
    if (set(actual_entries) != expected_files | {"images"}
            or any(path.is_symlink() for path in actual_entries.values())
            or not actual_entries["images"].is_dir()):
        raise ValueError("Generated website files do not match the reviewed inventory")
    for name, content in expected_text.items():
        if cancelled():
            raise InterruptedError("Website publication was cancelled")
        if (root / name).read_bytes() != content.encode("utf-8"):
            raise ValueError("Generated website asset changed after Review Changes")
    page_text = {name: (root / name).read_text(encoding="utf-8")
                 for name in output_pages(prepared.document)}
    for image in prepared.images:
        if cancelled():
            raise InterruptedError("Website publication was cancelled")
        output = root / image.relative_path
        if not output.is_file() or output.is_symlink():
            raise ValueError("Generated website is missing an image derivative")
        if hashlib.sha256(output.read_bytes()).hexdigest() != image.sha256:
            raise ValueError("Generated image derivative failed integrity verification")
        if not any(image.relative_path in text for text in page_text.values()):
            raise ValueError("Generated website does not reference a planned image")
    inventory = set(required) | {image.relative_path for image in prepared.images}
    for name, text in page_text.items():
        _verify_html_references(text, name, inventory, page_text.__getitem__)


def _verify_html_references(text: str, page_name: str, inventory: set[str], read_page) -> None:
    for reference in re.findall(r'(?:href|src)="([^"]+)"', text):
        if reference.startswith(("file:", "http:", "https:", "/", "//")):
            raise ValueError("Website references a non-portable or remote resource")
        target, marker = (reference.split("#", 1) + [""])[:2] if "#" in reference else (reference, "")
        if not target:
            target = page_name
        path = PurePosixPath(target)
        if (path.is_absolute() or ".." in path.parts or "\\" in target
                or path.as_posix() != target or target not in inventory):
            raise ValueError("Website references a missing or unsafe local asset")
        if marker and (not target.endswith(".html") or f'id="{marker}"' not in (text if target == page_name else read_page(target))):
            raise ValueError("Website contains a broken navigation link")


def _open_directory_chain(path: Path) -> int:
    """Open every component without following symlinks; return the pinned fd."""
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            next_fd = os.open(component, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        os.close(fd)
        raise
