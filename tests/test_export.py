"""
tests/test_export.py
Unit tests for production screenplay exporters (Hollywood PDF and shooting beat sheet).
Runs 100% offline with zero external API calls.
"""

import asyncio
from pathlib import Path
from aiohttp.test_utils import make_mocked_request
from aiohttp import web

from app.core.config import settings
from app.export.pdf import export_screenplay_to_pdf, sanitize_text_for_pdf
from app.export.beat_sheet import generate_beat_sheet, suggest_camera_framing
from tools.dashboard.service import get_all_scripts
from tools.dashboard.server import (
    handle_export_script_pdf,
    handle_get_script_beat_sheet,
    handle_export_script_beat_sheet,
)


def test_sanitize_text_for_pdf():
    """Verify sanitize_text_for_pdf handles rupees, xml entities, and special chars."""
    raw = "Total: ₹800 & <Gravy> with emojis 🎬"
    cleaned = sanitize_text_for_pdf(raw)
    assert "Rs. 800" in cleaned
    assert "&amp;" in cleaned
    assert "&lt;Gravy&gt;" in cleaned
    assert "🎬" not in cleaned


def test_suggest_camera_framing():
    """Verify camera framing heuristic assigns appropriate shot types."""
    assert "Hook" in suggest_camera_framing(1, 10, "action", "Mummy enters room")
    assert "Snap Zoom" in suggest_camera_framing(5, 10, "dialogue", "Mummy shrieks in horror")
    assert "Fast Track" in suggest_camera_framing(8, 10, "action", "Dadi jumps and scurries away")
    assert "Blackout" in suggest_camera_framing(10, 10, "button", "BLACKOUT.")


def test_export_screenplay_to_pdf(tmp_path):
    """Verify export_screenplay_to_pdf creates valid Hollywood screenplay PDF."""
    scripts = get_all_scripts()
    assert len(scripts) > 0, "No scripts found in test database"
    test_id = scripts[0]["script_id"]

    out_file = tmp_path / f"{test_id}_test.pdf"
    res = export_screenplay_to_pdf(test_id, output_path=out_file)

    assert res.is_file()
    assert res.stat().st_size > 1000
    with open(res, "rb") as f:
        header = f.read(5)
        assert header == b"%PDF-"


def test_generate_beat_sheet_markdown_and_csv(tmp_path):
    """Verify generate_beat_sheet produces structured beats and exports files."""
    scripts = get_all_scripts()
    test_id = scripts[0]["script_id"]

    payload = generate_beat_sheet(test_id, export_files=True)
    assert payload["script_id"] == test_id
    assert payload["total_beats"] > 0
    assert "beats" in payload

    first_beat = payload["beats"][0]
    assert "beat_number" in first_beat
    assert "time_range" in first_beat
    assert "framing" in first_beat
    assert "character" in first_beat
    assert "dialogue_cue" in first_beat

    md_file = settings.exports_dir / f"{test_id}_beat_sheet.md"
    csv_file = settings.exports_dir / f"{test_id}_shotlist.csv"
    assert md_file.is_file()
    assert csv_file.is_file()


def test_handle_export_script_pdf_endpoint():
    """Verify REST handler serves generated PDF file response."""
    scripts = get_all_scripts()
    test_id = scripts[0]["script_id"]

    async def _run():
        req = make_mocked_request("GET", f"/api/script/{test_id}/export/pdf", match_info={"script_id": test_id})
        resp = await handle_export_script_pdf(req)
        assert isinstance(resp, web.FileResponse)
        assert resp.status == 200
        assert "Content-Disposition" in resp.headers

    asyncio.run(_run())


def test_handle_get_script_beat_sheet_endpoint():
    """Verify REST handler returns JSON payload with beats."""
    scripts = get_all_scripts()
    test_id = scripts[0]["script_id"]

    async def _run():
        req = make_mocked_request("GET", f"/api/script/{test_id}/beat_sheet", match_info={"script_id": test_id})
        resp = await handle_get_script_beat_sheet(req)
        assert resp.status == 200
        assert resp.content_type == "application/json"

    asyncio.run(_run())


def test_handle_export_script_beat_sheet_endpoint():
    """Verify REST handler serves Markdown file download."""
    scripts = get_all_scripts()
    test_id = scripts[0]["script_id"]

    async def _run():
        req = make_mocked_request("GET", f"/api/script/{test_id}/export/beat_sheet", match_info={"script_id": test_id})
        resp = await handle_export_script_beat_sheet(req)
        assert isinstance(resp, web.FileResponse)
        assert resp.status == 200

    asyncio.run(_run())

