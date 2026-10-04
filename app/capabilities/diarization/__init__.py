"""
app/capabilities/diarization/__init__.py
Registration hook for Speaker Diarization providers (Sub-Phase 3.4).
"""

from app.core.registry import registry
from app.capabilities.diarization.providers.pyannote import PyAnnoteDiarizationProvider
from app.capabilities.diarization.providers.assemblyai import AssemblyAIDiarizationProvider

# Register pyannote (local) and assemblyai (cloud/fallback)
registry.register("diarization", "pyannote", PyAnnoteDiarizationProvider)
registry.register("diarization", "assemblyai", AssemblyAIDiarizationProvider)
