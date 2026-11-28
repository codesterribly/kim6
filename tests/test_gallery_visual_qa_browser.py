"""Rendered browser regressions for the confirmed KIMng gallery QA defects."""

import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
import sys
from urllib.request import urlopen

from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/bin"))

try:
    from websockets.sync.client import connect as websocket_connect
except ImportError:  # pragma: no cover - environment-specific browser support
    websocket_connect = None

from kim_story_publication import StoryDocument, StoryElement, render_website  # noqa: E402


VIEWPORTS = (
    (1920, 1080),
    (1440, 900),
    (800, 900),
    (768, 1024),
    (390, 844),
    (375, 812),
)
MODERN_RESPONSIVE_VIEWPORTS = (
    (1920, 1080), (1440, 900),
    (799, 900), (800, 900), (801, 900), (820, 900), (834, 900),
    (900, 900), (940, 900), (955, 900), (956, 900), (1024, 900),
    (768, 1024), (390, 844), (375, 812),
)
THEMES = (
    ("simple-light", "simple-gallery"),
    ("simple-dark", "simple-gallery"),
    ("modern", "photo-essay"),
    ("classic", "photo-essay"),
    ("dramatic", "photo-essay"),
)


class GalleryVisualQABrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chrome = shutil.which("google-chrome")
        if not cls.chrome:
            raise unittest.SkipTest("DEPENDENCY_MISSING: google-chrome executable")
        if websocket_connect is None:
            raise unittest.SkipTest("DEPENDENCY_MISSING: Python websockets package")

    def test_gallery_themes_viewports_viewer_geometry_and_heading_hierarchy(self):
        artifact_value = os.environ.get("KIM_GALLERY_BROWSER_ARTIFACT_DIR")
        artifact_dir = (Path(artifact_value) if artifact_value else
                        Path(tempfile.mkdtemp(prefix="kim-gallery-visual-qa-")))
        artifact_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="kim-gallery-visual-qa-fixtures-") as temp:
            root = Path(temp)
            fixtures = {}
            for style, publication_type in THEMES:
                fixtures[style] = self._write_gallery(
                    root / style, style=style, publication_type=publication_type,
                    chapters=False,
                )
            chapter_fixture = self._write_gallery(
                root / "modern-with-chapters", style="modern",
                publication_type="photo-essay", chapters=True,
            )

            profile = root / "chrome-profile"
            process = subprocess.Popen(
                [self.chrome, "--headless=new", "--disable-gpu", "--no-first-run",
                 "--disable-background-networking", "--disable-sync",
                 "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
                 "--remote-allow-origins=http://localhost",
                 f"--user-data-dir={profile}", "about:blank"],
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True,
            )
            websocket = None
            try:
                endpoint_file = profile / "DevToolsActivePort"
                deadline = time.monotonic() + 12
                while not endpoint_file.exists() and time.monotonic() < deadline:
                    if process.poll() is not None:
                        stderr = process.stderr.read() if process.stderr else ""
                        self.fail(
                            "BROWSER_STARTUP_BLOCKED: Chrome exited before DevTools started "
                            f"(exit {process.returncode}): {stderr.strip()}"
                        )
                    time.sleep(.05)
                if not endpoint_file.exists():
                    self.fail("BROWSER_STARTUP_BLOCKED: Chrome did not expose DevTools")
                port = endpoint_file.read_text(encoding="utf-8").splitlines()[0]
                try:
                    tabs = json.loads(urlopen(
                        f"http://127.0.0.1:{port}/json/list", timeout=2).read())
                    target = next(tab for tab in tabs if tab.get("type") == "page")
                    websocket = websocket_connect(
                        target["webSocketDebuggerUrl"], origin="http://localhost",
                        open_timeout=5,
                    )
                except Exception as exc:
                    raise RuntimeError(
                        f"BROWSER_AUTOMATION_FAILED: DevTools connection failed: {exc}"
                    ) from exc

                next_id = 0
                browser_errors = []

                def command(method, params=None):
                    nonlocal next_id
                    next_id += 1
                    request_id = next_id
                    try:
                        websocket.send(json.dumps({
                            "id": request_id, "method": method,
                            "params": params or {},
                        }))
                        while True:
                            response = json.loads(websocket.recv(timeout=8))
                            if response.get("id") == request_id:
                                if "error" in response:
                                    raise RuntimeError(response["error"])
                                return response.get("result", {})
                            self._collect_browser_error(response, browser_errors)
                    except Exception as exc:
                        raise RuntimeError(
                            f"BROWSER_AUTOMATION_FAILED: DevTools {method}: {exc}"
                        ) from exc

                def evaluate(expression):
                    result = command("Runtime.evaluate", {
                        "expression": expression, "returnByValue": True,
                        "awaitPromise": True,
                    })
                    remote = result.get("result", {})
                    if remote.get("exceptionDetails"):
                        raise RuntimeError(
                            "BROWSER_AUTOMATION_FAILED: JavaScript evaluation: "
                            f"{remote['exceptionDetails']}"
                        )
                    return remote.get("value")

                def set_viewport(width, height):
                    command("Emulation.setDeviceMetricsOverride", {
                        "width": width, "height": height, "deviceScaleFactor": 1,
                        "mobile": width <= 768,
                    })

                def load_gallery(path, width, height):
                    set_viewport(width, height)
                    command("Page.navigate", {"url": path.as_uri()})
                    deadline = time.monotonic() + 8
                    while time.monotonic() < deadline:
                        if evaluate(
                            "document.readyState === 'complete' && "
                            "!!document.querySelector('.gallery-viewer-trigger')"
                        ):
                            break
                        time.sleep(.05)
                    self.assertEqual(evaluate("document.readyState"), "complete")
                    evaluate(
                        "Array.from(document.images).forEach(image => image.loading='eager'); "
                        "Promise.all(Array.from(document.images).map(image => image.decode()))"
                    )
                    self.assertEqual(evaluate("location.protocol"), "file:")

                def save_screenshot(name):
                    result = command("Page.captureScreenshot", {
                        "format": "png", "fromSurface": True,
                        "captureBeyondViewport": False,
                    })
                    data = base64.b64decode(result.get("data", ""))
                    self.assertGreater(len(data), 24, f"empty screenshot: {name}")
                    self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n",
                                     f"invalid PNG screenshot: {name}")
                    path = artifact_dir / name
                    path.write_bytes(data)
                    return path

                def scroll_for_screenshot(selector):
                    evaluate(
                        "document.documentElement.style.scrollBehavior='auto';"
                        "(()=>{const target=document.querySelector(" + json.dumps(selector) + ");"
                        "window.scrollTo(0,window.scrollY+target.getBoundingClientRect().top-64)})()"
                    )

                command("Runtime.enable")
                command("Log.enable")
                command("Page.enable")

                screenshot_names = set()
                for style, _publication_type in THEMES:
                    viewports = (MODERN_RESPONSIVE_VIEWPORTS
                                 if style == "modern" else VIEWPORTS)
                    for width, height in viewports:
                        with self.subTest(style=style, viewport=(width, height)):
                            load_gallery(fixtures[style], width, height)
                            context = f"{style} at {width}x{height}"
                            self._assert_gallery_geometry(
                                evaluate, context, configured_viewport=(width, height))
                            self._assert_heading_hierarchy(evaluate, has_chapters=False)
                            self._assert_contrast(evaluate, style)

                            if style == "simple-dark" and (width, height) == (390, 844):
                                scroll_for_screenshot(
                                    ".image-story-item[data-element-id='portrait']"
                                )
                                save_screenshot("simple-dark-contrast-mobile.png")
                                screenshot_names.add("simple-dark-contrast-mobile.png")
                            if style == "simple-dark" and (width, height) == (1920, 1080):
                                scroll_for_screenshot(
                                    ".image-story-item[data-element-id='portrait']"
                                )
                                save_screenshot("simple-dark-contrast-desktop.png")
                                screenshot_names.add("simple-dark-contrast-desktop.png")

                            if style == "modern" and (width, height) == (1920, 1080):
                                evaluate("window.scrollTo(0, 0)")
                                save_screenshot("gallery-modern-hero-desktop.png")
                                screenshot_names.add("gallery-modern-hero-desktop.png")
                            if style == "modern":
                                evaluate("window.scrollTo(0, 0)")
                                hero_screenshot = f"gallery-modern-hero-{width}x{height}.png"
                                save_screenshot(hero_screenshot)
                                screenshot_names.add(hero_screenshot)
                            if style == "modern" and (width, height) == (390, 844):
                                evaluate("window.scrollTo(0, 0)")
                                save_screenshot("gallery-modern-hero-mobile.png")
                                screenshot_names.add("gallery-modern-hero-mobile.png")
                            if style == "modern" and (width, height) == (390, 844):
                                scroll_for_screenshot(
                                    ".image-story-item[data-element-id='portrait']"
                                )
                                save_screenshot("gallery-modern-portrait-mobile.png")
                                screenshot_names.add("gallery-modern-portrait-mobile.png")
                            if style == "modern" and (width, height) == (1440, 900):
                                scroll_for_screenshot(
                                    ".image-story-item[data-element-id='portrait']"
                                )
                                save_screenshot("gallery-modern-portrait-desktop.png")
                                screenshot_names.add("gallery-modern-portrait-desktop.png")
                            if style == "modern" and (width, height) == (375, 812):
                                scroll_for_screenshot(
                                    ".image-story-item[data-element-id='widescreen']"
                                )
                                save_screenshot("gallery-modern-widescreen-mobile.png")
                                screenshot_names.add("gallery-modern-widescreen-mobile.png")
                            if style == "modern" and (width, height) == (1440, 900):
                                scroll_for_screenshot(
                                    ".image-story-item[data-element-id='widescreen']"
                                )
                                save_screenshot("gallery-modern-widescreen-desktop.png")
                                screenshot_names.add("gallery-modern-widescreen-desktop.png")

                            capture_viewer = style == "modern" and (width, height) in {
                                (1440, 900), (390, 844),
                            }
                            self._assert_viewer_geometry(
                                evaluate, context, save_screenshot,
                                mobile=(width <= 600),
                                screenshot_names=screenshot_names,
                                capture_screenshots=capture_viewer,
                            )
                            if style == "modern" and (width, height) in {
                                (1440, 900), (390, 844),
                            }:
                                self._assert_viewer_interactions(evaluate, context)

                load_gallery(chapter_fixture, 1440, 900)
                self._assert_heading_hierarchy(evaluate, has_chapters=True)
                chapter_state = json.loads(evaluate(
                    "JSON.stringify({chapter: document.querySelector('.chapter h2')?.textContent, "
                    "toc: [...document.querySelectorAll('.contents a')].map(link => link.textContent), "
                    "links: [...document.querySelectorAll('.chapter-nav a')].map(link => link.textContent)})"
                ))
                self.assertEqual(chapter_state["chapter"], "Field notes")
                self.assertIn("Field notes", chapter_state["toc"])
                self.assertIn("Back to opening", chapter_state["links"])
                self.assertIn("Next chapter", chapter_state["links"])

                evaluate("new Promise(resolve => setTimeout(resolve, 150))")
                while True:
                    try:
                        response = json.loads(websocket.recv(timeout=.12))
                    except TimeoutError:
                        break
                    self._collect_browser_error(response, browser_errors)
                self.assertEqual(browser_errors, [], browser_errors)
                for name in sorted(screenshot_names):
                    print(f"BROWSER_SCREENSHOT={artifact_dir / name}")
            finally:
                if websocket is not None:
                    websocket.close()
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                if process.stderr:
                    process.stderr.close()

    @staticmethod
    def _collect_browser_error(response, browser_errors):
        if (response.get("method") == "Runtime.exceptionThrown"
                or response.get("method") == "Log.entryAdded"
                and response.get("params", {}).get("entry", {}).get("level") == "error"):
            browser_errors.append(response)

    @staticmethod
    def _write_gallery(root, *, style, publication_type, chapters):
        (root / "images").mkdir(parents=True)
        (root / "thumbs").mkdir(parents=True)
        image_specs = (
            ("hero", 900, 600, 0xff39718e, "Cover description."),
            ("portrait", 600, 900, 0xffb76c42, "Portrait description paragraph one.\n\nPortrait description paragraph two."),
            ("landscape", 1200, 800, 0xff337799, "Landscape description paragraph one.\n\nLandscape description paragraph two."),
            ("widescreen", 1600, 600, 0xff7465a6, "Widescreen description paragraph one.\n\nWidescreen description paragraph two."),
        )
        elements = []
        for element_id, width, height, color, description in image_specs:
            image = QImage(width, height, QImage.Format_RGB32)
            image.fill(color)
            output = f"images/{element_id}.jpg"
            if not image.save(str(root / output), "JPEG"):
                raise RuntimeError(f"Could not create browser fixture image {output}")
            thumb_rel = ""
            tw, th = 0, 0
            if publication_type == "simple-gallery":
                scale = min(1.0, 640 / max(width, height))
                tw = max(1, round(width * scale))
                th = max(1, round(height * scale))
                thumb_img = image.scaled(tw, th)
                thumb_rel = f"thumbs/{element_id}.jpg"
                if not thumb_img.save(str(root / thumb_rel), "JPEG"):
                    raise RuntimeError(f"Could not create browser fixture thumb {thumb_rel}")
            elements.append(StoryElement(
                "image", element_id,
                "" if element_id == "hero" else f"{element_id.title()} heading",
                "", "", output, f"/private/source-{element_id}.jpg",
                image_width=width, image_height=height, description=description,
                thumb_image=thumb_rel, thumb_width=tw, thumb_height=th,
            ))
        if chapters:
            elements.insert(2, StoryElement("heading", "chapter-field-notes", "Field notes"))
            elements.insert(3, StoryElement("heading", "chapter-long-view", "The long view"))
        layout = "masonry" if publication_type == "simple-gallery" else "one-per-section"
        rendered = render_website(StoryDocument(
            "Gallery visual QA", "A generated browser fixture.", publication_type,
            style, True, tuple(elements), layout=layout,
        ))
        root.mkdir(parents=True, exist_ok=True)
        (root / "index.html").write_text(rendered.html, encoding="utf-8")
        (root / "style.css").write_text(rendered.css, encoding="utf-8")
        (root / "gallery-viewer.css").write_text(rendered.viewer_css, encoding="utf-8")
        (root / "gallery-viewer.js").write_text(rendered.viewer_js, encoding="utf-8")
        return root / "index.html"

    def _assert_gallery_geometry(self, evaluate, context, *, configured_viewport):
        expression = (
            "JSON.stringify((() => { const rect = element => { if(!element)return null; "
            "const r=element.getBoundingClientRect(); "
            "return {x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}; }; "
            "const pubType=document.body.dataset.publicationType || ''; "
            "const items=[...document.querySelectorAll('.image-story-item')].map(item => { "
            "const image=item.querySelector('.photograph img'); const heading=item.querySelector('.image-heading'); "
            "const description=item.querySelector('.image-description'); return {id:item.dataset.elementId, "
            "src:image?image.getAttribute('src'):'', "
            "item:rect(item), image:rect(image), naturalWidth:image.naturalWidth, "
            "naturalHeight:image.naturalHeight, heading:heading?rect(heading):null, "
            "description:description?rect(description):null}; }); "
            "const coverContainer=document.querySelector('.cover.has-hero'); "
            "const coverCopy=document.querySelector('.cover-copy'); const hero=document.querySelector('.hero-image img'); "
            "const heroStory=document.querySelector('.hero-image'); "
            "const heroHeading=document.querySelector('.cover-copy .story-title'); "
            "const heroImageHeading=document.querySelector('.hero-image .image-heading'); "
            "const heroDescription=document.querySelector('.hero-image .image-description'); "
            "const story=document.querySelector('#story'); "
            "const grid=document.querySelector('.image-group'); "
            "const cw = el => el ? getComputedStyle(el).width : null; "
            "return {configuredViewport:CONFIGURED_VIEWPORT, publicationType:pubType, "
            "width:innerWidth, height:innerHeight, contentWidth:document.documentElement.clientWidth, "
            "media800:matchMedia('(max-width: 800px)').matches, "
            "scrollWidth:document.documentElement.scrollWidth, items, "
            "grid:rect(grid), "
            "coverContainer:rect(coverContainer), cover:rect(coverCopy), hero:rect(hero), heroStory:rect(heroStory), "
            "heroHeading:rect(heroHeading), heroImageHeading:rect(heroImageHeading), "
            "heroDescription:rect(heroDescription), story:rect(story), "
            "intro:rect(document.querySelector('.cover-copy .introduction')), computed:{"
            "coverCopy:cw(coverCopy), heroStory:cw(heroStory), heroImage:cw(hero), "
            "heroTitle:cw(heroHeading), heroImageHeading:cw(heroImageHeading), "
            "heroDescription:cw(heroDescription), story:cw(story)}}; })())"
        ).replace("CONFIGURED_VIEWPORT", json.dumps(configured_viewport))
        state_value = evaluate(expression)
        state = json.loads(state_value)
        if context.startswith("modern "):
            bounds = lambda rect: [round(rect["x"], 2), round(rect["right"], 2)]
            print("R01_GEOMETRY " + json.dumps({
                "configured": state["configuredViewport"],
                "innerWidth": state["width"], "clientWidth": state["contentWidth"],
                "media800": state["media800"], "scrollWidth": state["scrollWidth"],
                "coverCopy": bounds(state["cover"]),
                "heroStory": bounds(state["heroStory"]),
                "heroImage": bounds(state["hero"]),
                "heroTitle": bounds(state["heroHeading"]),
                "heroDescription": bounds(state["heroDescription"]),
                "story": bounds(state["story"]), "computedWidths": state["computed"],
            }, separators=(",", ":")))
        self.assertEqual(state["width"], configured_viewport[0],
                         f"{context}: configured and effective viewport widths differ: {state}")
        self.assertEqual(state["height"], configured_viewport[1],
                         f"{context}: configured and effective viewport heights differ: {state}")
        self.assertLessEqual(state["scrollWidth"], state["width"], f"{context}: page overflow {state}")

        if state["publicationType"] == "simple-gallery":
            self.assertIsNone(state["heroStory"], f"{context}: Simple Gallery must not render mandatory editorial hero")
            self.assertIsNone(state["coverContainer"], f"{context}: Simple Gallery must not render .cover.has-hero")
            self.assertIsNotNone(state["grid"], f"{context}: Simple Gallery must render an immediate gallery grid")
            self.assertLess(state["grid"]["y"], state["height"], f"{context}: Simple Gallery grid must be visible above the fold")
            self.assertEqual(len(state["items"]), 4, f"{context}: expected 4 gallery tiles")
            for item in state["items"]:
                with self.subTest(context=context, element=item["id"]):
                    self.assertTrue(item["src"].startswith("thumbs/"), f"{context}: expected thumbnail src: {item}")
                    self.assertGreater(item["naturalWidth"], 0)
                    self.assertGreater(item["naturalHeight"], 0)
                    self.assertGreater(item["image"]["width"], 0)
                    self.assertGreater(item["image"]["height"], 0)
                    natural_ratio = item["naturalWidth"] / item["naturalHeight"]
                    rendered_ratio = item["image"]["width"] / item["image"]["height"]
                    self.assertAlmostEqual(rendered_ratio, natural_ratio, delta=.025,
                                           msg=f"{context}: aspect ratio changed: {item}")
            return
        for item in state["items"]:
            with self.subTest(context=context, element=item["id"]):
                self.assertGreater(item["image"]["width"], 0)
                self.assertGreater(item["image"]["height"], 0)
                natural_ratio = item["naturalWidth"] / item["naturalHeight"]
                rendered_ratio = item["image"]["width"] / item["image"]["height"]
                self.assertAlmostEqual(rendered_ratio, natural_ratio, delta=.025,
                                       msg=f"{context}: aspect ratio changed: {item}")
                if item["id"] == "hero":
                    continue
                self.assertAlmostEqual(item["item"]["x"], item["image"]["x"], delta=2,
                                       msg=f"{context}: item/image x mismatch: {item}")
                self.assertAlmostEqual(item["item"]["width"], item["image"]["width"], delta=2,
                                       msg=f"{context}: item/image width mismatch: {item}")
                if item["heading"]:
                    self.assertAlmostEqual(item["heading"]["x"], item["image"]["x"], delta=2,
                                           msg=f"{context}: image heading left edge mismatch: {item}")
                    self.assertAlmostEqual(item["heading"]["width"], item["image"]["width"], delta=2,
                                           msg=f"{context}: image heading width mismatch: {item}")
                if item["description"]:
                    self.assertAlmostEqual(item["description"]["x"], item["image"]["x"], delta=2,
                                           msg=f"{context}: description left edge mismatch: {item}")
                    self.assertAlmostEqual(item["description"]["width"], item["image"]["width"], delta=2,
                                           msg=f"{context}: description width mismatch: {item}")

        if context.startswith("modern "):
            hero = next(item for item in state["items"] if item["id"] == "hero")
            self.assertAlmostEqual(state["cover"]["x"], hero["image"]["x"], delta=2,
                                   msg=f"{context}: hero heading container x mismatch: {state}")
            self.assertAlmostEqual(state["cover"]["width"], hero["image"]["width"], delta=2,
                                   msg=f"{context}: hero heading container width mismatch: {state}")
            self.assertAlmostEqual(state["intro"]["x"], state["cover"]["x"], delta=2,
                                   msg=f"{context}: hero description x mismatch")
            self.assertLessEqual(state["intro"]["width"], state["cover"]["width"] + 2,
                                 f"{context}: hero description wider than the hero photograph")
            for label, rect in (
                ("hero story", state["heroStory"]),
                ("hero description", state["heroDescription"]),
            ):
                self.assertAlmostEqual(rect["x"], state["hero"]["x"], delta=2,
                                       msg=f"{context}: {label} left edge differs from image: {state}")
                self.assertAlmostEqual(rect["width"], state["hero"]["width"], delta=2,
                                       msg=f"{context}: {label} width differs from image: {state}")
            self.assertAlmostEqual(state["heroHeading"]["x"], state["cover"]["x"], delta=2,
                                   msg=f"{context}: hero title is not aligned with its copy: {state}")
            self.assertLessEqual(state["heroHeading"]["right"], state["cover"]["right"] + 2,
                                 f"{context}: hero title extends beyond its copy: {state}")
            self.assertEqual(state["media800"], state["width"] <= 800,
                             f"{context}: unexpected 800px media-query result: {state}")
            for label, rect in (
                ("hero copy", state["cover"]),
                ("hero story", state["heroStory"]),
                ("hero image", state["hero"]),
                ("hero title", state["heroHeading"]),
                ("hero description", state["heroDescription"]),
                ("hero introduction", state["intro"]),
            ):
                self.assertGreaterEqual(rect["x"], 15,
                                        f"{context}: {label} has no left gutter: {state}")
                self.assertLessEqual(rect["right"], state["contentWidth"] - 15,
                                     f"{context}: {label} has no right gutter: {state}")
            if state["width"] <= 800:
                for label, rect in (
                    ("hero copy", state["cover"]),
                    ("hero introduction", state["intro"]),
                    ("hero story", state["heroStory"]),
                    ("hero image", state["hero"]),
                    ("hero title", state["heroHeading"]),
                    ("hero description", state["heroDescription"]),
                ):
                    self.assertGreaterEqual(rect["x"], 15,
                                            f"{context}: {label} lost left gutter: {state}")
                    self.assertLessEqual(rect["right"], state["width"] - 15,
                                         f"{context}: {label} lost right gutter: {state}")
                for label, rect in (("hero copy", state["cover"]),
                                    ("hero story", state["heroStory"]),
                                    ("hero image", state["hero"])):
                    self.assertAlmostEqual(rect["x"], 16, delta=1.5,
                                           msg=f"{context}: {label} should keep a 16px gutter: {state}")
                    self.assertAlmostEqual(rect["right"], state["contentWidth"] - 16, delta=1.5,
                                           msg=f"{context}: {label} should keep a 16px gutter: {state}")

    def _assert_heading_hierarchy(self, evaluate, *, has_chapters):
        headings = json.loads(evaluate(
            "JSON.stringify([...document.querySelectorAll('h1,h2,h3')].map(h => "
            "({tag:h.tagName,text:h.textContent.trim(),className:h.className})))"
        ))
        self.assertEqual(sum(item["tag"] == "H1" for item in headings), 1, headings)
        image_headings = [item for item in headings if "image-heading" in item["className"]]
        self.assertEqual(len(image_headings), 3, headings)
        self.assertTrue(all(item["tag"] == "H2" for item in image_headings), headings)
        if has_chapters:
            self.assertIn({"tag": "H2", "text": "Field notes", "className": ""}, headings)
        else:
            self.assertFalse(any(item["tag"] == "H3" for item in headings), headings)

    def _assert_contrast(self, evaluate, style):
        state = json.loads(evaluate(
            "JSON.stringify((() => { const rgb=value => value.match(/[\\d.]+/g).map(Number).slice(0,3); "
            "const linear=x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}; "
            "const lum=color=>{const [r,g,b]=rgb(color).map(linear);return .2126*r+.7152*g+.0722*b}; "
            "const bg=getComputedStyle(document.body).backgroundColor; const items=[...document.querySelectorAll("
            "'.image-description,.image-heading')].map(el=>{const fg=getComputedStyle(el).color; "
            "const a=lum(fg),b=lum(bg);return {selector:el.className,text:el.textContent.trim(),fg,bg, "
            "ratio:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};});return {bg,items};})())"
        ))
        if style == "simple-dark":
            self.assertEqual(state["bg"], "rgb(18, 22, 28)")
            for item in state["items"]:
                self.assertGreaterEqual(item["ratio"], 4.5,
                                        f"Simple Dark contrast below 4.5:1: {item}")
        elif style == "simple-light":
            colors = {item["selector"]: item["fg"] for item in state["items"]}
            self.assertIn("rgb(23, 33, 43)", colors.values())
            self.assertIn("rgb(23, 105, 163)", colors.values())
        elif style == "modern":
            colors = {item["selector"]: item["fg"] for item in state["items"]}
            self.assertIn("rgb(23, 105, 163)", colors.values())
            self.assertIn("rgb(22, 37, 52)", colors.values())

    def _assert_viewer_geometry(self, evaluate, context, save_screenshot, *, mobile,
                                screenshot_names, capture_screenshots=False):
        metrics = ("mobile" if mobile else "desktop")
        screenshot_name = f"viewer-fit-portrait-{metrics}.png"
        image_specs = (
            (0, "hero landscape", (900, 600)),
            (1, "portrait", (600, 900)),
            (2, "landscape", (1200, 800)),
            (3, "widescreen", (1600, 600)),
        )
        for image_index, aspect, (expected_width, expected_height) in image_specs:
            image_context = f"{context}, {aspect} image"
            evaluate(f"document.querySelectorAll('.gallery-viewer-trigger')[{image_index}].click()")
            self.assertTrue(evaluate("document.querySelector('#gallery-viewer').open"))
            evaluate(
                "new Promise((resolve,reject)=>{const img=document.querySelector('.gallery-viewer__image'); "
                f"const width={expected_width},height={expected_height},started=Date.now();"
                "const poll=()=>{if(img.naturalWidth===width&&img.naturalHeight===height)resolve(true);"
                "else if(Date.now()-started>5000)reject(new Error('viewer image did not load at expected size'));"
                "else setTimeout(poll,20)};poll()})"
            )
            for fit_cycle in (0, 1):
                self.assertTrue(evaluate("document.querySelector('#gallery-viewer').open"))
                evaluate("document.querySelector('[data-viewer-action=fit]').click()")
                self._wait_for_fit(evaluate, expected_width / expected_height, image_context, aspect)
                fit = self._viewer_rectangles(evaluate)
                self._assert_fits_stage(fit, image_context, aspect)
                if capture_screenshots and image_index == 1 and fit_cycle == 0:
                    save_screenshot(screenshot_name)
                    screenshot_names.add(screenshot_name)

                evaluate("document.querySelector('[data-viewer-action=zoom-in]').click(); "
                         "document.querySelector('[data-viewer-action=zoom-in]').click()")
                self._wait_for_zoom(evaluate, image_context, aspect)
                self.assertEqual(evaluate(
                    "document.querySelector('.gallery-viewer__image').style.getPropertyValue('--gallery-viewer-zoom')"
                ), "2")
                zoomed = self._viewer_rectangles(evaluate)
                edges = self._assert_zoom_edges_reachable(evaluate, zoomed, image_context)
                if capture_screenshots and image_index == 1 and fit_cycle == 0:
                    evaluate("document.querySelector('.gallery-viewer__stage').scrollTo(0,0)")
                    self._wait_for_scroll(evaluate, edges["start"], image_context)
                    save_screenshot(f"viewer-zoom-2x-{metrics}.png")
                    screenshot_names.add(f"viewer-zoom-2x-{metrics}.png")
                    evaluate(
                        "(()=>{const s=document.querySelector('.gallery-viewer__stage');"
                        "s.scrollTo(s.scrollWidth,s.scrollHeight)})()"
                    )
                    self._wait_for_scroll(evaluate, edges["end"], image_context)
                    save_screenshot(f"viewer-zoom-2x-right-bottom-{metrics}.png")
                    screenshot_names.add(f"viewer-zoom-2x-right-bottom-{metrics}.png")
                if fit_cycle == 0:
                    evaluate("document.querySelector('[data-viewer-action=fit]').click()")
                    self._wait_for_fit(evaluate, expected_width / expected_height, image_context, aspect)
                    self._assert_fits_stage(self._viewer_rectangles(evaluate), image_context, aspect)
            evaluate("document.querySelector('[data-viewer-action=close]').click()")
            self.assertFalse(evaluate("document.querySelector('#gallery-viewer').open"))
            evaluate(
                "new Promise(resolve=>{const wait=()=>document.querySelector("
                "'.gallery-viewer__image').getAttribute('src')===null?resolve(true):setTimeout(wait,10);wait()})"
            )

    @staticmethod
    def _viewer_rectangles(evaluate):
        return json.loads(evaluate(
            "JSON.stringify((() => {const stage=document.querySelector('.gallery-viewer__stage'); "
            "const image=document.querySelector('.gallery-viewer__image'); const s=stage.getBoundingClientRect(); "
            "const i=image.getBoundingClientRect(); return {stage:{x:s.x,y:s.y,width:s.width,height:s.height, "
            "right:s.right,bottom:s.bottom,clientWidth:stage.clientWidth,clientHeight:stage.clientHeight, "
            "scrollWidth:stage.scrollWidth,scrollHeight:stage.scrollHeight,scrollLeft:stage.scrollLeft, "
            "scrollTop:stage.scrollTop},image:{x:i.x,y:i.y,width:i.width,height:i.height, "
            "right:i.right,bottom:i.bottom,naturalWidth:image.naturalWidth,naturalHeight:image.naturalHeight, "
            "zoom:image.style.getPropertyValue('--gallery-viewer-zoom')},computed:{"
            "stageDisplay:getComputedStyle(stage).display,justifyItems:getComputedStyle(stage).justifyItems,"
            "alignItems:getComputedStyle(stage).alignItems,imageMarginLeft:getComputedStyle(image).marginLeft,"
            "imageMarginRight:getComputedStyle(image).marginRight,imageDisplay:getComputedStyle(image).display,"
            "imagePosition:getComputedStyle(image).position,imageTransform:getComputedStyle(image).transform,"
            "imageOffsetLeft:image.offsetLeft,imageOffsetParent:image.offsetParent?.className}};})())"
        ))

    def _assert_fits_stage(self, geometry, context, aspect):
        stage = geometry["stage"]
        image = geometry["image"]
        self.assertGreaterEqual(image["x"], stage["x"] - 1,
                                f"{context}: {aspect} image left clipped in Fit: {geometry}")
        self.assertGreaterEqual(image["y"], stage["y"] - 1,
                                f"{context}: {aspect} image top clipped in Fit: {geometry}")
        self.assertLessEqual(image["right"], stage["right"] + 1,
                             f"{context}: {aspect} image right clipped in Fit: {geometry}")
        self.assertLessEqual(image["bottom"], stage["bottom"] + 1,
                             f"{context}: {aspect} image bottom clipped in Fit: {geometry}")
        self.assertLessEqual(stage["scrollWidth"], stage["clientWidth"] + 1,
                             f"{context}: {aspect} unexpectedly scrolls in Fit: {geometry}")
        self.assertLessEqual(stage["scrollHeight"], stage["clientHeight"] + 1,
                             f"{context}: {aspect} unexpectedly scrolls in Fit: {geometry}")
        self.assertAlmostEqual(
            image["x"], stage["x"] + (stage["clientWidth"] - image["width"]) / 2,
            delta=2, msg=f"{context}: {aspect} is not centered horizontally in Fit: {geometry}",
        )
        self.assertAlmostEqual(
            image["y"], stage["y"] + (stage["clientHeight"] - image["height"]) / 2,
            delta=2, msg=f"{context}: {aspect} is not centered vertically in Fit: {geometry}",
        )
        self.assertGreater(image["naturalWidth"], 0, f"{context}: {aspect} did not load: {geometry}")
        self.assertGreater(image["naturalHeight"], 0, f"{context}: {aspect} did not load: {geometry}")
        self.assertAlmostEqual(
            image["width"] / image["height"],
            image["naturalWidth"] / image["naturalHeight"], delta=.01,
            msg=f"{context}: {aspect} Fit changed the image aspect ratio: {geometry}",
        )

    def _wait_for_fit(self, evaluate, expected_ratio, context, aspect):
        result = evaluate(
            "new Promise((resolve,reject)=>{const image=document.querySelector("
            "'.gallery-viewer__image'),stage=document.querySelector('.gallery-viewer__stage'); "
            f"const ratio={expected_ratio},started=Date.now();const poll=()=>{{"
            "const i=image.getBoundingClientRect(),s=stage.getBoundingClientRect();"
            "const actual=i.width/i.height;const ready=Math.abs(actual-ratio)<.01&&"
            "Math.abs(i.width-parseFloat(image.style.width))<1&&"
            "Math.abs(i.height-parseFloat(image.style.height))<1&&"
            "i.left>=s.left-1&&i.top>=s.top-1&&i.right<=s.right+1&&i.bottom<=s.bottom+1&&"
            "stage.scrollWidth<=stage.clientWidth+1&&stage.scrollHeight<=stage.clientHeight+1;"
            "if(ready)resolve(true);else if(Date.now()-started>3000)reject(new Error('Fit geometry did not settle'));"
            "else setTimeout(poll,20)};poll()})"
        )
        self.assertTrue(result, f"{context}: {aspect} Fit did not settle")

    def _assert_zoom_edges_reachable(self, evaluate, initial, context):
        self.assertEqual(initial["image"]["zoom"], "2", initial)
        evaluate("document.querySelector('.gallery-viewer__stage').scrollTo(0,0)")
        start = self._viewer_rectangles(evaluate)
        self.assertEqual(start["stage"]["scrollLeft"], 0, f"{context}: horizontal minimum: {start}")
        self.assertEqual(start["stage"]["scrollTop"], 0, f"{context}: vertical minimum: {start}")
        if start["image"]["width"] > start["stage"]["clientWidth"] + 1:
            self.assertAlmostEqual(start["image"]["x"], start["stage"]["x"], delta=2,
                                   msg=f"{context}: zoomed left edge is unreachable: {start}")
        else:
            expected_x = start["stage"]["x"] + (start["stage"]["clientWidth"] - start["image"]["width"]) / 2
            self.assertAlmostEqual(start["image"]["x"], expected_x, delta=2,
                                   msg=f"{context}: fitting image is not centered horizontally: {start}")
        if start["image"]["height"] > start["stage"]["clientHeight"] + 1:
            self.assertAlmostEqual(start["image"]["y"], start["stage"]["y"], delta=2,
                                   msg=f"{context}: zoomed top edge is unreachable: {start}")
        else:
            expected_y = start["stage"]["y"] + (start["stage"]["clientHeight"] - start["image"]["height"]) / 2
            self.assertAlmostEqual(start["image"]["y"], expected_y, delta=2,
                                   msg=f"{context}: fitting image is not centered vertically: {start}")
        self._assert_scroll_extent_covers_image(start, context)
        evaluate("new Promise(resolve=>{const s=document.querySelector('.gallery-viewer__stage');"
                 "s.scrollTo(s.scrollWidth,s.scrollHeight);"
                 "requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(true)))})")
        end = self._viewer_rectangles(evaluate)
        self._assert_scroll_extent_covers_image(end, context)
        self.assertLessEqual(
            abs(end["stage"]["scrollLeft"] -
                max(0, end["stage"]["scrollWidth"] - end["stage"]["clientWidth"])),
            1, f"{context}: horizontal maximum is unreachable: {end}",
        )
        self.assertLessEqual(
            abs(end["stage"]["scrollTop"] -
                max(0, end["stage"]["scrollHeight"] - end["stage"]["clientHeight"])),
            1, f"{context}: vertical maximum is unreachable: {end}",
        )
        if end["image"]["width"] > end["stage"]["clientWidth"] + 1:
            self.assertGreater(end["stage"]["scrollLeft"], 0,
                               f"{context}: no horizontal overflow for oversized image: {end}")
            self.assertLessEqual(end["image"]["right"],
                                 end["stage"]["x"] + end["stage"]["clientWidth"] + 1,
                                 f"{context}: zoomed right edge is unreachable: {end}")
        else:
            expected_x = end["stage"]["x"] + (end["stage"]["clientWidth"] - end["image"]["width"]) / 2
            self.assertAlmostEqual(end["image"]["x"], expected_x, delta=2,
                                   msg=f"{context}: fitting image is not centered: {end}")
            self.assertLessEqual(end["image"]["right"], end["stage"]["right"] + 1,
                                 f"{context}: fitting image is right of the stage: {end}")
        if end["image"]["height"] > end["stage"]["clientHeight"] + 1:
            self.assertGreater(end["stage"]["scrollTop"], 0,
                               f"{context}: no vertical overflow for oversized image: {end}")
            self.assertLessEqual(end["image"]["bottom"],
                                 end["stage"]["y"] + end["stage"]["clientHeight"] + 1,
                                 f"{context}: zoomed bottom edge is unreachable: {end}")
        else:
            expected_y = end["stage"]["y"] + (end["stage"]["clientHeight"] - end["image"]["height"]) / 2
            self.assertAlmostEqual(end["image"]["y"], expected_y, delta=2,
                                   msg=f"{context}: fitting image is not centered: {end}")
            self.assertLessEqual(end["image"]["bottom"], end["stage"]["bottom"] + 1,
                                 f"{context}: fitting image is below the stage: {end}")
        return {"start": start, "end": end}

    def _assert_scroll_extent_covers_image(self, geometry, context):
        stage = geometry["stage"]
        image = geometry["image"]
        required_width = max(stage["clientWidth"], image["right"] - stage["x"])
        required_height = max(stage["clientHeight"], image["bottom"] - stage["y"])
        self.assertGreaterEqual(stage["scrollWidth"], required_width - 1,
                                f"{context}: scrollWidth omits rendered image: {geometry}")
        self.assertGreaterEqual(stage["scrollHeight"], required_height - 1,
                                f"{context}: scrollHeight omits rendered image: {geometry}")

    def _wait_for_zoom(self, evaluate, context, aspect):
        result = evaluate(
            "new Promise(resolve=>{const image=document.querySelector("
            "'.gallery-viewer__image'),stage=document.querySelector('.gallery-viewer__stage');"
            "const started=Date.now();const poll=()=>{const i=image.getBoundingClientRect(),s=stage.getBoundingClientRect();"
            "const ready=image.style.getPropertyValue('--gallery-viewer-zoom')==='2'&&"
            "Math.abs(i.width-parseFloat(image.style.width))<1&&"
            "Math.abs(i.height-parseFloat(image.style.height))<1&&"
            "Math.abs(i.width/i.height-image.naturalWidth/image.naturalHeight)<.01;"
            "const state={ready,width:i.width,targetWidth:parseFloat(image.style.width),height:i.height,"
            "targetHeight:parseFloat(image.style.height),scrollWidth:stage.scrollWidth,scrollHeight:stage.scrollHeight,"
            "left:i.left,top:i.top,stageLeft:s.left,stageTop:s.top,ratio:i.width/i.height,"
            "naturalRatio:image.naturalWidth/image.naturalHeight,stageDisplay:getComputedStyle(stage).display,"
            "justifyItems:getComputedStyle(stage).justifyItems,imageDisplay:getComputedStyle(image).display,"
            "imagePosition:getComputedStyle(image).position,imageTransform:getComputedStyle(image).transform,"
            "marginLeft:getComputedStyle(image).marginLeft,marginRight:getComputedStyle(image).marginRight,"
            "offsetLeft:image.offsetLeft,offsetParent:image.offsetParent?.className};"
            "if(ready||Date.now()-started>1000)resolve(state);else requestAnimationFrame(poll)};poll()})"
        )
        self.assertTrue(result["ready"], f"{context}: {aspect} 2x zoom geometry did not settle: {result}")

    def _wait_for_scroll(self, evaluate, geometry, context):
        expected_left = geometry["stage"]["scrollLeft"]
        expected_top = geometry["stage"]["scrollTop"]
        result = evaluate(
            "new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve(true))))"
        )
        self.assertTrue(result, f"{context}: scroll did not settle")
        settled = self._viewer_rectangles(evaluate)
        self.assertLessEqual(abs(settled["stage"]["scrollLeft"] - expected_left), 1, settled)
        self.assertLessEqual(abs(settled["stage"]["scrollTop"] - expected_top), 1, settled)

    def _assert_viewer_interactions(self, evaluate, context):
        evaluate("document.documentElement.style.scrollBehavior='auto';window.scrollTo(0,320)")
        expected_scroll = evaluate("window.scrollY")
        trigger = "document.querySelectorAll('.gallery-viewer-trigger')[1]"
        evaluate(f"{trigger}.click()")
        self.assertEqual(evaluate(
            "document.querySelector('.gallery-viewer__status').textContent"
        ), "Image 2 of 4", context)
        evaluate("document.dispatchEvent(new KeyboardEvent('keydown', "
                 "{key:'ArrowRight',bubbles:true}))")
        self.assertEqual(evaluate(
            "document.querySelector('.gallery-viewer__status').textContent"
        ), "Image 3 of 4", context)
        evaluate("document.querySelector('[data-viewer-action=previous]').click()")
        self.assertEqual(evaluate(
            "document.querySelector('.gallery-viewer__status').textContent"
        ), "Image 2 of 4", context)
        evaluate("document.dispatchEvent(new KeyboardEvent('keydown', "
                 "{key:'Escape',bubbles:true}))")
        self.assertFalse(evaluate("document.querySelector('#gallery-viewer').open"))
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if evaluate(f"document.activeElement === {trigger}"):
                break
            time.sleep(.02)
        self.assertTrue(evaluate(f"document.activeElement === {trigger}"),
                        f"{context}: focus did not return to the opener")
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if evaluate("Math.abs(window.scrollY - " + str(expected_scroll) + ") <= 1"):
                break
            time.sleep(.02)
        self.assertEqual(evaluate("window.scrollY"), expected_scroll,
                         f"{context}: closing viewer changed page scroll")


if __name__ == "__main__":
    unittest.main()
