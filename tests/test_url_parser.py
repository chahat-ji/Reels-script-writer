"""
tests/test_url_parser.py
Unit tests for URL parsing, shortcode extraction, tracking parameter removal,
and canonicalization across all Instagram link shapes.
"""

from app.ingestion.url_parser import (
    clean_input_string,
    is_instagram_url,
    parse_instagram_shortcode,
    canonicalize_url,
)


def test_clean_input_string_strips_quotes_and_spaces():
    """Verify enclosing quotes and whitespace are safely removed."""
    assert clean_input_string("  https://instagram.com/reel/XYZ/  ") == "https://instagram.com/reel/XYZ/"
    assert clean_input_string('"https://instagram.com/reel/XYZ/"') == "https://instagram.com/reel/XYZ/"
    assert clean_input_string("'https://instagram.com/reel/XYZ/'") == "https://instagram.com/reel/XYZ/"


def test_parse_instagram_shortcode_all_variants():
    """Verify shortcode extraction across all Instagram URL variations."""
    target_code = "Dd_AXb6hFb6"
    test_urls = [
        # Query parameters with tracking and encoding
        "https://www.instagram.com/reel/Dd_AXb6hFb6/?utm_source=ig_web_copy_link&obrf=MzRlODBiNWFlZA==&srtk=MzRlODBiNWFlZA==",
        # Clean reel URLs
        "https://www.instagram.com/reel/Dd_AXb6hFb6",
        "https://www.instagram.com/reel/Dd_AXb6hFb6/",
        # /reels/ plural
        "https://www.instagram.com/reels/Dd_AXb6hFb6/",
        # /p/ post/feed format
        "https://www.instagram.com/p/Dd_AXb6hFb6/",
        # /tv/ format
        "https://www.instagram.com/tv/Dd_AXb6hFb6/?utm_medium=copy_link",
        # /share/ formats
        "https://www.instagram.com/share/reel/Dd_AXb6hFb6/?utm_source=share",
        "https://www.instagram.com/share/p/Dd_AXb6hFb6/",
        # Subpaths with creator username
        "https://www.instagram.com/some_creator/reel/Dd_AXb6hFb6/",
        # /feed/ format
        "https://www.instagram.com/feed/Dd_AXb6hFb6/",
        # Domain variations without www or mobile
        "https://instagram.com/reel/Dd_AXb6hFb6",
        "http://instagr.am/p/Dd_AXb6hFb6/",
        "https://m.instagram.com/reel/Dd_AXb6hFb6/",
        # Quoted string
        "\"https://www.instagram.com/reel/Dd_AXb6hFb6/?utm_source=ig_web_copy_link\"",
    ]

    for url in test_urls:
        extracted = parse_instagram_shortcode(url)
        assert extracted == target_code, f"Failed for URL: {url}"


def test_canonicalize_instagram_urls():
    """Verify canonicalize_url produces standard reel URL for Instagram inputs."""
    expected_canonical = "https://www.instagram.com/reel/Dd_AXb6hFb6/"

    url_with_params = (
        "https://www.instagram.com/reel/Dd_AXb6hFb6/?utm_source=ig_web_copy_link&obrf=MzRlODBiNWFlZA==&srtk=MzRlODBiNWFlZA=="
    )
    url_without_params = "https://www.instagram.com/reel/Dd_AXb6hFb6"
    url_post_format = "https://www.instagram.com/p/Dd_AXb6hFb6/"
    url_feed_format = "https://www.instagram.com/feed/Dd_AXb6hFb6/"

    assert canonicalize_url(url_with_params) == expected_canonical
    assert canonicalize_url(url_without_params) == expected_canonical
    assert canonicalize_url(url_post_format) == expected_canonical
    assert canonicalize_url(url_feed_format) == expected_canonical


def test_is_instagram_url():
    """Verify Instagram domain detection."""
    assert is_instagram_url("https://www.instagram.com/reel/123/") is True
    assert is_instagram_url("http://instagr.am/p/123/") is True
    assert is_instagram_url("https://youtube.com/watch?v=123") is False
    assert is_instagram_url("/local/path/to/video.mp4") is False


def test_canonicalize_generic_url_strips_tracking():
    """Verify general tracking params are stripped from other URLs."""
    generic_url = "https://example.com/video.mp4?utm_source=twitter&utm_medium=social&custom_param=keep"
    canonical = canonicalize_url(generic_url)
    assert "utm_source" not in canonical
    assert "utm_medium" not in canonical
    assert "custom_param=keep" in canonical

