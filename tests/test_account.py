"""
tests/test_account.py
Unit tests for user account creation, creator profile management,
and upload & script history tracking.

Strictly offline: uses isolated SQLite test fixtures.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.account.service import AccountService, slugify
from app.models.schema import Base, Script, Style, StyleReference, User, Video, VideoMemory
import app.core.database


@pytest.fixture
def mock_db_session(tmp_path, monkeypatch):
    """Provide an isolated SQLite database session for account testing."""
    db_file = tmp_path / "test_account.db"
    test_engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(test_engine)
    TestingSession = sessionmaker(bind=test_engine)

    monkeypatch.setattr(app.core.database, "engine", test_engine)
    monkeypatch.setattr(app.core.database, "SessionLocal", TestingSession)

    return TestingSession


def test_slugify():
    """Verify slug generation for creator IDs and usernames."""
    assert slugify("Ashish Chanchlani") == "ashish_chanchlani"
    assert slugify("BB Ki Vines!") == "bb_ki_vines"
    assert slugify("   Clean--Name_Here   ") == "clean_name_here"


def test_create_or_get_user(mock_db_session):
    """Verify user registration and retrieval with future OAuth fields."""
    service = AccountService()

    # Create new user
    user = service.create_or_get_user(username="Rosh", email="rosh@example.com", auth_provider="local")
    assert user.username == "rosh"
    assert user.user_id == "usr_rosh"
    assert user.email == "rosh@example.com"
    assert user.auth_provider == "local"

    # Retrieve existing user
    same_user = service.create_or_get_user(username="ROSH")
    assert same_user.user_id == user.user_id


def test_create_and_list_creators(mock_db_session):
    """Verify creating creator profiles under a user and filtering by user_id."""
    service = AccountService()
    user = service.create_or_get_user(username="creator_admin")

    # Add creator 1
    c1 = service.create_creator(user_id=user.user_id, creator_name="Nani Comedy", description="Family sketch comedy")
    assert c1.name == "Nani Comedy"
    assert c1.user_id == user.user_id
    assert c1.style_id == "c_nani_comedy"

    # Add creator 2
    c2 = service.create_creator(user_id=user.user_id, creator_name="Desi Banter")
    assert c2.style_id == "c_desi_banter"

    # List creators
    creators = service.list_creators(user_id=user.user_id)
    assert len(creators) == 2
    names = {c.name for c in creators}
    assert names == {"Nani Comedy", "Desi Banter"}


def test_creator_upload_and_script_history(mock_db_session):
    """Verify querying upload history and generated script history."""
    service = AccountService()
    user = service.create_or_get_user(username="test_writer")
    creator = service.create_creator(user_id=user.user_id, creator_name="Viral Reelz", creator_id="c_viral")

    # Simulate ingested video and style reference
    with mock_db_session() as session:
        vid = Video(
            video_id="v_mock1",
            sha256="mock_sha123",
            source_url="https://instagram.com/reel/123",
            storage_uri="/data/videos/v_mock1.mp4",
            duration_ms=45000,
            status="indexed",
        )
        ref = StyleReference(style_id="c_viral", video_id="v_mock1", relevance=1.0)
        script = Script(
            script_id="scr_001",
            user_id=user.user_id,
            style_id="c_viral",
            premise="Trying to sneak out of home",
            script_text="SCENE 1: BEDROOM...",
        )
        session.add_all([vid, ref, script])
        session.commit()

    # Query upload history
    uploads = service.get_creator_upload_history("c_viral")
    assert len(uploads) == 1
    assert uploads[0]["video_id"] == "v_mock1"
    assert uploads[0]["status"] == "indexed"
    assert uploads[0]["duration_ms"] == 45000

    # Query script history
    scripts = service.get_user_script_history(user_id=user.user_id, style_id="c_viral")
    assert len(scripts) == 1
    assert scripts[0].script_id == "scr_001"
    assert "SCENE 1" in scripts[0].script_text


def test_authentication_enforcement_and_session_lifecycle(mock_db_session, tmp_path):
    """Verify that mandatory authentication blocks backdoor entry and sessions lifecycle properly."""
    from app.account.service import (
        clear_current_session,
        get_authenticated_user,
        get_current_user_id,
        set_current_user_id,
    )

    session_file = tmp_path / ".current_user"

    # 1. No session file -> PermissionError
    with pytest.raises(PermissionError) as exc_info:
        get_authenticated_user(session_file=session_file)
    assert "Access Denied: No user is currently logged in" in str(exc_info.value)

    # 2. Session file with non-existent user -> PermissionError
    set_current_user_id("usr_non_existent", session_file=session_file)
    with pytest.raises(PermissionError) as exc_info:
        get_authenticated_user(session_file=session_file)
    assert "was not found in the database" in str(exc_info.value)

    # 3. Valid user -> successfully authenticated
    service = AccountService()
    user = service.create_or_get_user(username="real_user", email="real@example.com")
    set_current_user_id(user.user_id, session_file=session_file)

    auth_user = get_authenticated_user(session_file=session_file)
    assert auth_user.user_id == user.user_id
    assert auth_user.username == "real_user"

    # 4. Clear session -> PermissionError restored
    clear_current_session(session_file=session_file)
    assert get_current_user_id(session_file=session_file) is None
    with pytest.raises(PermissionError):
        get_authenticated_user(session_file=session_file)


def test_cross_creator_superpower_deduplication(mock_db_session):
    """Verify cross-creator deduplication: Video memory created for Creator A is instantly shared with Creator B."""
    import numpy as np
    from unittest.mock import MagicMock
    from app.generation.context import ContextBuilder
    from app.memory.index import VectorRetriever
    from app.memory.service import MemoryService

    with mock_db_session() as session:
        # Create 2 creators
        c_a = Style(style_id="c_creator_a", name="Creator A", version=1, bible_text="Style A Bible")
        c_b = Style(style_id="c_creator_b", name="Creator B", version=1, bible_text="Style B Bible")

        # Create a video originally belonging to Creator A
        vid = Video(
            video_id="v_shared100",
            sha256="hash_shared100",
            storage_uri="/storage/v_shared100.mp4",
            status="indexed",
        )
        ref_a = StyleReference(style_id="c_creator_a", video_id="v_shared100", relevance=1.0)
        session.add_all([c_a, c_b, vid, ref_a])
        session.commit()

        # Add pre-computed VideoMemory with embedding
        fake_emb = np.ones(768, dtype=np.float32)
        mem = VideoMemory(
            video_id="v_shared100",
            style_id="c_creator_a",
            memory_text="CREATIVE MEMORY: Shared hilarious prank sketch",
            metadata_json={"characters": ["Pappu", "Chhotu"], "comedy_mechanisms": ["Status Reversal"]},
        )
        mem.set_embedding(fake_emb)
        session.add(mem)
        session.commit()

    # Verify superpower reuse in MemoryService
    mock_embed_client = MagicMock()
    memory_service = MemoryService(embed_client=mock_embed_client)

    # Distill and index for Creator B
    reused_mem = memory_service.distill_and_index_video(video_id="v_shared100", style_id="c_creator_b")

    # Embed client must NOT be called (0 tokens spent!)
    assert not mock_embed_client.embed_text.called
    assert reused_mem.video_id == "v_shared100"

    # Verify StyleReference exists for Creator B
    with mock_db_session() as session:
        ref_b = session.query(StyleReference).filter_by(style_id="c_creator_b", video_id="v_shared100").first()
        assert ref_b is not None

    # Verify ContextBuilder picks up this shared memory for Creator B
    builder = ContextBuilder()
    context_b = builder.build_context(style_id="c_creator_b", premise="New prank idea")
    assert context_b.memory_count == 1
    assert "v_shared100" in context_b.user_prompt
    assert "Shared hilarious prank sketch" in context_b.user_prompt

    # Verify VectorRetriever finds this shared memory for Creator B
    mock_embed_client.embed_text.return_value = np.ones(768, dtype=np.float32)
    retriever = VectorRetriever(embed_client=mock_embed_client)
    matches_b = retriever.search_memories(query="Prank idea", style_id="c_creator_b", top_k=5)
    assert len(matches_b) == 1
    assert matches_b[0].video_id == "v_shared100"
