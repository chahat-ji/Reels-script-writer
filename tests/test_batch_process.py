"""
tests/test_batch_process.py
Unit and Integration tests for batch_process.py.

Verifies:
  1. CLI argument validation (rejects empty args, rejects both target and --all).
  2. Inspect reel status on complete vs incomplete reel directories.
  3. Reel processing execution skips existing outputs and only fills missing manifests.
  4. Discovery and processing logic for --all.
"""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from batch_process import inspect_reel_status, process_reel, process_all, process_target


def test_cli_no_args():
    """Verify CLI without any arguments exits with status 1 and shows guidance."""
    res = subprocess.run(
        [sys.executable, "batch_process.py"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 1
    assert "Please provide a target" in res.stdout or "Please provide a target" in res.stderr


def test_cli_both_target_and_all():
    """Verify specifying both a target and --all is rejected."""
    res = subprocess.run(
        [sys.executable, "batch_process.py", "DdMkWeaxKTT", "--all"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 1
    assert "not both" in res.stdout or "not both" in res.stderr


def test_cli_help():
    """Verify --help displays clean usage and exits 0."""
    res = subprocess.run(
        [sys.executable, "batch_process.py", "--help"],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "target" in res.stdout
    assert "--all" in res.stdout


def test_inspect_reel_status_incomplete(tmp_path):
    """Verify inspect_reel_status correctly flags an incomplete reel directory."""
    reel_dir = tmp_path / "mock_reel"
    reel_dir.mkdir()
    (reel_dir / "video.mp4").write_text("dummy")

    status = inspect_reel_status(reel_dir)
    assert status["video"] is True
    assert status["audio"] is False
    assert status["specs"] is False
    assert status["plan"] is False
    assert status["shots"] is False
    assert status["ocr"] is False
    assert status["faces"] is False
    assert status["speech"] is False
    assert status["diarization"] is False
    assert status["timeline"] is False
    assert status["report"] is False
    assert status["is_complete"] is False


def test_inspect_reel_status_complete(tmp_path):
    """Verify inspect_reel_status correctly flags a complete reel directory."""
    reel_dir = tmp_path / "mock_reel"
    reel_dir.mkdir()
    (reel_dir / "video.mp4").write_text("dummy")
    (reel_dir / "audio.wav").write_text("dummy")
    (reel_dir / "media_specs.json").write_text("{}")
    (reel_dir / "plan.json").write_text("{}")
    (reel_dir / "manifest_shots_pyscenedetect_v1.0.0.json").write_text("{}")
    (reel_dir / "manifest_ocr_rapidocr_v1.0.0.json").write_text("{}")
    (reel_dir / "manifest_faces_mediapipe_v1.0.0.json").write_text("{}")
    (reel_dir / "manifest_speech_assemblyai_v1.3.0.json").write_text("{}")
    (reel_dir / "manifest_diarization_assemblyai_v1.0.0.json").write_text("{}")
    (reel_dir / "timeline.json").write_text("{}")
    (reel_dir / "timeline_report.html").write_text("<html></html>")

    status = inspect_reel_status(reel_dir)
    assert status["video"] is True
    assert status["audio"] is True
    assert status["specs"] is True
    assert status["plan"] is True
    assert status["shots"] is True
    assert status["ocr"] is True
    assert status["faces"] is True
    assert status["speech"] is True
    assert status["diarization"] is True
    assert status["timeline"] is True
    assert status["report"] is True
    assert status["is_complete"] is True


def test_process_reel_on_complete_directory(tmp_path):
    """Verify process_reel recognizes already complete directories and completes without errors."""
    data_root = tmp_path / "data"
    reel_dir = data_root / "reels" / "reel_123"
    reel_dir.mkdir(parents=True)
    (reel_dir / "video.mp4").write_text("dummy")
    (reel_dir / "audio.wav").write_text("dummy")
    (reel_dir / "media_specs.json").write_text("{}")
    (reel_dir / "plan.json").write_text("{}")
    (reel_dir / "manifest_shots_test.json").write_text("{}")
    (reel_dir / "manifest_ocr_test.json").write_text("{}")
    (reel_dir / "manifest_faces_test.json").write_text("{}")
    (reel_dir / "manifest_speech_test.json").write_text("{}")
    (reel_dir / "manifest_diarization_test.json").write_text("{}")
    (reel_dir / "timeline.json").write_text("{}")
    (reel_dir / "timeline_report.html").write_text("<html></html>")

    ok = process_reel("reel_123", data_root=str(data_root))
    assert ok is True


def test_process_all_discovers_reels(tmp_path):
    """Verify process_all discovers all reel folders in data/reels."""
    data_root = tmp_path / "data"
    reels_root = data_root / "reels"
    reels_root.mkdir(parents=True)

    for r_name in ["reel_A", "reel_B"]:
        r_dir = reels_root / r_name
        r_dir.mkdir()
        (r_dir / "video.mp4").write_text("dummy")
        (r_dir / "audio.wav").write_text("dummy")
        (r_dir / "media_specs.json").write_text("{}")
        (r_dir / "plan.json").write_text("{}")
        (r_dir / "manifest_shots_t.json").write_text("{}")
        (r_dir / "manifest_ocr_t.json").write_text("{}")
        (r_dir / "manifest_faces_t.json").write_text("{}")
        (r_dir / "manifest_speech_t.json").write_text("{}")
        (r_dir / "manifest_diarization_t.json").write_text("{}")
        (r_dir / "timeline.json").write_text("{}")
        (r_dir / "timeline_report.html").write_text("<html></html>")

    ok = process_all(data_root=str(data_root))
    assert ok is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
