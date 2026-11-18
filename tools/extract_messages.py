#!/usr/bin/env python3
"""Regenerate po/kimng.pot from active Bash, Python and desktop sources.

Requires GNU xgettext, msgcat and msgfmt. Run with --check to detect drift.
SOURCE_DATE_EPOCH overrides the default timestamp (the last Git commit time).
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "po/kimng.pot"


def run(*command):
    return subprocess.check_output(command, cwd=ROOT, text=True, encoding="utf-8")


def extract(directory):
    common = ["--from-code=UTF-8", "--sort-output", "--no-wrap",
              "--package-name=KIMng", "--package-version=development",
              "--copyright-holder=KIMng contributors",
              "--msgid-bugs-address=https://github.com/codesterribly/kim6/issues"]
    shell = directory / "shell.pot"
    python = directory / "python.pot"
    desktop = directory / "desktop.pot"
    run("xgettext", *common, "--language=Shell", "--keyword=gettext",
        "--output=" + str(shell), "src/bin/kim_all")
    sources = sorted(path.relative_to(ROOT).as_posix()
                     for path in (ROOT / "src/bin").glob("*.py"))
    run("xgettext", *common, "--language=Python", "--keyword=tr",
        "--keyword=N_", "--keyword=_", "--keyword=gettext",
        "--keyword=ngettext:1,2", "--output=" + str(python), *sources)

    # Read intltool-marked desktop keys directly, retaining the real source
    # path and line number instead of references to a temporary Python file.
    messages = {}
    for path in sorted((ROOT / "src").glob("kim_*.desktop.in")):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith(("_Name=", "_X-KDE-Submenu=")):
                value = line.split("=", 1)[1]
                if value:
                    messages.setdefault(value, []).append(f"{path.relative_to(ROOT)}:{number}")
    desktop.write_text(
        'msgid ""\nmsgstr ""\n"Content-Type: text/plain; charset=UTF-8\\n"\n\n' +
        "".join("#: " + " ".join(references) + "\nmsgid " +
                json.dumps(value, ensure_ascii=False) + '\nmsgstr ""\n\n'
                for value, references in sorted(messages.items())), encoding="utf-8")
    content = run("msgcat", "--use-first", "--sort-output", "--no-wrap",
                  str(shell), str(python), str(desktop))
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is None:
        epoch = run("git", "log", "-1", "--format=%ct").strip()
    date = datetime.fromtimestamp(int(epoch), timezone.utc).strftime("%Y-%m-%d %H:%M%z")
    content = re.sub(r'POT-Creation-Date: [^"\n]*',
                     lambda _: "POT-Creation-Date: " + date + r"\n", content)
    content = content.replace("# SOME DESCRIPTIVE TITLE.", "# KIMng translation template.")
    content = content.replace("# FIRST AUTHOR <EMAIL@ADDRESS>, YEAR.\n", "")
    result = directory / "kimng.pot"
    result.write_text(content, encoding="utf-8")
    run("msgfmt", "--check", "--output-file=" + os.devnull, str(result))
    return content


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    options = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="kimng-gettext-") as temporary:
        content = extract(Path(temporary))
    if options.check:
        # A new commit or a caller's timestamp override is not source drift.
        date_header = re.compile(r'^"POT-Creation-Date: .*\n', re.MULTILINE)
        if (not CATALOG.is_file() or
                date_header.sub("", CATALOG.read_text(encoding="utf-8")) !=
                date_header.sub("", content)):
            parser.exit(1, "po/kimng.pot is stale; run python3 -B tools/extract_messages.py\n")
        print("po/kimng.pot matches active sources; msgfmt --check passed")
    else:
        CATALOG.write_text(content, encoding="utf-8")
        print("Regenerated po/kimng.pot; msgfmt --check passed")


if __name__ == "__main__":
    main()
