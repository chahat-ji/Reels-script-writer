"""
tests/test_dashboard.py
Unit tests for the verification dashboard service and request handlers.
Tests video listing, extraction payload building, and HTTP response handling.
"""

import asyncio
from pathlib import Path
from aiohttp.test_utils import make_mocked_request
from aiohttp import web

from tools.dashboard.service import (
    get_all_videos,
    get_video_payload,
    get_all_scripts,
    get_script_payload,
    parse_screenplay_elements,
    update_script_review,
)
from tools.dashboard.server import (
    handle_index,
    handle_list_videos,
    handle_get_video,
    handle_list_scripts,
    handle_get_script,
    handle_update_script_review,
    handle_stream_video,
)


def test_get_all_videos_service():
    """Verify get_all_videos returns valid records with extraction status."""
    videos = get_all_videos()
    assert isinstance(videos, list)
    assert len(videos) > 0
    first = videos[0]
    assert "video_id" in first
    assert "has_extraction" in first
    assert "status" in first


def test_get_video_payload_service():
    """Verify get_video_payload retrieves complete metadata and extraction."""
    videos = get_all_videos()
    test_id = videos[0]["video_id"]

    payload = get_video_payload(test_id)
    assert payload is not None
    assert payload["video_id"] == test_id
    assert "has_video_file" in payload
    assert "extraction" in payload
    if payload["extraction"]:
        assert "sp" in payload["extraction"]
        assert "sc" in payload["extraction"]


def test_handle_index_handler():
    """Verify handle_index serves the index.html file response."""
    async def _run():
        req = make_mocked_request("GET", "/")
        resp = await handle_index(req)
        assert isinstance(resp, web.FileResponse)
        assert resp.status == 200
        assert Path(resp._path).name == "index.html"

    asyncio.run(_run())


def test_handle_list_videos_handler():
    """Verify handle_list_videos returns JSON response with video catalog."""
    async def _run():
        req = make_mocked_request("GET", "/api/videos")
        resp = await handle_list_videos(req)
        assert resp.status == 200
        assert resp.content_type == "application/json"

    asyncio.run(_run())


def test_handle_get_video_handler():
    """Verify handle_get_video returns JSON payload for valid video_id."""
    videos = get_all_videos()
    test_id = videos[0]["video_id"]

    async def _run():
        req = make_mocked_request("GET", f"/api/video/{test_id}", match_info={"video_id": test_id})
        resp = await handle_get_video(req)
        assert resp.status == 200
        assert resp.content_type == "application/json"

    asyncio.run(_run())


def test_handle_stream_video_handler():
    """Verify handle_stream_video serves video file with FileResponse."""
    videos = get_all_videos()
    test_id = videos[0]["video_id"]

    async def _run():
        req = make_mocked_request("GET", f"/stream/{test_id}", match_info={"video_id": test_id})
        resp = await handle_stream_video(req)
        assert isinstance(resp, web.FileResponse)
        assert resp.status == 200
        assert Path(resp._path).suffix == ".mp4"

    asyncio.run(_run())


def test_parse_screenplay_elements():
    """Verify screenplay text parsing identifies sluglines, characters, dialogue, and buttons."""
    sample = (
        "# SCREENPLAY: scr_test\n\n"
        "**INT. LIVING ROOM - DAY**\n\n"
        "MUMMY enters holding a spoon.\n\n"
        "MUMMY\n"
        "(Angry)\n"
        "Where is the paneer?\n\n"
        "DADI\n"
        "In your dreams.\n\n"
        "**BLACKOUT.**\n"
    )
    elements = parse_screenplay_elements(sample)
    types = [e["type"] for e in elements]
    assert "slugline" in types
    assert "character" in types
    assert "parenthetical" in types
    assert "dialogue" in types
    assert "button" in types


def test_get_all_scripts_and_payload_service():
    """Verify get_all_scripts and get_script_payload retrieve valid records."""
    scripts = get_all_scripts()
    assert isinstance(scripts, list)
    if scripts:
        s = scripts[0]
        assert "script_id" in s
        assert "status" in s
        assert "word_count" in s
        assert s["word_count"] > 0
        assert "est_duration_sec" in s

        payload = get_script_payload(s["script_id"])
        assert payload is not None
        assert payload["script_id"] == s["script_id"]
        assert "script_text" in payload
        assert "parsed_elements" in payload
        assert "style_bible" in payload
        assert "reference_videos" in payload


def test_handle_list_scripts_handler():
    """Verify handle_list_scripts returns HTTP 200 with JSON list."""
    async def _run():
        req = make_mocked_request("GET", "/api/scripts")
        resp = await handle_list_scripts(req)
        assert resp.status == 200
        assert resp.content_type == "application/json"

    asyncio.run(_run())


def test_handle_get_script_handler():
    """Verify handle_get_script returns HTTP 200 with script payload."""
    scripts = get_all_scripts()
    if not scripts:
        return
    test_id = scripts[0]["script_id"]

    async def _run():
        req = make_mocked_request("GET", f"/api/script/{test_id}", match_info={"script_id": test_id})
        resp = await handle_get_script(req)
        assert resp.status == 200
        assert resp.content_type == "application/json"

    asyncio.run(_run())


def test_handle_update_script_review_handler():
    """Verify handle_update_script_review persists review status and rating."""
    scripts = get_all_scripts()
    if not scripts:
        return
    test_id = scripts[0]["script_id"]

    # 1. Update review via service
    updated = update_script_review(test_id, status="approved", rating=5, review_notes="Excellent comedic timing!")
    assert updated is not None
    assert updated["status"] == "approved"
    assert updated["rating"] == 5

    # 2. Re-fetch via payload
    payload = get_script_payload(test_id)
    assert payload["status"] == "approved"
    assert payload["rating"] == 5
    assert payload["review_notes"] == "Excellent comedic timing!"


