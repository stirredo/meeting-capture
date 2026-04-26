# meeting-capture

Always-on, fully local audio capture daemon for macOS. Records system audio (whatever is playing through your speakers — Zoom, Meet, Teams, browser calls, anything) and writes timestamped Markdown transcripts to `~/transcripts/`. **No driver, no kernel extension, no `sudo`, no reboot.** Just one user-grantable Audio Capture permission.

Designed to feed [context-orchestrator](https://github.com/stirredo/context-orchestrator) — meeting-capture writes transcripts; context-orchestrator's `transcript-watcher` indexes them. The two are coupled only through the `~/transcripts/` directory, so each can fail independently.

## Why

Manual save-after-meeting workflows fail in practice (real-world adherence ~40%). Otter joins meetings as a visible bot. Granola needs a Google Workspace account. Cluely is cloud-only. None offer invisible local capture with auto file output, so this project does.

## How it works

```
System audio  →  audiotee (Core Audio Tap, macOS 14.2+)
              →  PCM stream on stdout (int16 @ 16kHz mono)
              →  Python daemon (silence-chunked, ~3s gap = chunk boundary)
              →  mlx-whisper (local transcription, Apple Silicon)
              →  ~/transcripts/meeting-YYYY-MM-DDTHH-MM-SS.md
```

A new transcript file is started whenever the gap between chunks exceeds 15 minutes (= a new meeting). The daemon stays in the background via launchd; raw audio chunks are deleted after transcription.

The audio source is [`audiotee`](https://github.com/makeusabrew/audiotee), a tiny Swift CLI that wraps Apple's Core Audio Tap API (`CATapDescription` / `AudioHardwareCreateProcessTap`). This is the same API category that lets Cluely-style tools work without admin rights.

## Requirements

- macOS **14.2+** (Core Audio Tap API)
- Apple Silicon (mlx-whisper)
- Python 3.10+
- Xcode command-line tools (for building `audiotee` — `xcode-select --install`)
- **No `sudo` required**

## Setup

```bash
git clone https://github.com/stirredo/meeting-capture.git
cd meeting-capture
./setup.sh
```

`setup.sh` clones [audiotee](https://github.com/makeusabrew/audiotee) into `vendor/`, builds it via `swift build -c release`, ad-hoc codesigns the binary, drops it in `bin/audiotee`, then creates a Python venv and installs the package. It also fires `audiotee` once briefly to trigger the system permission prompt.

After setup, approve the prompt in **System Settings → Privacy & Security → Audio Capture** for the `audiotee` binary. That's it — no kernel driver to authorize, no reboot.

## Use

```bash
.venv/bin/meeting-capture check       # verify audiotee + permission
.venv/bin/meeting-capture install     # install launchd auto-start agent
.venv/bin/meeting-capture status
.venv/bin/meeting-capture pause       # touches ~/.meeting-capture/paused
.venv/bin/meeting-capture resume
.venv/bin/meeting-capture stop
.venv/bin/meeting-capture start
.venv/bin/meeting-capture run         # foreground (debugging)
```

For sensitive calls, `pause` until done, then `resume`.

## Files

- `~/transcripts/meeting-*.md` — final transcripts (this is what context-orchestrator watches)
- `~/.meeting-capture/daemon.log` — daemon log
- `~/.meeting-capture/paused` — pause sentinel
- `~/.meeting-capture/audio/` — temporary chunk WAVs (deleted after transcription)
- `~/Library/LaunchAgents/com.stirredo.meeting-capture.plist` — launchd agent
- `bin/audiotee` — the audio source binary (built locally, gitignored)

## Tests

```bash
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

Tests cover silence detection, trimming, audiotee discovery, session bucketing, and transcript appending. End-to-end recording is exercised via the `run` and `check` commands.

## Why this works on locked-down work laptops

Pre-2023 system-audio capture on macOS required a kernel-level audio driver (BlackHole, Soundflower, Loopback, etc.), which needs `sudo` to install and an admin reboot to load. On corporate laptops with MDM, that's a non-starter.

Core Audio Tap (macOS 14.2+) and ScreenCaptureKit (macOS 13+) moved system-audio access into user-space APIs gated by per-app TCC permissions. Users can grant those permissions themselves — no admin, no driver, no reboot.
