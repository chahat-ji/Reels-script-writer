"""
app/ingestion/downloader.py
Instagram Reel and web video downloader using yt-dlp.

Downloads video files from Instagram URLs into a local staging directory
prior to SHA-256 deduplication and permanent storage placement.
"""

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import yt_dlp
from app.core.config import console
from app.ingestion.url_parser import canonicalize_url


@dataclass
class DownloadedVideo:
    """Metadata container for a downloaded video asset."""
    video_path: Path
    title: Optional[str]
    duration_seconds: Optional[float]
    source_url: str


def download_video(url: str, output_dir: Optional[Path] = None) -> DownloadedVideo:
    """
    Download a video from an Instagram URL (or any yt-dlp supported URL).

    Args:
        url: The Instagram Reel or video URL to download.
        output_dir: Optional staging directory. Defaults to a temporary directory.

    Returns:
        DownloadedVideo object containing path to the downloaded MP4 and metadata.

    Raises:
        RuntimeError: If download fails or output file cannot be located.
    """
    clean_url = canonicalize_url(url)
    staging_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp(prefix="reel_download_"))
    staging_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold cyan][DOWNLOADING][/bold cyan] Fetching video from: [underline]{clean_url}[/underline]")

    # Template for yt-dlp output file
    output_template = str(staging_dir / "%(id)s.%(ext)s")

    ydl_opts = {
        "outtmpl": output_template,
        "format": "mp4/bestvideo+bestaudio/best",
        # Avoid merging errors on macOS by ensuring mp4 container
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract video info and download
            info_dict = ydl.extract_info(clean_url, download=True)
            if not info_dict:
                raise RuntimeError(f"Unable to extract video information from {clean_url}")

            video_id = info_dict.get("id", "downloaded_video")
            title = info_dict.get("title")
            duration = info_dict.get("duration")

            # Resolve the downloaded file path
            candidate_files = list(staging_dir.glob(f"{video_id}.*"))
            if not candidate_files:
                # Fallback to any media file in staging_dir
                candidate_files = [f for f in staging_dir.iterdir() if f.is_file() and not f.name.startswith(".")]

            if not candidate_files:
                raise RuntimeError(f"Downloaded video file not found in {staging_dir}")

            downloaded_file = candidate_files[0]
            console.print(
                f"[bold green][DOWNLOADED][/bold green] Successfully saved to staging: "
                f"[yellow]{downloaded_file.name}[/yellow] "
                f"({downloaded_file.stat().st_size / (1024 * 1024):.2f} MB)"
            )

            return DownloadedVideo(
                video_path=downloaded_file,
                title=title,
                duration_seconds=float(duration) if duration else None,
                source_url=clean_url,
            )

    except Exception as exc:
        console.print(f"[bold red][DOWNLOAD ERROR][/bold red] Failed to download video: {exc}")
        raise RuntimeError(f"Download failed for {clean_url}: {exc}") from exc

