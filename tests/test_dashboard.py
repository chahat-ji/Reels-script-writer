"""
tests/test_dashboard.py
Unit tests for the verification dashboard service and request handlers.
Tests video listing, extraction payload building, and HTTP response handling.
"""

import asyncio
from pathlib import Path
from aiohttp.test_utils import make_mocked_request
from aiohttp import web

from tools.dashboard.service import get_all_videos, get_video_payload
from tools.dashboard.server import (
    handle_index,
    handle_list_videos,
    handle_get_video,
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

