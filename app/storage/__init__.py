"""
app/storage package
Provides durable object storage abstractions and local filesystem implementations.
"""

from app.storage.base import ObjectStorage
from app.storage.local import LocalStorageProvider

__all__ = ["ObjectStorage", "LocalStorageProvider"]

