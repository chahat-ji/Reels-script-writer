"""
app/capabilities/speech/__init__.py
Auto-registration for all Speech providers.
"""

from app.core.registry import registry
from app.capabilities.speech.providers.assemblyai import AssemblyAISpeechProvider
from app.capabilities.speech.providers.mlx_whisper import MLXWhisperProvider

# Register AssemblyAI (Paid API)
registry.register("speech", AssemblyAISpeechProvider.name, AssemblyAISpeechProvider)

# Register MLX Whisper (Local Apple Silicon)
registry.register("speech", MLXWhisperProvider.name, MLXWhisperProvider)

# Auto-register shots capability providers
import app.capabilities.shots