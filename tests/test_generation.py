"""
tests/test_generation.py
Unit tests for Phase 5 Script Generation and adaptive 10-memory context retrieval.

Strictly offline: all LLM calls and storage operations are mocked.
"""

from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.generation.context import ContextBuilder, GenerationContext
from app.generation.generator import ScreenplayGenerator
from app.generation.service import ScriptService
from app.memory.index import MemoryMatch
from app.models.schema import Base, Script, Style, User, Video, VideoMemory
import app.core.database

MOCK_STYLE_BIBLE = """STYLE BIBLE v1
LANGUAGE: Colloquial Hindi.
REGISTER: Casual domestic banter.
DIALOGUE: Short turns, high density.
CHARACTER DYNAMIC: One boasts, one undercuts.
COMEDY ENGINE: Normal -> Assertion -> Escalation -> Reversal.
COMMON COMEDIC DEVICES: Status reversal, teasing.
PACING: Fast.
PHYSICAL COMEDY: Sneaky glances.
ENDINGS: Sudden punchline undercut.
"""

SAMPLE_SCREENPLAY_OUTPUT = """
SCENE 1: INT. LIVING ROOM - MORNING
Raju (20s) tiptoes into the room holding a crumpled report card.

RAJU
(whispering)
Agar mummy ne dekh liya toh antim sanskar tay hai.

Nani pops up from behind the sofa like a ninja.

NANI
Kiska antim sanskar? Tera ya tere marksheet ka?

RAJU
(startled)
Nani! Aap yahan kya kar rahi ho?

NANI
Tera future dekh rahi hoon... jo bilkul andhera hai.
"""


@pytest.fixture
def mock_db_session(tmp_path, monkeypatch):
    """Provide an isolated SQLite database session for generation testing."""
    db_file = tmp_path / "test_generation.db"
    test_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(test_engine)
    TestingSession = sessionmaker(bind=test_engine)

    monkeypatch.setattr(app.core.database, "engine", test_engine)
    monkeypatch.setattr(app.core.database, "SessionLocal", TestingSession)

    return TestingSession


def test_context_builder_direct_mode_under_10_videos(mock_db_session):
    """Verify that creators with <= 10 videos use direct all-in-context (0 embedding calls)."""
    with mock_db_session() as session:
        style = Style(style_id="c_desi", name="Desi Comedy", version=1, bible_text=MOCK_STYLE_BIBLE)
        session.add(style)

        # Create 3 video memories
        for i in range(1, 4):
            v = Video(video_id=f"v_00{i}", sha256=f"hash_{i}", storage_uri=f"/v{i}.mp4", status="indexed")
            mem = VideoMemory(
                video_id=f"v_00{i}",
                style_id="c_desi",
                memory_text=f"VIDEO v_00{i}\nCHARACTERS: A, B\nSITUATION: Joke {i}",
            )
            session.add_all([v, mem])
        session.commit()

    mock_retriever = MagicMock()
    builder = ContextBuilder(retriever=mock_retriever)

    context = builder.build_context(style_id="c_desi", premise="Boy hides report card from mom")

    # Assert that direct mode was selected and vector search was NOT called
    assert context.retrieval_mode == "direct_all"
    assert context.memory_count == 3
    assert not mock_retriever.search_memories.called
    assert "STYLE BIBLE" in context.user_prompt
    assert "Boy hides report card from mom" in context.user_prompt
    assert "--- REFERENCE MEMORY 1/3: v_001 ---" in context.user_prompt


def test_context_builder_dynamic_mode_over_10_videos(mock_db_session):
    """Verify that creators with > 10 videos trigger dynamic Top-10 vector retrieval."""
    with mock_db_session() as session:
        style = Style(style_id="c_large", name="Big Channel", version=1, bible_text=MOCK_STYLE_BIBLE)
        session.add(style)

        # Create 12 video memories
        for i in range(1, 13):
            vid_id = f"v_{i:03d}"
            v = Video(video_id=vid_id, sha256=f"hash_{i}", storage_uri=f"/{vid_id}.mp4", status="indexed")
            mem = VideoMemory(
                video_id=vid_id,
                style_id="c_large",
                memory_text=f"VIDEO {vid_id}\nSITUATION: Scenario {i}",
            )
            session.add_all([v, mem])
        session.commit()

    # Mock the vector retriever to return 10 ranked matches
    mock_retriever = MagicMock()
    mock_retriever.search_memories.return_value = [
        MemoryMatch(
            video_id=f"v_{i:03d}",
            style_id="c_large",
            score=0.95 - (i * 0.02),
            memory_text=f"VIDEO v_{i:03d}\nSITUATION: Relevant joke {i}",
            metadata={},
        )
        for i in range(1, 11)
    ]

    builder = ContextBuilder(retriever=mock_retriever)
    context = builder.build_context(style_id="c_large", premise="Cheating in exams")

    assert context.retrieval_mode == "dynamic_vector_top10"
    assert context.memory_count == 10
    # Vector search must have been called with top_k=10
    mock_retriever.search_memories.assert_called_once_with(
        style_id="c_large", query="Cheating in exams", top_k=10
    )


def test_screenplay_generator_with_mock_client():
    """Verify ScreenplayGenerator produces sanitized screenplay output."""
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = f"```text\n{SAMPLE_SCREENPLAY_OUTPUT}\n```"
    mock_client.models.generate_content.return_value = mock_response

    generator = ScreenplayGenerator(client=mock_client)

    dummy_context = GenerationContext(
        style_id="c_desi",
        premise="Test Premise",
        retrieval_mode="direct_all",
        memory_count=2,
        system_instruction="System prompt",
        user_prompt="User prompt",
    )

    script = generator.generate_screenplay(dummy_context)

    assert mock_client.models.generate_content.called
    assert not script.startswith("```")
    assert "SCENE 1: INT. LIVING ROOM" in script
    assert "Kiska antim sanskar?" in script


def test_script_service_end_to_end(mock_db_session, tmp_path):
    """Verify complete ScriptService generation, SQLite persistence, and file writing."""
    with mock_db_session() as session:
        user = User(user_id="usr_rosh", username="rosh")
        style = Style(style_id="c_test", name="Test Style", version=1, bible_text=MOCK_STYLE_BIBLE)
        v = Video(video_id="v_01", sha256="h01", storage_uri="/v01.mp4", status="indexed")
        mem = VideoMemory(video_id="v_01", style_id="c_test", memory_text="Sample joke")
        session.add_all([user, style, v, mem])
        session.commit()

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_SCREENPLAY_OUTPUT
    mock_client.models.generate_content.return_value = mock_resp

    generator = ScreenplayGenerator(client=mock_client)
    service = ScriptService(
        generator=generator,
        scripts_dir=tmp_path,
    )

    script_record = service.generate_script(
        style_id="c_test",
        premise="Hiding report card",
        user_id="usr_rosh",
    )

    assert script_record.script_id.startswith("scr_")
    assert script_record.user_id == "usr_rosh"
    assert script_record.style_id == "c_test"
    assert "Kiska antim sanskar?" in script_record.script_text

    # Verify file saved on disk
    saved_file = tmp_path / f"{script_record.script_id}.txt"
    assert saved_file.is_file()
    assert "Hiding report card" in saved_file.read_text(encoding="utf-8")

    # Verify retrieval via service
    retrieved = service.get_script(script_record.script_id)
    assert retrieved is not None
    assert retrieved.script_id == script_record.script_id
