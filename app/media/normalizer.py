"""
app/media/normalizer.py
Audio normalization and technical container inspection using ffmpeg/ffprobe.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from rich.console import Console
from app.models.media import AudioSpecs, VideoSpecs

console = Console()


def probe_media(file_path: Path) -> dict:
    """Run ffprobe to get container streams and format metadata."""
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(file_path),
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {file_path}: {res.stderr}")
    return json.loads(res.stdout)


def extract_media_specs(probe_data: dict) -> Tuple[Optional[VideoSpecs], AudioSpecs]:
    """Parse ffprobe JSON output into typed AudioSpecs and VideoSpecs."""
    video_specs = None
    audio_specs = None

    for stream in probe_data.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video" and video_specs is None:
            fps_str = stream.get("r_frame_rate", "30/1")
            if "/" in fps_str:
                num, den = map(float, fps_str.split("/"))
                fps = round(num / den, 2) if den != 0 else 30.0
            else:
                fps = float(fps_str)

            video_specs = VideoSpecs(
                width=int(stream.get("width", 0)),
                height=int(stream.get("height", 0)),
                fps=fps,
                duration_seconds=float(stream.get("duration", probe_data.get("format", {}).get("duration", 0.0))),
                codec=stream.get("codec_name", "unknown"),
            )
        elif codec_type == "audio" and audio_specs is None:
            audio_specs = AudioSpecs(
                sample_rate=int(stream.get("sample_rate", 16000)),
                channels=int(stream.get("channels", 1)),
                codec=stream.get("codec_name", "unknown"),
                duration_seconds=float(stream.get("duration", probe_data.get("format", {}).get("duration", 0.0))),
            )

    if not audio_specs:
        duration = float(probe_data.get("format", {}).get("duration", 0.0))
        audio_specs = AudioSpecs(duration_seconds=duration)

    return video_specs, audio_specs


def normalize_audio(video_path: Path, output_audio_path: Path) -> AudioSpecs:
    """
    Converts audio track to standardized 16-bit, 16 kHz mono PCM WAV.
    """
    if output_audio_path.exists():
        console.print(f"[bold cyan][CACHE HIT][/bold cyan] Normalized audio present: [green]{output_audio_path.name}[/green]")
    else:
        console.print(f"[bold yellow][NORMALIZING][/bold yellow] Extracting 16kHz mono WAV for [green]{video_path.name}[/green]...")
        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(output_audio_path),
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg conversion failed: {res.stderr}")
        console.print(f"[bold blue][SAVED][/bold blue] Standardized audio saved: [green]{output_audio_path.name}[/green]")

    probe_data = probe_media(output_audio_path)
    _, audio_specs = extract_media_specs(probe_data)
    return audio_specs