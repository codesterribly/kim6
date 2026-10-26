"""Documentation contracts against the dispatcher and Dolphin templates."""
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import unittest
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]


def menu_entries(path):
    entries = []
    for block in re.split(r"\n(?=\[Desktop Action )", path.read_text(encoding="utf-8")):
        if not block.startswith("[Desktop Action "):
            continue
        action_id = block.split("]", 1)[0][len("[Desktop Action "):]
        label = next((line.split("=", 1)[1] for line in block.splitlines()
                      if line.startswith(("_Name=", "Name="))), "")
        command = next((line[5:] for line in block.splitlines() if line.startswith("Exec=")), "")
        entries.append((path.name, action_id, label, command))
    return entries


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])


def markdown_slug(heading):
    heading = re.sub(r"`([^`]*)`", r"\1", heading)
    heading = re.sub(r"[^\w -]", "", heading.lower())
    return re.sub(r"\s+", "-", heading.strip())


class DocumentationContractTests(unittest.TestCase):
    def test_getting_started_examples_match_real_menu_actions_and_output_names(self):
        entries = {action_id: (menu_name, label, command)
                   for menu in sorted((ROOT / "src").glob("kim_*.desktop.in"))
                   for menu_name, action_id, label, command in menu_entries(menu)}
        guide = (ROOT / "docs/GETTING_STARTED.md").read_text(encoding="utf-8")
        expected = {
            "Resize1600": ("kim_compressandresize.desktop.in", "Resize (1600x1600 pixels)",
                           "kim_all resize --size 1600x1600 -- %F",
                           "KIM6 — Compress, resize and web export"),
            "Compress70": ("kim_compress.desktop.in", "JPEG quality: 70%",
                           "kim_all compress --quality 70 -- %F", "KIM6 — JPEG compression"),
            "ConvertJPG": ("kim_convertandrotate.desktop.in", "Convert to JPEG",
                           "kim_all convert --format jpg -- %F", "KIM6 — Convert and transform"),
            "StripGPS": ("kim_publication.desktop.in", "Remove GPS coordinates…",
                         "kim_all stripmeta --mode gps -- %F", "KIM6 — Publish and organize"),
        }
        for action_id, (menu_name, label, command, submenu) in expected.items():
            with self.subTest(action_id=action_id):
                self.assertEqual((menu_name, label, command), entries[action_id])
                self.assertIn(label, guide)
                self.assertIn(submenu, guide)
        for output_name in ("lake_resized.jpg", "lake_compressed.jpg", "garden.jpg", "trip_gps.jpg"):
            self.assertIn(output_name, guide)
        self.assertIn("choose **Create new**", guide)
        self.assertIn("selected originals unchanged", guide)

    def test_authoritative_inventory_matches_all_menu_ids_labels_and_execs(self):
        expected = [entry for menu in sorted((ROOT / "src").glob("kim_*.desktop.in"))
                    for entry in menu_entries(menu)]
        self.assertEqual(107, len(expected))
        inventory = (ROOT / "docs/ACTIONS.md").read_text(encoding="utf-8")
        rows = set(re.findall(r"^\| `([^`]+)` \| `([^`]+)` \| ([^|]+) \| `([^`]+)` \|$",
                              inventory, re.M))
        documented = {(menu, action_id, label, command)
                      for menu, action_id, label, command in expected}
        self.assertEqual(documented, rows)
        self.assertIn("107", inventory)

    def test_cli_reference_covers_every_dispatcher_route(self):
        dispatcher = (ROOT / "src/bin/kim_all").read_text(encoding="utf-8")
        main = dispatcher.split("\nmain() {", 1)[1].split("\n}\n\nif", 1)[0]
        routes = set(re.findall(r"^    ([a-z][a-z0-9]*)\)\s+", main, re.M))
        cli = (ROOT / "docs/CLI.md").read_text(encoding="utf-8")
        for route in routes:
            with self.subTest(route=route):
                self.assertRegex(cli, rf"(?m)^#{{1,6}} `{re.escape(route)}`$")

    def test_configuration_reference_covers_dispatcher_settings(self):
        config = (ROOT / "docs/CONFIGURATION.md").read_text(encoding="utf-8")
        documented = set(re.findall(r"^\| `(KIM_[A-Z0-9_]+)` \|", config, re.M))
        self.assertEqual({
            "KIM_CONFIG_FILE", "KIM_POLICY", "KIM_NAME_AFFIX_POSITION",
            "KIM_WEB_QUALITY", "KIM_WEB_FORMAT", "KIM_WEB_COLOR_MODE",
            "KIM_COPYRIGHT_CREATOR", "KIM_COPYRIGHT_NOTICE",
            "KIM_COPYRIGHT_USAGE_RIGHTS", "KIM_GIF_DELAY",
        }, documented)

    def test_documentation_links_and_html_anchors_resolve(self):
        parser = AnchorParser()
        html = (ROOT / "docs/index.html").read_text(encoding="utf-8")
        parser.feed(html)
        self.assertNotIn("<script", html.lower())
        self.assertIn('aria-label="Main navigation"', html)
        self.assertIn('href="#main"', html)
        self.assertEqual(1, len(re.findall(r"<h1(?:\s|>)", html, re.I)))
        for href in parser.links:
            if href.startswith(("https://", "http://", "mailto:")):
                continue
            if href.startswith("#"):
                self.assertIn(href[1:], parser.ids, href)
                continue
            target = (ROOT / "docs" / href.split("#", 1)[0]).resolve()
            self.assertTrue(target.is_relative_to((ROOT / "docs").resolve()), href)
            self.assertTrue(target.exists(), href)
            if "#" in href:
                linked = AnchorParser()
                linked.feed(target.read_text(encoding="utf-8"))
                self.assertIn(href.split("#", 1)[1], linked.ids, href)

    def test_archive_preserves_upstream_and_pre_overhaul_sources(self):
        for name in ("README.md", "INSTALL.md", "DEVELOPMENT.md", "index.html", "work.css"):
            with self.subTest(name=name):
                result = subprocess.run(
                    ["git", "--no-pager", "show", f"764c9fe:{'docs/' if name in ('index.html', 'work.css') else ''}{name}"],
                    cwd=ROOT, capture_output=True, check=True,
                )
                self.assertEqual(result.stdout, (ROOT / "docs/archive/upstream" / name).read_bytes())
                prior_path = ROOT / ("docs/" if name in ("index.html", "work.css") else "") / name
                prior = subprocess.run(
                    ["git", "--no-pager", "show", f"1278daf:{'docs/' if name in ('index.html', 'work.css') else ''}{name}"],
                    cwd=ROOT, capture_output=True, check=True,
                )
                self.assertEqual(prior.stdout,
                                 (ROOT / "docs/archive/upstream/pre-overhaul" / name).read_bytes())
                self.assertNotEqual(b"", prior_path.read_bytes())
        archive_index = (ROOT / "docs/archive/upstream/ARCHIVE.md").read_text(encoding="utf-8")
        self.assertIn("Original upstream documents", archive_index)
        self.assertIn("Pre-overhaul KIM6 snapshot", archive_index)

    def test_current_markdown_links_and_heading_anchors_resolve(self):
        markdown_files = [ROOT / "README.md", ROOT / "INSTALL.md", ROOT / "DEVELOPMENT.md"]
        markdown_files += sorted((ROOT / "docs").glob("*.md"))
        markdown_files.append(ROOT / "docs/archive/upstream/ARCHIVE.md")
        for source in markdown_files:
            content = source.read_text(encoding="utf-8")
            for match in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", content):
                target_ref = match.group(1).strip()
                if target_ref.startswith(("https://", "http://", "mailto:")):
                    continue
                target_path, _, fragment = target_ref.partition("#")
                target_path = unquote(target_path.split("?", 1)[0])
                target = (source.parent / target_path).resolve() if target_path else source
                with self.subTest(source=source.relative_to(ROOT), href=target_ref):
                    self.assertTrue(target.is_relative_to(ROOT), target_ref)
                    self.assertTrue(target.exists(), target_ref)
                    if fragment and target.suffix == ".md":
                        linked = target.read_text(encoding="utf-8")
                        target_slugs = {markdown_slug(m.group(1)) for m in
                                        re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", linked, re.M)}
                        self.assertIn(unquote(fragment), target_slugs, target_ref)


if __name__ == "__main__":
    unittest.main()
