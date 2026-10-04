"""
app/capabilities/speech/__init__.py
Speech capability package initialization and provider auto-registration.
"""

from app.core.registry import registry
from app.capabilities.speech.providers.assemblyai import AssemblyAISpeechProvider

# Auto-register AssemblyAI
registry.register("speech", AssemblyAISpeechProvider.name, AssemblyAISpeechProvider)