"""
app/extraction/gemini_extractor.py
One-time multimodal video analysis using Google GenAI SDK and Gemini 3.8 Flash.

Manages the ephemeral Gemini Files API lifecycle:
1. Upload local permanent video from storage.
2. Await remote processing state ACTIVE.
3. Execute schema-constrained multimodal extraction.
4. Delete remote Gemini file immediately.
5. Save result to the permanent archive and database.
"""

import time
from pathlib import Path
from typing import Optional
from google import genai
from google.genai import types
from app.core.config import console, settings
from app.core.database import get_db_session
from app.extraction.archive import archive_extraction
from app.extraction.normalizer import get_media_duration_ms, normalize_extraction
from app.models.extraction import VideoExtraction
from app.models.schema import Video, StyleReference
from app.storage.local import LocalStorageProvider

EXTRACTION_SYSTEM_PROMPT = """
You are an expert comedic screenwriter and media analyst.
Analyze the provided reference comedy video reel with extreme precision.

Follow these STRICT token-optimization and schema rules:
1. COMPACT SCHEMA: Use compact keys ('sp', 'sc', 's', 'e', 'loc', 'sit', 'x', 'cd', 'mech', 'esc', 'rev', 'punch', 'rhythm', 'pace', 'phys').
2. SPEAKER CODES: In 'sp', list each character with 'c' (code 'A', 'B'), 'n' (name), and 'desc' (traits). In turn arrays 'x', ALWAYS use the single-letter code ('A', 'B'). NEVER write full character names in 'x'.
3. ROMAN / ENGLISH SCRIPT ONLY: All dialogue in 'x' MUST be transcribed exclusively in the Roman/English alphabet (Latin characters), regardless of the spoken language (e.g. write "Lo ji garma garam coffee piyo.", NOT Devanagari "लो जी गरमा गरम कॉफ़ी पियो।"). Never output non-Latin or Indic Unicode scripts.
4. TURN FORMAT: Format each turn in 'x' as an array: [start_ms, end_ms, speaker_code, dialogue_roman, emotion?, action?]. Omit emotion or action if not meaningful.
5. CREATIVE DYNAMICS ('cd'): Capture the comedic engine ('mech' such as status-undercutting, escalation, reversal), setup, escalation beat ('esc'), reversal ('rev'), final punchline ('punch'), and physical comedy ('phys').
"""


class GeminiExtractor:
    """
    Executes one-time multimodal video extraction via Gemini 3.8 Flash.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        client: Optional[genai.Client] = None,
    ):
        self.model_name = model_name or settings.extraction_model
        if client:
            self.client = client
        else:
            resolved_key = api_key or settings.get_gemini_api_key()
            self.client = genai.Client(api_key=resolved_key)

        self.storage = LocalStorageProvider(settings.data_dir)

    def _resolve_video_path(self, video_id: str) -> Path:
        """Find the local filesystem path for a stored video."""
        with get_db_session() as session:
            video = session.query(Video).filter_by(video_id=video_id).first()
            if not video:
                raise ValueError(f"Video {video_id} not found in database.")

            # If URI is file://, resolve path
            if video.storage_uri.startswith("file://"):
                local_path = Path(video.storage_uri.replace("file://", "")).resolve()
                if local_path.is_file():
                    return local_path

            # Fallback to storage key
            style_ref = session.query(StyleReference).filter_by(video_id=video_id).first()
            style_id = style_ref.style_id if style_ref else "default_style"
            path = self.storage.get_local_path(f"videos/{style_id}/{video_id}.mp4")
            if path and path.is_file():
                return path

        raise FileNotFoundError(f"Local video file could not be resolved for video {video_id}")

    def extract(self, video_id: str, version: int = 1) -> VideoExtraction:
        """
        Perform one-time multimodal video extraction and save to permanent archive.

        Args:
            video_id: Video identifier in library.
            version: Extraction schema version number (default 1).

        Returns:
            Parsed VideoExtraction instance.
        """
        video_path = self._resolve_video_path(video_id)
        console.print(
            f"[bold cyan][GEMINI MULTIMODAL][/bold cyan] Analyzing video: "
            f"[yellow]{video_path.name}[/yellow] using model [magenta]{self.model_name}[/magenta]"
        )

        remote_file = None
        try:
            # 1. Ephemeral Upload to Gemini Files API
            console.print("[dim]Uploading video to temporary Gemini staging...[/dim]")
            remote_file = self.client.files.upload(file=str(video_path))
            console.print(f"[dim]Uploaded remote file ID: {remote_file.name}. Polling status...[/dim]")

            # 2. Wait until processed and ACTIVE
            while remote_file.state.name == "PROCESSING":
                time.sleep(2)
                remote_file = self.client.files.get(name=remote_file.name)

            if remote_file.state.name != "ACTIVE":
                raise RuntimeError(
                    f"Gemini remote file processing failed with state: {remote_file.state.name}"
                )

            console.print("[bold green][READY][/bold green] Video ready on Gemini. Generating structured extraction...")

            # 3. Schema-constrained Multimodal Generation
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[remote_file, EXTRACTION_SYSTEM_PROMPT],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=VideoExtraction,
                    temperature=0.2,
                ),
            )

            # 4. Parse response into Pydantic model
            if not response.text:
                raise RuntimeError("Empty response received from Gemini extraction model.")

            extraction = VideoExtraction.model_validate_json(response.text)
            extraction.v = version

            # 5. Defensive Timing Normalization
            media_dur_ms = get_media_duration_ms(video_path)
            if media_dur_ms:
                with get_db_session() as session:
                    db_video = session.query(Video).filter_by(video_id=video_id).first()
                    if db_video and not db_video.duration_ms:
                        db_video.duration_ms = media_dur_ms

            extraction = normalize_extraction(extraction, max_duration_ms=media_dur_ms)

            console.print(
                f"[bold green][EXTRACTION SUCCEEDED][/bold green] Extracted {len(extraction.sc)} scenes, "
                f"{len(extraction.sp)} speakers, and {len(extraction.cd.mech)} comedy mechanisms."
            )

            # 6. Archive normalized extraction permanently
            archive_extraction(video_id=video_id, extraction=extraction, version=version)
            return extraction

        finally:
            # 6. Strict cleanup: Delete remote Gemini file immediately
            if remote_file:
                try:
                    console.print(f"[dim]Cleaning up ephemeral Gemini file: {remote_file.name}...[/dim]")
                    self.client.files.delete(name=remote_file.name)
                    console.print("[dim]Ephemeral file deleted from Gemini Files API.[/dim]")
                except Exception as cleanup_err:
                    console.print(f"[yellow]Warning: Failed to delete remote Gemini file: {cleanup_err}[/yellow]")

