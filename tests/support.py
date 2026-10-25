"""Owned workspaces for dispatcher subprocess tests; Python standard library only.

These helpers are for trusted tests of the current Bash dispatcher, not a kernel
sandbox for hostile scripts. Fixtures belong under Workspace.root or explicitly
registered temporary roots used for cross-filesystem tests.
"""
from pathlib import Path
from dataclasses import dataclass, field
import hashlib
import base64
import json
import os
import shutil
import signal
import stat
import subprocess
import tempfile
import unittest


@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str
    calls: list
    outputs: dict
    before_entries: dict = field(default_factory=dict)
    after_entries: dict = field(default_factory=dict)
    events: list = field(default_factory=list)

    @property
    def changed_entries(self):
        """Include deletion and metadata-only changes, without following links."""
        names = self.before_entries.keys() | self.after_entries.keys()
        absent = EntryState(False)
        return {
            name: (self.before_entries.get(name, absent), self.after_entries.get(name, absent))
            for name in names
            if self.before_entries.get(name, absent) != self.after_entries.get(name, absent)
        }


@dataclass(frozen=True)
class EntryState:
    exists: bool
    kind: str | None = None
    device: int | None = None
    inode: int | None = None
    size: int | None = None
    mtime_ns: int | None = None
    mode: int | None = None
    sha256: str | None = None
    link_target: str | None = None


class Workspace:
    def __init__(self):
        self._temporary = tempfile.TemporaryDirectory(prefix="kim6-test-", dir="/tmp")
        self._extra_temporaries = []
        self.root = Path(self._temporary.name).resolve()
        self.control = self.root / ".control"
        self.bin = self.control / "bin"
        self.bin.mkdir(parents=True)
        for directory in ("home", "config", "data", "cache", "runtime", "tmp"):
            (self.control / directory).mkdir(mode=0o700)
        self.production = Path(__file__).resolve().parents[1] / "src/bin/kim_all"
        self.dispatcher = self.control / "kim_all"
        shutil.copyfile(self.production, self.dispatcher)
        self.dispatcher.chmod(0o700)
        self.plan = self.control / "plan.json"
        self.plan.write_text(json.dumps({"responses": {}, "config": {}}))
        self.log = self.control / "calls.jsonl"
        self.log.touch()
        self.events = self.control / "events.jsonl"
        self.events.touch()
        adapter = self.control / "adapter.py"
        shutil.copyfile(Path(__file__).with_name("adapter.py"), adapter)
        adapter.chmod(0o700)
        self.tools = {
            "kdialog", "qdbus", "qdbus6", "kreadconfig6", "gettext", "magick",
            "convert", "mogrify", "montage", "identify", "exiftool", "pdfinfo", "pdftoppm", "ffmpeg",
            "ffprobe", "kmail", "thunderbird", "xdg-email", "xdg-open", "okular",
            "mktemp", "rm", "cp", "mv", "mkdir", "mkfifo", "touch", "chmod", "dirname", "awk",
            "basename", "cat", "date", "tr", "stat", "ln", "cmp", "sleep", "head", "grep", "cut", "od", "sort", "setsid",
        }
        for tool in self.tools:
            (self.bin / tool).symlink_to(adapter)
        (self.bin / "bash").symlink_to(shutil.which("bash"))
        self.env = {
            "HOME": str(self.control / "home"), "PATH": str(self.bin),
            "TMPDIR": str(self.control / "tmp"), "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8", "TZ": "UTC", "PYTHONDONTWRITEBYTECODE": "1",
            "XDG_CONFIG_HOME": str(self.control / "config"),
            "XDG_DATA_HOME": str(self.control / "data"),
            "XDG_CACHE_HOME": str(self.control / "cache"),
            "XDG_RUNTIME_DIR": str(self.control / "runtime"),
            "KIM_CONFIG_FILE": str(self.control / "config/kim_kdeimagemenu"),
            "KIM_TEST_ROOT": str(self.root),
        }
        Path(self.env["KIM_CONFIG_FILE"]).touch()

    def path(self, relative):
        path = self.root / relative
        roots = [self.root, *(Path(t.name) for t in self._extra_temporaries)]
        if not any(path.resolve().is_relative_to(root) for root in roots):
            raise ValueError("path escapes test workspace")
        return path

    def close(self):
        for temporary in self._extra_temporaries:
            temporary.cleanup()
        self._temporary.cleanup()

    def add_filesystem_root(self, parent):
        """Register another temporary fixture root for genuine EXDEV tests."""
        temporary = tempfile.TemporaryDirectory(prefix='.kim6-test-', dir=parent)
        self._extra_temporaries.append(temporary)
        self.env['KIM_TEST_EXTRA_ROOTS'] = json.dumps([t.name for t in self._extra_temporaries])
        return Path(temporary.name)

    def respond(self, tool, **response):
        """Script an external response: stdout/stderr/status and owned writes.

        writes maps workspace-relative filenames to text. It can deliberately
        produce nonempty output followed by failure, without running a codec.
        """
        if tool not in self.tools:
            raise ValueError("unknown adapter")
        plan = json.loads(self.plan.read_text())
        plan["responses"][tool] = response
        self.plan.write_text(json.dumps(plan))

    def sequence(self, tool, responses):
        """One scripted response per call; exhaustion is an adapter error."""
        if tool not in self.tools:
            raise ValueError("unknown adapter")
        plan = json.loads(self.plan.read_text())
        plan["responses"][tool] = list(responses)
        self.plan.write_text(json.dumps(plan))
        (self.control / (tool + ".index")).unlink(missing_ok=True)

    def configure(self, key, value):
        """Set a value returned by the isolated kreadconfig6 adapter."""
        plan = json.loads(self.plan.read_text())
        plan["config"][key] = value
        self.plan.write_text(json.dumps(plan))

    def respond_to(self, tool, argument, responses):
        """Route a response/sequence by one external argument, not call order."""
        if tool not in self.tools:
            raise ValueError("unknown adapter")
        plan = json.loads(self.plan.read_text())
        plan.setdefault("routes", {}).setdefault(tool, {})[argument] = responses
        self.plan.write_text(json.dumps(plan))
        tag = hashlib.sha256(argument.encode()).hexdigest()[:12]
        (self.control / f"{tool}.{tag}.index").unlink(missing_ok=True)

    def ppm(self, relative):
        """3x2 P6 fixture: red/green/blue above yellow/magenta/cyan."""
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"P6\n3 2\n255\n" + bytes.fromhex(
            "ff0000 00ff00 0000ff ffff00 ff00ff 00ffff"))
        return path

    def jpeg(self, relative):
        """Embedded 3x2 six-color JPEG; no installed encoder needed by K02.

        Encoded once from ppm() inside an owned workspace with ImageMagick.
        Tests copy these bytes, never transform repository fixture files.
        """
        data = (
            "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAMCAgMCAgMDAwMEAwMEBQgFBQQEBQoH"
            "BwYIDAoMDAsKCwsNDhIQDQ4RDgsLEBYQERMUFRUVDA8XGBYUGBIUFRT/2wBDAQME"
            "BAUEBQkFBQkUDQsNFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQU"
            "FBQUFBQUFBQUFBQUFBT/wAARCAACAAMDAREAAhEBAxEB/8QAFAABAAAAAAAA"
            "AAAAAAAAAAAAB//EAB4QAAMAAgEFAAAAAAAAAAAAAAECAwQFBgAHITEy/8QAFQEBAQ"
            "AAAAAAAAAAAAAAAAAABwj/xAAeEQEBAAICAgMAAAAAAAAAAAACAQMEBQYRMQcSIv/a"
            "AAwDAQACEQMRAD8AVX7T8I2mx29s3hugy7Ls82C0vq4OwnPJrOaAlflUVVUegqg"
            "DwB0s9G5Le0up8Ti1c7ButgVhVkqeINrxLP02klfaVqvm22yB83cvyXH983cOn"
            "svGKdd2FoyvJrYcmRWSyfZtJte00krbbb//2Q=="
        )
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(data, validate=True))
        return path

    def png(self, relative):
        """3x2 six-color RGB PNG built with the standard library, no encoder."""
        import struct
        import zlib
        def chunk(kind, data):
            return (struct.pack("!I", len(data)) + kind + data
                    + struct.pack("!I", zlib.crc32(kind + data)))
        pixels = bytes.fromhex("ff0000 00ff00 0000ff ffff00 ff00ff 00ffff")
        raw = b"\0" + pixels[:9] + b"\0" + pixels[9:]
        data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!IIBBBBB", 3, 2, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
        path = self.path(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def use_real_conversion(self):
        """Enable the narrow real encoder seam for tiny owned image fixtures."""
        executable = shutil.which("magick")
        if not executable:
            raise unittest.SkipTest("ImageMagick magick is unavailable")
        plan = json.loads(self.plan.read_text())
        plan["real_conversion"] = executable
        self.plan.write_text(json.dumps(plan))
        self.env["MAGICK_TEMPORARY_PATH"] = str(self.control / "tmp")
        self.env["MAGICK_THREAD_LIMIT"] = "1"

    def use_real_compression(self):
        """Enable only JPEG compression of bounded, test-owned fixtures."""
        executable = shutil.which("magick")
        if not executable:
            raise unittest.SkipTest("ImageMagick magick is unavailable")
        plan = json.loads(self.plan.read_text())
        plan["real_compression"] = executable
        self.plan.write_text(json.dumps(plan))
        self.env["MAGICK_TEMPORARY_PATH"] = str(self.control / "tmp")
        self.env["MAGICK_THREAD_LIMIT"] = "1"

    def shared_progress(self, body, *args):
        """Exercise shared progress helpers with the real dispatcher definitions."""
        source = self.dispatcher.read_text()
        entrypoint = '\nmain "$@"\n'
        if source.count(entrypoint) != 1:
            raise ValueError("dispatcher entrypoint changed")
        harness = self.control / "progress-helper"
        harness.write_text(source.replace(entrypoint, "\n") + "\nmk_workdir\n" + body + "\n")
        return self._run(["/bin/bash", str(harness), *map(str, args)])

    def use_real_stripmeta(self):
        """Run only the fixed metadata-removal command on owned fixtures."""
        executable = shutil.which("exiftool")
        if not executable:
            raise unittest.SkipTest("exiftool unavailable")
        plan = json.loads(self.plan.read_text())
        plan["real_stripmeta"] = executable
        self.plan.write_text(json.dumps(plan))

    def use_real_metadata_tools(self):
        """Check installed chmod/touch on owned staging entries."""
        plan = json.loads(self.plan.read_text())
        plan["real_metadata_tools"] = {name: shutil.which(name) for name in ("touch", "chmod", "exiftool")}
        if not all(plan["real_metadata_tools"].values()):
            raise unittest.SkipTest("chmod/touch unavailable")
        self.plan.write_text(json.dumps(plan))

    def metadata_fault(self, **options):
        """Inject a metadata producer failure or owned D-Bus disappearance."""
        plan = json.loads(self.plan.read_text())
        plan.update(options)
        self.plan.write_text(json.dumps(plan))

    def atomic_overwrite(self, destination):
        """Exercise unmodified K12 helpers independently of action migration."""
        source = self.dispatcher.read_text()
        entrypoint = '\nmain "$@"\n'
        if source.count(entrypoint) != 1:
            raise ValueError("dispatcher entrypoint changed")
        harness = self.control / "atomic-helper"
        harness.write_text(source.replace(entrypoint, "\n") + '''
mk_workdir
scratch="$(mktemp "$KIMDIR/atomic_XXXXXX.${1##*.}")"
rm -f -- "$scratch"
exiftool -all= -tagsfromfile "$1" -icc_profile -Orientation -o "$scratch" -- "$1" || exit "$?"
atomic_overwrite_file "$1" "$scratch"
''')
        return self._run(["/bin/bash", str(harness), str(destination)])

    def use_real_resize(self):
        """Enable only bounded synthetic fixture resizing with installed ImageMagick."""
        executable = shutil.which("magick")
        if not executable:
            raise unittest.SkipTest("ImageMagick magick is unavailable")
        plan = json.loads(self.plan.read_text())
        plan["real_resize"] = executable
        self.plan.write_text(json.dumps(plan))
        self.env["MAGICK_TEMPORARY_PATH"] = str(self.control / "tmp")
        self.env["MAGICK_THREAD_LIMIT"] = "1"

    def use_real_transform(self):
        """Run rotation/reflection only on small owned fixtures and private stages."""
        executable = shutil.which("magick")
        if not executable:
            raise unittest.SkipTest("ImageMagick unavailable")
        plan = json.loads(self.plan.read_text())
        plan["real_transform"] = executable
        self.plan.write_text(json.dumps(plan))
        self.env["MAGICK_TEMPORARY_PATH"] = str(self.control / "tmp")
        self.env["MAGICK_THREAD_LIMIT"] = "1"

    def use_real_magick(self):
        """Opt in to narrowly validated real PPM operations, never arbitrary CLI."""
        executable = shutil.which("magick")
        if not executable:
            raise unittest.SkipTest("optional real ImageMagick magick is unavailable")
        plan = json.loads(self.plan.read_text())
        plan["real_magick"] = executable
        self.plan.write_text(json.dumps(plan))

    def use_real_video_tools(self):
        """Run FFmpeg/ffprobe only on short, test-owned videos and stages."""
        tools = {name: shutil.which(name) for name in ("ffmpeg", "ffprobe")}
        if not all(tools.values()):
            raise unittest.SkipTest("FFmpeg and ffprobe are unavailable")
        plan = json.loads(self.plan.read_text())
        plan["real_video_tools"] = tools
        self.plan.write_text(json.dumps(plan))

    def use_real_slideshow_tools(self):
        self.use_real_video_tools()
        self.use_real_metadata_tools()
        executable = shutil.which("magick")
        if not executable:
            raise unittest.SkipTest("ImageMagick is unavailable")
        plan = json.loads(self.plan.read_text())
        plan["real_slideshow_magick"] = executable
        self.plan.write_text(json.dumps(plan))

    def use_real_publication_tools(self):
        """Run real PDF/TIFF/GIF producers and validators on tiny owned fixtures."""
        tools = {name: shutil.which(name) for name in ('magick', 'identify', 'pdfinfo', 'pdftoppm')}
        if not all(tools.values()):
            raise unittest.SkipTest('real publication tools are unavailable')
        plan = json.loads(self.plan.read_text())
        plan['real_publication_tools'] = tools
        self.plan.write_text(json.dumps(plan))
        self.env['MAGICK_TEMPORARY_PATH'] = str(self.control / 'tmp')
        self.env['MAGICK_THREAD_LIMIT'] = '1'

    def use_real_gallery_collage(self):
        """Run gallery and collage encoders on bounded owned PPM fixtures."""
        tools = {name: shutil.which(name) for name in ('magick', 'identify')}
        if not all(tools.values()):
            raise unittest.SkipTest('real gallery/collage image tools are unavailable')
        plan = json.loads(self.plan.read_text())
        plan['real_gallery_collage_tools'] = tools
        self.plan.write_text(json.dumps(plan))
        self.env['MAGICK_TEMPORARY_PATH'] = str(self.control / 'tmp')
        self.env['MAGICK_THREAD_LIMIT'] = '1'

    def use_real_web_email(self):
        """Run bounded synthetic-image web/email producers and validators."""
        tools = {name: shutil.which(name) for name in ('magick', 'identify')}
        if not all(tools.values()):
            raise unittest.SkipTest('real web/email image tools are unavailable')
        plan = json.loads(self.plan.read_text())
        plan['real_web_email_tools'] = tools
        self.plan.write_text(json.dumps(plan))
        self.env['MAGICK_TEMPORARY_PATH'] = str(self.control / 'tmp')
        self.env['MAGICK_THREAD_LIMIT'] = '1'

    def image_info(self, path):
        executable = shutil.which('identify')
        if not executable:
            raise unittest.SkipTest('ImageMagick identify unavailable')
        result = subprocess.run([executable, '-regard-warnings', '-format', '%m|%w|%h', '-'],
                                input=Path(path).read_bytes(), capture_output=True, text=False, timeout=10)
        if result.returncode:
            raise AssertionError(result.stderr.decode(errors='replace'))
        format_name, width, height = result.stdout.decode().split('|')
        return format_name, int(width), int(height)

    def use_real_mv(self):
        """Exercise only installed rename-only forms on test-owned paths."""
        executable = shutil.which("mv")
        if not executable:
            raise unittest.SkipTest("mv is unavailable")
        plan = json.loads(self.plan.read_text())
        plan["real_mv"] = executable
        self.plan.write_text(json.dumps(plan))

    def use_real_rename_files(self):
        """Exercise installed copy/link/unlink/stat/compare on owned fixtures."""
        plan = json.loads(self.plan.read_text())
        plan['real_rename_files'] = {name: shutil.which(name) for name in ('cp', 'ln', 'rm', 'stat', 'cmp')}
        if not all(plan['real_rename_files'].values()):
            raise unittest.SkipTest('rename filesystem utilities unavailable')
        plan['real_rename_exif'] = shutil.which('exiftool')
        if not plan['real_rename_exif']:
            raise unittest.SkipTest('ExifTool unavailable')
        self.plan.write_text(json.dumps(plan))

    @staticmethod
    def _read_without_atime(path):
        try:
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOATIME", 0))
        except OSError:
            return path.read_bytes()
        with os.fdopen(descriptor, "rb") as source:
            return source.read()

    def _snapshot(self):
        snapshot = {}
        for path in self.root.rglob("*"):
            if (path.relative_to(self.root).parts[0] == ".control" or path.is_symlink()
                    or not path.is_file() or not path.resolve().is_relative_to(self.root)):
                continue
            payload = self._read_without_atime(path)
            snapshot[str(path.relative_to(self.root))] = payload
        return snapshot

    def observe(self, relative):
        """lstat an owned entry, including dangling links; never hash a referent.

        Access time is deliberately excluded: reading fixtures may update it.
        Parents must resolve inside the workspace, but the final symlink is
        observed as an entry even if it points outside or no longer resolves.
        """
        path = Path(os.path.abspath(self.root / relative))
        roots = [self.root, *(Path(t.name) for t in self._extra_temporaries)]
        if not any(path.is_relative_to(root) and path.parent.resolve().is_relative_to(root) for root in roots):
            raise ValueError("observation escapes test workspace")
        try:
            info = path.lstat()
        except FileNotFoundError:
            return EntryState(False)
        kind = ("symlink" if stat.S_ISLNK(info.st_mode) else
                "file" if stat.S_ISREG(info.st_mode) else
                "directory" if stat.S_ISDIR(info.st_mode) else "other")
        return EntryState(
            True, kind, info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            stat.S_IMODE(info.st_mode),
            hashlib.sha256(self._read_without_atime(path)).hexdigest() if kind == "file" else None,
            os.readlink(path) if kind == "symlink" else None,
        )

    def _entries(self):
        return {
            str(path.relative_to(self.root)): self.observe(path)
            for path in self.root.rglob("*")
            if path.relative_to(self.root).parts[0] != ".control"
        }

    def _run(self, argv):
        before = self._snapshot()
        before_entries = self._entries()
        first_call = len(self.log.read_text().splitlines())
        first_event = len(self.events.read_text().splitlines())
        process = subprocess.Popen(argv, cwd=self.root, env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            raise
        finally:
            # No owned background child may outlive the test invocation.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        after = self._snapshot()
        after_entries = self._entries()
        calls = [json.loads(line) for line in self.log.read_text().splitlines()[first_call:]]
        events = [json.loads(line) for line in self.events.read_text().splitlines()[first_event:]]
        return Result(process.returncode, stdout.decode("utf-8", "surrogateescape"),
                      stderr.decode("utf-8", "surrogateescape"), calls,
                      {name: data for name, data in after.items() if before.get(name) != data},
                      before_entries, after_entries, events)

    def dispatch(self, *args):
        for argument in args:
            if str(argument).startswith("/"):
                self.path(argument)
        return self._run([str(self.dispatcher), *map(str, args)])

    def command(self, tool, *args):
        if tool not in self.tools:
            raise ValueError("unknown adapter")
        return self._run([str(self.bin / tool), *map(str, args)])
