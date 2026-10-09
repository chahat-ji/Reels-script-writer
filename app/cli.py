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

from app.account.service import AccountService
from app.core.config import console, settings
from app.core.database import init_db
from app.generation.service import ScriptService
from app.ingestion.queue import IngestionQueue
from app.ingestion.url_parser import clean_input_string
from app.style.service import StyleService

SESSION_FILE = settings.data_dir / ".current_user"


def get_current_user_id() -> str:
    """Return the currently logged-in user_id from local session, defaulting to 'usr_pilot_default'."""
    if SESSION_FILE.is_file():
        saved = SESSION_FILE.read_text(encoding="utf-8").strip()
        if saved:
            return saved
    return "usr_pilot_default"


def set_current_user_id(user_id: str) -> None:
    """Save the active user_id to local session."""
    SESSION_FILE.write_text(user_id.strip(), encoding="utf-8")


# ---------------------------------------------------------------------------
# Command Handlers
# ---------------------------------------------------------------------------

def handle_user(args: argparse.Namespace) -> None:
    """Handle user account commands."""
    service = AccountService()
    if args.user_action == "login":
        user = service.create_or_get_user(username=args.username, email=args.email)
        set_current_user_id(user.user_id)
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
        uid = get_current_user_id()
        console.print(f"[bold cyan]Current Active User ID:[/bold cyan] [green]{uid}[/green]")
    elif args.user_action == "list":
        # Query all users
        with service.create_or_get_user("pilot_default"):
            pass  # Ensure DB initialized
        from app.core.database import get_db_session
        from app.models.schema import User
        with get_db_session() as session:
            users = session.query(User).order_by(User.created_at.desc()).all()
            table = Table(title="👥 Registered Users", border_style="cyan")
            table.add_column("User ID", style="bold cyan")
            table.add_column("Username", style="green")
            table.add_column("Email", style="dim")
            table.add_column("Provider", style="magenta")
            for u in users:
                table.add_row(u.user_id, u.username, u.email or "N/A", u.auth_provider)
            console.print(table)


def handle_creator(args: argparse.Namespace) -> None:
    """Handle creator profile commands."""
    service = AccountService()
    user_id = get_current_user_id()

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
    user_id = get_current_user_id()
    script_service = ScriptService()
    script = script_service.generate_script(
        style_id=args.creator_id,
        premise=args.premise,
        user_id=user_id,
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
    service = AccountService()
    user_id = get_current_user_id()

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

    return parser


def main() -> None:
    """CLI Entrypoint."""
    init_db()
    parser = build_parser()
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)

    args = parser.parse_args()
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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

