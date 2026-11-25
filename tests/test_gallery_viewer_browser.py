"""Real Chrome checks for the local gallery viewer.

Dependency absence is a visible unittest skip. Browser startup and DevTools
problems are errors with environment/automation markers, never passing skips.
"""

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/bin"))

try:
    from websockets.sync.client import connect as websocket_connect
except ImportError:  # pragma: no cover - environment-specific browser support
    websocket_connect = None

from kim_story_publication import StoryDocument, StoryElement, render_website  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402


class GalleryViewerBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chrome = shutil.which("google-chrome")
        if not cls.chrome:
            raise unittest.SkipTest("DEPENDENCY_MISSING: google-chrome executable")
        if websocket_connect is None:
            raise unittest.SkipTest("DEPENDENCY_MISSING: Python websockets package")

    def test_viewer_navigation_zoom_escape_focus_and_mobile_overflow(self):
        artifact_value = os.environ.get("KIM_GALLERY_BROWSER_ARTIFACT_DIR")
        artifact_dir = (Path(artifact_value) if artifact_value else
                        Path(tempfile.mkdtemp(prefix="kim-gallery-browser-artifacts-")))
        artifact_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="kim-gallery-viewer-browser-") as temp:
            root = Path(temp)
            (root / "images").mkdir()
            elements = []
            for index, color in enumerate((0xff337799, 0xffb76c42), 1):
                image = QImage(720, 480, QImage.Format_RGB32)
                image.fill(color)
                self.assertTrue(image.save(str(root / f"images/{index:04d}.jpg"), "JPEG"))
                elements.append(StoryElement(
                    "image", f"frame-{index}", f"Frame {index}", "", "",
                    f"images/{index:04d}.jpg", f"/private/source-{index}.jpg",
                    image_width=720, image_height=480,
                    description=f"Description for frame {index}.\n\nSecond paragraph for frame {index}.",
                ))
            rendered = render_website(StoryDocument(
                "Viewer test", "A local browser test.", "photo-essay", "modern",
                True, tuple(elements), layout="one-per-section",
            ))
            (root / "index.html").write_text(rendered.html, encoding="utf-8")
            (root / "style.css").write_text(rendered.css, encoding="utf-8")
            (root / "gallery-viewer.css").write_text(rendered.viewer_css, encoding="utf-8")
            (root / "gallery-viewer.js").write_text(rendered.viewer_js, encoding="utf-8")

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
                    self.fail(
                        "BROWSER_STARTUP_BLOCKED: Chrome did not create DevToolsActivePort "
                        "within 12 seconds"
                    )
                port = endpoint_file.read_text(encoding="utf-8").splitlines()[0]
                try:
                    tabs = json.loads(urlopen(
                        f"http://127.0.0.1:{port}/json/list", timeout=2).read())
                    target = next(tab for tab in tabs if tab.get("type") == "page")
                    websocket = websocket_connect(
                        target["webSocketDebuggerUrl"], origin="http://localhost",
                        open_timeout=5)
                except Exception as exc:
                    raise RuntimeError(
                        "BROWSER_AUTOMATION_FAILED: DevTools localhost/websocket connection failed: "
                        f"{exc}"
                    ) from exc

                next_id = 0
                browser_errors = []

                def command(method, params=None):
                    nonlocal next_id
                    next_id += 1
                    request_id = next_id
                    try:
                        websocket.send(json.dumps({
                            "id": request_id, "method": method, "params": params or {},
                        }))
                        while True:
                            response = json.loads(websocket.recv(timeout=5))
                            if response.get("id") == request_id:
                                if "error" in response:
                                    raise RuntimeError(response["error"])
                                return response.get("result", {})
                            if (response.get("method") == "Runtime.exceptionThrown"
                                    or response.get("method") == "Log.entryAdded"
                                    and response.get("params", {}).get("entry", {}).get("level") == "error"):
                                browser_errors.append(response)
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

                def save_screenshot(name):
                    screenshot = command("Page.captureScreenshot", {
                        "format": "png", "fromSurface": True,
                        "captureBeyondViewport": False,
                    })
                    data = base64.b64decode(screenshot.get("data", ""))
                    self.assertGreater(len(data), 24, f"empty screenshot: {name}")
                    self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n",
                                     f"invalid PNG screenshot: {name}")
                    path = artifact_dir / name
                    path.write_bytes(data)
                    return path

                command("Runtime.enable")
                command("Log.enable")
                command("Page.enable")
                command("Page.navigate", {"url": (root / "index.html").as_uri()})
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    if evaluate("document.readyState === 'complete' && !!document.getElementById('gallery-viewer')"):
                        break
                    time.sleep(.05)
                self.assertTrue(evaluate("document.readyState === 'complete'"))
                self.assertEqual(evaluate("location.protocol"), "file:")
                self.assertEqual(evaluate("document.querySelectorAll('.gallery-viewer-trigger').length"), 2)
                alignment = json.loads(evaluate(
                    "JSON.stringify(Array.from(document.querySelectorAll('.image-story-item'), "
                    "item => ({id: item.dataset.elementId, image: "
                    "item.querySelector('.photograph img').alt, description: "
                    "item.querySelector('.image-description').dataset.descriptionFor, "
                    "text: item.querySelector('.image-description').innerText})))"))
                self.assertEqual([item["id"] for item in alignment], ["frame-1", "frame-2"])
                for index, item in enumerate(alignment, 1):
                    self.assertEqual(item["description"], item["id"])
                    self.assertIn(f"Frame {index}", item["image"])
                    self.assertIn(f"Description for frame {index}", item["text"])
                    self.assertIn(f"Second paragraph for frame {index}", item["text"])
                self.assertTrue(evaluate("document.querySelector('.photograph img').naturalWidth === 720"))

                command("Emulation.setDeviceMetricsOverride", {
                    "width": 1440, "height": 900, "deviceScaleFactor": 1,
                    "mobile": False,
                })
                evaluate("window.scrollTo(0, 0)")
                desktop_path = save_screenshot("gallery-desktop.png")

                evaluate("window.scrollTo(0, 420)")
                start_scroll = evaluate("window.scrollY")
                evaluate("document.querySelectorAll('.gallery-viewer-trigger')[0].click()")
                self.assertTrue(evaluate("document.getElementById('gallery-viewer').open"))
                self.assertEqual(evaluate("document.querySelector('.gallery-viewer__status').textContent"),
                                 "Image 1 of 2")
                self.assertTrue(evaluate("document.querySelector('[data-viewer-action=previous]').disabled"))
                desktop_viewer_path = save_screenshot("gallery-desktop-viewer.png")
                evaluate("document.querySelector('[data-viewer-action=zoom-in]').click()")
                self.assertEqual(evaluate("document.querySelector('.gallery-viewer__image').style.getPropertyValue('--gallery-viewer-zoom')"), "1.5")
                evaluate("document.dispatchEvent(new KeyboardEvent('keydown', {key:'ArrowRight', bubbles:true}))")
                self.assertEqual(evaluate("document.querySelector('.gallery-viewer__status').textContent"),
                                 "Image 2 of 2")
                evaluate("document.querySelector('[data-viewer-action=previous]').click()")
                self.assertEqual(evaluate("document.querySelector('.gallery-viewer__status').textContent"),
                                 "Image 1 of 2")
                evaluate("document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true}))")
                self.assertFalse(evaluate("document.getElementById('gallery-viewer').open"))
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    if evaluate("document.activeElement.matches('.gallery-viewer-trigger')"):
                        break
                    time.sleep(.02)
                self.assertTrue(evaluate("document.activeElement.matches('.gallery-viewer-trigger')"))
                self.assertEqual(evaluate("window.scrollY"), start_scroll)

                command("Emulation.setDeviceMetricsOverride", {
                    "width": 390, "height": 844, "deviceScaleFactor": 1,
                    "mobile": True,
                })
                self.assertTrue(evaluate("document.documentElement.scrollWidth <= window.innerWidth"))
                geometry = json.loads(evaluate(
                    "JSON.stringify((() => { const image = document.querySelector('.photograph img'); "
                    "const rect = image.getBoundingClientRect(); return {width: rect.width, "
                    "height: rect.height, naturalWidth: image.naturalWidth, "
                    "scrollWidth: document.documentElement.scrollWidth}; })())"))
                self.assertGreater(geometry["width"], 0)
                self.assertAlmostEqual(geometry["width"] / geometry["height"], 1.5, places=2)
                self.assertLessEqual(geometry["scrollWidth"], 390)
                evaluate("window.scrollTo(0, 0)")
                mobile_path = save_screenshot("gallery-mobile.png")
                evaluate("document.querySelectorAll('.gallery-viewer-trigger')[1].click()")
                self.assertTrue(evaluate("document.getElementById('gallery-viewer').open"))
                self.assertTrue(evaluate("document.querySelector('.gallery-viewer__image').naturalWidth === 720"))
                self.assertEqual(evaluate("document.querySelector('.gallery-viewer__image').style.getPropertyValue('--gallery-viewer-zoom')"), "1")
                mobile_viewer_path = save_screenshot("gallery-mobile-viewer.png")
                evaluate("document.querySelector('[data-viewer-action=close]').click()")
                self.assertFalse(evaluate("document.getElementById('gallery-viewer').open"))
                evaluate("0")
                self.assertEqual(browser_errors, [], browser_errors)
                print(f"BROWSER_SCREENSHOT_DESKTOP={desktop_path}")
                print(f"BROWSER_SCREENSHOT_DESKTOP_VIEWER={desktop_viewer_path}")
                print(f"BROWSER_SCREENSHOT_MOBILE={mobile_path}")
                print(f"BROWSER_SCREENSHOT_MOBILE_VIEWER={mobile_viewer_path}")
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


if __name__ == "__main__":
    unittest.main()
