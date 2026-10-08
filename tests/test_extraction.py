"""
tests/test_extraction.py
Unit tests verifying compact structured JSON schema, Romanized dialogue,
turn array unpacking, archival storage, and GeminiExtractor lifecycle.
"""

from unittest.mock import MagicMock
import pytest
from app.extraction.archive import archive_extraction, load_archived_extraction
from app.extraction.gemini_extractor import GeminiExtractor
from app.models.extraction import (
    CompactCreativeDynamics,
    CompactScene,
    SpeakerEntry,
    VideoExtraction,
)
from app.models.schema import Video, Style, Base
import app.core.database
import app.core.config
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture
def sample_compact_extraction() -> VideoExtraction:
    """Fixture providing a sample compact VideoExtraction matching Section 6 of description.txt."""
    scene = CompactScene(
        s=0,
        e=28500,
        loc="Domestic kitchen",
        sit="Saala proudly presents ordinary coffee",
        x=[
            [0, 2500, "A", "Lo ji garma garam coffee piyo.", "friendly", "hands over steaming cup"],
            [2500, 5200, "B", "Hmm, achha ji, kaanch ke bartan?", "skeptical", "inspects cup"],
            [5200, 7000, "A", "Haan ji."],
        ],
    )

    return VideoExtraction(
        v=1,
        sp=[
            SpeakerEntry(c="A", n="Saala", desc="confident, eager to impress, defensive"),
            SpeakerEntry(c="B", n="Jija", desc="dry, deadpan skeptic, status undercutter"),
        ],
        sc=[scene],
        cd=CompactCreativeDynamics(
            mech=["status-undercutting", "escalation", "reversal"],
            setup="Saala presents coffee",
            esc="Jija questions hot glass safety",
            rev="Saala defends boiling glass handle",
            punch="Handle is also boiling glass",
            rhythm="short turns (1.5-3s), high density",
            pace="fast",
            phys=["presents cup", "inspects at arm's length"],
        ),
        lang="hi",
    )


def test_compact_schema_and_turn_unpacking(sample_compact_extraction):
    """Verify single-letter speaker codes, Roman script dialogue, and turn unpacking."""
    extraction = sample_compact_extraction

    # Verify single-letter codes
    assert "A" in extraction.speakers
    assert "B" in extraction.speakers
    assert extraction.speakers["A"] == "Saala"
    assert extraction.speakers["B"] == "Jija"

    # Verify turn array structure
    scene = extraction.sc[0]
    turn_1 = scene.x[0]
    assert turn_1[0] == 0
    assert turn_1[1] == 2500
    assert turn_1[2] == "A"
    # Ensure dialogue is in Roman / Latin script (no non-ASCII Indic characters)
    dialogue_str = turn_1[3]
    assert dialogue_str == "Lo ji garma garam coffee piyo."
    assert all(ord(char) < 128 for char in dialogue_str)

    # Test unpack_turns() resolving "A" -> "Saala"
    unpacked = extraction.unpack_turns()
    assert len(unpacked) == 3
    assert unpacked[0].speaker_code == "A"
    assert unpacked[0].speaker_name == "Saala"
    assert unpacked[0].dialogue == "Lo ji garma garam coffee piyo."
    assert unpacked[0].emotion == "friendly"
    assert unpacked[0].action == "hands over steaming cup"

    assert unpacked[1].speaker_code == "B"
    assert unpacked[1].speaker_name == "Jija"
    assert unpacked[1].dialogue == "Hmm, achha ji, kaanch ke bartan?"
    assert unpacked[1].emotion == "skeptical"

    # Optional action omitted in turn 3
    assert unpacked[2].speaker_code == "A"
    assert unpacked[2].dialogue == "Haan ji."
    assert unpacked[2].emotion is None
    assert unpacked[2].action is None


def test_archive_and_load_compact_extraction(sample_compact_extraction, tmp_path, monkeypatch):
    """Verify archival persistence and retrieval from disk and database."""
    test_db_url = f"sqlite:///{tmp_path / 'archive_test.db'}"
    test_engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=test_engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    monkeypatch.setattr(app.core.database, "SessionLocal", TestingSession)
    monkeypatch.setattr(app.core.config.settings, "extractions_dir", tmp_path / "extractions")

    # Add prerequisite records
    with TestingSession() as sess:
        sess.add(Style(style_id="default_style", version=1))
        sess.add(Video(video_id="v_test123", sha256="test_hash_123", storage_uri="file:///dummy.mp4"))
        sess.commit()

    # Archive
    archive_path = archive_extraction(video_id="v_test123", extraction=sample_compact_extraction, version=1)
    assert archive_path.is_file()

    # Load back
    loaded = load_archived_extraction(video_id="v_test123", version=1)
    assert loaded is not None
    assert loaded.v == 1
    assert loaded.speakers["A"] == "Saala"
    assert len(loaded.sc) == 1
    assert loaded.sc[0].x[0][3] == "Lo ji garma garam coffee piyo."
    assert "status-undercutting" in loaded.cd.mech


def test_gemini_extractor_lifecycle_and_cleanup(sample_compact_extraction, tmp_path, monkeypatch):
    """
    Verify GeminiExtractor file lifecycle:
    Uploads file, awaits active, parses compact extraction, and deletes remote file.
    """
    mock_client = MagicMock()

    mock_remote_file = MagicMock()
    mock_remote_file.name = "files/mock_remote_video_123"
    mock_remote_file.state.name = "ACTIVE"
    mock_client.files.upload.return_value = mock_remote_file

    mock_response = MagicMock()
    mock_response.text = sample_compact_extraction.model_dump_json()
    mock_client.models.generate_content.return_value = mock_response

    dummy_video = tmp_path / "test_video.mp4"
    dummy_video.write_bytes(b"dummy video data")

    monkeypatch.setattr(
        GeminiExtractor,
        "_resolve_video_path",
        lambda self, video_id: dummy_video,
    )
    monkeypatch.setattr(
        "app.extraction.gemini_extractor.archive_extraction",
        lambda video_id, extraction, version: tmp_path / "archived.json",
    )

    extractor = GeminiExtractor(client=mock_client, model_name="gemini-3.8-flash")
    result = extractor.extract(video_id="v_mock_001")

    # Verify upload called
    mock_client.files.upload.assert_called_once()

    # Verify model called with gemini-3.8-flash
    call_args = mock_client.models.generate_content.call_args
    assert call_args.kwargs["model"] == "gemini-3.8-flash"

    # Verify remote file was deleted (lifecycle cleanup requirement)
    mock_client.files.delete.assert_called_once_with(name="files/mock_remote_video_123")

    assert result.v == 1
    assert result.speakers["A"] == "Saala"
    assert result.sc[0].x[0][2] == "A"
