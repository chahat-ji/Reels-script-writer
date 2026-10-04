"""
tests/test_fusion.py
Verification CLI for Sub-Phase 3.5: Consensus, Speaker Resolver & Multimodal Fusion.

Usage:
    python tests/test_fusion.py DdMkWeaxKTT
    python tests/test_fusion.py DeEKAEKhx_Z
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from app.fusion.timeline_aligner import TimelineAligner

console = Console()


def run_fusion(reel_id: str):
    # Resolve Reel ID
    target_path = Path(reel_id)
    if target_path.exists():
        if target_path.is_dir() and target_path.parent.name == "reels":
            reel_id = target_path.name
        elif target_path.is_file() and target_path.parent.parent.name == "reels":
            reel_id = target_path.parent.name

    reel_dir = Path("data/reels") / reel_id
    if not reel_dir.exists():
        console.print(f"[bold red]Error: Reel folder not found at {reel_dir}[/bold red]")
        sys.exit(1)

    console.print(Panel.fit(
        f"[bold cyan]Sub-Phase 3.5: Multimodal Fusion & Speaker Resolver on:[/bold cyan] [green]{reel_id}[/green]\n"
        f"[dim]Data directory: {reel_dir}[/dim]"
    ))

    aligner = TimelineAligner()
    timeline = aligner.align(reel_id)

    pacing_dna = timeline["pacing_dna"]
    resolved = timeline["resolved_speakers"]
    tracks = timeline["tracks"]

    # 1. Multimodal Evidence DNA Table
    dna_table = Table(title="Multimodal Video DNA Summary")
    dna_table.add_column("Lane / Modality", style="cyan")
    dna_table.add_column("Key Metric", style="green")
    dna_table.add_column("Details", style="white")

    # Pacing
    p = pacing_dna["pacing"]
    dna_table.add_row(
        "Shots & Pacing",
        f"{p.get('total_shots', 0)} cuts | ASD: {p.get('avg_shot_duration_sec', 0)}s",
        f"Hook shot: {p.get('hook_shot_duration_sec', 0)}s",
    )

    # Speech
    sp = pacing_dna["speech"]
    dna_table.add_row(
        "Speech (ASR)",
        f"{sp.get('total_words', 0)} words ({sp.get('words_per_minute', 0)} WPM)",
        f"Primary engine: {sp.get('primary_asr', 'none')}",
    )

    # Visuals (OCR)
    v = pacing_dna["visuals"]
    dna_table.add_row(
        "On-Screen OCR",
        f"{v.get('total_text_overlays', 0)} text overlays",
        f"Text coverage: {v.get('ocr_coverage_pct', 0)}% of video",
    )

    # Visuals (Faces)
    dna_table.add_row(
        "Face Tracking",
        f"{v.get('total_face_tracks', 0)} face tracks",
        f"On-screen: {v.get('face_on_screen_pct', 0)}% | Active speech: {v.get('visual_speech_pct', 0)}%",
    )

    # Speakers
    spk = pacing_dna["speakers"]
    dna_table.add_row(
        "Diarization",
        f"{spk.get('unique_speakers_detected', 0)} acoustic voice clusters",
        f"Speakers: {', '.join(resolved.get('speaker_to_face', {}).keys()) or 'None'}",
    )

    console.print(dna_table)

    # 2. Speaker-to-Face Resolver Table
    resolver_table = Table(title="Acoustic Voice to Visual Face Resolver Matrix")
    resolver_table.add_column("Acoustic Speaker", style="cyan", width=18)
    resolver_table.add_column("Resolved Face", style="magenta", width=16)
    resolver_table.add_column("Status", style="bold", width=14)
    resolver_table.add_column("Total Overlap", style="yellow", width=14)
    resolver_table.add_column("Speaking Overlap", style="green", width=16)
    resolver_table.add_column("Confidence", style="white", width=12)

    details = resolved.get("details", {})
    if not details:
        resolver_table.add_row("No speakers", "-", "[dim]N/A[/dim]", "-", "-", "-")
    else:
        for spk_id, info in details.items():
            face_id = info.get("face_id") or "[dim]Off-Screen[/dim]"
            status = info.get("status", "unknown")
            if status == "matched":
                status_str = "[bold green]MATCHED[/bold green]"
            else:
                status_str = "[yellow]OFF-SCREEN[/yellow]"

            tot_ov = f"{info.get('overlap_ms', 0) / 1000:.2f}s"
            spk_ov = f"{info.get('speaking_overlap_ms', 0) / 1000:.2f}s"
            conf = f"{info.get('confidence', 0.0) * 100:.0f}%"

            resolver_table.add_row(spk_id, face_id, status_str, tot_ov, spk_ov, conf)

    console.print(resolver_table)

    # 3. Synchronized Timeline Preview (First 8 events)
    sample_table = Table(title="Multimodal Timeline Sample (Speech + Resolved Speakers)")
    sample_table.add_column("Time Range", style="yellow", width=16)
    sample_table.add_column("Speaker", style="cyan", width=14)
    sample_table.add_column("Face", style="magenta", width=12)
    sample_table.add_column("Utterance / Text", style="white")

    utterances = tracks.get("speech_utterances", [])
    if utterances:
        for utt in utterances[:8]:
            p = utt.get("payload", {})
            spk_label = p.get("speaker") or "SPEAKER_00"
            face_label = p.get("resolved_face_id") or "[dim]Off-Screen[/dim]"
            time_str = f"{utt['start_ms']/1000:.2f}s → {utt['end_ms']/1000:.2f}s"
            text_str = p.get("text", "")
            preview = text_str if len(text_str) <= 60 else text_str[:57] + "..."
            sample_table.add_row(time_str, spk_label, face_label, preview)
        console.print(sample_table)

    console.print(f"\n[bold green]✓ Sub-Phase 3.5 Complete: timeline.json verified in data/reels/{reel_id}/[/bold green]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python tests/test_fusion.py <reel_id>[/yellow]")
        console.print("[dim]Example: python tests/test_fusion.py DdMkWeaxKTT[/dim]")
        sys.exit(1)

    target_reel = sys.argv[1]
    run_fusion(target_reel)
