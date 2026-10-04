"""
tests/test_faces.py
Verification CLI for Sub-Phase 3.3: Face & Active Speaker Tracking (MediaPipe).

Usage:
    python tests/test_faces.py data/reels/DdMkWeaxKTT/video.mp4
    python tests/test_faces.py DdMkWeaxKTT --fps 5.0 --mar-thresh 0.18
"""

import os
os.environ["MPLCONFIGDIR"] = "/tmp"
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


def analyze_faces(
    target: str,
    sample_fps: float = 5.0,
    mar_thresh: float = 0.18,
):
    # 1. Resolve Reel ID and video path
    target_path = Path(target)
    if target_path.exists():
        if target_path.is_file():
            if target_path.parent.parent.name == "reels":
                reel_id = target_path.parent.name
            else:
                reel_id = target_path.stem
            video_path = target_path
        elif target_path.is_dir() and target_path.parent.name == "reels":
            reel_id = target_path.name
            video_path = target_path / "video.mp4"
        else:
            media = ingest_media(target)
            reel_id = media.reel_id
            video_path = media.video_path
    else:
        # Check as reel ID
        reel_path = Path("data/reels") / target
        if reel_path.exists():
            reel_id = target
            video_path = reel_path / "video.mp4"
        else:
            media = ingest_media(target)
            reel_id = media.reel_id
            video_path = media.video_path

    if not video_path.exists():
        console.print(f"[bold red]Error: Video file not found at {video_path}[/bold red]")
        sys.exit(1)

    console.print(Panel.fit(
        f"[bold cyan]Sub-Phase 3.3: Face & Active Speaker Analysis on:[/bold cyan] [green]{reel_id}[/green]\n"
        f"[dim]Video: {video_path} | FPS: {sample_fps} | MAR Threshold: {mar_thresh}[/dim]"
    ))

    # 2. Resolve Provider
    provider_cls = registry.get("faces", "mediapipe")
    if not provider_cls:
        console.print("[bold red]Error: 'mediapipe' provider not registered for 'faces'.[/bold red]")
        sys.exit(1)

    provider = provider_cls(
        sample_fps=sample_fps,
        speaking_mar_threshold=mar_thresh,
    )

    # 3. Execute via TaskRunner (idempotent disk caching)
    job = {
        "video_path": str(video_path),
        "sample_fps": sample_fps,
        "speaking_mar_threshold": mar_thresh,
    }
    result = runner.execute(reel_id, provider, job)

    metrics = result.raw_payload.get("metrics", {})
    total_tracks = metrics.get("total_face_tracks", len(result.events))
    speaking_tracks = metrics.get("speaking_face_tracks", 0)
    frames_sampled = metrics.get("frames_sampled", 0)
    face_cov = metrics.get("face_coverage_pct", 0.0)
    spk_cov = metrics.get("speaking_coverage_pct", 0.0)
    duration_ms = metrics.get("video_duration_ms", 0)

    # 4. Summary Table
    summary_table = Table(title="Face & Active Speaker Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    summary_table.add_column("Description", style="white")

    summary_table.add_row("Total Face Tracks", str(total_tracks), "Continuous visible face intervals")
    summary_table.add_row("Speaking Face Tracks", str(speaking_tracks), "Face intervals with active mouth movement (MAR)")
    summary_table.add_row("Frames Sampled", str(frames_sampled), f"Frames analyzed at {sample_fps} fps")
    summary_table.add_row("Face On-Screen Coverage", f"{face_cov}%", "% of video duration where a face is visible")
    summary_table.add_row("Active Speech Coverage", f"{spk_cov}%", "% of video duration with visual speech")
    summary_table.add_row("Video Duration", f"{duration_ms / 1000:.2f}s", "Total video length")
    console.print(summary_table)

    if not result.events:
        console.print("[yellow]⚠ No faces detected in this video.[/yellow]")
        console.print(f"[bold green]✓ Manifest saved: data/reels/{reel_id}/manifest_faces_mediapipe_v1.0.0.json[/bold green]")
        return

    # 5. Tracks Breakdown Table
    tracks_table = Table(title=f"Detected Face Tracks ({total_tracks} tracks)")
    tracks_table.add_column("#", style="dim", width=4)
    tracks_table.add_column("Face ID", style="cyan", width=9)
    tracks_table.add_column("Start", style="yellow", width=8)
    tracks_table.add_column("End", style="yellow", width=8)
    tracks_table.add_column("Duration", style="magenta", width=9)
    tracks_table.add_column("Speaking?", style="bold", width=10)
    tracks_table.add_column("Avg MAR", style="white", width=9)
    tracks_table.add_column("Spk Ratio", style="dim", width=10)
    tracks_table.add_column("BBox [y1,x1,y2,x2]", style="dim")

    for i, ev in enumerate(result.events):
        p = ev.payload
        dur_ms = ev.end_ms - ev.start_ms
        is_spk = p.get("is_speaking", False)
        spk_display = "[bold green]YES[/bold green]" if is_spk else "[dim]No[/dim]"
        bbox = p.get("bbox", [])
        bbox_str = f"[{bbox[0]:.2f}, {bbox[1]:.2f}, {bbox[2]:.2f}, {bbox[3]:.2f}]" if len(bbox) == 4 else "-"

        tracks_table.add_row(
            str(i + 1),
            p.get("face_id", f"face_{i}"),
            f"{ev.start_ms / 1000:.2f}s",
            f"{ev.end_ms / 1000:.2f}s",
            f"{dur_ms / 1000:.2f}s",
            spk_display,
            f"{p.get('avg_mar', 0.0):.4f}",
            f"{int(p.get('speaking_ratio', 0.0) * 100)}%",
            bbox_str,
        )

    console.print(tracks_table)

    # 6. Speaker resolver preview
    console.print("\n[bold yellow]🎙️ Fusion Readiness Preview (for Phase 3.5):[/bold yellow]")
    for ev in result.events:
        if ev.payload.get("is_speaking", False):
            console.print(
                f"  Face [cyan]{ev.payload.get('face_id')}[/cyan] is speaking at "
                f"[yellow]{ev.start_ms/1000:.2f}s → {ev.end_ms/1000:.2f}s[/yellow] "
                f"(MAR: [green]{ev.payload.get('avg_mar'):.3f}[/green], "
                f"confidence: [magenta]{ev.confidence:.2f}[/magenta])"
            )

    console.print(f"\n[bold green]✓ Verified Sub-Phase 3.3: Manifest saved in data/reels/{reel_id}/[/bold green]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python tests/test_faces.py <reel_id_or_video_path> [options][/yellow]")
        console.print("  [dim]--fps <float>        Sample rate (default: 5.0)[/dim]")
        console.print("  [dim]--mar-thresh <float> Speaking threshold (default: 0.18)[/dim]")
        console.print("[dim]Example: python tests/test_faces.py DdMkWeaxKTT[/dim]")
        sys.exit(1)

    target_video = sys.argv[1]
    fps = 5.0
    thresh = 0.18

    if "--fps" in sys.argv:
        idx = sys.argv.index("--fps")
        if idx + 1 < len(sys.argv):
            fps = float(sys.argv[idx + 1])

    if "--mar-thresh" in sys.argv:
        idx = sys.argv.index("--mar-thresh")
        if idx + 1 < len(sys.argv):
            thresh = float(sys.argv[idx + 1])

    analyze_faces(target_video, sample_fps=fps, mar_thresh=thresh)
