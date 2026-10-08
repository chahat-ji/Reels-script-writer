"""
batch_process.py
Batch dashboard and processing manager for the Video-to-Style system.

Inspects all video entries in SQLite, displays a comprehensive progress table
showing their pipeline completion levels, and can batch-process pending entries
or external URL list files.
"""

import sys
from pathlib import Path
from typing import List, Optional
from rich.panel import Panel
from rich.table import Table

from app.core.config import console
from app.core.database import get_db_session, init_db
from app.ingestion.service import IngestionService
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
        table.add_column("Ingested At", style="dim", width=20)

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

            created_str = v.created_at.strftime("%Y-%m-%d %H:%M") if v.created_at else "N/A"

            table.add_row(
                v.video_id,
                f"{v.sha256[:10]}...",
                style_display,
                audio_display,
                status_badge,
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


def process_url_file(file_path: Path) -> None:
    """
    Read URLs from a text file (one URL per line) and ingest each one.
    """
    if not file_path.is_file():
        console.print(f"[bold red]Error: File not found: {file_path}[/bold red]")
        return

    urls = [line.strip() for line in file_path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    console.print(f"[bold cyan][BATCH INGESTION][/bold cyan] Found {len(urls)} URLs in {file_path.name}")

    ingestion_service = IngestionService()
    for idx, url in enumerate(urls, 1):
        console.print(f"\n[bold magenta]Processing ({idx}/{len(urls)}):[/bold magenta] {url}")
        try:
            ingestion_service.ingest(source=url)
        except Exception as exc:
            console.print(f"[bold red]Failed to process {url}: {exc}[/bold red]")

    # Refresh dashboard after batch
    console.print("\n[bold green]Batch processing completed. Updated dashboard:[/bold green]")
    display_dashboard()


def main():
    """
    CLI Entrypoint for batch management and status reporting.
    Usage:
        python batch_process.py               -> Shows progress dashboard
        python batch_process.py <urls.txt>    -> Ingests URLs from file and shows dashboard
    """
    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        if target.is_file():
            process_url_file(target)
            return

    # Default action: display progress dashboard
    display_dashboard()


if __name__ == "__main__":
    main()

