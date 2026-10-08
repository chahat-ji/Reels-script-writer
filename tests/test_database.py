"""
tests/test_database.py
Unit tests verifying SQLite database engine, tables, constraints, and NumPy embedding serialization.
"""

import pytest
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models.schema import Base, Style, Video, VideoMemory, StyleReference


@pytest.fixture
def db_session():
    """Provides an isolated in-memory SQLite database session for each test."""
    test_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=test_engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_create_style(db_session):
    """Verify Style creation and default versioning."""
    style = Style(style_id="desi_comedy_01", bible_text="# Desi Comedy Style Bible")
    db_session.add(style)
    db_session.commit()

    retrieved = db_session.query(Style).filter_by(style_id="desi_comedy_01").first()
    assert retrieved is not None
    assert retrieved.version == 1
    assert "Desi Comedy" in retrieved.bible_text


def test_video_sha256_uniqueness(db_session):
    """Verify SHA-256 duplicate constraint enforcement."""
    v1 = Video(
        video_id="v_001",
        sha256="abc123def456",
        storage_uri="file:///data/videos/style_01/v_001.mp4",
        status="stored",
    )
    db_session.add(v1)
    db_session.commit()

    # Attempting to add another video with identical SHA-256 must fail
    v2 = Video(
        video_id="v_002",
        sha256="abc123def456",
        storage_uri="file:///data/videos/style_01/v_002.mp4",
        status="stored",
    )
    db_session.add(v2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_video_memory_with_numpy_embedding(db_session):
    """Verify VideoMemory storage and NumPy embedding array round-trip."""
    style = Style(style_id="style_01")
    video = Video(
        video_id="v_001",
        sha256="hash_001",
        storage_uri="file:///data/videos/style_01/v_001.mp4",
    )
    db_session.add_all([style, video])
    db_session.commit()

    # Create dummy 768-dim float32 embedding
    original_vector = np.random.rand(768).astype(np.float32)

    memory = VideoMemory(
        video_id="v_001",
        style_id="style_01",
        memory_text="Sample Video Memory Markdown",
        structured_extraction={"v": 1, "sp": {"A": "Saala"}},
        metadata_json={"comedy": ["teasing", "reversal"]},
    )
    memory.set_embedding(original_vector)
    db_session.add(memory)
    db_session.commit()

    # Retrieve and verify embedding matches perfectly
    retrieved = db_session.query(VideoMemory).filter_by(video_id="v_001").first()
    assert retrieved is not None
    restored_vector = retrieved.get_embedding()
    assert restored_vector is not None
    assert restored_vector.shape == (768,)
    assert np.allclose(original_vector, restored_vector)


def test_style_reference_relationship(db_session):
    """Verify StyleReference links styles and videos."""
    style = Style(style_id="style_01")
    video = Video(
        video_id="v_001",
        sha256="hash_001",
        storage_uri="file:///data/videos/style_01/v_001.mp4",
    )
    db_session.add_all([style, video])
    db_session.commit()

    ref = StyleReference(style_id="style_01", video_id="v_001", relevance=0.95)
    db_session.add(ref)
    db_session.commit()

    retrieved_style = db_session.query(Style).filter_by(style_id="style_01").first()
    assert len(retrieved_style.references) == 1
    assert retrieved_style.references[0].video_id == "v_001"
    assert retrieved_style.references[0].relevance == 0.95

