"""Always-on audio capture from BlackHole, chunked by silence."""
from __future__ import annotations

import queue
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

SAMPLE_RATE = 16_000
CHANNELS = 1
BLOCK_SECONDS = 0.25
SILENCE_RMS = 0.005
SILENCE_GAP_SECONDS = 3.0
MIN_CHUNK_SECONDS = 8.0
MAX_CHUNK_SECONDS = 600.0
DEVICE_NAME_HINT = "BlackHole"


def find_input_device(name_hint: str = DEVICE_NAME_HINT) -> int | None:
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0 and name_hint.lower() in dev["name"].lower():
            return idx
    return None


def _rms(block: np.ndarray) -> float:
    if block.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(block, dtype=np.float64))))


@dataclass
class Chunk:
    path: Path
    started_at: float
    duration_seconds: float


def stream_chunks(
    out_dir: Path,
    is_paused,
    sample_rate: int = SAMPLE_RATE,
    device: int | None = None,
) -> Iterator[Chunk]:
    """Yield finished audio chunks. Caller drives consumption (transcription, cleanup)."""
    device = device if device is not None else find_input_device()
    if device is None:
        raise RuntimeError(
            "No BlackHole input device found. Run `brew install blackhole-2ch` and "
            "configure a Multi-Output Device in Audio MIDI Setup."
        )

    block_size = int(sample_rate * BLOCK_SECONDS)
    blocks: queue.Queue[np.ndarray] = queue.Queue()

    def callback(indata, frames, time_info, status):
        blocks.put(indata.copy())

    buffer: list[np.ndarray] = []
    chunk_started: float | None = None
    silent_run = 0.0

    with sd.InputStream(
        samplerate=sample_rate,
        channels=CHANNELS,
        device=device,
        blocksize=block_size,
        dtype="float32",
        callback=callback,
    ):
        while True:
            try:
                block = blocks.get(timeout=1.0)
            except queue.Empty:
                continue

            if is_paused():
                buffer.clear()
                chunk_started = None
                silent_run = 0.0
                continue

            level = _rms(block)
            if level >= SILENCE_RMS:
                if chunk_started is None:
                    chunk_started = time.time()
                buffer.append(block)
                silent_run = 0.0
            elif buffer:
                buffer.append(block)
                silent_run += BLOCK_SECONDS

            duration = len(buffer) * BLOCK_SECONDS
            if buffer and (
                (silent_run >= SILENCE_GAP_SECONDS and duration >= MIN_CHUNK_SECONDS)
                or duration >= MAX_CHUNK_SECONDS
            ):
                audio = np.concatenate(buffer, axis=0)
                buffer.clear()
                started = chunk_started or time.time()
                chunk_started = None
                silent_run = 0.0

                trimmed = _trim_trailing_silence(audio)
                if len(trimmed) / sample_rate < MIN_CHUNK_SECONDS:
                    continue

                path = out_dir / f"chunk-{int(started)}.wav"
                sf.write(path, trimmed, sample_rate, subtype="PCM_16")
                yield Chunk(path=path, started_at=started, duration_seconds=len(trimmed) / sample_rate)


def _trim_trailing_silence(audio: np.ndarray, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    window = int(sample_rate * BLOCK_SECONDS)
    if window <= 0 or audio.size <= window:
        return audio
    end = audio.shape[0]
    while end > window:
        chunk = audio[end - window : end]
        if _rms(chunk) >= SILENCE_RMS:
            break
        end -= window
    return audio[:end]
