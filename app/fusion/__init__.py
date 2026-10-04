"""
app/fusion/__init__.py
Multimodal fusion and speaker resolver package (Phase 0.3 Capstone).
"""

from app.fusion.timeline_aligner import TimelineAligner
from app.fusion.speaker_resolver import SpeakerResolver
from app.fusion.consensus import SpeechConsensus

__all__ = ["TimelineAligner", "SpeakerResolver", "SpeechConsensus"]
