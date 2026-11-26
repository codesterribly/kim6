"""Independent coverage of the KIMng runtime installation inventory."""

import ast
import os
from pathlib import Path, PurePosixPath
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


def inventory():
    command = r'''
set -euo pipefail
source "$1"

test "${#runtime_sources[@]}" -eq "${#runtime_files[@]}"
test "${#runtime_sources[@]}" -eq "${#runtime_modes[@]}"

for i in "${!runtime_files[@]}"; do
    printf 'file\t%s\t%s\t%s\n' \
        "${runtime_sources[$i]}" \
        "${runtime_files[$i]}" \
        "${runtime_modes[$i]}"
done

for name in "${menu_names[@]}"; do
    printf 'menu\t%s\n' "$name"
done

for name in "${retired_documentation_files[@]}"; do
    printf 'retired\t%s\n' "$name"
done
'''

    result = subprocess.run(
        [
            "bash", "-c", command, "bash",
            str(ROOT / "install_inventory.sh")
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )

    records = [
        line.split("\t")
        for line in result.stdout.splitlines()
    ]

    files = [
        tuple(row[1:])
        for row in records if row[0] == "file"
    ]

    menus = [
        row[1]
        for row in records if row[0] == "menu"
    ]

    retired = [
        row[1]
        for row in records if row[0] == "retired"
    ]

    return files, menus, retired


def independent_runtime_sources():
    """Enumerate active runtime directories, not installer declarations."""

    paths = {ROOT / "src/bin/kim_all"}

    paths.update(
        (ROOT / "src/bin").glob("*.py")
    )

    for directory in ("gallery", "recipes"):
        paths.update(
            path
            for path in (ROOT / "src" / directory).rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and not path.name.endswith((".bak", ".pyc", ".pyo"))
        )

    return {
        path.relative_to(ROOT).as_posix()
        for path in paths
    }


class InstallationInventoryTests(unittest.TestCase):

    def setUp(self):
        self.files, self.menus, self.retired = inventory()

        self.sources = {
            source for source, _, _ in self.files
        }

        self.destinations = {
            destination for _, destination, _ in self.files
        }

    def test_all_active_runtime_sources_are_packaged(self):
        expected = independent_runtime_sources()

        self.assertEqual(
            expected - self.sources,
            set(),
            "Active runtime source is missing from installation inventory"
        )

        for source in expected:
            destination = source.removeprefix("src/")

            self.assertIn(
                destination,
                self.destinations,
                source
            )

    def test_no_archives_or_local_backups_are_packaged(self):
        for source in self.sources:
            with self.subTest(source=source):
                self.assertNotIn(
                    "archive",
                    PurePosixPath(source).parts
                )

                self.assertFalse(
                    source.endswith((".bak", ".pyc", ".pyo"))
                )

    def test_all_menu_templates_are_packaged(self):
        expected = {
            path.name.removesuffix(".in")
            for path in (ROOT / "src").glob("*.desktop.in")
        }

        self.assertEqual(expected, set(self.menus))
        self.assertEqual(len(self.menus), len(expected))

    def test_inventory_paths_and_modes_are_valid(self):
        for source, destination, mode in self.files:
            with self.subTest(source=source):
                for value in (source, destination):
                    path = PurePosixPath(value)

                    self.assertFalse(path.is_absolute())
                    self.assertNotIn("..", path.parts)
                    self.assertNotIn("\\", value)

                path = ROOT / source

                self.assertTrue(path.is_file(), source)
                self.assertFalse(path.is_symlink(), source)

                expected_mode = (
                    "0755" if destination == "bin/kim_all"
                    else "0644"
                )

                self.assertEqual(expected_mode, mode)

    def test_inventory_has_no_duplicate_or_retired_destinations(self):
        self.assertEqual(len(self.files), len(self.sources))
        self.assertEqual(len(self.files), len(self.destinations))
        self.assertEqual(len(self.retired), len(set(self.retired)))

        self.assertFalse(
            self.destinations.intersection(self.retired)
        )

    def test_every_internal_python_import_is_packaged(self):
        modules = {
            path.stem
            for path in (ROOT / "src/bin").glob("*.py")
        }

        for source, _, _ in self.files:
            if not source.startswith("src/bin/"):
                continue

            if not source.endswith(".py"):
                continue

            tree = ast.parse(
                (ROOT / source).read_text(),
                filename=source
            )

            for node in ast.walk(tree):
                imported = []

                if isinstance(node, ast.Import):
                    imported = [
                        alias.name for alias in node.names
                    ]

                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported = [node.module]

                for name in imported:
                    module = name.split(".")[0]

                    if module in modules or module.startswith("kim_"):
                        self.assertIn(
                            f"bin/{module}.py",
                            self.destinations,
                            f"{source}:{node.lineno}: {module}"
                        )

    def test_public_documentation_is_packaged(self):
        expected = {
            "ABOUT",
            "LICENSE.md",
            "INSTALL.md",
            "README.md",
            "docs/ACTIONS.md",
            "docs/DEVELOPMENT.md",
            "docs/FORMATS.md",
            "docs/RECIPES.md",
            "docs/commandconfig.md",
            "docs/index.html",
            "docs/work.css",
            "docs/images/kimng-brand-icon.png",
            "docs/images/kimng-guide-icon.png",
        }

        expected.update(
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "docs/reference").glob("*.html")
        )

        expected.update(
            path.relative_to(ROOT).as_posix()
            for path in (ROOT / "docs/images/screenshots").glob("*.png")
        )

        self.assertFalse(
            expected - self.sources,
            expected - self.sources
        )


if __name__ == "__main__":
    unittest.main()
