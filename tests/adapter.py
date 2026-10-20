#!/usr/bin/python3
"""External-command adapters. Never forward media or desktop calls by default.

Unknown invocations fail closed. Scripted writes are confined to the owned root.
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
    if not path.resolve().is_relative_to(ROOT):
        raise ValueError("adapter refused path outside test workspace")
    if path.resolve() == ROOT:
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
    if tool == "magick" and "real_magick" in plan and response is None:
        return real_magick(plan["real_magick"], args)
    if tool == "magick" and "real_conversion" in plan and response is None:
        return real_conversion(plan["real_conversion"], args)
    if tool == "magick" and "real_compression" in plan and response is None:
        return real_compression(plan["real_compression"], args)
    if tool == "magick" and "real_resize" in plan and response is None:
        return real_resize(plan["real_resize"], args)
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
        response = None
    if tool == "mv" and "real_mv" in plan and response is None:
        if args in (["--help"], ["--version"]):
            return subprocess.call([plan["real_mv"], *args])
        if len(args) != 5 or args[2] != "--" or args[:2] not in (
                ["--no-copy", "-fT"], ["--exchange", "-T"]):
            raise ValueError("real mv requires a rename-only publication form")
        for value in args[3:]:
            owned(value)
        return subprocess.call([plan["real_mv"], *args])
    if response is not None:
        if tool == "kdialog" and any(flag in args for flag in (
                "--getexistingdirectory", "--getsavefilename")) and response.get("stdout", "").strip():
            owned(response["stdout"].strip())
        for name, content in response.get("writes", {}).items():
            path = owned(ROOT / name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        if "output_base64" in response:
            if tool not in ("magick", "convert", "montage", "mogrify", "exiftool", "cp"):
                raise ValueError("output injection unsupported for " + tool)
            output = args[args.index("-o") + 1] if tool == "exiftool" else args[-1]
            if tool == "magick":
                output = output.removeprefix("JPEG:")
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
    if tool in plan.get("real_metadata_tools", {}):
        if tool == "touch" and len(args) == 4 and args[0] == "-r" and args[2] == "--":
            owned(args[1]); owned(args[3])
        elif tool == "chmod" and len(args) == 2 and args[0].startswith("--reference="):
            owned(args[0].split("=", 1)[1]); owned(args[1])
        else:
            raise ValueError("unsupported real metadata preparation")
        return subprocess.run([plan["real_metadata_tools"][tool], *args], timeout=10).returncode
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
        signature = (len(args) == 5 and args[:3] == ["-regard-warnings", "+ping", "-format"]
                     and args[3] == signature_format and args[4] in ("-", "TGA:-"))
        hinted = args == ["-regard-warnings", "+ping", "-format", "%m %w %h\\n", "TGA:-"]
        compression = hinted or args == ["-regard-warnings", "+ping", "-format", "%m %w %h\\n", "-"]
        formatted = signature or compression or args == ["-regard-warnings", "+ping", "-format", "%m\\n", "-"]
        limit = 8388608 if signature else (8388608 if compression and "real_resize" in plan else (65536 if compression else 4096))
        if formatted:
            payload = sys.stdin.buffer.read(limit + 1)
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
            options = ["-format", args[3] if signature else ("%m %w %h\n" if compression else "%m\n")] if formatted else []
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
    elif tool == "stat":
        if len(args) != 4 or args[:1] != ["-c"] or args[2] != "--":
            raise ValueError("unsupported stat invocation")
        info = owned(args[3]).lstat()
        formats = {"%d:%i": f"{info.st_dev}:{info.st_ino}", "%d": str(info.st_dev),
                   "%h": str(info.st_nlink)}
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
    elif tool == "cat":
        if not args:
            sys.stdout.buffer.write(sys.stdin.buffer.read())
        for value in args:
            if value != "--":
                sys.stdout.buffer.write(owned(value).read_bytes())
    elif tool in ("mkdir", "rm", "cp", "mv", "touch", "chmod", "ln"):
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


def real_conversion(executable, args):
    if len(args) != 3 or args[0] != "--":
        raise ValueError("real conversion requires explicit source and output")
    source, destination = map(owned, args[1:])
    formats = {"ppm", "png", "jpg", "jpeg", "jpe", "gif", "gif87", "bmp", "bmp2", "bmp3",
               "tif", "tiff", "tiff64", "webp", "avif", "heic", "pnm", "pam", "pgm", "pbm",
               "png00", "png8", "png24", "png32", "png48", "png64", "pdf", "miff", "ico"}
    for path in (source, destination):
        if path.suffix.lower().lstrip(".") not in formats or any(c in str(path) for c in "[]%@:*?\\"):
            raise ValueError("real conversion requires plain owned fixture paths")
    if source.stat().st_size > 4096 or source == destination or destination.exists() or destination.is_symlink():
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


def filesystem(tool, args):
    # Only forms used by the recovered dispatcher; reject unknown options.
    allowed = {"mkdir": {"-p", "--"}, "rm": {"-f", "-rf", "--"},
               "cp": {"-f", "--"}, "mv": {"-f", "-fT", "--no-copy", "--"},
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
        if len(paths) != 2 or paths[1].is_dir():
            raise ValueError("only explicit single-file destinations are supported")
        if tool == "cp":
            shutil.copyfile(*paths)
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
