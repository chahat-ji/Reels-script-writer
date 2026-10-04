"""
tests/test_diarization.py
Verification CLI for Sub-Phase 3.4: Dedicated Speaker Diarization.

Supports:
- PyAnnote Audio (local, gated model on HuggingFace)
- AssemblyAI (cloud/cached utterance fallback)
- Automatic fallback chain: pyannote -> assemblyai

Usage:
    python tests/test_diarization.py DdMkWeaxKTT
    python tests/test_diarization.py DeEKAEKhx_Z --provider assemblyai
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


def analyze_diarization(
    target: str,
    preferred_provider: str = "chain",
):
    # 1. Resolve Reel ID and audio path
    target_path = Path(target)
    if target_path.exists():
        if target_path.is_file():
            if target_path.parent.parent.name == "reels":
                reel_id = target_path.parent.name
            else:
                reel_id = target_path.stem
            audio_path = target_path.parent / "audio.wav"
        elif target_path.is_dir() and target_path.parent.name == "reels":
            reel_id = target_path.name
            audio_path = target_path / "audio.wav"
        else:
            media = ingest_media(target)
            reel_id = media.reel_id
            audio_path = media.audio_path
    else:
        # Check as reel ID
        reel_path = Path("data/reels") / target
        if reel_path.exists():
            reel_id = target
            audio_path = reel_path / "audio.wav"
        else:
            media = ingest_media(target)
            reel_id = media.reel_id
            audio_path = media.audio_path

    if not audio_path.exists():
        console.print(f"[bold red]Error: Audio file not found at {audio_path}[/bold red]")
        sys.exit(1)

    console.print(Panel.fit(
        f"[bold cyan]Sub-Phase 3.4: Speaker Diarization on:[/bold cyan] [green]{reel_id}[/green]\n"
        f"[dim]Audio: {audio_path} | Mode: {preferred_provider}[/dim]"
    ))

    job = {"audio_path": str(audio_path), "video_path": str(audio_path.parent / "video.mp4")}

    # 2. Execute via TaskRunner
    if preferred_provider == "chain":
        provider_names = ["pyannote", "assemblyai"]
        result = runner.execute_chain(reel_id, "diarization", provider_names, job)
    else:
        provider_cls = registry.get("diarization", preferred_provider)
        if not provider_cls:
            console.print(f"[bold red]Error: Unknown diarization provider '{preferred_provider}'[/bold red]")
            sys.exit(1)
        provider = provider_cls()
        result = runner.execute(reel_id, provider, job)

    metrics = result.raw_payload.get("metrics", {})
    total_turns = metrics.get("total_speaker_turns", len(result.events))
    unique_speakers = metrics.get("unique_speakers", [])
    speaker_count = metrics.get("speaker_count", len(unique_speakers))
    total_speech_ms = metrics.get("total_speech_duration_ms", 0)

    # 3. Summary Table
    summary_table = Table(title="Speaker Diarization Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    summary_table.add_column("Description", style="white")

    summary_table.add_row("Provider Used", f"{result.provider_name} ({result.provider_version})", "Active diarization engine")
    summary_table.add_row("Unique Speakers", f"{speaker_count} ({', '.join(unique_speakers)})", "Acoustic voice clusters identified")
    summary_table.add_row("Total Speaker Turns", str(total_turns), "Number of conversational speaking turns")
    summary_table.add_row("Total Speech Duration", f"{total_speech_ms / 1000:.2f}s", "Accumulated vocal duration")
    console.print(summary_table)

    if not result.events:
        console.print("[yellow]⚠ No speaker turns detected in this audio.[/yellow]")
        console.print(f"[bold green]✓ Manifest saved: data/reels/{reel_id}/manifest_diarization_{result.provider_name}_v{result.provider_version}.json[/bold green]")
        return

    # 4. Turns Breakdown Table
    turns_table = Table(title=f"Detected Speaker Turns ({total_turns} turns)")
    turns_table.add_column("#", style="dim", width=4)
    turns_table.add_column("Speaker", style="cyan", width=12)
    turns_table.add_column("Start", style="yellow", width=8)
    turns_table.add_column("End", style="yellow", width=8)
    turns_table.add_column("Duration", style="magenta", width=9)
    turns_table.add_column("Utterance / Text Preview", style="white")

    # Colors for distinct speakers
    speaker_colors = ["cyan", "magenta", "yellow", "green", "blue"]

    for i, ev in enumerate(result.events):
        p = ev.payload
        dur_ms = ev.end_ms - ev.start_ms
        spk = p.get("speaker", "UNKNOWN")
        text = p.get("text", "")
        preview_text = text if len(text) <= 55 else text[:52] + "..."

        try:
            spk_idx = int(spk.replace("SPEAKER_", "")) % len(speaker_colors)
            spk_style = speaker_colors[spk_idx]
        except Exception:
            spk_style = "cyan"

        turns_table.add_row(
            str(i + 1),
            f"[{spk_style}]{spk}[/{spk_style}]",
            f"{ev.start_ms / 1000:.2f}s",
            f"{ev.end_ms / 1000:.2f}s",
            f"{dur_ms / 1000:.2f}s",
            preview_text or "[dim](acoustic turn)[/dim]",
        )

    console.print(turns_table)

    # 5. Fusion Readiness Preview
    console.print("\n[bold yellow]🎙️ Fusion Readiness Preview (for Phase 3.5):[/bold yellow]")
    console.print(f"  Ready to correlate {len(unique_speakers)} audio speaker(s) with visual face tracks.")
    console.print(f"[bold green]✓ Verified Sub-Phase 3.4: Manifest saved in data/reels/{reel_id}/[/bold green]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python tests/test_diarization.py <reel_id_or_audio_path> [--provider <chain|pyannote|assemblyai>][/yellow]")
        console.print("[dim]Example: python tests/test_diarization.py DdMkWeaxKTT[/dim]")
        sys.exit(1)

    target_audio = sys.argv[1]
    provider_choice = "chain"

    if "--provider" in sys.argv:
        idx = sys.argv.index("--provider")
        if idx + 1 < len(sys.argv):
            provider_choice = sys.argv[idx + 1]

    analyze_diarization(target_audio, preferred_provider=provider_choice)
