"""
app/ingestion/queue.py
Concurrency-controlled background ingestion queue.

Implements the hybrid processing model:
- Processes incoming video URLs concurrently using a bounded thread pool (default concurrency=2)
  to maximize throughput while safely avoiding Gemini 429 rate limits.
- Advances each video through Phase 1 Ingestion -> Phase 2 Extraction -> Phase 3 Memory Indexing.
- Automatically triggers a single batch Style Bible synthesis once all items are indexed.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional
from app.core.config import console, settings
from app.extraction.gemini_extractor import GeminiExtractor
from app.ingestion.service import IngestionService
from app.memory.service import MemoryService
from app.style.service import StyleService


@dataclass
class BatchResult:
    """Container tracking the results of a concurrent batch upload."""

    total: int
    succeeded: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    style_id: str = "default_style"
    style_bible_version: Optional[int] = None


class IngestionQueue:
    """
    Queue orchestrating concurrent video ingestion with bounded parallel workers.
    """

    def __init__(
        self,
        max_workers: int = 2,
        ingestion_service: Optional[IngestionService] = None,
        extractor: Optional[GeminiExtractor] = None,
        memory_service: Optional[MemoryService] = None,
        style_service: Optional[StyleService] = None,
    ):
        self.max_workers = max_workers
        self.ingestion_service = ingestion_service or IngestionService()
        self.extractor = extractor
        self.memory_service = memory_service or MemoryService()
        self.style_service = style_service or StyleService()

    def process_single_video(self, source: str, style_id: str) -> str:
        """
        Advance an individual video through Ingestion -> Extraction -> Memory Indexing.
        """
        # 1. Phase 1 Ingestion
        res = self.ingestion_service.ingest(source=source)
        video_id = res.video_id

        # 2. Phase 2 Extraction (if needed)
        archive_path = settings.extractions_dir / f"{video_id}_v1.json"
        if not archive_path.is_file() or res.status == "stored":
            if not self.extractor:
                self.extractor = GeminiExtractor()
            self.extractor.extract(video_id=video_id)

        # 3. Phase 3 Memory Distillation & Vector Indexing
        self.memory_service.distill_and_index_video(video_id=video_id, style_id=style_id)

        return video_id

    def process_batch(
        self,
        sources: List[str],
        style_id: str = "default_style",
        auto_synthesize: bool = True,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ) -> BatchResult:
        """
        Process multiple video sources concurrently with max_workers.

        Args:
            sources: List of URLs or video file paths.
            style_id: Creator style identifier.
            auto_synthesize: If True, executes 1 batch Style Bible synthesis after completion.
            progress_callback: Optional callback(current, total, video_id).

        Returns:
            BatchResult summarizing completed video IDs and failures.
        """
        clean_sources = [s.strip() for s in sources if s.strip() and not s.startswith("#")]
        result = BatchResult(total=len(clean_sources), style_id=style_id)

        if not clean_sources:
            return result

        console.print(
            f"\n[bold cyan][INGESTION QUEUE][/bold cyan] Starting batch of {len(clean_sources)} videos "
            f"for style '[green]{style_id}[/green]' (Concurrency: {self.max_workers})..."
        )

        completed_count = 0
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_src = {
                executor.submit(self.process_single_video, src, style_id): src
                for src in clean_sources
            }

            for future in as_completed(future_to_src):
                src = future_to_src[future]
                completed_count += 1
                try:
                    vid_id = future.result()
                    result.succeeded.append(vid_id)
                    console.print(
                        f"[bold green]✓ [{completed_count}/{len(clean_sources)}][/bold green] "
                        f"Indexed [cyan]{vid_id}[/cyan]"
                    )
                    if progress_callback:
                        progress_callback(completed_count, len(clean_sources), vid_id)
                except Exception as exc:
                    result.failed.append(src)
                    console.print(
                        f"[bold red]✗ [{completed_count}/{len(clean_sources)}] Failed {src}:[/bold red] {exc}"
                    )

        # Execute single batch Style Bible synthesis if requested and videos succeeded
        if auto_synthesize and result.succeeded:
            console.print("\n[bold cyan][INGESTION QUEUE][/bold cyan] Triggering batch Style Bible synthesis...")
            try:
                style_record = self.style_service.synthesize_style(style_id=style_id)
                result.style_bible_version = style_record.version
            except Exception as synth_exc:
                console.print(f"[bold red]Batch Style Synthesis encountered an error:[/bold red] {synth_exc}")

        return result

