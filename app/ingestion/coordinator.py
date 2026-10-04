"""
app/ingestion/coordinator.py
End-to-end ingestion handler: downloads, probes, and normalizes media.
"""

import json
import shutil
from pathlib import Path
from typing import Optional
from rich.console import Console

from app.ingestion.instagram import download_instagram_reel
from app.media.normalizer import probe_media, extract_media_specs, normalize_audio
from app.models.media import IngestedMedia

console = Console()


def ingest_media(source: str, data_root: str = "data") -> IngestedMedia:
    """
    Phase 1 Entry point:
    - Ingests URL (via yt-dlp) or local MP4.
    - Runs ffprobe container inspection.
    - Extracts 16 kHz mono WAV.
    - Writes metadata.json and returns typed IngestedMedia.
    """
    root_dir = Path(data_root) / "reels"

    # 1. Acquire video file & metadata
    if source.startswith("http://") or source.startswith("https://"):
        reel_id, video_path, metadata = download_instagram_reel(source, output_root=str(root_dir))
        source_url = source
    else:
        src_path = Path(source)
        if not src_path.exists():
            raise FileNotFoundError(f"Input file not found: {source}")
        reel_id = src_path.stem
        reel_dir = root_dir / reel_id
        reel_dir.mkdir(parents=True, exist_ok=True)
        video_path = reel_dir / f"video{src_path.suffix}"
        if not video_path.exists():
            shutil.copy(src_path, video_path)
        metadata = {"id": reel_id, "source": str(src_path)}
        source_url = None

    reel_dir = video_path.parent
    metadata_path = reel_dir / "metadata.json"
    if not metadata_path.exists():
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)

    # 2. Inspect original video specs with ffprobe
    raw_probe = probe_media(video_path)
    video_specs, _ = extract_media_specs(raw_probe)

    # 3. Normalize audio track to standard 16 kHz mono WAV
    audio_path = reel_dir / "audio.wav"
    audio_specs = normalize_audio(video_path, audio_path)

    # 4. Save container and specs report
    specs_manifest = reel_dir / "media_specs.json"
    with open(specs_manifest, "w", encoding="utf-8") as f:
        json.dump({
            "reel_id": reel_id,
            "video_specs": video_specs.model_dump() if video_specs else None,
            "audio_specs": audio_specs.model_dump(),
        }, f, indent=2)

    return IngestedMedia(
        reel_id=reel_id,
        source_url=source_url,
        video_path=video_path,
        audio_path=audio_path,
        metadata_path=metadata_path,
        audio_specs=audio_specs,
        video_specs=video_specs,
        raw_metadata=metadata,
    )