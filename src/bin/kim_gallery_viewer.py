"""Local, optional image viewer shared by generated KIMng galleries.

The assets enhance ordinary links to the generated JPEG derivatives. Without
JavaScript, each link still opens its image directly in the browser.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class GalleryViewerAssets:
    stylesheet: str
    script: str


_STYLESHEET = r"""
.photograph .gallery-viewer-trigger { display: block; cursor: zoom-in; }
.gallery-viewer[hidden] { display: none; }
.gallery-viewer {
    position: fixed;
    inset: 0;
    z-index: 1000;
    width: 100%;
    max-width: none;
    height: 100%;
    max-height: none;
    margin: 0;
    padding: 0;
    border: 0;
    background: #080a0deF;
    color: #f5f4f1;
}
.gallery-viewer::backdrop { background: #080a0deF; }
.gallery-viewer__layout {
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
    width: 100%;
    height: 100%;
    padding: clamp(.5rem, 2vw, 1.25rem);
    gap: .75rem;
}
.gallery-viewer__toolbar {
    display: flex;
    align-items: center;
    justify-content: center;
    flex-wrap: wrap;
    gap: .5rem;
}
.gallery-viewer__toolbar button {
    min-width: 44px;
    min-height: 44px;
    padding: .45rem .8rem;
    border: 1px solid #ffffff65;
    border-radius: 999px;
    background: #20252dcc;
    color: inherit;
    font: 600 .94rem/1.2 system-ui, sans-serif;
    cursor: pointer;
}
.gallery-viewer__toolbar button:hover:not(:disabled) { background: #3b424bcc; }
.gallery-viewer__toolbar button:disabled { opacity: .48; cursor: default; }
.gallery-viewer__toolbar button:focus-visible,
.gallery-viewer__stage:focus-visible {
    outline: 3px solid #9ed8ff;
    outline-offset: 3px;
}
.gallery-viewer__stage {
    display: grid;
    place-items: center;
    min-width: 0;
    min-height: 0;
    overflow: auto;
    overscroll-behavior: contain;
}
.gallery-viewer__stage.is-zoomed { place-items: start; }
.gallery-viewer__image {
    display: block;
    width: auto;
    height: auto;
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    object-fit: contain;
    transition: width .15s ease-out, height .15s ease-out;
}
.gallery-viewer__stage.is-zoomed .gallery-viewer__image {
    max-width: none;
    max-height: none;
    margin: auto;
}
.gallery-viewer__caption,
.gallery-viewer__status {
    min-height: 1.5em;
    margin: 0;
    color: #e4e5e8;
    text-align: center;
    font: 500 .92rem/1.4 system-ui, sans-serif;
}
@media (max-width: 600px) {
    .gallery-viewer__layout { padding: .4rem; gap: .4rem; }
    .gallery-viewer__toolbar { gap: .35rem; }
    .gallery-viewer__toolbar button { padding-inline: .62rem; }
}
@media (prefers-reduced-motion: reduce) {
    .gallery-viewer__image { transition: none; }
}
"""


_SCRIPT = r"""(() => {
  "use strict";
  const dialog = document.getElementById("gallery-viewer");
  if (!dialog || typeof dialog.showModal !== "function") return;

  const triggers = Array.from(document.querySelectorAll(".gallery-viewer-trigger"));
  if (!triggers.length) return;
  const image = dialog.querySelector(".gallery-viewer__image");
  const stage = dialog.querySelector(".gallery-viewer__stage");
  const caption = dialog.querySelector(".gallery-viewer__caption");
  const status = dialog.querySelector(".gallery-viewer__status");
  const previous = dialog.querySelector('[data-viewer-action="previous"]');
  const next = dialog.querySelector('[data-viewer-action="next"]');
  let current = -1;
  let zoom = 1;
  let fitWidth = 0;
  let fitHeight = 0;
  let returnFocus = null;
  let returnScroll = [0, 0];

  function measureFit() {
    if (!image.naturalWidth || !image.naturalHeight) return;
    const wasZoomed = stage.classList.contains("is-zoomed");
    if (wasZoomed) stage.classList.remove("is-zoomed");
    const availableWidth = stage.clientWidth;
    const availableHeight = stage.clientHeight;
    if (wasZoomed) stage.classList.add("is-zoomed");
    if (!availableWidth || !availableHeight) return;
    const scale = Math.min(
      availableWidth / image.naturalWidth,
      availableHeight / image.naturalHeight,
    );
    fitWidth = image.naturalWidth * scale;
    fitHeight = image.naturalHeight * scale;
  }

  function sizeImage() {
    if (!fitWidth || !fitHeight) return;
    image.style.width = `${fitWidth * zoom}px`;
    image.style.height = `${fitHeight * zoom}px`;
  }

  function paint() {
    const link = triggers[current];
    const source = link.getAttribute("href");
    const sourceImage = link.querySelector("img");
    const alt = sourceImage ? sourceImage.getAttribute("alt") || "Photograph" : "Photograph";
    fitWidth = 0;
    fitHeight = 0;
    image.src = source;
    image.alt = alt;
    caption.textContent = link.getAttribute("data-viewer-caption") || "";
    status.textContent = `Image ${current + 1} of ${triggers.length}`;
    previous.disabled = current === 0;
    next.disabled = current === triggers.length - 1;
    setZoom(1);
  }

  function setZoom(value) {
    zoom = Math.min(3, Math.max(1, value));
    image.style.setProperty("--gallery-viewer-zoom", String(zoom));
    if (zoom === 1 || !fitWidth || !fitHeight) measureFit();
    stage.classList.toggle("is-zoomed", zoom > 1);
    sizeImage();
    stage.scrollTop = 0;
    stage.scrollLeft = 0;
  }

  image.addEventListener("load", () => {
    measureFit();
    sizeImage();
  });
  window.addEventListener("resize", () => {
    measureFit();
    sizeImage();
  });

  function open(index, trigger) {
    current = index;
    returnFocus = trigger;
    returnScroll = [window.scrollX, window.scrollY];
    paint();
    dialog.showModal();
    measureFit();
    sizeImage();
    dialog.querySelector('[data-viewer-action="close"]').focus({ preventScroll: true });
  }

  function close() {
    if (dialog.open) dialog.close();
  }

  function move(delta) {
    const destination = current + delta;
    if (destination < 0 || destination >= triggers.length) return;
    current = destination;
    paint();
    stage.focus({ preventScroll: true });
  }

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest && event.target.closest(".gallery-viewer-trigger");
    if (trigger) {
      event.preventDefault();
      open(triggers.indexOf(trigger), trigger);
      return;
    }
    const action = event.target.closest && event.target.closest("[data-viewer-action]");
    if (!action || !dialog.open) return;
    switch (action.dataset.viewerAction) {
      case "close": close(); break;
      case "previous": move(-1); break;
      case "next": move(1); break;
      case "zoom-in": setZoom(zoom + .5); break;
      case "zoom-out": setZoom(zoom - .5); break;
      case "fit": setZoom(1); break;
    }
  });

  document.addEventListener("keydown", (event) => {
    if (!dialog.open) return;
    if (event.key === "Escape") { event.preventDefault(); close(); }
    if (event.key === "ArrowLeft") { event.preventDefault(); move(-1); }
    if (event.key === "ArrowRight") { event.preventDefault(); move(1); }
    if (event.key === "+" || event.key === "=") { event.preventDefault(); setZoom(zoom + .5); }
    if (event.key === "-") { event.preventDefault(); setZoom(zoom - .5); }
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) close();
  });
  dialog.addEventListener("close", () => {
    image.removeAttribute("src");
    if (returnFocus && returnFocus.isConnected) returnFocus.focus({ preventScroll: true });
    requestAnimationFrame(() => window.scrollTo(returnScroll[0], returnScroll[1]));
  });
})();
"""


def gallery_viewer_assets() -> GalleryViewerAssets:
    """Return the shared, offline viewer assets written into each gallery."""
    return GalleryViewerAssets(stylesheet=_STYLESHEET, script=_SCRIPT)
