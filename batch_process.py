"""
batch_process.py
Batch processing service: Scans and upgrades existing reels to the latest pipeline phases.

Checks all reels in data/reels/ (or specified IDs) and brings older phase data up to date:
  - Ingestion & Audio Normalization (Phase 1)
  - Preflight & Execution Plan (Phase 1)
  - Scene Cut & Pacing Detection (Phase 3.1)
  - On-Screen OCR & Hook Extraction (Phase 3.2)
  - Face Tracking & Active Speaker MAR (Phase 3.3)
  - Speech Transcription & Diarization (Phase 2 & Phase 3.4)
  - Master Multimodal Consensus & timeline.json Fusion (Phase 3.5)
  - Interactive HTML Timeline Dashboard (Option 1)
  - Annotated Debug Videos (Option 2, optional)

Usage:
  # Check status and upgrade all reels in data/reels/ to current pipeline state
  python batch_process.py

  # Upgrade all reels using local-only profile (MLX Whisper, $0 cost)
  python batch_process.py --local

  # Update specific reels only
  python batch_process.py DdMkWeaxKTT DeEKAEKhx_Z

  # Force re-running all lanes across all reels even if cached
  python batch_process.py --force

  # Batch export annotated debug videos for all reels
  python batch_process.py --export-videos
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

os.environ["MPLCONFIGDIR"] = "/tmp"

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Capability auto-registration
import app.capabilities
from app.core.config import config
from app.core.registry import registry
from app.core.runner import runner
from app.core.preflight import analyze_audio_condition
from app.core.router import create_execution_plan
from app.ingestion.coordinator import ingest_media
from app.fusion.timeline_aligner import TimelineAligner
from tools.generate_timeline_report import generate_report_for_reel
from tools.export_annotated_video import export_annotated_video

console = Console()


def inspect_reel_status(reel_dir: Path) -> Dict[str, bool]:
    """Inspects which phase manifests exist for a given reel directory."""
    has_video = (reel_dir / "video.mp4").exists()
    has_audio = (reel_dir / "audio.wav").exists()
    has_specs = (reel_dir / "media_specs.json").exists()
    has_plan = (reel_dir / "plan.json").exists()
    
    has_shots = any(reel_dir.glob("manifest_shots_*.json"))
    has_ocr = any(reel_dir.glob("manifest_ocr_*.json"))
    has_faces = any(reel_dir.glob("manifest_faces_*.json"))
    has_speech = any(reel_dir.glob("manifest_speech_*.json"))
    has_diarization = any(reel_dir.glob("manifest_diarization_*.json"))
    has_timeline = (reel_dir / "timeline.json").exists()
    has_report = (reel_dir / "timeline_report.html").exists()
    has_debug_video = (reel_dir / "annotated_debug.mp4").exists()

    is_complete = all([
        has_video, has_audio, has_specs, has_plan,
        has_shots, has_ocr, has_faces, has_speech,
        has_diarization, has_timeline, has_report,
    ])

    return {
        "video": has_video,
        "audio": has_audio,
        "specs": has_specs,
        "plan": has_plan,
        "shots": has_shots,
        "ocr": has_ocr,
        "faces": has_faces,
        "speech": has_speech,
        "diarization": has_diarization,
        "timeline": has_timeline,
        "report": has_report,
        "debug_video": has_debug_video,
        "is_complete": is_complete,
    }


def upgrade_reel(
    reel_id: str,
    profile_name: str = "default",
    force: bool = False,
    generate_html: bool = True,
    export_video: bool = False,
    data_root: str = "data",
) -> bool:
    """Brings a single reel up to date with the latest pipeline phases."""
    reel_dir = Path(data_root) / "reels" / reel_id
    if not reel_dir.exists():
        console.print(f"[bold red]Reel directory not found: {reel_dir}[/bold red]")
        return False

    status = inspect_reel_status(reel_dir)
    console.print(f"\n[bold cyan]▶ Updating Reel:[/bold cyan] [green]{reel_id}[/green]")

    video_path = reel_dir / "video.mp4"
    audio_path = reel_dir / "audio.wav"

    # Step 1: Ingestion check
    if not video_path.exists():
        console.print(f"[red]Missing video.mp4 in {reel_dir}. Cannot proceed.[/red]")
        return False

    if not audio_path.exists() or not status["specs"]:
        console.print("[dim]Extracting missing normalized audio & specs...[/dim]")
        ingest_media(str(video_path), data_root=data_root)

    # Step 2: Preflight & Plan check
    if not status["plan"] or force:
        console.print("[dim]Updating preflight profile & plan.json...[/dim]")
        condition = analyze_audio_condition(audio_path, reel_id)
        create_execution_plan(condition, profile_name=profile_name, data_root=data_root)

    profile = config.get_profile(profile_name)
    speech_prov = profile.get("speech", "assemblyai")
    diar_prov = profile.get("diarization", "pyannote")

    # Step 3: Multi-Lane Capabilities
    # 3.1 Shots
    if not status["shots"] or force:
        shot_prov_cls = registry.get("shots", "pyscenedetect")
        if shot_prov_cls:
            runner.execute(reel_id, shot_prov_cls(), {"video_path": str(video_path)}, force=force)

    # 3.2 OCR
    if not status["ocr"] or force:
        ocr_prov_cls = registry.get("ocr", "rapidocr")
        if ocr_prov_cls:
            runner.execute(reel_id, ocr_prov_cls(), {"video_path": str(video_path)}, force=force)

    # 3.3 Faces
    if not status["faces"] or force:
        face_prov_cls = registry.get("faces", "mediapipe")
        if face_prov_cls:
            runner.execute(reel_id, face_prov_cls(), {"video_path": str(video_path)}, force=force)

    # 3.4 Speech
    if not status["speech"] or force:
        speech_chain = [speech_prov]
        if speech_prov == "assemblyai":
            speech_chain.append("mlx_whisper")
        runner.execute_chain(reel_id, "speech", speech_chain, {"audio_path": str(audio_path)}, force=force)

    # 3.5 Diarization
    if not status["diarization"] or force:
        diar_chain = ["pyannote"] if profile_name in ("local_only", "local") else ["pyannote", "assemblyai"]
        runner.execute_chain(reel_id, "diarization", diar_chain, {"audio_path": str(audio_path)}, force=force)

    # Step 4: Multimodal Fusion check
    if not status["timeline"] or force or not status["is_complete"]:
        console.print("[dim]Re-aligning multimodal timeline...[/dim]")
        aligner = TimelineAligner(data_root=data_root)
        aligner.align(reel_id)

    # Step 5: HTML Report check
    if generate_html and (not status["report"] or force or not status["is_complete"]):
        generate_report_for_reel(reel_id, auto_open=False)

    # Optional: Debug Video
    if export_video and (not status["debug_video"] or force):
        export_annotated_video(reel_id, auto_open=False)

    console.print(f"[bold green]✓ {reel_id} is up to date![/bold green]")
    return True


def batch_process(
    reel_ids: Optional[List[str]] = None,
    profile_name: str = "default",
    force: bool = False,
    export_videos: bool = False,
    data_root: str = "data",
):
    reels_dir = Path(data_root) / "reels"
    if not reels_dir.exists():
        console.print(f"[bold red]Reels directory not found: {reels_dir}[/bold red]")
        sys.exit(1)

    # Discover target reels
    if reel_ids:
        targets = reel_ids
    else:
        targets = [
            d.name for d in sorted(reels_dir.iterdir())
            if d.is_dir() and not d.name.startswith(".")
        ]

    if not targets:
        console.print("[yellow]No reels found in data/reels/[/yellow]")
        return

    console.print(Panel.fit(
        f"[bold cyan]Creator DNA & Script Synthesis Engine[/bold cyan]\n"
        f"Batch Target: [green]{len(targets)} reels[/green] in [white]{reels_dir}[/white]\n"
        f"Profile: [yellow]{profile_name}[/yellow] | Force Recompute: [magenta]{force}[/magenta]",
        title="🔄 BATCH PROCESS & UPGRADE",
        border_style="cyan",
    ))

    # Initial Status Scan Table
    initial_table = Table(title="Initial Reel Inventory Status")
    initial_table.add_column("Reel ID", style="cyan")
    initial_table.add_column("Shots", justify="center")
    initial_table.add_column("OCR", justify="center")
    initial_table.add_column("Faces", justify="center")
    initial_table.add_column("Speech", justify="center")
    initial_table.add_column("Diarization", justify="center")
    initial_table.add_column("Timeline", justify="center")
    initial_table.add_column("Report", justify="center")
    initial_table.add_column("Phase State", style="magenta")

    def mark(val: bool) -> str:
        return "[green]✓[/green]" if val else "[red]✗[/red]"

    for r_id in targets:
        st = inspect_reel_status(reels_dir / r_id)
        phase_state = "[bold green]Up to Date[/bold green]" if st["is_complete"] else "[yellow]Needs Upgrade[/yellow]"
        initial_table.add_row(
            r_id,
            mark(st["shots"]),
            mark(st["ocr"]),
            mark(st["faces"]),
            mark(st["speech"]),
            mark(st["diarization"]),
            mark(st["timeline"]),
            mark(st["report"]),
            phase_state,
        )

    console.print(initial_table)

    # Process each reel
    success_count = 0
    for idx, r_id in enumerate(targets, 1):
        console.rule(f"[{idx}/{len(targets)}] {r_id}")
        ok = upgrade_reel(
            reel_id=r_id,
            profile_name=profile_name,
            force=force,
            generate_html=True,
            export_video=export_videos,
            data_root=data_root,
        )
        if ok:
            success_count += 1

    # Final summary
    console.print(Panel.fit(
        f"[bold green]✓ Batch process complete![/bold green]\n"
        f"Successfully verified & upgraded: [bold cyan]{success_count} / {len(targets)}[/bold cyan] reels.",
        title="🎉 BATCH FINISHED",
        border_style="green",
    ))


def main():
    parser = argparse.ArgumentParser(
        description="Creator DNA & Script Synthesis Engine: Batch Reel Upgrader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "reels",
        nargs="*",
        help="Optional list of specific reel IDs to process. If omitted, scans all reels in data/reels/",
    )
    parser.add_argument(
        "--profile",
        "-p",
        default="default",
        choices=["default", "local_only", "local"],
        help="Execution profile from config/profiles.yaml (default: 'default', 'local_only': 100%% local free)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Convenience shortcut for --profile local_only (uses MLX Whisper + PyAnnote, $0 cost)",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force re-running all capability lanes even if cached manifests exist",
    )
    parser.add_argument(
        "--export-videos",
        action="store_true",
        help="Also export annotated debug videos (.mp4) for all processed reels",
    )

    args = parser.parse_args()

    profile = "local_only" if (args.local or args.profile == "local") else args.profile

    try:
        batch_process(
            reel_ids=args.reels if args.reels else None,
            profile_name=profile,
            force=args.force,
            export_videos=args.export_videos,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Batch processing cancelled by user.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]Fatal error during batch processing:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
