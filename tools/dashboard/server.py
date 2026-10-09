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
from tools.dashboard.service import (
    get_all_videos,
    get_video_payload,
    get_all_scripts,
    get_script_payload,
    update_script_review,
)

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


async def handle_list_scripts(request: web.Request) -> web.Response:
    """REST API: Return list of all generated screenplays in the catalog."""
    style_id = request.query.get("style_id")
    user_id = request.query.get("user_id")
    scripts = get_all_scripts(style_id=style_id, user_id=user_id)
    return web.json_response(scripts)


async def handle_get_script(request: web.Request) -> web.Response:
    """REST API: Return complete screenplay, Style Bible, and review metadata for script_id."""
    script_id = request.match_info["script_id"]
    payload = get_script_payload(script_id)
    if not payload:
        return web.json_response({"error": "Script not found"}, status=404)
    return web.json_response(payload)


async def handle_update_script_review(request: web.Request) -> web.Response:
    """REST API: Update human evaluation status, 1-5 rating, and notes for script_id."""
    script_id = request.match_info["script_id"]
    try:
        body = await request.json()
    except Exception:
        body = {}

    status = body.get("status", "draft")
    rating = body.get("rating")
    review_notes = body.get("review_notes")

    updated = update_script_review(
        script_id=script_id,
        status=status,
        rating=rating,
        review_notes=review_notes,
    )
    if not updated:
        return web.json_response({"error": "Script not found"}, status=404)
    return web.json_response(updated)


async def handle_export_script_pdf(request: web.Request) -> web.FileResponse:
    """REST API: Generate and download Hollywood standard screenplay PDF."""
    from app.export.pdf import export_screenplay_to_pdf
    script_id = request.match_info["script_id"]
    try:
        pdf_path = export_screenplay_to_pdf(script_id)
    except ValueError as err:
        return web.json_response({"error": str(err)}, status=404)

    return web.FileResponse(
        pdf_path,
        headers={"Content-Disposition": f'attachment; filename="{script_id}.pdf"'},
    )


async def handle_get_script_beat_sheet(request: web.Request) -> web.Response:
    """REST API: Return JSON shooting beat sheet and shot list for script_id."""
    from app.export.beat_sheet import generate_beat_sheet
    script_id = request.match_info["script_id"]
    try:
        payload = generate_beat_sheet(script_id, export_files=False)
    except ValueError as err:
        return web.json_response({"error": str(err)}, status=404)

    return web.json_response(payload)


async def handle_export_script_beat_sheet(request: web.Request) -> web.FileResponse:
    """REST API: Download Markdown shooting beat sheet table."""
    from app.export.beat_sheet import generate_beat_sheet
    script_id = request.match_info["script_id"]
    try:
        _ = generate_beat_sheet(script_id, export_files=True)
    except ValueError as err:
        return web.json_response({"error": str(err)}, status=404)

    md_path = settings.exports_dir / f"{script_id}_beat_sheet.md"
    return web.FileResponse(
        md_path,
        headers={"Content-Disposition": f'attachment; filename="{script_id}_beat_sheet.md"'},
    )


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
    app.router.add_get("/api/scripts", handle_list_scripts)
    app.router.add_get("/api/script/{script_id}", handle_get_script)
    app.router.add_post("/api/script/{script_id}/review", handle_update_script_review)
    app.router.add_get("/api/script/{script_id}/export/pdf", handle_export_script_pdf)
    app.router.add_get("/api/script/{script_id}/beat_sheet", handle_get_script_beat_sheet)
    app.router.add_get("/api/script/{script_id}/export/beat_sheet", handle_export_script_beat_sheet)
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

