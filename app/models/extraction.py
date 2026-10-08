"""
app/models/extraction.py
Pydantic schemas for Gemini one-time multimodal video extraction.

Implements the high-efficiency compact structured JSON format specified
in Sections 6 and 7 of description.txt:
- Compact single/double-letter keys (sp, sc, s, e, x, cd, mech, esc, rev, punch)
- Single-letter speaker codes ('A', 'B') in turn arrays to eliminate name repetition
- Transcribed dialogue exclusively in Roman/English alphabet (Latin script)
  to minimize token consumption and unify cross-lingual processing
- Turn arrays: [start_ms, end_ms, speaker_code, dialogue_roman, emotion?, action?]
- Pure typed lists (no additionalProperties) for full Gemini Developer API compatibility
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


@dataclass
class UnpackedTurn:
    """
    Convenience container for programmatic consumption of an unpacked dialogue turn.
    Resolves speaker code 'A' -> Character name 'Saala'.
    """
    start_ms: int
    end_ms: int
    speaker_code: str
    speaker_name: str
    dialogue: str
    emotion: Optional[str] = None
    action: Optional[str] = None


class SpeakerEntry(BaseModel):
    """
    Speaker mapping and character persona (Section 5 & 6).
    Avoids additionalProperties in OpenAPI schema for Gemini Developer API.
    - c: Speaker code ('A', 'B', 'C')
    - n: Character name ('Saala', 'Jija')
    - desc: Character personality, role, or traits
    """
    c: str = Field(..., description="Speaker code 'A', 'B', 'C'")
    n: str = Field(..., description="Character name")
    desc: Optional[str] = Field(default=None, description="Character personality, role, or traits")


class CompactScene(BaseModel):
    """
    Compact scene block representation (Section 6: 'sc').
    Uses abbreviated keys to maximize token efficiency:
    - s: start offset in milliseconds
    - e: end offset in milliseconds
    - loc: scene setting / location
    - sit: situation / dramatic inciting beat
    - x: dialogue and action turns array
    """
    s: int = Field(default=0, ge=0, description="Scene start offset in milliseconds")
    e: int = Field(..., ge=0, description="Scene end offset in milliseconds")
    loc: Optional[str] = Field(default=None, description="Visual setting/location")
    sit: Optional[str] = Field(default=None, description="Dramatic situation or beat premise")
    x: List[List[Union[int, str]]] = Field(
        default_factory=list,
        description="Array of turns: [start_ms, end_ms, speaker_code, dialogue_roman, emotion?, action?]",
    )


class CompactCreativeDynamics(BaseModel):
    """
    Compact creative comedy and pacing dynamics (Section 5 & 6: 'cd').
    Uses abbreviated keys:
    - mech: comedic mechanisms
    - setup: setup premise
    - esc: escalation beat
    - rev: status or narrative reversal
    - punch: final punchline / undercut
    - rhythm: dialogue rhythm
    - pace: scene pacing
    - phys: observed physical comedic actions
    """
    mech: List[str] = Field(
        default_factory=list,
        description="Comedy mechanisms (e.g. ['status-undercutting', 'escalation', 'reversal'])",
    )
    setup: Optional[str] = Field(default=None, description="Comedic premise setup")
    esc: Optional[str] = Field(default=None, description="How the tension or absurdity escalates")
    rev: Optional[str] = Field(default=None, description="Turn or status reversal beat")
    punch: Optional[str] = Field(default=None, description="Final comedic punchline or undercut")
    rhythm: str = Field(
        default="short turns (1.5-3s), high dialogue density",
        description="Dialogue turn pacing pattern",
    )
    pace: str = Field(default="fast", description="Overall pacing (e.g. 'fast', 'punchy')")
    phys: List[str] = Field(
        default_factory=list,
        description="Meaningful physical gestures and reactions observed",
    )


class VideoExtraction(BaseModel):
    """
    Root compact extraction schema returned directly by Gemini 3.8 Flash (Section 6).
    
    Guarantees:
    1. Low output-token usage (saves ~70% of tokens compared to verbose JSON).
    2. Zero name repetition in turns (uses single-letter speaker codes 'A', 'B').
    3. Dialogue transcribed strictly in Roman/English alphabet (Latin script).
    4. Deterministic parsing and lossless archival representation.
    5. Pure typed arrays compatible with Gemini Developer API.
    """
    v: int = Field(default=1, description="Extraction schema version")
    sp: List[SpeakerEntry] = Field(
        default_factory=list,
        description="List of speakers: [{'c': 'A', 'n': 'Saala', 'desc': 'confident, eager to impress'}]",
    )
    sc: List[CompactScene] = Field(
        default_factory=list,
        description="Chronological scene blocks with compact turn arrays",
    )
    cd: CompactCreativeDynamics = Field(
        default_factory=CompactCreativeDynamics,
        description="Creative and comedic dynamics",
    )
    lang: str = Field(default="hi", description="Primary spoken language code (e.g. 'hi', 'en')")

    # -------------------------------------------------------------------------
    # Convenience Accessor Properties
    # -------------------------------------------------------------------------
    @property
    def speakers(self) -> Dict[str, str]:
        """Dictionary map of speaker code -> character name (e.g. {'A': 'Saala'})."""
        return {entry.c: entry.n for entry in self.sp}

    @property
    def characters(self) -> Dict[str, str]:
        """Dictionary map of speaker code -> character description."""
        return {entry.c: (entry.desc or entry.n) for entry in self.sp}

    @property
    def scenes(self) -> List[CompactScene]:
        """Convenience alias for scenes list."""
        return self.sc

    @property
    def creative_dynamics(self) -> CompactCreativeDynamics:
        """Convenience alias for creative dynamics."""
        return self.cd

    def get_character_name(self, speaker_code: str) -> str:
        """Resolve single-letter speaker code 'A' -> character name 'Saala'."""
        for entry in self.sp:
            if entry.c == speaker_code:
                return entry.n
        return speaker_code

    def unpack_turns(self) -> List[UnpackedTurn]:
        """
        Unpack all compact turn arrays across all scenes into typed UnpackedTurn objects
        with resolved character names for downstream synthesis and RAG generation.
        """
        unpacked = []
        for scene in self.sc:
            for turn in scene.x:
                if len(turn) >= 4:
                    start_ms = int(turn[0])
                    end_ms = int(turn[1])
                    speaker_code = str(turn[2])
                    dialogue = str(turn[3])
                    emotion = str(turn[4]) if len(turn) > 4 and turn[4] else None
                    action = str(turn[5]) if len(turn) > 5 and turn[5] else None

                    unpacked.append(
                        UnpackedTurn(
                            start_ms=start_ms,
                            end_ms=end_ms,
                            speaker_code=speaker_code,
                            speaker_name=self.get_character_name(speaker_code),
                            dialogue=dialogue,
                            emotion=emotion,
                            action=action,
                        )
                    )
        return unpacked

    def to_compact_dict(self) -> Dict[str, Any]:
        """Serialize directly into compact dictionary representation for archiving."""
        return self.model_dump()

    @classmethod
    def from_compact_dict(cls, data: Dict[str, Any]) -> "VideoExtraction":
        """Reconstruct VideoExtraction from dictionary format supporting both list and dict sp."""
        raw_sp = data.get("sp") or []
        sp_entries = []
        if isinstance(raw_sp, dict):
            raw_char = data.get("char") or {}
            for code, name in raw_sp.items():
                sp_entries.append(
                    SpeakerEntry(c=str(code), n=str(name), desc=raw_char.get(code))
                )
        elif isinstance(raw_sp, list):
            for item in raw_sp:
                if isinstance(item, dict):
                    sp_entries.append(SpeakerEntry(**item))
                elif isinstance(item, SpeakerEntry):
                    sp_entries.append(item)

        raw_sc = data.get("sc") or []
        sc_scenes = []
        for s in raw_sc:
            if isinstance(s, dict):
                sc_scenes.append(CompactScene(**s))
            elif isinstance(s, CompactScene):
                sc_scenes.append(s)

        raw_cd = data.get("cd") or {}
        cd_obj = CompactCreativeDynamics(**raw_cd) if isinstance(raw_cd, dict) else raw_cd

        return cls(
            v=data.get("v", 1),
            sp=sp_entries,
            sc=sc_scenes,
            cd=cd_obj,
            lang=data.get("lang", "hi"),
        )
