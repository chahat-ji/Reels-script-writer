"""
app/capabilities/faces/__init__.py
Registration hook for Face & Active Speaker Tracking providers (Sub-Phase 3.3).
"""

from app.core.registry import registry
from app.capabilities.faces.providers.mediapipe import MediaPipeFaceProvider

registry.register("faces", "mediapipe", MediaPipeFaceProvider)
