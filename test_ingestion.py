"""
test_ingestion.py
Verify Phase 1: Ingestion & Normalization pipeline standalone.
"""

import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from app.ingestion.coordinator import ingest_media

console = Console()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python test_ingestion.py <instagram_url_or_video_file>[/yellow]")
        sys.exit(1)

    target = sys.argv[1]
    console.print(Panel.fit(f"[bold cyan]Running Ingestion Pipeline on:[/bold cyan] {target}"))

    media = ingest_media(target)

    # Display inspection results
    table = Table(title=f"Ingestion Report: {media.reel_id}")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Reel ID", media.reel_id)
    table.add_row("Video File", str(media.video_path))
    table.add_row("Normalized Audio", str(media.audio_path))

    if media.video_specs:
        table.add_row("Video Resolution", f"{media.video_specs.width}x{media.video_specs.height}")
        table.add_row("Video FPS", str(media.video_specs.fps))
        table.add_row("Duration", f"{media.video_specs.duration_seconds:.2f}s")

    table.add_row("Audio Sample Rate", f"{media.audio_specs.sample_rate} Hz")
    table.add_row("Audio Channels", str(media.audio_specs.channels))
    table.add_row("Audio Codec", media.audio_specs.codec)

    console.print(table)
    console.print("[bold green]✓ Phase 1 Ingestion & Normalization complete.[/bold green]")