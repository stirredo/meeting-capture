#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
PY="$VENV/bin/python"
VENDOR="$SCRIPT_DIR/vendor/audiotee"
BIN="$SCRIPT_DIR/bin/audiotee"

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

# 2. Build audiotee (Core Audio Tap CLI — no driver, no sudo)
mkdir -p "$SCRIPT_DIR/vendor" "$SCRIPT_DIR/bin"
if [ ! -d "$VENDOR/.git" ]; then
    echo "Cloning audiotee..."
    git clone --depth=1 https://github.com/makeusabrew/audiotee.git "$VENDOR"
else
    echo "Updating audiotee..."
    git -C "$VENDOR" pull --ff-only --quiet || true
fi

echo "Building audiotee (release)..."
(cd "$VENDOR" && swift build -c release --quiet)

BUILT=$(find "$VENDOR/.build/release" -maxdepth 1 -type f -name audiotee -perm -111 | head -1)
if [ -z "$BUILT" ]; then
    echo "audiotee build failed — no binary at $VENDOR/.build/release/audiotee"
    exit 1
fi

cp "$BUILT" "$BIN"
codesign --force --sign - "$BIN" 2>/dev/null || true
chmod +x "$BIN"
echo "audiotee binary: $BIN"

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
echo "Triggering audio-capture permission prompt (approve in System Settings)..."
echo "  (Will exit after ~2 seconds.)"
"$BIN" --sample-rate 16000 >/dev/null 2>&1 &
PROBE_PID=$!
sleep 2
kill "$PROBE_PID" 2>/dev/null || true
wait "$PROBE_PID" 2>/dev/null || true

# 5. Next steps
cat <<EOF

Done. Next steps:
  $PY -m meeting_capture.cli check     # confirm audiotee + permission
  $PY -m meeting_capture.cli install   # launchd auto-start at login
  $PY -m meeting_capture.cli status

Permission: System Settings -> Privacy & Security -> Audio Capture -> allow audiotee.

Transcripts land in ~/transcripts/ (picked up by context-orchestrator's transcript-watcher).
Pause:  touch ~/.meeting-capture/paused
Resume: rm    ~/.meeting-capture/paused
EOF
