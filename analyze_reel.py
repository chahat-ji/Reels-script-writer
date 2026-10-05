"""
analyze_reel.py
Primary Service Entrypoint: End-to-end processing pipeline for new and individual reels.

Executes all pipeline phases up to current progress:
  Phase 1: Ingestion, Container Probing & 16kHz Audio Normalization
  Preflight: Audio Health Profiling & Execution Planning
  Phase 2 & 3 Capabilities:
    - Shots & Pacing (PySceneDetect)
    - On-Screen OCR & Hook Extraction (RapidOCR)
    - Face Tracking & Active Speaker MAR (MediaPipe)
    - Speech Transcription (AssemblyAI Cloud or MLX Whisper Local)
    - Speaker Diarization (PyAnnote Local / AssemblyAI Cloud)
  Phase 3.5: Multimodal Consensus, Speaker-to-Face Resolution & Master timeline.json
  Outputs:
    - Interactive HTML Timeline Dashboard (Option 1)
    - Annotated Debug MP4 Video (Option 2, optional)

Usage:
  # Process an Instagram Reel URL (Default profile: AssemblyAI + PyAnnote)
  python analyze_reel.py "https://www.instagram.com/reel/C8xYz123456/"

  # Process a local MP4 with 100% local profile (MLX Whisper + Apple Silicon, $0.00 cost)
  python analyze_reel.py path/to/my_video.mp4 --local

  # Re-analyze an existing reel and auto-open HTML dashboard
  python analyze_reel.py DdMkWeaxKTT --open

  # Full analysis including annotated debug video export
  python analyze_reel.py DeEKAEKhx_Z --export-video --open
"""

import argparse
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

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


def analyze_reel(
    source: str,
    profile_name: str = "default",
    force: bool = False,
    generate_html: bool = True,
    export_video: bool = False,
    auto_open: bool = False,
    skip_shots: bool = False,
    skip_ocr: bool = False,
    skip_faces: bool = False,
    skip_speech: bool = False,
    skip_diarization: bool = False,
    data_root: str = "data",
) -> Dict[str, Any]:
    """
    Executes end-to-end processing pipeline for a given reel URL, file path, or ID.
    """
    console.print(Panel.fit(
        f"[bold cyan]Creator DNA & Script Synthesis Engine[/bold cyan]\n"
        f"Target Source: [green]{source}[/green]\n"
        f"Profile: [yellow]{profile_name}[/yellow] | Force Re-run: [magenta]{force}[/magenta]",
        title="🎬 ANALYZE REEL",
        border_style="cyan",
    ))

    # ---------------------------------------------------------
    # STEP 1: Ingestion & Normalization (Phase 1)
    # ---------------------------------------------------------
    console.print("\n[bold cyan]▶ STEP 1/5: Media Ingestion & Container Inspection[/bold cyan]")
    
    # Check if target is already an existing reel directory in data/reels
    existing_reel_dir = Path(data_root) / "reels" / source
    if existing_reel_dir.exists() and (existing_reel_dir / "video.mp4").exists():
        reel_id = source
        reel_dir = existing_reel_dir
        video_path = reel_dir / "video.mp4"
        audio_path = reel_dir / "audio.wav"
        console.print(f"[green]✓ Found existing reel run-store: {reel_dir}[/green]")
    else:
        try:
            media = ingest_media(source, data_root=data_root)
            reel_id = media.reel_id
            reel_dir = Path(data_root) / "reels" / reel_id
            video_path = media.video_path
            audio_path = media.audio_path
            console.print(f"[green]✓ Ingestion successful for reel:[/green] [bold white]{reel_id}[/bold white]")
            if media.video_specs:
                console.print(
                    f"  Resolution: {media.video_specs.width}x{media.video_specs.height} | "
                    f"FPS: {media.video_specs.fps} | Duration: {media.video_specs.duration_seconds:.1f}s"
                )
        except Exception as e:
            console.print(f"[bold red]Ingestion failed:[/bold red] {e}")
            raise

    # ---------------------------------------------------------
    # STEP 2: Preflight Profiling & Router Planning (Phase 1)
    # ---------------------------------------------------------
    console.print("\n[bold cyan]▶ STEP 2/5: Preflight Health & Execution Routing[/bold cyan]")
    condition = analyze_audio_condition(audio_path, reel_id)
    plan = create_execution_plan(condition, profile_name=profile_name, data_root=data_root)

    profile = config.get_profile(profile_name)
    max_budget = profile.get("limits", {}).get("max_usd_per_reel", 0.25)

    routing_table = Table(title=f"Execution Plan: {profile_name} (Max Budget: ${max_budget:.2f})")
    routing_table.add_column("Capability", style="cyan")
    routing_table.add_column("Provider", style="magenta")
    routing_table.add_column("Type", style="green")

    speech_prov = profile.get("speech", "assemblyai")
    diar_prov = profile.get("diarization", "pyannote")
    routing_table.add_row("Shots", "pyscenedetect", "Local")
    routing_table.add_row("OCR", "rapidocr", "Local ONNX")
    routing_table.add_row("Faces", "mediapipe", "Local Metal")
    routing_table.add_row("Speech", speech_prov, "Local MLX" if speech_prov == "mlx_whisper" else "Cloud API")
    routing_table.add_row("Diarization", diar_prov, "Local PyAnnote / Cloud Fallback")
    console.print(routing_table)

    # ---------------------------------------------------------
    # STEP 3: Multi-Lane Capability Execution (Phase 2 & Phase 3)
    # ---------------------------------------------------------
    console.print("\n[bold cyan]▶ STEP 3/5: Multi-Modal Lane Execution[/bold cyan]")

    # 3.1 Shot Boundary Detection
    if not skip_shots:
        try:
            shot_prov_cls = registry.get("shots", "pyscenedetect")
            if shot_prov_cls:
                runner.execute(reel_id, shot_prov_cls(), {"video_path": str(video_path)}, force=force)
        except Exception as e:
            console.print(f"[yellow]Warning: Shot detection encountered an issue: {e}[/yellow]")

    # 3.2 On-Screen OCR
    if not skip_ocr:
        try:
            ocr_prov_cls = registry.get("ocr", "rapidocr")
            if ocr_prov_cls:
                runner.execute(reel_id, ocr_prov_cls(), {"video_path": str(video_path)}, force=force)
        except Exception as e:
            console.print(f"[yellow]Warning: OCR detection encountered an issue: {e}[/yellow]")

    # 3.3 Face Tracking & Active Speaker MAR
    if not skip_faces:
        try:
            face_prov_cls = registry.get("faces", "mediapipe")
            if face_prov_cls:
                runner.execute(reel_id, face_prov_cls(), {"video_path": str(video_path)}, force=force)
        except Exception as e:
            console.print(f"[yellow]Warning: Face tracking encountered an issue: {e}[/yellow]")

    # 3.4 Speech Transcription
    if not skip_speech:
        try:
            speech_chain = [speech_prov]
            if speech_prov == "assemblyai":
                speech_chain.append("mlx_whisper")
            runner.execute_chain(reel_id, "speech", speech_chain, {"audio_path": str(audio_path)}, force=force)
        except Exception as e:
            console.print(f"[yellow]Warning: Speech transcription encountered an issue: {e}[/yellow]")

    # 3.5 Speaker Diarization
    if not skip_diarization:
        try:
            if profile_name in ("local_only", "local"):
                diar_chain = ["pyannote"]
            else:
                diar_chain = ["pyannote", "assemblyai"]
            runner.execute_chain(reel_id, "diarization", diar_chain, {"audio_path": str(audio_path)}, force=force)
        except Exception as e:
            console.print(f"[yellow]Warning: Diarization encountered an issue: {e}[/yellow]")

    # ---------------------------------------------------------
    # STEP 4: Multimodal Fusion & Alignment (Phase 3.5)
    # ---------------------------------------------------------
    console.print("\n[bold cyan]▶ STEP 4/5: Multimodal Consensus & Speaker Resolution[/bold cyan]")
    aligner = TimelineAligner(data_root=data_root)
    timeline = aligner.align(reel_id)

    # ---------------------------------------------------------
    # STEP 5: Visual Reports & Artifacts
    # ---------------------------------------------------------
    console.print("\n[bold cyan]▶ STEP 5/5: Generating Output Reports & Artifacts[/bold cyan]")
    html_path = reel_dir / "timeline_report.html"
    video_out_path = reel_dir / "annotated_debug.mp4"

    if generate_html:
        generate_report_for_reel(reel_id, auto_open=False)

    if export_video:
        export_annotated_video(reel_id, auto_open=False)

    # Summary Panel
    console.print(Panel.fit(
        f"[bold green]✓ Pipeline analysis complete for {reel_id}![/bold green]\n\n"
        f"Master Timeline: [cyan]{reel_dir / 'timeline.json'}[/cyan]\n"
        f"HTML Dashboard:  [cyan]{html_path if html_path.exists() else 'Not generated'}[/cyan]\n"
        f"Debug Video:     [cyan]{video_out_path if video_out_path.exists() else 'Not requested'}[/cyan]",
        title="🎉 ANALYSIS FINISHED",
        border_style="green",
    ))

    # Auto-open if requested
    if auto_open:
        if html_path.exists():
            webbrowser.open(f"file://{html_path.resolve()}")
        elif export_video and video_out_path.exists():
            import subprocess
            subprocess.run(["open", str(video_out_path)])

    return timeline


def main():
    parser = argparse.ArgumentParser(
        description="Creator DNA & Script Synthesis Engine: Analyze Reel Entrypoint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "source",
        help="Instagram Reel URL (https://www.instagram.com/reel/...), local video path (.mp4/.mov), or existing reel ID",
    )
    # Support legacy optional audio_path argument if someone runs: python analyze_reel.py <reel_id> <audio_path> [profile]
    parser.add_argument(
        "audio_path_legacy",
        nargs="?",
        default=None,
        help="[Legacy compatibility] Optional path to audio file if passing raw reel_id",
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
        help="Bypass cache and force re-execution of all providers",
    )
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Disable automatic generation of interactive HTML report",
    )
    parser.add_argument(
        "--export-video",
        action="store_true",
        help="Export burn-in annotated debug video (Option 2 .mp4)",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Automatically open generated HTML report or debug video when done",
    )
    parser.add_argument("--skip-shots", action="store_true", help="Skip shot detection lane")
    parser.add_argument("--skip-ocr", action="store_true", help="Skip on-screen OCR lane")
    parser.add_argument("--skip-faces", action="store_true", help="Skip face tracking lane")
    parser.add_argument("--skip-speech", action="store_true", help="Skip speech transcription lane")
    parser.add_argument("--skip-diarization", action="store_true", help="Skip speaker diarization lane")

    args = parser.parse_args()

    # Handle legacy positional profile argument if audio_path_legacy looks like a profile
    profile = args.profile
    if args.audio_path_legacy in ["default", "local_only", "local"]:
        profile = args.audio_path_legacy
    elif args.local or args.profile == "local":
        profile = "local_only"

    try:
        analyze_reel(
            source=args.source,
            profile_name=profile,
            force=args.force,
            generate_html=not args.no_report,
            export_video=args.export_video,
            auto_open=args.open,
            skip_shots=args.skip_shots,
            skip_ocr=args.skip_ocr,
            skip_faces=args.skip_faces,
            skip_speech=args.skip_speech,
            skip_diarization=args.skip_diarization,
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Processing cancelled by user.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]Fatal error during reel analysis:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()