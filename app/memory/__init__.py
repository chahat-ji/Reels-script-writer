"""
app/memory package
Creative Video Memory distillation, faceted metadata tagging,
and NumPy vector cosine search retrieval.
"""

from app.memory.index import EmbeddingClient, MemoryMatch, VectorRetriever
from app.memory.metadata import extract_memory_metadata
from app.memory.service import MemoryService
from app.memory.transformer import transform_to_video_memory

__all__ = [
    "transform_to_video_memory",
    "extract_memory_metadata",
    "EmbeddingClient",
    "VectorRetriever",
    "MemoryMatch",
    "MemoryService",
]

