"""
app/ingestion/service.py
Unified Ingestion Service coordinating downloading, audio extraction,
SHA-256 deduplication, durable storage, and SQLite database registration.
"""

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union
from app.core.config import console, settings
from app.core.database import get_db_session
from app.ingestion.audio_extractor import extract_audio
from app.ingestion.downloader import download_video
from app.ingestion.url_parser import (
    canonicalize_url,
    clean_input_string,
    is_instagram_url,
    parse_instagram_shortcode,
)
from app.models.schema import Style, StyleReference, Video
from app.storage.base import ObjectStorage
from app.storage.local import LocalStorageProvider


@dataclass
class IngestionResult:
    """Outcome report for an ingested video asset."""
    video_id: str
    sha256: str
    storage_uri: str
    audio_uri: Optional[str]
    duration_ms: Optional[int]
    is_duplicate: bool
    status: str
    message: str


def compute_sha256(file_path: Path) -> str:
    """
    Compute the SHA-256 checksum of a file in 64KB streaming blocks.
    Used for instant duplicate detection before permanent ingestion.
    """
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            sha.update(chunk)
    return sha.hexdigest()


class IngestionService:
    """
    Coordinates one-time video intake.
    
    Adheres strictly to the architectural invariant:
    UPLOAD ONCE -> UNDERSTAND ONCE -> STORE UNDERSTANDING -> GENERATE INDEFINITELY.
    """

    def __init__(self, storage: Optional[ObjectStorage] = None):
        # Default to local disk object storage provider
        self.storage: ObjectStorage = storage or LocalStorageProvider(settings.data_dir)

    def ingest(
        self,
        source: Union[str, Path],
        style_id: str = "default_style",
        language: str = "hi",
    ) -> IngestionResult:
        """
        Ingest a video into permanent storage and register in SQLite database.

        Args:
            source: An Instagram Reel URL (http://...) or local video file path.
            style_id: Creative style identifier (defaults to 'default_style').
            language: Dialogue language code (defaults to 'hi' for Hindi).

        Returns:
            IngestionResult detailing the storage URIs and duplicate status.
        """
        clean_source = clean_input_string(str(source))
        canonical_source = canonicalize_url(clean_source)
        is_web = canonical_source.startswith("http://") or canonical_source.startswith("https://")
        temp_cleanup_paths = []

        # 1. Pre-Download Idempotency Check for Web URLs
        if is_web:
            with get_db_session() as session:
                existing_video = session.query(Video).filter(
                    (Video.source_url == canonical_source) | (Video.source_url == clean_source)
                ).first()

                # Fallback Instagram shortcode match
                if not existing_video and is_instagram_url(clean_source):
                    shortcode = parse_instagram_shortcode(clean_source)
                    if shortcode:
                        existing_video = session.query(Video).filter(
                            Video.source_url.like(f"%/{shortcode}/%")
                        ).first()

                if existing_video:
                    # Verify physical video file exists in storage
                    storage_file = None
                    if existing_video.storage_uri.startswith("file://"):
                        candidate = Path(existing_video.storage_uri.replace("file://", "")).resolve()
                        if candidate.is_file():
                            storage_file = candidate
                    if not storage_file:
                        fallback = settings.videos_dir / style_id / f"{existing_video.video_id}.mp4"
                        if fallback.is_file():
                            storage_file = fallback

                    if storage_file:
                        console.print(
                            f"[bold yellow][PRE-DOWNLOAD IDEMPOTENT][/bold yellow] Video already downloaded and stored as "
                            f"[bold green]{existing_video.video_id}[/bold green] (source: [underline]{canonical_source}[/underline]). "
                            f"Skipping yt-dlp download entirely."
                        )

                        existing_ref = (
                            session.query(StyleReference)
                            .filter_by(style_id=style_id, video_id=existing_video.video_id)
                            .first()
                        )
                        if not existing_ref:
                            existing_style = session.query(Style).filter_by(style_id=style_id).first()
                            if not existing_style:
                                session.add(Style(style_id=style_id, version=1))
                            session.add(StyleReference(style_id=style_id, video_id=existing_video.video_id, relevance=1.0))
                            session.commit()

                        return IngestionResult(
                            video_id=existing_video.video_id,
                            sha256=existing_video.sha256,
                            storage_uri=existing_video.storage_uri,
                            audio_uri=existing_video.audio_uri,
                            duration_ms=existing_video.duration_ms,
                            is_duplicate=True,
                            status=existing_video.status,
                            message=f"Pre-download check: Video already exists for {canonical_source}. Skipped yt-dlp download.",
                        )

            # Not found in pre-download check: Proceed to download
            console.print(f"[bold cyan][PIPELINE][/bold cyan] Ingesting web video: [underline]{canonical_source}[/underline]")
            download_meta = download_video(canonical_source)
            raw_video_path = download_meta.video_path
            duration_ms = int(download_meta.duration_seconds * 1000) if download_meta.duration_seconds else None
            temp_cleanup_paths.append(raw_video_path)
            temp_cleanup_paths.append(raw_video_path.parent)  # temporary folder
            source_url_to_save = canonical_source
        else:
            # Local file path
            raw_video_path = Path(clean_source).resolve()
            if not raw_video_path.is_file():
                raise FileNotFoundError(f"Local video file not found: {raw_video_path}")
            console.print(f"[bold cyan][PIPELINE][/bold cyan] Ingesting local video: [yellow]{raw_video_path.name}[/yellow]")
            duration_ms = None
            source_url_to_save = None

        # 2. Compute SHA-256 checksum
        console.print("[dim]Computing SHA-256 fingerprint for duplicate detection...[/dim]")
        video_hash = compute_sha256(raw_video_path)
        console.print(f"[dim]Fingerprint: {video_hash[:16]}...[/dim]")

        # 3. Post-Download SHA-256 Check in database
        with get_db_session() as session:
            existing_video = session.query(Video).filter_by(sha256=video_hash).first()
            if existing_video:
                console.print(
                    f"[bold yellow][DUPLICATE DETECTED][/bold yellow] Video already exists in library as "
                    f"[bold green]{existing_video.video_id}[/bold green]. Skipping re-processing."
                )

                # Backfill source_url if it was missing
                if source_url_to_save and not existing_video.source_url:
                    existing_video.source_url = source_url_to_save
                    session.commit()

                # Ensure StyleReference exists for this style as well
                existing_ref = (
                    session.query(StyleReference)
                    .filter_by(style_id=style_id, video_id=existing_video.video_id)
                    .first()
                )
                if not existing_ref:
                    existing_style = session.query(Style).filter_by(style_id=style_id).first()
                    if not existing_style:
                        session.add(Style(style_id=style_id, version=1))
                    session.add(StyleReference(style_id=style_id, video_id=existing_video.video_id, relevance=1.0))
                    session.commit()

                # Clean up temporary downloads
                for p in temp_cleanup_paths:
                    if p.is_dir():
                        shutil.rmtree(p, ignore_errors=True)
                    elif p.is_file():
                        p.unlink(missing_ok=True)

                return IngestionResult(
                    video_id=existing_video.video_id,
                    sha256=existing_video.sha256,
                    storage_uri=existing_video.storage_uri,
                    audio_uri=existing_video.audio_uri,
                    duration_ms=existing_video.duration_ms,
                    is_duplicate=True,
                    status=existing_video.status,
                    message="Duplicate video detected via SHA-256. Existing record preserved.",
                )

        # 4. Extract audio track from video
        temp_audio_path = extract_audio(raw_video_path)
        temp_cleanup_paths.append(temp_audio_path)

        # 5. Place in permanent object storage
        video_id = f"v_{video_hash[:10]}"
        video_storage_key = f"videos/{style_id}/{video_id}.mp4"
        audio_storage_key = f"audio/{style_id}/{video_id}.m4a"

        console.print(f"[dim]Storing permanently at key: {video_storage_key}[/dim]")
        video_uri = self.storage.put(raw_video_path, video_storage_key)
        audio_uri = self.storage.put(temp_audio_path, audio_storage_key)

        # 6. Record entity in SQLite
        with get_db_session() as session:
            # Ensure Style record exists
            target_style = session.query(Style).filter_by(style_id=style_id).first()
            if not target_style:
                target_style = Style(style_id=style_id, version=1)
                session.add(target_style)

            # Insert Video with canonical source_url
            new_video = Video(
                video_id=video_id,
                sha256=video_hash,
                source_url=source_url_to_save,
                storage_uri=video_uri,
                audio_uri=audio_uri,
                duration_ms=duration_ms,
                language=language,
                status="stored",
            )
            session.add(new_video)

            # Insert StyleReference
            ref = StyleReference(style_id=style_id, video_id=video_id, relevance=1.0)
            session.add(ref)
            session.commit()

        # 7. Clean up staging files
        for p in temp_cleanup_paths:
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.is_file():
                p.unlink(missing_ok=True)

        console.print(
            f"[bold green][INGESTION COMPLETE][/bold green] Ingested "
            f"[bold cyan]{video_id}[/bold cyan] permanently into style [magenta]{style_id}[/magenta]."
        )

        return IngestionResult(
            video_id=video_id,
            sha256=video_hash,
            storage_uri=video_uri,
            audio_uri=audio_uri,
            duration_ms=duration_ms,
            is_duplicate=False,
            status="stored",
            message="New video successfully stored and indexed.",
        )

