#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
PY="$VENV/bin/python"

echo "Setting up meeting-capture..."

# 1. BlackHole virtual audio driver (one-time)
if ! brew list --cask blackhole-2ch &>/dev/null; then
    echo "Installing BlackHole 2ch (system audio capture driver)..."
    brew install --cask blackhole-2ch
    echo ""
    echo "  IMPORTANT: open Audio MIDI Setup and create a Multi-Output Device"
    echo "  combining your speakers + BlackHole 2ch, then set it as system output."
    echo "  Otherwise audio won't be captured (or won't play through speakers)."
    echo ""
else
    echo "BlackHole 2ch already installed."
fi

# 2. portaudio (sounddevice dep)
if ! brew list portaudio &>/dev/null; then
    echo "Installing portaudio..."
    brew install portaudio
fi

# 3. venv + install
if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV"
fi

echo "Installing meeting-capture..."
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -e "$SCRIPT_DIR"

# 4. Show next steps
echo ""
echo "Done. Next steps:"
echo "  $PY -m meeting_capture.cli devices    # confirm BlackHole shows up"
echo "  $PY -m meeting_capture.cli install    # install launchd auto-start"
echo "  $PY -m meeting_capture.cli status     # check daemon"
echo ""
echo "Transcripts will land in ~/transcripts/  (picked up by context-orchestrator)"
echo "Pause:  touch ~/.meeting-capture/paused"
echo "Resume: rm    ~/.meeting-capture/paused"
