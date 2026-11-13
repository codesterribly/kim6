#!/usr/bin/env python3
"""Generate disposable JPEG/XMP fixtures for the KIM6 browser qualification.

Requires ffmpeg and ExifTool. Generated images default to a disposable /tmp
directory and are never repository assets. The conflicting fixture deliberately
carries different embedded JPEG and adjacent sidecar XMP values; malformed
fixtures are intentional and are not standards-compliant images.
"""
import argparse
from pathlib import Path
import shutil
import subprocess


DEFAULT_OUTPUT_DIR = Path("/tmp/kim6-metadata-browser-fixtures")
COLORS = [
    ("complete.jpg", (30, 120, 210)),
    ("conflicting_sidecar.jpg", (220, 80, 30)),
    ("exif_only.jpg", (30, 170, 80)),
    ("xmp_only.jpg", (150, 50, 180)),
    ("missing_metadata.jpg", (240, 190, 20)),
    ("repeated_keywords.jpg", (20, 170, 180)),
    ("language_alternatives.jpg", (180, 90, 110)),
    ("long_description.jpg", (80, 80, 80)),
]


def run(args):
    subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def make_jpeg(root, name, color):
    width, height = 640, 420
    r, g, b = color
    # A smooth x/y pattern makes each disposable preview visibly distinct.
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            pixels.extend((min(255, r + x * 80 // width),
                           min(255, g + y * 70 // height),
                           max(0, b - x * 50 // width)))
    ppm = root / (name + ".ppm")
    ppm.write_bytes(f"P6\n{width} {height}\n255\n".encode() + pixels)
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(ppm), "-frames:v", "1",
         "-q:v", "2", str(root / name)])
    ppm.unlink()


def tags(root, filename, *values):
    run(["exiftool", "-overwrite_original", *values, str(root / filename)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR,
                        help=f"disposable output directory (default: {DEFAULT_OUTPUT_DIR})")
    root = parser.parse_args().output_dir.expanduser().resolve()
    if not shutil.which("ffmpeg") or not shutil.which("exiftool"):
        raise SystemExit("ffmpeg and ExifTool must be on PATH")
    root.mkdir(parents=True, exist_ok=True)
    for name, color in COLORS:
        make_jpeg(root, name, color)

    tags(root, "complete.jpg",
         "-Make=KIM6 Synthetic Camera", "-Model=Fixture X1",
         "-DateTimeOriginal=2024:03:14 09:26:53", "-ExposureTime=1/125",
         "-FNumber=2.8", "-ISO=200", "-FocalLength=50",
         "-LensModel=Fixture Prime 50mm", "-Artist=Élodie Photographer",
         "-IPTC:By-line=Élodie Photographer", "-IPTC:CopyrightNotice=© 2026 KIM6 Test Collection",
         "-IPTC:ObjectName=Harbor at dawn", "-IPTC:Caption-Abstract=Morning light over Montréal.",
         "-IPTC:Keywords=harbor", "-IPTC:Keywords+=dawn", "-IPTC:Keywords+=harbor",
         "-XMP-dc:Title-x-default=Harbor at dawn", "-XMP-dc:Title-fr=Port au lever du jour",
         "-XMP-dc:Description-x-default=Morning light over Montréal.\nA calm harbor.",
         "-XMP-dc:Description-fr=La lumière du matin sur Montréal.",
         "-XMP-dc:Creator=Élodie Photographer", "-XMP-dc:Subject=harbor",
         "-XMP-dc:Subject+=dawn", "-XMP-dc:Subject+=harbor",
         "-XMP-dc:Rights=© 2026 KIM6 Test Collection",
         "-XMP-xmpRights:UsageTerms-x-default=Use permitted for testing only.",
         "-XMP-iptcExt:LocationCreatedCity=Montréal",
         "-XMP-iptcExt:LocationCreatedCountryName=Canada")

    tags(root, "conflicting_sidecar.jpg", "-Make=Fixture Camera", "-Model=Conflict Body",
         "-XMP-dc:Description-x-default=Embedded description says blue sky.",
         "-XMP-dc:Subject=embedded", "-XMP-dc:Subject+=same")
    sidecar = root / "conflicting_sidecar.xmp"
    sidecar.write_text("<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<x:xmpmeta xmlns:x=\"adobe:ns:meta/\" xmlns:rdf=\"http://www.w3.org/1999/02/22-rdf-syntax-ns#\" "
        "xmlns:dc=\"http://purl.org/dc/elements/1.1/\">\n"
        "<rdf:RDF><rdf:Description rdf:about=\"\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\">"
        "<dc:description><rdf:Alt><rdf:li xml:lang=\"x-default\">Sidecar description says gray clouds.</rdf:li>"
        "</rdf:Alt></dc:description><dc:subject><rdf:Bag><rdf:li>sidecar</rdf:li>"
        "<rdf:li>same</rdf:li></rdf:Bag></dc:subject></rdf:Description></rdf:RDF></x:xmpmeta>\n",
        encoding="utf-8")
    run(["exiftool", "-overwrite_original", str(sidecar)])

    tags(root, "exif_only.jpg", "-Make=Fixture Camera", "-Model=EXIF Only 2", "-ISO=400",
         "-DateTimeOriginal=2022:11:05 16:10:00", "-Artist=Only EXIF creator")
    tags(root, "xmp_only.jpg", "-XMP-dc:Title-x-default=雪の山",
         "-XMP-dc:Description-x-default=Snow peaks with Unicode metadata.",
         "-XMP-dc:Creator=山田 花子", "-XMP-dc:Subject=雪", "-XMP-dc:Subject+=山")
    # missing_metadata.jpg intentionally remains a plain JPEG with no metadata.
    tags(root, "repeated_keywords.jpg", "-XMP-dc:Title=Repeated words",
         "-XMP-dc:Subject=orchid", "-XMP-dc:Subject+=orchid", "-XMP-dc:Subject+=purple",
         "-IPTC:Keywords=orchid", "-IPTC:Keywords+=orchid", "-IPTC:Keywords+=purple")
    tags(root, "language_alternatives.jpg", "-XMP-dc:Title-x-default=Morning",
         "-XMP-dc:Title-fr=Matin", "-XMP-dc:Title-ja=朝",
         "-XMP-dc:Description-x-default=First line.\nSecond line.",
         "-XMP-dc:Description-fr=Première ligne.\nDeuxième ligne.")
    long_text = "Long description start.\n" + ("Unicode test: café, 雪, résumé. " * 180) + "\nLong description end."
    tags(root, "long_description.jpg", "-XMP-dc:Description-x-default=" + long_text)

    # Deliberately malformed/unreadable files with image-like names.
    (root / "malformed.jpg").write_bytes(b"not a JPEG\x00ExifTool fixture error\n")
    valid = (root / "missing_metadata.jpg").read_bytes()
    (root / "truncated.jpg").write_bytes(valid[:len(valid) // 3])
    (root / "README.txt").write_text(
        "Synthetic KIM6 Metadata Browser qualification collection.\n"
        "All images were generated by this script; no personal images were used.\n"
        "malformed.jpg is arbitrary non-image data. truncated.jpg is a JPEG cut to one third.\n"
        "conflicting_sidecar.jpg intentionally conflicts with conflicting_sidecar.xmp in\n"
        "dc:Description and dc:Subject. These are intentional test conflicts.\n",
        encoding="utf-8")
    print(f"Generated {len(list(root.glob('*.jpg')))} JPEG fixtures plus one XMP sidecar in {root}")


if __name__ == "__main__":
    main()
