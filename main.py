"""
main.py
Primary entry point for the Video-to-Style Script Generation system.

Takes a single Instagram Reel URL (or local video path) without requiring any flags,
and executes it through the pipeline:
1. Video download (yt-dlp)
2. Audio extraction (ffmpeg)
3. SHA-256 duplicate detection
4. Permanent object storage placement
5. SQLite catalog registration

This entry point will automatically invoke subsequent pipeline phases
(Gemini multimodal extraction, memory distillation, script generation)
as they are implemented.
"""

import sys
from pathlib import Path
from typing import Optional
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

from app.account.service import AccountService, get_authenticated_user
from app.core.config import console, settings
from app.core.database import init_db
from app.extraction.gemini_extractor import GeminiExtractor
from app.ingestion.service import IngestionService
from app.ingestion.url_parser import clean_input_string
from app.memory.service import MemoryService
from app.models.schema import User
from app.style.service import StyleService


def run_pipeline(source: str, style_id: Optional[str] = None, user: Optional[User] = None) -> None:
    """
    Execute a single video source through the current pipeline level for an authenticated user.
    """
    # Ensure database schema is initialized
    init_db()

    active_user = user or get_authenticated_user()
    account_service = AccountService()

    # Resolve target creator / style
    if not style_id:
        user_creators = account_service.list_creators(user_id=active_user.user_id)
        if user_creators:
            target_style_id = user_creators[0].style_id
        else:
            creator = account_service.create_creator(
                user_id=active_user.user_id,
                creator_name=f"{active_user.username.capitalize()}'s Style",
                creator_id=f"c_{active_user.username}",
            )
            target_style_id = creator.style_id
    else:
        target_style_id = style_id

    console.print(
        Panel.fit(
            f"[bold cyan]Video-to-Style Pipeline[/bold cyan]\n"
            f"[green]User:[/green] {active_user.username} ({active_user.user_id})\n"
            f"[yellow]Source:[/yellow] {source}\n"
            f"[yellow]Target Style / Creator:[/yellow] {target_style_id}",
            border_style="cyan",
            title="🎬 Video Intake",
        )
    )

    # Step 1: Ingestion & Storage Pipeline
    ingestion_service = IngestionService()
    result = ingestion_service.ingest(source=source, style_id=target_style_id)

    # Render summary table of the ingestion result
    table = Table(title="Pipeline Ingestion Summary", border_style="green")
    table.add_column("Property", style="bold white", width=18)
    table.add_column("Value", style="cyan")

    table.add_row("Video ID", result.video_id)
    table.add_row("Duplicate Status", "[yellow]DUPLICATE (Skipped)[/yellow]" if result.is_duplicate else "[green]NEW ASSET (Stored)[/green]")
    table.add_row("SHA-256 Fingerprint", result.sha256)
    table.add_row("Permanent Video URI", result.storage_uri)
    table.add_row("Permanent Audio URI", result.audio_uri or "[dim]N/A[/dim]")
    table.add_row("Duration (ms)", str(result.duration_ms) if result.duration_ms else "[dim]Unknown[/dim]")
    table.add_row("Pipeline Level", f"[bold green]{result.status.upper()} (Phase 1 Ready)[/bold green]")
    table.add_row("Status Message", result.message)

    console.print(table)

    # Step 2: Phase 2 - One-Time Gemini Multimodal Video Extraction
    if result.status == "stored":
        if settings.gemini_api_key:
            try:
                console.print("\n[bold cyan]Step 2: Launching Phase 2 Gemini Multimodal Extraction...[/bold cyan]")
                extractor = GeminiExtractor()
                extraction = extractor.extract(video_id=result.video_id)
                speaker_list = [f"{code}: {name}" for code, name in extraction.speakers.items()]
                devices = extraction.cd.mech if extraction.cd.mech else ["General Comedy"]
                console.print(
                    Panel(
                        f"[bold green]✓ Phase 2 Extraction Completed for {result.video_id}![/bold green]\n"
                        f"• Scenes: {len(extraction.sc)}\n"
                        f"• Speakers: {', '.join(speaker_list)}\n"
                        f"• Comedy Devices: {', '.join(devices)}\n"
                        f"• Archive Location: data/extractions/{result.video_id}_v1.json",
                        title=f"✨ {extractor.model_name} Extraction Result",
                        border_style="green",
                    )
                )
            except Exception as ext_err:
                console.print(f"[bold red]Phase 2 Extraction encountered an error:[/bold red] {ext_err}")
        else:
            console.print(
                f"\n[yellow]💡 Phase 1 Complete. To run Phase 2 Gemini ({settings.extraction_model}) extraction, "
                "set GEMINI_API_KEY in your .env file.[/yellow]"
            )

    # Step 3: Phase 3 - Video Memory Distillation & Vector Indexing
    if settings.gemini_api_key:
        archive_path = settings.extractions_dir / f"{result.video_id}_v1.json"
        if archive_path.is_file():
            try:
                console.print("\n[bold cyan]Step 3: Launching Phase 3 Video Memory Distillation & Indexing...[/bold cyan]")
                memory_service = MemoryService()
                mem = memory_service.distill_and_index_video(video_id=result.video_id, style_id=style_id)
                chars = mem.metadata_json.get("characters", []) if mem.metadata_json else []
                mechs = mem.metadata_json.get("comedy_mechanisms", []) if mem.metadata_json else []
                console.print(
                    Panel(
                        f"[bold green]✓ Phase 3 Video Memory & Vector Index Ready for {result.video_id}![/bold green]\n"
                        f"• Characters: {', '.join(chars) if chars else 'N/A'}\n"
                        f"• Comedy Mechanisms: {', '.join(mechs) if mechs else 'N/A'}\n"
                        f"• Embedding: 768-dim float32 NumPy vector stored in SQLite\n"
                        f"• Pipeline Status: [bold green]INDEXED[/bold green]",
                        title="🧠 Creative Video Memory Distilled",
                        border_style="green",
                    )
                )
            except Exception as mem_err:
                console.print(f"[bold red]Phase 3 Memory Indexing encountered an error:[/bold red] {mem_err}")

    # Step 4: Phase 4 - Style Bible Status
    style_service = StyleService()
    # Step 4: Phase 4 - Style Bible Status
    active_style = style_service.get_style(style_id=target_style_id)
    if active_style and active_style.bible_text:
        console.print(
            f"\n[dim]📖 Active Style Bible: [bold green]{target_style_id} (v{active_style.version})[/bold green] "
            f"(data/styles/{target_style_id}_v{active_style.version}.md)[/dim]\n"
            f"[dim]To synthesize or update the Style Bible, run: [bold cyan]python batch_process.py --synthesize-style {target_style_id}[/bold cyan][/dim]"
        )
    else:
        console.print(
            f"\n[yellow]💡 Phase 4 Ready: To synthesize the global Style Bible for '{target_style_id}', "
            f"run: [bold cyan]python batch_process.py --synthesize-style {target_style_id}[/bold cyan][/yellow]"
        )


def main():
    """
    CLI Entrypoint.
    Accepts URL directly via argument: python main.py <url> [creator_id]
    Or prompts interactively if run without arguments.
    Enforces mandatory authentication - backdoor access closed.
    """
    init_db()

    # Enforce mandatory user authentication
    try:
        user = get_authenticated_user()
    except PermissionError as auth_err:
        console.print(
            Panel(
                f"[bold red]Access Denied:[/bold red] You must be logged in to run the pipeline.\n\n"
                f"Please log in using: [cyan]python -m app.cli user login <username>[/cyan]",
                title="🔒 Authentication Required",
                border_style="red",
            )
        )
        sys.exit(1)

    target_style = None
    if len(sys.argv) > 1:
        source = clean_input_string(sys.argv[1])
        if len(sys.argv) > 2 and not sys.argv[2].startswith("-"):
            target_style = clean_input_string(sys.argv[2])
    else:
        raw_prompt = Prompt.ask(
            "[bold cyan]Enter Instagram Reel URL / video file path[/bold cyan] [dim](or press Enter for Interactive Studio)[/dim]",
            default="",
        )
        source = clean_input_string(raw_prompt)
        if not source:
            from app.interactive import interactive_main
            interactive_main()
            return

    if not source:
        console.print("[bold red]Error: No video URL or file path provided.[/bold red]")
        sys.exit(1)

    run_pipeline(source=source, style_id=target_style, user=user)


if __name__ == "__main__":
    main()

