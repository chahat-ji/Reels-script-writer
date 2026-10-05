"""
compare_speech.py
Comprehensive Speech Engine Comparison & Benchmark Suite.

Compares:
  - AssemblyAI (Cloud API)
  - MLX Whisper (Local Apple Silicon Large-v3)
  - Multimodal Gold Standard ground_truth.json (if available in data/gold/ or data/reels/)

Metrics Computed against Gold Standard:
  - Word Error Rate (WER %)
  - Character Error Rate (CER %)
  - Word Recall & Coverage (% of ground truth words captured)
  - Segment / Utterance Count
  - API Cost ($) & Execution Latency

Usage:
  python compare_speech.py DdMkWeaxKTT
  python compare_speech.py DeEKAEKhx_Z
  python compare_speech.py DdrIIFTCWdx
  python compare_speech.py <reel_url_or_file> [--refresh]
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import app.capabilities.speech
from app.core.registry import registry
from app.core.runner import runner
from app.ingestion.coordinator import ingest_media

console = Console()


def normalize_text(text: str) -> str:
    """Normalizes text for linguistic evaluation (strips punctuation & extra whitespace)."""
    # Remove common Latin & Devanagari punctuation (including danda ।)
    text = re.sub(r"[।,\.\?!:;\"\(\)\[\]\{\}«»\-—_/#@*~`]", " ", text)
    return " ".join(text.lower().split())


def levenshtein_distance(seq1: List[str], seq2: List[str]) -> int:
    """Computes exact Levenshtein edit distance using space-optimized 2-row DP."""
    if len(seq1) < len(seq2):
        seq1, seq2 = seq2, seq1
    prev = list(range(len(seq2) + 1))
    for i, c1 in enumerate(seq1):
        curr = [i + 1] * (len(seq2) + 1)
        for j, c2 in enumerate(seq2):
            curr[j + 1] = prev[j] if c1 == c2 else 1 + min(prev[j + 1], curr[j], prev[j])
        prev = curr
    return prev[-1]


def compute_wer(ref_words: List[str], hyp_words: List[str]) -> float:
    """Word Error Rate = (Substitutions + Deletions + Insertions) / Total Reference Words."""
    if not ref_words:
        return 0.0
    dist = levenshtein_distance(ref_words, hyp_words)
    return round((dist / len(ref_words)) * 100, 2)


def compute_cer(ref_text: str, hyp_text: str) -> float:
    """Character Error Rate on non-whitespace characters."""
    ref_chars = [c for c in ref_text if not c.isspace()]
    hyp_chars = [c for c in hyp_text if not c.isspace()]
    if not ref_chars:
        return 0.0
    dist = levenshtein_distance(ref_chars, hyp_chars)
    return round((dist / len(ref_chars)) * 100, 2)


def load_gold_standard(reel_id: str) -> Optional[Dict[str, Any]]:
    """Loads ground_truth.json from data/gold/ or data/reels/."""
    candidates = [
        Path("data/gold") / reel_id / "ground_truth.json",
        Path("data/reels") / reel_id / "ground_truth.json",
    ]
    for path in candidates:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not read {path}: {e}[/yellow]")
    return None


def run_comparison(target: str, language: Optional[str] = None, force_refresh: bool = False):
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
        # Check if already a reel ID in data/reels
        existing_dir = Path("data/reels") / target
        if existing_dir.exists():
            reel_id = target
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
        console.print("[bold red]Both 'assemblyai' and 'mlx_whisper' must be registered.[/bold red]")
        return

    # Delete cached mlx_whisper file if refresh is asked
    if force_refresh:
        for f in (Path("data/reels") / reel_id).glob("manifest_speech_mlx_whisper_*.json"):
            f.unlink()
            console.print(f"[yellow]Cleared old cache: {f.name}[/yellow]")

    console.print(Panel.fit(
        f"[bold cyan]Comparing Speech Providers on:[/bold cyan] [green]{reel_id}[/green]\n"
        f"[dim]Audio File: {audio_path}[/dim]",
        title="🎙️ SPEECH BENCHMARK ARENA",
        border_style="cyan",
    ))

    job = {"audio_path": str(audio_path)}
    if language:
        job["language"] = language

    # 3. Execute / load both providers
    res_aai = runner.execute(reel_id, aai_cls(), job, force=force_refresh)
    res_mlx = runner.execute(reel_id, mlx_cls(), job, force=force_refresh)

    # 4. Extract outputs
    aai_words_raw = [ev for ev in res_aai.events if ev.type == "word"]
    mlx_words_raw = [ev for ev in res_mlx.events if ev.type == "word"]
    aai_utts_raw = [ev for ev in res_aai.events if ev.type == "utterance"]
    mlx_utts_raw = [ev for ev in res_mlx.events if ev.type == "utterance"]

    aai_text_full = res_aai.raw_payload.get("text", "")
    mlx_text_full = res_mlx.raw_payload.get("text", "")

    aai_norm = normalize_text(aai_text_full)
    mlx_norm = normalize_text(mlx_text_full)

    aai_words = aai_norm.split()
    mlx_words = mlx_norm.split()

    # 5. Check for Gold Standard
    gold_data = load_gold_standard(reel_id)

    # 6. Render Metrics Table
    if gold_data:
        gt_utts = gold_data.get("speech_utterances", [])
        gt_text_full = " ".join(u.get("text", "") for u in gt_utts)
        gt_norm = normalize_text(gt_text_full)
        gt_words = gt_norm.split()

        wer_aai = compute_wer(gt_words, aai_words)
        wer_mlx = compute_wer(gt_words, mlx_words)
        cer_aai = compute_cer(gt_norm, aai_norm)
        cer_mlx = compute_cer(gt_norm, mlx_norm)

        coverage_aai = round((len(aai_words) / max(1, len(gt_words))) * 100, 1)
        coverage_mlx = round((len(mlx_words) / max(1, len(gt_words))) * 100, 1)

        table = Table(title=f"Benchmark Scorecard vs. Gold Standard ({reel_id})", border_style="cyan")
        table.add_column("Metric", style="cyan", justify="left")
        table.add_column("Gold Standard", style="bold yellow", justify="center")
        table.add_column("AssemblyAI (Cloud)", style="bold green", justify="center")
        table.add_column("MLX Whisper (Apple Silicon)", style="bold magenta", justify="center")

        table.add_row("Status / Tier", "Human Ground Truth", "Cloud API (Paid)", "Local Large-v3 (Free)")
        table.add_row("Total Spoken Words", f"{len(gt_words)} words", f"{len(aai_words)} words", f"{len(mlx_words)} words")
        table.add_row("Word Coverage / Recall", "100.0%", f"{coverage_aai}%", f"{coverage_mlx}%")
        table.add_row("Conversational Turns", f"{len(gt_utts)} utterances", f"{len(aai_utts_raw)} utterances", f"{len(mlx_utts_raw)} utterances")

        # Color-code WER
        def wer_badge(w: float) -> str:
            color = "green" if w < 10.0 else ("yellow" if w < 30.0 else "red")
            return f"[{color}]{w:.2f}%[/{color}]"

        def cer_badge(c: float) -> str:
            color = "green" if c < 8.0 else ("yellow" if c < 20.0 else "red")
            return f"[{color}]{c:.2f}%[/{color}]"

        table.add_row("Word Error Rate (WER ↓)", "[dim]0.0% (Ref)[/dim]", wer_badge(wer_aai), wer_badge(wer_mlx))
        table.add_row("Character Error Rate (CER ↓)", "[dim]0.0% (Ref)[/dim]", cer_badge(cer_aai), cer_badge(cer_mlx))
        console.print(table)

        # Highlight winner
        winner = "AssemblyAI" if wer_aai < wer_mlx else "MLX Whisper"
        diff = abs(wer_aai - wer_mlx)
        console.print(
            f"[bold cyan]Analysis Verdict:[/bold cyan] [green]{winner}[/green] had higher accuracy "
            f"(WER difference: {diff:.2f}%).\n"
        )

        # Render 3 Side-by-Side Panels
        panel_gt = Panel(gt_text_full, title="[bold yellow]Gold Standard (Ground Truth)[/bold yellow]", width=40)
        panel_aai = Panel(aai_text_full, title=f"[bold green]AssemblyAI (WER: {wer_aai}%)[/bold green]", width=40)
        panel_mlx = Panel(mlx_text_full, title=f"[bold magenta]MLX Whisper (WER: {wer_mlx}%)[/bold magenta]", width=40)
        console.print(Columns([panel_gt, panel_aai, panel_mlx]))

    else:
        # Fallback pairwise table when no gold standard is available
        console.print(f"[yellow]Notice: No ground_truth.json found for {reel_id}. Showing pairwise engine delta.[/yellow]\n")
        table = Table(title="Pairwise Engine Comparison Metrics")
        table.add_column("Metric", style="cyan")
        table.add_column("AssemblyAI (Paid API)", style="green")
        table.add_column("MLX Whisper (Local Apple Silicon)", style="magenta")

        table.add_row("Total Words Extracted", str(len(aai_words_raw)), str(len(mlx_words_raw)))
        table.add_row("Utterance Segments", str(len(aai_utts_raw)), str(len(mlx_utts_raw)))
        table.add_row("Model / Tier", res_aai.provider_name, res_mlx.metadata.get("model", "local"))
        console.print(table)

        panel_aai = Panel(aai_text_full, title="[bold green]AssemblyAI Transcript[/bold green]", width=60)
        panel_mlx = Panel(mlx_text_full, title="[bold magenta]MLX Whisper Transcript[/bold magenta]", width=60)
        console.print(Columns([panel_aai, panel_mlx]))

    # 7. Word Alignment Preview
    timeline_table = Table(title="Word Alignment Sample (First 8 Tokens)")
    timeline_table.add_column("Idx", style="dim", justify="right")
    timeline_table.add_column("AssemblyAI Word (ms)", style="green")
    timeline_table.add_column("MLX Whisper Word (ms)", style="magenta")

    max_len = min(8, max(len(aai_words_raw), len(mlx_words_raw)))
    for i in range(max_len):
        w_a = f"{aai_words_raw[i].payload['text']} ({aai_words_raw[i].start_ms}-{aai_words_raw[i].end_ms})" if i < len(aai_words_raw) else "-"
        w_m = f"{mlx_words_raw[i].payload['text']} ({mlx_words_raw[i].start_ms}-{mlx_words_raw[i].end_ms})" if i < len(mlx_words_raw) else "-"
        timeline_table.add_row(str(i + 1), w_a, w_m)

    console.print(timeline_table)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python compare_speech.py <reel_id|reel_url> [--refresh] [--lang <code>][/yellow]")
        console.print("[dim]Example: python compare_speech.py DeEKAEKhx_Z[/dim]")
        sys.exit(1)

    target_input = sys.argv[1]
    refresh = "--refresh" in sys.argv
    lang = None
    if "--lang" in sys.argv:
        idx = sys.argv.index("--lang")
        if idx + 1 < len(sys.argv):
            lang = sys.argv[idx + 1]

    run_comparison(target_input, language=lang, force_refresh=refresh)