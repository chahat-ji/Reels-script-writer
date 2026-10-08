"""
app/storage/local.py
Local filesystem implementation of ObjectStorage.

Stores durable media assets under a configurable root directory (e.g. data/),
with path-traversal security protection and automatic directory management.
"""

import shutil
from pathlib import Path
from typing import Optional, Union

from app.storage.base import ObjectStorage


class LocalStorageProvider(ObjectStorage):
    """
    Durable object storage provider backed by the local filesystem.
    
    Organizes assets under self.root_dir (e.g. data/):
    - data/videos/{style_id}/{video_id}.mp4
    - data/audio/{style_id}/{video_id}.m4a
    """

    def __init__(self, root_dir: Union[str, Path] = "data"):
        self.root_dir = Path(root_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_key(self, key: str) -> Path:
        """
        Safely resolve a storage key into an absolute local Path.
        Guards against directory traversal attacks (e.g. '../../etc/passwd').
        """
        # Strip leading slashes to prevent absolute path escapes
        cleaned_key = key.lstrip("/\\")
        target_path = (self.root_dir / cleaned_key).resolve()

        # Security check: target must be inside root_dir
        if not str(target_path).startswith(str(self.root_dir)):
            raise ValueError(f"Security error: key '{key}' attempts to traverse outside storage root.")

        return target_path

    def put(self, source_path: Union[str, Path], key: str) -> str:
        """
        Store a source file under the specified storage key.
        Creates parent directories if necessary and copies the file.
        """
        source = Path(source_path).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"Source file does not exist: {source}")

        target = self._resolve_key(key)
        target.parent.mkdir(parents=True, exist_ok=True)

        # Only copy if source and target are distinct paths
        if source != target:
            shutil.copy2(source, target)

        return self.get_uri(key)

    def get(self, key: str, destination_path: Union[str, Path]) -> Path:
        """
        Retrieve a file from storage and copy it to destination_path.
        """
        target = self._resolve_key(key)
        if not target.is_file():
            raise FileNotFoundError(f"Storage object does not exist at key: {key}")

        destination = Path(destination_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)

        if target != destination:
            shutil.copy2(target, destination)

        return destination

    def exists(self, key: str) -> bool:
        """
        Check if a file exists at the given key.
        """
        try:
            target = self._resolve_key(key)
            return target.is_file()
        except ValueError:
            return False

    def get_uri(self, key: str) -> str:
        """
        Return the canonical file:// URI for the storage key.
        """
        target = self._resolve_key(key)
        return f"file://{target}"

    def delete(self, key: str) -> bool:
        """
        Delete the file at the given key if it exists.
        """
        target = self._resolve_key(key)
        if target.is_file():
            target.unlink()
            return True
        return False

    def get_local_path(self, key: str) -> Optional[Path]:
        """
        Return the local Path for the key if the file exists on disk.
        """
        target = self._resolve_key(key)
        return target if target.is_file() else None

