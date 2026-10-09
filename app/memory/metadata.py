"""
app/memory/metadata.py
Faceted metadata tag extractor for Video Memories.

Extracts structured, filterable metadata saved into the
SQLite video_memories.metadata_json column for faceted queries
(character filtering, mechanism matching, setting, pacing).
"""

from typing import Any, Dict, List, Union
from app.models.extraction import VideoExtraction


def extract_memory_metadata(extraction: Union[VideoExtraction, dict]) -> Dict[str, Any]:
    """
    Extract structured faceted tags from an extraction payload.

    Args:
        extraction: Validated VideoExtraction model or dictionary.

    Returns:
        Dictionary containing faceted tags:
        - characters: List of character names
        - character_codes: List of speaker codes ('A', 'B')
        - settings: List of distinct scene locations
        - comedy_mechanisms: List of comedic mechanism tags
        - pacing: Overall pacing descriptor
        - language: Language identifier
        - scene_count: Total scenes
        - dialogue_turn_count: Total dialogue lines
    """
    if isinstance(extraction, dict):
        ext = VideoExtraction.model_validate(extraction)
    else:
        ext = extraction

    # 1. Characters
    characters = [sp.n for sp in ext.sp] if ext.sp else []
    character_codes = [sp.c for sp in ext.sp] if ext.sp else []

    # 2. Settings
    settings_set = []
    for sc in ext.sc:
        if sc.loc and sc.loc not in settings_set:
            settings_set.append(sc.loc)

    # 3. Comedic Mechanisms
    cd = ext.cd
    mechanisms = cd.mech if cd and cd.mech else []

    # 4. Turn & Scene Counts
    total_turns = sum(len(sc.x) for sc in ext.sc)

    # 5. Compile Faceted Dict
    return {
        "characters": characters,
        "character_codes": character_codes,
        "settings": settings_set,
        "comedy_mechanisms": mechanisms,
        "pacing": cd.pace if cd and cd.pace else "fast",
        "dialogue_density": "high" if total_turns > 5 else "moderate",
        "language": ext.lang,
        "scene_count": len(ext.sc),
        "dialogue_turn_count": total_turns,
    }

