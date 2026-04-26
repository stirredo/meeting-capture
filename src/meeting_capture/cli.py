"""CLI: meeting-capture {start,stop,pause,resume,status,install,uninstall,run,mic,last,tail}."""
from __future__ import annotations

import argparse
import os
import plistlib
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .mic import active_mic_name, is_mic_active, mic_name
from .paths import (
    AUDIO_DIR,
    LAUNCHD_LABEL,
    LAUNCHD_PLIST,
    LOG_FILE,
    PAUSE_FILE,
    PID_FILE,
    TRANSCRIPTS_DIR,
    ensure_dirs,
)


def _read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except ValueError:
        return None


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _format_age(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h ago"
    return f"{int(seconds // 86400)}d ago"


def _last_transcript() -> Path | None:
    if not TRANSCRIPTS_DIR.exists():
        return None
    files = sorted(TRANSCRIPTS_DIR.glob("meeting-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _last_chunk_log_line() -> str | None:
    if not LOG_FILE.exists():
        return None
    try:
        with LOG_FILE.open("r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
    except OSError:
        return None
    for line in reversed(lines):
        if "chunk " in line and " -> " in line:
            return line.rstrip()
    return None


def cmd_status(_args) -> int:
    ensure_dirs()
    pid = _read_pid()
    running = pid is not None and _is_running(pid)
    paused = PAUSE_FILE.exists()
    mic_on = is_mic_active()

    print(f"meeting-capture {__version__}")
    print(f"  daemon:           {'running (pid ' + str(pid) + ')' if running else 'stopped'}")
    print(f"  paused:           {paused}")
    if mic_on:
        print(f"  mic in use:       True ({active_mic_name() or 'unknown device'})")
    else:
        print(f"  mic in use:       False (default: {mic_name() or 'unknown device'})")
    if running and mic_on and not paused:
        print(f"  state:            ACTIVELY RECORDING")
    elif running and not paused:
        print(f"  state:            idle (waiting for mic to activate)")
    elif running and paused:
        print(f"  state:            paused")
    else:
        print(f"  state:            not running")

    last = _last_transcript()
    if last is not None:
        st = last.stat()
        size_kb = st.st_size / 1024
        age = time.time() - st.st_mtime
        print(f"  last transcript:  {last.name} ({size_kb:.1f} KB, {_format_age(age)})")
    else:
        print(f"  last transcript:  (none yet)")

    last_log = _last_chunk_log_line()
    if last_log is not None:
        print(f"  last chunk log:   {last_log}")

    print(f"  transcripts dir:  {TRANSCRIPTS_DIR}")
    print(f"  log file:         {LOG_FILE}")
    print(f"  launchd:          {'installed' if LAUNCHD_PLIST.exists() else 'not installed'}")
    return 0


def cmd_mic(_args) -> int:
    print(f"default input:       {mic_name() or '(none)'}")
    print(f"in use by other app: {is_mic_active()}")
    if is_mic_active():
        print(f"active device:       {active_mic_name() or '(unknown)'}")
    return 0


def cmd_last(_args) -> int:
    last = _last_transcript()
    if last is None:
        print("(no transcripts yet)", file=sys.stderr)
        return 1
    print(last)
    return 0


def cmd_tail(_args) -> int:
    if not LOG_FILE.exists():
        print(f"no log file at {LOG_FILE}", file=sys.stderr)
        return 1
    subprocess.run(["tail", "-f", str(LOG_FILE)])
    return 0


def cmd_pause(_args) -> int:
    ensure_dirs()
    PAUSE_FILE.touch()
    print(f"paused (touch {PAUSE_FILE})")
    return 0


def cmd_resume(_args) -> int:
    try:
        PAUSE_FILE.unlink()
        print("resumed")
    except FileNotFoundError:
        print("not paused")
    return 0


def cmd_run(_args) -> int:
    from .daemon import run

    run()
    return 0


def cmd_start(args) -> int:
    if LAUNCHD_PLIST.exists():
        subprocess.run(["launchctl", "load", "-w", str(LAUNCHD_PLIST)], check=False)
        print("started via launchd")
        return 0
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"already running (pid {pid})")
        return 0
    log = open(LOG_FILE, "ab")
    proc = subprocess.Popen(
        [sys.executable, "-m", "meeting_capture.daemon"],
        stdout=log,
        stderr=log,
        start_new_session=True,
    )
    print(f"started (pid {proc.pid})")
    return 0


def cmd_stop(_args) -> int:
    if LAUNCHD_PLIST.exists():
        subprocess.run(["launchctl", "unload", "-w", str(LAUNCHD_PLIST)], check=False)
        print("stopped via launchd")
        return 0
    pid = _read_pid()
    if not pid or not _is_running(pid):
        print("not running")
        return 0
    os.kill(pid, signal.SIGTERM)
    print(f"sent SIGTERM to pid {pid}")
    return 0


def _plist_payload(python_exe: str) -> bytes:
    payload = {
        "Label": LAUNCHD_LABEL,
        "ProgramArguments": [python_exe, "-m", "meeting_capture.daemon"],
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False, "Crashed": True},
        "StandardOutPath": str(LOG_FILE),
        "StandardErrorPath": str(LOG_FILE),
        "WorkingDirectory": str(Path.home()),
        "EnvironmentVariables": {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin"),
        },
        "ProcessType": "Background",
    }
    return plistlib.dumps(payload)


def cmd_install(_args) -> int:
    ensure_dirs()
    LAUNCHD_PLIST.parent.mkdir(parents=True, exist_ok=True)
    payload = _plist_payload(sys.executable)
    LAUNCHD_PLIST.write_bytes(payload)
    subprocess.run(["launchctl", "unload", str(LAUNCHD_PLIST)], check=False, stderr=subprocess.DEVNULL)
    subprocess.run(["launchctl", "load", "-w", str(LAUNCHD_PLIST)], check=False)
    print(f"installed launchd agent at {LAUNCHD_PLIST}")
    print("daemon will auto-start at login.")
    return 0


def cmd_uninstall(_args) -> int:
    if not LAUNCHD_PLIST.exists():
        print("launchd agent not installed")
        return 0
    subprocess.run(["launchctl", "unload", "-w", str(LAUNCHD_PLIST)], check=False)
    LAUNCHD_PLIST.unlink()
    print(f"removed {LAUNCHD_PLIST}")
    return 0


def cmd_check(_args) -> int:
    from .recorder import find_audiotee

    binary = find_audiotee()
    if binary is None:
        print("audiotee: NOT FOUND. Run setup.sh to build it.")
        return 1
    print(f"audiotee: {binary}")
    print("Trigger the audio-capture permission prompt by running:")
    print(f"  {binary} --sample-rate 16000 > /dev/null")
    print("Approve the prompt in System Settings -> Privacy & Security -> Audio Capture.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="meeting-capture")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="show daemon status").set_defaults(func=cmd_status)
    sub.add_parser("start", help="start the daemon").set_defaults(func=cmd_start)
    sub.add_parser("stop", help="stop the daemon").set_defaults(func=cmd_stop)
    sub.add_parser("pause", help="pause capture (creates pause file)").set_defaults(func=cmd_pause)
    sub.add_parser("resume", help="resume capture").set_defaults(func=cmd_resume)
    sub.add_parser("run", help="run daemon in foreground").set_defaults(func=cmd_run)
    sub.add_parser("install", help="install launchd auto-start agent").set_defaults(func=cmd_install)
    sub.add_parser("uninstall", help="remove launchd agent").set_defaults(func=cmd_uninstall)
    sub.add_parser("check", help="verify audiotee is built and prompt audio-capture permission").set_defaults(func=cmd_check)
    sub.add_parser("mic", help="show current mic-activity state (the gate that triggers recording)").set_defaults(func=cmd_mic)
    sub.add_parser("last", help="print the path of the most recent transcript").set_defaults(func=cmd_last)
    sub.add_parser("tail", help="follow the daemon log").set_defaults(func=cmd_tail)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
