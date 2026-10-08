"""
tools/dashboard/server.py
Lightweight aiohttp web server for the human verification dashboard.

Provides:
- Video streaming with HTTP Range (206) support for smooth seeking
- REST APIs for video catalog and JSON extraction payloads
- Static asset serving for HTML, CSS, and JS frontend
"""

import sys
from pathlib import Path
from aiohttp import web
from rich.panel import Panel

# Ensure workspace root is on sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.core.config import console, settings
from tools.dashboard.service import get_all_videos, get_video_payload

STATIC_DIR = Path(__file__).resolve().parent / "static"


async def handle_index(request: web.Request) -> web.FileResponse:
    """Serve the single-page application index.html."""
    return web.FileResponse(STATIC_DIR / "index.html")


async def handle_list_videos(request: web.Request) -> web.Response:
    """REST API: Return list of all ingested videos in the catalog."""
    videos = get_all_videos()
    return web.json_response(videos)


async def handle_get_video(request: web.Request) -> web.Response:
    """REST API: Return complete extraction data and metadata for video_id."""
    video_id = request.match_info["video_id"]
    payload = get_video_payload(video_id)
    if not payload:
        return web.json_response({"error": "Video not found"}, status=404)
    return web.json_response(payload)


async def handle_stream_video(request: web.Request) -> web.StreamResponse:
    """
    Stream video MP4 file with native HTTP 206 Partial Content range support.
    Enables smooth instant scrubbing and seeking in HTML5 video player.
    """
    video_id = request.match_info["video_id"]
    payload = get_video_payload(video_id)
    if not payload:
        raise web.HTTPNotFound(text="Video not found")

    style_id = payload.get("style_id", "default_style")
    video_file = settings.videos_dir / style_id / f"{video_id}.mp4"

    if not video_file.is_file():
        # Search all style subdirectories as fallback
        candidates = list(settings.videos_dir.glob(f"*/{video_id}.mp4"))
        if candidates:
            video_file = candidates[0]
        else:
            raise web.HTTPNotFound(text="Video file not found on disk")

    return web.FileResponse(video_file)


def create_app() -> web.Application:
    """Build and configure the aiohttp web application."""
    app = web.Application()
    app.router.add_get("/", handle_index)
    app.router.add_get("/api/videos", handle_list_videos)
    app.router.add_get("/api/video/{video_id}", handle_get_video)
    app.router.add_get("/stream/{video_id}", handle_stream_video)
    app.router.add_static("/static/", path=STATIC_DIR, name="static")
    return app


def main():
    """Launch the human verification dashboard."""
    port = 8080
    host = "127.0.0.1"

    console.print(
        Panel.fit(
            f"[bold green]Video-to-Style Verification Dashboard[/bold green]\n"
            f"[cyan]Server URL:[/cyan] [underline]http://{host}:{port}[/underline]\n"
            f"[dim]Select any ingested video to view synchronized video playback and teleprompter script.[/dim]",
            title="🎬 Human Verification Tool",
            border_style="green",
        )
    )

    app = create_app()
    web.run_app(app, host=host, port=port, print=None)


if __name__ == "__main__":
    main()

