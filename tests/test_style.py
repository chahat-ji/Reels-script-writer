"""
tests/test_style.py
Unit tests for Phase 4 Style Synthesis & Style Bible generation.

Strictly offline: all Gemini API calls and storage environments are mocked.
Never calls real external APIs.
"""

from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.schema import Base, Style, StyleReference, Video, VideoMemory
from app.style.aggregator import CorpusStats, StyleAggregator, StyleCorpus
from app.style.service import StyleService
from app.style.synthesizer import StyleSynthesizer
from app.style.versioning import StyleVersioning
import app.core.database


SAMPLE_BIBLE_MARKDOWN = """STYLE BIBLE v1
STYLE ID: test_comedy

LANGUAGE
Colloquial Hindi and Hinglish slang.

REGISTER
Casual, domestic, playful sibling and familial banter.

DIALOGUE
Short snappy turns.
High dialogue density with rapid interruptions.
Minimal narrative exposition.

CHARACTER DYNAMIC
One character makes greedy or confident claims.
The other character challenges and turns the tables.

COMEDY ENGINE
Normal domestic situation
→ confident claim
→ suspicion
→ objection
→ escalation
→ reversal/punchline.

COMMON COMEDIC DEVICES
- Status reversal
- Moral hypocrisy
- Underhanded teamwork
- Teasing

PACING
Fast and bouncy with rapid exchanges every 2-4 seconds.

PHYSICAL COMEDY
Subtle glances, sneaky winks, counting money, abruptly turning away.

ENDINGS
A sudden undercut reversal where the con-artist gets exposed.
"""


@pytest.fixture
def mock_db_session(tmp_path, monkeypatch):
    """Provide an isolated SQLite database session for style testing."""
    db_file = tmp_path / "test_style.db"
    test_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(test_engine)
    TestingSession = sessionmaker(bind=test_engine)

    monkeypatch.setattr(app.core.database, "engine", test_engine)
    monkeypatch.setattr(app.core.database, "SessionLocal", TestingSession)

    return TestingSession


def test_style_aggregator_success(mock_db_session):
    """Verify StyleAggregator aggregates multiple video memories and calculates corpus metrics."""
    with mock_db_session() as session:
        # Create test style and videos
        style = Style(style_id="test_comedy", version=1)
        v1 = Video(video_id="v_001", sha256="hash1", storage_uri="/v1.mp4", status="indexed")
        v2 = Video(video_id="v_002", sha256="hash2", storage_uri="/v2.mp4", status="indexed")
        session.add_all([style, v1, v2])

        mem1 = VideoMemory(
            video_id="v_001",
            style_id="test_comedy",
            memory_text="VIDEO v_001\nCHARACTERS: Nani, Granddaughter\nSITUATION: Scamming change.",
            metadata_json={
                "characters": ["Nani", "Granddaughter"],
                "comedy_mechanisms": ["status-reversal", "con-escalation"],
                "settings": ["Living room"],
                "pacing": "Fast",
                "language": "hi",
            },
        )
        mem2 = VideoMemory(
            video_id="v_002",
            style_id="test_comedy",
            memory_text="VIDEO v_002\nCHARACTERS: Nani, Son\nSITUATION: Tea preparation.",
            metadata_json={
                "characters": ["Nani", "Son"],
                "comedy_mechanisms": ["status-reversal", "teasing"],
                "settings": ["Kitchen"],
                "pacing": "Fast",
                "language": "hi",
            },
        )
        session.add_all([mem1, mem2])
        session.commit()

    aggregator = StyleAggregator()
    corpus = aggregator.aggregate_style_corpus("test_comedy")

    assert corpus.style_id == "test_comedy"
    assert corpus.stats.total_memories == 2
    assert "v_001" in corpus.stats.video_ids
    assert "v_002" in corpus.stats.video_ids
    # Nani appeared twice, should be the top character
    assert corpus.stats.unique_characters[0] == "Nani"
    # status-reversal appeared in both memories
    assert "status-reversal" in corpus.stats.common_mechanisms
    assert "--- REFERENCE VIDEO MEMORY 1/2: v_001 ---" in corpus.formatted_prompt_corpus
    assert "--- REFERENCE VIDEO MEMORY 2/2: v_002 ---" in corpus.formatted_prompt_corpus


def test_style_aggregator_empty_raises(mock_db_session):
    """Verify ValueError is raised when querying a style with zero memories."""
    aggregator = StyleAggregator()
    with pytest.raises(ValueError, match="No VideoMemory records found"):
        aggregator.aggregate_style_corpus("nonexistent_style")


def test_style_synthesizer_with_mock_client():
    """Verify StyleSynthesizer correctly cleans and validates synthesized Style Bible markdown."""
    mock_genai_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = f"```markdown\n{SAMPLE_BIBLE_MARKDOWN}\n```"
    mock_genai_client.models.generate_content.return_value = mock_response

    synthesizer = StyleSynthesizer(
        api_key="mock_key",
        model_name="gemini-3.8-flash",
        client=mock_genai_client,
    )

    corpus = StyleCorpus(
        style_id="test_comedy",
        memories=[{"video_id": "v_001", "memory_text": "Sample text", "metadata": {}}],
        stats=CorpusStats(
            total_memories=1,
            video_ids=["v_001"],
            unique_characters=["Nani"],
            common_mechanisms=["status-reversal"],
            dominant_language="hi",
        ),
        formatted_prompt_corpus="VIDEO MEMORY v_001",
    )

    result_md = synthesizer.synthesize_bible(corpus, target_version=1)

    assert mock_genai_client.models.generate_content.called
    assert result_md.startswith("STYLE BIBLE v1")
    assert "STYLE ID: test_comedy" in result_md
    assert "LANGUAGE" in result_md
    assert "REGISTER" in result_md
    assert "DIALOGUE" in result_md
    assert "CHARACTER DYNAMIC" in result_md
    assert "COMEDY ENGINE" in result_md
    assert "COMMON COMEDIC DEVICES" in result_md
    assert "PACING" in result_md
    assert "PHYSICAL COMEDY" in result_md
    assert "ENDINGS" in result_md
    assert not result_md.startswith("```")


def test_style_versioning_and_file_persistence(mock_db_session, tmp_path):
    """Verify version bumping (v1 -> v2) and disk file persistence."""
    versioning = StyleVersioning(styles_dir=tmp_path)

    # Insert parent Video records for foreign key integrity
    with mock_db_session() as session:
        v1 = Video(video_id="v_001", sha256="h1", storage_uri="/v1.mp4", status="indexed")
        v2 = Video(video_id="v_002", sha256="h2", storage_uri="/v2.mp4", status="indexed")
        v3 = Video(video_id="v_003", sha256="h3", storage_uri="/v3.mp4", status="indexed")
        session.add_all([v1, v2, v3])
        session.commit()

    # Initially version should be 1
    v1_target = versioning.determine_target_version("desi_style")
    assert v1_target == 1

    # Persist v1
    style_v1 = versioning.persist_style_bible(
        style_id="desi_style",
        version=1,
        bible_text=SAMPLE_BIBLE_MARKDOWN,
        video_ids=["v_001", "v_002"],
    )
    assert style_v1.version == 1

    # Verify disk files
    v1_file = tmp_path / "desi_style_v1.md"
    latest_file = tmp_path / "desi_style_latest.md"
    assert v1_file.is_file()
    assert latest_file.is_file()
    assert "STYLE BIBLE v1" in v1_file.read_text(encoding="utf-8")

    # Verify StyleReference rows in DB
    with mock_db_session() as session:
        refs = session.query(StyleReference).filter_by(style_id="desi_style").all()
        assert len(refs) == 2
        ref_ids = {r.video_id for r in refs}
        assert ref_ids == {"v_001", "v_002"}

    # Bumping version for newly added reference videos
    v2_target = versioning.determine_target_version("desi_style")
    assert v2_target == 2

    bible_v2_text = SAMPLE_BIBLE_MARKDOWN.replace("v1", "v2")
    style_v2 = versioning.persist_style_bible(
        style_id="desi_style",
        version=2,
        bible_text=bible_v2_text,
        video_ids=["v_001", "v_002", "v_003"],
    )
    assert style_v2.version == 2

    # Verify v1 still exists and v2 is created
    assert v1_file.is_file()
    v2_file = tmp_path / "desi_style_v2.md"
    assert v2_file.is_file()
    assert "STYLE BIBLE v2" in v2_file.read_text(encoding="utf-8")
    assert "STYLE BIBLE v2" in latest_file.read_text(encoding="utf-8")


def test_style_service_complete_flow(mock_db_session, tmp_path):
    """Verify StyleService end-to-end orchestration with mocked Gemini client."""
    with mock_db_session() as session:
        st = Style(style_id="sketch_style", version=1)
        v = Video(video_id="v_100", sha256="hash100", storage_uri="/v100.mp4", status="indexed")
        session.add_all([st, v])
        session.commit()

        mem = VideoMemory(
            video_id="v_100",
            style_id="sketch_style",
            memory_text="VIDEO v_100\nCHARACTERS: A, B\nSITUATION: Sketch comedic escalation.",
            metadata_json={"characters": ["A", "B"], "comedy_mechanisms": ["teasing"]},
        )
        session.add(mem)
        session.commit()

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = SAMPLE_BIBLE_MARKDOWN.replace("test_comedy", "sketch_style")
    mock_client.models.generate_content.return_value = mock_resp

    synthesizer = StyleSynthesizer(client=mock_client)
    versioning = StyleVersioning(styles_dir=tmp_path)
    service = StyleService(
        synthesizer=synthesizer,
        versioning=versioning,
    )

    created_style = service.synthesize_style(style_id="sketch_style")

    assert created_style.style_id == "sketch_style"
    assert created_style.version == 1
    assert "STYLE BIBLE v1" in created_style.bible_text

    # Retrieve through service
    fetched_style = service.get_style("sketch_style")
    assert fetched_style is not None
    assert fetched_style.version == 1
