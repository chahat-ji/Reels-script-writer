"""
app/generation/parser.py
Screenplay element parser and metrics extractor for short-form video scripts.

Parses raw screenplay text into structured, typed elements for:
- Syntax-highlighted teleprompter rendering
- Industry-standard PDF page formatting
- Shooting beat sheet and shot list generation

Element types:
- slugline: Scene headers (INT. / EXT.)
- character: Character speaking cues
- parenthetical: Actor direction / emotion inside parentheses
- dialogue: Character dialogue lines
- action: Scene action / description
- button: Punchline ending / blackout transitions
- meta: Script comments / tags (# ...)
- blank: Empty spacing line
"""

import re
from typing import Any, Dict, List


def parse_screenplay_elements(script_text: str) -> List[Dict[str, str]]:
    """
    Parse screenplay text into typed elements for teleprompters, exporters, and beat sheets.

    Returns a list of dictionaries with 'type' and 'text'.
    """
    elements: List[Dict[str, str]] = []
    lines = script_text.splitlines() if script_text else []
    prev_was_character = False
    prev_was_parenthetical = False

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            prev_was_character = False
            prev_was_parenthetical = False
            elements.append({"type": "blank", "text": ""})
            continue

        # Meta comment
        if line.startswith("#"):
            elements.append({"type": "meta", "text": line})
            prev_was_character = False
            prev_was_parenthetical = False
            continue

        # Slugline
        clean_upper = re.sub(r"^\*+|\*+$", "", line).strip().upper()
        if clean_upper.startswith("INT.") or clean_upper.startswith("EXT."):
            elements.append({"type": "slugline", "text": line})
            prev_was_character = False
            prev_was_parenthetical = False
            continue

        # Button / Transition
        if clean_upper in (
            "BLACKOUT.", "BLACKOUT",
            "FADE OUT.", "FADE OUT",
            "CUT TO BLACK.", "CUT TO BLACK",
            "THE END.", "THE END",
        ):
            elements.append({"type": "button", "text": line})
            prev_was_character = False
            prev_was_parenthetical = False
            continue

        # Parenthetical
        if line.startswith("(") and line.endswith(")"):
            elements.append({"type": "parenthetical", "text": line})
            prev_was_character = False
            prev_was_parenthetical = True
            continue

        # Character cue (Short, uppercase or uppercase name before parenthetical)
        upper_token = re.sub(r"\s*\([^)]*\)", "", line).strip()
        is_character = (
            len(upper_token) > 0
            and len(upper_token) <= 30
            and upper_token.isupper()
            and not upper_token.endswith((".", "!", "?"))
            and not upper_token.startswith(("INT", "EXT"))
        )

        if is_character:
            elements.append({"type": "character", "text": line})
            prev_was_character = True
            prev_was_parenthetical = False
            continue

        # Dialogue following character or parenthetical
        if prev_was_character or prev_was_parenthetical:
            elements.append({"type": "dialogue", "text": line})
            continue

        # Action line
        elements.append({"type": "action", "text": line})
        prev_was_character = False
        prev_was_parenthetical = False

    return elements


def calculate_screenplay_metrics(script_text: str) -> Dict[str, Any]:
    """
    Calculate performance and production metrics from screenplay text:
    - word_count: Total spoken/action words
    - est_duration_sec: Estimated runtime assuming ~3 words/second short-form pacing
    - scene_count: Number of INT./EXT. sluglines
    - characters: Set of distinct uppercase character cues
    """
    if not script_text:
        return {
            "word_count": 0,
            "est_duration_sec": 0,
            "scene_count": 0,
            "characters": [],
            "total_elements": 0,
        }

    words = len(re.findall(r"\b\w+\b", script_text))
    est_duration = max(15, round(words / 3.0)) if words > 0 else 0
    elements = parse_screenplay_elements(script_text)

    scene_count = sum(1 for e in elements if e.get("type") == "slugline")
    characters = sorted(list({
        e["text"].strip()
        for e in elements
        if e.get("type") == "character" and e.get("text")
    }))

    return {
        "word_count": words,
        "est_duration_sec": est_duration,
        "scene_count": scene_count,
        "characters": characters,
        "total_elements": len(elements),
    }

