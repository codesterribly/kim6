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
    this.textContent = ""; this.alt = ""; this.src = ""; this.styles = {};
    this.naturalWidth = 720; this.naturalHeight = 480;
    this.clientWidth = 1000; this.clientHeight = 700;
    this.classes = new Set(); this.style = {setProperty: (key, value) => this.styles[key] = value};
    this.classList = {
      toggle: (key, active) => active ? this.classes.add(key) : this.classes.delete(key),
      contains: (key) => this.classes.has(key),
      add: (key) => this.classes.add(key),
      remove: (key) => this.classes.delete(key),
    };
  }
  addEventListener(name, callback) { this.handlers[name] = callback; }
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
  close() { this.open = false; this.handlers.close(); }
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
};
const triggers = [1, 2].map((number) => {
  const trigger = new Element(`trigger-${number}`);
  const thumb = new Element(`thumbnail-${number}`);
  thumb.attributes = {alt: `Frame ${number}`};
  trigger.trigger = true;
  trigger.attributes = {href: `images/${number}.jpg`, "data-viewer-caption": `Caption ${number}`};
  trigger.children = {img: thumb};
  return trigger;
});
global.window = {scrollX: 3, scrollY: 420, handlers: {},
  scrollTo(x, y) { this.scrollX = x; this.scrollY = y; },
  addEventListener(name, callback) { this.handlers[name] = callback; }};
global.requestAnimationFrame = (callback) => callback();
global.document = {
  activeElement: null, handlers: {},
  createElement(tag) { return new Element(tag); },
  getElementById(id) { return id === "gallery-viewer" ? dialog : null; },
  querySelectorAll(selector) { return selector === ".gallery-viewer-trigger" ? triggers : []; },
  addEventListener(name, callback) { this.handlers[name] = callback; },
};
function click(target) {
  let prevented = false;
  document.handlers.click({target, preventDefault() { prevented = true; }});
  return prevented;
}
function key(key) {
  let prevented = false;
  document.handlers.keydown({key, preventDefault() { prevented = true; }});
  return prevented;
}
vm.runInThisContext(fs.readFileSync(0, "utf8"));
assert.strictEqual(click(triggers[0]), true);
assert.strictEqual(dialog.open, true);
const feedback = stage.appended[0];
assert.strictEqual(feedback.attributes.role, "status");
assert.strictEqual(feedback.textContent, "Loading image...");
assert.strictEqual(feedback.hidden, false);
assert.strictEqual(image.hidden, true);
image.handlers.load();
assert.strictEqual(feedback.textContent, "");
assert.strictEqual(feedback.hidden, true);
assert.strictEqual(image.hidden, false);
assert.strictEqual(image.src, "images/1.jpg");
assert.strictEqual(caption.textContent, "Caption 1");
assert.strictEqual(status.textContent, "Image 1 of 2");
assert.strictEqual(actions.previous.disabled, true);
click(actions["zoom-in"]);
assert.strictEqual(image.styles["--gallery-viewer-zoom"], "1.5");
assert.strictEqual(key("ArrowRight"), true);
assert.strictEqual(image.src, "images/2.jpg");
assert.strictEqual(feedback.textContent, "Loading image...");
image.handlers.error();
assert.strictEqual(feedback.textContent, "Unable to load this image.");
assert.strictEqual(feedback.hidden, false);
assert.strictEqual(image.hidden, true);
assert.strictEqual(status.textContent, "Image 2 of 2");
assert.strictEqual(actions.next.disabled, true);
key("ArrowRight");
assert.strictEqual(status.textContent, "Image 2 of 2");
click(actions.previous);
assert.strictEqual(image.src, "images/1.jpg");
assert.strictEqual(feedback.textContent, "Loading image...");
image.handlers.load();
assert.strictEqual(feedback.hidden, true);
assert.strictEqual(image.hidden, false);
assert.strictEqual(key("Escape"), true);
assert.strictEqual(dialog.open, false);
assert.strictEqual(document.activeElement, triggers[0]);
assert.deepStrictEqual([window.scrollX, window.scrollY], [3, 420]);
assert.strictEqual(image.src, "");
assert.strictEqual(feedback.textContent, "");
assert.strictEqual(feedback.hidden, true);
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
