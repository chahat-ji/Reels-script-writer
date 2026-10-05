"""
batch_process.py
Creator DNA & Script Synthesis Engine: Unified Batch & Pipeline Processor.

Process modes:
  1. Single Target (URL, Video file, or Reel ID):
     Processes that specific reel through the complete end-to-end pipeline.
     Usage:
       python batch_process.py "https://www.instagram.com/reel/C8xYz123456/"
       python batch_process.py DdMkWeaxKTT
       python batch_process.py path/to/video.mp4 --local

  2. All Reels (--all):
     Discovers and processes/upgrades all reels in data/reels/.
     Usage:
       python batch_process.py --all
       python batch_process.py --all --local
       python batch_process.py --all --force
       python batch_process.py --all --export-videos

Complete Pipeline Phases:
  - Step 1: Ingestion & Audio Normalization (16kHz mono WAV + media_specs.json)
  - Step 2: Preflight Audio Analysis & Execution Planning (condition_report.json + plan.json)
  - Step 3: Multi-Lane AI Capabilities:
      - Shots (pyscenedetect)
      - OCR (rapidocr)
      - Faces & Active Speaker MAR (mediapipe)
      - Speech ASR (AssemblyAI / MLX Whisper)
      - Speaker Diarization (PyAnnote / AssemblyAI)
  - Step 4: Multimodal Consensus & Timeline Fusion (timeline.json + Pacing DNA)
  - Step 5: Comparison Dashboard & Report (timeline_report.html)
  - Step 6 (Optional): Annotated Debug Video (annotated_debug.mp4)
"""

import argparse
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def inspect_reel_status(reel_dir: Path, profile_name: str = "default") -> Dict[str, Any]:
    """Inspects which phase manifests exist for a given reel directory and profile."""
    profile = config.get_profile(profile_name)
    speech_prov = profile.get("speech", "assemblyai")
    diar_prov = profile.get("diarization", "pyannote")

    has_video = (reel_dir / "video.mp4").exists()
    has_audio = (reel_dir / "audio.wav").exists()
    has_specs = (reel_dir / "media_specs.json").exists()
    has_plan = (reel_dir / "plan.json").exists()

    has_shots = any(reel_dir.glob("manifest_shots_*.json"))
    has_ocr = any(reel_dir.glob("manifest_ocr_*.json"))
    has_faces = any(reel_dir.glob("manifest_faces_*.json"))

    # Check provider-specific speech manifest matching the active profile
    has_speech_target = any(reel_dir.glob(f"manifest_speech_{speech_prov}_*.json"))
    
    # Check diarization manifest
    has_diar_target = any(reel_dir.glob(f"manifest_diarization_{diar_prov}_*.json")) or any(reel_dir.glob("manifest_diarization_*.json"))

    has_timeline = (reel_dir / "timeline.json").exists()
    has_report = (reel_dir / "timeline_report.html").exists()
    has_debug_video = (reel_dir / "annotated_debug.mp4").exists()
    
    # Ground truth presence
    has_gold = (reel_dir / "ground_truth.json").exists() or (Path("data/gold") / reel_dir.name / "ground_truth.json").exists()

    is_complete = all([
        has_video, has_audio, has_specs, has_plan,
        has_shots, has_ocr, has_faces,
        has_speech_target, has_diar_target,
        has_timeline, has_report,
    ])

    return {
        "video": has_video,
        "audio": has_audio,
        "specs": has_specs,
        "plan": has_plan,
        "shots": has_shots,
        "ocr": has_ocr,
        "faces": has_faces,
        "speech": has_speech_target,
        "speech_prov": speech_prov,
        "diarization": has_diar_target,
        "diar_prov": diar_prov,
        "timeline": has_timeline,
        "report": has_report,
        "gold": has_gold,
        "debug_video": has_debug_video,
        "is_complete": is_complete,
    }


def upgrade_reel(
    reel_id: str,
    profile_name: str = "default",
    force: bool = False,
    generate_html: bool = True,
    export_video: bool = False,
    auto_open: bool = False,
    data_root: str = "data",
) -> bool:
    """
    Executes the complete end-to-end pipeline for a single reel, ensuring all
    parameters and phase outputs are computed up to current progress.
    """
    reel_dir = Path(data_root) / "reels" / reel_id
    if not reel_dir.exists():
        console.print(f"[bold red]Reel directory not found: {reel_dir}[/bold red]")
        return False

    status = inspect_reel_status(reel_dir, profile_name=profile_name)
    console.print(f"\n[bold cyan]▶ Processing Reel:[/bold cyan] [green]{reel_id}[/green] [dim]({profile_name})[/dim]")

    video_path = reel_dir / "video.mp4"
    audio_path = reel_dir / "audio.wav"

    # Step 1: Ingestion & Container Specs
    if not video_path.exists():
        console.print(f"[red]Missing video.mp4 in {reel_dir}. Cannot proceed.[/red]")
        return False

    if not audio_path.exists() or not status["specs"]:
        console.print("[dim]Extracting missing normalized 16kHz audio & media specs...[/dim]")
        ingest_media(str(video_path), data_root=data_root)

    # Step 2: Preflight & Plan check
    if not status["plan"] or force:
        console.print("[dim]Generating audio condition profile & execution plan.json...[/dim]")
        condition = analyze_audio_condition(audio_path, reel_id)
        create_execution_plan(condition, profile_name=profile_name, data_root=data_root)

    profile = config.get_profile(profile_name)
    speech_prov = profile.get("speech", "assemblyai")

    # Step 3: Multi-Lane AI Capabilities (All parameters)
    # 3.1 Shots (Scene Detection)
    if not status["shots"] or force:
        console.print("[dim]Running PySceneDetect shot boundary detection...[/dim]")
        shot_prov_cls = registry.get("shots", "pyscenedetect")
        if shot_prov_cls:
            runner.execute(reel_id, shot_prov_cls(), {"video_path": str(video_path)}, force=force)

    # 3.2 OCR (On-Screen Text)
    if not status["ocr"] or force:
        console.print("[dim]Running RapidOCR visual text & hook extraction...[/dim]")
        ocr_prov_cls = registry.get("ocr", "rapidocr")
        if ocr_prov_cls:
            runner.execute(reel_id, ocr_prov_cls(), {"video_path": str(video_path)}, force=force)

    # 3.3 Faces & Active Speaker MAR
    if not status["faces"] or force:
        console.print("[dim]Running MediaPipe face tracking & mouth aspect ratio (MAR)...[/dim]")
        face_prov_cls = registry.get("faces", "mediapipe")
        if face_prov_cls:
            runner.execute(reel_id, face_prov_cls(), {"video_path": str(video_path)}, force=force)

    # 3.4 Speech ASR
    if not status["speech"] or force:
        console.print(f"[dim]Running speech transcription ({speech_prov})...[/dim]")
        speech_chain = [speech_prov]
        if speech_prov == "assemblyai":
            speech_chain.append("mlx_whisper")
        runner.execute_chain(reel_id, "speech", speech_chain, {"audio_path": str(audio_path)}, force=force)

    # 3.5 Speaker Diarization
    if not status["diarization"] or force:
        console.print("[dim]Running speaker diarization...[/dim]")
        diar_chain = ["pyannote"] if profile_name in ("local_only", "local") else ["pyannote", "assemblyai"]
        runner.execute_chain(reel_id, "diarization", diar_chain, {"audio_path": str(audio_path)}, force=force)

    # Step 4: Multimodal Consensus & Timeline Fusion
    # Re-align if timeline missing, forced, or previous step updated manifests
    timeline_path = reel_dir / "timeline.json"
    if not timeline_path.exists() or force or not status["is_complete"]:
        console.print("[dim]Aligning multimodal consensus timeline & computing Pacing DNA...[/dim]")
        aligner = TimelineAligner(data_root=data_root)
        aligner.align(reel_id)

    # Step 5: Comparison Dashboard & Report
    if generate_html:
        report_path = reel_dir / "timeline_report.html"
        if not report_path.exists() or force or not status["is_complete"]:
            console.print("[dim]Generating interactive comparison dashboard...[/dim]")
            generate_report_for_reel(reel_id, auto_open=auto_open)

    # Step 6 (Optional): Annotated Debug Video
    if export_video and (not status["debug_video"] or force):
        console.print("[dim]Exporting annotated debug video (.mp4)...[/dim]")
        export_annotated_video(reel_id, auto_open=auto_open)

    console.print(f"[bold green]✓ {reel_id} pipeline complete and verified![/bold green]")
    return True


def process_target(
    target: str,
    profile_name: str = "default",
    force: bool = False,
    generate_html: bool = True,
    export_video: bool = False,
    auto_open: bool = False,
    data_root: str = "data",
) -> bool:
    """
    Ingests and processes a single target (URL, file path, or reel ID)
    through the complete pipeline.
    """
    console.print(Panel.fit(
        f"[bold cyan]Single Target Pipeline Processing[/bold cyan]\n"
        f"Target: [green]{target}[/green]\n"
        f"Profile: [yellow]{profile_name}[/yellow] | Force Recompute: [magenta]{force}[/magenta]",
        title="🎬 PROCESS TARGET",
        border_style="cyan",
    ))

    # Resolve Reel ID: check if existing in data/reels first
    existing_dir = Path(data_root) / "reels" / target
    if existing_dir.exists() and (existing_dir / "video.mp4").exists():
        reel_id = target
    else:
        # URL or video file path: ingest first
        console.print("[cyan]Ingesting media and probing container specs...[/cyan]")
        media = ingest_media(target, data_root=data_root)
        reel_id = media.reel_id

    return upgrade_reel(
        reel_id=reel_id,
        profile_name=profile_name,
        force=force,
        generate_html=generate_html,
        export_video=export_video,
        auto_open=auto_open,
        data_root=data_root,
    )


def batch_process_all(
    profile_name: str = "default",
    force: bool = False,
    export_videos: bool = False,
    auto_open: bool = False,
    data_root: str = "data",
):
    """Processes/upgrades all reels currently in data/reels/."""
    reels_dir = Path(data_root) / "reels"
    if not reels_dir.exists():
        console.print(f"[bold red]Reels directory not found: {reels_dir}[/bold red]")
        sys.exit(1)

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
        title="🔄 BATCH PROCESS ALL REELS",
        border_style="cyan",
    ))

    # Initial Inventory Status Scan Table
    initial_table = Table(title="Initial Reel Inventory Status")
    initial_table.add_column("Reel ID", style="cyan")
    initial_table.add_column("Shots", justify="center")
    initial_table.add_column("OCR", justify="center")
    initial_table.add_column("Faces", justify="center")
    initial_table.add_column("Speech", justify="center")
    initial_table.add_column("Diarization", justify="center")
    initial_table.add_column("Timeline", justify="center")
    initial_table.add_column("Report", justify="center")
    initial_table.add_column("Gold Ref", justify="center")
    initial_table.add_column("Phase State", style="magenta")

    def mark(val: bool) -> str:
        return "[green]✓[/green]" if val else "[red]✗[/red]"

    for r_id in targets:
        st = inspect_reel_status(reels_dir / r_id, profile_name=profile_name)
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
            mark(st["gold"]),
            phase_state,
        )

    console.print(initial_table)

    # Execute complete pipeline on each reel
    success_count = 0
    for idx, r_id in enumerate(targets, 1):
        console.rule(f"[{idx}/{len(targets)}] {r_id}")
        ok = upgrade_reel(
            reel_id=r_id,
            profile_name=profile_name,
            force=force,
            generate_html=True,
            export_video=export_videos,
            auto_open=auto_open,
            data_root=data_root,
        )
        if ok:
            success_count += 1

    console.print(Panel.fit(
        f"[bold green]✓ Batch process complete![/bold green]\n"
        f"Successfully verified & processed: [bold cyan]{success_count} / {len(targets)}[/bold cyan] reels.",
        title="🎉 BATCH FINISHED",
        border_style="green",
    ))


def main():
    parser = argparse.ArgumentParser(
        description="Creator DNA & Script Synthesis Engine: Simplified Batch & Pipeline Processor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single reel URL or local file through the complete pipeline:
  python batch_process.py "https://www.instagram.com/reel/C8xYz123456/"
  python batch_process.py path/to/video.mp4
  python batch_process.py DdMkWeaxKTT

  # Process all reels in data/reels/:
  python batch_process.py --all

  # Process all reels using 100% local Apple Silicon profile ($0 cost):
  python batch_process.py --all --local

  # Force recompute all stages for all reels:
  python batch_process.py --all --force
        """,
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Reel URL, local video file path, or existing reel_id to process. If omitted, specify --all to process all reels.",
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Process all reels in data/reels/",
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
        help="Force re-running all pipeline lanes even if manifests already exist",
    )
    parser.add_argument(
        "--export-videos",
        "--export-video",
        action="store_true",
        dest="export_video",
        help="Also export annotated debug videos (.mp4) for processed reels",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Auto-open the generated HTML comparison dashboard in default browser",
    )

    args = parser.parse_args()

    # Determine profile
    profile = "local_only" if (args.local or args.profile == "local") else args.profile

    # Validate arguments: either target or --all must be given
    if not args.target and not args.all:
        console.print("[yellow]Please provide a target (URL, file path, or reel ID) or specify '--all'.[/yellow]")
        console.print("[dim]Examples:[/dim]")
        console.print("  python batch_process.py <reel_url | file_path | reel_id>")
        console.print("  python batch_process.py --all")
        console.print("  python batch_process.py --all --local")
        sys.exit(1)

    try:
        if args.target:
            # Single target mode
            process_target(
                target=args.target,
                profile_name=profile,
                force=args.force,
                generate_html=True,
                export_video=args.export_video,
                auto_open=args.open,
            )
        elif args.all:
            # Batch all mode
            batch_process_all(
                profile_name=profile,
                force=args.force,
                export_videos=args.export_video,
                auto_open=args.open,
            )
    except KeyboardInterrupt:
        console.print("\n[yellow]Processing cancelled by user.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]Fatal error during pipeline processing:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
