"""
tools/dashboard/service.py
Data service layer for the human verification dashboard.

Fetches video records from SQLite and pairs them with their archived
multimodal extraction JSON files from data/extractions/.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.database import get_db_session
from app.extraction.normalizer import get_media_duration_ms, normalize_extraction
from app.models.schema import Video, VideoMemory, StyleReference


def get_all_videos() -> List[Dict[str, Any]]:
    """
    Retrieve all ingested videos from SQLite and check if an extraction exists.
    Returns a sorted list of video summaries for the UI dropdown.
    """
    items = []
    with get_db_session() as session:
        videos = session.query(Video).order_by(Video.created_at.desc()).all()
        for v in videos:
            archive_file = settings.extractions_dir / f"{v.video_id}_v1.json"
            has_extraction = archive_file.is_file() or (v.status == "extracted")

            items.append({
                "video_id": v.video_id,
                "sha256": v.sha256[:10],
                "status": v.status,
                "has_extraction": has_extraction,
                "has_audio": bool(v.audio_uri),
                "created_at": v.created_at.strftime("%Y-%m-%d %H:%M") if v.created_at else "N/A",
            })
    return items


def get_video_payload(video_id: str) -> Optional[Dict[str, Any]]:
    """
    Compile complete verification payload for a specific video:
    - Metadata from SQLite
    - Extracted JSON (scenes, speakers, turns, comedic dynamics)
    - Local video streaming path
    """
    with get_db_session() as session:
        video = session.query(Video).filter_by(video_id=video_id).first()
        if not video:
            return None

        style_ref = session.query(StyleReference).filter_by(video_id=video_id).first()
        style_id = style_ref.style_id if style_ref else "default_style"

        # Resolve local video path
        video_path = None
        if video.storage_uri.startswith("file://"):
            candidate = Path(video.storage_uri.replace("file://", "")).resolve()
            if candidate.is_file():
                video_path = str(candidate)

        if not video_path:
            candidate = settings.videos_dir / style_id / f"{video_id}.mp4"
            if candidate.is_file():
                video_path = str(candidate)

        # Load extraction JSON from archive file or database
        extraction_data = None
        archive_file = settings.extractions_dir / f"{video_id}_v1.json"
        if archive_file.is_file():
            try:
                extraction_data = json.loads(archive_file.read_text(encoding="utf-8"))
            except Exception:
                pass

        if not extraction_data:
            memory = session.query(VideoMemory).filter_by(video_id=video_id).first()
            if memory and memory.structured_extraction:
                extraction_data = memory.structured_extraction

        # Defensively normalize extraction timestamps for smooth UI playback
        if extraction_data:
            video_dur_ms = video.duration_ms
            if not video_dur_ms and video_path:
                video_dur_ms = get_media_duration_ms(video_path)
            extraction_data = normalize_extraction(extraction_data, max_duration_ms=video_dur_ms)

        return {
            "video_id": video.video_id,
            "style_id": style_id,
            "sha256": video.sha256,
            "status": video.status,
            "language": video.language,
            "has_video_file": bool(video_path),
            "extraction": extraction_data,
        }

