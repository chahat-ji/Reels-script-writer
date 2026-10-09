"""
batch_process.py
Batch dashboard, URL ingestion, and pipeline synchronization manager.

Features:
- Progress dashboard displaying pipeline completion levels across all videos.
- Batch ingestion of URL lists from text files.
- Pipeline synchronization flag (--sync / -s) to bring all library videos
  up to the current active pipeline level (Phase 2 Gemini extraction).
"""

import sys
from pathlib import Path
from typing import List, Optional
from rich.panel import Panel
from rich.table import Table

from app.core.config import console, settings
from app.core.database import get_db_session, init_db
from app.extraction.gemini_extractor import GeminiExtractor
from app.ingestion.service import IngestionService
from app.memory.service import MemoryService
from app.models.schema import Video, VideoMemory, StyleReference


def display_dashboard() -> List[Video]:
    """
    Query the SQLite database and display a formatted Rich table
    showing all ingested videos and their current pipeline progression.
    """
    init_db()

    with get_db_session() as session:
        videos = session.query(Video).order_by(Video.created_at.desc()).all()

        if not videos:
            console.print(
                Panel(
                    "[yellow]No videos have been ingested yet.[/yellow]\n"
                    "Run [cyan]python main.py <url>[/cyan] to ingest your first reference video.",
                    title="📊 Pipeline Dashboard",
                    border_style="yellow",
                )
            )
            return []

        table = Table(
            title=f"📊 Reference Library Progress Dashboard ({len(videos)} Total Videos)",
            border_style="cyan",
            header_style="bold magenta",
        )
        table.add_column("Video ID", style="bold cyan", width=14)
        table.add_column("SHA-256", style="dim", width=12)
        table.add_column("Style", style="white", width=14)
        table.add_column("Audio", justify="center", width=8)
        table.add_column("Status / Pipeline Level", width=22)
        table.add_column("Source URL", style="dim", width=30)
        table.add_column("Ingested At", style="dim", width=18)

        stored_count = 0
        extracted_count = 0
        indexed_count = 0

        for v in videos:
            # Check style association
            style_names = [ref.style_id for ref in v.references]
            style_display = ", ".join(style_names) if style_names else "default_style"

            # Check audio
            audio_display = "[green]✓ Yes[/green]" if v.audio_uri else "[red]✗ No[/red]"

            # Check pipeline stage
            if v.status == "indexed":
                status_badge = "[bold green]INDEXED (Phase 3)[/bold green]"
                indexed_count += 1
            elif v.status == "extracted":
                status_badge = "[bold blue]EXTRACTED (Phase 2)[/bold blue]"
                extracted_count += 1
            else:
                status_badge = "[bold yellow]STORED (Phase 1)[/bold yellow]"
                stored_count += 1

            source_display = (v.source_url[:28] + "...") if v.source_url and len(v.source_url) > 30 else (v.source_url or "Local File")
            created_str = v.created_at.strftime("%Y-%m-%d %H:%M") if v.created_at else "N/A"

            table.add_row(
                v.video_id,
                f"{v.sha256[:10]}...",
                style_display,
                audio_display,
                status_badge,
                source_display,
                created_str,
            )

        console.print(table)

        # Print summary statistics
        summary = (
            f"[bold]Total Videos:[/bold] {len(videos)} | "
            f"[bold yellow]Phase 1 Stored:[/bold yellow] {stored_count} | "
            f"[bold blue]Phase 2 Extracted:[/bold blue] {extracted_count} | "
            f"[bold green]Phase 3 Indexed:[/bold green] {indexed_count}"
        )
        console.print(Panel(summary, border_style="dim", title="📈 Pipeline Status Summary"))
        return videos


def sync_all_videos(style_id: Optional[str] = None) -> None:
    """
    Synchronize all stored videos in SQLite to the current active pipeline level.
    Executes Phase 2 Gemini extraction on any videos that are in 'stored' state.
    """
    init_db()
    console.print(
        Panel(
            f"[bold cyan]Synchronizing library videos to current pipeline level (Phase 2 - Gemini Extraction)...[/bold cyan]\n"
            f"[dim]Model: {settings.extraction_model}[/dim]",
            title="🔄 Pipeline Batch Synchronizer",
            border_style="cyan",
        )
    )

    with get_db_session() as session:
        query = session.query(Video)
        if style_id:
            query = query.join(StyleReference).filter(StyleReference.style_id == style_id)
        videos = query.all()

        if not videos:
            console.print("[yellow]No videos found in library to synchronize.[/yellow]")
            return

        # Step A: Identify and run Phase 2 Extraction for videos in 'stored' state
        pending_extraction = [
            v for v in videos
            if v.status == "stored" or not (settings.extractions_dir / f"{v.video_id}_v1.json").is_file()
        ]

        if pending_extraction:
            console.print(f"[bold yellow]Phase 2: {len(pending_extraction)} videos pending extraction...[/bold yellow]")
            extractor = GeminiExtractor()
            for idx, video in enumerate(pending_extraction, 1):
                console.print(
                    f"[bold magenta][PHASE 2: {idx}/{len(pending_extraction)}][/bold magenta] "
                    f"Extracting [bold cyan]{video.video_id}[/bold cyan]..."
                )
                try:
                    extractor.extract(video_id=video.video_id)
                    video.status = "extracted"
                    session.commit()
                except Exception as exc:
                    console.print(f"[bold red]✗ Failed to extract {video.video_id}: {exc}[/bold red]")

        # Step B: Identify and run Phase 3 Memory Indexing for videos in 'extracted' state
        # Refresh video records
        session.expire_all()
        refreshed_videos = query.all()
        pending_indexing = [
            v for v in refreshed_videos
            if v.status in ("extracted", "stored") and (settings.extractions_dir / f"{v.video_id}_v1.json").is_file()
        ]

        if pending_indexing:
            console.print(f"\n[bold green]Phase 3: {len(pending_indexing)} videos pending vector indexing...[/bold green]")
            memory_service = MemoryService()
            for idx, video in enumerate(pending_indexing, 1):
                console.print(
                    f"[bold magenta][PHASE 3: {idx}/{len(pending_indexing)}][/bold magenta] "
                    f"Indexing [bold cyan]{video.video_id}[/bold cyan]..."
                )
                try:
                    memory_service.distill_and_index_video(video_id=video.video_id)
                except Exception as exc:
                    console.print(f"[bold red]✗ Failed to index {video.video_id}: {exc}[/bold red]")

        if not pending_extraction and not pending_indexing:
            console.print("[bold green]✓ All videos are already synchronized to current pipeline level![/bold green]")

    console.print("\n[bold green]Synchronization completed. Updated dashboard:[/bold green]")
    display_dashboard()


def process_url_file(file_path: Path, sync_level: bool = False) -> None:
    """
    Read URLs from a text file (one URL per line) and ingest each one.
    If sync_level is True, also runs extraction on each newly ingested video.
    """
    if not file_path.is_file():
        console.print(f"[bold red]Error: File not found: {file_path}[/bold red]")
        return

    urls = [line.strip() for line in file_path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    console.print(f"[bold cyan][BATCH INGESTION][/bold cyan] Found {len(urls)} URLs in {file_path.name}")

    ingestion_service = IngestionService()
    extractor = GeminiExtractor() if sync_level else None

    for idx, url in enumerate(urls, 1):
        console.print(f"\n[bold magenta]Processing ({idx}/{len(urls)}):[/bold magenta] {url}")
        try:
            res = ingestion_service.ingest(source=url)
            if sync_level and (not res.is_duplicate or res.status != "extracted"):
                console.print(f"[dim]Syncing {res.video_id} to Phase 2 Extraction...[/dim]")
                extractor.extract(video_id=res.video_id)
        except Exception as exc:
            console.print(f"[bold red]Failed to process {url}: {exc}[/bold red]")

    # Refresh dashboard after batch
    console.print("\n[bold green]Batch processing completed. Updated dashboard:[/bold green]")
    display_dashboard()


def main():
    """
    CLI Entrypoint for batch management, status reporting, and synchronization.
    Usage:
        python batch_process.py               -> Shows progress dashboard
        python batch_process.py --sync        -> Syncs all stored videos in DB to current pipeline level
        python batch_process.py -s            -> Shortcut for --sync
        python batch_process.py <urls.txt>    -> Ingests URLs from file
        python batch_process.py <urls.txt> -s -> Ingests URLs from file and syncs them
    """
    args = sys.argv[1:]
    sync_requested = any(arg in ("--sync", "-s", "--sync-all") for arg in args)
    file_args = [arg for arg in args if not arg.startswith("-")]

    if file_args:
        target_file = Path(file_args[0])
        if target_file.is_file():
            process_url_file(target_file, sync_level=sync_requested)
            return

    if sync_requested:
        sync_all_videos()
        return

    # Default action: display progress dashboard
    display_dashboard()


if __name__ == "__main__":
    main()
