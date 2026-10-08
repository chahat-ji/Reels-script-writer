"""
tests/test_storage.py
Unit tests verifying LocalStorageProvider operations, file durability, and security checks.
"""

import pytest
from pathlib import Path
from app.storage.local import LocalStorageProvider


@pytest.fixture
def storage(tmp_path):
    """Provides a LocalStorageProvider instance rooted in a temporary directory."""
    return LocalStorageProvider(root_dir=tmp_path / "data_storage")


@pytest.fixture
def sample_file(tmp_path):
    """Creates a temporary sample text/media file."""
    src = tmp_path / "sample_video.mp4"
    src.write_bytes(b"dummy binary video content 1234567890")
    return src


def test_storage_put_and_exists(storage, sample_file):
    """Verify storing a file and checking its existence."""
    key = "videos/style_01/v001.mp4"
    assert not storage.exists(key)

    uri = storage.put(sample_file, key)
    assert uri.startswith("file://")
    assert "videos/style_01/v001.mp4" in uri
    assert storage.exists(key)


def test_storage_get(storage, sample_file, tmp_path):
    """Verify retrieving a stored file to a destination path."""
    key = "audio/style_01/v001.m4a"
    storage.put(sample_file, key)

    dest = tmp_path / "downloaded_audio.m4a"
    result = storage.get(key, dest)

    assert result.is_file()
    assert result.read_bytes() == sample_file.read_bytes()


def test_storage_delete(storage, sample_file):
    """Verify deleting a stored file."""
    key = "videos/style_01/v_to_delete.mp4"
    storage.put(sample_file, key)
    assert storage.exists(key)

    deleted = storage.delete(key)
    assert deleted is True
    assert not storage.exists(key)

    # Subsequent delete should return False gracefully
    assert storage.delete(key) is False


def test_storage_get_local_path(storage, sample_file):
    """Verify local filesystem path resolution."""
    key = "videos/style_01/v002.mp4"
    storage.put(sample_file, key)

    local_path = storage.get_local_path(key)
    assert local_path is not None
    assert local_path.is_file()
    assert local_path.name == "v002.mp4"


def test_path_traversal_protection(storage, sample_file, tmp_path):
    """Verify that path traversal attempts are blocked."""
    malicious_key = "../../outside_system_file.txt"

    with pytest.raises(ValueError, match="traverse outside storage root"):
        storage.put(sample_file, malicious_key)

    with pytest.raises(ValueError, match="traverse outside storage root"):
        dest = tmp_path / "target.txt"
        storage.get(malicious_key, dest)

