"""
tests/test_shots.py
Dedicated verification CLI for Sub-Phase 3.1: Shot Boundary Detection & Visual Pacing.
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

import app.capabilities  # Auto-registers capabilities
from app.core.registry import registry
from app.core.runner import runner
from app.ingestion.coordinator import ingest_media

console = Console()


def analyze_shots(target: str, threshold: float = 27.0):
    # 1. Resolve Reel ID and video path
    target_path = Path(target)
    if target_path.exists():
        if target_path.is_file() and target_path.parent.parent.name == "reels":
            reel_id = target_path.parent.name
            video_path = target_path
        elif target_path.is_dir() and target_path.parent.name == "reels":
            reel_id = target_path.name
            video_path = target_path / "video.mp4"
        else:
            media = ingest_media(target)
            reel_id = media.reel_id
            video_path = media.video_path
    else:
        media = ingest_media(target)
        reel_id = media.reel_id
        video_path = media.video_path

    if not video_path.exists():
        console.print(f"[bold red]Error: Video file not found at {video_path}[/bold red]")
        sys.exit(1)

    console.print(Panel.fit(
        f"[bold cyan]Sub-Phase 3.1: Shot Boundary Analysis on:[/bold cyan] [green]{reel_id}[/green]\n"
        f"[dim]Video Path: {video_path} | Threshold: {threshold}[/dim]"
    ))

    # 2. Resolve Provider
    provider_cls = registry.get("shots", "pyscenedetect")
    if not provider_cls:
        console.print("[bold red]Error: 'pyscenedetect' provider not registered for 'shots'.[/bold red]")
        sys.exit(1)

    provider = provider_cls(threshold=threshold)

    # 3. Execute via TaskRunner (with automatic disk caching)
    job = {"video_path": str(video_path), "threshold": threshold}
    result = runner.execute(reel_id, provider, job)

    metrics = result.raw_payload.get("metrics", {})
    total_shots = metrics.get("total_shots", len(result.events))
    total_duration = metrics.get("total_duration_sec", 0.0)
    asd = metrics.get("avg_shot_duration_sec", 0.0)
    hook_shot = metrics.get("hook_shot_duration_sec", 0.0)

    # Pacing Rhythm Evaluation
    if asd < 1.8:
        pacing_style = "[bold red]Rapid-Fire / Hyper-Edited[/bold red] (High stimulus)"
    elif asd <= 3.2:
        pacing_style = "[bold yellow]Dynamic / Conversational[/bold yellow] (Standard short-form)"
    else:
        pacing_style = "[bold green]Cinematic / Relaxed[/bold green] (Long takes)"

    # 4. Summary Table
    summary_table = Table(title="Visual Pacing DNA Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    summary_table.add_column("Description", style="white")

    summary_table.add_row("Total Cuts / Shots", str(total_shots), "Number of detected visual transitions")
    summary_table.add_row("Total Video Duration", f"{total_duration:.2f}s", "Length of analyzed footage")
    summary_table.add_row("Average Shot Duration (ASD)", f"{asd:.2f}s", "Pacing speed metric")
    summary_table.add_row("Hook Shot Duration", f"{hook_shot:.2f}s", "Duration before first visual cut")
    summary_table.add_row("Pacing Classification", pacing_style, "Content visual rhythm category")

    console.print(summary_table)

    # 5. Shot Breakdown Table
    breakdown_table = Table(title=f"Detected Shots & Transitions ({total_shots} Cuts)")
    breakdown_table.add_column("#", style="dim")
    breakdown_table.add_column("Start", style="yellow")
    breakdown_table.add_column("End", style="yellow")
    breakdown_table.add_column("Duration", style="magenta")
    breakdown_table.add_column("Frames", style="dim")

    for i, ev in enumerate(result.events):
        p = ev.payload
        dur_str = f"{p.get('duration_sec', 0.0):.2f}s ({p.get('duration_ms', 0)}ms)"
        frame_str = f"{p.get('start_frame', '-')} -> {p.get('end_frame', '-')}"
        start_sec = f"{ev.start_ms / 1000:.2f}s"
        end_sec = f"{ev.end_ms / 1000:.2f}s"
        breakdown_table.add_row(str(i + 1), start_sec, end_sec, dur_str, frame_str)

    console.print(breakdown_table)
    console.print(f"[bold green]✓ Verified Sub-Phase 3.1: Manifest cached in data/reels/{reel_id}/[/bold green]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python tests/test_shots.py <reel_id_or_video_path> [--threshold <float>][/yellow]")
        console.print("[dim]Example: python tests/test_shots.py data/reels/DdMkWeaxKTT/video.mp4[/dim]")
        sys.exit(1)

    target_video = sys.argv[1]
    th = 27.0
    if "--threshold" in sys.argv:
        idx = sys.argv.index("--threshold")
        if idx + 1 < len(sys.argv):
            th = float(sys.argv[idx + 1])

    analyze_shots(target_video, threshold=th)
