"""
app/ingestion/coordinator.py
End-to-end ingestion handler: downloads, probes, and normalizes audio track.
"""

import json
import shutil
from pathlib import Path
from typing import Optional
from rich.console import Console

from app.ingestion.instagram import download_instagram_reel
from app.media.normalizer import probe_media, extract_media_specs, normalize_audio
from app.media.separator import isolate_vocals
from app.models.media import IngestedMedia

console = Console()


def ingest_media(source: str, data_root: str = "data", separate_stems: bool = False) -> IngestedMedia:
    """
    Ingests URL (via yt-dlp) or local MP4:
    - Runs ffprobe container inspection.
    - Extracts standardized 16 kHz mono WAV (audio.wav).
    - Preserves raw audio by default for speech transcription.
    - Writes metadata.json, media_specs.json, and returns typed IngestedMedia.
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

        if src_path.is_file() and src_path.parent.parent.name == "reels":
            reel_id = src_path.parent.name
            reel_dir = src_path.parent
            video_path = src_path if src_path.suffix.lower() in [".mp4", ".mov", ".mkv"] else (reel_dir / "video.mp4")
        elif src_path.is_dir() and src_path.parent.name == "reels":
            reel_id = src_path.name
            reel_dir = src_path
            video_path = reel_dir / "video.mp4"
        else:
            reel_id = src_path.stem
            reel_dir = root_dir / reel_id
            reel_dir.mkdir(parents=True, exist_ok=True)
            video_path = reel_dir / f"video{src_path.suffix}"
            if not video_path.exists() and src_path != video_path:
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

    # 3. Extract baseline 16 kHz mono audio mix
    raw_audio_path = reel_dir / "audio.wav"
    audio_specs = normalize_audio(video_path, raw_audio_path)

    # 4. Optional stem separation (disabled by default for speech transcription)
    if separate_stems:
        active_audio_path = isolate_vocals(raw_audio_path, output_dir=reel_dir)
    else:
        active_audio_path = raw_audio_path

    # 5. Save container and specs report
    specs_manifest = reel_dir / "media_specs.json"
    with open(specs_manifest, "w", encoding="utf-8") as f:
        json.dump({
            "reel_id": reel_id,
            "video_specs": video_specs.model_dump() if video_specs else None,
            "audio_specs": audio_specs.model_dump(),
            "speech_audio_file": active_audio_path.name,
            "stems_isolated": separate_stems and active_audio_path.name == "vocals.wav",
        }, f, indent=2)

    return IngestedMedia(
        reel_id=reel_id,
        source_url=source_url,
        video_path=video_path,
        audio_path=active_audio_path,
        metadata_path=metadata_path,
        audio_specs=audio_specs,
        video_specs=video_specs,
        raw_metadata=metadata,
    )