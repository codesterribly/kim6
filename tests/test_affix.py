"""K16/A15 filename placement through the dispatcher boundary."""
import base64
import unittest
from support import Workspace


class AffixTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Workspace()
        self.addCleanup(self.workspace.close)
        self.workspace.env["KIM_POLICY"] = "create"
        self.workspace.env["KIM_WEB_FORMAT"] = "keep"
        self.workspace.respond_to("kdialog", "--inputbox", [
            {"stdout": "3x2\n"}, {"stdout": "75\n"},
        ])

    def run_action(self, action, sources, destination=None, payload=None):
        payload = sources[0].read_bytes() if payload is None else payload
        self.workspace.respond("exiftool" if action == "stripmeta" else "magick",
                               output_base64=base64.b64encode(payload).decode(),
                               **({"stdout": "3 2\n"} if action == "resize" else {}))
        destination = destination or sources[0].parent
        args = {"webexport": (destination,), "compress": ("75", destination),
                "resize": ("3x2", destination), "stripmeta": ()}[action]
        result = self.workspace.dispatch(action, *args, *sources)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(any(e["tool"] in ("magick", "exiftool") and e["status"] == 0
                            for e in result.events), "producer was not exercised")
        return result

    def test_explicit_prefix_webexport(self):
        source = self.workspace.jpeg("input/photo.jpg")
        self.workspace.env["KIM_NAME_AFFIX_POSITION"] = "prefix"
        result = self.run_action("webexport", [source])
        self.assertEqual(set(result.outputs), {"input/web_photo.jpg"})
        self.assertEqual(result.outputs["input/web_photo.jpg"], source.read_bytes())


# Literal expected names are independent examples from the approved naming rules.
NAMES = {
    "webexport": ("web_photo.part 雪.jpg", "photo.part 雪_web.jpg"),
    "compress": ("compressed_photo.part 雪.jpg", "photo.part 雪_compressed.jpg"),
    "resize": ("resized_photo.part 雪.jpg", "photo.part 雪_resized.jpg"),
    "stripmeta": ("stripped_photo.part 雪.jpg", "photo.part 雪_stripped.jpg"),
}
SETTINGS = {
    "AFF1_default": (None, None, 1),
    "AFF2_prefix": ("prefix", None, 0),
    "AFF3_suffix": ("suffix", None, 1),
    "AFF4_env_prefix_wins": ("prefix", "suffix", 0),
    "AFF5_env_suffix_wins": ("suffix", "prefix", 1),
    "AFF6_config_prefix": (None, "prefix", 0),
    "AFF6_config_suffix": (None, "suffix", 1),
}


def naming_case(action, env, config, position, scenario="ordinary"):
    def test(self):
        if env is not None:
            self.workspace.env["KIM_NAME_AFFIX_POSITION"] = env
        if config is not None:
            self.workspace.configure("NAME_AFFIX_POSITION", config)
        source = self.workspace.jpeg("input/photo.part 雪.jpg")
        before = self.workspace.observe(source)
        destination = source.parent
        if scenario in ("alternate", "batch") and action != "stripmeta":
            destination = self.workspace.path("exports")
            destination.mkdir()
        expected = NAMES[action][position]
        sources = [source]
        protected = {}
        names = {str((destination / expected).relative_to(self.workspace.root))}
        if scenario == "collision":
            occupied = destination / expected
            occupied.write_bytes(b"unrelated existing export")
            separator = "-" if action == "stripmeta" else "_"
            numbered = destination / (expected[:-4] + separator + "1.jpg")
            numbered.write_bytes(b"another existing export")
            protected = {path: self.workspace.observe(path) for path in (occupied, numbered)}
            names = {str((destination / (expected[:-4] + separator + "2.jpg"))
                         .relative_to(self.workspace.root))}
        elif scenario == "batch":
            second = self.workspace.jpeg("other/photo.part 雪.jpg")
            sources.append(second)
            protected[second] = self.workspace.observe(second)
            if action == "stripmeta":
                names.add("other/" + expected)
            else:
                names.add("exports/" + expected[:-4] + "_1.jpg")
        elif scenario == "overwrite":
            self.workspace.env["KIM_POLICY"] = "overwrite"
            names = {"input/photo.part 雪.jpg"}
        payload = b"processed image bytes" if scenario == "overwrite" else source.read_bytes()
        if action in ("compress", "resize") and scenario == "overwrite":
            # Naming still requires changed bytes, now a valid JPEG for K19/K20.
            # A JPEG COM marker changes the fixture without requiring an encoder.
            original = source.read_bytes()
            payload = original[:2] + b"\xff\xfe\x00\x06K19!" + original[2:]
        if action == "stripmeta" and scenario == "overwrite":
            # Model lossless comment removal with valid JPEG bytes.
            payload = source.read_bytes()
            source.write_bytes(payload[:2] + b"\xff\xfe\x00\x06K22!" + payload[2:])
        result = self.run_action(action, sources, destination, payload=payload)
        if scenario == "overwrite":
            self.assertEqual(list(source.parent.iterdir()), [source])
            self.assertEqual(source.read_bytes(), payload)
            self.assertEqual(set(result.outputs), names)
        else:
            self.assertEqual(set(result.outputs), names)
            self.assertEqual(self.workspace.observe(source), before)
            self.assertTrue(all(data == source.read_bytes() for data in result.outputs.values()))
        for path, state in protected.items():
            self.assertEqual(self.workspace.observe(path), state)
    return test


for action in NAMES:
    for requirement, (env, config, position) in SETTINGS.items():
        setattr(AffixTests, "test_" + requirement + "_" + action,
                naming_case(action, env, config, position))
    for position, mode in enumerate(("prefix", "suffix")):
        for requirement, scenario in (("AFF7_collisions", "collision"),
                                      ("AFF8_batch_duplicate_basenames", "batch"),
                                      ("AFF9_alternate_destination", "alternate")):
            if action == "stripmeta" and scenario == "alternate":
                continue  # stripmeta has no output-directory argument.
            setattr(AffixTests, "test_" + requirement + "_" + mode + "_" + action,
                    naming_case(action, mode, None, position, scenario))
        if action != "webexport":
            setattr(AffixTests, "test_AFF11_overwrite_exclusion_" + mode + "_" + action,
                    naming_case(action, mode, None, position, "overwrite"))


def rename_case(position):
    def test(self):
        self.workspace.env["KIM_NAME_AFFIX_POSITION"] = position
        source = self.workspace.jpeg("input/PHOTO.JPG")
        before = self.workspace.observe(source)
        result = self.workspace.dispatch("rename", "lowercase", source)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(result.outputs), {"input/photo.JPG"})
        self.assertEqual(self.workspace.observe(source), before)
    return test


for position in ("prefix", "suffix"):
    setattr(AffixTests, "test_AFF12_rename_exclusion_" + position, rename_case(position))


def extension_case(action, extension, expected):
    def test(self):
        self.workspace.env["KIM_NAME_AFFIX_POSITION"] = "prefix"
        source = self.workspace.ppm("input/photo.part 雪" + extension)
        if action == "webexport":
            self.workspace.env["KIM_WEB_FORMAT"] = "webp"
        result = self.run_action(action, [source])
        self.assertEqual(set(result.outputs), {"input/" + expected})
    return test


for action, extension, expected in (
    ("webexport", ".ppm", "web_photo.part 雪.webp"),
    ("resize", ".ppm", "resized_photo.part 雪.ppm"),
    ("stripmeta", ".ppm", "stripped_photo.part 雪.ppm"),
):
    setattr(AffixTests, "test_AFF10_output_extension_" + action,
            extension_case(action, extension, expected))


def web_format_case(position, fmt, expected):
    def test(self):
        source = self.workspace.jpeg("input/photo.jpg")
        self.workspace.env.update(KIM_NAME_AFFIX_POSITION=position,
                                  KIM_WEB_FORMAT=fmt, KIM_POLICY="overwrite")
        before = self.workspace.observe(source)
        result = self.run_action("webexport", [source])
        self.assertEqual(set(result.outputs), {"input/" + expected})
        self.assertEqual(self.workspace.observe(source), before)
    return test


for position, cases in (
    ("prefix", (("jpg", "web_photo.jpg"), ("webp", "web_photo.webp"),
                ("avif", "web_photo.avif"), ("keep", "web_photo.jpg"))),
    ("suffix", (("jpg", "photo_web.jpg"), ("webp", "photo_web.webp"),
                ("avif", "photo_web.avif"), ("keep", "photo_web.jpg"))),
):
    for fmt, expected in cases:
        setattr(AffixTests, "test_AFF10_AFF11_web_overwrite_" + position + "_" + fmt,
                web_format_case(position, fmt, expected))


def extensionless_case(action, position, expected):
    def test(self):
        source = self.workspace.ppm("input/photo 雪")
        self.workspace.env["KIM_NAME_AFFIX_POSITION"] = position
        result = self.run_action(action, [source])
        self.assertEqual(set(result.outputs), {"input/" + expected})
    return test


for action, position, expected in (
    ("resize", "prefix", "resized_photo 雪"),
    ("resize", "suffix", "photo 雪_resized"),
    ("stripmeta", "prefix", "stripped_photo 雪"),
    ("stripmeta", "suffix", "photo 雪_stripped"),
    ("webexport", "prefix", "web_photo 雪.jpg"),
    ("webexport", "suffix", "photo 雪_web.jpg"),
):
    setattr(AffixTests, "test_AFF10_extensionless_" + action + "_" + position,
            extensionless_case(action, position, expected))


if __name__ == "__main__":
    unittest.main()
