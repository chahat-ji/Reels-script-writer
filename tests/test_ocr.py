"""
tests/test_ocr.py
Verification CLI for Sub-Phase 3.2: On-Screen OCR & Text Extraction.

Usage:
    python tests/test_ocr.py data/reels/DdMkWeaxKTT/video.mp4
    python tests/test_ocr.py DdMkWeaxKTT --fps 4.0 --min-conf 0.65
"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

import app.capabilities  # Auto-registers all capabilities
from app.core.registry import registry
from app.core.runner import runner
from app.ingestion.coordinator import ingest_media

console = Console()


def analyze_ocr(
    target: str,
    sample_fps: float = 3.0,
    min_confidence: float = 0.60,
    similarity_threshold: float = 0.75,
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
        # Try as reel ID
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
        f"[bold cyan]Sub-Phase 3.2: On-Screen OCR on:[/bold cyan] [green]{reel_id}[/green]\n"
        f"[dim]Video: {video_path} | FPS: {sample_fps} | MinConf: {min_confidence}[/dim]"
    ))

    # 2. Resolve provider
    provider_cls = registry.get("ocr", "rapidocr")
    if not provider_cls:
        console.print("[bold red]Error: 'rapidocr' provider not registered for 'ocr'.[/bold red]")
        sys.exit(1)

    provider = provider_cls(
        sample_fps=sample_fps,
        min_confidence=min_confidence,
        similarity_threshold=similarity_threshold,
    )

    # 3. Execute via TaskRunner (idempotent disk caching)
    job = {
        "video_path": str(video_path),
        "sample_fps": sample_fps,
        "min_confidence": min_confidence,
        "similarity_threshold": similarity_threshold,
    }
    result = runner.execute(reel_id, provider, job)

    metrics = result.raw_payload.get("metrics", {})
    total_spans = metrics.get("total_text_spans", len(result.events))
    total_raw = metrics.get("total_raw_detections", 0)
    frames_sampled = metrics.get("frames_sampled", 0)
    coverage_pct = metrics.get("text_coverage_pct", 0.0)
    duration_ms = metrics.get("video_duration_ms", 0)

    # 4. Summary Panel
    summary_table = Table(title="On-Screen OCR Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    summary_table.add_column("Description", style="white")

    summary_table.add_row("Total Text Spans", str(total_spans), "Unique merged text overlays detected")
    summary_table.add_row("Raw OCR Detections", str(total_raw), "Per-frame detections before merging")
    summary_table.add_row("Frames Sampled", str(frames_sampled), f"Frames analyzed at {sample_fps} fps")
    summary_table.add_row("Text Coverage", f"{coverage_pct}%", "% of video duration containing text")
    summary_table.add_row("Video Duration", f"{duration_ms / 1000:.2f}s", "Total video length")
    console.print(summary_table)

    if not result.events:
        console.print("[yellow]⚠ No text overlays detected in this video.[/yellow]")
        console.print(f"[bold green]✓ Manifest saved: data/reels/{reel_id}/manifest_ocr_rapidocr_v1.0.0.json[/bold green]")
        return

    # 5. Text Spans Table
    spans_table = Table(title=f"Detected Text Overlays ({total_spans} spans)")
    spans_table.add_column("#", style="dim", width=4)
    spans_table.add_column("Start", style="yellow", width=8)
    spans_table.add_column("End", style="yellow", width=8)
    spans_table.add_column("Duration", style="magenta", width=10)
    spans_table.add_column("Text", style="white")
    spans_table.add_column("Conf", style="cyan", width=6)
    spans_table.add_column("Frames", style="dim", width=7)

    for i, ev in enumerate(result.events):
        p = ev.payload
        dur_ms = ev.end_ms - ev.start_ms
        text = p.get("text", "")
        # Truncate long text for display
        display_text = text if len(text) <= 60 else text[:57] + "..."
        spans_table.add_row(
            str(i + 1),
            f"{ev.start_ms / 1000:.2f}s",
            f"{ev.end_ms / 1000:.2f}s",
            f"{dur_ms}ms",
            display_text,
            f"{ev.confidence:.2f}",
            str(p.get("frame_count", 1)),
        )

    console.print(spans_table)

    # 6. Hook/CTA analysis
    hook_text_spans = [e for e in result.events if e.start_ms < 3000]
    if hook_text_spans:
        console.print(f"\n[bold yellow]🪝 Hook Text (first 3s):[/bold yellow]")
        for ev in hook_text_spans:
            console.print(f"  [cyan]{ev.start_ms}ms → {ev.end_ms}ms[/cyan]: [white]\"{ev.payload['text']}\"[/white]")

    cta_keywords = {"link", "follow", "subscribe", "comment", "like", "bio", "swipe", "click", "share"}
    cta_spans = [
        e for e in result.events
        if any(kw in e.payload.get("text", "").lower() for kw in cta_keywords)
    ]
    if cta_spans:
        console.print(f"\n[bold magenta]📣 Potential CTA Text:[/bold magenta]")
        for ev in cta_spans:
            console.print(f"  [cyan]{ev.start_ms / 1000:.1f}s[/cyan]: [white]\"{ev.payload['text']}\"[/white]")

    console.print(f"\n[bold green]✓ Verified Sub-Phase 3.2: Manifest saved in data/reels/{reel_id}/[/bold green]")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python tests/test_ocr.py <reel_id_or_video_path> [options][/yellow]")
        console.print("[yellow]Options:[/yellow]")
        console.print("  [dim]--fps <float>       Sample rate (default: 3.0)[/dim]")
        console.print("  [dim]--min-conf <float>  Minimum confidence (default: 0.60)[/dim]")
        console.print("  [dim]--sim <float>       Text similarity merge threshold (default: 0.75)[/dim]")
        console.print("[dim]Example: python tests/test_ocr.py data/reels/DdMkWeaxKTT/video.mp4 --fps 4.0[/dim]")
        sys.exit(1)

    target_video = sys.argv[1]
    fps = 3.0
    conf = 0.60
    sim = 0.75

    if "--fps" in sys.argv:
        idx = sys.argv.index("--fps")
        if idx + 1 < len(sys.argv):
            fps = float(sys.argv[idx + 1])

    if "--min-conf" in sys.argv:
        idx = sys.argv.index("--min-conf")
        if idx + 1 < len(sys.argv):
            conf = float(sys.argv[idx + 1])

    if "--sim" in sys.argv:
        idx = sys.argv.index("--sim")
        if idx + 1 < len(sys.argv):
            sim = float(sys.argv[idx + 1])

    analyze_ocr(target_video, sample_fps=fps, min_confidence=conf, similarity_threshold=sim)
