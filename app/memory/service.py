"""
app/memory/service.py
Memory distillation and indexing orchestrator.

Coordinates transforming compact extractions into Creative Video Memories,
extracting faceted metadata, computing vector embeddings, and persisting
records in SQLite.
"""

from typing import List, Optional
from app.core.config import console, settings
from app.core.database import get_db_session
from app.extraction.archive import load_archived_extraction
from app.memory.index import EmbeddingClient
from app.memory.metadata import extract_memory_metadata
from app.memory.transformer import transform_to_video_memory
from app.models.schema import Video, VideoMemory, StyleReference


class MemoryService:
    """
    High-level service managing Video Memory creation and indexing.
    """

    def __init__(self, embed_client: Optional[EmbeddingClient] = None):
        self.embed_client = embed_client or EmbeddingClient()

    def distill_and_index_video(
        self,
        video_id: str,
        style_id: Optional[str] = None,
    ) -> VideoMemory:
        """
        Distill an extracted video into a Creative Video Memory and index its embedding.

        Args:
            video_id: Target video identifier.
            style_id: Optional style identifier. Defaults to existing reference or 'default_style'.

        Returns:
            Persisted VideoMemory database model instance.
        """
        # 1. Resolve style association and check for existing memory in SQLite
        target_style_id = style_id
        with get_db_session() as session:
            if not target_style_id:
                ref = session.query(StyleReference).filter_by(video_id=video_id).first()
                target_style_id = ref.style_id if ref else "default_style"

            # Superpower Reuse: if video memory and vector already exist, reuse instantly
            existing_memory = session.query(VideoMemory).filter_by(video_id=video_id).first()
            if existing_memory and existing_memory.embedding is not None and existing_memory.memory_text:
                ref = session.query(StyleReference).filter_by(style_id=target_style_id, video_id=video_id).first()
                if not ref:
                    session.add(StyleReference(style_id=target_style_id, video_id=video_id, relevance=1.0))
                    session.commit()
                _ = (existing_memory.video_id, existing_memory.memory_text, existing_memory.embedding)
                session.expunge(existing_memory)
                console.print(
                    f"[bold green][SUPERPOWER REUSE][/bold green] Creative memory and 768-dim embedding "
                    f"already exist for [cyan]{video_id}[/cyan]. Linked to creator '[magenta]{target_style_id}[/magenta]' "
                    f"(0 LLM/embedding tokens)."
                )
                return existing_memory

        # 2. Load canonical extraction
        extraction = load_archived_extraction(video_id)
        if not extraction:
            raise FileNotFoundError(f"No archived extraction found for video: {video_id}")

        console.print(
            f"[bold cyan][MEMORY DISTILLATION][/bold cyan] Transforming "
            f"[yellow]{video_id}[/yellow] into creative Video Memory..."
        )

        # 3. Transform to Markdown & Extract Faceted Metadata
        memory_markdown = transform_to_video_memory(video_id=video_id, extraction=extraction)
        metadata_tags = extract_memory_metadata(extraction=extraction)

        # 4. Compute semantic embedding
        console.print(
            f"[dim]Generating 768-dim vector embedding with {self.embed_client.model_name}...[/dim]"
        )
        embedding_vec = self.embed_client.embed_text(memory_markdown)

        # 5. Persist into SQLite video_memories table
        with get_db_session() as session:
            memory_record = session.query(VideoMemory).filter_by(video_id=video_id).first()
            if not memory_record:
                memory_record = VideoMemory(
                    video_id=video_id,
                    style_id=target_style_id,
                    extraction_version=extraction.v,
                )
                session.add(memory_record)

            memory_record.style_id = target_style_id
            memory_record.memory_text = memory_markdown
            memory_record.metadata_json = metadata_tags
            memory_record.structured_extraction = extraction.model_dump()
            memory_record.set_embedding(embedding_vec)

            # Update parent video status to 'indexed'
            db_video = session.query(Video).filter_by(video_id=video_id).first()
            if db_video:
                db_video.status = "indexed"

            session.flush()
            # Eagerly access fields before session closure to avoid DetachedInstanceError
            _ = (memory_record.video_id, memory_record.memory_text, memory_record.embedding)
            session.expunge(memory_record)

        console.print(
            f"[bold green][INDEXED (Phase 3)][/bold green] Video Memory persisted and indexed "
            f"for [cyan]{video_id}[/cyan] (dim: {len(embedding_vec)})."
        )
        return memory_record

    def distill_and_index_all(self, style_id: Optional[str] = None) -> List[str]:
        """
        Batch distill and index all eligible extracted videos in the library.
        """
        indexed_ids = []
        with get_db_session() as session:
            query = session.query(Video)
            if style_id:
                query = query.join(StyleReference).filter(StyleReference.style_id == style_id)
            videos = query.all()

            for video in videos:
                archive_file = settings.extractions_dir / f"{video.video_id}_v1.json"
                if archive_file.is_file() and video.status in ("extracted", "stored"):
                    indexed_ids.append(video.video_id)

        console.print(
            f"[bold cyan][BATCH INDEXING][/bold cyan] Found {len(indexed_ids)} videos to index."
        )

        completed = []
        for vid in indexed_ids:
            try:
                self.distill_and_index_video(video_id=vid, style_id=style_id)
                completed.append(vid)
            except Exception as exc:
                console.print(f"[bold red]Failed to index {vid}: {exc}[/bold red]")

        return completed
