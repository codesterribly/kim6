#!/usr/bin/env python3
"""Prepare and track safe, human-run KIM6 Dolphin acceptance cases."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any

QA_DIR = Path(__file__).resolve().parent
ROOT = QA_DIR.parent
GENERATED = QA_DIR / "generated"
STATE_DIR = QA_DIR / "state"
REPORT_DIR = QA_DIR / "reports"
PLAN_PATH = QA_DIR / "ACCEPTANCE_PLAN.md"
OWNER_TEXT = "KIM6 human acceptance workspace v1\n"
STATE_VERSION = 1
MENU_TITLES = {
    "kim_compress.desktop.in": "JPEG compression",
    "kim_compressandresize.desktop.in": "Resize, web export and email",
    "kim_convertandrotate.desktop.in": "Convert, rotate and flip",
    "kim_compressandresizevideo.desktop.in": "Video tools",
    "kim_publication.desktop.in": "Publish and organize",
}

class InventoryError(RuntimeError):
    pass

class SafetyError(RuntimeError):
    pass

class ValidationResult:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks: list[str] = []

    def as_dict(self) -> dict[str, list[str]]:
        return {"errors": self.errors, "warnings": self.warnings, "checks": self.checks}


def parse_menu(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    main: dict[str, str] = {}
    actions: dict[str, dict[str, str]] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if section == "Desktop Entry":
            main[key] = value
        elif section.startswith("Desktop Action "):
            action_id = section[len("Desktop Action "):]
            actions.setdefault(action_id, {})[key] = value
    declared = [item for item in main.get("Actions", "").split(";") if item]
    duplicates = sorted({item for item in declared if declared.count(item) > 1})
    if duplicates:
        raise InventoryError(f"{path.name}: duplicate action ID(s): {', '.join(duplicates)}")
    undeclared = sorted(set(actions) - set(declared))
    missing = sorted(set(declared) - set(actions))
    if undeclared or missing:
        raise InventoryError(f"{path.name}: action section mismatch; missing={missing}, undeclared={undeclared}")
    result = []
    for action_id in declared:
        fields = actions[action_id]
        label = fields.get("_Name", fields.get("Name", ""))
        command = fields.get("Exec", "")
        try:
            words = shlex.split(command)
        except ValueError as error:
            raise InventoryError(f"{path.name}/{action_id}: malformed Exec: {error}") from error
        if not words or words[0] != "kim_all":
            raise InventoryError(f"{path.name}/{action_id}: expected kim_all Exec, got {command!r}")
        if len(words) < 2:
            raise InventoryError(f"{path.name}/{action_id}: missing dispatcher command")
        result.append({
            "menu": path.name,
            "menu_title": MENU_TITLES.get(path.name, main.get("Name", path.stem)),
            "submenu": main.get("_X-KDE-Submenu", main.get("X-KDE-Submenu", main.get("Name", path.stem))),
            "action_id": action_id,
            "label": label,
            "exec": command,
            "dispatcher": words[1:],
            "mime": main.get("MimeType", ""),
        })
    return result


def _desktop_sections(text: str) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    main: dict[str, str] = {}
    actions: dict[str, dict[str, str]] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if section == "Desktop Entry":
            main[key] = value
        elif section.startswith("Desktop Action "):
            actions.setdefault(section[len("Desktop Action "):], {})[key] = value
    return main, actions


def _route_and_args(entry: dict[str, Any]) -> tuple[str, list[str]]:
    return entry["dispatcher"][0], entry["dispatcher"][1:]


def _fixture_class(route: str, args: list[str], action_id: str, menu: str = "") -> list[str]:
    if route in {"about", "license", "manual"}:
        # The dispatcher takes no media argument, but a right-click context
        # menu needs a harmless selected file to expose its informational item.
        return ["video-audio.mp4"] if "video" in menu else ["photo.jpg"]
    if route in {"video", "videoframes", "videoaudio", "videogif"}:
        if route == "video" and action_id in {"Videohd72017264mp4", "Av1hd720Balanced"}:
            return ["video-silent.mp4"]
        if route == "videoaudio" and ("mute" in action_id.lower() or action_id == "ExtractVideoAudio"):
            return ["video-multiaudio.mkv"]
        return ["video-audio.mp4"]
    if route in {"album", "print", "contactsheet", "tiffjoin", "animate", "pelemele", "slideshow", "gallery"}:
        return ["sequence-red.png", "sequence-green.png", "sequence-blue.png"]
    if route == "rename":
        return ["dated-photo.jpg", "sequence-red.png", "-leading ü [1].jpg"]
    if route in {"copyright", "timeshift", "datesync", "stripmeta"}:
        return ["metadata.jpg"]
    if route == "rotate" and "exif" in action_id.lower():
        return ["orientation-6.jpg"]
    if route == "convert":
        if "GIF" in action_id:
            return ["animated.gif"]
        if action_id == "ConvertJPG":
            return ["orientation-6.jpg"]
        if action_id == "ConvertPNG":
            return ["transparent.png"]
        if action_id in {"ConvertAVIF", "ConvertHEIC", "ConvertJXL", "ConvertJP2Lossless", "ConvertJP2Lossy"}:
            return ["profile-wide.jpg"]
        if action_id == "ConvertPDF":
            return ["photo.tif"]
        return ["photo.png"] if "JPG" in action_id else ["photo.jpg"]
    if route == "resizeandsend":
        return ["photo.jpg", "wide.jpg"]
    if route == "webexport":
        return ["profile-wide.jpg"]
    if route == "resize":
        return ["large.jpg", "unicode photo ü [1].jpg"] if action_id == "ResizePercent" else ["large.jpg"]
    if route in {"compress", "rotate", "flipflop"}:
        return ["-leading ü [1].jpg"] if action_id == "CompressCustom" else ["photo.jpg"]
    return ["photo.png"]


def _source_behavior(route: str) -> str:
    if route in {"about", "license", "manual"}:
        return "none"
    if route in {"rotate", "rotatewithexif", "flipflop"}:
        return "in_place"
    if route == "rename":
        return "rename"
    if route in {"webexport", "resizeandsend", "videoframes", "videoaudio", "videogif", "slideshow",
                 "gallery", "pelemele", "album", "print", "contactsheet", "tiffjoin", "animate"}:
        return "derived"
    return "authorized_overwrite"


def _expected(route: str, args: list[str]) -> str:
    if route in {"about", "license", "manual"}:
        return {"about": "KDialog About text opens.", "license": "Installed LICENSE.md opens.",
                "manual": "Installed docs/index.html and its stylesheet open."}[route]
    targets = {
        "compress": "A validated JPEG beside the selected image, tagged _compressed (or configured prefix), collision numbered.",
        "convert": "A validated output in the selected target format, in the case directory; choose it in the save dialog.",
        "resize": "A validated resized image beside the source, tagged _resized; percentage/preset geometry is visible in dimensions.",
        "webexport": "A distinct validated derivative in the selected export directory; never the original.",
        "resizeandsend": "A mail draft with only prepared image attachments; attachment storage is isolated under this QA workspace when using its isolated Dolphin session.",
        "rotate": "The selected disposable copy is transformed in place after validation.",
        "rotatewithexif": "The selected orientation-tagged disposable copy is auto-oriented in place.",
        "flipflop": "The selected disposable copy is flipped/flopped in place after validation.",
        "stripmeta": "A validated stripped derivative or authorized replacement; use the requested metadata scope.",
        "copyright": "A validated image with selected rights fields, or a numbered derivative.",
        "timeshift": "A validated image with shifted camera date tags, or a numbered derivative.",
        "datesync": "Filesystem mtime or EXIF dates match the chosen direction; use the source copy in this case.",
        "rename": "The renamed/moved test files are in the case directory; originals remain in this disposable case when create mode is selected.",
        "album": "A multi-page PDF in the chosen case directory.",
        "print": "A print-layout PDF in the chosen case directory.",
        "contactsheet": "A printable PDF contact sheet with the selected grid, labels and page size.",
        "gallery": "A complete gallery directory containing index.html, main images and thumbnails.",
        "pelemele": "A validated collage image in the chosen case directory.",
        "tiffjoin": "A multi-page TIFF in the chosen case directory, in selection order.",
        "animate": "An animated GIF in the chosen case directory, with the selected delay and loop behavior.",
        "video": "A validated encoded video in the case directory, with the selected codec/container preset.",
        "videoframes": "One extracted frame, thumbnail or labeled contact sheet in the case directory.",
        "videoaudio": "An extracted audio file or muted derived video in the case directory.",
        "videogif": "A validated animated GIF for the chosen video interval in the case directory.",
        "slideshow": "A silent H.264 MP4 in the chosen case directory, with slides in natural filename order.",
    }
    return targets.get(route, "A validated result in this case directory; follow the action's destination prompt.")


def _dependencies(route: str) -> list[str]:
    deps = {"about": ["kdialog"], "license": ["xdg-open"], "manual": ["xdg-open"],
            "compress": ["magick", "identify", "qdbus", "kdialog"],
            "convert": ["magick", "identify", "qdbus", "kdialog"],
            "resize": ["magick", "identify", "exiftool", "qdbus", "kdialog"],
            "webexport": ["magick", "identify", "exiftool", "qdbus", "kdialog"],
            "resizeandsend": ["magick", "identify", "qdbus", "kdialog", "optional mail client"],
            "stripmeta": ["exiftool", "magick", "identify", "qdbus", "kdialog"],
            "copyright": ["exiftool", "magick", "identify", "qdbus", "kdialog"],
            "timeshift": ["exiftool", "magick", "identify", "qdbus", "kdialog"],
            "datesync": ["exiftool", "magick", "qdbus", "kdialog"],
            "rename": ["qdbus", "kdialog", "optional exiftool for EXIF-date mode"],
            "gallery": ["magick", "identify", "qdbus", "kdialog", "optional xdg-open"],
            "pelemele": ["magick", "identify", "qdbus", "kdialog"],
            "album": ["magick", "identify", "qdbus", "kdialog", "PDF delegate"],
            "print": ["magick", "identify", "qdbus", "kdialog", "PDF delegate"],
            "contactsheet": ["magick", "identify", "qdbus", "kdialog", "PDF delegate"],
            "tiffjoin": ["magick", "identify", "qdbus", "kdialog"],
            "animate": ["magick", "identify", "qdbus", "kdialog"],
            "video": ["ffmpeg", "ffprobe", "qdbus", "kdialog", "selected optional encoder"],
            "videoframes": ["ffmpeg", "ffprobe", "magick for contact sheets", "qdbus", "kdialog"],
            "videoaudio": ["ffmpeg", "ffprobe", "qdbus", "kdialog", "audio encoder as requested"],
            "videogif": ["ffmpeg", "ffprobe", "qdbus", "kdialog"],
            "slideshow": ["ffmpeg", "ffprobe", "magick", "identify", "libx264", "qdbus", "kdialog"]}
    if route in {"rotate", "rotatewithexif", "flipflop"}:
        return ["magick", "identify", "exiftool", "qdbus", "kdialog"]
    return deps.get(route, ["see action help"])


def _checks(route: str) -> list[str]:
    checks = {
        "about": ["Dialog is legible and identifies KIM6."],
        "license": ["Opened document is the installed GPL license."],
        "manual": ["Manual renders and stylesheet loads."],
        "compress": ["JPEG bytes decode; actual format and dimensions are valid; source is unchanged in create mode."],
        "convert": ["Actual format matches selected format; decode succeeds; frame count is not silently lost."],
        "resize": ["Decode, actual format, frame count and dimensions are plausible for chosen geometry."],
        "webexport": ["Actual output format, dimensions and profile are checked; source remains byte-identical."],
        "resizeandsend": ["Draft contains only prepared files with valid formats; source hashes remain unchanged."],
        "rotate": ["Decode, dimensions, frame count and source replacement are checked; visually confirm direction."],
        "rotatewithexif": ["Orientation dimensions/pixels are normalized and EXIF orientation is no longer misleading."],
        "flipflop": ["Decode and dimensions are valid; compare asymmetric shapes to confirm axis."],
        "stripmeta": ["Decode, pixel/frame integrity and requested tag scope are checked."],
        "copyright": ["Creator/copyright fields read back; unrelated metadata and pixels remain."],
        "timeshift": ["Selected camera date tags read back with expected offset; filesystem mtime unchanged."],
        "datesync": ["Compare EXIF date and filesystem mtime in the selected direction."],
        "rename": ["Each selected byte hash appears under the expected new name; no unrelated entry is lost."],
        "album": ["Automated: pdfinfo can read the PDF and reports a positive page count and physical page size. Human: compare page count, image order and layout to the selected options."],
        "print": ["Automated: pdfinfo can read the PDF and reports a positive page count and physical page size. Human: compare page orientation and print layout to the chosen options."],
        "contactsheet": ["Automated: pdfinfo reports readable pages and correct physical size. Human: inspect image order, number/filename labels, grid and pagination."],
        "gallery": ["index.html and all relative image/thumbnail references exist."],
        "pelemele": ["Image decodes and selected tile ordering/layout is visible."],
        "tiffjoin": ["Automated: TIFF fully decodes and page count matches selected input frame count. Human: inspect page order."],
        "animate": ["Automated: GIF fully decodes and frame count matches selected input frame count. Human: inspect frame order, delay and loop behavior."],
        "video": ["ffprobe confirms container, requested codec and size bounds; full decode and approximate source-duration preservation are checked. Review audio stream mapping and visual quality."],
        "videoframes": ["Automated: output image fully decodes and observed dimensions/frame count are reported. Human: check requested timestamp and contact-sheet labels."],
        "videoaudio": ["ffprobe confirms audio codec/container and stream count, or confirms no audio after mute; full decode and approximate duration are checked."],
        "videogif": ["Automated: GIF fully decodes, has at least two frames, and observed dimensions are reported. Human: inspect timing and loop behavior."],
        "slideshow": ["Automated: ffprobe confirms H.264 MP4, observed dimensions, selected frame rate, approximate duration, frame count when reported, no audio, and full decode. Human: compare image order and dimensions to the interactive choices."],
    }
    return checks.get(route, ["Use the action-specific technical and visual checks in this case."])


def _interactive_choices(route: str, args: list[str], label: str) -> list[str]:
    choices: dict[str, list[str]] = {
        "compress": ["Custom quality when the menu entry is custom.", "Create or overwrite policy when not fixed by KIM_POLICY."],
        "resize": ["Custom geometry or percentage where requested.", "Create or overwrite policy when not fixed by KIM_POLICY."],
        "webexport": ["Export destination and configured output format/color policy.", "Never overwrites selected sources."],
        "resizeandsend": ["Email size is fixed by the preset; the action chooses a supported mail client or persistent fallback."],
        "convert": ["Custom format for the custom entry; destination and create/overwrite prompts as provided by the action."],
        "rotate": ["Custom angle for the custom entry; output policy follows the in-place action dialog."],
        "flipflop": ["Confirm the horizontal/vertical direction shown in the visible label."],
        "stripmeta": ["Metadata scope, and create/overwrite policy when supported by the selected mode."],
        "copyright": ["Choose creator, notice and/or usage-rights fields; blank fields are left unchanged."],
        "timeshift": ["Choose offset direction and the camera timestamp fields to shift."],
        "datesync": ["Choose EXIF-to-filesystem or filesystem-to-EXIF; file-to-EXIF also asks which date tags to update."],
        "rename": ["Choose naming mode, sequence/base or EXIF date format, destination, and conflict behavior as prompted."],
        "album": ["Choose an album layout and output filename; this action does not prompt for a title."],
        "print": ["Choose one of the supported print layouts and page settings."],
        "contactsheet": ["Choose page size/orientation, grid, labels, image fit, background, resolution and title."],
        "gallery": ["Enter gallery title/author and layout/output options."],
        "pelemele": ["Choose canvas/image size, layout, background, border, spacing/overlap and rotation/shadow options."],
        "tiffjoin": ["Choose the output location/name; selected order is used."],
        "animate": ["Choose frame delay and animation settings."],
        "video": ["Create or overwrite mode when asked."],
        "videoframes": ["Timestamp or contact-sheet grid only for interactive entries; format is fixed by the menu preset."],
        "videoaudio": ["Audio format only for the extract entry; mute has no format dialog."],
        "videogif": ["Choose interval, frame rate, width and loop behavior."],
        "slideshow": ["Choose slide duration, frame size/rate, background and ordering options."],
    }
    selected = list(choices.get(route, []))
    if route == "video":
        codec = _arg_value(args, "--codec")
        quality = _arg_value(args, "--av1-quality")
        if codec == "av1" and quality == "custom":
            selected = ["Enter an AV1 CRF and speed preset when prompted; defaults are CRF 30 and speed 7.",
                        "Create or overwrite mode when asked."]
        elif codec == "av1":
            selected = [f"Use the AV1 {quality} quality preset.", "Create or overwrite mode when asked."]
    if route in {"about", "license", "manual"}:
        selected = ["No processing dialog; open the informational resource and close it."]
    if "…" not in label and route in {"compress", "resize", "rotate"}:
        selected = [choice for choice in selected if not choice.startswith("Custom") and not choice.startswith("Custom geometry") and not choice.startswith("Custom angle")]
    return selected or ["No additional menu-specific input; confirm the operation shown in the label."]


def load_cases(repo: Path = ROOT) -> list[dict[str, Any]]:
    menu_paths = sorted((repo / "src").glob("kim_*.desktop.in"))
    if len(menu_paths) != 5:
        raise InventoryError(f"Expected five service menus, found {len(menu_paths)}")
    cases = []
    seen_ids: set[str] = set()
    seen_menu_actions: set[tuple[str, str]] = set()
    for menu in menu_paths:
        for entry in parse_menu(menu):
            case_id = f"{menu.stem}:{entry['action_id']}"
            if case_id in seen_ids or (menu.name, entry["action_id"]) in seen_menu_actions:
                raise InventoryError(f"duplicate acceptance case {case_id}")
            seen_ids.add(case_id)
            seen_menu_actions.add((menu.name, entry["action_id"]))
            route, args = _route_and_args(entry)
            behavior = _source_behavior(route)
            fixtures = _fixture_class(route, args, entry["action_id"], menu.name)
            cases.append({
                **entry,
                "id": case_id,
                "route": route,
                "args": args,
                "fixtures": fixtures,
                "source_behavior": behavior,
                "dependencies": _dependencies(route),
                "expected": _expected(route, args),
                "interactive": ("…" in entry["label"] or any("interactive" in arg or "custom" in arg for arg in args)),
                "interactive_choices": _interactive_choices(route, args, entry["label"]),
                "technical_checks": _checks(route),
                "human_checks": _human_checks(route, entry["label"]),
            })
    return cases


def _human_checks(route: str, label: str) -> list[str]:
    base = [f"Check that the menu starts the operation named ‘{label}’."]
    if route in {"about", "license", "manual"}:
        return ["Confirm the expected informational resource opens, is readable, and can be closed."]
    if route in {"video", "videoframes", "videoaudio", "videogif", "slideshow"}:
        base += ["Play or open the result; check the requested motion, orientation, audio, timing and sequence. Automated checks cannot judge subjective quality."]
    elif route == "flipflop":
        base += ["Open the result beside its input and use the asymmetric colored shapes to confirm which axis changed."]
    elif route in {"compress", "resize", "convert", "webexport", "pelemele", "rotate", "rotatewithexif"}:
        base += ["Open the result beside its input; check framing, orientation and visible detail. Automated checks cannot judge subjective quality."]
    elif route in {"stripmeta", "copyright", "timeshift", "datesync"}:
        base += ["Open the result and confirm it still looks the same; compare the exact metadata/date fields requested in this case."]
    elif route == "rename":
        base += ["Check the resulting names and verify every selected image remains present; compare the names with the selected mode."]
    elif route in {"album", "print"}:
        base += ["Open the PDF and check page orientation, image order and layout; automated page counts do not judge layout quality."]
    elif route == "gallery":
        base += ["Open the gallery index in a browser, click a thumbnail and check the title, author and columns."]
    elif route == "tiffjoin":
        base += ["Open the TIFF as pages and check that red, green, then blue appear in that order."]
    elif route == "animate":
        base += ["Open the GIF in an animation-capable viewer and check red, green, blue order, delay and looping."]
    elif route == "resizeandsend":
        base += ["Check that the draft contains only the expected prepared images and do not send it."]
    else:
        base += ["Check that the result matches the expected behavior below."]
    return base


def render_plan(cases: list[dict[str, Any]]) -> str:
    lines = ["# KIM6 Human Acceptance Plan", "", f"Generated from the five current service-menu templates: **{len(cases)} menu actions**.",
             "", "Regenerate with `python3 qa/acceptance.py inventory`. Do not edit the action list by hand.",
             "Each case has a disposable input copy under `qa/generated/cases/`. Actions must be invoked manually in Dolphin; command execution is not equivalent to GUI acceptance.", ""]
    for menu in sorted({case["menu"] for case in cases}):
        group = [case for case in cases if case["menu"] == menu]
        lines += [f"## {MENU_TITLES.get(menu, menu)} (`{menu}`)", "", "| Case ID | Action ID | Visible label | Dispatcher command | Sources | Source policy |", "|---|---|---|---|---|---|"]
        for case in group:
            args = " ".join(case["dispatcher"])
            fixtures = ", ".join(case["fixtures"]) or "none"
            lines.append(f"| `{case['id']}` | `{case['action_id']}` | {case['label']} | `kim_all {args}` | {fixtures} | {case['source_behavior']} |")
        lines.append("")
        for case in group:
            lines += [f"### {case['label']} — `{case['id']}`", "",
                      f"- **Menu path:** {case['submenu']} → {case['label']}",
                      f"- **Dispatcher contract:** `{case['exec']}`",
                      f"- **Select for the Dolphin context menu:** {', '.join(case['fixtures']) if case['fixtures'] else 'No files.'}",
                      f"- **Files passed to dispatcher:** {'yes' if '%F' in case['exec'] or '%U' in case['exec'] else 'no (context file only)'}",
                      f"- **Interactive choices:** {'; '.join(case['interactive_choices'])}",
                      f"- **Suggested choices:** {_case_guidance(case)[0]}",
                      f"- **Expected:** {_case_guidance(case)[1]}",
                      f"- **Source behavior:** `{case['source_behavior']}`. Inputs are case-local disposable copies.",
                      f"- **Dependencies:** {', '.join(case['dependencies'])}",
                      f"- **Technical validation:** {' '.join(case['technical_checks'])}",
                      f"- **Human inspection:** {' '.join(case['human_checks'])}", ""]
    lines += ["## Status meanings", "", "The CLI result log separates **GUI verified**, **CLI verified**, **GUI blocked by KDE**, and **Not tested**. Only a person invoking a menu in Dolphin can record GUI verification. `validate` performs technical checks only.", ""]
    return "\n".join(lines)


def write_plan(repo: Path, cases: list[dict[str, Any]]) -> Path:
    path = repo / "qa" / "ACCEPTANCE_PLAN.md"
    content = render_plan(cases)
    if path.is_symlink():
        raise SafetyError(f"refusing symlink acceptance plan: {path}")
    if path.exists():
        previous = path.read_text(encoding="utf-8")
        if previous != content and not previous.startswith("# KIM6 Human Acceptance Plan\n\nGenerated from the five current service-menu templates:"):
            raise SafetyError(f"refusing to overwrite an unrecognized plan file: {path}")
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        _write_atomic_text(path, content, 0o644)
    return path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _reject_symlink_components(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for component in absolute.parts[1:]:
        current = current / component
        if current.is_symlink():
            raise SafetyError(f"refusing symlink path component: {current}")


def _write_exclusive(path: Path, data: str, mode: int = 0o600) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _write_atomic_text(path: Path, data: str, mode: int = 0o600) -> None:
    _reject_symlink_components(path.absolute())
    if path.is_symlink():
        raise SafetyError(f"refusing symlink file: {path}")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        _fsync_dir(path.parent)
    finally:
        if temp.exists():
            temp.unlink()


def _write_new_marker(path: Path, text: str) -> None:
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        _fsync_dir(path.parent)
    finally:
        if temp.exists():
            temp.unlink()


def _fsync_dir(path: Path) -> None:
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def claim_workspace(path: Path) -> Path:
    path = path.absolute()
    _reject_symlink_components(path)
    if path.exists():
        if not path.is_dir():
            raise SafetyError(f"workspace path is not a directory: {path}")
        marker = path / ".kim6-acceptance-owner"
        if marker.is_symlink() or not marker.is_file() or marker.read_text(encoding="utf-8") != OWNER_TEXT:
            raise SafetyError(f"existing workspace is not positively owned by KIM6 QA: {path}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        return claim_workspace(path)
    try:
        _write_exclusive(path / ".kim6-acceptance-owner", OWNER_TEXT)
        _fsync_dir(path.parent)
    except Exception:
        marker = path / ".kim6-acceptance-owner"
        if marker.exists() and not marker.is_symlink(): marker.unlink()
        try: path.rmdir()
        except OSError: pass
        raise
    return path


def assert_workspace(path: Path) -> Path:
    path = path.absolute()
    _reject_symlink_components(path)
    marker = path / ".kim6-acceptance-owner"
    if not path.is_dir() or marker.is_symlink() or not marker.is_file() or marker.read_text(encoding="utf-8") != OWNER_TEXT:
        raise SafetyError(f"acceptance workspace is missing or not owned by KIM6 QA: {path}; run prepare first")
    case_root = path / "cases"
    case_marker = case_root / ".kim6-acceptance-owner"
    if case_root.is_symlink() or not case_root.is_dir() or case_marker.is_symlink() or not case_marker.is_file() or case_marker.read_text(encoding="utf-8") != OWNER_TEXT:
        raise SafetyError(f"acceptance case directory is missing or not owned: {case_root}")
    return path


def assert_case_directory(workspace: Path, case_id: str) -> Path:
    assert_workspace(workspace)
    safe_id = re.sub(r"[^A-Za-z0-9_.:-]", "_", case_id)
    target = workspace / "cases" / safe_id
    _reject_symlink_components(target)
    marker = target / ".kim6-case-owner"
    if target.is_symlink() or not target.is_dir() or marker.is_symlink() or not marker.is_file() or marker.read_text(encoding="utf-8") != case_id + "\n":
        raise SafetyError(f"case directory is missing or not owned by {case_id}: {target}")
    return target


def assert_toolkit_path(path: Path, label: str) -> Path:
    path = Path(path)
    if ".." in path.parts:
        raise SafetyError(f"{label} must stay inside {QA_DIR}: parent traversal is not allowed")
    path = path.absolute()
    _reject_symlink_components(path)
    path = path.resolve(strict=False)
    try:
        path.relative_to(QA_DIR.resolve())
    except ValueError as error:
        raise SafetyError(f"{label} must stay inside {QA_DIR}: {path}") from error
    return path


def assert_owned_directory(path: Path, marker_name: str, marker_text: str) -> Path:
    path = path.absolute()
    _reject_symlink_components(path)
    marker = path / marker_name
    if not path.is_dir() or path.is_symlink() or marker.is_symlink() or not marker.is_file() or marker.read_text(encoding="utf-8") != marker_text:
        raise SafetyError(f"directory is not owned by this acceptance toolkit: {path}")
    return path


def create_owned_case_dir(workspace: Path, case_id: str) -> Path:
    workspace = workspace.absolute()
    root_marker = workspace / ".kim6-acceptance-owner"
    _reject_symlink_components(workspace)
    if not workspace.is_dir() or root_marker.is_symlink() or not root_marker.is_file() or root_marker.read_text(encoding="utf-8") != OWNER_TEXT:
        raise SafetyError(f"case creation requires a QA-owned workspace: {workspace}")
    case_root = workspace / "cases"
    if not case_root.exists():
        case_root.mkdir(mode=0o700)
        _write_exclusive(case_root / ".kim6-acceptance-owner", OWNER_TEXT)
    case_root_marker = case_root / ".kim6-acceptance-owner"
    if case_root.is_symlink() or case_root_marker.is_symlink() or not case_root_marker.is_file() or case_root_marker.read_text(encoding="utf-8") != OWNER_TEXT:
        raise SafetyError("cases directory is not QA-owned")
    safe_id = re.sub(r"[^A-Za-z0-9_.:-]", "_", case_id)
    destination = case_root / safe_id
    _reject_symlink_components(destination)
    if destination.exists():
        marker = destination / ".kim6-case-owner"
        if destination.is_symlink() or not marker.is_file() or marker.read_text(encoding="utf-8") != case_id + "\n":
            raise SafetyError(f"existing case directory is not owned by this case: {destination}")
        return destination
    try:
        destination.mkdir(mode=0o700)
    except FileExistsError as error:
        raise SafetyError(f"case destination appeared during preparation: {destination}") from error
    try:
        _write_exclusive(destination / ".kim6-case-owner", case_id + "\n")
    except Exception:
        try: destination.rmdir()
        except OSError: pass
        raise
    return destination


def reset_case_dir(workspace: Path, case_id: str, allowed_names: set[str], required_files: set[str] | None = None) -> None:
    case_root = workspace / "cases"
    case_root_marker = case_root / ".kim6-acceptance-owner"
    if case_root.is_symlink() or case_root_marker.is_symlink() or not case_root_marker.is_file() or case_root_marker.read_text(encoding="utf-8") != OWNER_TEXT:
        raise SafetyError("cases directory is not QA-owned")
    safe_id = re.sub(r"[^A-Za-z0-9_.:-]", "_", case_id)
    target = case_root / safe_id
    _reject_symlink_components(target)
    if not target.is_dir() or target.is_symlink():
        raise SafetyError(f"case directory is missing or unsafe: {target}")
    marker = target / ".kim6-case-owner"
    if marker.is_symlink() or not marker.is_file() or marker.read_text(encoding="utf-8") != case_id + "\n":
        raise SafetyError(f"case ownership check failed: {target}")
    allowed = set(allowed_names) | {".kim6-case-owner", "case.json", "INSTRUCTIONS.txt"}
    actual = {str(p.relative_to(target)) for p in target.rglob("*")}
    unknown = actual - allowed
    if unknown:
        raise SafetyError(f"case contains untracked entries; validate first or inspect manually: {sorted(unknown)}")
    for name in required_files or set():
        fixture = target / name
        if fixture.is_symlink():
            raise SafetyError(f"refusing symlink in case fixture: {fixture}")
        if not fixture.is_file():
            raise SafetyError(f"case fixture is missing or is not a regular file: {fixture}")
    for entry in target.rglob("*"):
        if entry.is_symlink():
            raise SafetyError(f"refusing symlink in case output: {entry}")
        if not entry.is_file() and not entry.is_dir():
            raise SafetyError(f"refusing unusual case entry: {entry}")
    shutil.rmtree(target)
    _fsync_dir(case_root)


def default_state() -> dict[str, Any]:
    return {"version": STATE_VERSION, "current_case": None, "results": {}}


def load_state(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise SafetyError(f"refusing symlink state file: {path}")
    if not path.exists():
        return default_state()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != STATE_VERSION or not isinstance(data.get("results"), dict):
        raise SafetyError(f"unrecognized acceptance state file: {path}")
    return data


def save_state(path: Path, state: dict[str, Any]) -> None:
    _reject_symlink_components(path.parent)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise SafetyError(f"refusing symlink state file: {path}")
    state = {**state, "version": STATE_VERSION}
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        _fsync_dir(path.parent)
    finally:
        if temp.exists():
            temp.unlink()


def check_source_preservation(case: dict[str, Any], baseline: dict[str, str], current: dict[str, str], policy: str) -> ValidationResult:
    result = ValidationResult()
    behavior = case["source_behavior"]
    if behavior == "none":
        result.checks.append("No media source is selected.")
        return result
    missing = [name for name in baseline if name not in current]
    changed = [name for name, digest in baseline.items() if name in current and current[name] != digest]
    if behavior == "derived":
        if missing or changed:
            result.errors.append(f"Derived-only action changed or removed selected source(s): {missing + changed}")
        else:
            result.checks.append("Selected source hashes are unchanged.")
    elif behavior == "authorized_overwrite":
        if missing:
            result.errors.append(f"Selected source path(s) disappeared: {missing}")
        elif changed and policy != "overwrite":
            result.errors.append(f"Source changed without recorded overwrite authorization: {changed}")
        else:
            result.checks.append("Source state is consistent with the recorded create/overwrite choice.")
    elif behavior == "in_place":
        if missing or policy != "in-place":
            result.errors.append(f"In-place action requires its disposable source path and in-place policy: {missing}")
        else:
            result.checks.append("Only the disposable case copy was eligible for in-place transformation.")
    elif behavior == "rename":
        if not missing and not changed:
            result.errors.append("No selected file was renamed or otherwise changed.")
        else:
            result.checks.append("Rename case changed a selected disposable entry; verify all byte hashes at their new paths.")
    return result


def capability(name: str, available: bool, reason: str = "") -> dict[str, str]:
    return {"name": name, "status": "available" if available else "blocked", "reason": reason if not available else ""}


def result_totals(cases: list[dict[str, Any]], state: dict[str, Any]) -> dict[str, int]:
    result_rows = state.get("results", {})
    totals = {key: 0 for key in ("passed", "failed", "skipped", "blocked", "pending", "gui_verified", "cli_verified", "gui_blocked", "not_tested")}
    for case in cases:
        row = result_rows.get(case["id"], {})
        status = row.get("status", "pending")
        totals[status if status in {"passed", "failed", "skipped", "blocked"} else "pending"] += 1
        mode = row.get("mode", "")
        if status == "passed" and mode == "gui": totals["gui_verified"] += 1
        elif status == "passed" and mode == "cli": totals["cli_verified"] += 1
        elif status == "blocked" and row.get("mode") == "gui": totals["gui_blocked"] += 1
        else: totals["not_tested"] += 1
    return totals


def _run(argv: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        return subprocess.CompletedProcess(argv, 127, "", str(error))


def _image_info(path: Path) -> tuple[str, list[tuple[int, int]]]:
    identify = shutil.which("identify")
    magick = shutil.which("magick")
    if not identify or not magick:
        raise FileNotFoundError("ImageMagick identify/magick is unavailable")
    media_path = str(path.resolve(strict=True))
    decoded = _run([magick, media_path, "null:"], timeout=60)
    if decoded.returncode:
        raise ValueError(f"ImageMagick full decode failed: {decoded.stderr.strip()}")
    probe = _run([identify, "-regard-warnings", "-format", "%m|%w|%h\n", media_path], timeout=30)
    if probe.returncode:
        raise ValueError(f"identify failed: {probe.stderr.strip()}")
    formats: set[str] = set()
    dimensions = []
    for line in probe.stdout.splitlines():
        parts = line.split("|")
        if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
            raise ValueError(f"unexpected identify record: {line!r}")
        formats.add(parts[0].upper())
        dimensions.append((int(parts[1]), int(parts[2])))
    if not dimensions or len(formats) != 1:
        raise ValueError("empty image or inconsistent frame encodings")
    return next(iter(formats)), dimensions


def _video_info(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise FileNotFoundError("ffprobe is unavailable")
    media_path = str(path.resolve(strict=True))
    probe = _run([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", media_path], timeout=30)
    if probe.returncode:
        raise ValueError(f"ffprobe failed: {probe.stderr.strip()}")
    try:
        data = json.loads(probe.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("ffprobe returned invalid JSON") from error
    if not data.get("format", {}).get("format_name"):
        raise ValueError("output container is not identified")
    return data


def _media_duration(info: dict[str, Any]) -> float | None:
    value = info.get("format", {}).get("duration")
    try:
        duration = float(value)
    except (TypeError, ValueError):
        return None
    return duration if duration > 0 else None


def _rate_value(value: Any) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        numerator, denominator = value.split("/", 1)
        denominator_value = float(denominator)
        if denominator_value == 0:
            return None
        return float(numerator) / denominator_value
    except (ValueError, ZeroDivisionError):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


def _image_signature(path: Path) -> list[str]:
    identify = shutil.which("identify")
    if not identify:
        raise FileNotFoundError("ImageMagick identify is unavailable")
    proc = _run([identify, "-regard-warnings", "-format", "%#\\n", str(path.resolve(strict=True))], timeout=60)
    if proc.returncode:
        raise ValueError(f"image pixel signature failed: {proc.stderr.strip()}")
    signatures = [line for line in proc.stdout.splitlines() if line]
    if not signatures:
        raise ValueError("image has no pixel signature")
    return signatures


def _email_attachment_root(generated: Path) -> Path:
    return generated / "gui-data" / "kim6" / "email-attachments"


def _email_snapshot(generated: Path) -> list[str]:
    root = _email_attachment_root(generated)
    _reject_symlink_components(root)
    if root.is_symlink():
        raise SafetyError(f"refusing symlink email-attachment directory: {root}")
    if not root.exists():
        return []
    return sorted(path.name for path in root.iterdir() if path.is_dir() and not path.is_symlink())


def _exiftool_json(path: Path) -> dict[str, Any]:
    exiftool = shutil.which("exiftool")
    if not exiftool:
        raise FileNotFoundError("ExifTool is unavailable")
    proc = _run([exiftool, "-json", "-G1", "-s", "-GPS:all", "-DateTimeOriginal", "-CreateDate", "-ModifyDate",
                 "-SubSecTimeOriginal", "-OffsetTimeOriginal", "-Artist", "-Copyright", "-XMP-dc:Rights",
                 "-XMP-iptcExt:DigitalSourceType", "-XMP-iptcExt:AIPromptInformation",
                 "-XMP-iptcExt:AIPromptWriterName", str(path.resolve(strict=True))], timeout=30)
    if proc.returncode:
        raise ValueError(f"ExifTool metadata read failed: {proc.stderr.strip()}")
    try:
        records = json.loads(proc.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("ExifTool returned invalid JSON") from error
    return records[0] if records else {}


def _icc_digest(path: Path) -> str:
    exiftool = shutil.which("exiftool")
    if not exiftool:
        raise FileNotFoundError("ExifTool is unavailable for ICC verification")
    try:
        proc = subprocess.run([exiftool, "-b", "-ICC_Profile", str(path.resolve(strict=True))],
                              capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(f"ICC profile read failed: {error}") from error
    if proc.returncode:
        raise ValueError(f"ICC profile read failed: {proc.stderr.decode(errors='replace').strip()}")
    return hashlib.sha256(proc.stdout).hexdigest() if proc.stdout else ""


def _datetime_matches_file_mtime(path: Path, tags: dict[str, Any]) -> bool:
    values = {key.rsplit(":", 1)[-1]: value for key, value in tags.items()}
    capture = str(values.get("DateTimeOriginal", ""))
    if not re.match(r"^\d{4}:\d{2}:\d{2} \d{2}:\d{2}:\d{2}$", capture):
        return False
    wall = datetime.strptime(capture, "%Y:%m:%d %H:%M:%S")
    offset = str(values.get("OffsetTimeOriginal", ""))
    stat = path.stat()
    if offset in {"Z", "+00:00"}:
        zone = timezone.utc
        expected_seconds = int(wall.replace(tzinfo=zone).timestamp())
        if int(stat.st_mtime) != expected_seconds:
            return False
    elif re.fullmatch(r"[+-]\d{2}:\d{2}", offset):
        sign = 1 if offset[0] == "+" else -1
        hours, minutes = (int(part) for part in offset[1:].split(":"))
        zone = timezone(sign * timedelta(hours=hours, minutes=minutes))
        expected_seconds = int(wall.replace(tzinfo=zone).timestamp())
        if int(stat.st_mtime) != expected_seconds:
            return False
    else:
        file_clock = time.localtime(stat.st_mtime)
        if (wall.year, wall.month, wall.day, wall.hour, wall.minute, wall.second) != (
                file_clock.tm_year, file_clock.tm_mon, file_clock.tm_mday, file_clock.tm_hour, file_clock.tm_min, file_clock.tm_sec):
            return False
    fraction = str(values.get("SubSecTimeOriginal", ""))
    if fraction:
        digits = re.sub(r"\D", "", fraction)[:9].ljust(9, "0")
        if stat.st_mtime_ns % 1_000_000_000 != int(digits):
            return False
    return True


def _decode_video(path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError("ffmpeg is unavailable for full output decode")
    proc = _run([ffmpeg, "-hide_banner", "-v", "error", "-xerror", "-nostdin", "-i",
                 str(path.resolve(strict=True)), "-map", "0:v?", "-map", "0:a?", "-f", "null", "-"], timeout=180)
    if proc.returncode:
        raise ValueError(f"full FFmpeg decode failed: {proc.stderr.strip()}")


def validate_case_data(case: dict[str, Any], case_dir: Path, baseline: dict[str, str], policy: str = "create") -> dict[str, Any]:
    result = ValidationResult()
    external_outputs: list[dict[str, str]] = []
    record_path = case_dir / "case.json"
    if record_path.is_symlink():
        raise SafetyError(f"refusing symlink case metadata: {record_path}")
    case_record = json.loads(record_path.read_text(encoding="utf-8")) if record_path.is_file() else {}
    current = {}
    excluded = {".kim6-case-owner", "case.json", "INSTRUCTIONS.txt"}
    for path in case_dir.rglob("*"):
        relative = str(path.relative_to(case_dir))
        if path.is_symlink() and relative not in excluded:
            result.errors.append(f"Unexpected symlink in case output: {relative}")
        elif path.is_file() and relative not in excluded:
            current[relative] = sha256(path)
    source_result = check_source_preservation(case, baseline, current, policy)
    result.errors.extend(source_result.errors)
    result.checks.extend(source_result.checks)
    source_names = set(baseline)
    outputs = [case_dir / name for name in current if name not in source_names or (name in baseline and current[name] != baseline[name])]
    if case["route"] == "gallery":
        outputs.extend(path for path in case_dir.iterdir() if path.is_dir() and not path.is_symlink())
    route = case["route"]
    unavailable = case_record.get("unavailable_fixtures", [])
    if unavailable:
        result.errors.append("Required test media could not be generated: " + ", ".join(unavailable))
    if route in {"about", "license", "manual"}:
        result.checks.append("Informational action requires direct human confirmation; no media output is expected.")
    elif case["source_behavior"] == "in_place":
        if not outputs:
            result.errors.append("No selected disposable source changed; verify the operation was completed.")
    elif route == "resizeandsend":
        # Use the documented isolated XDG home, not the validator process's
        # ambient environment, which may be a different terminal session.
        generated_root = case_dir.parent.parent
        attachment_root = _email_attachment_root(generated_root)
        _reject_symlink_components(attachment_root)
        if attachment_root.is_symlink():
            raise SafetyError(f"refusing symlink email-attachment directory: {attachment_root}")
        snapshot = set(case_record.get("email_snapshot_dirs", []))
        attachments = [p for group in attachment_root.glob("attachments.*") if group.is_dir() and not group.is_symlink() and group.name not in snapshot
                       for p in group.iterdir() if p.is_file() and not p.is_symlink()] if attachment_root.exists() else []
        if attachments:
            for output in attachments:
                try:
                    _image_info(output)
                    result.checks.append(f"Email attachment fully decodes: {output.name}")
                    external_outputs.append({"path": str(output.relative_to(generated_root)), "sha256": sha256(output)})
                except FileNotFoundError as error: result.warnings.append(str(error))
                except ValueError as error: result.errors.append(f"{output.name}: {error}")
        elif case_record.get("external_outputs"):
            for item in case_record["external_outputs"]:
                relative = Path(item.get("path", ""))
                if relative.is_absolute() or ".." in relative.parts:
                    result.errors.append("Recorded email attachment path escapes the QA workspace.")
                    continue
                output = generated_root / relative
                if output.is_symlink() or not output.is_file() or sha256(output) != item.get("sha256"):
                    result.errors.append(f"Previously validated persistent email attachment changed or disappeared: {relative}")
                    continue
                try:
                    _image_info(output)
                    external_outputs.append(item)
                    result.checks.append(f"Persistent email attachment remains accessible: {output.name}")
                except (FileNotFoundError, ValueError) as error:
                    result.errors.append(f"{relative}: {error}")
        else:
            result.errors.append("No new prepared attachment was found; run this case using the isolated Dolphin session after `next` records its attachment baseline.")
    elif case["route"] == "datesync" and not outputs:
        if shutil.which("exiftool"):
            for name in baseline:
                source = case_dir / name
                try:
                    tags = _exiftool_json(source)
                    if not _datetime_matches_file_mtime(source, tags):
                        result.errors.append(f"Filesystem mtime does not match DateTimeOriginal: {name}")
                    else:
                        result.checks.append(f"Filesystem mtime matches DateTimeOriginal: {name}, with any embedded offset and subsecond field considered.")
                except (ValueError, OSError):
                    result.errors.append(f"Could not compare the EXIF and filesystem times: {name}")
        else:
            result.warnings.append("ExifTool unavailable; cannot inspect date synchronization.")
    elif case["source_behavior"] != "rename" and not outputs:
        result.errors.append("No new or changed result was found in the case directory; choose it in output dialogs.")
    if route == "rename":
        wanted = set(baseline.values())
        found = {sha256(path) for path in case_dir.rglob("*") if path.is_file() and str(path.relative_to(case_dir)) not in excluded}
        if not wanted.issubset(found):
            result.errors.append("One or more original fixture byte hashes are not present after rename.")
    for output in outputs:
        if output.is_dir():
            index = output / "index.html"
            if not index.is_file():
                result.errors.append(f"Gallery directory lacks index.html: {output.name}")
            else:
                text = index.read_text(encoding="utf-8", errors="replace")
                from urllib.parse import unquote, urlsplit
                for relative in re.findall(r'(?:src|href)=["\']([^"\']+)', text):
                    parsed = urlsplit(html.unescape(relative))
                    if parsed.scheme or parsed.netloc or relative.startswith("#"):
                        continue
                    asset = (output / unquote(parsed.path)).resolve()
                    if not asset.is_relative_to(output.resolve()):
                        result.errors.append(f"Gallery reference escapes its output directory: {relative}")
                    elif not asset.exists():
                        result.errors.append(f"Gallery references missing asset: {relative}")
                result.checks.append("Gallery index and relative assets exist.")
            continue
        suffix = output.suffix.lower()
        try:
            if suffix in {".jpg", ".jpeg", ".jpe", ".png", ".gif", ".tif", ".tiff", ".webp", ".avif", ".heic", ".heif", ".bmp", ".jp2", ".jxl", ".tga", ".ico", ".cur"}:
                actual_format, dimensions = _image_info(output)
                expected = {".jpg": "JPEG", ".jpeg": "JPEG", ".jpe": "JPEG", ".tif": "TIFF", ".tiff": "TIFF", ".avif": "HEIC"}.get(suffix, suffix[1:].upper())
                if actual_format not in {expected, "JPG" if expected == "JPEG" else expected}:
                    result.errors.append(f"{output.name}: extension suggests {expected}, decoded bytes are {actual_format}")
                result.checks.append(f"Image fully decoded: {output.name} ({actual_format}, {dimensions[0][0]}×{dimensions[0][1]}, {len(dimensions)} frame(s)).")
                source_info = case_record.get("baseline_image_info", {})
                expected_frame_total = sum(item.get("frames", 1) for item in source_info.values())
                if route in {"animate", "tiffjoin"} and expected_frame_total and len(dimensions) != expected_frame_total:
                    result.errors.append(f"{route} output frame/page count is {len(dimensions)}; expected {expected_frame_total} selected frames.")
                elif route in {"compress", "convert", "resize", "rotate", "flipflop", "webexport", "stripmeta", "copyright", "timeshift", "datesync"} and len(source_info) == 1:
                    expected_frames = next(iter(source_info.values())).get("frames")
                    if expected_frames and len(dimensions) != expected_frames:
                        result.errors.append(f"Output frame count changed from {expected_frames} to {len(dimensions)}: {output.name}")
                elif route == "videogif" and len(dimensions) < 2:
                    result.errors.append("Video-to-GIF result contains fewer than two frames.")
                if route == "resize" and "--size" in case["args"]:
                    try:
                        geometry = case["args"][case["args"].index("--size") + 1]
                        limit_width, limit_height = (int(part) for part in geometry.split("x", 1))
                        if dimensions[0][0] > limit_width or dimensions[0][1] > limit_height:
                            result.errors.append(f"Resize exceeds the requested {geometry} bounds: {output.name}")
                    except (ValueError, IndexError):
                        pass
                if route in {"stripmeta", "copyright", "timeshift", "datesync"}:
                    expected_signatures = [signature for signatures in case_record.get("baseline_pixel_signatures", {}).values() for signature in signatures]
                    if expected_signatures:
                        actual_signatures = _image_signature(output)
                        if actual_signatures not in [case_record.get("baseline_pixel_signatures", {}).get(name) for name in case_record.get("fixtures", [])]:
                            result.errors.append(f"Metadata/date operation changed decoded pixels: {output.name}")
                        else:
                            result.checks.append("Decoded pixels and frame order match the selected fixture.")
                    if shutil.which("exiftool"):
                        tags = _exiftool_json(output)
                        tag_names = {key.rsplit(":", 1)[-1] for key, value in tags.items() if value not in (None, "", [], {})}
                        if route == "stripmeta":
                            mode = "all"
                            try: mode = case["args"][case["args"].index("--mode") + 1]
                            except (ValueError, IndexError): pass
                            if mode in {"gps", "all"} and any(name.startswith("GPS") for name in tag_names):
                                result.errors.append(f"GPS tags remain after {mode} metadata removal: {output.name}")
                            if mode == "ai" and tag_names.intersection({"DigitalSourceType", "AIPromptInformation", "AIPromptWriterName"}):
                                result.errors.append(f"Recognized AI metadata remains: {output.name}")
                        elif route == "copyright" and not tag_names.intersection({"Artist", "Copyright", "Rights"}):
                            result.warnings.append(f"No standard creator/rights tag was found; review the selected fields: {output.name}")
                        elif route in {"timeshift", "datesync"} and "DateTimeOriginal" not in tag_names:
                            result.errors.append(f"Capture timestamp is missing: {output.name}")
                        if route == "datesync" and not _datetime_matches_file_mtime(output, tags):
                            result.errors.append(f"DateTimeOriginal and filesystem modification time do not agree: {output.name}")
                        if route in {"stripmeta", "copyright", "timeshift"}:
                            expected_icc = set(case_record.get("baseline_icc_sha256", {}).values())
                            if expected_icc:
                                actual_icc = _icc_digest(output)
                                if actual_icc not in expected_icc:
                                    result.errors.append(f"ICC profile was not preserved: {output.name}")
                                else:
                                    result.checks.append("ICC profile bytes match a selected source profile.")
                            source_by_name = next((name for name in case_record.get("fixtures", [])
                                                   if Path(name).stem in output.stem or output.stem in Path(name).stem), None)
                            if source_by_name and output != case_dir / source_by_name:
                                source_stat = case_record.get("baseline_mtime_ns", {}).get(source_by_name)
                                source_mode = case_record.get("baseline_mode", {}).get(source_by_name)
                                if source_stat is not None and output.stat().st_mtime_ns != source_stat:
                                    result.errors.append(f"Metadata-only derivative did not preserve source mtime: {output.name}")
                                if source_mode is not None and (output.stat().st_mode & 0o777) != source_mode:
                                    result.warnings.append(f"Output permissions differ from source: {output.name}")
                            elif output.name in case_record.get("baseline_mtime_ns", {}):
                                if route != "datesync" and output.stat().st_mtime_ns != case_record["baseline_mtime_ns"][output.name]:
                                    result.errors.append(f"Metadata-only replacement changed filesystem mtime: {output.name}")
            elif suffix in {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}:
                info = _video_info(output)
                _decode_video(output)
                streams = info.get("streams", [])
                types = [stream.get("codec_type") for stream in streams]
                source_video_info = case_record.get("baseline_video_info", {})
                source_info = next(iter(source_video_info.values()), {})
                source_duration = _media_duration(source_info)
                output_duration = _media_duration(info)
                if route in {"video", "videoaudio"} and source_duration is not None:
                    if output_duration is None or abs(output_duration - source_duration) > max(0.25, source_duration * 0.02):
                        result.errors.append(f"{output.name}: output duration differs from source by more than the 2%/250 ms tolerance.")
                    else:
                        result.checks.append(f"Duration approximately matches source ({source_duration:.3f}s → {output_duration:.3f}s).")
                if case["route"] == "videoaudio" and "mute" in case["action_id"].lower() and "audio" in types:
                    result.errors.append(f"{output.name}: muted output still contains audio.")
                if case["route"] == "videoaudio" and "mute" in case["action_id"].lower():
                    source_video = [stream.get("codec_name") for stream in source_info.get("streams", []) if stream.get("codec_type") == "video"]
                    output_video = [stream.get("codec_name") for stream in streams if stream.get("codec_type") == "video"]
                    if not source_video or output_video != source_video:
                        result.errors.append(f"{output.name}: mute operation did not preserve video stream codecs ({source_video} → {output_video}).")
                if case["route"] == "video":
                    args = case["args"]
                    codec = args[args.index("--codec") + 1] if "--codec" in args else ""
                    expected_codecs = {"libx264": {"h264"}, "libx265": {"hevc"}, "av1": {"av1"}}
                    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
                    actual_codecs = {stream.get("codec_name") for stream in video_streams}
                    if not video_streams or not actual_codecs.issubset(expected_codecs.get(codec, set())):
                        result.errors.append(f"Video codec does not match requested {codec}: {sorted(actual_codecs)}")
                    size = args[args.index("--size") + 1] if "--size" in args else ""
                    bounds = {"hd720": (1280, 720), "hd1080": (1920, 1080)}.get(size)
                    if bounds and video_streams and (int(video_streams[0].get("width", 0)) > bounds[0] or int(video_streams[0].get("height", 0)) > bounds[1]):
                        result.errors.append(f"Transcoded video exceeds the selected {size} bounds.")
                    if "--container" in args and args[args.index("--container") + 1] == "mp4" and "mp4" not in info["format"]["format_name"].split(","):
                        result.errors.append("Requested MP4 output did not probe as an MP4-family container.")
                    source_audio = [stream.get("codec_name") for stream in source_info.get("streams", []) if stream.get("codec_type") == "audio"]
                    output_audio = [stream.get("codec_name") for stream in streams if stream.get("codec_type") == "audio"]
                    if source_audio and (len(output_audio) != len(source_audio) or output_audio != source_audio):
                        result.warnings.append(f"Audio stream mapping differs from source; inspect container compatibility ({source_audio} → {output_audio}).")
                if case["route"] == "slideshow":
                    video_streams = [stream for stream in streams if stream.get("codec_type") == "video"]
                    if not video_streams or video_streams[0].get("codec_name") != "h264":
                        result.errors.append("Slideshow output is not H.264 video.")
                    if "audio" in types:
                        result.errors.append("Slideshow unexpectedly contains audio.")
                    if video_streams:
                        expected_fps = 25.0
                        expected_seconds = 3.0
                        if "--fps" in case["args"]:
                            try: expected_fps = float(case["args"][case["args"].index("--fps") + 1])
                            except (ValueError, IndexError): pass
                        if "--seconds-per-photo" in case["args"]:
                            try: expected_seconds = float(case["args"][case["args"].index("--seconds-per-photo") + 1])
                            except (ValueError, IndexError): pass
                        actual_fps = _rate_value(video_streams[0].get("avg_frame_rate") or video_streams[0].get("r_frame_rate"))
                        expected_frames = len(case_record.get("fixtures", [])) * expected_seconds * expected_fps
                        try: frame_count = int(video_streams[0].get("nb_read_frames", video_streams[0].get("nb_frames")))
                        except (TypeError, ValueError): frame_count = None
                        if actual_fps is None or abs(actual_fps - expected_fps) > 0.01:
                            result.errors.append(f"Slideshow frame rate is {actual_fps}; expected {expected_fps:g} fps.")
                        expected_duration = len(case_record.get("fixtures", [])) * expected_seconds
                        if output_duration is None or abs(output_duration - expected_duration) > 1 / expected_fps:
                            result.errors.append("Slideshow duration differs from image count × seconds per photo by more than one frame.")
                        if frame_count is not None and abs(frame_count - expected_frames) > max(1, len(case_record.get("fixtures", []))):
                            result.errors.append(f"Slideshow frame count {frame_count} differs from expected approximately {expected_frames:g}.")
                video_dimensions = [f"{stream.get('width')}×{stream.get('height')}" for stream in streams
                                    if stream.get("codec_type") == "video" and stream.get("width") and stream.get("height")]
                dimensions_text = ", ".join(video_dimensions) if video_dimensions else "video dimensions unavailable"
                result.checks.append(f"Video/container probed and fully decoded: {output.name} ({info['format']['format_name']}; {dimensions_text}; {', '.join(types) or 'no streams'}).")
            elif suffix == ".pdf":
                pdfinfo = shutil.which("pdfinfo")
                if pdfinfo:
                    info = _run([pdfinfo, str(output)])
                    if info.returncode:
                        result.errors.append(f"PDF inspection failed: {output.name}")
                    else:
                        page_line = next((line.strip() for line in info.stdout.splitlines() if line.startswith("Pages:")), "")
                        size_line = next((line.strip() for line in info.stdout.splitlines() if line.startswith("Page size:")), "")
                        page_match = re.search(r"Pages:\s+(\d+)", page_line)
                        if not page_match or int(page_match.group(1)) < 1:
                            result.errors.append(f"PDF has no readable pages: {output.name}")
                        else:
                            result.checks.append(f"PDF readable: {output.name}; {page_line}; {size_line or 'physical page size unavailable'}. Compare page order and layout visually.")
                else: result.warnings.append("pdfinfo unavailable; visually open the PDF.")
            elif suffix in {".m4a", ".mp3", ".flac", ".wav"}:
                info = _video_info(output)
                _decode_video(output)
                audio_streams = [stream for stream in info.get("streams", []) if stream.get("codec_type") == "audio"]
                if not audio_streams:
                    result.errors.append(f"Audio output has no audio stream: {output.name}")
                if len(audio_streams) != 1:
                    result.errors.append(f"Audio output should contain exactly one selected stream; found {len(audio_streams)}.")
                if any(stream.get("codec_type") == "video" for stream in info.get("streams", [])):
                    result.errors.append(f"Unexpected video stream in audio output: {output.name}")
                expected_audio = {".m4a": {"aac"}, ".mp3": {"mp3"}, ".flac": {"flac"}, ".wav": {"pcm_s16le", "pcm_s24le", "pcm_s32le", "pcm_f32le"}}
                actual_audio = {stream.get("codec_name") for stream in info.get("streams", []) if stream.get("codec_type") == "audio"}
                if actual_audio and not actual_audio.issubset(expected_audio[suffix]):
                    result.errors.append(f"Audio codec does not match {suffix}: {sorted(actual_audio)}")
                if route == "videoaudio" and source_duration is not None:
                    source_audio = [stream for stream in source_info.get("streams", []) if stream.get("codec_type") == "audio"]
                    try: expected_duration = float(source_audio[0].get("duration")) if source_audio else source_duration
                    except (TypeError, ValueError): expected_duration = source_duration
                    audio_output_duration = _media_duration(info)
                    if audio_output_duration is None or abs(audio_output_duration - expected_duration) > max(0.35, expected_duration * 0.02):
                        result.errors.append("Audio duration differs from the first source audio stream by more than the 2%/350 ms tolerance.")
                result.checks.append(f"Audio container probed: {output.name}.")
            elif suffix == ".html":
                result.checks.append(f"HTML output exists: {output.name}; inspect it in a browser.")
            else:
                result.warnings.append(f"No automated content validator configured for {output.name}; inspect it manually.")
        except FileNotFoundError as error:
            result.warnings.append(f"Validator unavailable: {error}")
        except ValueError as error:
            result.errors.append(f"{output.name}: {error}")
    if not result.checks and not result.errors:
        result.warnings.append("No technical checks were available.")
    return {**result.as_dict(), "outputs": [str(p.relative_to(case_dir)) for p in outputs if p.exists()],
            "external_outputs": external_outputs}


def _run_checked(argv: list[str], label: str, timeout: int = 60) -> None:
    proc = _run(argv, timeout=timeout)
    if proc.returncode:
        raise RuntimeError(f"{label} failed: {proc.stderr.strip() or proc.stdout.strip()}")


def _capability_inventory() -> dict[str, Any]:
    tools = ("magick", "identify", "exiftool", "ffmpeg", "ffprobe", "pdfinfo", "qdbus", "kdialog", "dolphin", "dbus-run-session", "intltool-merge")
    inventory: dict[str, Any] = {"tools": {name: shutil.which(name) is not None for name in tools}}
    magick = shutil.which("magick")
    if magick:
        formats = _run([magick, "-list", "format"], timeout=30).stdout
        names = ("JPEG", "PNG", "GIF", "TIFF", "BMP", "WEBP", "AVIF", "HEIC", "JXL", "JP2", "J2K", "APNG", "ICO", "CUR", "SVG", "PDF", "PSD", "EXR", "HDR")
        inventory["imagemagick_formats"] = {name: bool(re.search(rf"(?m)^{re.escape(name)}\*?\s+[r-][w-]", formats)) for name in names}
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        encoders = _run([ffmpeg, "-hide_banner", "-encoders"], timeout=30).stdout
        names = ("libx264", "libx265", "libsvtav1", "libaom-av1", "aac", "libmp3lame", "flac", "pcm_s16le")
        inventory["ffmpeg_encoders"] = {name: bool(re.search(rf"(?m)^\s*[A-Z.]{6}\s+{re.escape(name)}(?:\s|$)", encoders)) for name in names}
    inventory["icc_profiles"] = {"srgb": _find_profile(("sRGB.icc", "sRGB2014.icc")) is not None,
                                  "display_p3_or_adobe_rgb": _find_profile(("DisplayP3.icc", "AdobeRGB1998.icc", "AdobeRGB.icc")) is not None,
                                  "rec709": _find_profile(("Rec709.icc", "BT709.icc", "rec709.icc")) is not None}
    return inventory


def _find_profile(names: tuple[str, ...]) -> Path | None:
    roots = (Path("/usr/share/color/icc"), Path("/usr/share/icc"), Path("/usr/local/share/color/icc"))
    for root in roots:
        if root.exists():
            for name in names:
                hits = list(root.rglob(name))
                if hits and hits[0].is_file():
                    return hits[0]
    return None


def _draw_image(magick: str, target: Path, color: str, width: int = 640, height: int = 480, suffix: str = "png") -> None:
    commands = [magick, "-size", f"{width}x{height}", "xc:white", "-fill", color,
                "-draw", f"rectangle 30,30 {width // 2},{height - 30}", "-fill", "#1e40af",
                "-draw", f"rectangle {width // 2 + 20},80 {width - 30},{height // 2}",
                f"{suffix}:{target}"]
    _run_checked(commands, f"create {target.name}")


def _generate_masters(directory: Path) -> dict[str, Any]:
    magick = shutil.which("magick")
    if not magick:
        raise RuntimeError("ImageMagick 7 (magick) is required to create acceptance fixtures")
    exiftool = shutil.which("exiftool")
    ffmpeg = shutil.which("ffmpeg")
    _draw_image(magick, directory / "photo.jpg", "#e11d48", suffix="jpeg")
    _draw_image(magick, directory / "photo.png", "#16a34a")
    _draw_image(magick, directory / "wide.jpg", "#f59e0b", 960, 360, "jpeg")
    _draw_image(magick, directory / "portrait.jpg", "#7c3aed", 360, 640, "jpeg")
    _draw_image(magick, directory / "tiny.png", "#0ea5e9", 48, 32)
    _draw_image(magick, directory / "large.jpg", "#64748b", 2048, 1536, "jpeg")
    shutil.copy2(directory / "photo.jpg", directory / "unicode photo ü [1].jpg")
    shutil.copy2(directory / "photo.jpg", directory / "-leading ü [1].jpg")
    _run_checked([magick, "-size", "640x480", "xc:none", "-fill", "#dc2626cc", "-draw", "circle 220,240 220,80",
                  "-fill", "#2563eb88", "-draw", "rectangle 300,80 600,400", str(directory / "transparent.png")], "create transparent fixture")
    _run_checked([magick, str(directory / "photo.jpg"), str(directory / "photo.tif")], "create TIFF fixture")
    for name, color in (("sequence-red.png", "#ef4444"), ("sequence-green.png", "#22c55e"), ("sequence-blue.png", "#3b82f6")):
        _draw_image(magick, directory / name, color)
    _run_checked([magick, "-delay", "6", "-size", "160x120", "xc:#ef4444", "-delay", "12", "-size", "160x120", "xc:#2563eb", "-loop", "0", str(directory / "animated.gif")], "create animated GIF")
    metadata = directory / "metadata.jpg"
    shutil.copy2(directory / "photo.jpg", metadata)
    shutil.copy2(metadata, directory / "dated-photo.jpg")
    metadata_seeded = False
    orientation_seeded = False
    if exiftool:
        _run_checked([exiftool, "-overwrite_original", "-GPSLatitude=42", "-GPSLongitude=3",
                      "-DateTimeOriginal=2024:02:29 23:45:06", "-CreateDate=2024:02:29 23:45:06",
                      "-ModifyDate=2024:02:29 23:45:06", "-SubSecTimeOriginal=123",
                      "-Artist=KIM6 Acceptance Photographer", "-Copyright=Copyright © 2024 QA Fixture",
                      "-XMP-dc:Rights=QA sample rights", "-XMP-iptcExt:DigitalSourceType=trainedAlgorithmicMedia",
                      "-XMP-iptcExt:AIPromptInformation=synthetic QA prompt", "-XMP-iptcExt:AIPromptWriterName=Fixture Generator",
                      str(metadata)], "seed metadata fixture")
        _run_checked([exiftool, "-overwrite_original", "-Orientation#=6", str(directory / "dated-photo.jpg")], "seed EXIF date fixture")
        orientation = directory / "orientation-6.jpg"
        shutil.copy2(directory / "photo.jpg", orientation)
        _run_checked([exiftool, "-overwrite_original", "-Orientation#=6", "-DateTimeOriginal=2024:02:29 23:45:06", str(orientation)], "seed orientation fixture")
        metadata_seeded = orientation_seeded = True
    else:
        shutil.copy2(directory / "photo.jpg", directory / "orientation-6.jpg")
    profiles: dict[str, bool] = {}
    srgb_profile = _find_profile(("sRGB.icc", "sRGB2014.icc"))
    if srgb_profile and exiftool:
        _run_checked([magick, str(directory / "metadata.jpg"), "-profile", str(srgb_profile), str(directory / "metadata-profiled.jpg")], "attach ICC profile to metadata fixture")
        shutil.move(directory / "metadata-profiled.jpg", directory / "metadata.jpg")
    for name, patterns, target in (
        ("srgb", ("sRGB.icc", "sRGB2014.icc"), directory / "profile-srgb.jpg"),
        ("wide-gamut", ("DisplayP3.icc", "AdobeRGB1998.icc", "AdobeRGB.icc"), directory / "profile-wide.jpg"),
    ):
        profile = _find_profile(patterns)
        if profile:
            _run_checked([magick, str(directory / "photo.jpg"), "-profile", str(profile), str(target)], f"create {name} profile sample")
            profiles[name] = True
        else:
            shutil.copy2(directory / "photo.jpg", target)
            profiles[name] = False
    video_status: dict[str, bool] = {"audio": False, "silent": False, "multi_audio": False}
    if ffmpeg:
        encoders = _run([ffmpeg, "-hide_banner", "-encoders"], timeout=20).stdout
        if "libx264" in encoders or "mpeg4" in encoders:
            common = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=12:duration=2"]
            if "libx264" in encoders:
                vcodec = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
            else:
                vcodec = ["-c:v", "mpeg4", "-q:v", "5"]
            _run_checked(common + [*vcodec, "-an", str(directory / "video-silent.mp4")], "create silent video fixture")
            video_status["silent"] = True
            if "aac" in encoders:
                _run_checked(common + ["-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-map", "0:v:0", "-map", "1:a:0", *vcodec, "-c:a", "aac", "-shortest", str(directory / "video-audio.mp4")], "create video/audio fixture")
                _run_checked(common + ["-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-f", "lavfi", "-i", "sine=frequency=660:duration=2", "-map", "0:v:0", "-map", "1:a:0", "-map", "2:a:0", *vcodec, "-c:a", "aac", "-shortest", str(directory / "video-multiaudio.mkv")], "create multiple-audio fixture")
                video_status.update(audio=True, multi_audio=True)
    return {"exiftool_metadata_seeded": metadata_seeded, "exif_orientation_seeded": orientation_seeded,
            "profiles": profiles, "video": video_status, "capabilities": _capability_inventory()}


def _owned_tree(path: Path, label: str, owner_text: str) -> Path:
    _reject_symlink_components(path.absolute())
    if path.is_symlink():
        raise SafetyError(f"refusing symlink path: {path}")
    if path.exists():
        marker = path / label
        if not path.is_dir() or marker.is_symlink() or not marker.is_file() or marker.read_text(encoding="utf-8") != owner_text:
            raise SafetyError(f"existing path is not owned: {path}")
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.mkdir(mode=0o700)
    except FileExistsError as error:
        raise SafetyError(f"owned directory appeared during creation: {path}") from error
    try:
        _write_exclusive(path / label, owner_text)
    except Exception:
        try: path.rmdir()
        except OSError: pass
        raise
    return path


def _make_masters(generated: Path) -> dict[str, Any]:
    masters = generated / "masters"
    marker_name = ".kim6-masters-owner"
    owner = "KIM6 acceptance pristine fixture masters v1\n"
    if masters.exists():
        if masters.is_symlink() or not (masters / marker_name).is_file() or (masters / marker_name).read_text() != owner:
            raise SafetyError("existing master fixture directory is not owned")
        manifest_path = masters / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            raise SafetyError("master fixtures are incomplete; inspect manually, refusing to overwrite")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, digest in manifest["sha256"].items():
            path = masters / name
            if path.is_symlink() or not path.is_file() or sha256(path) != digest:
                raise SafetyError(f"pristine master fixture changed: {name}; refusing to replace it")
        if "environment_capabilities" not in manifest:
            manifest["environment_capabilities"] = _capability_inventory()
            if manifest_path.is_symlink():
                raise SafetyError("refusing symlink fixture manifest")
            _write_atomic_text(manifest_path, json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return manifest
    stage = generated / f".masters.stage-{os.getpid()}-{time.time_ns()}"
    stage.mkdir(mode=0o700)
    try:
        capabilities = _generate_masters(stage)
        hashes = {p.name: sha256(p) for p in stage.iterdir() if p.is_file() and p.name not in {marker_name, "manifest.json"}}
        manifest = {"version": 1, "capabilities": capabilities, "sha256": hashes}
        (stage / marker_name).write_text(owner, encoding="utf-8")
        (stage / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.rename(stage, masters)
        _fsync_dir(generated)
        return manifest
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise


def _baseline_for(case_dir: Path, fixture_names: list[str]) -> dict[str, str]:
    return {name: sha256(case_dir / name) for name in fixture_names}


def _instructions(case: dict[str, Any], case_dir: Path) -> str:
    policy = _validation_policy(case)
    guidance, expected = _case_guidance(case)
    behavior = case["source_behavior"]
    if case["route"] in {"about", "license", "manual"}:
        output_location = "No output file; the selected case image only opens the context menu."
    elif case["route"] == "resizeandsend":
        output_location = "Use the persistent attachment folder reported by the action; the email draft is temporary and must not be sent during this test."
    elif behavior == "derived":
        output_location = "This case folder. If the action asks for a destination, choose this folder."
    elif behavior == "rename":
        output_location = "This case folder or the destination you choose; keep every renamed test file inside this case folder."
    elif behavior in {"in_place", "authorized_overwrite"}:
        output_location = "This case folder. In-place or authorized overwrite choices change only these disposable case copies."
    else:
        output_location = "This case folder unless the action's instructions below specify otherwise."
    lines = [f"KIM6 Dolphin acceptance case: {case['label']}", f"Case ID: {case['id']}", "",
             f"1. Open this case directory in Dolphin: {case_dir}",
             f"2. Select: {', '.join(case['fixtures']) if case['fixtures'] else '(no files)' }.",
             "   Informational actions use a selected file only to expose the context menu; the file is not passed to kim_all.",
             f"3. Menu path: {case['submenu']} → {case['label']}.",
             f"4. {guidance}",
             f"5. Output location: {output_location}",
             "   Inspect the result described below. Do not send email or print pages during this test; close any draft or viewer when finished.",
             f"6. After visual inspection, run `python3 qa/acceptance.py pass --mode gui --policy {policy}`. This validates the files and records a pass only if the checks succeed.",
             f"   If a check fails, inspect details with `python3 qa/acceptance.py validate --policy {policy}`, correct or explain the issue, then try again.", "",
             "Expected result: " + expected, "",
             "Source handling: " + _source_explanation(case),
             "", "Technical checks:"]
    lines += ["- " + check for check in case["technical_checks"]]
    lines += ["", "Human checks:"]
    lines += ["- " + check for check in case["human_checks"]]
    unavailable = case.get("unavailable_fixtures", [])
    if unavailable:
        lines += ["", "Fixture unavailable: " + ", ".join(unavailable) + ". This case cannot be run until its listed fixture dependency is available."]
    lines += ["", "If a requested optional codec/delegate is not present, mark the case blocked or skipped with the exact missing capability.", ""]
    return "\n".join(lines)


def _validation_policy(case: dict[str, Any]) -> str:
    behavior = case["source_behavior"]
    if behavior == "authorized_overwrite":
        return _effective_policy() or "create"
    return {"in_place": "in-place", "rename": "rename", "derived": "derived", "none": "derived"}[behavior]


@lru_cache(maxsize=1)
def _effective_policy() -> str | None:
    if "KIM_POLICY" in os.environ:
        configured = os.environ["KIM_POLICY"]
        return configured if configured in {"create", "overwrite"} else None
    if "KIM_CONFIG_FILE" in os.environ:
        config_file = Path(os.environ["KIM_CONFIG_FILE"])
    elif (GENERATED / "gui-config" / "kim_kdeimagemenu").is_file():
        config_file = GENERATED / "gui-config" / "kim_kdeimagemenu"
    else:
        config_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        config_file = config_home / "kim_kdeimagemenu"
    kreadconfig = shutil.which("kreadconfig6")
    if not kreadconfig or not config_file.is_file():
        return None
    result = _run([kreadconfig, "--file", str(config_file), "--group", "<default>", "--key", "KIM_POLICY"], timeout=5)
    value = result.stdout.strip()
    return value if result.returncode == 0 and value in {"create", "overwrite"} else None


def _arg_value(args: list[str], name: str, default: str = "") -> str:
    try:
        return args[args.index(name) + 1]
    except (ValueError, IndexError):
        return default


def _source_explanation(case: dict[str, Any]) -> str:
    behavior = case["source_behavior"]
    if behavior == "derived":
        return "This action creates a separate result. It must not replace a selected source, even if KIM_POLICY is set to overwrite."
    if behavior == "in_place":
        return "This action changes the selected file in place. The only selected files are disposable QA copies; do not use personal media."
    if behavior == "rename":
        return "This action renames or moves the selected disposable files. Check that no unrelated case file is displaced."
    if behavior == "authorized_overwrite":
        return "Choose create mode for this test when asked; in create mode the selected source remains unchanged. If KIM_POLICY or the KIM6 config forces overwrite, or if you choose overwrite in a prompt, the selected test copy may change; never use personal media. Use `--policy overwrite` when recording that result."
    return "No media source is changed by this informational action."


def _case_guidance(case: dict[str, Any]) -> tuple[str, str]:
    route, args, label = case["route"], case["args"], case["label"]
    fixtures = ", ".join(case["fixtures"])
    tag = ""
    if route == "compress":
        quality = _arg_value(args, "--quality")
        if quality:
            return f"Use the menu preset at JPEG quality {quality}. Do not confuse this with resizing; it changes JPEG encoding quality.", f"A JPEG tagged `_compressed` (normally `{Path(case['fixtures'][0]).stem}_compressed.jpg` with the default suffix setting)."
        return "Enter a JPEG quality from 1 to 100 when prompted; use 50 for this check.", "A JPEG derivative tagged `_compressed`, or the explicitly selected overwrite result."
    if route == "resize":
        size = _arg_value(args, "--size")
        if "--custom-percent" in args:
            return "Enter 50% in the resize percentage prompt (valid range 1–1000%).", "A resized derivative at half the source width and height, tagged `_resized`; check the decoded dimensions."
        if size:
            return f"The menu requests a maximum size of {size}; keep the aspect ratio when the prompt offers geometry choices.", f"A smaller image tagged `_resized`, within {size} bounds."
        return "Choose a custom size such as 800x600, or choose 50% for the percentage action.", "A correctly sized image tagged `_resized`; check dimensions in the file properties."
    if route == "convert":
        fmt = _arg_value(args, "--format", "the format you choose")
        fmt = {"jpg": "JPEG", "jpeg": "JPEG", "tif": "TIFF", "bmp": "BMP", "heic": "HEIC/HEIF", "jxl": "JPEG XL", "jp2": "JPEG 2000"}.get(fmt, fmt.upper())
        extra = " The BMP5 preset should produce a BMP5 bitmap." if "--bmp5" in args else ""
        return f"The menu preset targets {fmt}.{extra} If a destination or filename dialog appears, save in this case folder and keep the matching extension.", f"A readable {fmt} file with a matching extension in this case folder."
    if route == "webexport":
        size, quality = _arg_value(args, "--size", "1600x1600"), _arg_value(args, "--quality", "75")
        fmt = _arg_value(args, "--format", "configured web format")
        return f"Use the {size} size and quality {quality} preset; select this case folder as the export destination. Format: {fmt}. The action always makes a derivative.", "A distinct web image in this case folder; the selected source remains unchanged."
    if route == "resizeandsend":
        size = _arg_value(args, "--size", "full")
        return f"Use the {size} mail preset. Inspect the draft's attachment list, then close the draft without sending.", "A draft containing only prepared image attachments. Prepared attachments remain in the QA-owned persistent attachment area after the action exits."
    if route in {"rotate", "rotatewithexif"}:
        angle = _arg_value(args, "--angle")
        choice = f"Use the {angle} degree rotation." if angle else ("Choose a custom angle such as 17 degrees." if "--custom" in args else "Choose automatic EXIF orientation correction.")
        return choice + " Confirm the direction by comparing the asymmetric fixture.", "The disposable image is changed in place and its visible orientation is corrected."
    if route == "flipflop":
        operation = "vertically flip (top and bottom exchange)" if args[:1] == ["flip"] else "horizontally flop (left and right exchange)"
        return f"Use the requested operation: {operation}. Compare the asymmetric colored shapes.", f"The selected disposable image is transformed in place: {operation}."
    if route == "stripmeta":
        mode = _arg_value(args, "--mode", "all")
        scope = {"gps": "GPS/location fields only", "ai": "recognized AI-generation metadata only", "all": "all metadata"}.get(mode, "all metadata")
        return f"Confirm the requested {scope} removal when prompted. Choose create mode for this check if offered.", f"A result with {scope} removed; image pixels and unrelated metadata should follow the action's documented policy."
    if route == "copyright":
        return "Enter a short creator and copyright notice, leave usage rights blank, and select only the fields you intend to update. Save in this case folder if asked.", "The chosen rights tags are present; the image pixels and unrelated metadata are unchanged."
    if route == "timeshift":
        return "Choose a one-hour forward shift and the default capture-date fields; review the before/after confirmation before accepting.", "The selected EXIF camera dates move forward by one hour; filesystem modification time is unchanged."
    if route == "datesync":
        direction = _arg_value(args, "--direction")
        if not direction:
            direction = "choose EXIF to file for this first run"
        return f"Choose {direction}. Review the displayed before/after time and confirm the direction explicitly.", "The selected date values match in the chosen direction; image bytes remain unchanged for EXIF-to-file mode."
    if route == "rename":
        mode = args[0] if args else "interactive"
        return ("Choose sequential numbering, use base `acceptance`, start at 1, and select the case folder as the destination." if mode == "interactive" else "Choose the EXIF date naming format shown by the dialog, then confirm the target names before proceeding."), "The selected files have new names in the chosen case folder; verify all files remain present and ordered."
    if route == "album":
        return "Choose `2x2 landscape album` (the default), then accept the suggested output name in this case folder.", "A multi-page PDF album with the three selected images in order."
    if route == "print":
        return "Choose `11.5x15 cm: 1x2 images, portrait` (the default), then save the PDF in this case folder.", "A print-layout PDF with portrait physical pages and the selected images."
    if route == "gallery":
        return "Enter title `KIM6 acceptance`, author `QA`, and 3 columns; choose this case folder for the gallery output if asked.", "A gallery directory with an index, full-size images and thumbnails."
    if route == "pelemele":
        return "Use the defaults shown: 400x400 image size, 5x4 grid, 15% overlap and grey background; save in this case folder.", "A PNG collage containing all three colored source images."
    if route == "tiffjoin":
        return "Accept the suggested TIFF output name and choose this case folder if a destination is requested.", "A multi-page TIFF whose pages follow the selected red, green, blue order."
    if route == "animate":
        return "Use a 100-centisecond frame delay and loop count 0 (infinite); save the GIF in this case folder.", "An animated GIF showing red, green, then blue frames and looping continuously."
    if route == "video":
        size = _arg_value(args, "--size")
        codec = _arg_value(args, "--codec")
        container = _arg_value(args, "--container")
        if codec == "av1":
            quality = _arg_value(args, "--av1-quality")
            preset = f"AV1 {quality} quality" if quality != "custom" else "AV1 custom quality (use CRF 30 and speed 7 for this check)"
            detail = f"{preset}; output size {size}; container {container}."
        else:
            detail = f"{codec}, CRF {_arg_value(args, '--crf')}, output size {size}, container {container}."
        return f"Use this preset: {detail} Choose create mode if prompted.", "A playable video encoded with the requested codec, quality setting, size limit and container; the original remains in create mode."
    if route == "videoframes":
        mode = _arg_value(args, "--mode")
        if mode == "single":
            return "Enter timestamp 00:00:01.000 and keep PNG format.", "One PNG frame taken at the requested timestamp."
        if mode == "contact":
            return "Choose a 3x3 grid, PNG format, and accept the suggested output name.", "One labeled contact sheet with sampled frames and timestamps."
        return "Accept the automatic thumbnail choice and JPG format.", "One representative video thumbnail; sampling uses the action's documented midpoint rule."
    if route == "videoaudio":
        if _arg_value(args, "--mode") == "mute":
            return "Choose the suggested output name. Do not select an audio format; this operation copies video streams and removes audio.", "A new silent video with the video stream copied without re-encoding."
        return "Choose M4A/AAC when asked and accept the suggested output name.", "An audio-only M4A file; inspect the draft/file and confirm no video stream is present."
    if route == "videogif":
        return "Use start 00:00:00, duration 2 seconds, 10 fps, width 320, and infinite loop.", "A small animated GIF of the requested video segment."
    if route == "slideshow":
        return "Use 3 seconds per photo, 1280x720, 25 fps, black background and the natural filename ordering; save as `slideshow.mp4` in this case folder.", "A silent H.264 MP4 showing red, green, then blue slides, each for about 3 seconds."
    if route in {"about", "license", "manual"}:
        return "Open the item and close it after checking the installed information resource.", case["expected"]
    return "Follow the choices printed by the action and save any result in this case folder.", case["expected"]


def prepare(generated: Path = GENERATED, state_dir: Path = STATE_DIR, repo: Path = ROOT) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    generated = claim_workspace(generated)
    state_dir = _owned_tree(state_dir.absolute(), ".kim6-acceptance-state-owner", OWNER_TEXT)
    # The transfer inbox is initialized here so a receiving checkout has a
    # known QA-owned place for a manually copied result bundle.
    _owned_tree(QA_DIR / "transfers", ".kim6-acceptance-transfer-owner", OWNER_TEXT)
    cases = load_cases(repo)
    (repo / "qa").mkdir(exist_ok=True)
    plan_path = write_plan(repo, cases)
    master_manifest = _make_masters(generated)
    masters = generated / "masters"
    _owned_tree(generated / "cases", ".kim6-acceptance-owner", OWNER_TEXT)
    for case in cases:
        destination = create_owned_case_dir(generated, case["id"])
        if (destination / "case.json").is_symlink():
            raise SafetyError(f"refusing symlink case metadata: {destination / 'case.json'}")
        if (destination / "INSTRUCTIONS.txt").is_symlink():
            raise SafetyError(f"refusing symlink case instructions: {destination / 'INSTRUCTIONS.txt'}")
        if (destination / "case.json").exists():
            existing = json.loads((destination / "case.json").read_text(encoding="utf-8"))
            if existing.get("id") != case["id"]:
                raise SafetyError(f"case metadata mismatch: {destination}")
            instruction_path = destination / "INSTRUCTIONS.txt"
            case_for_instructions = {**case,
                                     "fixtures": existing.get("fixtures", case["fixtures"]),
                                     "unavailable_fixtures": existing.get("unavailable_fixtures", [])}
            instructions = _instructions(case_for_instructions, destination)
            if not instruction_path.exists():
                _write_exclusive(instruction_path, instructions)
            elif instruction_path.read_text(encoding="utf-8") != instructions:
                _write_atomic_text(instruction_path, instructions)
            if "baseline_image_info" not in existing and all(
                    name in existing.get("baseline_sha256", {}) and (destination / name).is_file() and
                    not (destination / name).is_symlink() and sha256(destination / name) == existing["baseline_sha256"][name]
                    for name in existing.get("fixtures", [])):
                existing["baseline_image_info"] = {}
                for name in existing.get("fixtures", []):
                    if Path(name).suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".webp", ".bmp"}:
                        fmt, dims = _image_info(destination / name)
                        existing["baseline_image_info"][name] = {"format": fmt, "frames": len(dims), "dimensions": dims}
                _write_atomic_text(destination / "case.json", json.dumps(existing, indent=2, sort_keys=True) + "\n")
            unchanged = all(name in existing.get("baseline_sha256", {}) and (destination / name).is_file() and
                            not (destination / name).is_symlink() and sha256(destination / name) == existing["baseline_sha256"][name]
                            for name in existing.get("fixtures", []))
            if "baseline_video_info" not in existing and unchanged:
                existing["baseline_video_info"] = {}
                if shutil.which("ffprobe"):
                    for name in existing.get("fixtures", []):
                        if Path(name).suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}:
                            try: existing["baseline_video_info"][name] = _video_info(destination / name)
                            except (OSError, ValueError, FileNotFoundError): pass
                _write_atomic_text(destination / "case.json", json.dumps(existing, indent=2, sort_keys=True) + "\n")
            continue
        allowed_partial = {".kim6-case-owner", *case["fixtures"]}
        unexpected = {p.name for p in destination.iterdir()} - allowed_partial
        if unexpected:
            raise SafetyError(f"incomplete case contains unrecognized entries; inspect manually: {destination}: {sorted(unexpected)}")
        for name in case["fixtures"]:
            source = masters / name
            if not source.is_file() or source.is_symlink():
                if name.startswith("video-"):
                    continue
                raise SafetyError(f"required fixture master is unavailable: {name}")
            target = destination / name
            if target.exists():
                if target.is_symlink() or not target.is_file() or sha256(target) != master_manifest["sha256"][name]:
                    raise SafetyError(f"partial case fixture differs from pristine master; refusing to overwrite: {target}")
            else:
                with source.open("rb") as src, target.open("xb") as dst:
                    shutil.copyfileobj(src, dst)
                    dst.flush()
                    os.fsync(dst.fileno())
        available = [name for name in case["fixtures"] if (destination / name).is_file()]
        unavailable = [name for name in case["fixtures"] if name not in available]
        case_for_instructions = {**case, "unavailable_fixtures": unavailable}
        icc_hashes: dict[str, str] = {}
        if shutil.which("exiftool"):
            for name in available:
                if Path(name).suffix.lower() in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp"}:
                    icc_hashes[name] = _icc_digest(destination / name)
        image_baselines: dict[str, dict[str, Any]] = {}
        video_baselines: dict[str, dict[str, Any]] = {}
        for name in available:
            if Path(name).suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".webp", ".bmp"}:
                fmt, dims = _image_info(destination / name)
                image_baselines[name] = {"format": fmt, "frames": len(dims), "dimensions": dims}
            elif Path(name).suffix.lower() in {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"} and shutil.which("ffprobe"):
                try:
                    video_baselines[name] = _video_info(destination / name)
                except (OSError, ValueError, FileNotFoundError):
                    pass
        record = {"id": case["id"], "menu": case["menu"], "action_id": case["action_id"],
                  "fixtures": available, "unavailable_fixtures": unavailable,
                  "baseline_sha256": _baseline_for(destination, available),
                  "baseline_mtime_ns": {name: (destination / name).stat().st_mtime_ns for name in available},
                  "baseline_mode": {name: (destination / name).stat().st_mode & 0o777 for name in available},
                  "baseline_pixel_signatures": {name: _image_signature(destination / name) for name in available
                                                if (destination / name).suffix.lower() in {".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".webp", ".bmp"}},
                  "baseline_image_info": image_baselines,
                  "baseline_video_info": video_baselines,
                  "baseline_icc_sha256": icc_hashes,
                  "master_sha256": {name: master_manifest["sha256"][name] for name in available},
                  "prepared_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        _write_exclusive(destination / "case.json", json.dumps(record, indent=2, sort_keys=True) + "\n")
        _write_exclusive(destination / "INSTRUCTIONS.txt", _instructions(case_for_instructions, destination))
    state_path = state_dir / "progress.json"
    state = load_state(state_path)
    save_state(state_path, state)
    return cases, master_manifest


def _find_case(cases: list[dict[str, Any]], case_id: str) -> dict[str, Any]:
    for case in cases:
        if case["id"] == case_id:
            return case
    short = [case for case in cases if case["action_id"] == case_id]
    if len(short) == 1:
        return short[0]
    raise KeyError(f"unknown or ambiguous case ID: {case_id}")


def _render_html(cases: list[dict[str, Any]], state: dict[str, Any]) -> str:
    totals = result_totals(cases, state)
    environment = _environment_snapshot()
    parts = ["<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>",
             "<title>KIM6 Acceptance Progress</title><style>body{font:16px system-ui;margin:2rem auto;max-width:1200px;padding:0 1rem;color:#18212b}table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccd3dc;padding:.55rem;text-align:left;vertical-align:top}th{background:#eef2f7}select{font:inherit;padding:.4rem}.status-passed{color:#116329}.status-failed{color:#9b1c1c}.status-blocked{color:#805500}.group{margin:2.5rem 0}code{white-space:pre-wrap}.details{white-space:pre-wrap;max-width:36rem}.environment{color:#435264}</style></head><body>",
             "<h1>KIM6 Human Acceptance Progress</h1><p>Read-only dashboard. Record results with the CLI. A technical check is not a human GUI pass.</p>",
             f"<p>Cases: {len(cases)} · Passed: {totals['passed']} · Failed: {totals['failed']} · Skipped: {totals['skipped']} · Environment blocked: {totals['blocked']} · Pending: {totals['pending']} · GUI passes: {totals['gui_verified']} · CLI-only passes: {totals['cli_verified']} · GUI blocked: {totals['gui_blocked']}</p>",
             f"<p class='environment'>Report host: {html.escape(environment['hostname'])} · revision: {html.escape(environment['git_revision'])} · KDE: {html.escape(environment['kde_version'] or 'not detected')} · Qt: {html.escape(environment['qt_version'] or 'not detected')}</p>",
             "<label>Filter <select id='filter'><option value='all'>All</option><option>pending</option><option>passed</option><option>failed</option><option>skipped</option><option>blocked</option></select></label><p>Use the filter to focus on pending, failed, skipped or blocked cases.</p>"]
    for menu in sorted({case["menu"] for case in cases}):
        group = [c for c in cases if c["menu"] == menu]
        menu_passed = sum(state.get("results", {}).get(c["id"], {}).get("status") == "passed" for c in group)
        parts += [f"<section class='group'><h2>{html.escape(MENU_TITLES.get(menu, menu))} — {menu_passed}/{len(group)} passed</h2><table><thead><tr><th>Case</th><th>Action</th><th>Status</th><th>Test type</th><th>Technical validation</th><th>Outputs</th><th>Instructions / files</th><th>Recorded environment</th><th>Notes</th></tr></thead><tbody>"]
        for case in (c for c in cases if c["menu"] == menu):
            row = state.get("results", {}).get(case["id"], {})
            status = row.get("status", "pending")
            if status not in {"pending", "passed", "failed", "skipped", "blocked"}:
                status = "pending"
            mode = ({"gui": "GUI verified", "cli": "CLI verified"}.get(row.get("mode"), "Not tested")
                    if status == "passed" else ("GUI blocked by KDE" if status == "blocked" and row.get("reason") == "KDE submenu issue" else "Not tested"))
            notes = row.get("note", row.get("reason", ""))
            validation = state.get("validations", {}).get(case["id"], {})
            errors = validation.get("errors", [])
            warnings = validation.get("warnings", [])
            checks = validation.get("checks", [])
            technical = "Not run" if not (errors or warnings or checks) else "\n".join(
                [*("PASS: " + str(item) for item in checks), *("WARN: " + str(item) for item in warnings), *("FAIL: " + str(item) for item in errors)])
            safe_id = re.sub(r"[^A-Za-z0-9_.:-]", "_", case["id"])
            case_link = f"../generated/cases/{safe_id}/"
            output_links = []
            from urllib.parse import quote
            for output in validation.get("outputs", []):
                relative = Path(str(output))
                if relative.is_absolute() or ".." in relative.parts:
                    continue
                output_links.append(f"<a href='{html.escape(case_link + quote(relative.as_posix(), safe='/'))}'>{html.escape(relative.as_posix())}</a>")
            for output in validation.get("external_outputs", []):
                relative = Path(str(output.get("path", "")))
                if relative.is_absolute() or ".." in relative.parts:
                    continue
                external_link = "../generated/" + quote(relative.as_posix(), safe="/")
                output_links.append(f"<a href='{html.escape(external_link)}'>{html.escape(relative.as_posix())} (persistent)</a>")
            outputs_html = " · ".join(output_links) if output_links else "—"
            provenance = row.get("provenance", {})
            env_text = "\n".join(str(provenance.get(key) or "not recorded") for key in ("hostname", "git_revision", "kde_version", "qt_version", "test_mode"))
            recorded_at = row.get("updated_at", "not recorded")
            parts.append(f"<tr data-status='{status}' class='status-{status}'><td><code>{html.escape(case['id'])}</code></td><td>{html.escape(case['label'])}</td><td>{status}</td><td>{mode}</td><td class='details'>{html.escape(technical)}</td><td>{outputs_html}</td><td><a href='{html.escape(case_link)}INSTRUCTIONS.txt'>Instructions</a> · <a href='{html.escape(case_link)}'>case directory</a></td><td class='details'>{html.escape(env_text)}\n{html.escape(recorded_at)}</td><td>{html.escape(str(notes or ''))}</td></tr>")
        parts.append("</tbody></table></section>")
    parts.append("<script>document.getElementById('filter').addEventListener('change',function(){document.querySelectorAll('tr[data-status]').forEach(function(row){row.hidden=this.value!=='all'&&row.dataset.status!==this.value},this)})</script></body></html>")
    return "\n".join(parts) + "\n"


def _ensure_case_outputs_tracked(case_dir: Path, case_record: dict[str, Any], validation: dict[str, Any]) -> None:
    tracked = set(case_record.get("owned_outputs", []))
    for relative in validation.get("outputs", []):
        path = Path(relative)
        parents = list(path.parents)
        tracked.add(path.as_posix())
        tracked.update(parent.as_posix() for parent in parents if str(parent) != ".")
        full = case_dir / path
        if full.is_dir() and not full.is_symlink():
            tracked.update(str(child.relative_to(case_dir)) for child in full.rglob("*"))
    case_record["owned_outputs"] = sorted(tracked)
    external = {item.get("path"): item for item in case_record.get("external_outputs", [])}
    external.update({item.get("path"): item for item in validation.get("external_outputs", [])})
    case_record["external_outputs"] = [external[key] for key in sorted(external) if key]
    _write_atomic_text(case_dir / "case.json", json.dumps(case_record, indent=2, sort_keys=True) + "\n")


def _open_dolphin(path: Path, isolated: bool = False, generated: Path = GENERATED) -> str:
    dolphin = shutil.which("dolphin")
    if not dolphin:
        return "Dolphin was not found; open this path manually: " + str(path)
    if not isolated:
        subprocess.Popen([dolphin, "--new-window", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return "Opened a Dolphin window. For revision-matched menus, install the isolated QA copy and use --isolated."
    dbus_run = shutil.which("dbus-run-session")
    if not dbus_run:
        return "dbus-run-session is unavailable; cannot launch isolated Dolphin. Open manually only after following qa/README.md."
    generated = assert_workspace(generated)
    data_home = generated / "gui-data"
    config_home = generated / "gui-config"
    cache_home = generated / "gui-cache"
    for directory in (data_home, config_home, cache_home):
        _reject_symlink_components(directory)
        directory.mkdir(parents=True, exist_ok=True)
    prefix = data_home / "kio" / "servicemenus"
    dispatcher = prefix / "kim6" / "bin" / "kim_all"
    if not dispatcher.is_file():
        return "Isolated menu copy is not installed. Follow qa/README.md to run the explicit isolated install command first."
    env = os.environ.copy()
    # Use the isolated user data tree and the standard system share. Do not
    # inherit arbitrary host XDG_DATA_DIRS entries such as /usr/local/share.
    # System-wide service menus under /usr/share can still be visible.
    env.update({"XDG_DATA_HOME": str(data_home), "XDG_CONFIG_HOME": str(config_home), "XDG_CACHE_HOME": str(cache_home),
                "XDG_DATA_DIRS": "/usr/share"})
    subprocess.Popen([dbus_run, "--", "env", *[f"{key}={value}" for key, value in env.items() if key.startswith("XDG_")],
                      dolphin, "--new-window", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return "Opened Dolphin with isolated user data/config/cache and D-Bus; email attachments and KIM6 user data stay under qa/generated/gui-data. System-wide menus from /usr/share may also appear; use only the matching KIM6 menu contract verified by check-install, and do not invoke a duplicate or unidentified menu."


def _print_case(case: dict[str, Any], directory: Path) -> None:
    print(f"\n{case['label']} — {case['id']}")
    print(f"Menu: {case['submenu']} → {case['label']}")
    print("Select: " + (", ".join(case["fixtures"]) if case["fixtures"] else "no files"))
    print("Dispatcher contract: " + case["exec"])
    if case["route"] in {"about", "license", "manual"}:
        print("The selected file exposes this context-menu item; kim_all receives no file argument.")
    elif "%F" not in case["exec"] and "%U" not in case["exec"]:
        print("The selected file exposes this context-menu item; confirm the Exec contract before assuming it receives the file.")
    print("Interactive choices: " + "; ".join(case["interactive_choices"]))
    print("Dependencies: " + ", ".join(case["dependencies"]))
    if case.get("unavailable_fixtures"):
        print("BLOCKED fixture: " + ", ".join(case["unavailable_fixtures"]) + "; mark blocked/skipped with the missing requirement.")
    guidance, expected = _case_guidance(case)
    print("Choices: " + guidance)
    print("Expected: " + expected)
    print("Source handling: " + _source_explanation(case))
    print("Case directory: " + str(directory))
    print("Technical checks: " + " ".join(case["technical_checks"]))
    policy = _validation_policy(case)
    print(f"After visual inspection, run: python3 qa/acceptance.py pass --mode gui --policy {policy}")
    print(f"That command validates and records only on success; inspect further with: python3 qa/acceptance.py validate --policy {policy}")
    if case["source_behavior"] == "in_place":
        print("WARNING: this action is in-place. It will only touch disposable files in this case directory.")


def _get_state(state_path: Path) -> dict[str, Any]:
    return load_state(state_path)


def _environment_snapshot(mode: str = "") -> dict[str, Any]:
    def version(argv: list[str]) -> str | None:
        proc = _run(argv, timeout=5)
        return (proc.stdout or proc.stderr).strip().splitlines()[0][:240] if proc.returncode == 0 and (proc.stdout or proc.stderr).strip() else None

    def package_version(package: str) -> str | None:
        dpkg_query = shutil.which("dpkg-query")
        if not dpkg_query:
            return None
        proc = _run([dpkg_query, "-W", "-f=${Version}", package], timeout=5)
        value = proc.stdout.strip()
        return f"{package} {value}" if proc.returncode == 0 and value else None

    revision_proc = _run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], timeout=5)
    dirty_proc = _run(["git", "-C", str(ROOT), "status", "--porcelain"], timeout=5)
    qt_version = version([shutil.which("qmake6") or "qmake6", "-query", "QT_VERSION"]) if shutil.which("qmake6") else None
    if not qt_version and shutil.which("qtpaths6"):
        qt_version = version([shutil.which("qtpaths6") or "qtpaths6", "--query", "QT_VERSION"])
    kde_version = version([shutil.which("kf6-config") or "kf6-config", "--version"]) if shutil.which("kf6-config") else None
    if not kde_version:
        kde_version = package_version("plasma-workspace")
    return {
        "hostname": socket.gethostname(),
        "git_revision": revision_proc.stdout.strip() if revision_proc.returncode == 0 else "unknown",
        "working_tree_dirty": bool(dirty_proc.stdout.strip()) if dirty_proc.returncode == 0 else None,
        "kde_version": kde_version,
        "qt_version": qt_version,
        "test_mode": mode or "unspecified",
    }


class MergeConflict(RuntimeError):
    pass


def export_state(state_path: Path, output: Path, cases: list[dict[str, Any]]) -> dict[str, Any]:
    if output.is_symlink():
        raise SafetyError(f"refusing symlink export path: {output}")
    if output.exists():
        raise SafetyError(f"export file already exists; choose a new name: {output}")
    state = load_state(state_path)
    known = {case["id"] for case in cases}
    results = {case_id: {**row, "case_id": case_id} for case_id, row in state.get("results", {}).items() if case_id in known}
    validations = {case_id: row for case_id, row in state.get("validations", {}).items() if case_id in known}
    bundle = {"format": "kim6-acceptance-results", "version": 1, "exported_at": _utc_now(),
              "source": _environment_snapshot("export"), "results": results, "validations": validations}
    _write_exclusive(output, json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True) + "\n", 0o600)
    return bundle


def read_import_bundle(path: Path) -> dict[str, Any]:
    path = Path(path)
    _reject_symlink_components(path.absolute())
    if path.is_symlink() or not path.is_file():
        raise SafetyError(f"import must be a regular, non-symlink JSON file: {path}")
    try:
        bundle = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SafetyError(f"cannot read acceptance transfer file: {error}") from error
    if bundle.get("format") != "kim6-acceptance-results" or bundle.get("version") != 1:
        raise SafetyError("unrecognized acceptance transfer file")
    if not isinstance(bundle.get("results"), dict) or not isinstance(bundle.get("validations", {}), dict):
        raise SafetyError("transfer file has invalid results or validations")
    for case_id, row in bundle["results"].items():
        if not isinstance(case_id, str) or not isinstance(row, dict) or row.get("status") not in {"passed", "failed", "skipped", "blocked"}:
            raise SafetyError(f"invalid result record for {case_id!r}")
        if row.get("case_id", case_id) != case_id:
            raise SafetyError(f"result case ID does not match its record key: {case_id}")
        if row.get("mode", "") not in {"gui", "cli", ""}:
            raise SafetyError(f"invalid test mode for {case_id}")
    for case_id, validation in bundle.get("validations", {}).items():
        if not isinstance(case_id, str) or not isinstance(validation, dict):
            raise SafetyError(f"invalid technical validation record for {case_id!r}")
    return bundle


def import_state(state_path: Path, bundle_path: Path, case_ids: set[str], resolution: str = "") -> dict[str, Any]:
    bundle = read_import_bundle(bundle_path)
    incoming = bundle["results"]
    unknown = sorted(set(incoming) - case_ids)
    if unknown:
        raise SafetyError("transfer contains unknown case ID(s): " + ", ".join(unknown))
    unknown_validations = sorted(set(bundle.get("validations", {})) - case_ids)
    if unknown_validations:
        raise SafetyError("transfer contains validation for unknown case ID(s): " + ", ".join(unknown_validations))
    current = load_state(state_path)
    existing = current.setdefault("results", {})
    result_conflicts = {case_id for case_id, row in incoming.items() if case_id in existing and existing[case_id] != row}
    current_validations = current.setdefault("validations", {})
    validation_conflicts = set()
    for case_id, validation in bundle.get("validations", {}).items():
        if case_id not in current_validations:
            continue
        local_value = {key: value for key, value in current_validations[case_id].items() if key != "checked_at"}
        imported_value = {key: value for key, value in validation.items() if key != "checked_at"}
        if local_value != imported_value:
            validation_conflicts.add(case_id)
    conflict_ids = result_conflicts | validation_conflicts
    conflicts = sorted(conflict_ids)
    if conflicts and not resolution:
        raise MergeConflict("conflicting result(s): " + ", ".join(conflicts) + "; rerun with --resolve keep-local or --resolve use-imported")
    if resolution not in {"", "keep-local", "use-imported"}:
        raise ValueError("resolution must be keep-local or use-imported")
    for case_id, row in incoming.items():
        if case_id not in existing or (case_id in conflicts and resolution == "use-imported"):
            existing[case_id] = row
        elif case_id in existing and existing[case_id] == row:
            continue
    for case_id, validation in bundle.get("validations", {}).items():
        if case_id not in current_validations or case_id not in conflict_ids or resolution == "use-imported":
            current_validations[case_id] = validation
    save_state(state_path, current)
    return current


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _save_result(state_path: Path, case_id: str, status: str, mode: str = "", note: str = "", policy: str = "create") -> None:
    state = _get_state(state_path)
    row = {"case_id": case_id, "status": status, "updated_at": _utc_now(), "provenance": _environment_snapshot(mode)}
    if mode: row["mode"] = mode
    if note: row["note"] = note
    if status == "blocked": row["reason"] = note
    row["policy"] = policy
    state.setdefault("results", {})[case_id] = row
    if state.get("current_case") == case_id:
        state["current_case"] = None
    save_state(state_path, state)


def _print_validation(validation: dict[str, Any]) -> None:
    for check in validation["checks"]: print("PASS technical: " + check)
    for warning in validation["warnings"]: print("WARN technical: " + warning)
    for error in validation["errors"]: print("FAIL technical: " + error)
    if not validation["errors"]:
        print("Technical validation complete. This is not GUI acceptance or subjective quality assessment.")


def run_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated", type=Path, default=GENERATED, help=argparse.SUPPRESS)
    parser.add_argument("--state-dir", type=Path, default=STATE_DIR, help=argparse.SUPPRESS)
    parser.add_argument("--reports", type=Path, default=REPORT_DIR, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory", help="regenerate the template-derived acceptance plan")
    sub.add_parser("prepare", help="create pristine fixtures and per-action disposable copies")
    next_p = sub.add_parser("next", help="show/open the next pending Dolphin case")
    next_p.add_argument("--no-open", action="store_true")
    next_p.add_argument("--isolated", action="store_true", help="open in a QA-only D-Bus/XDG Dolphin session")
    next_p.add_argument("--case-id", help="open a named case without changing its recorded result")
    status_p = sub.add_parser("status", help="show acceptance progress")
    status_p.add_argument("--filter", choices=("all", "pending", "passed", "failed", "skipped", "blocked"), default="all")
    val = sub.add_parser("validate", help="inspect outputs after the human runs an action")
    val.add_argument("case_id", nargs="?")
    val.add_argument("--policy", choices=("create", "overwrite", "in-place", "derived", "rename"), default="create")
    for name in ("pass", "fail", "skip", "blocked"):
        mark = sub.add_parser(name, help=f"record {name} for the current or named case")
        mark.add_argument("case_id", nargs="?")
        mark.add_argument("--mode", choices=("gui", "cli"), default="cli")
        mark.add_argument("--policy", choices=("create", "overwrite", "in-place", "derived", "rename"), default="create")
        mark.add_argument("--note", default="")
        mark.add_argument("--reason", default="")
    reset = sub.add_parser("reset", help="reset one owned case without removing other cases or progress")
    reset.add_argument("case_id")
    sub.add_parser("report", help="write a shareable read-only HTML/JSON report")
    export_p = sub.add_parser("export", help="write a transfer file for cross-machine result merging")
    export_p.add_argument("--output", type=Path, help="new JSON file inside qa/; default is a timestamped qa/transfers file")
    import_p = sub.add_parser("import", help="merge results from a transfer file without overwriting conflicts")
    import_p.add_argument("bundle", type=Path)
    import_p.add_argument("--resolve", choices=("keep-local", "use-imported"), help="explicitly resolve conflicting results")
    sub.add_parser("second-pass", help="print focused safety edge-case checklist")
    install = sub.add_parser("install-isolated", help="explicitly install matching QA menus under qa/generated/gui-data")
    check = sub.add_parser("check-install", help="verify isolated installed dispatcher and menu action contracts")
    options = parser.parse_args(argv)
    try:
        options.generated = assert_toolkit_path(options.generated, "generated workspace")
        options.state_dir = assert_toolkit_path(options.state_dir, "state directory")
        options.reports = assert_toolkit_path(options.reports, "report directory")
    except SafetyError as error:
        print(f"acceptance: {error}", file=sys.stderr)
        return 2
    cases = load_cases(ROOT)
    state_path = options.state_dir / "progress.json"
    try:
        if options.command == "inventory":
            path = write_plan(ROOT, cases)
            print(f"Wrote {path.relative_to(ROOT)} with {len(cases)} cases.")
            return 0
        if options.command == "prepare":
            cases, manifest = prepare(options.generated, options.state_dir, ROOT)
            print(f"Prepared {len(cases)} cases under {options.generated.absolute() / 'cases'}")
            print(f"Pristine fixtures: {options.generated.absolute() / 'masters'}")
            print("Capability notes: " + json.dumps(manifest["capabilities"], sort_keys=True))
            print("Persistent progress: " + str(options.state_dir.absolute() / "progress.json"))
            print("Run: python3 qa/acceptance.py next")
            return 0
        if options.command == "second-pass":
            print(SECOND_PASS)
            return 0
        if options.command == "install-isolated":
            workspace = claim_workspace(options.generated)
            gui_data = workspace / "gui-data"
            _reject_symlink_components(gui_data)
            prefix = gui_data / "kio" / "servicemenus"
            (prefix.parent).mkdir(parents=True, exist_ok=True)
            env = os.environ.copy()
            env.update({"XDG_DATA_HOME": str(gui_data), "XDG_CONFIG_HOME": str(workspace / "gui-config"),
                        "XDG_CACHE_HOME": str(workspace / "gui-cache")})
            Path(env["XDG_CONFIG_HOME"]).mkdir(parents=True, exist_ok=True)
            Path(env["XDG_CACHE_HOME"]).mkdir(parents=True, exist_ok=True)
            cmd = [str(ROOT / "install.sh"), "--prefix", str(prefix)]
            proc = subprocess.run(cmd, cwd=ROOT, env=env, check=False)
            return proc.returncode
        if options.command == "check-install":
            return _check_isolated_install(options.generated.absolute())
        if options.command == "next":
            assert_workspace(options.generated)
            assert_owned_directory(options.state_dir, ".kim6-acceptance-state-owner", OWNER_TEXT)
            state = _get_state(state_path)
            if options.case_id:
                case = _find_case(cases, options.case_id)
            else:
                pending = [case for case in cases if state.get("results", {}).get(case["id"], {}).get("status", "pending") == "pending"]
                if not pending:
                    print("No pending cases. Use status --filter failed|skipped|blocked to review remaining items.")
                    return 0
                case = pending[0]
            case_dir = assert_case_directory(options.generated, case["id"])
            record = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
            if case["route"] == "resizeandsend" and "email_snapshot_dirs" not in record:
                record["email_snapshot_dirs"] = _email_snapshot(options.generated)
                _write_atomic_text(case_dir / "case.json", json.dumps(record, indent=2, sort_keys=True) + "\n")
            case = {**case, "fixtures": record.get("fixtures", []), "unavailable_fixtures": record.get("unavailable_fixtures", [])}
            state["current_case"] = case["id"]
            save_state(state_path, state)
            _print_case(case, case_dir)
            if not options.no_open:
                print(_open_dolphin(case_dir, options.isolated, options.generated))
            else:
                print("Open this directory in Dolphin, then invoke the menu action manually.")
            return 0
        if options.command == "status":
            state = _get_state(state_path)
            totals = result_totals(cases, state)
            print(" | ".join(f"{key}: {totals[key]}" for key in ("passed", "failed", "skipped", "blocked", "pending", "gui_verified", "cli_verified", "not_tested")))
            for menu in sorted({case["menu"] for case in cases}):
                group = [c for c in cases if c["menu"] == menu]
                counts = result_totals(group, state)
                print(f"{MENU_TITLES.get(menu, menu)}: {counts['passed']}/{len(group)} passed; {counts['failed']} failed; {counts['skipped']} skipped; {counts['blocked']} blocked; {counts['pending']} pending")
            for case in cases:
                row = state.get("results", {}).get(case["id"], {})
                status = row.get("status", "pending")
                if options.filter == "all" or options.filter == status:
                    mode = row.get("mode", "not tested")
                    print(f"{status:7} {case['id']} — {case['label']} [{mode}]")
                    if row.get("note") or row.get("reason"):
                        print("        " + row.get("note", row.get("reason", "")))
            return 0
        if options.command == "report":
            report_root = _owned_tree(options.reports.absolute(), ".kim6-acceptance-report-owner", OWNER_TEXT)
            state = _get_state(state_path)
            stamp = f"{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{time.time_ns()}"
            html_path = report_root / f"acceptance-{stamp}.html"
            json_path = report_root / f"acceptance-{stamp}.json"
            _write_exclusive(html_path, _render_html(cases, state), 0o600)
            totals = result_totals(cases, state)
            _write_exclusive(json_path, json.dumps({"totals": totals, "environment": _environment_snapshot(),
                                                     "results": state.get("results", {}),
                                                     "validations": state.get("validations", {})},
                                                    indent=2, ensure_ascii=False) + "\n", 0o600)
            print("Read-only dashboard: " + str(html_path))
            print("JSON report: " + str(json_path))
            print("Use the CLI to record results; the HTML dashboard is read-only.")
            return 0
        if options.command == "export":
            if options.output:
                output = options.output
            else:
                transfer_dir = _owned_tree(QA_DIR / "transfers", ".kim6-acceptance-transfer-owner", OWNER_TEXT)
                output = transfer_dir / f"acceptance-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{time.time_ns()}.json"
            output = assert_toolkit_path(output, "export file")
            bundle = export_state(state_path, output, cases)
            print(f"Exported {len(bundle['results'])} recorded case result(s): {output}")
            print("On the other checkout, run prepare, copy this JSON into qa/transfers/, then run: python3 qa/acceptance.py import qa/transfers/<file.json>")
            return 0
        if options.command == "import":
            bundle_path = assert_toolkit_path(options.bundle, "import file")
            assert_owned_directory(options.state_dir, ".kim6-acceptance-state-owner", OWNER_TEXT)
            merged = import_state(state_path, bundle_path, {case["id"] for case in cases}, options.resolve or "")
            print(f"Merged results; {len(merged.get('results', {}))} case result(s) are now recorded.")
            if options.resolve:
                print(f"Conflicts were resolved explicitly using: {options.resolve}.")
            return 0
        if options.command == "reset":
            assert_owned_directory(options.state_dir, ".kim6-acceptance-state-owner", OWNER_TEXT)
            case = _find_case(cases, options.case_id)
            case_dir = assert_case_directory(options.generated, case["id"])
            record_path = case_dir / "case.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            recorded_fixtures = set(record.get("fixtures", []))
            allowed = set(case["fixtures"]) | recorded_fixtures | set(record.get("owned_outputs", []))
            reset_case_dir(options.generated.absolute(), case["id"], allowed, recorded_fixtures)
            state = _get_state(state_path)
            state.get("results", {}).pop(case["id"], None)
            if state.get("current_case") == case["id"]: state["current_case"] = None
            save_state(state_path, state)
            print(f"Reset only {case['id']}; progress for all other cases is retained. Run prepare to recreate its fresh copies.")
            if record.get("external_outputs"):
                print("Persistent email attachment files were left in qa/generated/gui-data; close the mail client before deciding whether to remove these QA-owned copies manually.")
            return 0
        if options.command == "validate":
            assert_owned_directory(options.state_dir, ".kim6-acceptance-state-owner", OWNER_TEXT)
            case = _find_case(cases, options.case_id or _get_state(state_path).get("current_case") or "")
            case_dir = assert_case_directory(options.generated, case["id"])
            record_path = case_dir / "case.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            validation = validate_case_data(case, case_dir, record["baseline_sha256"], options.policy)
            _ensure_case_outputs_tracked(case_dir, record, validation)
            _print_validation(validation)
            save_state(state_path, _merge_validation(_get_state(state_path), case["id"], validation))
            return int(bool(validation["errors"]))
        if options.command in {"pass", "fail", "skip", "blocked"}:
            assert_owned_directory(options.state_dir, ".kim6-acceptance-state-owner", OWNER_TEXT)
            state = _get_state(state_path)
            case = _find_case(cases, options.case_id or state.get("current_case") or "")
            mode = options.mode
            note = options.note
            reason = options.reason
            validation = None
            if options.command == "pass":
                case_dir = assert_case_directory(options.generated, case["id"])
                record = json.loads((case_dir / "case.json").read_text(encoding="utf-8"))
                validation = validate_case_data(case, case_dir, record["baseline_sha256"], options.policy)
                _print_validation(validation)
                if validation["errors"]:
                    print("Not marked passed; address technical errors or mark blocked with a reason.")
                    return 1
                _ensure_case_outputs_tracked(case_dir, record, validation)
            if options.command == "fail" and not note:
                note = input("Brief failure note (required): ").strip()
                if not note: raise ValueError("fail requires --note or a nonempty note")
            if options.command in {"skip", "blocked"} and not reason:
                reason = input("Reason (required): ").strip()
                if not reason: raise ValueError(f"{options.command} requires --reason or a nonempty reason")
            status_value = {"pass": "passed", "fail": "failed", "skip": "skipped", "blocked": "blocked"}[options.command]
            _save_result(state_path, case["id"], status_value, mode, note or reason, options.policy)
            if validation is not None:
                save_state(state_path, _merge_validation(_get_state(state_path), case["id"], validation))
            print(f"Recorded {status_value.upper()} ({mode}) for {case['id']}.")
            return 0
    except (InventoryError, SafetyError, MergeConflict, RuntimeError, ValueError, KeyError, OSError, json.JSONDecodeError) as error:
        print(f"acceptance: {error}", file=sys.stderr)
        return 2
    return 2


def _merge_validation(state: dict[str, Any], case_id: str, validation: dict[str, Any]) -> dict[str, Any]:
    state.setdefault("validations", {})[case_id] = {**validation, "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    return state


def _check_isolated_install(generated: Path) -> int:
    try:
        generated = assert_workspace(generated)
    except SafetyError as error:
        print(str(error), file=sys.stderr)
        return 1
    prefix = generated / "gui-data" / "kio" / "servicemenus"
    runtime = prefix / "kim6" / "bin" / "kim_all"
    if runtime.is_symlink() or not runtime.is_file() or not (runtime.stat().st_mode & 0o111):
        print("Isolated KIM6 is not installed; run: python3 qa/acceptance.py install-isolated", file=sys.stderr)
        return 1
    if sha256(runtime) != sha256(ROOT / "src/bin/kim_all"):
        print("Installed dispatcher differs from the working-tree dispatcher.", file=sys.stderr)
        return 1
    templates = {p.name.removesuffix(".in"): parse_menu(p) for p in (ROOT / "src").glob("kim_*.desktop.in")}
    required_resources = ("ABOUT", "LICENSE.md", "INSTALL.md", "docs/index.html", "docs/work.css",
                          "gallery/index.part1", "gallery/index.part2")
    missing_resources = [name for name in required_resources if not (prefix / "kim6" / name).is_file()]
    if missing_resources:
        print("Missing installed KIM6 resource(s): " + ", ".join(missing_resources), file=sys.stderr)
        return 1
    legacy_names = {"kim_album", "kim_compress", "kim_convert", "kim_flipflop", "kim_galery", "kim_multiburst",
                    "kim_other", "kim_pelemele", "kim_print", "kim_rename", "kim_resize", "kim_resizeandsend",
                    "kim_rotate", "kim_rotatewithexif", "kim_sortbydate", "kim_stripmeta", "kim_treatment",
                    "kim_video", "kim_webexport"}
    legacy_active = []
    for name in legacy_names:
        legacy_path = prefix / "kim6" / "bin" / name
        if legacy_path.is_symlink() or (legacy_path.is_file() and bool(legacy_path.stat().st_mode & 0o111)):
            legacy_active.append(name)
    if legacy_active:
        print("Installed legacy executable(s) are still active: " + ", ".join(sorted(legacy_active)), file=sys.stderr)
        return 1
    total = 0
    for menu_name, entries in templates.items():
        installed = prefix / menu_name
        if installed.is_symlink() or not installed.is_file() or installed.stat().st_mode & 0o111:
            print(f"Missing installed menu: {installed}", file=sys.stderr); return 1
        text = installed.read_text(encoding="utf-8", errors="replace")
        installed_main, installed_actions = _desktop_sections(text)
        template_path = ROOT / "src" / f"{menu_name}.in"
        expected_main, expected_actions = _desktop_sections(template_path.read_text(encoding="utf-8"))
        declared_match = installed_main.get("Actions")
        actual_ids = [item for item in declared_match.split(";") if item] if declared_match else []
        expected_ids = [entry["action_id"] for entry in entries]
        if actual_ids != expected_ids:
            print(f"Installed action inventory differs for {menu_name}: expected {len(expected_ids)}, got {len(actual_ids)}", file=sys.stderr)
            return 1
        if set(installed_actions) != set(expected_actions):
            print(f"Installed action sections differ from {menu_name} template.", file=sys.stderr)
            return 1
        for key, value in expected_main.items():
            if key == "Actions":
                continue
            installed_key = key[1:] if key.startswith("_") else key
            translations = [v for candidate, v in installed_main.items() if candidate == installed_key or candidate.startswith(installed_key + "[")]
            if value not in translations:
                print(f"Installed menu field {key} differs from its template in {menu_name}.", file=sys.stderr)
                return 1
        for entry in entries:
            fields = installed_actions[entry["action_id"]]
            expected_fields = expected_actions[entry["action_id"]]
            label = expected_fields.get("_Name", expected_fields.get("Name", ""))
            if not any(value == label for key, value in fields.items() if key == "Name" or key.startswith("Name[")):
                print(f"Visible label differs for {entry['action_id']} in {installed}.", file=sys.stderr); return 1
            exec_value = fields.get("Exec", "")
            if not exec_value:
                print(f"Missing Exec for {entry['action_id']}", file=sys.stderr); return 1
            try: words = shlex.split(exec_value)
            except ValueError: return 1
            if not words or words[0] != str(runtime):
                print(f"Action {entry['action_id']} does not call the QA installed dispatcher", file=sys.stderr); return 1
            if words[1:] != entry["dispatcher"]:
                print(f"Argument mismatch for {entry['action_id']}: {words[1:]} != {entry['dispatcher']}", file=sys.stderr); return 1
            for key, value in expected_fields.items():
                if key in {"_Name", "Name", "Exec"}:
                    continue
                if fields.get(key) != value:
                    print(f"Action field {key} differs for {entry['action_id']} in {installed}.", file=sys.stderr); return 1
            total += 1
    print(f"Verified dispatcher hash and all {total} installed menu argument contracts.")
    system_roots = set(filter(None, os.environ.get("XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":")))
    system_roots.add("/usr/share")
    collisions = []
    for root in sorted(system_roots):
        for menu_name in templates:
            candidate = Path(root) / "kio" / "servicemenus" / menu_name
            if candidate.exists() or candidate.is_symlink():
                collisions.append(str(candidate))
    if collisions:
        print("Potential system-wide menu duplicates remain visible in the isolated session:")
        for path in collisions:
            print("  " + path)
        print("The isolated test session does not hide or modify these files. Do not guess between duplicate entries.")
    else:
        print("No same-name service menus were found in the checked XDG_DATA_DIRS roots.")
    print("This verifies installed files, not successful live Dolphin GUI behavior.")
    return 0 if total == 108 else 1


SECOND_PASS = """KIM6 second-pass safety acceptance checklist

Use only qa/generated/cases copies. Re-prepare an individual case before each destructive check.
- Cancel an operation before processing, during a producer, and immediately before publication; confirm no unwanted output and no lost existing target.
- For create-capable actions, make a collision by running twice; verify numbered output and preserved first output.
- For authorized overwrite, use only disposable case copies; verify output validation happens before replacement.
- For web export, email preparation, video utilities, and slideshow, confirm the selected source remains byte-identical even under overwrite configuration.
- For rotate/flip, confirm the prominent in-place warning and only the disposable source changes.
- Test missing optional encoders/delegates and verify a clear failure without format substitution.
- Compare JPEG quality with percentage resize: quality changes JPEG encoding; percentage changes dimensions.
- Compare sRGB web export with preserve-profile; confirm the embedded profile and visible colors.
- Verify GPS-only mode removes coordinates but retains dates, camera fields, copyright, ICC and pixels; it is not full anonymization.
- Inspect best-effort AI field removal and note that signed C2PA credentials may remain.
- Verify copyright/rights fields and selected-field behavior.
- Verify timestamp shift and both datesync directions; camera wall time is not timezone conversion.
- Verify EXIF orientation and animation frames, delays and loops.
- Verify mute contains no audio while video packets remain stream-copied.
- Verify slideshow natural filename order and each photo's display duration.
- Run a mixed batch with one invalid file; confirm accurate partial-failure reporting and retained successful outputs.
- Exercise missing dependencies, invalid input, and cancellation messages.
- In isolated prefixes only, test installer, reinstaller and uninstaller; keep unrelated files and active system menus untouched.
- Open installed Manual and verify its CSS stylesheet loads.
"""

if __name__ == "__main__":
    raise SystemExit(run_cli())
