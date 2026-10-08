"""
app/extraction/reprocessor.py
Batch and single-video reprocessing subsystem.

Implements Section 23 of description.txt:
When extraction prompt or schema evolves (v1 -> v2), videos are re-extracted
directly from permanent object storage without requiring user re-uploads.
"""

from typing import List, Optional
from app.core.config import console
from app.core.database import get_db_session
from app.extraction.gemini_extractor import GeminiExtractor
from app.models.extraction import VideoExtraction
from app.models.schema import Video, StyleReference


def reprocess_video(video_id: str, new_version: int = 2) -> VideoExtraction:
    """
    Re-extract a stored video using the latest extraction version.

    Args:
        video_id: Target video identifier.
        new_version: Incremented extraction version number.

    Returns:
        Updated VideoExtraction instance.
    """
    console.print(
        f"[bold cyan][REPROCESSING][/bold cyan] Re-extracting video "
        f"[yellow]{video_id}[/yellow] to version [green]v{new_version}[/green]..."
    )
    extractor = GeminiExtractor()
    return extractor.extract(video_id=video_id, version=new_version)


def reprocess_all(
    style_id: Optional[str] = None,
    new_version: int = 2,
) -> List[VideoExtraction]:
    """
    Batch re-extract all videos in a style or library.

    Args:
        style_id: Optional style filter. If None, processes all library videos.
        new_version: Target extraction version.

    Returns:
        List of newly extracted VideoExtraction objects.
    """
    extractor = GeminiExtractor()
    results = []

    with get_db_session() as session:
        query = session.query(Video)
        if style_id:
            query = query.join(StyleReference).filter(StyleReference.style_id == style_id)
        videos = query.all()

        console.print(
            f"[bold cyan][BATCH REPROCESS][/bold cyan] Found {len(videos)} videos "
            f"to reprocess to v{new_version}."
        )

        for idx, video in enumerate(videos, 1):
            console.print(f"\n[magenta]Reprocessing ({idx}/{len(videos)}):[/magenta] {video.video_id}")
            try:
                ext = extractor.extract(video_id=video.video_id, version=new_version)
                results.append(ext)
            except Exception as exc:
                console.print(f"[bold red]Failed to reprocess {video.video_id}: {exc}[/bold red]")

    return results

