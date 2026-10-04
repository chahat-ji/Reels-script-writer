"""
app/ingestion/instagram.py
Download Instagram reels and extract metadata using yt-dlp.
"""

import json
import re
from pathlib import Path
from typing import Dict, Any, Tuple
from rich.console import Console
import yt_dlp

console = Console()


def extract_reel_id(url: str) -> str:
    """Extract the shortcode/reel ID from an Instagram URL."""
    pattern = r"(?:reels?|p)/([A-Za-z0-9_-]+)"
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    # Fallback to sanitized URL string
    return re.sub(r"[^a-zA-Z0-9_-]", "_", url.split("?")[0].strip("/"))[-15:]


def download_instagram_reel(url: str, output_root: str = "data/reels") -> Tuple[str, Path, Dict[str, Any]]:
    """
    Downloads an Instagram reel to data/reels/{reel_id}/video.mp4
    and writes metadata to data/reels/{reel_id}/metadata.json.
    
    Returns:
        (reel_id, video_path, metadata)
    """
    reel_id = extract_reel_id(url)
    reel_dir = Path(output_root) / reel_id
    reel_dir.mkdir(parents=True, exist_ok=True)

    video_path = reel_dir / "video.mp4"
    metadata_path = reel_dir / "metadata.json"

    # Skip download if video already exists
    if video_path.exists() and metadata_path.exists():
        console.print(f"[bold cyan][CACHE HIT][/bold cyan] Reel [green]{reel_id}[/green] already downloaded.")
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        return reel_id, video_path, metadata

    console.print(f"[bold green][DOWNLOADING][/bold green] Fetching reel from [cyan]{url}[/cyan]...")

    ydl_opts = {
        "outtmpl": str(video_path),
        "format": "mp4/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "overwrites": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        metadata = {
            "id": reel_id,
            "title": info.get("title"),
            "description": info.get("description"),
            "duration": info.get("duration"),
            "uploader": info.get("uploader"),
            "uploader_id": info.get("uploader_id"),
            "url": url,
        }

    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    console.print(f"[bold blue][SAVED][/bold blue] Video saved to [green]{video_path}[/green]")
    return reel_id, video_path, metadata
