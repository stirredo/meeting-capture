import time
from pathlib import Path

from meeting_capture import cli


def test_format_age_seconds():
    assert cli._format_age(5) == "5s ago"


def test_format_age_minutes():
    assert cli._format_age(125) == "2m ago"


def test_format_age_hours():
    assert cli._format_age(7200) == "2h ago"


def test_format_age_days():
    assert cli._format_age(86400 * 3) == "3d ago"


def test_last_transcript_returns_none_when_dir_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "TRANSCRIPTS_DIR", tmp_path)
    assert cli._last_transcript() is None


def test_last_transcript_returns_most_recent(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "TRANSCRIPTS_DIR", tmp_path)
    older = tmp_path / "meeting-2026-01-01T00-00-00.md"
    newer = tmp_path / "meeting-2026-04-26T14-00-00.md"
    older.write_text("old")
    newer.write_text("new")
    import os
    past = time.time() - 3600
    os.utime(older, (past, past))
    assert cli._last_transcript() == newer


def test_last_chunk_log_line_returns_none_when_no_log(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "LOG_FILE", tmp_path / "missing.log")
    assert cli._last_chunk_log_line() is None


def test_last_chunk_log_line_finds_chunk_line(tmp_path, monkeypatch):
    log = tmp_path / "daemon.log"
    log.write_text(
        "2026-04-26 14:00:00 INFO meeting-capture daemon starting\n"
        "2026-04-26 14:01:00 INFO chunk 30.0s -> meeting-x.md (1234 chars)\n"
        "2026-04-26 14:01:30 INFO mic inactive — session ended\n"
    )
    monkeypatch.setattr(cli, "LOG_FILE", log)
    line = cli._last_chunk_log_line()
    assert line is not None
    assert "chunk 30.0s" in line
    assert "1234 chars" in line


def test_last_chunk_log_line_skips_non_chunk_lines(tmp_path, monkeypatch):
    log = tmp_path / "daemon.log"
    log.write_text("INFO some other line\nINFO another line\n")
    monkeypatch.setattr(cli, "LOG_FILE", log)
    assert cli._last_chunk_log_line() is None
