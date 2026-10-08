"""
main.py
Primary entry point for the Video-to-Style Script Generation system.

Takes a single Instagram Reel URL (or local video path) without requiring any flags,
and executes it through the pipeline:
1. Video download (yt-dlp)
2. Audio extraction (ffmpeg)
3. SHA-256 duplicate detection
4. Permanent object storage placement
5. SQLite catalog registration

This entry point will automatically invoke subsequent pipeline phases
(Gemini multimodal extraction, memory distillation, script generation)
as they are implemented.
"""

import sys
from pathlib import Path
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

from app.core.config import console
from app.core.database import init_db
from app.ingestion.service import IngestionService


def run_pipeline(source: str, style_id: str = "default_style") -> None:
    """
    Execute a single video source through the current pipeline level.
    """
    console.print(
        Panel.fit(
            f"[bold cyan]Video-to-Style Pipeline[/bold cyan]\n"
            f"[yellow]Source:[/yellow] {source}\n"
            f"[yellow]Target Style:[/yellow] {style_id}",
            border_style="cyan",
            title="🎬 Video Intake",
        )
    )

    # Ensure database schema is initialized
    init_db()

    # Step 1: Ingestion & Storage Pipeline
    ingestion_service = IngestionService()
    result = ingestion_service.ingest(source=source, style_id=style_id)

    # Render summary table of the ingestion result
    table = Table(title="Pipeline Ingestion Summary", border_style="green")
    table.add_column("Property", style="bold white", width=18)
    table.add_column("Value", style="cyan")

    table.add_row("Video ID", result.video_id)
    table.add_row("Duplicate Status", "[yellow]DUPLICATE (Skipped)[/yellow]" if result.is_duplicate else "[green]NEW ASSET (Stored)[/green]")
    table.add_row("SHA-256 Fingerprint", result.sha256)
    table.add_row("Permanent Video URI", result.storage_uri)
    table.add_row("Permanent Audio URI", result.audio_uri or "[dim]N/A[/dim]")
    table.add_row("Duration (ms)", str(result.duration_ms) if result.duration_ms else "[dim]Unknown[/dim]")
    table.add_row("Pipeline Level", f"[bold green]{result.status.upper()} (Phase 1 Ready)[/bold green]")
    table.add_row("Status Message", result.message)

    console.print(table)

    # Note: Phase 2 (Gemini Video Extraction) will be invoked here upon approval:
    # extractor = GeminiExtractor()
    # extraction = extractor.extract(result.video_id)


def main():
    """
    CLI Entrypoint.
    Accepts URL directly via argument: python main.py <url>
    Or prompts interactively if run without arguments.
    """
    if len(sys.argv) > 1:
        # User passed URL or path directly as first argument
        source = sys.argv[1].strip()
    else:
        # Interactive prompt if no arguments were provided
        source = Prompt.ask(
            "[bold cyan]Enter Instagram Reel URL or video file path[/bold cyan]"
        ).strip()

    if not source:
        console.print("[bold red]Error: No video URL or file path provided.[/bold red]")
        sys.exit(1)

    run_pipeline(source=source)


if __name__ == "__main__":
    main()

