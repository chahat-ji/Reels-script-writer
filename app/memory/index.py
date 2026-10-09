"""
app/memory/index.py
Vector embedding and in-memory semantic similarity search using pure NumPy.

Implements Sections 10 & 21 of description.txt:
- Generates 768-dimensional float32 embeddings using Gemini text-embedding-004.
- Stores embeddings in SQLite as raw float32 BLOBs (zero external vector DB).
- Implements vectorized cosine similarity search across style memories:
  similarity = (q · M^T) / (||q|| · ||M||)
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import numpy as np
from google import genai
from google.genai import types

from app.core.config import console, settings
from app.core.database import get_db_session
from app.models.schema import VideoMemory, StyleReference


@dataclass
class MemoryMatch:
    """Result container for a semantic vector search match."""
    video_id: str
    style_id: str
    score: float
    memory_text: str
    metadata: Dict[str, Any]


class EmbeddingClient:
    """
    Client for generating semantic vector embeddings via Gemini text-embedding-004.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        client: Optional[genai.Client] = None,
    ):
        self.model_name = model_name or settings.embedding_model
        if client:
            self.client = client
        else:
            resolved_key = api_key or settings.get_gemini_api_key()
            self.client = genai.Client(api_key=resolved_key)

    def embed_text(self, text: str) -> np.ndarray:
        """
        Generate a 768-dimensional float32 vector embedding for input text.

        Args:
            text: Input string to embed (Video Memory Markdown or premise query).

        Returns:
            1D NumPy array with dtype float32.
        """
        clean_text = text.strip()
        if not clean_text:
            raise ValueError("Cannot compute embedding for empty text string.")

        config = types.EmbedContentConfig(output_dimensionality=768)
        response = self.client.models.embed_content(
            model=self.model_name,
            contents=clean_text,
            config=config,
        )

        if not response.embeddings or not response.embeddings[0].values:
            raise RuntimeError(f"No embedding values returned by {self.model_name}.")

        values = response.embeddings[0].values
        return np.array(values, dtype=np.float32)


class VectorRetriever:
    """
    Vector search retriever operating directly on SQLite BLOBs using vectorized NumPy.
    """

    def __init__(self, embed_client: Optional[EmbeddingClient] = None):
        self.embed_client = embed_client or EmbeddingClient()

    def search_memories(
        self,
        query: str,
        style_id: str = "default_style",
        top_k: int = 5,
    ) -> List[MemoryMatch]:
        """
        Retrieve the top-K most semantically relevant Video Memories for a query.

        Args:
            query: Creative premise or search query.
            style_id: Style namespace filter.
            top_k: Maximum number of ranked results to return.

        Returns:
            List of MemoryMatch items sorted by cosine similarity descending.
        """
        # 1. Compute query vector
        query_vec = self.embed_client.embed_text(query)
        q_norm_val = np.linalg.norm(query_vec)
        if q_norm_val > 0:
            query_vec = query_vec / q_norm_val

        # 2. Fetch all memories for the style from SQLite
        with get_db_session() as session:
            memories = (
                session.query(VideoMemory)
                .filter(VideoMemory.style_id == style_id, VideoMemory.embedding.isnot(None))
                .all()
            )

            if not memories:
                return []

            # 3. Stack memory embeddings into 2D matrix M
            vectors = []
            records = []
            for mem in memories:
                vec = mem.get_embedding()
                if vec is not None and vec.size > 0:
                    vectors.append(vec)
                    records.append(mem)

            if not vectors:
                return []

            M = np.vstack(vectors).astype(np.float32)  # Shape: (N, D)

            # 4. Vectorized cosine similarity
            # M_norms shape: (N, 1)
            M_norms = np.linalg.norm(M, axis=1, keepdims=True)
            M_norms[M_norms == 0] = 1e-10
            M_norm = M / M_norms

            # Cosine similarity dot product: (N, D) · (D,) -> (N,)
            scores = np.dot(M_norm, query_vec)

            # 5. Top-K ranking
            top_indices = np.argsort(scores)[::-1][:top_k]

            results = []
            for idx in top_indices:
                matched_record = records[idx]
                score = float(scores[idx])
                results.append(
                    MemoryMatch(
                        video_id=matched_record.video_id,
                        style_id=matched_record.style_id,
                        score=score,
                        memory_text=matched_record.memory_text or "",
                        metadata=matched_record.metadata_json or {},
                    )
                )

            return results
