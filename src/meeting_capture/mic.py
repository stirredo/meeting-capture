"""Microphone activity detection — proxy for 'we are in a call right now'.

Uses AVFoundation.AVCaptureDevice.isInUseByAnotherApplication. When any other
process (Zoom, Teams, FaceTime, browser-based meeting, Slack call, etc.) has
opened the default input device, this returns True. Our daemon does not open
the mic itself, so this is a clean proxy for 'someone else is on a call.'

False positives: voice memos, Siri, dictation, voice-to-text. All rare and
the resulting transcripts are easy to delete from ~/transcripts/.
False negatives: meetings where you never unmute. Transcript still captures
the other side via system audio output, so this is fine.
"""
from __future__ import annotations


def is_mic_active() -> bool:
    """Return True if the default input device is in use by another app."""
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
    except ImportError:
        return False
    device = AVCaptureDevice.defaultDeviceWithMediaType_(AVMediaTypeAudio)
    if device is None:
        return False
    return bool(device.isInUseByAnotherApplication())


def mic_name() -> str | None:
    """Return the localized name of the default input device, for diagnostics."""
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio
    except ImportError:
        return None
    device = AVCaptureDevice.defaultDeviceWithMediaType_(AVMediaTypeAudio)
    return device.localizedName() if device else None
