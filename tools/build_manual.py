#!/usr/bin/env python3
"""Build KIM6's offline HTML reference pages from authoritative Markdown.

Run from anywhere: python3 tools/build_manual.py [--check]
Requires Pandoc at build time; generated HTML requires no runtime dependencies.
"""

import argparse
from html import escape, unescape
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
DOC_DIR = ROOT / "docs"
OUTPUT_DIR = DOC_DIR / "reference"
MAIN = (
    ROOT / "README.md",
    ROOT / "INSTALL.md",
    ROOT / "DEVELOPMENT.md",
    DOC_DIR / "ACTIONS.md",
    DOC_DIR / "commandconfig.md",
    DOC_DIR / "FORMATS.md",
)
LINK_RE = re.compile(r'(?P<start>\b(?:href|src)=")(?P<url>[^"]+)(?P<end>")')


def sources():
    for source in MAIN:
        if not source.is_file():
            raise RuntimeError(f"Required source document not found: {source.relative_to(ROOT)}")
    found = set(ROOT.glob("*.md")) | set(DOC_DIR.glob("*.md"))
    if (ROOT / "ABOUT").is_file():
        found.add(ROOT / "ABOUT")
    return sorted(found)


def page_names(paths):
    names = {}
    used = set()
    for source in paths:
        name = (source.stem if source.suffix else source.name) + ".html"
        if name.lower() in used:
            name = source.parent.name + "-" + name
        if name.lower() in used:
            raise RuntimeError(f"HTML output filename collision: {source}")
        used.add(name.lower())
        names[source.resolve()] = name
    return names


def rewrite_urls(html, source, names):
    def replacement(match):
        raw = unescape(match.group("url"))
        parts = urlsplit(raw)
        if parts.scheme or parts.netloc or not parts.path or parts.path.startswith("/"):
            return match.group(0)
        target = (source.parent / unquote(parts.path)).resolve()
        if target in names:
            path = names[target]
        elif target.is_relative_to(ROOT.resolve()):
            # Preserve links to non-Markdown project resources (images, scripts, etc.).
            path = os.path.relpath(target, OUTPUT_DIR).replace(os.sep, "/")
        else:
            return match.group(0)
        url = path + ("?" + parts.query if parts.query else "") + ("#" + parts.fragment if parts.fragment else "")
        return match.group("start") + escape(url, quote=True) + match.group("end")
    return LINK_RE.sub(replacement, html)


def render(source, names):
    command = [
        "pandoc", "--from=gfm", "--to=html5", "--no-highlight",
        "--wrap=none", str(source),
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f"Pandoc failed for {source}:\n{result.stderr}")
    main_html = rewrite_urls(result.stdout, source, names)
    display_name = source.stem if source.suffix else source.name
    title = escape(display_name)
    index_links = [
        ("Overview", ROOT / "README.md"),
        ("Installation", ROOT / "INSTALL.md"),
        ("All actions", DOC_DIR / "ACTIONS.md"),
        ("Commands & settings", DOC_DIR / "commandconfig.md"),
        ("Formats", DOC_DIR / "FORMATS.md"),
        ("Development", ROOT / "DEVELOPMENT.md"),
    ]
    links = "\n".join(
        f'<a href="{escape(names[path.resolve()], quote=True)}">{escape(label)}</a>'
        for label, path in index_links if path.resolve() in names
    )
    source_label = escape(str(source.relative_to(ROOT)))
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light dark">
  <title>{title} · KIM6 Reference</title>
  <link rel="stylesheet" href="../work.css">
</head>
<body class="reference-page">
  <a class="skip-link" href="#main">Skip to main content</a>
  <header class="topbar">
    <div class="topbar-inner page-width">
      <a class="brand" href="../index.html"><span class="brand-name">KIM<span>6</span></span><span class="brand-divider" aria-hidden="true"></span><span class="brand-description">Documentation</span></a>
      <nav class="top-actions" aria-label="Reference navigation"><a href="../index.html">User guide</a><a class="top-action-primary" href="README.html">Overview</a></nav>
    </div>
  </header>
  <div class="reference-layout page-width">
    <aside class="reference-sidebar" aria-label="Documentation sections">
      <p class="nav-heading">REFERENCE</p>
      <nav aria-label="Reference pages">{links}</nav>
      <a class="back-link" href="../index.html">← Back to the visual guide</a>
    </aside>
    <main id="main" class="reference-content">
      <div class="reference-source">KIM6 DOCUMENTATION · {source_label}</div>
      <article class="markdown-body">
{main_html}
      </article>
    </main>
  </div>
  <footer class="site-footer"><div class="page-width footer-inner"><div class="footer-brand"><span class="footer-logo">KIM<span>6</span></span><p>Reference generated from authoritative Markdown.</p></div><div class="footer-meta"><p><a href="../index.html">Back to the user guide</a></p></div></div></footer>
</body>
</html>
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if HTML is missing or stale; do not modify files")
    args = parser.parse_args()
    if not shutil.which("pandoc"):
        parser.error("Pandoc is required to build the HTML manual (install the 'pandoc' package).")
    try:
        paths = sources()
        names = page_names(paths)
        renders = {OUTPUT_DIR / names[path.resolve()]: render(path, names) for path in paths}
        stale = []
        for path, content in renders.items():
            if path.exists() and path.read_text(encoding="utf-8") == content:
                continue
            stale.append(path)
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
        if args.check and stale:
            print("Out-of-date HTML reference pages:", file=sys.stderr)
            for path in stale:
                print(f"  {path.relative_to(ROOT)}", file=sys.stderr)
            print("Run: python3 tools/build_manual.py", file=sys.stderr)
            return 1
        print(f"{'Verified' if args.check else 'Generated'} {len(renders)} HTML reference pages" + (f" ({len(stale)} updated)" if not args.check else ""))
        return 0
    except (RuntimeError, OSError) as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
