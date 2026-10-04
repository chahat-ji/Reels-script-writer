"""
app/capabilities/ocr/__init__.py
Registration hook for On-Screen OCR providers (Sub-Phase 3.2).
"""

from app.core.registry import registry
from app.capabilities.ocr.providers.rapidocr import RapidOCRProvider

registry.register("ocr", "rapidocr", RapidOCRProvider)
