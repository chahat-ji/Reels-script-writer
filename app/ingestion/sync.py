"""
app/ingestion/sync.py
Batch dashboard, URL ingestion, and pipeline synchronization manager.

Features:
- Progress dashboard displaying pipeline completion levels across all videos.
- Batch ingestion of URL lists from text files.
- Pipeline synchronization to bring all library videos up to active pipeline level.
- Synthesize Style Bible for target creator style.
"""

from pathlib import Path
import sys
from typing import List, Optional
from rich.panel import Panel
from rich.table import Table

from app.account.service import get_authenticated_user
from app.core.config import console, settings
from app.core.database import get_db_session, init_db
from app.extraction.gemini_extractor import GeminiExtractor
from app.ingestion.service import IngestionService
from app.memory.service import MemoryService
from app.models.schema import Style, StyleReference, User, Video
from app.style.service import StyleService


def display_dashboard(user: Optional[User] = None) -> List[Video]:
    """
    Query SQLite and display a formatted Rich table of all ingested videos
    and their pipeline progression.
    """
    init_db()
    active_user = user or get_authenticated_user()

    console.print(
        f"[bold cyan]👤 Logged in as:[/bold cyan] [bold green]{active_user.username}[/bold green] "
        f"([dim]{active_user.user_id}[/dim])"
    )

    with get_db_session() as session:
        videos = session.query(Video).order_by(Video.created_at.desc()).all()

        if not videos:
            console.print(
                Panel(
                    "[yellow]No videos have been ingested yet.[/yellow]\n"
                    "Run [cyan]python -m app.cli ingest <url>[/cyan] to ingest your first video.",
                    title="📊 Pipeline Dashboard",
                    border_style="yellow",
                )
            )
            return []

        table = Table(
            title=f"📊 Reference Library Progress Dashboard ({len(videos)} Total Videos)",
            border_style="cyan",
            header_style="bold magenta",
        )
        table.add_column("Video ID", style="bold cyan", width=14)
        table.add_column("SHA-256", style="dim", width=12)
        table.add_column("Style", style="white", width=14)
        table.add_column("Audio", justify="center", width=8)
        table.add_column("Status / Pipeline Level", width=22)
        table.add_column("Source URL", style="dim", width=30)
        table.add_column("Ingested At", style="dim", width=18)

        stored_count = 0
        extracted_count = 0
        indexed_count = 0

        for v in videos:
            style_names = [ref.style_id for ref in v.references]
            style_display = ", ".join(style_names) if style_names else "default_style"
            audio_display = "[green]✓ Yes[/green]" if v.audio_uri else "[red]✗ No[/red]"

            if v.status == "indexed":
                status_badge = "[bold green]INDEXED (Phase 3)[/bold green]"
                indexed_count += 1
            elif v.status == "extracted":
                status_badge = "[bold blue]EXTRACTED (Phase 2)[/bold blue]"
                extracted_count += 1
            else:
                status_badge = "[bold yellow]STORED (Phase 1)[/bold yellow]"
                stored_count += 1

            source_display = (
                (v.source_url[:28] + "...")
                if v.source_url and len(v.source_url) > 30
                else (v.source_url or "Local File")
            )
            created_str = v.created_at.strftime("%Y-%m-%d %H:%M") if v.created_at else "N/A"

            table.add_row(
                v.video_id,
                f"{v.sha256[:10]}...",
                style_display,
                audio_display,
                status_badge,
                source_display,
                created_str,
            )

        console.print(table)

        summary = (
            f"[bold]Total Videos:[/bold] {len(videos)} | "
            f"[bold yellow]Phase 1 Stored:[/bold yellow] {stored_count} | "
            f"[bold blue]Phase 2 Extracted:[/bold blue] {extracted_count} | "
            f"[bold green]Phase 3 Indexed:[/bold green] {indexed_count}"
        )
        console.print(Panel(summary, border_style="dim", title="📈 Pipeline Status Summary"))

        styles = session.query(Style).all()
        active_bibles = [f"[bold green]{s.style_id} (v{s.version})[/bold green]" for s in styles if s.bible_text]
        if active_bibles:
            bible_summary = " | ".join(active_bibles)
            console.print(f"[dim]📖 Synthesized Style Bibles (Phase 4): {bible_summary}[/dim]\n")
        else:
            console.print("[dim]📖 Style Bibles: None synthesized yet. Run with --synthesize-style to build.[/dim]\n")

        return videos


def sync_all_videos(style_id: Optional[str] = None, user_id: Optional[str] = None) -> None:
    """
    Synchronize stored videos in SQLite to active pipeline level.
    """
    init_db()

    with get_db_session() as session:
        query = session.query(Video).distinct()
        scope_title = "Global Library (Entire DB)"
        if style_id:
            query = query.join(StyleReference).filter(StyleReference.style_id == style_id)
            scope_title = f"Creator: {style_id}"
        elif user_id:
            owned_styles = [s.style_id for s in session.query(Style).filter_by(user_id=user_id).all()]
            if not owned_styles:
                console.print(f"[yellow]No creator profiles found for user '{user_id}'. Nothing to sync.[/yellow]")
                return
            query = query.join(StyleReference).filter(StyleReference.style_id.in_(owned_styles))
            scope_title = f"User Scoped: {user_id} ({len(owned_styles)} Creators)"

        videos = query.all()

        console.print(
            Panel(
                f"[bold cyan]Synchronizing videos to current pipeline level...[/bold cyan]\n"
                f"• Scope: [green]{scope_title}[/green]\n"
                f"• Target Videos: [yellow]{len(videos)}[/yellow]\n"
                f"[dim]Model: {settings.extraction_model}[/dim]",
                title="🔄 Pipeline Batch Synchronizer",
                border_style="cyan",
            )
        )

        if not videos:
            console.print("[yellow]No matching videos found in scope to synchronize.[/yellow]")
            return

        # Phase 2 Extraction for videos in 'stored' state
        pending_extraction = [
            v for v in videos
            if v.status == "stored" or not (settings.extractions_dir / f"{v.video_id}_v1.json").is_file()
        ]

        if pending_extraction:
            console.print(f"[bold yellow]Phase 2: {len(pending_extraction)} videos pending extraction...[/bold yellow]")
            extractor = GeminiExtractor()
            for idx, video in enumerate(pending_extraction, 1):
                console.print(
                    f"[bold magenta][PHASE 2: {idx}/{len(pending_extraction)}][/bold magenta] "
                    f"Extracting [bold cyan]{video.video_id}[/bold cyan]..."
                )
                try:
                    extractor.extract(video_id=video.video_id)
                    video.status = "extracted"
                    session.commit()
                except Exception as exc:
                    console.print(f"[bold red]✗ Failed to extract {video.video_id}: {exc}[/bold red]")

        # Phase 3 Memory Indexing
        session.expire_all()
        refreshed_videos = query.all()
        pending_indexing = [
            v for v in refreshed_videos
            if v.status in ("extracted", "stored") and (settings.extractions_dir / f"{v.video_id}_v1.json").is_file()
        ]

        if pending_indexing:
            console.print(f"\n[bold green]Phase 3: {len(pending_indexing)} videos pending vector indexing...[/bold green]")
            memory_service = MemoryService()
            for idx, video in enumerate(pending_indexing, 1):
                console.print(
                    f"[bold magenta][PHASE 3: {idx}/{len(pending_indexing)}][/bold magenta] "
                    f"Indexing [bold cyan]{video.video_id}[/bold cyan]..."
                )
                try:
                    memory_service.distill_and_index_video(video_id=video.video_id)
                except Exception as exc:
                    console.print(f"[bold red]✗ Failed to index {video.video_id}: {exc}[/bold red]")

        if not pending_extraction and not pending_indexing:
            console.print("[bold green]✓ All videos are already synchronized to current pipeline level![/bold green]")

    console.print("\n[bold green]Synchronization completed. Updated dashboard:[/bold green]")
    display_dashboard()


def process_url_file(file_path: Path, sync_level: bool = False) -> None:
    """Read URLs from a text file and ingest each one."""
    if not file_path.is_file():
        console.print(f"[bold red]Error: File not found: {file_path}[/bold red]")
        return

    urls = [line.strip() for line in file_path.read_text().splitlines() if line.strip() and not line.startswith("#")]
    console.print(f"[bold cyan][BATCH INGESTION][/bold cyan] Found {len(urls)} URLs in {file_path.name}")

    ingestion_service = IngestionService()
    extractor = GeminiExtractor() if sync_level else None

    for idx, url in enumerate(urls, 1):
        console.print(f"\n[bold magenta]Processing ({idx}/{len(urls)}):[/bold magenta] {url}")
        try:
            res = ingestion_service.ingest(source=url)
            if sync_level and (not res.is_duplicate or res.status != "extracted"):
                console.print(f"[dim]Syncing {res.video_id} to Phase 2 Extraction...[/dim]")
                if extractor:
                    extractor.extract(video_id=res.video_id)
        except Exception as exc:
            console.print(f"[bold red]Failed to process {url}: {exc}[/bold red]")

    console.print("\n[bold green]Batch processing completed. Updated dashboard:[/bold green]")
    display_dashboard()


def synthesize_style_corpus(style_id: str = "default_style") -> None:
    """Synthesize canonical Style Bible for a target style across indexed memories."""
    init_db()
    service = StyleService()
    try:
        style = service.synthesize_style(style_id=style_id)
        console.print(
            Panel(
                f"[bold green]✓ Successfully Synthesized Style Bible v{style.version} for '{style_id}'![/bold green]\n"
                f"• Artifact Location: data/styles/{style_id}_v{style.version}.md\n"
                f"• Latest Pointer: data/styles/{style_id}_latest.md\n"
                f"• Persisted in SQLite 'styles' table",
                title=f"📖 Style Bible v{style.version} Ready",
                border_style="green",
            )
        )
    except Exception as exc:
        console.print(f"[bold red]Style Synthesis failed:[/bold red] {exc}")


def main():
    """CLI Entrypoint for batch operations."""
    init_db()
    try:
        user = get_authenticated_user()
    except PermissionError:
        console.print(
            Panel(
                "[bold red]Access Denied:[/bold red] You must be logged in to run batch operations.\n\n"
                "Please log in using: [cyan]python -m app.cli user login <username>[/cyan]",
                title="🔒 Authentication Required",
                border_style="red",
            )
        )
        sys.exit(1)

    args = sys.argv[1:]
    sync_requested = any(arg in ("--sync", "-s", "--sync-all") for arg in args)
    file_args = [arg for arg in args if not arg.startswith("-")]

    if "--synthesize-style" in args or "-b" in args:
        flag = "--synthesize-style" if "--synthesize-style" in args else "-b"
        flag_idx = args.index(flag)
        target_style = (
            args[flag_idx + 1]
            if flag_idx + 1 < len(args) and not args[flag_idx + 1].startswith("-")
            else "default_style"
        )
        synthesize_style_corpus(style_id=target_style)
        return

    if file_args:
        target_file = Path(file_args[0])
        if target_file.is_file():
            process_url_file(target_file, sync_level=sync_requested)
            return

    if sync_requested:
        if any(arg in ("--all", "--global") for arg in args):
            sync_all_videos()
        else:
            sync_all_videos(user_id=user.user_id)
        return

    display_dashboard(user=user)


if __name__ == "__main__":
    main()

