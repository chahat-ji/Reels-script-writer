"""
app/extraction/normalizer.py
Defensive normalization and timing sanitization for multimodal video extractions.

Detects and repairs LLM timestamp arithmetic hallucinations where Gemini encodes
MM:SS timecodes as hundreds of seconds (e.g. 1:08 hallucinated as 108,000 ms instead
of (1*60+8)*1000 = 68,000 ms). Enforces strict monotonic turn ordering and scene bounds.
"""

import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.core.config import console
from app.models.extraction import VideoExtraction


def get_media_duration_ms(file_path: Union[str, Path]) -> Optional[int]:
    """
    Query the exact duration of a video or audio file in milliseconds using ffprobe.
    Returns None if ffprobe is unavailable or parsing fails.
    """
    path = Path(file_path).resolve()
    if not path.is_file():
        return None

    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "json",
            str(path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        meta = json.loads(result.stdout)
        dur_s = float(meta["format"]["duration"])
        return int(round(dur_s * 1000))
    except Exception:
        return None


def normalize_timestamp_ms(val_ms: int, max_duration_ms: Optional[int] = None) -> int:
    """
    Detect and correct an individual timestamp corrupted by the MM:SS concatenation bug.

    Formula:
        minutes = int(seconds) // 100
        seconds_remainder = seconds % 100
        corrected_ms = (minutes * 60 + seconds_remainder) * 1000

    Example:
        108000 ms -> 108s -> 1 min 08s -> 68s -> 68000 ms
        135000 ms -> 135s -> 1 min 35s -> 95s -> 95000 ms
    """
    if val_ms <= 0:
        return 0

    sec = val_ms / 1000.0
    minutes = int(sec) // 100
    remainder = sec - (minutes * 100)

    # Valid MM:SS representation requires minutes >= 1 and remainder in [0, 60)
    if minutes >= 1 and 0 <= remainder < 60:
        cand_sec = minutes * 60 + remainder
        cand_ms = int(round(cand_sec * 1000))

        # Criterion A: If max_duration_ms is known and original exceeds it while candidate fits
        if max_duration_ms and val_ms > max_duration_ms and cand_ms <= max_duration_ms:
            return cand_ms

        # Criterion B: General conversion for values >= 100_000 ms where candidate is strictly smaller
        if val_ms >= 100_000 and cand_ms < val_ms:
            if max_duration_ms is None or cand_ms <= max_duration_ms:
                return cand_ms

    if max_duration_ms and val_ms > max_duration_ms:
        return max_duration_ms

    return val_ms


def normalize_scene_turns(
    turns: List[Any],
    max_duration_ms: Optional[int] = None,
) -> List[Any]:
    """
    Normalize timestamps across all dialogue turns in a scene, ensuring
    strictly monotonic ordering and valid turn durations.
    """
    normalized_turns = []
    prev_end = 0

    for turn in turns:
        # Turn format: [start_ms, end_ms, speaker, dialogue, emotion?, action?]
        if not isinstance(turn, (list, tuple)) or len(turn) < 4:
            normalized_turns.append(turn)
            continue

        raw_start, raw_end = int(turn[0]), int(turn[1])
        norm_start = normalize_timestamp_ms(raw_start, max_duration_ms)
        norm_end = normalize_timestamp_ms(raw_end, max_duration_ms)

        # Ensure start is monotonic relative to prior turn
        if norm_start < prev_end and prev_end > 0:
            norm_start = prev_end

        # Ensure turn has positive duration
        if norm_end <= norm_start:
            norm_end = norm_start + 1500

        if max_duration_ms and norm_end > max_duration_ms:
            norm_end = max_duration_ms
            if norm_start >= norm_end:
                norm_start = max(0, norm_end - 1000)

        prev_end = norm_end

        # Rebuild turn tuple/list
        new_turn = [norm_start, norm_end] + list(turn[2:])
        normalized_turns.append(new_turn)

    return normalized_turns


def normalize_extraction_dict(
    data: Dict[str, Any],
    max_duration_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Apply timing normalization to a raw extraction dictionary.
    """
    scenes = data.get("sc", [])
    if not isinstance(scenes, list):
        return data

    for scene in scenes:
        orig_s = scene.get("s", 0)
        orig_e = scene.get("e", 0)

        scene["s"] = normalize_timestamp_ms(orig_s, max_duration_ms)
        scene["e"] = normalize_timestamp_ms(orig_e, max_duration_ms)

        turns = scene.get("x", [])
        if turns:
            scene["x"] = normalize_scene_turns(turns, max_duration_ms)
            # Ensure scene encompasses all its dialogue turns
            first_turn_s = scene["x"][0][0]
            last_turn_e = scene["x"][-1][1]
            scene["s"] = min(scene["s"], first_turn_s)
            scene["e"] = max(scene["e"], last_turn_e)

    return data


def normalize_extraction(
    extraction: Union[VideoExtraction, Dict[str, Any]],
    max_duration_ms: Optional[int] = None,
) -> Union[VideoExtraction, Dict[str, Any]]:
    """
    Entrypoint to defensively sanitize timestamps on VideoExtraction or dict.
    """
    if isinstance(extraction, VideoExtraction):
        raw_dict = extraction.model_dump()
        clean_dict = normalize_extraction_dict(raw_dict, max_duration_ms)
        return VideoExtraction.model_validate(clean_dict)
    elif isinstance(extraction, dict):
        return normalize_extraction_dict(extraction, max_duration_ms)
    return extraction

