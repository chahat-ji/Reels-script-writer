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
