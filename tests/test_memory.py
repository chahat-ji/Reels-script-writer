"""
tests/test_memory.py
Unit tests for Video Memory distillation, faceted metadata tagging,
and NumPy vector cosine similarity retrieval.
"""

from unittest.mock import MagicMock
import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.memory.index import EmbeddingClient, MemoryMatch, VectorRetriever
from app.memory.metadata import extract_memory_metadata
from app.memory.service import MemoryService
from app.memory.transformer import transform_to_video_memory
from app.models.extraction import (
    CompactCreativeDynamics,
    CompactScene,
    SpeakerEntry,
    VideoExtraction,
)
from app.models.schema import Base, Style, StyleReference, Video, VideoMemory
import app.core.database


@pytest.fixture
def sample_extraction() -> VideoExtraction:
    """Fixture providing a complete sample VideoExtraction."""
    return VideoExtraction(
        v=1,
        sp=[
            SpeakerEntry(c="A", n="Nani", desc="Mischievous opportunistic grandmother"),
            SpeakerEntry(c="B", n="Granddaughter", desc="Greedy naive young woman"),
        ],
        sc=[
            CompactScene(
                s=0,
                e=7000,
                loc="Living room",
                sit="Teasing over food",
                x=[
                    [1500, 4800, "A", "Oye dekh, khana khaa gaya.", "mocking", "points at dog"],
                ],
            ),
            CompactScene(
                s=7000,
                e=36000,
                loc="Kitchen",
                sit="Cash counter-con",
                x=[
                    [7000, 11500, "A", "Bhikari hai tu! Sharam nahi aati?", "indignant"],
                    [11700, 15000, "B", "Chhodo na Nani, aadhe-aadhe kar lenge!", "pleading"],
                    [15500, 18000, "A", "Ab karenge aadhe-aadhe!", "triumphant", "winks"],
                ],
            ),
        ],
        cd=CompactCreativeDynamics(
            mech=["status-reversal", "con-escalation"],
            setup="Granddaughter boasts about pocketing extra change.",
            esc="Nani feigns righteous indignation.",
            rev="Nani claims the note was 500 and extorts 300 more.",
            punch="Nani offers 50-50 split.",
            rhythm="Rapid back-and-forth listing",
            pace="Fast and bouncy",
            phys=["Counting cash", "Winking greedily"],
        ),
        lang="hi",
    )


def test_transform_to_video_memory(sample_extraction):
    """Verify Markdown distillation contains all required sections and resolved names."""
    markdown = transform_to_video_memory(video_id="v_test123", extraction=sample_extraction)

    assert "VIDEO v_test123" in markdown
    assert "CHARACTERS" in markdown
    assert "Nani — Mischievous opportunistic grandmother." in markdown
    assert "Granddaughter — Greedy naive young woman." in markdown

    assert "SETTING" in markdown
    assert "Living room, Kitchen" in markdown

    assert "SITUATION" in markdown
    assert "SEQUENCE" in markdown
    assert "DIALOGUE STYLE" in markdown
    assert "Language: Colloquial Hindi." in markdown

    assert "COMEDIC MECHANISMS" in markdown
    assert "- Status Reversal" in markdown
    assert "- Con Escalation" in markdown

    assert "PHYSICAL BEHAVIOR" in markdown
    assert "- Counting cash" in markdown

    assert "PACING" in markdown
    assert "Fast and bouncy." in markdown

    assert "REPRESENTATIVE DIALOGUE" in markdown
    # Verify speaker name was resolved from "A" -> "Nani"
    assert 'Nani: "' in markdown


def test_extract_memory_metadata(sample_extraction):
    """Verify faceted metadata tags extraction."""
    meta = extract_memory_metadata(sample_extraction)

    assert meta["characters"] == ["Nani", "Granddaughter"]
    assert meta["character_codes"] == ["A", "B"]
    assert "Living room" in meta["settings"]
    assert "Kitchen" in meta["settings"]
    assert meta["comedy_mechanisms"] == ["status-reversal", "con-escalation"]
    assert meta["pacing"] == "Fast and bouncy"
    assert meta["language"] == "hi"
    assert meta["scene_count"] == 2
    assert meta["dialogue_turn_count"] == 4


def test_numpy_vector_retriever_ranking(tmp_path, monkeypatch):
    """
    Verify in-memory pure NumPy cosine similarity ranking across SQLite BLOBs.
    """
    test_db_url = f"sqlite:///{tmp_path / 'retriever_test.db'}"
    test_engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(app.core.database, "SessionLocal", TestingSession)

    # 1. Insert two styles and video memories with synthetic vectors
    # Vector dim = 4 for simple testing
    query_vector = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
    close_vector = np.array([0.9, 0.1, 0.0, 0.0], dtype=np.float32)   # High cosine similarity
    distant_vector = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32) # Low cosine similarity

    with TestingSession() as sess:
        sess.add(Style(style_id="comedy_style", version=1))
        sess.add(Video(video_id="v_close", sha256="hash_close", storage_uri="file:///v_close.mp4"))
        sess.add(Video(video_id="v_distant", sha256="hash_distant", storage_uri="file:///v_distant.mp4"))

        mem1 = VideoMemory(video_id="v_close", style_id="comedy_style", memory_text="Close memory")
        mem1.set_embedding(close_vector)
        sess.add(mem1)

        mem2 = VideoMemory(video_id="v_distant", style_id="comedy_style", memory_text="Distant memory")
        mem2.set_embedding(distant_vector)
        sess.add(mem2)
        sess.commit()

    # 2. Mock EmbeddingClient to return query_vector
    mock_embed = MagicMock()
    mock_embed.embed_text.return_value = query_vector

    retriever = VectorRetriever(embed_client=mock_embed)
    matches = retriever.search_memories(query="test premise", style_id="comedy_style", top_k=2)

    assert len(matches) == 2
    assert matches[0].video_id == "v_close"
    assert matches[0].score > matches[1].score
    assert pytest.approx(matches[0].score, rel=1e-2) == 0.993  # Close to 1.0
    assert pytest.approx(matches[1].score, abs=1e-2) == 0.0    # Orthogonal


def test_memory_service_distill_and_index(sample_extraction, tmp_path, monkeypatch):
    """
    Verify complete MemoryService workflow:
    Loads extraction, distills Markdown, stores embedding BLOB, and marks video as indexed.
    """
    test_db_url = f"sqlite:///{tmp_path / 'service_test.db'}"
    test_engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    monkeypatch.setattr(app.core.database, "SessionLocal", TestingSession)

    # Insert baseline video
    with TestingSession() as sess:
        sess.add(Style(style_id="default_style", version=1))
        sess.add(Video(video_id="v_sample", sha256="hash_sample", storage_uri="file:///dummy.mp4", status="extracted"))
        sess.add(StyleReference(style_id="default_style", video_id="v_sample", relevance=1.0))
        sess.commit()

    # Mock load_archived_extraction to return sample_extraction
    monkeypatch.setattr(
        "app.memory.service.load_archived_extraction",
        lambda video_id: sample_extraction,
    )

    # Mock EmbeddingClient
    mock_embed = MagicMock()
    mock_embed.model_name = "text-embedding-004"
    mock_embed.embed_text.return_value = np.zeros(768, dtype=np.float32)

    service = MemoryService(embed_client=mock_embed)
    mem_record = service.distill_and_index_video(video_id="v_sample")

    assert mem_record is not None
    assert mem_record.video_id == "v_sample"
    assert "VIDEO v_sample" in mem_record.memory_text
    assert mem_record.get_embedding().shape == (768,)

    # Verify video status was updated to 'indexed'
    with TestingSession() as sess:
        updated_video = sess.query(Video).filter_by(video_id="v_sample").first()
        assert updated_video.status == "indexed"

