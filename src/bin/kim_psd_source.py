"""Read-only PSD boundary shared by Recipes and scoped ImageMagick consumers.

Scene zero invokes the PSD coder's merged-image / conditional layer fallback.
Never flatten an image list ourselves. TIFF staging retains 16-bit samples and
alpha. Destination encoders retain their existing precision rules (for example,
JPEG/GIF quantize to 8-bit; PNG/TIFF can retain 16-bit). Recipes retain RGB ICC until their ordered color step. Shell image
consumers normalize RGB to sRGB too; profiled CMYK/gray is transformed before
consumers that assume RGB. Untagged CMYK and unsupported modes fail closed.
"""
import contextlib
import contextvars
import hashlib
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile

import kim_process as process
from kim_process import ProcessError as PSDError

WARNING = ('PSD compatibility: KIM6 uses the saved composite or ImageMagick’s best-effort '
           'reconstruction. Masks, blend modes, adjustment layers, text and effects may look different. '
           'Composite provenance cannot be reliably detected.')
LIMITS = ['-limit', 'memory', '256MiB', '-limit', 'map', '512MiB',
          '-limit', 'disk', '1GiB', '-limit', 'thread', '2', '-limit', 'time', '120']


def command(args, **kwargs):
    try:
        result = process.run_process(args, timeout=150, **kwargs)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PSDError('PSD processing failed: ' + str(exc)) from exc
    diagnostics = process.metadata_diagnostics(args, result.returncode, result.stderr.decode(errors='replace'))
    if result.returncode or diagnostics:
        raise PSDError('PSD processing failed: ' + result.stderr.decode(errors='replace').strip())
    return result.stdout


def header(path):
    try:
        with open(path, 'rb') as stream:
            data = stream.read(26)
    except (OSError, ValueError):
        return None
    if not data.startswith(b'8BPS'):
        return None
    if len(data) != 26:
        raise PSDError('Truncated PSD header')
    version, = struct.unpack('>H', data[4:6])
    if version != 1:
        raise PSDError('PSB / large Photoshop documents are not supported')
    height, width, depth, mode = struct.unpack('>IIHH', data[14:26])
    if not width or not height or width > 30000 or height > 30000 or width * height > 100_000_000:
        raise PSDError('PSD canvas exceeds the 100 megapixel / 30000 pixel safety limit')
    if depth not in (8, 16) or mode not in (1, 3, 4):
        raise PSDError('PSD requires 8/16-bit RGB, grayscale or profiled CMYK')
    return width, height, depth, mode


def srgb():
    for path in ('/usr/share/color/icc/sRGB.icc', '/usr/share/color/icc/ghostscript/srgb.icc',
                 '/usr/share/color/icc/colord/sRGB.icc'):
        if Path(path).is_file():
            return path
    raise PSDError('An installed sRGB ICC profile is required for PSD color interpretation')


def normalize(path, directory, rgb=False):
    """Return one verified TIFF, or the original path for non-PSD inputs."""
    document = header(path)
    if document is None:
        return str(path)
    width, height, depth, mode = document
    directory = Path(directory)
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    source_stat = os.stat(path)
    identity = (source_stat.st_dev, source_stat.st_ino, source_stat.st_size,
                source_stat.st_mtime_ns, source_stat.st_ctime_ns)
    target = directory / (hashlib.sha256(repr((identity, rgb)).encode()).hexdigest() + '.tiff')
    if target.is_file():
        return str(target)
    if sum(p.stat().st_size for p in directory.glob('*.tiff')) > 2 * 1024**3:
        raise PSDError('PSD staging exceeds the 2 GiB batch limit; use a smaller batch')
    process.stage('Reading Photoshop document')
    fd, temporary = tempfile.mkstemp(suffix='.tiff', dir=directory)
    os.close(fd)
    try:
        # Inspect the document profile too: a decoder may discard a damaged
        # resource, which must not turn a malformed ICC into an sRGB assumption.
        process.stage('Inspecting Photoshop color profile')
        command(['exiftool', '-s3', '-ICC_Profile:ProfileFileSignature', str(path)])
        # Decode real pixels, not a ping: a plausible header is insufficient.
        process.stage('Preparing Photoshop composite')
        with open(path, 'rb') as source:
            command(['magick', *LIMITS, '-regard-warnings', 'psd:-[0]',
                     '+repage', '-compress', 'Zip', 'TIFF:' + temporary], stdin=source)
        record = command(['magick', 'identify', '-format', '%w|%h|%z|%[colorspace]\n', temporary]).decode().splitlines()
        if len(record) != 1:
            raise PSDError('PSD did not produce exactly one composite')
        w, h, bits, colorspace = record[0].split('|')
        if (int(w), int(h)) != (width, height):
            raise PSDError('PSD composite does not match the document canvas')
        process.stage('Inspecting composite color profile')
        has_icc = bool(command(['exiftool', '-b', '-ICC_Profile', temporary]))
        if mode == 4 and not has_icc:
            raise PSDError('Unprofiled CMYK PSD has unknown source colors; assign a valid source ICC profile before exporting')
        color_args = []
        if has_icc and (rgb or mode in (1, 4) or colorspace.lower() not in ('srgb', 'rgb')):
            color_args = ['-profile', srgb()]
        elif not has_icc:
            warning = 'Unprofiled RGB/grayscale source: KIM6 assumed sRGB for color interpretation.'
            process.add_warning(warning)
            if mode == 1: color_args += ['-colorspace', 'sRGB']
            color_args += ['-profile', srgb()]
        if color_args:
            process.stage('Converting composite color profile')
            converted = temporary + '.color.tiff'
            try:
                command(['magick', *LIMITS, '-regard-warnings', temporary, *color_args,
                         '-depth', str(depth), '-compress', 'Zip', 'TIFF:' + converted])
                os.replace(converted, temporary)
            finally:
                if os.path.exists(converted): os.unlink(converted)
        # IM serializes IPTC while decoding and can thereby invalidate a valid
        # Photoshop digest. Restore the source blocks verbatim, not individual
        # tags, without copying the source CMYK ICC onto transformed RGB pixels.
        # A digest already stale in the original remains stale: never repair it.
        process.stage('Preserving Photoshop metadata')
        blocks = {}
        for tag in ('IPTC','XMP'):
            blocks[tag] = command(['exiftool','-b','-' + tag,str(path)])
        if any(blocks.values()):
            command(['exiftool','-overwrite_original','-TagsFromFile',str(path),'-IPTC','-XMP',temporary])
            for tag, payload in blocks.items():
                actual = command(['exiftool','-b','-' + tag,temporary])
                # TIFF's IPTC tag uses four-byte LONG values. ExifTool pads
                # only that block to a word boundary; XMP must match exactly.
                padded = payload + b'\0' * (-len(payload) % 4) if tag == 'IPTC' else payload
                if actual not in (payload,padded):
                    raise PSDError('PSD ' + tag + ' block could not be preserved verbatim; no output was published')
        process.stage('Validating Photoshop composite')
        validation = ['-profile', srgb()] if has_icc and not color_args else []
        command(['magick', *LIMITS, '-regard-warnings', temporary, *validation, 'null:'])
        current = os.stat(path)
        if identity != (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_ctime_ns):
            raise PSDError('PSD changed during inspection; retry with a stable source')
        if sum(p.stat().st_size for p in directory.glob('*.tiff') if str(p) != temporary) + os.path.getsize(temporary) > 2 * 1024**3:
            raise PSDError('PSD staging exceeds the 2 GiB batch limit; use a smaller batch')
        os.replace(temporary, target)
        process.record_warnings(directory,path,identity,[WARNING]+process.session_warnings())
        return str(target)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


_SESSION = contextvars.ContextVar('kim_psd_session', default=None)


@contextlib.contextmanager
def source_session():
    """Bound reuse to one source inspection/execution, never a persistent cache.

    ContextVars isolate Qt workers. Each entry still checks the source identity
    and color policy; a new batch/settings generation gets a fresh workspace.
    """
    if _SESSION.get() is not None:
        yield
        return
    with tempfile.TemporaryDirectory(prefix='kim-psd-') as directory:
        token = _SESSION.set(directory)
        try:
            with process.warning_context():
                yield
        finally:
            _SESSION.reset(token)


@contextlib.contextmanager
def prepared(args, directory=None, rgb=False):
    """Normalize input arguments; output names and metadata writes stay untouched."""
    with contextlib.ExitStack() as stack:
        if directory is None:
            directory = _SESSION.get()
        if directory is None:
            directory = stack.enter_context(tempfile.TemporaryDirectory(prefix='kim-psd-'))
        result = list(args)
        # Only ImageMagick reads and ICC inspection use staged pixels/profile.
        icc_read = (args[0] == 'exiftool' and any(a.startswith('-ICC_Profile') for a in args)
                    and not any('=' in a or a == '-TagsFromFile' for a in args))
        if args[0] in ('magick', 'identify') or icc_read:
            for index, arg in enumerate(args[1:], 1):
                candidate = arg
                selector = ''
                if not os.path.isfile(candidate) and candidate.endswith('[0]'):
                    candidate, selector = candidate[:-3], '[0]'
                if os.path.isfile(candidate) and header(candidate) is not None:
                    result[index] = normalize(candidate, directory, rgb=rgb) + selector
        yield result


def opaque_background(args):
    if not args or args[0] != 'magick': return args
    output = args[-1]
    coder = output.split(':', 1)[0].lower() if ':' in output else Path(output).suffix[1:].lower()
    if coder in ('jpg', 'jpeg', 'jpe', 'jfif', 'bmp', 'pdf', 'ppm'):
        return args[:-1] + ['-background', 'white', '-alpha', 'remove', '-alpha', 'off', output]
    return args


def main():
    args = sys.argv[1:]
    directory = os.environ.get('KIM_PSD_CACHE')
    process._WARNINGS.set([])
    # Shell publication monitors already own this entire group. Decoder
    # children must remain in it so cancelling the wrapper stops staging too.
    # Qt/library callers instead own a private group for each tool invocation.
    process._SHELL_GROUP.set(True)
    if not directory:
        raise PSDError('PSD staging workspace is unavailable')
    # Shell consumers sometimes read from stdin, including the monitored
    # slideshow encoder. Preserve their stdin convention and process group.
    replacement = None
    try:
        if stat.S_ISREG(os.fstat(0).st_mode):
            source = f'/proc/{os.getpid()}/fd/0'
            if header(source) is not None:
                replacement = normalize(source, directory, rgb=True)
    except OSError:
        pass
    with prepared(args, directory, rgb=True) as resolved:
        if replacement or resolved != args:
            resolved = opaque_background(resolved)
        if replacement:
            stream = open(replacement, 'rb')
            os.dup2(stream.fileno(), 0)
        process.stage('Reading metadata' if resolved[0]=='exiftool' else 'Inspecting image' if resolved[0]=='identify' or resolved[1:2]==['identify'] else 'Processing image')
        os.execvp(resolved[0], resolved)


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (PSDError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        cache = os.environ.get('KIM_PSD_CACHE')
        if cache:
            Path(cache).mkdir(mode=0o700, parents=True, exist_ok=True)
            with open(Path(cache) / 'errors.txt', 'a') as log:
                log.write(str(exc) + '\n')
            if os.environ.get('DISPLAY') or os.environ.get('WAYLAND_DISPLAY'):
                try:
                    subprocess.run(['kdialog', '--title', 'KIM6 — PSD source', '--passivepopup', str(exc), '12'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
                except (OSError, subprocess.TimeoutExpired):
                    pass
        sys.exit(1)
