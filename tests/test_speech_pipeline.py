"""
test_speech_pipeline.py
End-to-end verification of Ingestion, Preflight, Planning, and Multi-Provider Speech execution.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

import app.capabilities.speech  # Triggers registrations
from app.ingestion.coordinator import ingest_media
from app.core.preflight import analyze_audio_condition
from app.core.router import create_execution_plan
from app.core.runner import runner

console = Console()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python test_speech_pipeline.py <url_or_video> [profile][/yellow]")
        console.print("[dim]Example profiles: 'default' (cloud-first), 'local_only' (zero-cost mlx)[/dim]")
        sys.exit(1)

    target = sys.argv[1]
    profile_name = sys.argv[2] if len(sys.argv) > 2 else "default"

    console.print(Panel.fit(f"[bold green]Running Pipeline (Profile: {profile_name})[/bold green]"))

    # 1. Ingest
    media = ingest_media(target)

    # 2. Preflight
    condition = analyze_audio_condition(media.audio_path, media.reel_id)

    # 3. Plan
    plan = create_execution_plan(condition, profile_name=profile_name)

    # 4. Execute Speech Task Chain
    speech_plan = plan.plans.get("speech")
    if not speech_plan:
        console.print("[red]No speech plan generated.[/red]")
        sys.exit(1)

    result = runner.execute_chain(
        reel_id=media.reel_id,
        capability="speech",
        provider_names=speech_plan.provider_chain,
        job={"audio_path": str(media.audio_path)},
    )

    # 5. Display First 15 Speech Events
    table = Table(title=f"Canonical Speech Events via '{result.provider_name}' (Total: {len(result.events)})")
    table.add_column("Track", style="cyan")
    table.add_column("Type", style="green")
    table.add_column("Time Window", style="yellow")
    table.add_column("Payload", style="white")

    for ev in result.events[:15]:
        table.add_row(
            ev.track,
            ev.type,
            f"{ev.start_ms}ms - {ev.end_ms}ms",
            str(ev.payload),
        )

    console.print(table)
    if len(result.events) > 15:
        console.print(f"[dim]...and {len(result.events) - 15} more events stored in manifest.[/dim]")