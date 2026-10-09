"""
tests/test_queue_and_cli.py
Unit tests for IngestionQueue and Unified CLI argument handling.

Strictly offline: all external services and models are mocked.
"""

from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.cli import build_parser
from app.ingestion.queue import BatchResult, IngestionQueue
from app.ingestion.service import IngestionResult
from app.models.schema import Base, Style
import app.core.database


@pytest.fixture
def mock_db_session(tmp_path, monkeypatch):
    """Provide an isolated SQLite database session."""
    db_file = tmp_path / "test_cli.db"
    test_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(test_engine)
    TestingSession = sessionmaker(bind=test_engine)

    monkeypatch.setattr(app.core.database, "engine", test_engine)
    monkeypatch.setattr(app.core.database, "SessionLocal", TestingSession)

    return TestingSession


def test_ingestion_queue_concurrent_batch():
    """Verify IngestionQueue processes items with worker pool and triggers 1 style synthesis at end."""
    mock_ingestion_service = MagicMock()
    mock_ingestion_service.ingest.side_effect = lambda source: IngestionResult(
        video_id=f"v_{source}",
        sha256=f"hash_{source}",
        storage_uri=f"/path/{source}.mp4",
        audio_uri=f"/path/{source}.m4a",
        duration_ms=30000,
        is_duplicate=False,
        status="stored",
        message="Success",
    )

    mock_extractor = MagicMock()
    mock_memory_service = MagicMock()
    mock_style_service = MagicMock()
    mock_style_record = MagicMock()
    mock_style_record.version = 2
    mock_style_service.synthesize_style.return_value = mock_style_record

    queue = IngestionQueue(
        max_workers=2,
        ingestion_service=mock_ingestion_service,
        extractor=mock_extractor,
        memory_service=mock_memory_service,
        style_service=mock_style_service,
    )

    sources = ["video1", "video2", "video3"]
    result = queue.process_batch(
        sources=sources,
        style_id="c_comedy",
        auto_synthesize=True,
    )

    assert result.total == 3
    assert len(result.succeeded) == 3
    assert len(result.failed) == 0
    assert result.style_bible_version == 2

    # Verify that Ingestion & Memory were called 3 times (once per video)
    assert mock_ingestion_service.ingest.call_count == 3
    assert mock_memory_service.distill_and_index_video.call_count == 3

    # Verify that Style Synthesis was called exactly ONCE in a single batch
    mock_style_service.synthesize_style.assert_called_once_with(style_id="c_comedy")


def test_cli_parser_commands():
    """Verify CLI parser correctly parses commands and arguments."""
    parser = build_parser()

    # User login
    args1 = parser.parse_args(["user", "login", "rosh", "--email", "rosh@example.com"])
    assert args1.subcommand == "user"
    assert args1.user_action == "login"
    assert args1.username == "rosh"
    assert args1.email == "rosh@example.com"

    # Creator add
    args2 = parser.parse_args(["creator", "add", "Nani Comedy", "--id", "nani_comedy", "--desc", "Hilarious reels"])
    assert args2.subcommand == "creator"
    assert args2.creator_action == "add"
    assert args2.name == "Nani Comedy"
    assert args2.id == "nani_comedy"

    # Script generate
    args3 = parser.parse_args(["generate", "nani_comedy", "--premise", "Nani hides the TV remote"])
    assert args3.subcommand == "generate"
    assert args3.creator_id == "nani_comedy"
    assert args3.premise == "Nani hides the TV remote"

    # History scripts
    args4 = parser.parse_args(["history", "scripts", "--creator", "nani_comedy"])
    assert args4.subcommand == "history"
    assert args4.history_action == "scripts"
    assert args4.creator == "nani_comedy"
