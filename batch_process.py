"""
batch_process.py
Creator DNA & Script Synthesis Engine: Clean & Minimal Pipeline Processor.

Two Entry Points Only:
  1. Single Reel:
       python batch_process.py <url | reel_id>
  2. All Reels:
       python batch_process.py --all

In both modes, it checks what is missing on disk and executes only the missing pipeline phases:
  - Step 1: Media Ingestion & 16kHz Audio Normalization (video.mp4, audio.wav, media_specs.json)
  - Step 2: Preflight Audio Analysis & Execution Planning (condition_report.json, plan.json)
  - Step 3: Multi-Lane AI Manifests:
      - Shots: PySceneDetect (manifest_shots_pyscenedetect_*.json)
      - OCR: RapidOCR (manifest_ocr_rapidocr_*.json)
      - Faces & MAR: MediaPipe (manifest_faces_mediapipe_*.json)
      - Speech Cloud: AssemblyAI (manifest_speech_assemblyai_*.json)
      - Speech Local: MLX Whisper (manifest_speech_mlx_whisper_*.json)
      - Diarization: AssemblyAI / PyAnnote (manifest_diarization_*.json)
  - Step 4: Multimodal Consensus Timeline (timeline.json + Pacing DNA)
  - Step 5: Comparison Dashboard & Report (timeline_report.html)
"""

import argparse
import os
import sys
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
from tools.dashboard import generate_dashboard

console = Console()


def inspect_reel_status(reel_dir: Path) -> Dict[str, Any]:
    """
    Inspects which pipeline manifests and outputs exist on disk for a given reel directory.
    Explicitly tracks both Cloud (AssemblyAI) and Local (MLX Whisper) speech engines.
    """
    has_video = (reel_dir / "video.mp4").exists()
    has_audio = (reel_dir / "audio.wav").exists()
    has_specs = (reel_dir / "media_specs.json").exists()
    has_plan = (reel_dir / "plan.json").exists()

    has_shots = any(reel_dir.glob("manifest_shots_*.json"))
    has_ocr = any(reel_dir.glob("manifest_ocr_*.json"))
    has_faces = any(reel_dir.glob("manifest_faces_*.json"))

    # Explicit differentiation between Cloud (AssemblyAI) and Local (MLX Whisper)
    has_speech_cloud = any(reel_dir.glob("manifest_speech_assemblyai_*.json"))
    has_speech_local = any(reel_dir.glob("manifest_speech_mlx_whisper_*.json"))

    # Diarization tracking
    has_diarization = any(reel_dir.glob("manifest_diarization_*.json"))

    has_timeline = (reel_dir / "timeline.json").exists()
    has_gold = (reel_dir / "ground_truth.json").exists() or (Path("data/gold") / reel_dir.name / "ground_truth.json").exists()

    is_complete = all([
        has_video, has_audio, has_specs, has_plan,
        has_shots, has_ocr, has_faces,
        has_speech_cloud, has_speech_local,
        has_diarization,
        has_timeline,
    ])

    return {
        "video": has_video,
        "audio": has_audio,
        "specs": has_specs,
        "plan": has_plan,
        "shots": has_shots,
        "ocr": has_ocr,
        "faces": has_faces,
        "speech_cloud": has_speech_cloud,
        "speech_local": has_speech_local,
        "diarization": has_diarization,
        "timeline": has_timeline,
        "gold": has_gold,
        "is_complete": is_complete,
    }


def process_reel(reel_id: str, data_root: str = "data") -> bool:
    """
    Checks what pipeline stages are missing for reel_id and executes only the missing steps.
    Ensures both Cloud (AssemblyAI) and Local (MLX Whisper) speech manifests are generated.
    """
    reel_dir = Path(data_root) / "reels" / reel_id
    if not reel_dir.exists():
        console.print(f"[bold red]Reel directory not found: {reel_dir}[/bold red]")
        return False

    status = inspect_reel_status(reel_dir)
    console.print(f"\n[bold cyan]▶ Checking Reel Pipeline:[/bold cyan] [green]{reel_id}[/green]")

    video_path = reel_dir / "video.mp4"
    audio_path = reel_dir / "audio.wav"

    if not video_path.exists():
        console.print(f"[red]Missing video.mp4 in {reel_dir}. Cannot proceed.[/red]")
        return False

    # Step 1: Missing normalized audio or media specs
    if not audio_path.exists() or not status["specs"]:
        console.print("[dim]Extracting missing normalized 16kHz audio & media specs...[/dim]")
        ingest_media(str(video_path), data_root=data_root)

    # Step 2: Missing preflight plan
    if not status["plan"]:
        console.print("[dim]Generating missing audio condition profile & execution plan.json...[/dim]")
        condition = analyze_audio_condition(audio_path, reel_id)
        create_execution_plan(condition, profile_name="default", data_root=data_root)

    # Step 3: Multi-Lane Capabilities (Run only what is missing)
    # 3.1 Shots
    if not status["shots"]:
        console.print("[dim]Running missing PySceneDetect shot boundary detection...[/dim]")
        shot_prov_cls = registry.get("shots", "pyscenedetect")
        if shot_prov_cls:
            runner.execute(reel_id, shot_prov_cls(), {"video_path": str(video_path)})

    # 3.2 OCR
    if not status["ocr"]:
        console.print("[dim]Running missing RapidOCR visual text extraction...[/dim]")
        ocr_prov_cls = registry.get("ocr", "rapidocr")
        if ocr_prov_cls:
            runner.execute(reel_id, ocr_prov_cls(), {"video_path": str(video_path)})

    # 3.3 Faces & MAR
    if not status["faces"]:
        console.print("[dim]Running missing MediaPipe face tracking & mouth aspect ratio...[/dim]")
        face_prov_cls = registry.get("faces", "mediapipe")
        if face_prov_cls:
            runner.execute(reel_id, face_prov_cls(), {"video_path": str(video_path)})

    # 3.4 Speech - Cloud (AssemblyAI)
    if not status["speech_cloud"]:
        console.print("[dim]Running missing Cloud speech transcription (AssemblyAI)...[/dim]")
        speech_aai_cls = registry.get("speech", "assemblyai")
        if speech_aai_cls:
            runner.execute(reel_id, speech_aai_cls(), {"audio_path": str(audio_path)})

    # 3.5 Speech - Local (MLX Whisper)
    if not status["speech_local"]:
        console.print("[dim]Running missing Local speech transcription (MLX Whisper)...[/dim]")
        speech_mlx_cls = registry.get("speech", "mlx_whisper")
        if speech_mlx_cls:
            runner.execute(reel_id, speech_mlx_cls(), {"audio_path": str(audio_path)})

    # 3.6 Diarization
    if not status["diarization"]:
        console.print("[dim]Running missing speaker diarization...[/dim]")
        diar_chain = ["pyannote", "assemblyai"]
        runner.execute_chain(reel_id, "diarization", diar_chain, {"audio_path": str(audio_path)})

    # Step 4: Multimodal Consensus Timeline
    # Re-align if timeline missing or any upstream capability was freshly computed
    timeline_path = reel_dir / "timeline.json"
    if not timeline_path.exists() or not status["is_complete"]:
        console.print("[dim]Aligning multimodal consensus timeline & computing Pacing DNA...[/dim]")
        aligner = TimelineAligner(data_root=data_root)
        aligner.align(reel_id)

    # Step 5: Update Central Dashboard
    generate_dashboard(initial_reel_id=reel_id, data_root=data_root)

    console.print(f"[bold green]✓ {reel_id} is up to date and verified![/bold green]")
    return True


def process_target(target: str, data_root: str = "data") -> bool:
    """
    Ingests and processes a single target (URL or existing reel_id) through the pipeline.
    """
    console.print(Panel.fit(
        f"[bold cyan]Processing Single Target[/bold cyan]\n"
        f"Target: [green]{target}[/green]",
        title="🎬 BATCH PROCESSOR",
        border_style="cyan",
    ))

    existing_dir = Path(data_root) / "reels" / target
    if existing_dir.exists() and (existing_dir / "video.mp4").exists():
        reel_id = target
    else:
        console.print("[cyan]Ingesting media and probing container specs...[/cyan]")
        media = ingest_media(target, data_root=data_root)
        reel_id = media.reel_id

    return process_reel(reel_id=reel_id, data_root=data_root)


def process_all(data_root: str = "data") -> bool:
    """Discovers and processes all reels in data/reels/."""
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
        return False

    console.print(Panel.fit(
        f"[bold cyan]Creator DNA & Script Synthesis Engine[/bold cyan]\n"
        f"Batch Target: [green]{len(targets)} reels[/green] in [white]{reels_dir}[/white]",
        title="🔄 BATCH PROCESS ALL REELS",
        border_style="cyan",
    ))

    # Initial Inventory Status Scan Table
    initial_table = Table(title="Initial Reel Inventory Status")
    initial_table.add_column("Reel ID", style="cyan")
    initial_table.add_column("Shots", justify="center")
    initial_table.add_column("OCR", justify="center")
    initial_table.add_column("Faces", justify="center")
    initial_table.add_column("Speech (Cloud)", justify="center")
    initial_table.add_column("Speech (Local)", justify="center")
    initial_table.add_column("Diarization", justify="center")
    initial_table.add_column("Timeline", justify="center")
    initial_table.add_column("Gold Ref", justify="center")
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
            mark(st["speech_cloud"]),
            mark(st["speech_local"]),
            mark(st["diarization"]),
            mark(st["timeline"]),
            mark(st["gold"]),
            phase_state,
        )

    console.print(initial_table)

    success_count = 0
    for idx, r_id in enumerate(targets, 1):
        console.rule(f"[{idx}/{len(targets)}] {r_id}")
        ok = process_reel(reel_id=r_id, data_root=data_root)
        if ok:
            success_count += 1

    console.print(Panel.fit(
        f"[bold green]✓ Batch process complete![/bold green]\n"
        f"Successfully verified & processed: [bold cyan]{success_count} / {len(targets)}[/bold cyan] reels.",
        title="🎉 BATCH FINISHED",
        border_style="green",
    ))
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Creator DNA Pipeline Processor: Single Target or All Reels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage:
  1. Process a single reel (URL, file path, or reel ID):
     python batch_process.py "https://www.instagram.com/reel/C8xYz123456/"
     python batch_process.py DdMkWeaxKTT

  2. Process all reels:
     python batch_process.py --all
        """,
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Reel URL or reel ID to process. Omit when using --all.",
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Process all reels in data/reels/",
    )

    args = parser.parse_args()

    # Enforce strictly: either target OR --all
    if args.target and args.all:
        console.print("[bold red]Error:[/bold red] Specify either a target OR '--all', not both.")
        sys.exit(1)

    if not args.target and not args.all:
        console.print("[yellow]Please provide a target (URL / reel ID) or specify '--all'.[/yellow]")
        console.print("[dim]Examples:[/dim]")
        console.print("  python batch_process.py <url | reel_id>")
        console.print("  python batch_process.py --all")
        sys.exit(1)

    try:
        if args.target:
            process_target(target=args.target)
        elif args.all:
            process_all()
    except KeyboardInterrupt:
        console.print("\n[yellow]Processing cancelled by user.[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[bold red]Fatal error during processing:[/bold red] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
