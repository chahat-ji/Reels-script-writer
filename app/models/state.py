"""
app/models/state.py
Schemas for condition reports, routing plans, and pipeline state.
"""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class AudioCondition(BaseModel):
    has_heavy_music: bool = Field(default=False, description="True if music-to-voice ratio exceeds threshold")
    music_energy_ratio: float = Field(default=0.0, description="Estimated background music energy ratio (0.0 - 1.0)")
    silence_ratio: float = Field(default=0.0, description="Percentage of audio below silence threshold")
    average_db: float = Field(default=-20.0, description="Mean volume in dBFS")
    needs_stem_separation: bool = Field(default=False, description="Flag indicating vocals need isolation")


class ConditionReport(BaseModel):
    reel_id: str
    audio_condition: AudioCondition
    duration_seconds: float
    flags: List[str] = Field(default_factory=list)


class TaskPlan(BaseModel):
    capability: str
    provider_chain: List[str] = Field(..., description="Ordered list of providers (primary -> fallbacks)")
    estimated_cost_usd: float = 0.0
    estimated_seconds: float = 0.0


class ExecutionPlan(BaseModel):
    reel_id: str
    profile: str
    preflight: ConditionReport
    plans: Dict[str, TaskPlan] = Field(default_factory=dict)