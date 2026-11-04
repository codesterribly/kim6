"""KDialog adapter for owned codec/delegate groups; stdout/stdin stay streaming.

The dispatcher still owns publication and stage cleanup. This adapter waits for
its process group to stop before returning, including when the dialog vanishes.
"""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time


def main():
    workspace=Path(sys.argv[1]); command=sys.argv[2:]
    ref=(workspace/'job.ref').read_text().strip().split()
    bus=shutil.which('qdbus') or shutil.which('qdbus6') or '/usr/lib/qt6/bin/qdbus'
    def call(*args):
        try: return subprocess.run([bus,*ref,*args],capture_output=True,text=True,timeout=3)
        except (OSError,subprocess.TimeoutExpired): return None
    def stopped():
        if (workspace/'job.cancelled').exists(): return True
        reply=call('wasCancelled')
        return reply is None or reply.returncode!=0 or reply.stdout.strip()!='false'
    stage_file=workspace/'job.stage'
    tool=Path(command[0]).name
    stage='Copying source' if tool=='cp' else 'Validating copied bytes' if tool=='cmp' else 'Inspecting video' if tool=='ffprobe' else 'Reading metadata' if tool=='exiftool' else 'Inspecting image' if tool=='identify' or 'identify' in command[1:2] else 'Checking / updating metadata' if any('metadata.py' in a or 'verify.py' in a for a in command) else 'Processing image'
    if tool=='exiftool' and any('=' in a or a=='-o' for a in command[1:]): stage='Updating metadata'
    # ffprobe inspects both videos and animated images.
    # Choose terminology from the active operation, without
    # changing progress messages for ordinary video actions.
    if tool == 'ffprobe':
        try:
            active_label = (
                (workspace / 'job.label')
                .read_text(encoding='utf-8')
                .lower()
            )
        except OSError:
            active_label = ''

        if any(term in active_label for term in (
            'animated png',
            'animated gif',
            'apng',
            'animation',
        )):
            stage = 'Inspecting animation'

    stage_file.write_text(stage)
    previous=''; interrupted=False
    child=None
    def observed_exit():
        # Keep the group leader unreaped until all owned delegates are stopped.
        # Signalling its numeric group after wait()/poll() can race PID reuse.
        return os.waitid(os.P_PID,child.pid,os.WEXITED | os.WNOHANG | os.WNOWAIT)
    def interrupt(*_):
        nonlocal interrupted
        interrupted=True
    for signum in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP): signal.signal(signum,interrupt)
    try:
        if stopped(): interrupted=True; return 130
        child=subprocess.Popen(command,start_new_session=True)
        while observed_exit() is None:
            if interrupted or stopped(): interrupted=True; break
            stage=stage_file.read_text() if stage_file.exists() else stage
            if stage!=previous:
                label=(workspace/'job.label').read_text() if (workspace/'job.label').exists() else ''
                call('setLabelText',label+'\n'+stage)
                with (workspace/'job.events').open('a') as log: log.write(json.dumps({'stage':stage,'label':label})+'\n')
                previous=stage
            time.sleep(.1)
        if interrupted: return 130
        # Recheck after an otherwise successful tool, before caller publication.
        event=observed_exit()
        rc=event.si_status if event.si_code==os.CLD_EXITED else -event.si_status
        if stopped(): interrupted=True; return 130
        return rc
    finally:
        if interrupted:
            (workspace/'job.cancelled').touch()
            call('setLabelText','Cancelling current operation… Waiting for cleanup.')
        if child is not None:
            try: os.killpg(child.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            deadline=time.monotonic()+2
            while observed_exit() is None and time.monotonic()<deadline: time.sleep(.05)
            # Kill surviving delegates too, even if the group leader exited.
            try: os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError: pass
            child.wait()


if __name__=='__main__': raise SystemExit(main())
