"""
app/api/admin.py
Admin Studio REST endpoints for platform administrators and creative evaluators.
Provides multimodal extraction debugging, human review sliders, Style Bible synthesis,
video streaming, and benchmarking metrics. Guarded strictly by require_admin.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_admin
from app.api.schemas import (
    BenchmarkMetricsResponse,
    ScriptDetailResponse,
    ScriptReviewRequest,
    ScriptSummaryResponse,
    StyleSummaryResponse,
    VideoSummaryResponse,
)
from app.core.config import settings
from app.extraction.normalizer import get_media_duration_ms, normalize_extraction
from app.generation.parser import calculate_screenplay_metrics, parse_screenplay_elements
from app.models.schema import Script, Style, StyleReference, User, Video, VideoMemory
from app.style.service import StyleService

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Studio"], dependencies=[Depends(require_admin)])


@router.get("/videos", response_model=List[VideoSummaryResponse])
def admin_list_videos(db: Session = Depends(get_db)):
    """
    List all ingested videos with extraction and audio status.
    """
    videos = db.query(Video).order_by(Video.created_at.desc()).all()
    results = []
    for v in videos:
        archive_file = settings.extractions_dir / f"{v.video_id}_v1.json"
        has_extraction = archive_file.is_file() or (v.status == "extracted")
        results.append(
            VideoSummaryResponse(
                video_id=v.video_id,
                sha256=v.sha256[:10],
                status=v.status,
                has_extraction=has_extraction,
                has_audio=bool(v.audio_uri),
                created_at=v.created_at.strftime("%Y-%m-%d %H:%M") if v.created_at else "N/A",
            )
        )
    return results


@router.get("/videos/{video_id}")
def admin_get_video_payload(video_id: str, db: Session = Depends(get_db)):
    """
    Return comprehensive verification payload including raw Gemini extraction JSON.
    """
    video = db.query(Video).filter_by(video_id=video_id).first()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    style_ref = db.query(StyleReference).filter_by(video_id=video_id).first()
    style_id = style_ref.style_id if style_ref else "default_style"

    # Resolve video file path
    video_path = None
    if video.storage_uri.startswith("file://"):
        candidate = Path(video.storage_uri.replace("file://", "")).resolve()
        if candidate.is_file():
            video_path = str(candidate)

    if not video_path:
        candidate = settings.videos_dir / style_id / f"{video_id}.mp4"
        if candidate.is_file():
            video_path = str(candidate)

    # Load extraction JSON
    extraction_data = None
    archive_file = settings.extractions_dir / f"{video_id}_v1.json"
    if archive_file.is_file():
        try:
            extraction_data = json.loads(archive_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    if not extraction_data:
        memory = db.query(VideoMemory).filter_by(video_id=video_id).first()
        if memory and memory.structured_extraction:
            extraction_data = memory.structured_extraction

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
        "stream_url": f"/api/v1/admin/stream/{video.video_id}",
        "extraction": extraction_data,
    }


@router.get("/stream/{video_id}")
def admin_stream_video(video_id: str, db: Session = Depends(get_db)):
    """
    Stream video MP4 with native HTTP 206 Partial Content range support.
    """
    video = db.query(Video).filter_by(video_id=video_id).first()
    if not video:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")

    style_ref = db.query(StyleReference).filter_by(video_id=video_id).first()
    style_id = style_ref.style_id if style_ref else "default_style"
    video_file = settings.videos_dir / style_id / f"{video_id}.mp4"

    if not video_file.is_file():
        candidates = list(settings.videos_dir.glob(f"*/{video_id}.mp4"))
        if candidates:
            video_file = candidates[0]
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file not found on disk")

    return FileResponse(path=video_file, media_type="video/mp4")


@router.get("/scripts", response_model=List[ScriptSummaryResponse])
def admin_list_all_scripts(
    style_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    List all scripts across all users with rating and evaluation metadata.
    """
    query = db.query(Script)
    if style_id:
        query = query.filter_by(style_id=style_id)
    scripts = query.order_by(Script.created_at.desc()).all()

    summaries = []
    for s in scripts:
        metrics = calculate_screenplay_metrics(s.script_text or "")
        summaries.append(
            ScriptSummaryResponse(
                script_id=s.script_id,
                creator_id=s.style_id,
                user_id=s.user_id,
                premise=s.premise,
                status=s.status or "draft",
                rating=s.rating,
                word_count=metrics["word_count"],
                est_duration_sec=metrics["est_duration_sec"],
                created_at=s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "N/A",
            )
        )
    return summaries


@router.post("/scripts/{script_id}/review")
def admin_update_script_review(
    script_id: str,
    review: ScriptReviewRequest,
    db: Session = Depends(get_db),
):
    """
    Save human evaluation rating (1-5 stars), approval status, and review critique.
    """
    script = db.query(Script).filter_by(script_id=script_id).first()
    if not script:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")

    valid_statuses = {"draft", "approved", "needs_revision", "rejected"}
    script.status = review.status.lower() if review.status.lower() in valid_statuses else "draft"
    if review.rating is not None:
        script.rating = max(1, min(5, int(review.rating)))
    if review.review_notes is not None:
        script.review_notes = review.review_notes.strip()

    db.commit()
    return {
        "script_id": script.script_id,
        "status": script.status,
        "rating": script.rating,
        "review_notes": script.review_notes,
    }


@router.get("/styles", response_model=List[StyleSummaryResponse])
def admin_list_styles(db: Session = Depends(get_db)):
    """
    List all Creator styles, active Style Bible versions, and reference counts.
    """
    styles = db.query(Style).all()
    results = []
    for s in styles:
        ref_count = db.query(StyleReference).filter_by(style_id=s.style_id).count()
        results.append(
            StyleSummaryResponse(
                style_id=s.style_id,
                name=s.name,
                version=s.version,
                has_bible=bool(s.bible_text),
                reference_video_count=ref_count,
            )
        )
    return results


@router.post("/styles/synthesize")
def admin_synthesize_style(
    style_id: str = "default_style",
):
    """
    Trigger synthesis of canonical Master Style Bible for a target creator style.
    """
    service = StyleService()
    try:
        style = service.synthesize_style(style_id=style_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    return {
        "style_id": style.style_id,
        "version": style.version,
        "message": f"Successfully synthesized Style Bible v{style.version}",
        "bible_length_chars": len(style.bible_text or ""),
    }


@router.get("/benchmarks", response_model=BenchmarkMetricsResponse)
def admin_get_benchmarks(db: Session = Depends(get_db)):
    """
    Calculate platform benchmarking metrics across library extractions and screenplay evaluations.
    """
    total_videos = db.query(Video).count()
    extracted_videos = db.query(Video).filter(Video.status.in_(["extracted", "indexed"])).count()
    total_scripts = db.query(Script).count()
    total_creators = db.query(Style).count()

    reviewed = db.query(Script).filter(Script.rating.isnot(None)).all()
    avg_rating = (sum(r.rating for r in reviewed) / len(reviewed)) if reviewed else None
    health_pct = (extracted_videos / total_videos * 100.0) if total_videos > 0 else 100.0

    return BenchmarkMetricsResponse(
        total_videos=total_videos,
        total_scripts=total_scripts,
        total_creators=total_creators,
        reviewed_scripts_count=len(reviewed),
        average_rating=round(avg_rating, 2) if avg_rating else None,
        extraction_health_percentage=round(health_pct, 1),
    )

