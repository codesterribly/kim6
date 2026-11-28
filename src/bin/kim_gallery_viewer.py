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
    background: #090b0ff5;
    color: #f5f4f1;
    overflow: hidden;
}
.gallery-viewer::backdrop { background: #090b0ff5; }
.gallery-viewer__layout {
    position: relative;
    display: grid;
    grid-template-rows: auto minmax(0, 1fr) auto;
    width: 100%;
    height: 100%;
    padding: clamp(.4rem, 1.4vw, .85rem);
    gap: .45rem;
    box-sizing: border-box;
}
.gallery-viewer__topbar {
    display: grid;
    grid-template-columns: 1fr auto 1fr;
    align-items: center;
    gap: .5rem;
    z-index: 4;
    pointer-events: none;
}
.gallery-viewer__topbar > * { pointer-events: auto; }
.gallery-viewer__status {
    justify-self: start;
    margin: 0;
    padding: .42rem .78rem;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, .2);
    background: rgba(15, 18, 24, .76);
    color: #f0f2f5;
    font: 600 .88rem/1.25 system-ui, sans-serif;
    letter-spacing: .01em;
    backdrop-filter: blur(8px);
    box-shadow: 0 2px 10px rgba(0, 0, 0, .38);
    white-space: nowrap;
}
.gallery-viewer__toolbar {
    justify-self: center;
    display: inline-flex;
    align-items: center;
    gap: .28rem;
    padding: .22rem;
    border-radius: 999px;
    border: 1px solid rgba(255, 255, 255, .2);
    background: rgba(15, 18, 24, .76);
    backdrop-filter: blur(8px);
    box-shadow: 0 2px 10px rgba(0, 0, 0, .38);
}
.gallery-viewer__close { justify-self: end; }
.gallery-viewer__btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: .3rem;
    min-width: 44px;
    min-height: 44px;
    padding: .4rem .72rem;
    border: 1px solid rgba(255, 255, 255, .26);
    border-radius: 999px;
    background: rgba(18, 22, 30, .78);
    color: #f5f4f1;
    font: 600 .9rem/1.2 system-ui, sans-serif;
    cursor: pointer;
    backdrop-filter: blur(8px);
    box-shadow: 0 2px 12px rgba(0, 0, 0, .42);
    transition: background-color .14s ease, border-color .14s ease, opacity .14s ease;
}
.gallery-viewer__toolbar .gallery-viewer__btn {
    border-color: transparent;
    background: transparent;
    box-shadow: none;
    backdrop-filter: none;
}
.gallery-viewer__btn svg {
    width: 1.2rem;
    height: 1.2rem;
    flex: 0 0 auto;
    pointer-events: none;
}
.gallery-viewer__btn:hover:not(:disabled) {
    background: rgba(255, 255, 255, .18);
    border-color: rgba(255, 255, 255, .42);
}
.gallery-viewer__btn[aria-pressed="true"] {
    background: rgba(255, 255, 255, .14);
}
.gallery-viewer__btn:disabled { opacity: .34; cursor: default; }
.gallery-viewer__btn:focus-visible,
.gallery-viewer__stage:focus-visible {
    outline: 3px solid #9ed8ff;
    outline-offset: 2px;
}
.gallery-viewer__stage-wrap {
    position: relative;
    min-width: 0;
    min-height: 0;
    width: 100%;
    height: 100%;
    display: flex;
}
.gallery-viewer__stage {
    position: relative;
    display: grid;
    place-items: center;
    flex: 1 1 auto;
    min-width: 0;
    min-height: 0;
    overflow: auto;
    overscroll-behavior: contain;
    touch-action: pan-y;
}
.gallery-viewer__stage.is-zoomed {
    place-items: start;
    cursor: grab;
    touch-action: none;
}
.gallery-viewer__stage.is-dragging {
    cursor: grabbing;
    user-select: none;
    -webkit-user-select: none;
}
.gallery-viewer__nav {
    position: absolute;
    top: 50%;
    transform: translateY(-50%);
    z-index: 3;
    width: 46px;
    height: 46px;
    padding: 0;
}
.gallery-viewer__nav--prev { left: clamp(.35rem, 1.4vw, 1rem); }
.gallery-viewer__nav--next { right: clamp(.35rem, 1.4vw, 1rem); }
.gallery-viewer__image[hidden],
.gallery-viewer__feedback[hidden] { display: none; }
.gallery-viewer__feedback {
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    z-index: 2;
    margin: 0;
    padding: .75rem 1rem;
    max-width: min(90%, 28rem);
    border-radius: .5rem;
    border: 1px solid rgba(255, 255, 255, .18);
    background: rgba(20, 24, 32, .9);
    color: #f5f4f1;
    font: 500 .95rem/1.5 system-ui, sans-serif;
    text-align: center;
    pointer-events: none;
}
.gallery-viewer__image {
    display: block;
    width: auto;
    height: auto;
    max-width: 100%;
    max-height: 100%;
    object-fit: contain;
    user-select: none;
    -webkit-user-select: none;
    -webkit-user-drag: none;
    transition: width .14s ease-out, height .14s ease-out;
}
.gallery-viewer__stage.is-wheeling .gallery-viewer__image,
.gallery-viewer__stage.is-dragging .gallery-viewer__image {
    transition: none;
}
.gallery-viewer__stage.is-zoomed .gallery-viewer__image {
    max-width: none;
    max-height: none;
    margin: auto;
}
.gallery-viewer__caption {
    margin: 0 auto;
    padding: .4rem .9rem;
    max-width: min(92%, 68ch);
    border-radius: .65rem;
    background: rgba(15, 18, 24, .74);
    border: 1px solid rgba(255, 255, 255, .14);
    color: #eceef2;
    text-align: center;
    font: 500 .92rem/1.45 system-ui, sans-serif;
    backdrop-filter: blur(8px);
}
.gallery-viewer__caption:empty {
    display: none;
    padding: 0;
    border: 0;
}
@media (max-width: 600px) {
    .gallery-viewer__layout { padding: .35rem; gap: .35rem; }
    .gallery-viewer__topbar { gap: .3rem; }
    .gallery-viewer__status { padding: .35rem .58rem; font-size: .82rem; }
    .gallery-viewer__toolbar { gap: .12rem; padding: .16rem; }
    .gallery-viewer__btn { min-width: 44px; min-height: 44px; padding: .32rem .54rem; font-size: .86rem; }
    .gallery-viewer__nav { width: 44px; height: 44px; }
}
@media (prefers-reduced-motion: reduce) {
    .gallery-viewer__image,
    .gallery-viewer__btn { transition: none; }
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
  const feedback = document.createElement("p");
  feedback.className = "gallery-viewer__feedback";
  feedback.setAttribute("role", "status");
  feedback.setAttribute("aria-live", "polite");
  feedback.hidden = true;
  stage.appendChild(feedback);

  function setFeedback(message) {
    feedback.textContent = message;
    feedback.hidden = !message;
    stage.setAttribute(
      "aria-busy", message === "Loading image..." ? "true" : "false"
    );
  }

  const previous = dialog.querySelector('[data-viewer-action="previous"]');
  const next = dialog.querySelector('[data-viewer-action="next"]');
  const zoomInBtn = dialog.querySelector('[data-viewer-action="zoom-in"]');
  const zoomOutBtn = dialog.querySelector('[data-viewer-action="zoom-out"]');
  const fitBtn = dialog.querySelector('[data-viewer-action="fit"]');
  const closeBtn = dialog.querySelector('[data-viewer-action="close"]');
  const MIN_ZOOM = 1;
  const MAX_ZOOM = 4;
  const ZOOM_STEP = 0.5;
  const SWIPE_MIN_X = 48;

  if (image) image.draggable = false;

  function triggerId(link, index) {
    const explicit = link.getAttribute("data-viewer-id");
    if (explicit) return explicit;
    const href = link.getAttribute("href") || "";
    const file = href.split("/").pop() || "";
    const stem = file.replace(/\.[^.]+$/, "").replace(/[^A-Za-z0-9_-]+/g, "-");
    return stem ? `image-${stem}` : `image-${index + 1}`;
  }

  const idToIndex = new Map();
  const indexToId = triggers.map((link, idx) => {
    const id = triggerId(link, idx);
    if (!idToIndex.has(id)) idToIndex.set(id, idx);
    return id;
  });

  let current = -1;
  let zoom = 1;
  let fitWidth = 0;
  let fitHeight = 0;
  let returnFocus = null;
  let returnScroll = [0, 0];
  let preViewerHash = "";
  let wheelTimer = 0;

  let dragActive = false;
  let dragPointerId = null;
  let dragMoved = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let dragScrollLeft = 0;
  let dragScrollTop = 0;

  let touchMode = "";
  let touchStartX = 0;
  let touchStartY = 0;
  let touchScrollLeft = 0;
  let touchScrollTop = 0;

  function safeHash() {
    return (typeof location !== "undefined" && location && typeof location.hash === "string")
      ? location.hash : "";
  }

  function baseUrlWithoutHash() {
    if (typeof location === "undefined" || !location) return "";
    return `${location.pathname || ""}${location.search || ""}`;
  }

  function updateFragment(id, mode) {
    if (typeof history === "undefined" || !history || typeof location === "undefined" || !location) return;
    const targetHash = id ? `#${id}` : preViewerHash;
    if (safeHash() === targetHash) return;
    const url = targetHash ? `${baseUrlWithoutHash()}${targetHash}` : baseUrlWithoutHash();
    try {
      if (mode === "push" && typeof history.pushState === "function") {
        history.pushState({ galleryViewerImage: id || null }, "", url);
      } else if (typeof history.replaceState === "function") {
        history.replaceState({ galleryViewerImage: id || null }, "", url);
      }
    } catch (_) {
      // Ignore history restrictions in synthetic environments.
    }
  }

  function restoreScrollInstant(x, y) {
    try {
      if (typeof window.scrollTo === "function") {
        if (window.scrollTo.length >= 2) {
          window.scrollTo(x, y);
        } else {
          window.scrollTo({ left: x, top: y, behavior: "instant" });
        }
      }
    } catch (_) {
      if (typeof window.scrollTo === "function") window.scrollTo(x, y);
    }
  }

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

  function updateZoomControls() {
    if (zoomOutBtn) zoomOutBtn.disabled = zoom <= MIN_ZOOM + 0.001;
    if (zoomInBtn) zoomInBtn.disabled = zoom >= MAX_ZOOM - 0.001;
    if (fitBtn) fitBtn.setAttribute("aria-pressed", zoom <= MIN_ZOOM + 0.001 ? "true" : "false");
  }

  function paint() {
    const link = triggers[current];
    const source = link.getAttribute("href");
    const sourceImage = link.querySelector("img");
    const alt = sourceImage ? sourceImage.getAttribute("alt") || "Photograph" : "Photograph";
    fitWidth = 0;
    fitHeight = 0;
    image.hidden = true;
    setFeedback("Loading image...");
    image.src = source;
    image.alt = alt;
    caption.textContent = link.getAttribute("data-viewer-caption") || "";
    status.textContent = `Image ${current + 1} of ${triggers.length}`;
    if (previous) previous.disabled = current === 0;
    if (next) next.disabled = current === triggers.length - 1;
    setZoom(1);
  }

  function setZoom(value, anchor) {
    const prevZoom = zoom;
    let nextZoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, Number(value) || 1));
    if (nextZoom < 1.02) nextZoom = 1;
    nextZoom = Math.round(nextZoom * 1000) / 1000;

    let ratioX = 0.5;
    let ratioY = 0.5;
    let pointerX = 0;
    let pointerY = 0;
    const hasAnchor = Boolean(
      anchor && typeof stage.getBoundingClientRect === "function"
      && typeof image.getBoundingClientRect === "function"
      && fitWidth && fitHeight
    );
    if (hasAnchor) {
      const sRect = stage.getBoundingClientRect();
      const iRect = image.getBoundingClientRect();
      pointerX = anchor.clientX - sRect.left;
      pointerY = anchor.clientY - sRect.top;
      if (iRect.width > 0 && iRect.height > 0) {
        ratioX = Math.min(1, Math.max(0, (anchor.clientX - iRect.left) / iRect.width));
        ratioY = Math.min(1, Math.max(0, (anchor.clientY - iRect.top) / iRect.height));
      }
    }

    zoom = nextZoom;
    image.style.setProperty("--gallery-viewer-zoom", String(zoom));
    if (zoom === 1 || !fitWidth || !fitHeight) measureFit();
    stage.classList.toggle("is-zoomed", zoom > 1);
    sizeImage();
    updateZoomControls();

    if (zoom <= 1) {
      stage.scrollTop = 0;
      stage.scrollLeft = 0;
    } else if (hasAnchor && nextZoom !== prevZoom) {
      const newW = fitWidth * zoom;
      const newH = fitHeight * zoom;
      const maxLeft = Math.max(0, stage.scrollWidth - stage.clientWidth);
      const maxTop = Math.max(0, stage.scrollHeight - stage.clientHeight);
      stage.scrollLeft = Math.min(maxLeft, Math.max(0, ratioX * newW - pointerX));
      stage.scrollTop = Math.min(maxTop, Math.max(0, ratioY * newH - pointerY));
    } else if (prevZoom <= 1) {
      stage.scrollTop = 0;
      stage.scrollLeft = 0;
    }
  }

  image.addEventListener("load", () => {
    image.hidden = false;
    setFeedback("");
    measureFit();
    sizeImage();
  });
  image.addEventListener("error", () => {
    image.hidden = true;
    fitWidth = 0;
    fitHeight = 0;
    setFeedback("Unable to load this image.");
  });
  window.addEventListener("resize", () => {
    measureFit();
    sizeImage();
  });

  function open(index, trigger, historyMode = "push") {
    if (index < 0 || index >= triggers.length) return;
    const wasOpen = dialog.open;
    if (!wasOpen) {
      returnFocus = trigger || triggers[index];
      returnScroll = [window.scrollX || 0, window.scrollY || 0];
      const existingHash = safeHash();
      preViewerHash = (existingHash && !idToIndex.has(existingHash.slice(1))) ? existingHash : "";
    }
    current = index;
    paint();
    if (!wasOpen) {
      dialog.showModal();
      measureFit();
      sizeImage();
      if (closeBtn) closeBtn.focus({ preventScroll: true });
    }
    if (historyMode !== "none") {
      updateFragment(indexToId[current], historyMode);
    }
  }

  function close(historyMode = "replace") {
    if (!dialog.open) return;
    dialog._kimCloseHistoryHandled = true;
    if (historyMode !== "none") {
      updateFragment("", historyMode);
    }
    dialog.close();
  }

  function move(delta, historyMode = "push") {
    const destination = current + delta;
    if (destination < 0 || destination >= triggers.length) return;
    current = destination;
    paint();
    if (historyMode !== "none") {
      updateFragment(indexToId[current], historyMode);
    }
    stage.focus({ preventScroll: true });
  }

  function syncFromFragment() {
    const raw = safeHash().replace(/^#/, "");
    if (raw && idToIndex.has(raw)) {
      const idx = idToIndex.get(raw);
      if (!dialog.open) {
        open(idx, triggers[idx], "none");
      } else if (idx !== current) {
        current = idx;
        paint();
      }
      return;
    }
    if (dialog.open) {
      close("none");
    }
  }

  stage.addEventListener("wheel", (event) => {
    if (!dialog.open || !fitWidth || !fitHeight) return;
    event.preventDefault();
    stage.classList.add("is-wheeling");
    if (wheelTimer) clearTimeout(wheelTimer);
    wheelTimer = setTimeout(() => stage.classList.remove("is-wheeling"), 120);
    const factor = event.deltaY < 0 ? 1.2 : (1 / 1.2);
    setZoom(zoom * factor, { clientX: event.clientX, clientY: event.clientY });
  }, { passive: false });

  stage.addEventListener("pointerdown", (event) => {
    if (!dialog.open || zoom <= 1) return;
    if (event.pointerType === "touch") return;
    if (typeof event.button === "number" && event.button !== 0) return;
    dragActive = true;
    dragMoved = false;
    dragPointerId = event.pointerId;
    dragStartX = event.clientX;
    dragStartY = event.clientY;
    dragScrollLeft = stage.scrollLeft;
    dragScrollTop = stage.scrollTop;
    stage.classList.add("is-dragging");
    if (typeof stage.setPointerCapture === "function" && dragPointerId != null) {
      try { stage.setPointerCapture(dragPointerId); } catch (_) {}
    }
  });

  stage.addEventListener("pointermove", (event) => {
    if (!dragActive) return;
    const dx = event.clientX - dragStartX;
    const dy = event.clientY - dragStartY;
    if (Math.abs(dx) > 3 || Math.abs(dy) > 3) dragMoved = true;
    stage.scrollLeft = dragScrollLeft - dx;
    stage.scrollTop = dragScrollTop - dy;
  });

  function endDrag() {
    if (!dragActive) return;
    dragActive = false;
    stage.classList.remove("is-dragging");
    if (typeof stage.releasePointerCapture === "function" && dragPointerId != null) {
      try { stage.releasePointerCapture(dragPointerId); } catch (_) {}
    }
    dragPointerId = null;
    if (dragMoved) {
      setTimeout(() => { dragMoved = false; }, 0);
    }
  }

  stage.addEventListener("pointerup", endDrag);
  stage.addEventListener("pointercancel", endDrag);

  stage.addEventListener("touchstart", (event) => {
    if (!dialog.open || !event.touches || event.touches.length !== 1) {
      touchMode = "";
      return;
    }
    const t = event.touches[0];
    touchStartX = t.clientX;
    touchStartY = t.clientY;
    touchScrollLeft = stage.scrollLeft;
    touchScrollTop = stage.scrollTop;
    touchMode = zoom > 1 ? "pan" : "swipe";
  }, { passive: true });

  stage.addEventListener("touchmove", (event) => {
    if (!dialog.open || !event.touches || event.touches.length !== 1) return;
    if (touchMode === "pan") {
      const t = event.touches[0];
      event.preventDefault();
      stage.scrollLeft = touchScrollLeft - (t.clientX - touchStartX);
      stage.scrollTop = touchScrollTop - (t.clientY - touchStartY);
    }
  }, { passive: false });

  stage.addEventListener("touchend", (event) => {
    if (!dialog.open || touchMode !== "swipe") {
      touchMode = "";
      return;
    }
    touchMode = "";
    const changed = event.changedTouches && event.changedTouches[0];
    if (!changed || zoom > 1) return;
    const dx = changed.clientX - touchStartX;
    const dy = changed.clientY - touchStartY;
    if (Math.abs(dx) >= SWIPE_MIN_X && Math.abs(dx) > Math.abs(dy) * 1.4) {
      move(dx < 0 ? 1 : -1);
    }
  }, { passive: true });

  document.addEventListener("click", (event) => {
    const action = event.target.closest && event.target.closest("[data-viewer-action]");
    if (action && dialog.open) {
      dragMoved = false;
      switch (action.dataset.viewerAction) {
        case "close": close("replace"); break;
        case "previous": move(-1); break;
        case "next": move(1); break;
        case "zoom-in": setZoom(zoom + ZOOM_STEP); break;
        case "zoom-out": setZoom(zoom - ZOOM_STEP); break;
        case "fit": setZoom(1); break;
      }
      return;
    }
    if (dragMoved) {
      dragMoved = false;
      return;
    }
    const trigger = event.target.closest && event.target.closest(".gallery-viewer-trigger");
    if (trigger) {
      event.preventDefault();
      open(triggers.indexOf(trigger), trigger, "push");
    }
  });

  document.addEventListener("keydown", (event) => {
    if (!dialog.open) return;
    if (event.key === "Escape") { event.preventDefault(); close("replace"); }
    if (event.key === "ArrowLeft") { event.preventDefault(); move(-1); }
    if (event.key === "ArrowRight") { event.preventDefault(); move(1); }
    if (event.key === "+" || event.key === "=") { event.preventDefault(); setZoom(zoom + ZOOM_STEP); }
    if (event.key === "-") { event.preventDefault(); setZoom(zoom - ZOOM_STEP); }
    if (event.key === "0") { event.preventDefault(); setZoom(1); }
  });

  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) close("replace");
  });
  dialog.addEventListener("close", () => {
    const handled = Boolean(dialog._kimCloseHistoryHandled);
    dialog._kimCloseHistoryHandled = false;
    endDrag();
    touchMode = "";
    image.removeAttribute("src");
    image.hidden = true;
    setFeedback("");
    if (!handled) {
      updateFragment("", "replace");
    }
    if (returnFocus && returnFocus.isConnected) returnFocus.focus({ preventScroll: true });
    requestAnimationFrame(() => restoreScrollInstant(returnScroll[0], returnScroll[1]));
  });

  window.addEventListener("popstate", syncFromFragment);
  window.addEventListener("hashchange", syncFromFragment);
  syncFromFragment();
})();
"""


def gallery_viewer_assets() -> GalleryViewerAssets:
    """Return the shared, offline viewer assets written into each gallery."""
    return GalleryViewerAssets(stylesheet=_STYLESHEET, script=_SCRIPT)
