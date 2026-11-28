"""Behavioral tests for the viewer script using a small DOM adapter in Node."""

import shutil
import subprocess
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/bin"))

from kim_gallery_viewer import gallery_viewer_assets  # noqa: E402


class GalleryViewerScriptTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "Node is required to exercise viewer events")
    def test_viewer_controls_preserve_order_focus_and_reader_position(self):
        script = gallery_viewer_assets().script
        harness = r'''const fs = require("fs");
const vm = require("vm");
const assert = require("assert");
class Element {
  constructor(name, action = "") {
    this.name = name; this.dataset = action ? {viewerAction: action} : {};
    this.handlers = {}; this.disabled = false; this.open = false;
    this.isConnected = true; this.scrollTop = 0; this.scrollLeft = 0;
    this.scrollWidth = 1000; this.scrollHeight = 700;
    this.textContent = ""; this.alt = ""; this.src = ""; this.styles = {};
    this.naturalWidth = 720; this.naturalHeight = 480;
    this.clientWidth = 1000; this.clientHeight = 700;
    this.classes = new Set();
    this.style = {
      width: "1000px", height: "666.67px",
      setProperty: (key, value) => this.styles[key] = value,
    };
    this.classList = {
      toggle: (key, active) => active ? this.classes.add(key) : this.classes.delete(key),
      contains: (key) => this.classes.has(key),
      add: (key) => this.classes.add(key),
      remove: (key) => this.classes.delete(key),
    };
  }
  addEventListener(name, callback) {
    this.handlers[name] = this.handlers[name] || [];
    this.handlers[name].push(callback);
  }
  emit(name, event = {}) {
    for (const cb of (this.handlers[name] || [])) cb(event);
  }
  getBoundingClientRect() {
    const w = parseFloat(this.style.width) || this.clientWidth;
    const h = parseFloat(this.style.height) || this.clientHeight;
    return {left: 0, top: 0, width: w, height: h, right: w, bottom: h};
  }
  setAttribute(name, value) {
    this.attributes = this.attributes || {};
    this.attributes[name] = value;
  }
  appendChild(child) {
    this.appended = this.appended || [];
    this.appended.push(child);
    return child;
  }
  focus() { document.activeElement = this; }
  querySelector(selector) { return this.children && this.children[selector]; }
  getAttribute(name) { return this.attributes && this.attributes[name] || ""; }
  removeAttribute(name) { if (name === "src") this.src = ""; }
  showModal() { this.open = true; }
  close() { this.open = false; this.emit("close"); }
  closest(selector) {
    if (selector === ".gallery-viewer-trigger" && this.trigger) return this;
    if (selector === "[data-viewer-action]" && this.dataset.viewerAction) return this;
    return null;
  }
}
const actions = {};
for (const name of ["close", "previous", "next", "zoom-in", "zoom-out", "fit"])
  actions[name] = new Element(name, name);
const image = new Element("viewer-image");
const stage = new Element("stage");
const caption = new Element("caption");
const status = new Element("status");
const dialog = new Element("dialog");
dialog.children = {
  ".gallery-viewer__image": image,
  ".gallery-viewer__stage": stage,
  ".gallery-viewer__caption": caption,
  ".gallery-viewer__status": status,
  '[data-viewer-action="previous"]': actions.previous,
  '[data-viewer-action="next"]': actions.next,
  '[data-viewer-action="close"]': actions.close,
  '[data-viewer-action="zoom-in"]': actions["zoom-in"],
  '[data-viewer-action="zoom-out"]': actions["zoom-out"],
  '[data-viewer-action="fit"]': actions.fit,
};
const triggers = [1, 2].map((number) => {
  const trigger = new Element(`trigger-${number}`);
  const thumb = new Element(`thumbnail-${number}`);
  thumb.attributes = {alt: `Frame ${number}`};
  trigger.trigger = true;
  trigger.attributes = {
    href: `images/000${number}.jpg`,
    "data-viewer-id": `image-000${number}`,
    "data-viewer-caption": `Caption ${number}`,
  };
  trigger.children = {img: thumb};
  return trigger;
});
const historyStack = [{url: "/gallery/index.html#chapter-1"}];
let historyIdx = 0;
global.location = {pathname: "/gallery/index.html", search: "", hash: "#chapter-1"};
global.history = {
  pushState(state, title, url) {
    historyStack.splice(historyIdx + 1);
    historyStack.push({state, url});
    historyIdx = historyStack.length - 1;
    const hashPos = url.indexOf("#");
    global.location.hash = hashPos >= 0 ? url.slice(hashPos) : "";
  },
  replaceState(state, title, url) {
    historyStack[historyIdx] = {state, url};
    const hashPos = url.indexOf("#");
    global.location.hash = hashPos >= 0 ? url.slice(hashPos) : "";
  },
  back() {
    if (historyIdx > 0) {
      historyIdx -= 1;
      const url = historyStack[historyIdx].url;
      const hashPos = url.indexOf("#");
      global.location.hash = hashPos >= 0 ? url.slice(hashPos) : "";
      window.emit("popstate");
    }
  },
  forward() {
    if (historyIdx < historyStack.length - 1) {
      historyIdx += 1;
      const url = historyStack[historyIdx].url;
      const hashPos = url.indexOf("#");
      global.location.hash = hashPos >= 0 ? url.slice(hashPos) : "";
      window.emit("popstate");
    }
  },
};
global.window = {
  scrollX: 3, scrollY: 420, handlers: {},
  scrollTo(x, y) {
    if (typeof x === "object" && x) { this.scrollX = x.left; this.scrollY = x.top; }
    else { this.scrollX = x; this.scrollY = y; }
  },
  addEventListener(name, callback) {
    this.handlers[name] = this.handlers[name] || [];
    this.handlers[name].push(callback);
  },
  emit(name, event = {}) {
    for (const cb of (this.handlers[name] || [])) cb(event);
  },
};
global.requestAnimationFrame = (callback) => callback();
global.document = {
  activeElement: null, handlers: {},
  createElement(tag) { return new Element(tag); },
  getElementById(id) { return id === "gallery-viewer" ? dialog : null; },
  querySelectorAll(selector) { return selector === ".gallery-viewer-trigger" ? triggers : []; },
  addEventListener(name, callback) {
    this.handlers[name] = this.handlers[name] || [];
    this.handlers[name].push(callback);
  },
  emit(name, event = {}) {
    for (const cb of (this.handlers[name] || [])) cb(event);
  },
};
function click(target) {
  let prevented = false;
  document.emit("click", {target, preventDefault() { prevented = true; }});
  return prevented;
}
function key(k) {
  let prevented = false;
  document.emit("keydown", {key: k, preventDefault() { prevented = true; }});
  return prevented;
}
vm.runInThisContext(fs.readFileSync(0, "utf8"));
// Section anchor #chapter-1 did not open viewer
assert.strictEqual(dialog.open, false);

// Open image 1
assert.strictEqual(click(triggers[0]), true);
assert.strictEqual(dialog.open, true);
assert.strictEqual(location.hash, "#image-0001");
const feedback = stage.appended[0];
assert.strictEqual(feedback.attributes.role, "status");
assert.strictEqual(feedback.textContent, "Loading image...");
assert.strictEqual(feedback.hidden, false);
assert.strictEqual(image.hidden, true);
image.emit("load");
assert.strictEqual(feedback.textContent, "");
assert.strictEqual(feedback.hidden, true);
assert.strictEqual(image.hidden, false);
assert.strictEqual(image.src, "images/0001.jpg");
assert.strictEqual(caption.textContent, "Caption 1");
assert.strictEqual(status.textContent, "Image 1 of 2");
assert.strictEqual(actions.previous.disabled, true);
assert.strictEqual(actions["zoom-out"].disabled, true);
assert.strictEqual(actions.fit.attributes["aria-pressed"], "true");

// Zoom in, wheel zoom, drag-to-pan, bounds, fit reset
click(actions["zoom-in"]);
assert.strictEqual(image.styles["--gallery-viewer-zoom"], "1.5");
assert.strictEqual(actions["zoom-out"].disabled, false);
assert.strictEqual(actions.fit.attributes["aria-pressed"], "false");
stage.scrollWidth = 2000; stage.scrollHeight = 1400;
let wheelPrevented = false;
stage.emit("wheel", {deltaY: -120, clientX: 800, clientY: 500, preventDefault() { wheelPrevented = true; }});
assert.strictEqual(wheelPrevented, true);
assert.ok(parseFloat(image.styles["--gallery-viewer-zoom"]) > 1.5);

// Drag-to-pan when zoomed does not navigate
const prevLeft = stage.scrollLeft;
stage.emit("pointerdown", {pointerType: "mouse", button: 0, pointerId: 1, clientX: 300, clientY: 300});
assert.strictEqual(stage.classList.contains("is-dragging"), true);
stage.emit("pointermove", {clientX: 220, clientY: 250});
assert.strictEqual(stage.scrollLeft, prevLeft + 80);
stage.emit("pointerup", {});
assert.strictEqual(stage.classList.contains("is-dragging"), false);
assert.strictEqual(status.textContent, "Image 1 of 2");

// Touch pan when zoomed must NOT trigger swipe navigation
stage.emit("touchstart", {touches: [{clientX: 300, clientY: 200}]});
let touchPrevented = false;
stage.emit("touchmove", {touches: [{clientX: 150, clientY: 200}], preventDefault() { touchPrevented = true; }});
assert.strictEqual(touchPrevented, true);
stage.emit("touchend", {changedTouches: [{clientX: 150, clientY: 200}]});
assert.strictEqual(status.textContent, "Image 1 of 2");

// Fit via '0' key resets zoom to 1
assert.strictEqual(key("0"), true);
assert.strictEqual(image.styles["--gallery-viewer-zoom"], "1");
assert.strictEqual(actions.fit.attributes["aria-pressed"], "true");

// Swipe left when unzoomed navigates to image 2
stage.emit("touchstart", {touches: [{clientX: 300, clientY: 200}]});
stage.emit("touchend", {changedTouches: [{clientX: 200, clientY: 205}]});
assert.strictEqual(image.src, "images/0002.jpg");
assert.strictEqual(location.hash, "#image-0002");
assert.strictEqual(feedback.textContent, "Loading image...");
image.emit("error");
assert.strictEqual(feedback.textContent, "Unable to load this image.");
assert.strictEqual(feedback.hidden, false);
assert.strictEqual(image.hidden, true);
assert.strictEqual(status.textContent, "Image 2 of 2");
assert.strictEqual(actions.next.disabled, true);
key("ArrowRight");
assert.strictEqual(status.textContent, "Image 2 of 2");

// Browser Back & Forward navigation
history.back();
assert.strictEqual(dialog.open, true);
assert.strictEqual(status.textContent, "Image 1 of 2");
assert.strictEqual(location.hash, "#image-0001");
history.forward();
assert.strictEqual(dialog.open, true);
assert.strictEqual(status.textContent, "Image 2 of 2");

// Previous button & Escape close restores pre-viewer section anchor, focus, and scroll
click(actions.previous);
assert.strictEqual(image.src, "images/0001.jpg");
image.emit("load");
assert.strictEqual(key("Escape"), true);
assert.strictEqual(dialog.open, false);
assert.strictEqual(location.hash, "#chapter-1");
assert.strictEqual(document.activeElement, triggers[0]);
assert.deepStrictEqual([window.scrollX, window.scrollY], [3, 420]);
assert.strictEqual(image.src, "");
assert.strictEqual(feedback.textContent, "");
assert.strictEqual(feedback.hidden, true);

// Invalid fragment does not open viewer
location.hash = "#image-9999";
window.emit("hashchange");
assert.strictEqual(dialog.open, false);

// Valid direct fragment opens image 2
location.hash = "#image-0002";
window.emit("hashchange");
assert.strictEqual(dialog.open, true);
assert.strictEqual(status.textContent, "Image 2 of 2");

console.log("viewer behavior verified");
'''
        result = subprocess.run(
            [shutil.which("node"), "-e", harness],
            input=script, text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        self.assertIn("viewer behavior verified", result.stdout)


if __name__ == "__main__":
    unittest.main()
