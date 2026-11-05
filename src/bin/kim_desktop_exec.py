"""Encode a literal executable path for a Desktop Entry Exec value.

This is Desktop Entry syntax, never a shell command or a replacement string.
"""


def exec_argument(text):
    if any(ord(c) < 32 or 127 <= ord(c) < 160 for c in text):
        raise ValueError('Control character in dispatcher path')
    # Field codes are expanded once, after argument unquoting.
    literal = text.replace('%', '%%')
    quoted = '"' + ''.join('\\' + c if c in '\\"`$' else c for c in literal) + '"'
    # The Desktop Entry string layer is decoded BEFORE Exec argument quoting.
    return quoted.replace('\\', '\\\\')


if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        sys.exit('Usage: kim_desktop_exec.py EXECUTABLE_PATH')
    try:
        print(exec_argument(sys.argv[1]))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
