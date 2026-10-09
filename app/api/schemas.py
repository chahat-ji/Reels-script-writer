"""
app/api/schemas.py
Pydantic Data Transfer Objects (DTOs) for API request and response models.
Strictly validates inputs and sanitizes public vs admin responses.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Auth Schemas
# ---------------------------------------------------------------------------

class LoginRequest(BaseModel):
    username_or_email: str = Field(..., description="Username or email address")
    password: str = Field(..., min_length=1, description="Account password")


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64, description="User handle")
    email: Optional[str] = Field(None, description="Optional email address")
    password: str = Field(..., min_length=4, description="Account password")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    role: str


class UserProfileResponse(BaseModel):
    user_id: str
    username: str
    email: Optional[str] = None
    role: str
    auth_provider: str = "local"


# ---------------------------------------------------------------------------
# Script & Screenplay Schemas
# ---------------------------------------------------------------------------

class ScriptGenerateRequest(BaseModel):
    premise: str = Field(..., min_length=3, description="Creative logline or situation")
    creator_id: Optional[str] = Field("default_style", description="Target creator profile")


class ScriptReviewRequest(BaseModel):
    status: str = Field("draft", description="Review status: draft, approved, needs_revision, rejected")
    rating: Optional[int] = Field(None, ge=1, le=5, description="1-5 star human rating")
    review_notes: Optional[str] = Field(None, description="Critique or revision guidance")


class ScriptSummaryResponse(BaseModel):
    script_id: str
    creator_id: str
    user_id: Optional[str]
    premise: str
    status: str
    rating: Optional[int]
    word_count: int
    est_duration_sec: int
    created_at: str


class ScriptDetailResponse(BaseModel):
    script_id: str
    creator_id: str
    creator_name: str
    user_id: Optional[str]
    premise: str
    script_text: str
    status: str
    rating: Optional[int]
    review_notes: str
    word_count: int
    est_duration_sec: int
    created_at: str
    parsed_elements: List[Dict[str, str]]
    style_bible: Optional[str] = None


# ---------------------------------------------------------------------------
# Video & Ingestion Schemas
# ---------------------------------------------------------------------------

class VideoUploadRequest(BaseModel):
    source_url: str = Field(..., description="Instagram Reel URL or local video path")
    creator_id: Optional[str] = Field("default_style", description="Creator to link video with")


class VideoSummaryResponse(BaseModel):
    video_id: str
    sha256: str
    status: str
    has_extraction: bool
    has_audio: bool
    created_at: str


# ---------------------------------------------------------------------------
# Admin & Benchmark Schemas
# ---------------------------------------------------------------------------

class StyleSummaryResponse(BaseModel):
    style_id: str
    name: Optional[str]
    version: int
    has_bible: bool
    reference_video_count: int


class BenchmarkMetricsResponse(BaseModel):
    total_videos: int
    total_scripts: int
    total_creators: int
    reviewed_scripts_count: int
    average_rating: Optional[float]
    extraction_health_percentage: float

