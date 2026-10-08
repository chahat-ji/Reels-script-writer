"""
app/ingestion package
Provides video download, audio extraction, deduplication, and ingestion coordination.
"""

from app.ingestion.audio_extractor import extract_audio
from app.ingestion.downloader import download_video
from app.ingestion.service import IngestionResult, IngestionService, compute_sha256

__all__ = [
    "download_video",
    "extract_audio",
    "compute_sha256",
    "IngestionService",
    "IngestionResult",
]

