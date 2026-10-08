"""
app/ingestion/audio_extractor.py
Audio extraction utility using ffmpeg.

Extracts a clean speech-optimized audio track (.m4a AAC) from the ingested MP4 video,
enabling fast audio playback, inspection, or audio-driven downstream processing.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional
from app.core.config import console


def find_ffmpeg_binary() -> str:
    """
    Locate the ffmpeg binary on the host system.
    Prefers /opt/homebrew/bin/ffmpeg on macOS Apple Silicon, falling back to system PATH.
    """
    homebrew_ffmpeg = Path("/opt/homebrew/bin/ffmpeg")
    if homebrew_ffmpeg.is_file():
        return str(homebrew_ffmpeg)

    path_ffmpeg = shutil.which("ffmpeg")
    if path_ffmpeg:
        return path_ffmpeg

    raise FileNotFoundError("ffmpeg binary was not found. Please install ffmpeg or ensure it is in PATH.")


def extract_audio(
    video_path: Path,
    output_path: Optional[Path] = None,
    audio_format: str = "m4a",
) -> Path:
    """
    Extract a high-quality speech audio stream from a video file using ffmpeg.

    Args:
        video_path: Path to the input video file.
        output_path: Optional explicit output destination. Defaults to input path with .m4a.
        audio_format: Target audio container/format (default 'm4a').

    Returns:
        Path to the extracted audio file.

    Raises:
        FileNotFoundError: If input video or ffmpeg binary is not found.
        RuntimeError: If ffmpeg fails during extraction.
    """
    video = Path(video_path).resolve()
    if not video.is_file():
        raise FileNotFoundError(f"Input video does not exist: {video}")

    ffmpeg_bin = find_ffmpeg_binary()

    if output_path:
        target_audio = Path(output_path).resolve()
    else:
        target_audio = video.with_suffix(f".{audio_format}")

    target_audio.parent.mkdir(parents=True, exist_ok=True)

    console.print(
        f"[bold cyan][EXTRACTING AUDIO][/bold cyan] Extracting audio stream from: "
        f"[yellow]{video.name}[/yellow]"
    )

    # ffmpeg command:
    # -y: overwrite output
    # -i: input file
    # -vn: disable video recording (audio only)
    # -acodec aac: use standard AAC encoder
    # -b:a 128k: 128 kbps bitrate (optimal for speech clarity & small footprint)
    # -ar 44100: 44.1 kHz sampling rate
    cmd = [
        ffmpeg_bin,
        "-y",
        "-i", str(video),
        "-vn",
        "-acodec", "aac",
        "-b:a", "128k",
        "-ar", "44100",
        str(target_audio),
    ]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        if result.returncode != 0:
            console.print(f"[bold red][FFMPEG ERROR][/bold red] {result.stderr}")
            raise RuntimeError(f"ffmpeg audio extraction failed: {result.stderr}")

        console.print(
            f"[bold green][AUDIO EXTRACTED][/bold green] Audio track ready: "
            f"[yellow]{target_audio.name}[/yellow] "
            f"({target_audio.stat().st_size / (1024 * 1024):.2f} MB)"
        )
        return target_audio

    except Exception as exc:
        console.print(f"[bold red][EXTRACTION FAILED][/bold red] {exc}")
        raise RuntimeError(f"Audio extraction failed for {video}: {exc}") from exc

