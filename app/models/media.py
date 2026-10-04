"""
app/models/media.py
Data contracts for ingested media and container inspection.
"""

from pathlib import Path
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class AudioSpecs(BaseModel):
    sample_rate: int = Field(default=16000, description="Sampling rate in Hz")
    channels: int = Field(default=1, description="Number of audio channels")
    codec: str = Field(default="pcm_s16le", description="Audio codec")
    duration_seconds: float = Field(..., ge=0.0)


class VideoSpecs(BaseModel):
    width: int
    height: int
    fps: float
    duration_seconds: float
    codec: str


class IngestedMedia(BaseModel):
    reel_id: str
    source_url: Optional[str] = None
    video_path: Path
    audio_path: Path
    metadata_path: Path
    audio_specs: AudioSpecs
    video_specs: Optional[VideoSpecs] = None
    raw_metadata: Dict[str, Any] = Field(default_factory=dict)