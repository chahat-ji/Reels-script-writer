"""
app/models/schema.py
SQLAlchemy declarative models for the Video-to-Style Script Generation architecture.

Defines the permanent data model specified in Section 21 of description.txt:
- Style: Global style registry and versioned Style Bibles.
- Video: Permanent video identity and metadata (with SHA-256 duplicate index).
- VideoMemory: Example-level creative RAG representation, raw extraction backup,
               and NumPy embedding vector.
- StyleReference: Relational mapping connecting videos to styles.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
import numpy as np
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class User(Base):
    """
    USER entity.
    Future-proofed for OAuth providers (Google, Clerk, Auth0).
    In pilot mode, auth_provider defaults to 'local'.
    """

    __tablename__ = "users"

    user_id = Column(String(64), primary_key=True, index=True)
    username = Column(String(64), unique=True, index=True, nullable=False)
    email = Column(String(128), unique=True, nullable=True)
    auth_provider = Column(String(32), default="local", nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relational associations
    styles = relationship("Style", back_populates="user", cascade="all, delete-orphan")
    scripts = relationship("Script", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.user_id}, username={self.username})>"


class Style(Base):
    """
    STYLE / CREATOR entity (Section 21 of description.txt).
    Represents a creative style catalog or creator profile (e.g. 'ashish_chanchlani', 'desi_comedy').
    Holds the synthesized Style Bible, human-friendly creator name, and current version number.
    """

    __tablename__ = "styles"

    style_id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=True, index=True)
    name = Column(String(128), nullable=True)  # Human-friendly creator name e.g. "Ashish Chanchlani"
    description = Column(Text, nullable=True)
    version = Column(Integer, default=1, nullable=False)
    bible_text = Column(Text, nullable=True)  # Markdown text of the synthesized Style Bible
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relational associations
    user = relationship("User", back_populates="styles")
    memories = relationship("VideoMemory", back_populates="style", cascade="all, delete-orphan")
    references = relationship("StyleReference", back_populates="style", cascade="all, delete-orphan")
    scripts = relationship("Script", back_populates="style", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Style(id={self.style_id}, name={self.name}, version={self.version})>"


class Video(Base):
    """
    VIDEO entity (Section 21 of description.txt).
    Permanent identity and storage pointer for an ingested video.
    Tracks the SHA-256 hash to guarantee duplicate uploads are immediately skipped.
    """

    __tablename__ = "videos"

    video_id = Column(String(64), primary_key=True, index=True)
    sha256 = Column(String(64), unique=True, index=True, nullable=False)  # For duplicate detection
    source_url = Column(Text, nullable=True, index=True)  # Canonical web source URL for pre-download idempotency
    storage_uri = Column(Text, nullable=False)  # Permanent URI (e.g. file:///... or s3://...)
    audio_uri = Column(Text, nullable=True)     # Extracted audio URI (e.g. file:///.../audio.m4a)
    duration_ms = Column(Integer, nullable=True)  # Duration in milliseconds
    language = Column(String(16), default="hi", nullable=False)
    status = Column(String(32), default="stored", nullable=False)  # stored, extracted, error
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relational associations
    memory = relationship("VideoMemory", back_populates="video", uselist=False, cascade="all, delete-orphan")
    references = relationship("StyleReference", back_populates="video", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Video(id={self.video_id}, sha256={self.sha256[:8]}..., status={self.status})>"


class VideoMemory(Base):
    """
    VIDEO_MEMORY entity (Section 21 of description.txt).
    Creative example-level representation used for RAG generation.
    Contains:
    - memory_text: Human-readable creative distillation (Markdown).
    - structured_extraction: Archival backup of the compact JSON returned by Gemini.
    - embedding: Serialized NumPy float32 embedding vector (from text-embedding-004).
    - metadata_json: Searchable faceted tags (characters, setting, comedy mechanisms, pace).
    - extraction_version: Version of the extraction prompt/schema used.
    """

    __tablename__ = "video_memories"

    video_id = Column(String(64), ForeignKey("videos.video_id"), primary_key=True)
    style_id = Column(String(64), ForeignKey("styles.style_id"), index=True, nullable=False)
    memory_text = Column(Text, nullable=True)
    structured_extraction = Column(JSON, nullable=True)
    embedding = Column(LargeBinary, nullable=True)  # Raw float32 bytes for fast NumPy cosine search
    metadata_json = Column(JSON, nullable=True)
    extraction_version = Column(Integer, default=1, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relational associations
    video = relationship("Video", back_populates="memory")
    style = relationship("Style", back_populates="memories")

    def set_embedding(self, vector: np.ndarray) -> None:
        """Serialize a 1D NumPy float32 array to raw bytes for BLOB storage."""
        if vector is not None:
            self.embedding = vector.astype(np.float32).tobytes()
        else:
            self.embedding = None

    def get_embedding(self) -> Optional[np.ndarray]:
        """Deserialize raw bytes back into a 1D NumPy float32 array."""
        if self.embedding:
            return np.frombuffer(self.embedding, dtype=np.float32)
        return None

    def __repr__(self) -> str:
        return f"<VideoMemory(video_id={self.video_id}, style_id={self.style_id}, v={self.extraction_version})>"


class StyleReference(Base):
    """
    STYLE_REFERENCE entity (Section 21 of description.txt).
    Associates reference videos with a style, including their relative creative relevance.
    """

    __tablename__ = "style_references"

    id = Column(Integer, primary_key=True, autoincrement=True)
    style_id = Column(String(64), ForeignKey("styles.style_id"), index=True, nullable=False)
    video_id = Column(String(64), ForeignKey("videos.video_id"), index=True, nullable=False)
    relevance = Column(Float, default=1.0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relational associations
    style = relationship("Style", back_populates="references")
    video = relationship("Video", back_populates="references")

    def __repr__(self) -> str:
        return f"<StyleReference(style={self.style_id}, video={self.video_id}, relevance={self.relevance})>"


class Script(Base):
    """
    SCRIPT entity.
    Stores original comedic screenplays generated in a creator's style based on a user premise.
    Maintains permanent history for the user and creator.
    """

    __tablename__ = "scripts"

    script_id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=True, index=True)
    style_id = Column(String(64), ForeignKey("styles.style_id"), index=True, nullable=False)
    premise = Column(Text, nullable=False)
    script_text = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relational associations
    user = relationship("User", back_populates="scripts")
    style = relationship("Style", back_populates="scripts")

    def __repr__(self) -> str:
        return f"<Script(id={self.script_id}, style={self.style_id})>"

