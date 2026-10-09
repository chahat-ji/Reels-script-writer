"""
app/ingestion package
Provides video download, audio extraction, deduplication, and ingestion coordination.
"""

from app.ingestion.audio_extractor import extract_audio
from app.ingestion.downloader import download_video
from app.ingestion.queue import BatchResult, IngestionQueue
from app.ingestion.service import IngestionResult, IngestionService, compute_sha256
from app.ingestion.url_parser import canonicalize_url, is_instagram_url, parse_instagram_shortcode

__all__ = [
    "download_video",
    "extract_audio",
    "compute_sha256",
    "IngestionService",
    "IngestionResult",
    "IngestionQueue",
    "BatchResult",
    "canonicalize_url",
    "is_instagram_url",
    "parse_instagram_shortcode",
]

