"""
tests/test_ingestion.py
Unit tests verifying SHA-256 deduplication, ffmpeg audio extraction,
and the IngestionService workflow.
"""

import subprocess
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.ingestion.audio_extractor import extract_audio, find_ffmpeg_binary
from app.ingestion.service import IngestionService, compute_sha256
from app.models.schema import Base
from app.storage.local import LocalStorageProvider
import app.core.database


@pytest.fixture
def synthetic_video(tmp_path) -> Path:
    """
    Generate a 1-second test MP4 video with a test audio tone using ffmpeg.
    Avoids requiring real network or external video downloads during unit tests.
    """
    ffmpeg_bin = find_ffmpeg_binary()
    output_video = tmp_path / "synthetic_test_video.mp4"

    cmd = [
        ffmpeg_bin,
        "-y",
        "-f", "lavfi",
        "-i", "testsrc=duration=1:size=320x240:rate=10",
        "-f", "lavfi",
        "-i", "sine=frequency=1000:duration=1",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "64k",
        str(output_video),
    ]

    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    assert output_video.is_file()
    return output_video


def test_compute_sha256(synthetic_video):
    """Verify deterministic SHA-256 computation."""
    hash1 = compute_sha256(synthetic_video)
    hash2 = compute_sha256(synthetic_video)
    assert hash1 == hash2
    assert len(hash1) == 64


def test_extract_audio_ffmpeg(synthetic_video, tmp_path):
    """Verify audio extraction produces a valid m4a audio file."""
    output_audio = tmp_path / "extracted_tone.m4a"
    result = extract_audio(synthetic_video, output_path=output_audio)

    assert result.is_file()
    assert result.stat().st_size > 0
    assert result.suffix == ".m4a"


def test_ingestion_service_flow_and_deduplication(synthetic_video, tmp_path, monkeypatch):
    """
    Verify complete ingestion workflow:
    1. First ingestion stores video and audio and creates database record.
    2. Second ingestion of same video detects duplicate and skips re-processing.
    """
    # Create isolated test database
    test_db_url = f"sqlite:///{tmp_path / 'isolated_test.db'}"
    test_engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    # Monkeypatch the database sessionmaker so tests do not touch production app.db
    monkeypatch.setattr(app.core.database, "SessionLocal", TestingSessionLocal)

    # Create isolated storage
    storage = LocalStorageProvider(root_dir=tmp_path / "storage")
    service = IngestionService(storage=storage)

    # First Ingestion
    result1 = service.ingest(source=synthetic_video, style_id="test_style")
    assert not result1.is_duplicate
    assert result1.status == "stored"
    assert result1.video_id.startswith("v_")
    assert storage.exists(f"videos/test_style/{result1.video_id}.mp4")
    assert storage.exists(f"audio/test_style/{result1.video_id}.m4a")

    # Second Ingestion (exact same video) -> Must be flagged as duplicate
    result2 = service.ingest(source=synthetic_video, style_id="test_style")
    assert result2.is_duplicate
    assert result2.video_id == result1.video_id
    assert result2.sha256 == result1.sha256

