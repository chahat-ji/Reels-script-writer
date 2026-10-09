"""
tools/dashboard/service.py
Data service layer for the human verification dashboard.

Fetches video records from SQLite and pairs them with their archived
multimodal extraction JSON files from data/extractions/.
"""

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.core.database import get_db_session
from app.extraction.normalizer import get_media_duration_ms, normalize_extraction
from app.models.schema import Video, VideoMemory, StyleReference, Style, Script


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


def parse_screenplay_elements(script_text: str) -> List[Dict[str, str]]:
    """
    Parse screenplay text into typed elements for syntax-highlighted teleprompter rendering.
    Types: slugline, character, parenthetical, dialogue, action, button, meta
    """
    elements = []
    lines = script_text.splitlines()
    prev_was_character = False
    prev_was_parenthetical = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            prev_was_character = False
            prev_was_parenthetical = False
            elements.append({"type": "blank", "text": ""})
            continue

        # Meta comment
        if line.startswith("#"):
            elements.append({"type": "meta", "text": line})
            prev_was_character = False
            prev_was_parenthetical = False
            continue

        # Slugline
        clean_upper = re.sub(r"^\*+|\*+$", "", line).strip().upper()
        if clean_upper.startswith("INT.") or clean_upper.startswith("EXT."):
            elements.append({"type": "slugline", "text": line})
            prev_was_character = False
            prev_was_parenthetical = False
            continue

        # Button / Transition
        if clean_upper in ("BLACKOUT.", "BLACKOUT", "FADE OUT.", "FADE OUT", "CUT TO BLACK.", "THE END."):
            elements.append({"type": "button", "text": line})
            prev_was_character = False
            prev_was_parenthetical = False
            continue

        # Parenthetical
        if line.startswith("(") and line.endswith(")"):
            elements.append({"type": "parenthetical", "text": line})
            prev_was_character = False
            prev_was_parenthetical = True
            continue

        # Character cue (Short, mostly uppercase or uppercase name before parenthetical)
        upper_token = re.sub(r"\s*\([^)]*\)", "", line).strip()
        is_character = (
            len(upper_token) > 0
            and len(upper_token) <= 30
            and upper_token.isupper()
            and not upper_token.endswith((".", "!", "?"))
            and not upper_token.startswith(("INT", "EXT"))
        )

        if is_character:
            elements.append({"type": "character", "text": line})
            prev_was_character = True
            prev_was_parenthetical = False
            continue

        # Dialogue
        if prev_was_character or prev_was_parenthetical:
            elements.append({"type": "dialogue", "text": line})
            continue

        # Action line
        elements.append({"type": "action", "text": line})
        prev_was_character = False
        prev_was_parenthetical = False

    return elements


def get_all_scripts(style_id: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Retrieve all generated scripts from SQLite with word count and runtime metrics.
    """
    items = []
    with get_db_session() as session:
        query = session.query(Script)
        if style_id:
            query = query.filter_by(style_id=style_id)
        if user_id:
            query = query.filter_by(user_id=user_id)
        scripts = query.order_by(Script.created_at.desc()).all()

        for s in scripts:
            words = len(re.findall(r"\b\w+\b", s.script_text or ""))
            est_duration = max(15, round(words / 3.0))
            items.append({
                "script_id": s.script_id,
                "style_id": s.style_id,
                "user_id": s.user_id,
                "premise": s.premise,
                "status": s.status or "draft",
                "rating": s.rating,
                "word_count": words,
                "est_duration_sec": est_duration,
                "created_at": s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "N/A",
            })
    return items


def get_script_payload(script_id: str) -> Optional[Dict[str, Any]]:
    """
    Compile complete verification payload for a specific script:
    - Screenplay text and parsed teleprompter lines
    - Metrics (word count, duration)
    - Associated Master Style Bible text
    - Reference videos used by this creator
    """
    with get_db_session() as session:
        script = session.query(Script).filter_by(script_id=script_id).first()
        if not script:
            return None

        # Style info and Style Bible
        style = session.query(Style).filter_by(style_id=script.style_id).first()
        creator_name = style.name if (style and style.name) else script.style_id
        bible_text = style.bible_text if (style and style.bible_text) else ""

        # Fallback to disk if DB bible_text is empty
        if not bible_text:
            bible_file = settings.styles_dir / f"{script.style_id}_v1.md"
            if bible_file.is_file():
                bible_text = bible_file.read_text(encoding="utf-8")

        # Reference videos
        ref_records = session.query(StyleReference).filter_by(style_id=script.style_id).all()
        ref_videos = []
        for r in ref_records:
            v = session.query(Video).filter_by(video_id=r.video_id).first()
            if v:
                ref_videos.append({
                    "video_id": v.video_id,
                    "status": v.status,
                    "relevance": r.relevance,
                    "stream_url": f"/stream/{v.video_id}",
                })

        words = len(re.findall(r"\b\w+\b", script.script_text or ""))
        est_duration = max(15, round(words / 3.0))
        parsed = parse_screenplay_elements(script.script_text or "")

        return {
            "script_id": script.script_id,
            "style_id": script.style_id,
            "creator_name": creator_name,
            "user_id": script.user_id,
            "premise": script.premise,
            "script_text": script.script_text,
            "status": script.status or "draft",
            "rating": script.rating,
            "review_notes": script.review_notes or "",
            "word_count": words,
            "est_duration_sec": est_duration,
            "created_at": script.created_at.strftime("%Y-%m-%d %H:%M") if script.created_at else "N/A",
            "style_bible": bible_text,
            "reference_videos": ref_videos,
            "parsed_elements": parsed,
        }


def update_script_review(
    script_id: str,
    status: str,
    rating: Optional[int] = None,
    review_notes: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Save human evaluation status, 1-5 star rating, and review notes to SQLite.
    """
    valid_statuses = {"draft", "approved", "needs_revision", "rejected"}
    clean_status = status.lower() if status and status.lower() in valid_statuses else "draft"

    with get_db_session() as session:
        script = session.query(Script).filter_by(script_id=script_id).first()
        if not script:
            return None

        script.status = clean_status
        if rating is not None:
            script.rating = max(1, min(5, int(rating)))
        if review_notes is not None:
            script.review_notes = review_notes.strip()

        session.commit()
        return {
            "script_id": script.script_id,
            "status": script.status,
            "rating": script.rating,
            "review_notes": script.review_notes,
        }


