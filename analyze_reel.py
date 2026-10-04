"""
analyze_reel.py
CLI entrypoint to run reel analysis through configured capability providers.
"""

import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

import app.capabilities.speech  # Triggers provider registrations
from app.core.registry import registry
from app.core.config import config
from app.core.runner import runner

console = Console()


def analyze_reel(reel_id: str, audio_path: str, profile_name: str = "default"):
    console.print(Panel.fit(f"[bold cyan]Analyzing Reel:[/bold cyan] [green]{reel_id}[/green] (Profile: [yellow]{profile_name}[/yellow])"))

    profile = config.get_profile(profile_name)
    speech_provider_name = profile.get("speech", "assemblyai")

    provider_cls = registry.get("speech", speech_provider_name)
    if not provider_cls:
        console.print(f"[bold red]Error:[/bold red] Provider '{speech_provider_name}' not registered for capability 'speech'.")
        return

    provider = provider_cls()

    # Estimate before execution
    estimate = provider.estimate({"duration_seconds": 30.0})
    console.print(f"[dim]Estimate -> Expected Time: {estimate.expected_seconds}s | Est. Cost: ${estimate.expected_cost_usd}[/dim]")

    try:
        result = runner.execute(reel_id, provider, {"audio_path": audio_path})
    except Exception as e:
        console.print(f"[bold red]Execution error:[/bold red] {e}")
        return

    # Print summary table
    table = Table(title=f"Extracted Speech Events (Total: {len(result.events)})")
    table.add_column("Type", style="cyan")
    table.add_column("Window (ms)", style="yellow")
    table.add_column("Confidence", style="magenta")
    table.add_column("Payload", style="white")

    # Display first 10 events as a sample
    for event in result.events[:10]:
        table.add_row(
            event.type,
            f"{event.start_ms} - {event.end_ms}",
            f"{event.confidence:.2f}",
            str(event.payload),
        )

    console.print(table)
    if len(result.events) > 10:
        console.print(f"[dim]...and {len(result.events) - 10} more events cached in manifest.[/dim]")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        console.print("[yellow]Usage: python analyze_reel.py <reel_id> <path_to_audio_file> [profile][/yellow]")
        console.print("[dim]Example: python analyze_reel.py sample_01 data/sample.mp3 default[/dim]")
        sys.exit(1)

    r_id = sys.argv[1]
    a_path = sys.argv[2]
    prof = sys.argv[3] if len(sys.argv) > 3 else "default"

    analyze_reel(r_id, a_path, prof)