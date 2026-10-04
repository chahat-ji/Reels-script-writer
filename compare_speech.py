"""
compare_speech.py
Direct side-by-side comparison between AssemblyAI and MLX Whisper on any reel.
"""

import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns

import app.capabilities.speech
from app.ingestion.coordinator import ingest_media
from app.core.registry import registry
from app.core.runner import runner

console = Console()


def run_comparison(target: str, language: str = None, force_refresh: bool = False):
    # 1. Resolve Reel ID and audio path
    target_path = Path(target)
    if target_path.exists():
        if target_path.is_file() and target_path.parent.parent.name == "reels":
            reel_id = target_path.parent.name
        elif target_path.is_dir() and target_path.parent.name == "reels":
            reel_id = target_path.name
        else:
            media = ingest_media(target)
            reel_id = media.reel_id
    else:
        media = ingest_media(target)
        reel_id = media.reel_id

    audio_path = Path("data/reels") / reel_id / "audio.wav"
    if not audio_path.exists():
        media = ingest_media(target)
        audio_path = media.audio_path

    # 2. Resolve Providers
    aai_cls = registry.get("speech", "assemblyai")
    mlx_cls = registry.get("speech", "mlx_whisper")

    if not aai_cls or not mlx_cls:
        console.print("[red]Both 'assemblyai' and 'mlx_whisper' must be registered.[/red]")
        return

    # Delete cached mlx_whisper file if refresh is asked
    if force_refresh:
        for f in (Path("data/reels") / reel_id).glob("manifest_speech_mlx_whisper_*.json"):
            f.unlink()
            console.print(f"[yellow]Cleared old cache: {f.name}[/yellow]")

    console.print(Panel.fit(f"[bold cyan]Comparing Speech Providers on:[/bold cyan] [green]{reel_id}[/green]"))

    job = {"audio_path": str(audio_path)}
    if language:
        job["language"] = language

    # 3. Execute both
    res_aai = runner.execute(reel_id, aai_cls(), job)
    res_mlx = runner.execute(reel_id, mlx_cls(), job)

    # 4. Extract word counts and text
    aai_words = [ev for ev in res_aai.events if ev.type == "word"]
    mlx_words = [ev for ev in res_mlx.events if ev.type == "word"]

    aai_text = res_aai.raw_payload.get("text", "")
    mlx_text = res_mlx.raw_payload.get("text", "")

    # 5. Summary Table
    table = Table(title="Provider Comparison Metrics")
    table.add_column("Metric", style="cyan")
    table.add_column("AssemblyAI (Paid API)", style="green")
    table.add_column("MLX Whisper (Local Apple Silicon)", style="magenta")

    table.add_row("Total Words Extracted", str(len(aai_words)), str(len(mlx_words)))
    table.add_row("Model / Tier", res_aai.provider_name, res_mlx.metadata.get("model", "local"))
    console.print(table)

    # 6. Side-by-Side Transcripts
    panel_aai = Panel(aai_text, title="[bold green]AssemblyAI Transcript[/bold green]", width=60)
    panel_mlx = Panel(mlx_text, title="[bold magenta]MLX Whisper Transcript[/bold magenta]", width=60)
    console.print(Columns([panel_aai, panel_mlx]))

    # 7. Alignment preview
    timeline_table = Table(title="First 8 Word Alignments")
    timeline_table.add_column("Idx", style="dim")
    timeline_table.add_column("AssemblyAI Word (ms)", style="green")
    timeline_table.add_column("MLX Whisper Word (ms)", style="magenta")

    max_len = min(8, max(len(aai_words), len(mlx_words)))
    for i in range(max_len):
        w_a = f"{aai_words[i].payload['text']} ({aai_words[i].start_ms}-{aai_words[i].end_ms})" if i < len(aai_words) else "-"
        w_m = f"{mlx_words[i].payload['text']} ({mlx_words[i].start_ms}-{mlx_words[i].end_ms})" if i < len(mlx_words) else "-"
        timeline_table.add_row(str(i + 1), w_a, w_m)

    console.print(timeline_table)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python compare_speech.py <reel_url_or_id> [--lang <code>] [--refresh][/yellow]")
        sys.exit(1)

    target_url = sys.argv[1]
    refresh = "--refresh" in sys.argv
    lang = None
    if "--lang" in sys.argv:
        idx = sys.argv.index("--lang")
        if idx + 1 < len(sys.argv):
            lang = sys.argv[idx + 1]

    run_comparison(target_url, language=lang, force_refresh=refresh)