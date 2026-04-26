#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
PY="$VENV/bin/python"

echo "Setting up meeting-capture..."

# 1. macOS / Swift toolchain check
if ! command -v swift &>/dev/null; then
    echo "Swift not found. Installing Xcode command-line tools (interactive prompt may appear)..."
    xcode-select --install || true
    echo "Re-run setup.sh after the install finishes."
    exit 1
fi

OS_VERSION=$(sw_vers -productVersion)
echo "macOS $OS_VERSION, Swift $(swift --version | head -1)"

# 1b. ffmpeg (mlx-whisper shells out to it to decode WAVs)
if ! command -v ffmpeg &>/dev/null; then
    if command -v brew &>/dev/null; then
        echo "Installing ffmpeg (mlx-whisper dependency)..."
        brew install ffmpeg
    else
        echo "ERROR: ffmpeg is required by mlx-whisper but not on PATH and brew is not installed."
        echo "Install ffmpeg manually (e.g. https://evermeet.cx/ffmpeg/) and re-run."
        exit 1
    fi
fi

# 2. Build sysaudio (our ScreenCaptureKit-based audio capture binary)
mkdir -p "$SCRIPT_DIR/bin"
SYSAUDIO_BIN="$SCRIPT_DIR/bin/sysaudio"

echo "Building sysaudio (SCK, release)..."
(cd "$SCRIPT_DIR/swift" && swift build -c release --quiet)

SYSAUDIO_BUILT_DIR=$(cd "$SCRIPT_DIR/swift" && swift build -c release --show-bin-path)
SYSAUDIO_BUILT="$SYSAUDIO_BUILT_DIR/sysaudio"
if [ ! -x "$SYSAUDIO_BUILT" ]; then
    echo "sysaudio build failed — no binary at $SYSAUDIO_BUILT"
    exit 1
fi

cp "$SYSAUDIO_BUILT" "$SYSAUDIO_BIN"
codesign --force --sign - "$SYSAUDIO_BIN" 2>/dev/null || true
chmod +x "$SYSAUDIO_BIN"
echo "sysaudio binary: $SYSAUDIO_BIN"

# 3. venv + install
if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV"
fi

echo "Installing meeting-capture..."
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -e "$SCRIPT_DIR"

# 4. One-time TCC permission prompt
echo ""
echo "Triggering screen-recording permission prompt (approve in System Settings)..."
echo "  (Will exit after ~2 seconds.)"
"$SYSAUDIO_BIN" --sample-rate 16000 >/dev/null 2>&1 &
PROBE_PID=$!
sleep 2
kill "$PROBE_PID" 2>/dev/null || true
wait "$PROBE_PID" 2>/dev/null || true

# 5. Next steps
cat <<EOF

Done. Next steps:
  $PY -m meeting_capture.cli check     # confirm sysaudio + permission
  $PY -m meeting_capture.cli install   # launchd auto-start at login
  $PY -m meeting_capture.cli status

Permission: System Settings -> Privacy & Security -> Screen & System Audio Recording.
The permission attaches to the parent terminal (Warp / Terminal / iTerm), not the
binary itself — restart the terminal once after granting.

Transcripts land in ~/transcripts/ (picked up by context-orchestrator's transcript-watcher).
Pause:  touch ~/.meeting-capture/paused
Resume: rm    ~/.meeting-capture/paused
EOF
