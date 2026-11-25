"""Run focused gallery regressions and classify real-browser verification."""

from __future__ import annotations

import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_SCREENSHOTS = (
    "gallery-modern-hero-desktop.png",
    "gallery-modern-hero-mobile.png",
    "gallery-modern-hero-1920x1080.png",
    "gallery-modern-hero-1440x900.png",
    "gallery-modern-hero-800x900.png",
    "gallery-modern-hero-799x900.png",
    "gallery-modern-hero-801x900.png",
    "gallery-modern-hero-820x900.png",
    "gallery-modern-hero-834x900.png",
    "gallery-modern-hero-900x900.png",
    "gallery-modern-hero-940x900.png",
    "gallery-modern-hero-955x900.png",
    "gallery-modern-hero-956x900.png",
    "gallery-modern-hero-1024x900.png",
    "gallery-modern-hero-768x1024.png",
    "gallery-modern-hero-390x844.png",
    "gallery-modern-hero-375x812.png",
    "gallery-modern-portrait-desktop.png",
    "gallery-modern-portrait-mobile.png",
    "gallery-modern-widescreen-desktop.png",
    "gallery-modern-widescreen-mobile.png",
    "viewer-fit-portrait-desktop.png",
    "viewer-fit-portrait-mobile.png",
    "viewer-zoom-2x-desktop.png",
    "viewer-zoom-2x-mobile.png",
    "viewer-zoom-2x-right-bottom-desktop.png",
    "viewer-zoom-2x-right-bottom-mobile.png",
    "simple-dark-contrast-desktop.png",
    "simple-dark-contrast-mobile.png",
)


def classify_browser_result(returncode: int, output: str) -> str:
    """Return an explicit result category; dependency skips never count as pass."""
    if "DEPENDENCY_MISSING:" in output or "skipped=" in output:
        return "INCOMPLETE_DEPENDENCY"
    if "BROWSER_STARTUP_BLOCKED:" in output:
        return "ENVIRONMENT_BLOCKED"
    if "BROWSER_AUTOMATION_FAILED:" in output:
        return "AUTOMATION_FAILED"
    if returncode == 0 and "Ran " in output and "\nOK" in output:
        return "PASSED"
    if returncode != 0 and ("FAIL:" in output or "AssertionError" in output):
        return "PRODUCT_FAILED"
    return "INCOMPLETE"


def validate_screenshot(path: Path) -> str | None:
    """Return a failure reason unless path contains a non-empty PNG image."""
    if not path.is_file():
        return "missing"
    try:
        data = path.read_bytes()
    except OSError as exc:
        return f"unreadable ({exc})"
    if len(data) < 24:
        return "empty or truncated"
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return "invalid PNG header"
    width, height = struct.unpack(">II", data[16:24])
    if width == 0 or height == 0:
        return "invalid PNG dimensions"
    return None


def _run(label: str, command: list[str], env: dict[str, str]) -> tuple[int, str]:
    print(f"\n=== {label} ===", flush=True)
    print("$ " + " ".join(command), flush=True)
    completed = subprocess.run(
        command, cwd=ROOT, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, check=False,
    )
    output = completed.stdout
    print(output, end="" if output.endswith("\n") else "\n", flush=True)
    print(f"Exit status: {completed.returncode}", flush=True)
    return completed.returncode, output


def main() -> int:
    artifact_dir = Path(tempfile.mkdtemp(prefix="kim-gallery-browser-artifacts-"))
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(ROOT / "tests"), env.get("PYTHONPATH", "")) if item)
    env["KIM_GALLERY_BROWSER_ARTIFACT_DIR"] = str(artifact_dir)
    python = sys.executable
    regressions = [
        python, "-m", "unittest", "tests.test_story_publication",
        "tests.test_photo_story", "tests.test_photo_preview_requests",
        "tests.test_gallery_viewer_script", "tests.test_gallery_browser_verification_runner",
        "-v",
    ]
    browser = [python, "-m", "unittest", "tests.test_gallery_viewer_browser",
               "tests.test_gallery_visual_qa_browser", "-v"]

    regression_code, _ = _run("Gallery regression tests", regressions, env)
    browser_code, browser_output = _run("Real Chrome browser verification", browser, env)
    browser_result = classify_browser_result(browser_code, browser_output)
    print(f"\nBrowser result: {browser_result}")
    print(f"Screenshot directory: {artifact_dir}")
    screenshots_ok = True
    for name in REQUIRED_SCREENSHOTS:
        screenshot = artifact_dir / name
        problem = validate_screenshot(screenshot)
        if problem:
            screenshots_ok = False
            print(f"Screenshot INVALID ({problem}): {screenshot}")
        else:
            print(f"Screenshot captured: {screenshot}")

    if regression_code != 0 or browser_result != "PASSED" or not screenshots_ok:
        print("Overall result: INCOMPLETE or FAILED. Do not report browser verification as passed.")
        return 1
    print("Overall result: PASSED. Focused regressions and browser verification completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
