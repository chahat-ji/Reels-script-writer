"""
test_preflight.py
Verify Phase 0: Preflight Inspection & Plan Generation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import app.capabilities.speech  # auto-registers speech providers
from app.ingestion.coordinator import ingest_media
from app.core.preflight import analyze_audio_condition
from app.core.router import create_execution_plan

console = Console()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python test_preflight.py <instagram_url_or_video_path>[/yellow]")
        sys.exit(1)

    target = sys.argv[1]
    
    # 1. Ingestion
    media = ingest_media(target)

    # 2. Preflight Inspection
    condition = analyze_audio_condition(media.audio_path, media.reel_id)

    # 3. Create Execution Plan
    plan = create_execution_plan(condition, profile_name="default")

    # Display Preflight Table
    table = Table(title=f"Preflight Condition Report: {media.reel_id}")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")

    table.add_row("Duration", f"{condition.duration_seconds:.2f}s")
    table.add_row("Average Volume", f"{condition.audio_condition.average_db} dB")
    table.add_row("Silence Ratio", f"{condition.audio_condition.silence_ratio * 100:.1f}%")
    table.add_row("Music Energy Ratio", f"{condition.audio_condition.music_energy_ratio:.2f}")
    table.add_row("Needs Stem Separation", str(condition.audio_condition.needs_stem_separation))
    table.add_row("Active Flags", ", ".join(condition.flags) or "None")

    console.print(table)
    console.print(Panel(str(plan.plans), title="Scheduled Execution Plan"))