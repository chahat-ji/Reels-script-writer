"""
app/ingestion/url_parser.py
URL parsing, sanitization, and canonicalization for Instagram and video sources.

Handles all Instagram link variants:
- /reel/{code}, /reels/{code}
- /p/{code} (posts / feed videos)
- /tv/{code} (IGTV)
- /share/reel/{code}, /share/p/{code}
- /feed/{code}
- Subpaths with creator usernames (instagram.com/{user}/reel/{code})
- Domain variations (www.instagram.com, m.instagram.com, instagr.am)
- Tracking query parameters (utm_*, igsh, obrf, srtk, etc.)
"""

import re
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Comprehensive regex to extract Instagram shortcode across all path structures
INSTAGRAM_SHORTCODE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.|m\.)?(?:instagram\.com|instagr\.am)/"
    r"(?:(?:share|feed|[^/?#]+)/)?(?:reel|reels|p|tv|feed)/([A-Za-z0-9_-]+)",
    re.IGNORECASE,
)

# Tracking parameters that should be stripped from any general URL
TRACKING_QUERY_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "igsh",
    "obrf",
    "srtk",
    "fbclid",
    "gclid",
    "ref",
}


def clean_input_string(raw_input: str) -> str:
    """
    Strip whitespace, surrounding quotes, and terminal escape artifacts.
    """
    cleaned = raw_input.strip()
    # Strip enclosing single or double quotes
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (
        cleaned.startswith("'") and cleaned.endswith("'")
    ):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def is_instagram_url(url: str) -> bool:
    """
    Check if a string represents an Instagram URL.
    """
    cleaned = clean_input_string(url).lower()
    return "instagram.com" in cleaned or "instagr.am" in cleaned


def parse_instagram_shortcode(url: str) -> Optional[str]:
    """
    Extract the canonical alphanumeric shortcode from any Instagram URL variation.

    Examples:
        - https://www.instagram.com/reel/Dd_AXb6hFb6/?utm_source=... -> 'Dd_AXb6hFb6'
        - https://www.instagram.com/reel/Dd_AXb6hFb6 -> 'Dd_AXb6hFb6'
        - https://www.instagram.com/reels/Dd_AXb6hFb6/ -> 'Dd_AXb6hFb6'
        - https://www.instagram.com/p/Dd_AXb6hFb6/ -> 'Dd_AXb6hFb6'
        - https://www.instagram.com/tv/Dd_AXb6hFb6/ -> 'Dd_AXb6hFb6'
        - https://www.instagram.com/share/reel/Dd_AXb6hFb6/ -> 'Dd_AXb6hFb6'
        - https://www.instagram.com/creator/reel/Dd_AXb6hFb6/ -> 'Dd_AXb6hFb6'
    """
    cleaned = clean_input_string(url)
    match = INSTAGRAM_SHORTCODE_REGEX.search(cleaned)
    if match:
        return match.group(1)
    return None


def canonicalize_url(source: str) -> str:
    """
    Translate any video URL or source string into a clean canonical representation.

    - For Instagram: Translates to standard 'https://www.instagram.com/reel/{shortcode}/'
      stripping all query tracking parameters.
    - For other URLs: Strips tracking query parameters (utm_*, fbclid, etc.).
    - For local paths: Resolves to absolute filesystem path string.
    """
    cleaned = clean_input_string(source)

    # 1. Instagram URL canonicalization
    if is_instagram_url(cleaned):
        shortcode = parse_instagram_shortcode(cleaned)
        if shortcode:
            return f"https://www.instagram.com/reel/{shortcode}/"

    # 2. General HTTP/HTTPS URL tracking cleanup
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        parsed = urlparse(cleaned)
        filtered_queries = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if k.lower() not in TRACKING_QUERY_PARAMS and not k.lower().startswith("utm_")
        ]
        new_query = urlencode(filtered_queries)
        clean_path = parsed.path.rstrip("/") + "/" if parsed.path else "/"
        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            clean_path,
            parsed.params,
            new_query,
            parsed.fragment,
        ))

    # 3. Local filesystem path
    local_path = Path(cleaned)
    if local_path.is_file():
        return str(local_path.resolve())

    return cleaned

