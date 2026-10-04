"""
app/capabilities/base.py
Core interfaces and data schemas for capabilities and providers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class Requirements(BaseModel):
    min_ram_gb: float = Field(default=2.0, description="Minimum RAM required in GB")
    needs_gpu: bool = Field(default=False, description="Whether Apple Silicon / CUDA GPU is required")
    api_key_env: Optional[str] = Field(default=None, description="Name of environment variable holding API key")
    languages: List[str] = Field(default_factory=lambda: ["en", "hi"], description="Supported language codes")


class Health(BaseModel):
    installed: bool = Field(..., description="Whether required binary or python module is installed")
    key_present: bool = Field(default=True, description="Whether API key is set if required")
    enough_ram: bool = Field(default=True, description="Whether host system has sufficient memory")
    error: Optional[str] = Field(default=None, description="Error message if not healthy")


class Estimate(BaseModel):
    expected_cost_usd: float = Field(default=0.0, description="Estimated API cost in USD")
    expected_seconds: float = Field(default=10.0, description="Estimated processing wall-clock time")
    peak_ram_gb: float = Field(default=1.0, description="Estimated peak RAM consumption")


class CanonicalEvent(BaseModel):
    track: Literal["speech", "diarization", "shot", "ocr", "face", "music", "beat"]
    start_ms: int = Field(..., ge=0, description="Start offset in milliseconds")
    end_ms: int = Field(..., ge=0, description="End offset in milliseconds")
    type: str = Field(..., description="Event type name (e.g., 'word', 'speaker_turn', 'scene_cut')")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Event-specific metadata")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Model confidence score")
    provider: str = Field(..., description="Name of provider generating this event")
    provider_version: str = Field(default="1.0.0")
    run_id: Optional[str] = Field(default=None)


class ProviderResult(BaseModel):
    capability: str
    provider_name: str
    provider_version: str
    events: List[CanonicalEvent] = Field(default_factory=list)
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Provider(ABC):
    capability: str
    name: str
    version: str = "1.0.0"
    tier: Literal["local", "free", "paid"]
    requirements: Requirements = Requirements()

    @abstractmethod
    def health(self) -> Health:
        """Check system prerequisites (binaries, API keys, memory)."""
        pass

    @abstractmethod
    def estimate(self, media_info: Dict[str, Any]) -> Estimate:
        """Estimate time, cost, and RAM for a given media input."""
        pass

    @abstractmethod
    def run(self, job: Dict[str, Any]) -> ProviderResult:
        """Execute task and return normalized CanonicalEvents alongside raw output."""
        pass