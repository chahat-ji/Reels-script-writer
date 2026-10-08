"""
app/extraction/archive.py
Archival storage and retrieval for compact structured extraction JSON.

Preserves the complete, lossless multimodal extraction as a permanent backup
layer as mandated by Section 8 of description.txt:
"video -> detailed extraction -> archive"
Enables full recovery, reprocessing, and rebuilding of Video Memories
and Style Bibles without re-uploading original video assets.
"""

import json
from pathlib import Path
from typing import Optional
from app.core.config import console, settings
from app.core.database import get_db_session
from app.models.extraction import VideoExtraction
from app.models.schema import Video, VideoMemory, StyleReference


def get_archive_path(video_id: str, version: int = 1) -> Path:
    """Generate canonical filesystem path for archived extraction JSON."""
    return settings.extractions_dir / f"{video_id}_v{version}.json"


def archive_extraction(video_id: str, extraction: VideoExtraction, version: int = 1) -> Path:
    """
    Persist structured extraction to both the archive filesystem and SQLite database.

    Args:
        video_id: Unique video identifier.
        extraction: Parsed VideoExtraction Pydantic instance.
        version: Extraction schema/prompt version number (default 1).

    Returns:
        Path to the saved JSON archive file.
    """
    archive_file = get_archive_path(video_id, version)
    archive_file.parent.mkdir(parents=True, exist_ok=True)

    compact_data = extraction.to_compact_dict()

    # 1. Write to filesystem archive (ensure_ascii=False preserves native Hindi/Devanagari)
    with open(archive_file, "w", encoding="utf-8") as f:
        json.dump(compact_data, f, indent=2, ensure_ascii=False)

    try:
        display_path = archive_file.relative_to(settings.base_dir)
    except ValueError:
        display_path = archive_file

    console.print(
        f"[bold green][ARCHIVED][/bold green] Permanent extraction saved to: "
        f"[cyan]{display_path}[/cyan]"
    )

    # 2. Update SQLite database record
    with get_db_session() as session:
        # Update video status to 'extracted'
        video = session.query(Video).filter_by(video_id=video_id).first()
        if video:
            video.status = "extracted"

        # Find or create VideoMemory record
        memory = session.query(VideoMemory).filter_by(video_id=video_id).first()
        if not memory:
            # Look up associated style
            style_ref = session.query(StyleReference).filter_by(video_id=video_id).first()
            style_id = style_ref.style_id if style_ref else "default_style"

            memory = VideoMemory(
                video_id=video_id,
                style_id=style_id,
                structured_extraction=compact_data,
                extraction_version=version,
            )
            session.add(memory)
        else:
            memory.structured_extraction = compact_data
            memory.extraction_version = version

        session.commit()

    return archive_file


def load_archived_extraction(video_id: str, version: int = 1) -> Optional[VideoExtraction]:
    """
    Retrieve archived extraction JSON from disk or SQLite fallback.

    Args:
        video_id: Unique video identifier.
        version: Extraction schema version.

    Returns:
        VideoExtraction instance or None if not found.
    """
    archive_file = get_archive_path(video_id, version)

    # Try filesystem archive first
    if archive_file.is_file():
        with open(archive_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return VideoExtraction.from_compact_dict(data)

    # Fallback to database
    with get_db_session() as session:
        memory = session.query(VideoMemory).filter_by(video_id=video_id).first()
        if memory and memory.structured_extraction:
            return VideoExtraction.from_compact_dict(memory.structured_extraction)

    return None
