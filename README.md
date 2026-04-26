# meeting-capture

Always-on, fully local audio capture daemon for macOS. Records system audio (whatever is playing through your speakers — Zoom, Meet, Teams, browser calls, anything) and writes timestamped Markdown transcripts to `~/transcripts/`. No cloud, no bot in the meeting, no UI presence.

Designed to feed [context-orchestrator](https://github.com/stirredo/context-orchestrator) — meeting-capture writes transcripts; context-orchestrator indexes them. The two are coupled only through the `~/transcripts/` directory, so each can fail independently.

## Why

Manual save-after-meeting workflows fail in practice (real-world adherence ~40%). Otter joins meetings as a visible bot. Granola needs a Google Workspace account. Cluely is cloud-only. None offer invisible local capture with auto file output, so this project does.

## How it works

```
System audio  →  BlackHole 2ch (virtual driver)
              →  sounddevice (silence-chunked recording, ~3s gap = chunk boundary)
              →  mlx-whisper (local, Apple Silicon)
              →  ~/transcripts/meeting-YYYY-MM-DDTHH-MM-SS.md
```

A new transcript file is started whenever the gap between chunks exceeds 15 minutes (i.e. a new meeting). The daemon stays in the background via launchd; raw audio chunks are deleted after transcription.

## Requirements

- macOS with Apple Silicon (mlx-whisper)
- Homebrew
- Python 3.10+

## Setup

```bash
git clone https://github.com/stirredo/meeting-capture.git
cd meeting-capture
./setup.sh
```

The script installs BlackHole 2ch and portaudio via Homebrew, creates a venv, and installs the package.

After setup, you must do one manual step: open **Audio MIDI Setup**, create a **Multi-Output Device** combining your normal speakers and **BlackHole 2ch**, then set that device as system output. This lets audio play normally while being captured.

## Use

```bash
# confirm BlackHole shows up as an input device
.venv/bin/meeting-capture devices

# install the launchd auto-start agent (runs at login)
.venv/bin/meeting-capture install

# manual control
.venv/bin/meeting-capture status
.venv/bin/meeting-capture pause      # touches ~/.meeting-capture/paused
.venv/bin/meeting-capture resume
.venv/bin/meeting-capture stop
.venv/bin/meeting-capture start
.venv/bin/meeting-capture run        # foreground (debugging)
```

For sensitive calls, `pause` until done, then `resume`.

## Files

- `~/transcripts/meeting-*.md` — final transcripts (this is what context-orchestrator watches)
- `~/.meeting-capture/daemon.log` — daemon log
- `~/.meeting-capture/paused` — pause sentinel
- `~/.meeting-capture/audio/` — temporary chunk WAVs (deleted after transcription)
- `~/Library/LaunchAgents/com.stirredo.meeting-capture.plist` — launchd agent

## Tests

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

Tests cover silence detection, trimming, session bucketing, and transcript appending. Recording and transcription themselves require hardware/audio and are exercised via the `run` and `devices` commands.
