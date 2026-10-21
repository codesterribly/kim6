#!/usr/bin/python3
"""External-command adapters. Never forward media or desktop calls by default.

Unknown invocations fail closed. Writes stay within registered, owned fixture roots.
Filesystem adapters are deliberately narrow: extend them with tests when needed.
"""
import json
import base64
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


ROOT = Path(os.environ["KIM_TEST_ROOT"]).resolve()
CONTROL = ROOT / ".control"
EFFECTS = {}


def owned(value):
    path = Path(value)
    if not path.is_absolute():
        path = Path.cwd() / path
    roots = [ROOT, *(Path(p).resolve() for p in json.loads(os.environ.get('KIM_TEST_EXTRA_ROOTS', '[]')))]
    if not any(path.resolve().is_relative_to(root) for root in roots):
        raise ValueError("adapter refused path outside test workspace")
    if path.resolve() in roots:
        raise ValueError("adapter refused workspace root operation")
    return path


def interrupt_progress(state):
    """Inject one progress outcome only within this synthetic workspace."""
    if state not in ('cancelled', 'gone', 'query_failed', 'owner_failed', 'malformed'):
        raise ValueError("unknown progress interruption")
    (CONTROL / "progress-state").write_text(state)
    EFFECTS["progress_interruption"] = state


def main():
    tool, args = Path(sys.argv[0]).name, sys.argv[1:]
    if tool == "sleep":
        if args != ["0.1"]:
            raise ValueError("test adapter only permits the bounded process-grace delay")
        time.sleep(0.1)
        return 0
    with (CONTROL / "calls.jsonl").open("a") as stream:
        stream.write(json.dumps({"tool": tool, "argv": args}, ensure_ascii=True) + "\n")
    plan = json.loads((CONTROL / "plan.json").read_text())
    response = plan["responses"].get(tool)
    counter_name = tool
    for argument, routed in plan.get("routes", {}).get(tool, {}).items():
        if argument in args:
            response = routed
            counter_name += "." + hashlib.sha256(argument.encode()).hexdigest()[:12]
            break
    # Profile validation is independent of scripted metadata producers.
    profile_query = ["-j", "-b", "-f", "-a", "-G1:4", "-ICC_Profile", "--"]
    if tool == "exiftool" and args[:-1] == profile_query and "-ICC_Profile" not in plan.get("routes", {}).get(tool, {}):
        fixture = owned(args[-1])
        if fixture.stat().st_size > 8388608:
            raise ValueError("profile fixture exceeds owned test bound")
        executable = shutil.which("exiftool", path=os.defpath)
        if not executable:
            raise ValueError("profile validator unavailable")
        return subprocess.run([executable, *args], timeout=10).returncode
    if (tool == "exiftool" and args[:3] == ["-b", "-ICC_Profile", "--"]
            and len(args) == 4 and response is None):
        fixture = owned(args[3])
        if fixture.stat().st_size > 8388608:
            raise ValueError("ICC profile fixture exceeds owned test bound")
        executable = shutil.which("exiftool", path=os.defpath)
        if not executable:
            raise ValueError("test ICC profile reader is unavailable")
        return subprocess.run([executable, *args], timeout=10,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    # Validate the D-Bus boundary even when a response has been scripted.
    if tool in ("qdbus", "qdbus6"):
        references = plan.get("progress_references", [plan.get("progress_reference", "org.kde.kdialog-test /ProgressDialog")])
        owner_query = (len(args) == 4 and args[:3] == ["org.freedesktop.DBus",
            "/org/freedesktop/DBus", "org.freedesktop.DBus.NameHasOwner"]
            and any(args[3] == reference.split()[0] for reference in references))
        if not owner_query and (len(args) < 3 or not any(args[:2] == reference.split() for reference in references)):
            raise ValueError("qdbus requires separate service and object path")
        method = args[2]
        interface = "org.kde.kdialog.ProgressDialog"
        valid = (owner_query or (method in ("wasCancelled", "close") and len(args) == 3)
                 or (method == "showCancelButton" and len(args) == 4 and args[3] in ("true", "false"))
                 or (method == "setLabelText" and len(args) == 4)
                 or (method == "org.freedesktop.DBus.Properties.Set" and len(args) == 6
                     and args[3] == interface and
                     ((args[4] == "autoClose" and args[5] in ("true", "false"))
                      or (args[4] == "value" and args[5].isdecimal()))))
        if not valid:
            raise ValueError("qdbus method argument contract mismatch")
        if (not owner_query and method == "org.freedesktop.DBus.Properties.Set" and
                len(args) == 6 and args[4:] == ["value", "1"] and
                plan.get("video_interrupt_after_first_item")):
            (CONTROL / "progress-gone").touch()
            return 0
    # A producer can remove only this workspace's simulated dialog service.
    if tool in ("qdbus", "qdbus6") and (CONTROL / "progress-gone").exists():
        if owner_query:
            print("false")
            return 0
        sys.stderr.write("ServiceUnknown: owned simulated service disappeared\n")
        return 2
    if tool in ("qdbus", "qdbus6") and (CONTROL / "progress-state").exists():
        state = (CONTROL / "progress-state").read_text()
        if owner_query:
            if state == "owner_failed":
                return 2
            print("false" if state == "gone" else "true")
            return 0
        if state == "gone" or (args[2] == "wasCancelled" and state in ("query_failed", "owner_failed")):
            return 2
        if args[2] == "wasCancelled":
            print("true" if state == "cancelled" else "unexpected")
            return 0
    if tool in ("qdbus", "qdbus6") and args[2] == "wasCancelled" and plan.get("metadata_cancel_after_stage"):
        if any(ROOT.rglob(".kim6-stage.*")):
            print("true")
            return 0
    if tool == "magick" and "real_magick" in plan and response is None:
        return real_magick(plan["real_magick"], args)
    if (tool == "magick" and "real_conversion" in plan and response is None
            and args == ["-list", "format"]):
        return subprocess.run([plan["real_conversion"], *args], timeout=10,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if tool == "magick" and "real_conversion" in plan and response is None:
        return real_conversion(plan["real_conversion"], args)
    if tool == "exiftool" and "real_web_email_tools" in plan and response is None:
        return real_web_email_tool(plan["real_web_email_tools"], tool, args)
    if tool == "exiftool" and "real_conversion" in plan and response is None:
        executable = shutil.which("exiftool", path=os.defpath)
        for value in args:
            path = value.split("<=", 1)[-1] if "<=" in value else value
            if path != "--" and path.startswith("/"):
                owned(path)
        return subprocess.run([executable, *args], timeout=15,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if tool == "cmp" and "real_web_email_tools" in plan and response is None:
        for value in args:
            if value != "--" and value.startswith("/"):
                candidate = Path(value)
                if candidate.is_relative_to(ROOT):
                    owned(candidate)
        executable = shutil.which("cmp", path=os.defpath)
        return subprocess.run([executable, *args], timeout=10,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if tool == "cmp" and "real_conversion" in plan and response is None:
        for value in args:
            if value != "--" and value.startswith("/"):
                owned(value)
        return subprocess.run([shutil.which("cmp", path=os.defpath), *args], timeout=10,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if tool in ("head", "grep", "cut", "od") and response is None:
        executable = shutil.which(tool, path=os.defpath)
        if tool in ("head", "od"):
            path = owned(args[-1])
            if path.stat().st_size > 8388608:
                raise ValueError("format-probe fixture exceeds test bound")
            if tool == "head" and args[:2] != ["-c", "1048576"]:
                raise ValueError("APNG header read exceeded the approved prefix")
        else:
            payload = sys.stdin.buffer.read(1048577)
            if len(payload) > 1048576:
                raise ValueError("format-probe input exceeds its one-megabyte bound")
            result = subprocess.run([executable, *args], input=payload, capture_output=True,
                                    timeout=10, env=dict(os.environ, PATH=os.defpath))
            sys.stdout.buffer.write(result.stdout)
            sys.stderr.buffer.write(result.stderr)
            return result.returncode
        return subprocess.run([executable, *args], timeout=10,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if tool == "identify" and response is None:
        executable = shutil.which("identify", path=os.defpath)
        if executable and args and "--" in args and args[-1] != "-":
            owned(args[-1])
            return subprocess.run([executable, *args], timeout=15,
                                  env=dict(os.environ, PATH=os.defpath)).returncode
    if tool == "magick" and "real_compression" in plan and response is None:
        return real_compression(plan["real_compression"], args)
    if tool == "magick" and "real_resize" in plan and response is None:
        return real_resize(plan["real_resize"], args)
    if tool == "magick" and "real_transform" in plan and response is None:
        return real_transform(plan["real_transform"], args)
    if tool in ("ffmpeg", "ffprobe") and "real_video_tools" in plan and response is None:
        return real_video_tool(plan["real_video_tools"], tool, args, plan)
    if tool == "exiftool" and "real_video_tools" in plan and response is None:
        source = owned(args[-1])
        return subprocess.run([shutil.which("exiftool", path=os.defpath), *args], timeout=15,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if "real_publication_tools" in plan and tool in ("magick", "identify", "pdfinfo", "pdftoppm") and response is None:
        return real_publication_tool(plan["real_publication_tools"], tool, args)
    if "real_web_email_tools" in plan and tool in ("magick", "identify", "exiftool") and response is None:
        return real_web_email_tool(plan["real_web_email_tools"], tool, args)
    if "real_gallery_collage_tools" in plan and tool in ("magick", "identify") and response is None:
        return real_gallery_collage_tool(plan["real_gallery_collage_tools"], tool, args)
    if tool == "exiftool" and "real_stripmeta" in plan and response is None:
        return real_stripmeta(plan["real_stripmeta"], args)
    if isinstance(response, list):
        counter = CONTROL / (counter_name + ".index")
        index = int(counter.read_text()) if counter.exists() else 0
        if index >= len(response):
            raise ValueError("scripted responses exhausted for " + tool)
        counter.write_text(str(index + 1))
        response = response[index]
    if response and response.get("passthrough"):
        if "interrupt" in response:
            interrupt_progress(response["interrupt"])
        for name, content in response.get("writes", {}).items():
            path = owned(ROOT / name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        response = None
        if tool == "magick" and "real_transform" in plan:
            return real_transform(plan["real_transform"], args)
        if tool == "magick" and "real_publication_tools" in plan:
            return real_publication_tool(plan["real_publication_tools"], tool, args)
        if tool == "magick" and "real_gallery_collage_tools" in plan:
            return real_gallery_collage_tool(plan["real_gallery_collage_tools"], tool, args)
        if tool in ("magick", "identify") and "real_web_email_tools" in plan:
            return real_web_email_tool(plan["real_web_email_tools"], tool, args)
    if tool == "mv" and "real_mv" in plan and response is None:
        if args in (["--help"], ["--version"]):
            return subprocess.call([plan["real_mv"], *args])
        if len(args) != 5 or args[2] != "--" or args[:2] not in (
                ["--no-copy", "-fT"], ["--exchange", "-T"]):
            raise ValueError("real mv requires a rename-only publication form")
        for value in args[3:]:
            owned(value)
        if plan.get("metadata_publication_fail"):
            return 74
        return subprocess.call([plan["real_mv"], *args])
    if response is not None:
        if tool == "ffmpeg" and "-progress" in args:
            progress_path = owned(args[args.index("-progress") + 1])
            with progress_path.open("wb") as stream:
                stream.write(b"out_time_ms=100000\nprogress=end\n")
        if tool == "kdialog" and any(flag in args for flag in (
                "--getexistingdirectory", "--getsavefilename")) and response.get("stdout", "").strip():
            owned(response["stdout"].strip())
        for name, content in response.get("writes", {}).items():
            path = owned(ROOT / name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        if "output_base64" in response:
            if tool not in ("magick", "convert", "montage", "mogrify", "exiftool", "cp", "ffmpeg"):
                raise ValueError("output injection unsupported for " + tool)
            output = args[args.index("-o") + 1] if tool == "exiftool" else args[-1]
            if tool == "magick":
                if ":" in output:
                    output = output.split(":", 1)[1]
            path = owned(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(response["output_base64"], validate=True))
            EFFECTS["output"] = str(path)
        if "interrupt" in response:
            interrupt_progress(response["interrupt"])
        if response.get("disappear_progress"):
            (CONTROL / "progress-gone").touch()
            EFFECTS["progress_service_disappeared"] = True
        if response.get("cancel"):
            (CONTROL / "cancelled").touch()
            EFFECTS["cancel_requested"] = True
        if response.get("barrier"):
            barrier = owned(CONTROL / ("barrier-" + response["barrier"]))
            barrier.mkdir(exist_ok=True)
            (barrier / str(os.getpid())).touch()
            deadline = time.monotonic() + 5
            while len(list(barrier.iterdir())) < 2:
                if time.monotonic() > deadline:
                    raise ValueError("barrier timed out")
                time.sleep(0.01)
        sys.stdout.write(response.get("stdout", ""))
        sys.stderr.write(response.get("stderr", ""))
        return response.get("status", 0)
    if tool in plan.get('real_rename_files', {}) and not (tool == 'rm' and '-rf' in args):
        if tool == 'stat':
            if len(args) != 4 or args[0] != '-c' or args[2] != '--':
                raise ValueError('unsupported rename stat')
            owned(args[-1])
        else:
            forms = {'cp': ['--preserve=mode,ownership,timestamps,xattr', '--'], 'ln': ['-T', '--'], 'cmp': ['-s', '--']}
            if tool == 'rm':
                values = args[2:] if args[:2] == ['-f', '--'] else args[1:] if args[:1] == ['--'] else []
                if len(values) != 1:
                    raise ValueError('unsupported rename removal')
            else:
                if args[:2] != forms[tool] or len(args) != 4:
                    raise ValueError('unsupported rename filesystem command')
                values = args[2:]
            for value in values:
                owned(value)
            if tool == 'cp' and not Path(args[-1]).parent.name.startswith('.kim6-stage.'):
                raise ValueError('rename copies require private staging')
        return subprocess.run([plan['real_rename_files'][tool], *args], timeout=10).returncode
    if tool == 'exiftool' and 'real_rename_exif' in plan:
        if not (len(args) == 6 and args[0] == '-s3' and args[1] in
                ('-DateTimeOriginal', '-CreateDate', '-ModifyDate') and args[2] == '-d' and args[4] == '--'):
            raise ValueError('unsupported rename EXIF query')
        owned(args[-1])
        return subprocess.run([plan['real_rename_exif'], *args], timeout=10).returncode
    if tool in plan.get("real_metadata_tools", {}):
        if tool == "exiftool":
            for value in args:
                if value == "--":
                    continue
                candidate = value.split("<=", 1)[-1]
                if candidate.startswith("/") and Path(candidate).exists():
                    owned(candidate)
            if "-o" in args:
                destination = owned(args[args.index("-o") + 1])
                if destination.exists() or destination.is_symlink():
                    raise ValueError("metadata output must be an unused owned stage")
                if plan.get("metadata_fail_output"):
                    return int(plan["metadata_fail_output"])
        elif tool == "touch" and len(args) == 4 and args[0] == "-r" and args[2] == "--":
            owned(args[1]); owned(args[3])
        elif tool == "chmod" and len(args) == 2 and args[0].startswith("--reference="):
            owned(args[0].split("=", 1)[1]); owned(args[1])
        else:
            if tool != "exiftool":
                raise ValueError("unsupported real metadata preparation")
        result = subprocess.run([plan["real_metadata_tools"][tool], *args], timeout=10)
        if (tool == "exiftool" and result.returncode == 0 and "-o" in args
                and plan.get("metadata_corrupt_output")):
            owned(args[args.index("-o") + 1]).write_bytes(b"invalid metadata-only output")
        if (tool == "exiftool" and result.returncode == 0 and "-o" in args
                and plan.get("metadata_wrong_timestamp")):
            stage = owned(args[args.index("-o") + 1])
            subprocess.run([plan["real_metadata_tools"][tool], "-overwrite_original",
                            "-DateTimeOriginal=2000:01:01 00:00:00", str(stage)],
                           timeout=10, check=True)
        if tool == "exiftool" and "-o" in args and plan.get("metadata_disappear_after_output"):
            (CONTROL / "progress-gone").touch()
        return result.returncode
    if tool == "gettext":
        print(args[-1])
    elif tool == "kreadconfig6":
        key = args[args.index("--key") + 1]
        print(plan["config"].get(key, ""))
    elif tool in ("qdbus", "qdbus6"):
        if args[2] == "org.freedesktop.DBus.NameHasOwner":
            print("true")
        elif args[2] == "wasCancelled":
            print("true" if (CONTROL / "cancelled").exists() else "false")
    elif tool == "kdialog":
        if "--progressbar" in args:
            print(plan.get("progress_reference", "org.kde.kdialog-test /ProgressDialog"))
        elif "--inputbox" in args:
            index = args.index("--inputbox")
            print(args[index + 2] if len(args) > index + 2 else "")
        elif "--radiolist" in args:
            choices = args[args.index("--radiolist") + 2:]
            for index in range(0, len(choices), 3):
                if choices[index + 2] == "on":
                    print(choices[index])
                    break
            else:
                raise ValueError("radiolist has no selected default")
        elif "--getexistingdirectory" in args:
            path = owned(ROOT / "out")
            path.mkdir(exist_ok=True)
            print(path)
        elif "--getsavefilename" in args:
            path = owned(ROOT / "out")
            path.mkdir(exist_ok=True)
            print(path / "publication.pdf")
        elif not any(flag in args for flag in ("--yesnocancel", "--yesno", "--error", "--msgbox", "--textbox")):
            raise ValueError("unsupported kdialog invocation")
    elif tool == 'kmail':
        if not args or len(args) % 2 or any(args[index] != '--attach' for index in range(0, len(args), 2)):
            raise ValueError('kmail attachments must use repeated --attach PATH arguments')
        for value in args[1::2]:
            path = owned(value)
            if not path.is_file():
                raise ValueError('kmail attachment is missing')
    elif tool == 'xdg-email':
        if not args or len(args) % 2 or any(args[index] != '--attach' for index in range(0, len(args), 2)):
            raise ValueError('xdg-email attachments must use repeated --attach PATH arguments')
        for value in args[1::2]:
            path = owned(value)
            if not path.is_file():
                raise ValueError('xdg-email attachment is missing')
    elif tool == 'thunderbird':
        if len(args) != 2 or args[0] != '-compose' or not args[1].startswith("attachment='file://"):
            raise ValueError('thunderbird requires one encoded compose attachment argument')
    elif tool == "mktemp":
        directory = "-d" in args
        template = args[-1]
        # kim_all hard-codes /tmp; relocate that allocation into this test.
        if template.startswith("/tmp/kim."):
            template = str(CONTROL / "tmp" / Path(template).name)
        path = owned(template)
        prefix, separator, suffix = path.name.partition("XXXXXX")
        if not separator:
            raise ValueError("unsupported mktemp template")
        if directory:
            directory_name = tempfile.mkdtemp(prefix=prefix, suffix=suffix, dir=path.parent)
            EFFECTS["directory_mode"] = Path(directory_name).stat().st_mode & 0o777
            print(directory_name)
        else:
            descriptor, name = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=path.parent)
            os.close(descriptor)
            print(name)
    elif tool == "identify":
        signature_format = "%m %w %h %[orientation] %[colorspace] %[gamma] %g %T %D %#\\n"
        image_records_format = "%m|%w|%h|%T|%n|%#\\n"
        web_input_format = "%m|%w|%h|%[orientation]|%n\\n"
        web_color_input_format = "%m|%w|%h|%[orientation]|%n|%[colorspace]\\n"
        signature = (len(args) == 5 and args[:3] == ["-regard-warnings", "+ping", "-format"]
                     and args[3] == signature_format and args[4] in ("-", "TGA:-"))
        hinted = args == ["-regard-warnings", "+ping", "-format", "%m %w %h\\n", "TGA:-"]
        compression = hinted or args == ["-regard-warnings", "+ping", "-format", "%m %w %h\\n", "-"]
        formatted = signature or compression or args == ["-regard-warnings", "+ping", "-format", "%m\\n", "-"]
        limit = 8388608 if signature else (8388608 if compression and "real_resize" in plan else (65536 if compression else 4096))
        if (len(args) == 4 and args[:3] == ['-ping', '-format', web_color_input_format]
                and args[3] == '-'):
            payload = sys.stdin.buffer.read(limit + 1)
            image_format = web_color_input_format
        elif (len(args) == 4 and args[:3] == ['-ping', '-format', web_input_format]
                and args[3] == '-'):
            payload = sys.stdin.buffer.read(limit + 1)
            image_format = web_input_format
        elif (len(args) == 5 and args[:3] == ['-regard-warnings', '-format', image_records_format]
                and args[3] == '--'):
            fixture_path = owned(args[4])
            if fixture_path.stat().st_size > 8388608:
                raise ValueError('full image validation fixture exceeds test bound')
            payload = fixture_path.read_bytes()
            image_format = image_records_format
        elif formatted:
            payload = sys.stdin.buffer.read(limit + 1)
            image_format = args[3] if signature else ("%m %w %h\\n" if compression else "%m\\n")
        elif len(args) == 4 and args[:3] == ["-regard-warnings", "+ping", "--"]:
            payload = owned(args[3]).read_bytes()
        else:
            raise ValueError("unconfigured external command: identify")
        if len(payload) > limit:
            raise ValueError("validation fixture too large")
        executable = shutil.which("identify", path=os.defpath)
        if not executable:
            raise ValueError("test image validator is unavailable")
        with tempfile.TemporaryDirectory(dir=CONTROL) as folder:
            fixture = Path(folder) / "fixture"
            fixture.write_bytes(payload)
            options = ["-format", image_format] if formatted or image_format in (image_records_format, web_input_format, web_color_input_format) else []
            input_name = ("TGA:" if hinted or (signature and args[4] == "TGA:-") else "") + str(fixture)
            # Decoder delegates (e.g. Ghostscript) need their normal utility
            # PATH. Input remains a bounded, private synthetic fixture.
            environment = dict(os.environ, PATH=os.defpath)
            return subprocess.call([executable, "-regard-warnings", "+ping", *options, "--", input_name],
                                   env=environment)
    elif tool == "mv" and args == ["--help"]:
        # Model a rename-only-capable installation; missing capability is tested
        # separately. Filesystem implementation below uses os.rename, no copy.
        print("--no-copy --no-target-directory")
    elif tool == "mv" and args == ["--version"]:
        print("mv (modeled coreutils)")
    elif tool == 'cmp':
        if len(args) != 4 or args[:2] != ['-s', '--']:
            raise ValueError('unsupported byte comparison')
        for value in args[2:]:
            owned(value)
        return subprocess.call([shutil.which('cmp', path=os.defpath), *args])
    elif tool == "stat":
        if len(args) != 4 or args[:1] != ["-c"] or args[2] != "--":
            raise ValueError("unsupported stat invocation")
        info = owned(args[3]).lstat()
        formats = {"%d:%i": f"{info.st_dev}:{info.st_ino}", "%d": str(info.st_dev),
                   "%h": str(info.st_nlink)}
        if args[1] == '%d:%i:%s:%y:%f:%u:%g':
            print(f'{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}:{info.st_mode}:{info.st_uid}:{info.st_gid}')
            return 0
        if args[1] == '%a:%u:%g:%y':
            print(f'{info.st_mode & 0o7777}:{info.st_uid}:{info.st_gid}:{info.st_mtime_ns}')
            return 0
        if args[1] == '%x:%y':
            print(f'{info.st_atime_ns}:{info.st_mtime_ns}')
            return 0
        if args[1] not in formats:
            raise ValueError("unsupported stat format")
        print(formats[args[1]])
    elif tool in ("basename", "dirname"):
        value = args[-1]
        print(os.path.basename(value) if tool == "basename" else os.path.dirname(value) or ".")
    elif tool in ("date", "tr"):
        if tool == "date" and (len(args) != 1 or not args[0].startswith("+")):
            raise ValueError("only date format output is supported")
        if tool == "tr" and args not in (["[:upper:]", "[:lower:]"], ["[:lower:]", "[:upper:]"]):
            raise ValueError("only case translation is supported")
        return subprocess.call(["/usr/bin/" + tool, *args])
    elif tool == "awk":
        return subprocess.call([shutil.which("awk", path=os.defpath), *args])
    elif tool == "cat":
        if not args:
            sys.stdout.buffer.write(sys.stdin.buffer.read())
        for value in args:
            if value != "--":
                sys.stdout.buffer.write(owned(value).read_bytes())
    elif tool in ("mkdir", "mkfifo", "rm", "cp", "mv", "touch", "chmod", "ln"):
        filesystem(tool, args)
    else:
        raise ValueError("unconfigured external command: " + tool)
    return 0


def real_magick(executable, args):
    # Restrict the real-tool seam to synthetic PPM files and a tiny operation
    # grammar. No coders, delegates, URLs, @files, globs or output side effects.
    if len(args) not in (2, 3):
        raise ValueError("real magick supports copy, -flip and -flop only")
    source, destination = owned(args[0]), owned(args[-1])
    operation = args[1:-1]
    if operation not in ([], ["-flip"], ["-flop"]):
        raise ValueError("unsupported real magick operation")
    for path in (source, destination):
        if path.suffix != ".ppm" or any(char in str(path) for char in "[]%@:*?\\"):
            raise ValueError("real magick requires plain owned PPM paths")
    if source == destination or destination.exists() or destination.is_symlink():
        raise ValueError("real magick requires a new output")
    if source.read_bytes() != b"P6\n3 2\n255\n" + bytes.fromhex(
            "ff0000 00ff00 0000ff ffff00 ff00ff 00ffff"):
        raise ValueError("real magick accepts only the synthetic fixture")
    destination.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.call([executable, str(source), *operation, "-depth", "8", str(destination)])


def real_publication_tool(tools, tool, args):
    executable = tools.get(tool, shutil.which(tool, path=os.defpath))
    if tool == 'magick':
        if len(args) < 4 or args[-1].split('.')[-1].lower() not in ('pdf', 'tif', 'tiff', 'gif'):
            raise ValueError('publication producer requires an approved derived format')
        output = owned(args[-1])
        if output.exists() or output.is_symlink() or not output.parent.name.startswith('.kim6-stage.'):
            raise ValueError('publication producer requires a new private stage')
        if args[0] == 'montage':
            if (len(args) < 14 or args[1] != '-tile' or args[3] != '-geometry' or
                    args[5] != '-page' or args[7:11] != ['-density', '72', '-background', 'white'] or
                    args[11] != '--'):
                raise ValueError('unsupported real montage invocation')
            input_values = args[12:-1]
            if not input_values:
                raise ValueError('real montage requires input images')
        elif args[0] == '--':
            if len(args) >= 4 and args[-2] == '-adjoin':
                input_values = args[1:-2]
                if not input_values:
                    raise ValueError('real TIFF join requires input images')
            elif (len(args) >= 8 and args[-6:-4] == ['-set', 'delay'] and
                  args[-4].isdigit() and args[-3] == '-loop' and args[-2].isdigit()):
                input_values = args[1:-6]
                if not input_values:
                    raise ValueError('real GIF animation requires input images')
            else:
                raise ValueError('unsupported real publication command')
        else:
            raise ValueError('unsupported real publication command')
        for value in input_values:
            source = owned(value)
            if not source.is_file() or source.stat().st_size > 65536 or source.suffix.lower() not in ('.ppm', '.png'):
                raise ValueError('publication producer requires small owned image fixtures')
        return subprocess.run([executable, *args], timeout=30,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if tool == 'identify':
        if args and args[-1] != '-' and '--' in args:
            fixture = owned(args[-1])
            if fixture.stat().st_size > 1048576:
                raise ValueError('web/email image exceeds test bound')
            return subprocess.run([executable, *args], timeout=20,
                                  env=dict(os.environ, PATH=os.defpath)).returncode
        if (len(args) == 5 and args[0] in ('-ping', '-regard-warnings') and
                args[1] == '-format' and args[3] == '--'):
            owned(args[4])
        elif len(args) == 4 and args[:3] == ['-regard-warnings', '-verbose', '--']:
            owned(args[3])
        elif len(args) == 3 and args[0] == '-verbose' and args[1] == '--':
            owned(args[2])
        else:
            raise ValueError('unsupported real publication identify query')
        return subprocess.run([executable, *args], timeout=20,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if tool == 'pdfinfo':
        if len(args) != 1:
            raise ValueError('pdfinfo accepts one owned PDF')
        owned(args[0])
        return subprocess.run([executable, *args], timeout=20, text=True,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if tool == 'pdftoppm':
        if len(args) != 9 or args[:6] != ['-f', args[1], '-l', args[3], '-scale-to', '32'] or args[6] != '-png':
            raise ValueError('unsupported PDF validation render')
        owned(args[7])
        owned(args[8])
        return subprocess.run([executable, *args], timeout=30,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    raise ValueError('unsupported real publication tool')


def real_gallery_collage_tool(tools, tool, args):
    """Use real ImageMagick only on small owned PPMs and private PNG/PPM stages."""
    executable = tools[tool]
    def is_private_stage(path):
        return any(parent.name.startswith('.kim6-stage.') for parent in path.parents)
    if tool == 'identify':
        valid = (len(args) == 5 and args[:3] == ['-regard-warnings', '-format', '%m|%w|%h|%T|%n|%#\\n']
                 and args[3] == '--')
        ping = (len(args) == 5 and args[:2] == ['-ping', '-format']
                and args[2] == '%m|%w|%h|%n\\n' and args[3] == '--')
        pixels = (len(args) == 5 and args[:2] == ['-regard-warnings', '-format']
                  and args[2] == '%[pixel:p{5,5}]|%[pixel:p{17,5}]' and args[3] == '--')
        if not (valid or ping or pixels):
            raise ValueError('unsupported gallery/collage image inspection')
        path = owned(args[-1])
        if not path.is_file() or path.stat().st_size > 8388608:
            raise ValueError('gallery/collage inspection requires a small owned image')
        return subprocess.run([executable, *args], timeout=20,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if args[:1] == ['montage']:
        if len(args) < 10 or args[1] != '-background' or args[3] != '-tile' or args[5] != '-geometry' or args[7] != '--':
            raise ValueError('unsupported real collage montage')
        output = owned(args[-1].removeprefix('PNG:'))
        inputs = [owned(value) for value in args[8:-1]]
        if (not inputs or output.exists() or output.is_symlink() or not is_private_stage(output)):
            raise ValueError('montage output must be a new private stage')
        if any(not path.is_file() or path.stat().st_size > 131072 or path.suffix != '.png'
               for path in inputs):
            raise ValueError('montage inputs must be small private PNG tiles')
        return subprocess.run([executable, *args], timeout=30,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    # Gallery main image producer consumes stdin; all collage producers consume
    # one test-owned PPM source and write one private PNG tile.
    if args[:1] == ['-']:
        if len(args) != 4 or args[1:3] != ['-resize', '800x800']:
            raise ValueError('unsupported real gallery image producer')
        output = owned(args[-1].split(':', 1)[1])
        if output.suffix != '.ppm' or not output.parent.name == 'images':
            raise ValueError('gallery image must be a private PPM asset')
        return subprocess.run([executable, *args], stdin=sys.stdin.buffer, timeout=20,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if args[:1] == ['--']:
        if len(args) == 5 and args[1].endswith('[0]') and args[2:4] == ['-resize', '200x200']:
            source = owned(args[1][:-3])
            output = owned(args[-1].removeprefix('PNG:'))
            if (source.suffix not in ('.ppm', '.png') or source.stat().st_size > 8388608
                    or output.suffix != '.png'):
                raise ValueError('unsupported gallery thumbnail')
            return subprocess.run([executable, *args], timeout=20,
                                  env=dict(os.environ, PATH=os.defpath)).returncode
        if args[:2] == ['--', '-[0]']:
            output = owned(args[-1].removeprefix('PNG:'))
            payload = sys.stdin.buffer.read(1048577)
            if (args[2] != '-resize' or len(payload) > 131072
                    or not payload.startswith((b'P6\n', b'P3\n'))
                    or not is_private_stage(output)
                    or output.exists() or output.is_symlink()):
                raise ValueError('collage tile requires a tiny PPM and private stage')
            return subprocess.run([executable, *args], input=payload, timeout=30,
                                  env=dict(os.environ, PATH=os.defpath)).returncode
    raise ValueError('unsupported real gallery/collage ImageMagick command')


def real_web_email_tool(tools, tool, args):
    """Run only small PPM/JPEG fixtures through the web/email action grammar."""
    executable = tools.get(tool, shutil.which(tool, path=os.defpath))
    if tool == 'identify':
        if (len(args) == 5 and args[:2] == ['-regard-warnings', '-format']
                and args[3] == '--'):
            fixture = owned(args[4])
            if fixture.stat().st_size > 1048576:
                raise ValueError('web/email output exceeds test bound')
            return subprocess.run([executable, *args], timeout=20,
                                  env=dict(os.environ, PATH=os.defpath)).returncode
        if (len(args) == 4 and args[0] == '-ping' and args[1] == '-format'
                and args[3] == '-'):
            payload = sys.stdin.buffer.read(1048577)
        elif (len(args) == 4 and args[0] == '-regard-warnings'
              and args[1] == '-format' and args[3] == '-'):
            payload = sys.stdin.buffer.read(1048577)
        else:
            raise ValueError('unsupported web/email identify command')
        if len(payload) > 1048576:
            raise ValueError('web/email fixture exceeds test bound')
        return subprocess.run([executable, *args], input=payload, timeout=20,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if tool == 'exiftool' and args[:2] == ['-b', '-ICC_Profile'] and len(args) == 4 and args[2] == '--':
        source = owned(args[3])
        if source.stat().st_size > 1048576:
            raise ValueError('web/email source exceeds test bound')
        return subprocess.run([shutil.which('exiftool', path=os.defpath), *args], timeout=15,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if not args or args[0] != '-' or len(args) < 4:
        raise ValueError('web/email production must read one image from stdin')
    allowed = {'-auto-orient', '-strip'}
    index = 1
    while index < len(args) - 1:
        if args[index] in allowed:
            index += 1
        elif args[index] == '-resize' and index + 1 < len(args) - 1:
            index += 2
        elif args[index] == '-quality' and index + 1 < len(args) - 1:
            index += 2
        elif args[index] == '-profile' and index + 1 < len(args) - 1:
            profile = Path(args[index + 1])
            if not profile.is_relative_to(Path('/usr/share/color/icc')):
                profile = owned(profile)
            if not profile.is_file() or profile.is_symlink():
                raise ValueError('web/email profile is not a trusted installed resource')
            if profile.stat().st_size > 8388608:
                raise ValueError('web/email profile exceeds test bound')
            index += 2
        else:
            break
    if index != len(args) - 1 or ':' not in args[-1]:
        raise ValueError('unsupported web/email ImageMagick command')
    output = owned(args[-1].split(':', 1)[1])
    if output.exists() or output.is_symlink():
        raise ValueError('web/email producer requires a new owned stage')
    payload = sys.stdin.buffer.read(1048577)
    if len(payload) > 1048576 or not payload.startswith((b'P6\n', b'P3\n', b'\xff\xd8\xff',
                                                          b'GIF87a', b'GIF89a', b'II*\x00', b'MM\x00*')):
        raise ValueError('web/email producer requires a small synthetic image fixture')
    if not (output.parent.name.startswith('.kim6-stage.') or
            output.parent.resolve().is_relative_to((CONTROL / 'tmp').resolve())):
        raise ValueError('web/email output must be in a private or destination-local stage')
    return subprocess.run([executable, *args], input=payload, timeout=30,
                          env=dict(os.environ, PATH=os.defpath)).returncode


def real_conversion(executable, args):
    if not args or args[0] != "--" or len(args) < 3:
        raise ValueError("real conversion requires explicit source and output")
    source = owned(args[1])
    destination_name = args[-1].split(":", 1)[-1]
    destination = owned(destination_name)
    if len(args) == 3:
        pass
    elif (len(args) == 5 and args[2:4] == ["-define", "jp2:rate=1"]
          and args[-1].startswith("JP2:")):
        pass
    elif (len(args) == 5 and args[2] == "-quality" and args[-1].startswith("JP2:")
          and args[3].isdigit()):
        pass
    else:
        raise ValueError("real conversion options are outside the approved test grammar")
    formats = {"ppm", "png", "jpg", "jpeg", "jpe", "jfif", "gif", "gif87", "bmp", "dib", "bmp2", "bmp3",
               "tif", "tiff", "tiff64", "webp", "avif", "heic", "pnm", "pam", "pgm", "pbm",
               "png00", "png8", "png24", "png32", "png48", "png64", "pdf", "miff", "ico",
               "cur", "apng", "jp2", "j2k", "jpc", "jxl", "heif"}
    for path in (source, destination):
        if path.suffix.lower().lstrip(".") not in formats or any(c in str(path) for c in "[]%@:*?\\"):
            raise ValueError("real conversion requires plain owned fixture paths")
    if source.stat().st_size > 8 * 1024 * 1024 or source == destination or destination.exists() or destination.is_symlink():
        raise ValueError("real conversion requires tiny input and unused output")
    return subprocess.call([executable, *args])


def real_compression(executable, args):
    if args[:1] != ["--"] or args[2:-1] not in (
            ["-strip", "-interlace", "Plane", "-quality", args[-2]],
            ["+profile", "!{icc,exif}", "+set", "comment", "-interlace", "Plane", "-quality", args[-2]]):
        raise ValueError("real compression requires approved JPEG options")
    if not args[-2].isdigit() or not 1 <= int(args[-2]) <= 100:
        raise ValueError("invalid real compression quality")
    source, destination = owned(args[1]), owned(args[-1].removeprefix("JPEG:"))
    if source.stat().st_size > 65536 or destination.exists() or destination.is_symlink():
        raise ValueError("real compression requires bounded input and unused output")
    if any(c in str(p) for p in (source, destination) for c in "[]%@:*?\\"):
        raise ValueError("real compression requires plain fixture paths")
    return subprocess.call([executable, *args])


def real_stripmeta(executable, args):
    if (len(args) != 9 or args[0:2] != ["-all=", "-tagsfromfile"]
            or args[3:6] != ["-icc_profile", "-Orientation", "-o"]
            or args[7] != "--" or args[2] != args[8]):
        raise ValueError("unsupported metadata stripping operation")
    source, destination = owned(args[2]), owned(args[6])
    if source.stat().st_size > 8388608 or destination.exists() or destination.is_symlink():
        raise ValueError("stripmeta requires bounded input and unused output")
    if any(c in str(p) for p in (source, destination) for c in "[]%@:*?\\"):
        raise ValueError("stripmeta requires plain owned fixture paths")
    return subprocess.run([executable, *args], timeout=10,
                          env=dict(os.environ, PATH=os.defpath)).returncode


def real_resize(executable, args):
    if (len(args) != 9 or args[0] != "--" or args[2] != "-resize"
            or args[4:8] != ["-format", "%w %h\\n", "-write", "info:"]):
        raise ValueError("real resize requires explicit source, geometry and output")
    source, destination = owned(args[1]), owned(args[-1])
    if source.stat().st_size > 65536 or destination.exists() or destination.is_symlink():
        raise ValueError("real resize requires bounded input and unused output")
    if any(c in str(p) for p in (source, destination) for c in "[]%@:*?\\"):
        raise ValueError("real resize requires plain owned fixture paths")
    # Test-only caps allow the 60 MP fixture but contain deliberate enormous
    # geometry failures. Production imposes no additional dimension limits.
    limits = ["-limit", "width", "16384", "-limit", "height", "16384",
              "-limit", "memory", "768MiB", "-limit", "map", "0",
              "-limit", "disk", "0"]
    return subprocess.run([executable, *limits, *args], timeout=60,
                          env=dict(os.environ, PATH=os.defpath)).returncode


def real_transform(executable, args):
    if (args[:1] != ["--"] or args[2] not in ("-rotate", "-auto-orient", "-flip", "-flop")
            or args[-5:-1] != ["-format", "%w %h\\n", "-write", "info:"]):
        raise ValueError("unsupported real transformation")
    output = args[-1]
    if ":" in output:
        encoding, output = output.split(":", 1)
        if not encoding.isalnum():
            raise ValueError("invalid transformation encoder")
    source, destination = owned(args[1]), owned(output)
    if (source.stat().st_size > 65536 or destination.exists() or destination.is_symlink()
            or not destination.parent.name.startswith('.kim6-stage.')):
        raise ValueError("transformation requires small source and unused private stage")
    return subprocess.run([executable, *args], timeout=15,
                          env=dict(os.environ, PATH=os.defpath)).returncode


def real_video_tool(tools, tool, args, plan):
    executable = tools[tool]
    if tool == "ffmpeg" and args == ["-hide_banner", "-encoders"]:
        return subprocess.run([executable, *args], timeout=10,
                              env=dict(os.environ, PATH=os.defpath)).returncode
    if tool == "ffmpeg" and plan.get("video_fail_encoding"):
        progress_path = Path(args[args.index("-progress") + 1])
        progress_fd = os.open(progress_path, os.O_WRONLY)
        os.write(progress_fd, b"out_time_ms=100000\nprogress=continue\n")
        os.close(progress_fd)
        return 19
    if tool == "ffmpeg" and plan.get("video_fail_before_progress"):
        return 19
    if tool == "ffprobe":
        if "-i" not in args:
            raise ValueError("real ffprobe requires an explicit input")
        source = owned(args[args.index("-i") + 1])
        if source.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("video fixture exceeds test bound")
        result = subprocess.run([executable, *args], timeout=10,
                                env=dict(os.environ, PATH=os.defpath), capture_output=True)
        if (plan.get("video_force_output_format") and
                source.parent.name.startswith(".kim6-stage.") and
                any(value.startswith("format=format_name") for value in args)):
            result.stdout = result.stdout.replace(
                b"format_name=mov,mp4,m4a,3gp,3g2,mj2",
                plan["video_force_output_format"].encode("ascii"),
            )
        if (plan.get("video_force_input_dimensions") and
                not source.parent.name.startswith(".kim6-stage.") and
                "stream=codec_type,codec_name,width,height,duration,nb_frames" in args):
            dimensions = plan["video_force_input_dimensions"]
            result.stdout = result.stdout.replace(b"width=96", f"width={dimensions['width']}".encode())
            result.stdout = result.stdout.replace(b"height=64", f"height={dimensions['height']}".encode())
        if plan.get("video_interrupt_on_probe_output") and source.parent.name.startswith(".kim6-stage."):
            (CONTROL / "progress-state").write_text(plan["video_interrupt_on_probe_output"])
        sys.stdout.buffer.write(result.stdout)
        sys.stderr.buffer.write(result.stderr)
        return result.returncode
    else:
        decoding_validation = args[-3:] == ["-f", "null", "-"]
        if "-nostdin" not in args or ("-progress" not in args and not decoding_validation):
            raise ValueError("real ffmpeg must be noninteractive and monitored or a decode validation")
        input_paths = [owned(args[index + 1]) for index, value in enumerate(args[:-1]) if value == "-i"]
        if not input_paths or any(path.stat().st_size > 2 * 1024 * 1024 for path in input_paths):
            raise ValueError("real ffmpeg requires bounded test-owned inputs")
        if decoding_validation:
            output = None
        else:
            if "-n" not in args:
                raise ValueError("real ffmpeg output must refuse replacement")
            output = owned(args[-1])
            if output.exists() or output.is_symlink() or not output.parent.name.startswith(".kim6-stage."):
                raise ValueError("real ffmpeg requires a new destination-local stage")
        if plan.get("video_create_collision") and output is not None:
            source = input_paths[0]
            target = source.with_name(source.stem + "-transcoded." + output.suffix.lstrip("."))
            target = owned(target)
            target.write_bytes(b"created during transcode; preserve me")
        if plan.get("video_hold_process"):
            child = subprocess.Popen(["/bin/sleep", "20"])
            (CONTROL / "video-child.pid").write_text(str(child.pid))
            if plan.get("video_interrupt_during_encode"):
                (CONTROL / "progress-state").write_text(plan["video_interrupt_during_encode"])
            progress_path = Path(args[args.index("-progress") + 1])
            progress_fd = os.open(progress_path, os.O_WRONLY)
            os.write(progress_fd, b"out_time_ms=100000\nprogress=continue\n")

            def stop_child(_signum, _frame):
                child.terminate()
                try:
                    child.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
                os.close(progress_fd)
                raise SystemExit(143)

            signal.signal(signal.SIGTERM, stop_child)
            os.write(1, b"out_time_ms=100000\nprogress=continue\n")
            while True:
                time.sleep(1)
    command = list(args)
    if tool == "ffmpeg" and plan.get("video_limit_output_duration") and output is not None:
        command[-1:-1] = ["-t", plan["video_limit_output_duration"]]
    result = subprocess.run([executable, *command], timeout=15,
                            env=dict(os.environ, PATH=os.defpath))
    if tool == "ffmpeg" and plan.get("video_interrupt_after_encode") and output is not None:
        (CONTROL / "progress-state").write_text(plan["video_interrupt_after_encode"])
    return result.returncode


def filesystem(tool, args):
    # Only forms used by the recovered dispatcher; reject unknown options.
    allowed = {"mkdir": {"-p", "--"}, "mkfifo": {"--"}, "rm": {"-f", "-rf", "--"},
               "cp": {"-f", "-p", "--preserve=mode,ownership,timestamps,xattr", "--"}, "mv": {"-f", "-fT", "-T", "--no-clobber", "--no-copy", "--"},
               "ln": {"-T", "--"},
               "touch": {"-r", "--"}, "chmod": set()}
    values = []
    for value in args:
        if value.startswith("--reference=") and tool == "chmod":
            values.append(value.split("=", 1)[1])
        elif value in allowed[tool]:
            continue
        elif value.startswith("-"):
            raise ValueError("unsupported filesystem option: " + value)
        else:
            values.append(value)
    paths = [owned(value) for value in values]
    if tool == "mkdir":
        for path in paths:
            path.mkdir(parents="-p" in args, exist_ok="-p" in args)
    elif tool == "mkfifo":
        for path in paths:
            os.mkfifo(path)
    elif tool == "rm":
        for path in paths:
            if path.is_symlink():
                path.unlink()
            elif path.is_dir():
                if "-rf" not in args:
                    raise ValueError("recursive rm not requested")
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok="-f" in args or "-rf" in args)
    elif tool == "ln":
        if len(paths) != 2 or args[:2] != ["-T", "--"]:
            raise ValueError("unsupported link invocation")
        os.link(*paths, follow_symlinks=False)
    elif tool in ("cp", "mv"):
        if tool == 'mv' and args[:3] == ['--no-clobber', '-T', '--'] and len(args) == 5:
            source, destination = map(owned, args[3:])
            executable = shutil.which('mv', path=os.defpath)
            if not executable:
                raise ValueError('installed mv unavailable')
            return_code = subprocess.run([executable, *args], timeout=10).returncode
            if return_code != 0:
                raise ValueError('directory publication refused')
            return
        if len(paths) != 2 or paths[1].is_dir():
            raise ValueError("only explicit single-file destinations are supported")
        if tool == "cp":
            (shutil.copy2 if '-p' in args or '--preserve=mode,ownership,timestamps,xattr' in args else shutil.copyfile)(*paths)
        elif "--no-copy" in args:
            os.rename(*paths)
        else:
            shutil.move(*paths)
    elif tool == "touch":
        if "-r" in args:
            reference, destination = paths
            destination.touch(exist_ok=True)
            attributes = reference.stat()
            os.utime(destination, ns=(attributes.st_atime_ns, attributes.st_mtime_ns))
        else:
            for path in paths:
                path.touch()
    elif tool == "chmod":
        reference, destination = paths
        destination.chmod(reference.stat().st_mode & 0o7777)


if __name__ == "__main__":
    try:
        status = main()
    except (ValueError, OSError, IndexError) as error:
        print("KIM test adapter: " + str(error), file=sys.stderr)
        status = 97
        EFFECTS["error"] = str(error)
    with (CONTROL / "events.jsonl").open("a") as stream:
        stream.write(json.dumps({"tool": Path(sys.argv[0]).name,
                                 "argv": sys.argv[1:], "status": status,
                                 **EFFECTS}) + "\n")
    raise SystemExit(status)
