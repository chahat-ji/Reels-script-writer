"""
app/capabilities/shots/__init__.py
Registration hook for Shot Boundary Detection providers.
"""

from app.core.registry import registry
from app.capabilities.shots.providers.pyscenedetect import PySceneDetectProvider

registry.register("shots", "pyscenedetect", PySceneDetectProvider)
