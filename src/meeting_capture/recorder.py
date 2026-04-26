"""Always-on system audio capture via the audiotee CLI (Core Audio Tap, macOS 14.2+).

audiotee streams raw PCM (int16, mono, configurable sample rate) on stdout. We read
that stream, chunk by silence, and emit WAV files for the transcriber. No driver,
no sudo, no kernel extension — only the user-grantable Audio Capture TCC permission.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

SAMPLE_RATE = 16_000
CHANNELS = 1
BYTES_PER_SAMPLE = 2  # int16 little-endian (audiotee resampled mode)
CHUNK_DURATION = 0.25  # how often audiotee flushes to stdout
SAMPLES_PER_BLOCK = int(SAMPLE_RATE * CHUNK_DURATION)
BLOCK_BYTES = SAMPLES_PER_BLOCK * CHANNELS * BYTES_PER_SAMPLE

SILENCE_RMS = 0.005
SILENCE_GAP_SECONDS = 3.0
MIN_CHUNK_SECONDS = 8.0
MAX_CHUNK_SECONDS = 600.0

AUDIOTEE_ENV_VAR = "MEETING_CAPTURE_AUDIOTEE"


def find_audiotee() -> Path | None:
    """Locate the audiotee binary. Search order: env var, vendored bin/, PATH."""
    env = os.environ.get(AUDIOTEE_ENV_VAR)
    if env and Path(env).is_file():
        return Path(env)

    pkg_dir = Path(__file__).resolve().parent
    for ancestor in [pkg_dir, *pkg_dir.parents]:
        candidate = ancestor / "bin" / "audiotee"
        if candidate.is_file():
            return candidate
        if (ancestor / ".git").exists():
            break

    on_path = shutil.which("audiotee")
    return Path(on_path) if on_path else None


def _rms_int16(block: np.ndarray) -> float:
    if block.size == 0:
        return 0.0
    floats = block.astype(np.float32) / 32768.0
    return float(np.sqrt(np.mean(np.square(floats, dtype=np.float64))))


@dataclass
class Chunk:
    path: Path
    started_at: float
    duration_seconds: float


FLUSH_MIN_SECONDS = 3.0


def stream_chunks(
    out_dir: Path,
    should_record,
    sample_rate: int = SAMPLE_RATE,
    audiotee_path: Path | None = None,
) -> Iterator[Chunk]:
    """Yield finished audio chunks while should_record() is True.

    Spawns audiotee, reads PCM, chunks by silence. When should_record() flips to
    False (e.g. the user hangs up), the in-flight buffer is flushed as a final
    chunk if it's at least FLUSH_MIN_SECONDS long, then the iterator exits and
    audiotee is terminated. This keeps the tail of a meeting from being lost.
    """
    binary = audiotee_path or find_audiotee()
    if binary is None:
        raise RuntimeError(
            "audiotee binary not found. Run setup.sh to build it, or set "
            f"{AUDIOTEE_ENV_VAR}=/path/to/audiotee."
        )

    cmd = [str(binary), "--sample-rate", str(sample_rate), "--chunk-duration", str(CHUNK_DURATION)]
    # Inherit our stderr so audiotee's JSON diagnostic log lands in the daemon log via launchd.
    # (Without this we have no visibility when the tap silently captures zeros.)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=0)
    if proc.stdout is None:
        raise RuntimeError("audiotee subprocess has no stdout")

    block_bytes = int(sample_rate * CHUNK_DURATION) * CHANNELS * BYTES_PER_SAMPLE

    buffer: list[np.ndarray] = []
    chunk_started: float | None = None
    silent_run = 0.0

    def _emit(audio: np.ndarray, started: float, min_seconds: float) -> Chunk | None:
        trimmed = _trim_trailing_silence(audio, sample_rate)
        if len(trimmed) / sample_rate < min_seconds:
            return None
        path = out_dir / f"chunk-{int(started)}.wav"
        sf.write(path, trimmed, sample_rate, subtype="PCM_16")
        return Chunk(path=path, started_at=started, duration_seconds=len(trimmed) / sample_rate)

    try:
        while should_record():
            raw = proc.stdout.read(block_bytes)
            if not raw:
                break
            block = np.frombuffer(raw, dtype="<i2")

            level = _rms_int16(block)
            if level >= SILENCE_RMS:
                if chunk_started is None:
                    chunk_started = time.time()
                buffer.append(block)
                silent_run = 0.0
            elif buffer:
                buffer.append(block)
                silent_run += CHUNK_DURATION

            duration = sum(len(b) for b in buffer) / sample_rate
            if buffer and (
                (silent_run >= SILENCE_GAP_SECONDS and duration >= MIN_CHUNK_SECONDS)
                or duration >= MAX_CHUNK_SECONDS
            ):
                audio = np.concatenate(buffer, axis=0)
                started = chunk_started or time.time()
                buffer.clear()
                chunk_started = None
                silent_run = 0.0

                chunk = _emit(audio, started, MIN_CHUNK_SECONDS)
                if chunk is not None:
                    yield chunk

        # should_record() went False — flush any in-flight buffer
        if buffer:
            audio = np.concatenate(buffer, axis=0)
            started = chunk_started or time.time()
            chunk = _emit(audio, started, FLUSH_MIN_SECONDS)
            if chunk is not None:
                yield chunk
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def _trim_trailing_silence(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    window = int(sample_rate * CHUNK_DURATION)
    if window <= 0 or audio.size <= window:
        return audio
    end = audio.shape[0]
    while end > window:
        if _rms_int16(audio[end - window : end]) >= SILENCE_RMS:
            break
        end -= window
    return audio[:end]
