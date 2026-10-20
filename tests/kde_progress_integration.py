#!/usr/bin/env python3
"""Explicit real-KDE K10 check. Opens only uniquely titled synthetic dialogs.

Run separately in the graphical session: python3 -B tests/kde_progress_integration.py
Uses installed accessibility D-Bus tools to activate only this test's Cancel
button; never broadcasts input or terminates unrelated processes.
"""
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import time
import sys
import uuid


SOURCE = (Path(__file__).resolve().parents[1] / 'src/bin/kim_all').read_text()
ENTRY = '\nmain "$@"\n'
assert SOURCE.count(ENTRY) == 1
SOURCE = SOURCE.replace(ENTRY, '\n')


def call(reference, *args):
    return subprocess.run(['qdbus', *reference, *args], capture_output=True, text=True, timeout=5)


def property_value(reference, name):
    result = call(reference, 'org.freedesktop.DBus.Properties.Get', 'org.kde.kdialog.ProgressDialog', name)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def activate_owned_cancel(reference):
    address = subprocess.run(['qdbus', 'org.a11y.Bus', '/org/a11y/bus',
        'org.a11y.Bus.GetAddress'], capture_output=True, text=True, timeout=5)
    assert address.returncode == 0, address.stderr
    bus = address.stdout.strip()
    pid = subprocess.run(['qdbus', 'org.freedesktop.DBus', '/org/freedesktop/DBus',
        'org.freedesktop.DBus.GetConnectionUnixProcessID', reference[0]],
        capture_output=True, text=True, timeout=5)
    assert pid.returncode == 0, pid.stderr
    owned_pid = int(pid.stdout.strip())
    def invoke(service, path, method, *args):
        result = subprocess.run(['gdbus', 'call', '--address', bus, '--dest', service,
            '--object-path', path, '--method', method, *args],
            capture_output=True, text=True, timeout=5)
        assert result.returncode == 0, result.stderr
        return result.stdout
    def children(service, path):
        reply = invoke(service, path, 'org.a11y.atspi.Accessible.GetChildren')
        return re.findall(r"\('([^']+)', (?:objectpath )?'([^']+)'\)", reply)
    deadline = time.monotonic() + 10
    seen_names = []
    while time.monotonic() < deadline:
        applications = children('org.a11y.atspi.Registry', '/org/a11y/atspi/accessible/root')
        for service, path in applications:
            reply = invoke('org.freedesktop.DBus', '/org/freedesktop/DBus',
                'org.freedesktop.DBus.GetConnectionUnixProcessID', service)
            match = re.search(r'(?:uint32 )?(\d+)', reply)
            if not match or int(match.group(1)) != owned_pid:
                continue
            pending = [(service, path)]
            visited = set()
            while pending:
                current = pending.pop()
                if current in visited:
                    continue
                visited.add(current)
                name = invoke(*current, 'org.freedesktop.DBus.Properties.Get',
                              'org.a11y.atspi.Accessible', 'Name')
                seen_names.append(name.strip())
                if "'Cancel'" in name or "'&Cancel'" in name:
                    actions = invoke(*current, 'org.a11y.atspi.Action.GetActions')
                    names = re.findall(r"\('([^']*)', '[^']*', '[^']*'\)", actions)
                    print('Owned Cancel actions:', names, flush=True)
                    index = next(i for i, name in enumerate(names) if name.lower() in ('press', 'click', 'activate'))
                    print('Owned Cancel state:', invoke(*current, 'org.a11y.atspi.Accessible.GetState').strip(), flush=True)
                    reply = invoke(*current, 'org.a11y.atspi.Action.DoAction', str(index))
                    assert 'true' in reply, reply
                    return
                pending.extend(children(*current))
        time.sleep(0.05)
    raise RuntimeError('No accessible Cancel button on owned PID: ' + repr(seen_names))


def scenario(mode):
    title = 'KIM6 K10 synthetic ' + uuid.uuid4().hex
    script = SOURCE + r'''
# Unique test title; all commands remain real KDE executables.
kdialog() { command kdialog --title "$K10_TEST_TITLE" "$@"; }
mk_workdir
ref="$(progress_open 2 'K10 synthetic photo 雪 with spaces')"
printf 'REFERENCE %s\n' "$ref"
progress_label "$ref" 'Processing photo 雪 with spaces.png'
progress_value "$ref" 1
printf 'READY\n'
IFS= read -r proceed
case "$proceed" in
  cancel) if progress_cancelled "$ref"; then printf 'INTERRUPTED\n'; else exit 74; fi ;;
  failure) exit 73 ;;
  success) if progress_cancelled "$ref"; then exit 75; fi
           progress_value "$ref" 2
           printf 'FINAL\n'
           IFS= read -r proceed ;;
esac
progress_close "$ref"
'''
    environment = dict(os.environ, K10_TEST_TITLE=title, QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1',
                       QT_ACCESSIBILITY='1', LANGUAGE='C', LC_ALL='C.UTF-8')
    process = subprocess.Popen(['/bin/bash', '-c', script], env=environment, stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, bufsize=0)
    reference = None
    received = bytearray()
    def line():
        deadline = time.monotonic() + 10
        while b'\n' not in received:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                raise TimeoutError('KDE harness protocol phase timed out')
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                raise RuntimeError('KDE harness closed stdout before the expected phase')
            received.extend(chunk)
        raw, _, tail = received.partition(b'\n')
        received[:] = tail
        return raw.decode().strip()
    def respond(text):
        process.stdin.write((text + '\n').encode())
        process.stdin.flush()
    try:
        first = line()
        assert first.startswith('REFERENCE '), first
        reference = first.removeprefix('REFERENCE ').split()
        assert len(reference) == 2
        assert line() == 'READY'
        assert property_value(reference, 'value') == '1'
        assert property_value(reference, 'autoClose') == 'false'
        initial = call(reference, 'wasCancelled')
        assert initial.returncode == 0 and initial.stdout.strip() == 'false', initial.stderr
        if mode in ('cancel', 'disappear'):
            if mode == 'cancel':
                # Activate the actual owned Cancel button, not a simulated loss.
                time.sleep(5)
                activate_owned_cancel(reference)
            else:
                assert call(reference, 'close').returncode == 0
            deadline = time.monotonic() + 5
            while True:
                state = call(reference, 'wasCancelled')
                owner = call(['org.freedesktop.DBus', '/org/freedesktop/DBus'],
                             'org.freedesktop.DBus.NameHasOwner', reference[0])
                assert owner.returncode == 0 and owner.stdout.strip() in ('true', 'false'), owner.stderr
                if owner.stdout.strip() == 'false':
                    print('REAL KDE observation:', mode, 'service disappeared;',
                          'wasCancelled status', state.returncode, repr(state.stdout), flush=True)
                    break
                assert state.returncode == 0, ('Service remains but method failed', state.stderr)
                assert state.stdout.strip() in ('true', 'false'), ('Malformed reply', state.stdout)
                if state.stdout.strip() == 'true':
                    print('REAL KDE observation:', mode, 'explicit wasCancelled=true', flush=True)
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError('Owned Cancel action left service present with explicit false')
                time.sleep(0.05)
            respond('cancel')
            assert line() == 'INTERRUPTED'
        elif mode == 'success':
            respond('success')
            assert line() == 'FINAL'
            assert property_value(reference, 'value') == '2'
            respond('close')
        else:
            respond('failure')
        output, error = process.communicate(timeout=10)
        assert process.returncode == (73 if mode == 'failure' else 0), (process.returncode, output, error)
        owner = subprocess.run(['qdbus', 'org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus.NameHasOwner', reference[0]], capture_output=True, text=True, timeout=5)
        assert owner.returncode == 0 and owner.stdout.strip() == 'false', owner.stdout + owner.stderr
        print('REAL KDE PASS:', mode, '(real KDialog/qdbus; owned service gone)', flush=True)
    finally:
        if reference:
            call(reference, 'close')
        if process.poll() is None:
            # Only this harness's dedicated process group, never a process-name kill.
            os.killpg(process.pid, signal.SIGTERM)
            process.communicate(timeout=5)


if __name__ == '__main__':
    modes = sys.argv[1:] or ('success', 'failure', 'cancel', 'disappear')
    assert all(mode in ('success', 'failure', 'cancel', 'disappear') for mode in modes)
    for mode in modes:
        scenario(mode)
