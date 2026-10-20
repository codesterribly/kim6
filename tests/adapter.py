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
    # Validate the D-Bus boundary even when a response has been scripted.
    if tool in ("qdbus", "qdbus6"):
        if len(args) < 3 or args[:2] != ["org.kde.kdialog-test", "/ProgressDialog"]:
            raise ValueError("qdbus requires separate service and object path")
    if tool == "magick" and "real_magick" in plan and response is None:
        return real_magick(plan["real_magick"], args)
    if tool == "magick" and "real_conversion" in plan and response is None:
        return real_conversion(plan["real_conversion"], args)
    if isinstance(response, list):
        counter = CONTROL / (counter_name + ".index")
        index = int(counter.read_text()) if counter.exists() else 0
        if index >= len(response):
            raise ValueError("scripted responses exhausted for " + tool)
        counter.write_text(str(index + 1))
        response = response[index]
    if response and response.get("passthrough"):
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
            path = owned(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(response["output_base64"], validate=True))
            EFFECTS["output"] = str(path)
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
    if tool == "gettext":
        print(args[-1])
    elif tool == "kreadconfig6":
        key = args[args.index("--key") + 1]
        print(plan["config"].get(key, ""))
    elif tool in ("qdbus", "qdbus6"):
        if args[2] == "wasCancelled":
            print("true" if (CONTROL / "cancelled").exists() else "false")
    elif tool == "kdialog":
        if "--progressbar" in args:
            print("org.kde.kdialog-test /ProgressDialog")
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
        formatted = args == ["-regard-warnings", "+ping", "-format", "%m\\n", "-"]
        if formatted:
            payload = sys.stdin.buffer.read(4097)
        elif len(args) == 4 and args[:3] == ["-regard-warnings", "+ping", "--"]:
            payload = owned(args[3]).read_bytes()
        else:
            raise ValueError("unconfigured external command: identify")
        if len(payload) > 4096:
            raise ValueError("validation fixture too large")
        executable = shutil.which("identify", path=os.defpath)
        if not executable:
            raise ValueError("test image validator is unavailable")
        with tempfile.TemporaryDirectory(dir=CONTROL) as folder:
            fixture = Path(folder) / "fixture"
            fixture.write_bytes(payload)
            options = ["-format", "%m\n"] if formatted else []
            # Decoder delegates (e.g. Ghostscript) need their normal utility
            # PATH. Input remains a bounded, private synthetic fixture.
            environment = dict(os.environ, PATH=os.defpath)
            return subprocess.call([executable, "-regard-warnings", "+ping", *options, "--", str(fixture)],
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
