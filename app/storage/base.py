"""
app/storage/base.py
Abstract base class defining the contract for permanent object storage.

Decouples file persistence from underlying storage backends (Local Disk, S3, GCS),
ensuring video and audio assets are permanently preserved outside ephemeral LLM contexts.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Union


class ObjectStorage(ABC):
    """
    Abstract interface for durable object storage.
    
    Guarantees that raw media assets (videos and extracted audio)
    have a permanent source of truth as required by Section 3 of description.txt.
    """

    @abstractmethod
    def put(self, source_path: Union[str, Path], key: str) -> str:
        """
        Store a local file permanently at the given key.
        
        Args:
            source_path: Local filesystem path of the source file.
            key: Relative storage key (e.g. 'videos/style_001/v001.mp4').
            
        Returns:
            Canonical storage URI (e.g. 'file:///.../data/videos/style_001/v001.mp4').
        """
        pass

    @abstractmethod
    def get(self, key: str, destination_path: Union[str, Path]) -> Path:
        """
        Retrieve a file from storage and write it to destination_path.
        
        Args:
            key: Storage key to retrieve.
            destination_path: Local path where the file should be written.
            
        Returns:
            Resolved Path of the downloaded/copied file.
        """
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        Check whether an object exists at the specified storage key.
        
        Args:
            key: Storage key to check.
            
        Returns:
            True if the object exists, False otherwise.
        """
        pass

    @abstractmethod
    def get_uri(self, key: str) -> str:
        """
        Return the canonical storage URI for the given key.
        
        Args:
            key: Storage key.
            
        Returns:
            Canonical URI string (e.g. 'file:///...' or 's3://...').
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        Delete an object from permanent storage.
        
        Args:
            key: Storage key to delete.
            
        Returns:
            True if the file was found and deleted, False if not found.
        """
        pass

    @abstractmethod
    def get_local_path(self, key: str) -> Optional[Path]:
        """
        Provide direct local filesystem Path access if the backend is local.
        Returns None for remote-only backends that do not cache locally.
        
        Args:
            key: Storage key.
            
        Returns:
            Local Path if available, None otherwise.
        """
        pass

