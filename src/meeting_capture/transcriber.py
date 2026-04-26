"""Local transcription via mlx-whisper (Apple Silicon)."""
from __future__ import annotations

from pathlib import Path

DEFAULT_MODEL = "mlx-community/whisper-small-mlx-q4"


def transcribe(audio_path: Path, model: str = DEFAULT_MODEL) -> str:
    import mlx_whisper

    result = mlx_whisper.transcribe(str(audio_path), path_or_hf_repo=model)
    return (result.get("text") or "").strip()
