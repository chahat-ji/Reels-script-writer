"""
app/cli.py
Unified Pilot CLI for the Creator-Based Script Generation Platform.

Commands:
  user login <username> [--email <email>]
  user whoami
  user list
  creator add <name> [--id <id>] [--desc <desc>]
  creator list
  creator synthesize <creator_id>
  upload <creator_id> <url_or_file> [--concurrency 2] [--no-synth]
  generate <creator_id> --premise "<premise>"
  history uploads [--creator <creator_id>]
  history scripts [--creator <creator_id>]
"""

import argparse
from pathlib import Path
import sys
from typing import List, Optional
from rich.panel import Panel
from rich.table import Table

from app.account.service import (
    AccountService,
    get_authenticated_user,
    get_current_user_id,
    set_current_user_id,
)
from app.core.config import console, settings
from app.core.database import get_db_session, init_db
from app.generation.service import ScriptService
from app.ingestion.queue import IngestionQueue
from app.ingestion.url_parser import clean_input_string
from app.models.schema import User
from app.style.service import StyleService


# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------

def handle_user(args: argparse.Namespace) -> None:
    """Handle user account commands."""
    service = AccountService()
    if args.user_action == "login":
        user = service.login(username=args.username, email=args.email)
        console.print(
            Panel(
                f"[bold green]✓ Logged in as:[/bold green] [cyan]{user.username}[/cyan]\n"
                f"• User ID: {user.user_id}\n"
                f"• Email: {user.email or 'N/A'}\n"
                f"• Auth Provider: {user.auth_provider}",
                title="👤 User Session",
                border_style="green",
            )
        )
    elif args.user_action == "whoami":
        try:
            user = get_authenticated_user()
            console.print(
                Panel(
                    f"[bold green]Active User:[/bold green] [cyan]{user.username}[/cyan]\n"
                    f"• User ID: {user.user_id}\n"
                    f"• Email: {user.email or 'N/A'}\n"
                    f"• Provider: {user.auth_provider}",
                    title="👤 Active Session",
                    border_style="green",
                )
            )
        except PermissionError:
            console.print(
                "[yellow]No active user logged in. Please log in with: [cyan]python -m app.cli user login <username>[/cyan][/yellow]"
            )
    elif args.user_action == "list":
        with get_db_session() as session:
            users = session.query(User).order_by(User.created_at.desc()).all()
            if not users:
                console.print("[yellow]No users registered in database.[/yellow]")
                return
            table = Table(title=f"👥 Registered Users ({len(users)} Total)", border_style="cyan")
            table.add_column("User ID", style="bold cyan")
            table.add_column("Username", style="green")
            table.add_column("Email", style="dim")
            table.add_column("Provider", style="magenta")
            for u in users:
                table.add_row(u.user_id, u.username, u.email or "N/A", u.auth_provider)
            console.print(table)


def handle_creator(args: argparse.Namespace) -> None:
    """Handle creator profile commands."""
    try:
        user = get_authenticated_user()
    except PermissionError as err:
        console.print(f"[bold red]{err}[/bold red]")
        return

    service = AccountService()
    user_id = user.user_id

    if args.creator_action == "add":
        creator = service.create_creator(
            user_id=user_id,
            creator_name=args.name,
            creator_id=args.id,
            description=args.desc,
        )
        console.print(
            Panel(
                f"[bold green]✓ Creator Profile Registered![/bold green]\n"
                f"• Creator Name: [cyan]{creator.name}[/cyan]\n"
                f"• Style ID: [green]{creator.style_id}[/green]\n"
                f"• Owner: {creator.user_id}",
                title="✨ Creator Registered",
                border_style="green",
            )
        )
    elif args.creator_action == "list":
        creators = service.list_creators(user_id=user_id if not args.all else None)
        if not creators:
            console.print("[yellow]No creator profiles found. Add one with: python -m app.cli creator add <name>[/yellow]")
            return
        table = Table(title=f"🎬 Creator Profiles ({len(creators)} Total)", border_style="cyan")
        table.add_column("Style ID", style="bold cyan")
        table.add_column("Name", style="green")
        table.add_column("Version", justify="center")
        table.add_column("Style Bible", justify="center")
        table.add_column("Owner", style="dim")
        for c in creators:
            bible_badge = "[green]✓ Ready[/green]" if c.bible_text else "[yellow]Pending[/yellow]"
            table.add_row(c.style_id, c.name or c.style_id, f"v{c.version}", bible_badge, c.user_id or "system")
        console.print(table)
    elif args.creator_action == "synthesize":
        style_service = StyleService()
        style_rec = style_service.synthesize_style(style_id=args.creator_id)
        console.print(
            Panel(
                f"[bold green]✓ Style Bible v{style_rec.version} Synthesized for '{args.creator_id}'![/bold green]\n"
                f"• Artifact: data/styles/{args.creator_id}_v{style_rec.version}.md",
                title="📖 Style Bible Ready",
                border_style="green",
            )
        )


def handle_upload(args: argparse.Namespace) -> None:
    """Handle batch video uploads under a creator profile."""
    try:
        user = get_authenticated_user()
    except PermissionError as err:
        console.print(f"[bold red]{err}[/bold red]")
        return

    creator_id = args.creator_id
    raw_source = args.source
    concurrency = args.concurrency or 2
    auto_synth = not args.no_synth

    # Check if raw_source is a file or single URL
    source_path = Path(raw_source)
    if source_path.is_file():
        urls = [line.strip() for line in source_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    else:
        urls = [clean_input_string(raw_source)]

    queue = IngestionQueue(max_workers=concurrency)
    res = queue.process_batch(sources=urls, style_id=creator_id, auto_synthesize=auto_synth)

    console.print(
        Panel(
            f"[bold green]Upload Completed for '{creator_id}'![/bold green]\n"
            f"• Authenticated User: {user.username} ({user.user_id})\n"
            f"• Total Submitted: {res.total}\n"
            f"• Successfully Indexed: [green]{len(res.succeeded)}[/green]\n"
            f"• Failed: [red]{len(res.failed)}[/red]\n"
            f"• Style Bible Version: {f'v{res.style_bible_version}' if res.style_bible_version else 'Unchanged'}",
            title="📥 Ingestion Summary",
            border_style="green",
        )
    )


def handle_generate(args: argparse.Namespace) -> None:
    """Handle screenplay generation for a creator."""
    try:
        user = get_authenticated_user()
    except PermissionError as err:
        console.print(f"[bold red]{err}[/bold red]")
        return

    script_service = ScriptService()
    script = script_service.generate_script(
        style_id=args.creator_id,
        premise=args.premise,
        user_id=user.user_id,
    )
    console.print(
        Panel(
            f"{script.script_text[:1200]}\n\n[dim]... (Full screenplay saved to data/scripts/{script.script_id}.txt)[/dim]",
            title=f"🎬 Screenplay Generated ({script.script_id})",
            border_style="cyan",
        )
    )


def handle_history(args: argparse.Namespace) -> None:
    """Handle history queries for uploads and generated scripts."""
    try:
        user = get_authenticated_user()
    except PermissionError as err:
        console.print(f"[bold red]{err}[/bold red]")
        return

    service = AccountService()
    user_id = user.user_id

    if args.history_action == "uploads":
        style_id = args.creator
        if not style_id:
            console.print("[yellow]Specify --creator <creator_id> to view upload history.[/yellow]")
            return
        uploads = service.get_creator_upload_history(style_id=style_id)
        if not uploads:
            console.print(f"[yellow]No upload history found for '{style_id}'.[/yellow]")
            return
        table = Table(title=f"📥 Upload History for '{style_id}' ({len(uploads)} Videos)", border_style="cyan")
        table.add_column("Video ID", style="bold cyan")
        table.add_column("Status", style="green")
        table.add_column("Duration", justify="center")
        table.add_column("Source URL", style="dim")
        table.add_column("Date", style="dim")
        for u in uploads:
            dur = f"{u['duration_ms']//1000}s" if u.get("duration_ms") else "N/A"
            table.add_row(u["video_id"], u["status"].upper(), dur, u["source_url"][:30], (u["created_at"] or "")[:16])
        console.print(table)

    elif args.history_action == "scripts":
        scripts = service.get_user_script_history(user_id=None if args.all else user_id, style_id=args.creator)
        if not scripts:
            console.print("[yellow]No generated scripts found.[/yellow]")
            return
        table = Table(title=f"📜 Generated Script History ({len(scripts)} Total)", border_style="cyan")
        table.add_column("Script ID", style="bold cyan")
        table.add_column("Creator", style="green")
        table.add_column("Premise", style="white", width=40)
        table.add_column("Created At", style="dim")
        for s in scripts:
            created_str = s.created_at.strftime("%Y-%m-%d %H:%M") if s.created_at else "N/A"
            premise_disp = (s.premise[:37] + "...") if len(s.premise) > 40 else s.premise
            table.add_row(s.script_id, s.style_id, premise_disp, created_str)
        console.print(table)


def handle_sync(args: argparse.Namespace) -> None:
    """Handle synchronization of pending video extractions and vector indexing."""
    try:
        user = get_authenticated_user()
    except PermissionError as err:
        console.print(f"[bold red]{err}[/bold red]")
        return

    from app.ingestion.sync import sync_all_videos
    if args.all:
        sync_all_videos()
    elif args.creator:
        sync_all_videos(style_id=args.creator)
    else:
        sync_all_videos(user_id=user.user_id)


# ---------------------------------------------------------------------------
# CLI Argument Parser Setup
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser hierarchy."""
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Creator-Based Script Generation Platform CLI")
    subparsers = parser.add_subparsers(dest="subcommand", help="Command to execute")

    # User subparser
    user_p = subparsers.add_parser("user", help="User account management")
    user_sp = user_p.add_subparsers(dest="user_action")
    login_p = user_sp.add_parser("login", help="Log in or create user")
    login_p.add_argument("username", help="Username")
    login_p.add_argument("--email", default=None, help="Optional email")
    user_sp.add_parser("whoami", help="Show active user session")
    user_sp.add_parser("list", help="List all registered users")

    # Creator subparser
    creator_p = subparsers.add_parser("creator", help="Creator profile management")
    creator_sp = creator_p.add_subparsers(dest="creator_action")
    add_c = creator_sp.add_parser("add", help="Add a creator profile")
    add_c.add_argument("name", help="Creator display name (e.g. 'Nani Comedy')")
    add_c.add_argument("--id", default=None, help="Custom creator ID (optional)")
    add_c.add_argument("--desc", default=None, help="Creator description")
    list_c = creator_sp.add_parser("list", help="List creators")
    list_c.add_argument("--all", action="store_true", help="List across all users")
    synth_c = creator_sp.add_parser("synthesize", help="Synthesize Style Bible for creator")
    synth_c.add_argument("creator_id", help="Creator style identifier")

    # Upload subparser
    upload_p = subparsers.add_parser("upload", help="Upload & ingest videos under creator")
    upload_p.add_argument("creator_id", help="Target creator style ID")
    upload_p.add_argument("source", help="Instagram URL, local file, or text file with URLs")
    upload_p.add_argument("--concurrency", type=int, default=2, help="Number of parallel workers (default: 2)")
    upload_p.add_argument("--no-synth", action="store_true", help="Skip automatic Style Bible synthesis")

    # Generate subparser
    gen_p = subparsers.add_parser("generate", help="Generate an original screenplay")
    gen_p.add_argument("creator_id", help="Creator style identifier")
    gen_p.add_argument("--premise", "-p", required=True, help="New sketch concept/premise")

    # History subparser
    hist_p = subparsers.add_parser("history", help="View upload and script history")
    hist_sp = hist_p.add_subparsers(dest="history_action")
    up_h = hist_sp.add_parser("uploads", help="View video uploads")
    up_h.add_argument("--creator", default=None, help="Filter by creator ID")
    scr_h = hist_sp.add_parser("scripts", help="View generated screenplays")
    scr_h.add_argument("--creator", default=None, help="Filter by creator ID")
    scr_h.add_argument("--all", action="store_true", help="List across all users")

    # Sync subparser
    sync_p = subparsers.add_parser("sync", help="Synchronize pending video extractions & vector indexing")
    sync_p.add_argument("--all", action="store_true", help="Sync all library videos across entire database (global)")
    sync_p.add_argument("--creator", default=None, help="Sync videos under specific creator ID")

    # Dashboard subparser
    dash_p = subparsers.add_parser("dashboard", help="Launch the local Web Studio verification dashboard")
    dash_p.add_argument("--port", type=int, default=8080, help="Web server port (default: 8080)")
    dash_p.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")

    # Serve subparser (FastAPI production REST API)
    serve_p = subparsers.add_parser("serve", help="Launch the FastAPI production REST API server")
    serve_p.add_argument("--host", default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    serve_p.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    serve_p.add_argument("--reload", action="store_true", help="Enable development auto-reload")

    # Menu / Interactive option
    parser.add_argument("--interactive", "-i", action="store_true", help="Launch interactive studio mode")
    subparsers.add_parser("menu", help="Launch interactive studio mode")

    return parser


def main() -> None:
    """CLI Entrypoint."""
    init_db()
    parser = build_parser()

    # Launch interactive wizard by default if no arguments are provided
    if len(sys.argv) == 1:
        from app.interactive import interactive_main
        interactive_main()
        return

    args = parser.parse_args()
    if getattr(args, "interactive", False) or args.subcommand == "menu":
        from app.interactive import interactive_main
        interactive_main()
        return

    if args.subcommand == "user":
        handle_user(args)
    elif args.subcommand == "creator":
        handle_creator(args)
    elif args.subcommand == "upload":
        handle_upload(args)
    elif args.subcommand == "generate":
        handle_generate(args)
    elif args.subcommand == "history":
        handle_history(args)
    elif args.subcommand == "sync":
        handle_sync(args)
    elif args.subcommand == "dashboard":
        from tools.dashboard.server import create_app
        from aiohttp import web
        port = args.port
        host = args.host
        console.print(
            Panel.fit(
                f"[bold green]Video-to-Style Verification Dashboard & Script Studio[/bold green]\n"
                f"[cyan]Server URL:[/cyan] [underline]http://{host}:{port}[/underline]\n"
                f"[dim]Reel verification & interactive script review in your browser.[/dim]",
                title="🎬 Web Studio",
                border_style="green",
            )
        )
        app = create_app()
        web.run_app(app, host=host, port=port, print=None)
    elif args.subcommand == "serve":
        import uvicorn
        console.print(
            Panel.fit(
                f"[bold green]Script Writer Production REST API[/bold green]\n"
                f"[cyan]API Base URL:[/cyan] [underline]http://{args.host}:{args.port}[/underline]\n"
                f"[cyan]Interactive Swagger Docs:[/cyan] [underline]http://{args.host}:{args.port}/docs[/underline]\n"
                f"[dim]User Studio Endpoints: /api/v1/scripts/* | Admin: /api/v1/admin/*[/dim]",
                title="🚀 FastAPI Server",
                border_style="green",
            )
        )
        uvicorn.run("app.api.main:app", host=args.host, port=args.port, reload=args.reload)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

