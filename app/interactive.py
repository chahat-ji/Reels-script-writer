"""
app/interactive.py
Interactive Studio CLI for the Script Writer Platform.

Provides a frictionless, menu-driven interface with selectable options and step-by-step
prompts so users don't need to memorize flags or subcommands.
"""

from pathlib import Path
import sys
from typing import List, Optional
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
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
from app.models.schema import Style, User
from app.style.service import StyleService


def select_creator(user_id: str, prompt_text: str = "Select a Creator") -> Optional[str]:
    """
    Display a numbered list of available creators and prompt user to select one.
    Offers an option to register a new creator on the fly.
    """
    account_service = AccountService()
    creators = account_service.list_creators(user_id=user_id)

    # If no user-specific creators, list all available creators
    if not creators:
        creators = account_service.list_creators()

    if not creators:
        console.print("[yellow]No creator profiles found. Let's create your first one![/yellow]")
        return add_creator_flow(user_id)

    console.print(f"\n[bold cyan]Available Creators for {prompt_text}:[/bold cyan]")
    for idx, c in enumerate(creators, 1):
        bible_badge = "[green]✓ Ready[/green]" if c.bible_text else "[yellow]Pending[/yellow]"
        console.print(f"  [bold green][{idx}][/bold green] [cyan]{c.name or c.style_id}[/cyan] ({c.style_id}) - Bible: {bible_badge}")
    console.print(f"  [bold green][+][/bold green] [dim]Create a new creator profile[/dim]")
    console.print(f"  [bold green][0][/bold green] [dim]Cancel / Go back[/dim]")

    choice = Prompt.ask("\nChoose an option", default="1")
    if choice in ("0", "cancel", "q"):
        return None
    if choice == "+":
        return add_creator_flow(user_id)

    try:
        idx = int(choice)
        if 1 <= idx <= len(creators):
            return creators[idx - 1].style_id
        console.print("[bold red]Invalid selection.[/bold red]")
        return None
    except ValueError:
        # User may have entered style_id directly
        cleaned = clean_input_string(choice)
        match = account_service.get_creator(cleaned)
        if match:
            return match.style_id
        console.print(f"[bold red]Creator '{choice}' not found.[/bold red]")
        return None


def add_creator_flow(user_id: str) -> Optional[str]:
    """Interactive flow to register a new creator profile."""
    console.print("\n[bold cyan]✨ Add a New Creator Profile[/bold cyan]")
    name = Prompt.ask("Enter Creator display name (e.g. 'Nani Comedy', 'Desi Banter')")
    if not name.strip():
        console.print("[yellow]Cancelled (name cannot be empty).[/yellow]")
        return None

    desc = Prompt.ask("Enter description (optional, press Enter to skip)", default="")
    custom_id = Prompt.ask("Custom Style ID (optional, press Enter for auto-generated)", default="")

    account_service = AccountService()
    creator = account_service.create_creator(
        user_id=user_id,
        creator_name=name.strip(),
        creator_id=custom_id.strip() if custom_id.strip() else None,
        description=desc.strip() if desc.strip() else None,
    )
    console.print(
        Panel(
            f"[bold green]✓ Creator Profile Registered![/bold green]\n"
            f"• Name: [cyan]{creator.name}[/cyan]\n"
            f"• Style ID: [green]{creator.style_id}[/green]\n"
            f"• Owner: {creator.user_id}",
            border_style="green",
        )
    )
    return creator.style_id


def ensure_authenticated_user() -> User:
    """Ensure a user is logged in, prompting for login if session is absent."""
    account_service = AccountService()
    try:
        return get_authenticated_user()
    except PermissionError:
        console.print(
            Panel(
                "[bold cyan]Welcome to Script Writer Studio![/bold cyan]\n"
                "No active user session found. Please enter your username to log in or register.",
                title="👤 Login Required",
                border_style="cyan",
            )
        )
        username = Prompt.ask("[bold green]Enter your username[/bold green]", default="test_user")
        email = Prompt.ask("Enter email (optional, press Enter to skip)", default="")
        user = account_service.login(username=username, email=email.strip() if email.strip() else None)
        console.print(f"[bold green]✓ Logged in as:[/bold green] [cyan]{user.username}[/cyan] ({user.user_id})\n")
        return user


def flow_generate_script(user: User) -> None:
    """Interactive screenplay generation flow."""
    console.print("\n[bold magenta]════════════════════════════════════════════════════════════[/bold magenta]")
    console.print("[bold cyan]✍️  Generate Original Comedy Screenplay[/bold cyan]")
    console.print("[bold magenta]════════════════════════════════════════════════════════════[/bold magenta]")

    style_id = select_creator(user_id=user.user_id, prompt_text="generation")
    if not style_id:
        return

    account_service = AccountService()
    creator = account_service.get_creator(style_id=style_id)

    # Check if Style Bible exists
    if not creator or not creator.bible_text:
        console.print(
            f"\n[yellow]Style Bible for '{style_id}' is not synthesized yet.[/yellow]"
        )
        # Check if creator has indexed videos
        uploads = account_service.get_creator_upload_history(style_id=style_id)
        if not uploads:
            console.print(
                "[bold red]This creator has 0 reference videos.[/bold red]\n"
                "Please upload at least 1 video before generating scripts.\n"
                "Tip: Choose option [2] from the main menu to upload videos."
            )
            return

        should_synth = Confirm.ask("Synthesize Style Bible now before generating?", default=True)
        if should_synth:
            style_service = StyleService()
            try:
                style_rec = style_service.synthesize_style(style_id=style_id)
                console.print(f"[bold green]✓ Style Bible v{style_rec.version} ready![/bold green]")
            except Exception as exc:
                console.print(f"[bold red]Style synthesis failed:[/bold red] {exc}")
                return
        else:
            return

    console.print("\n[bold green]Enter your comedy sketch concept or premise:[/bold green]")
    premise = Prompt.ask(
        "Premise",
        default="Raju hides his poor marksheet inside the refrigerator, but Nani already found it",
    )
    if not premise.strip():
        console.print("[yellow]Generation cancelled (empty premise).[/yellow]")
        return

    script_service = ScriptService()
    try:
        script = script_service.generate_script(
            style_id=style_id,
            premise=premise.strip(),
            user_id=user.user_id,
        )
        console.print(
            Panel(
                f"{script.script_text}\n\n"
                f"[dim]Saved permanently to: data/scripts/{script.script_id}.txt[/dim]",
                title=f"🎬 Screenplay Generated ({script.script_id})",
                border_style="green",
            )
        )
    except Exception as exc:
        console.print(f"[bold red]Generation encountered an error:[/bold red] {exc}")


def flow_upload_videos(user: User) -> None:
    """Interactive video upload flow."""
    console.print("\n[bold magenta]════════════════════════════════════════════════════════════[/bold magenta]")
    console.print("[bold cyan]📥 Upload Reference Videos[/bold cyan]")
    console.print("[bold magenta]════════════════════════════════════════════════════════════[/bold magenta]")

    style_id = select_creator(user_id=user.user_id, prompt_text="upload target")
    if not style_id:
        return

    source = Prompt.ask("\nEnter Instagram Reel URL, video file path, or text file with URLs")
    clean_src = clean_input_string(source)
    if not clean_src:
        console.print("[yellow]Cancelled (empty input).[/yellow]")
        return

    # Check if text file with multiple URLs
    src_path = Path(clean_src)
    if src_path.is_file() and not src_path.suffix.lower() in (".mp4", ".mov", ".mkv", ".avi", ".webm"):
        urls = [line.strip() for line in src_path.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
        console.print(f"[cyan]Found {len(urls)} URLs in {src_path.name}.[/cyan]")
        concurrency = IntPrompt.ask("Worker concurrency (parallel threads)", default=2)
    else:
        urls = [clean_src]
        concurrency = 2

    auto_synth = Confirm.ask("Automatically update / synthesize Style Bible after upload?", default=True)

    queue = IngestionQueue(max_workers=concurrency)
    res = queue.process_batch(sources=urls, style_id=style_id, auto_synthesize=auto_synth)

    console.print(
        Panel(
            f"[bold green]✓ Ingestion Completed for '{style_id}'![/bold green]\n"
            f"• Total Processed: {res.total}\n"
            f"• Successfully Indexed: [green]{len(res.succeeded)}[/green]\n"
            f"• Failed: [red]{len(res.failed)}[/red]\n"
            f"• Style Bible: {f'v{res.style_bible_version}' if res.style_bible_version else 'Ready'}",
            title="📥 Ingestion Summary",
            border_style="green",
        )
    )


def flow_view_creators(user: User) -> None:
    """Interactive flow to list creators and synthesize Style Bibles."""
    account_service = AccountService()
    creators = account_service.list_creators(user_id=user.user_id)

    if not creators:
        console.print("[yellow]No creator profiles found.[/yellow]")
        add_now = Confirm.ask("Would you like to create one now?", default=True)
        if add_now:
            add_creator_flow(user.user_id)
        return

    table = Table(title=f"🎬 Creator Profiles ({len(creators)} Total)", border_style="cyan")
    table.add_column("#", justify="center", style="bold green")
    table.add_column("Style ID", style="bold cyan")
    table.add_column("Name", style="green")
    table.add_column("Version", justify="center")
    table.add_column("Style Bible", justify="center")
    table.add_column("Owner", style="dim")

    for idx, c in enumerate(creators, 1):
        bible_badge = "[green]✓ Ready[/green]" if c.bible_text else "[yellow]Pending[/yellow]"
        table.add_row(str(idx), c.style_id, c.name or c.style_id, f"v{c.version}", bible_badge, c.user_id or "system")
    console.print(table)

    action = Prompt.ask(
        "\nOptions: [S]ynthesize Bible for a creator, [+] Add new creator, [Enter] Back",
        default="",
    ).strip().lower()

    if action in ("s", "synthesize"):
        target_num = IntPrompt.ask(f"Enter creator number [1-{len(creators)}]", default=1)
        if 1 <= target_num <= len(creators):
            target_creator = creators[target_num - 1]
            style_service = StyleService()
            try:
                style_rec = style_service.synthesize_style(style_id=target_creator.style_id)
                console.print(
                    Panel(
                        f"[bold green]✓ Style Bible v{style_rec.version} Synthesized![/bold green]\n"
                        f"• Creator: {target_creator.name} ({target_creator.style_id})\n"
                        f"• Artifact: data/styles/{target_creator.style_id}_v{style_rec.version}.md",
                        border_style="green",
                    )
                )
            except Exception as exc:
                console.print(f"[bold red]Synthesis failed:[/bold red] {exc}")
    elif action == "+":
        add_creator_flow(user.user_id)


def flow_view_history(user: User) -> None:
    """Interactive flow to inspect upload and screenplay history."""
    console.print("\n[bold cyan]📜 History Explorer[/bold cyan]")
    console.print("  [1] Uploaded Reference Videos History")
    console.print("  [2] Generated Comedy Scripts History")
    console.print("  [0] Back to Main Menu")

    choice = Prompt.ask("Select option", default="1")
    account_service = AccountService()

    if choice == "1":
        style_id = select_creator(user_id=user.user_id, prompt_text="upload history")
        if not style_id:
            return
        uploads = account_service.get_creator_upload_history(style_id=style_id)
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

    elif choice == "2":
        scripts = account_service.get_user_script_history(user_id=user.user_id)
        if not scripts:
            console.print("[yellow]No generated scripts found for your account.[/yellow]")
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


def flow_switch_user() -> User:
    """Interactive user switch / login flow."""
    account_service = AccountService()
    username = Prompt.ask("Enter username to log in")
    email = Prompt.ask("Enter email (optional, press Enter to skip)", default="")
    user = account_service.login(username=username, email=email.strip() if email.strip() else None)
    console.print(f"[bold green]✓ Active user switched to:[/bold green] [cyan]{user.username}[/cyan] ({user.user_id})")
    return user


def flow_sync_videos(user: User) -> None:
    """Interactive flow to synchronize pending video extractions and vector indexing."""
    console.print("\n[bold magenta]════════════════════════════════════════════════════════════[/bold magenta]")
    console.print("[bold cyan]🔄 Synchronize Videos Pipeline (Phase 2 & Phase 3)[/bold cyan]")
    console.print("[bold magenta]════════════════════════════════════════════════════════════[/bold magenta]")
    console.print("Bring pending videos up to Phase 2 (Gemini Extraction) and Phase 3 (Vector Indexing).\n")
    console.print("  [bold green][1][/bold green] 👤 Sync My Videos      [dim](Only videos under your creator profiles)[/dim]")
    console.print("  [bold green][2][/bold green] 🎬 Sync by Creator     [dim](Select a specific creator to sync)[/dim]")
    console.print("  [bold green][3][/bold green] 🌐 Sync All in DB      [dim](Global sync across entire database)[/dim]")
    console.print("  [bold green][0][/bold green] ↩️  Back to Main Menu")

    choice = Prompt.ask("\nSelect sync scope [0-3]", default="1").strip()
    from app.ingestion.sync import sync_all_videos

    if choice == "1":
        sync_all_videos(user_id=user.user_id)
    elif choice == "2":
        creator_id = select_creator(user_id=user.user_id, prompt_text="sync")
        if creator_id:
            sync_all_videos(style_id=creator_id)
    elif choice == "3":
        sync_all_videos()
    elif choice in ("0", "q", "back"):
        return
    else:
        console.print("[bold red]Invalid option.[/bold red]")


def interactive_main() -> None:
    """Main interactive studio loop."""
    init_db()
    user = ensure_authenticated_user()

    while True:
        try:
            console.print()
            console.print(
                Panel(
                    f"[bold cyan]🎬 Script Writer – Interactive Studio[/bold cyan]\n"
                    f"👤 [green]Logged in as:[/green] [bold white]{user.username}[/bold white] [dim]({user.user_id})[/dim]",
                    border_style="cyan",
                )
            )
            console.print("[bold yellow]What would you like to do?[/bold yellow]")
            console.print("  [bold green][1][/bold green] ✍️  Generate Script        [dim](Write comedy screenplay from premise)[/dim]")
            console.print("  [bold green][2][/bold green] 📥 Upload Videos          [dim](Ingest Reel URLs or video files)[/dim]")
            console.print("  [bold green][3][/bold green] 🔄 Sync Pending Videos    [dim](Process pending extractions & embeddings)[/dim]")
            console.print("  [bold green][4][/bold green] ✨ Add Creator Profile    [dim](Create new comedic style)[/dim]")
            console.print("  [bold green][5][/bold green] 📖 Creator Profiles & Bibles [dim](View profiles & synthesize)[/dim]")
            console.print("  [bold green][6][/bold green] 📜 View History           [dim](Uploads & generated screenplays)[/dim]")
            console.print("  [bold green][7][/bold green] 📊 Pipeline Status        [dim](View terminal database stats)[/dim]")
            console.print("  [bold green][8][/bold green] 🌐 Web Studio Dashboard   [dim](Launch browser Reel & Script Reviewer)[/dim]")
            console.print("  [bold green][9][/bold green] 👤 Switch User / Login    [dim](Change active account)[/dim]")
            console.print("  [bold green][0][/bold green] 🚪 Exit")

            choice = Prompt.ask("\nSelect an option [0-9]", default="1").strip()

            if choice == "1":
                flow_generate_script(user)
            elif choice == "2":
                flow_upload_videos(user)
            elif choice == "3":
                flow_sync_videos(user)
            elif choice == "4":
                add_creator_flow(user.user_id)
            elif choice == "5":
                flow_view_creators(user)
            elif choice == "6":
                flow_view_history(user)
            elif choice == "7":
                from app.ingestion.sync import display_dashboard
                display_dashboard(user=user)
            elif choice == "8":
                from tools.dashboard.server import create_app
                from aiohttp import web
                console.print("\n[bold green]Starting Web Studio Dashboard on http://127.0.0.1:8080...[/bold green]")
                console.print("[dim]Press Ctrl+C in terminal when finished to return to the interactive studio.[/dim]\n")
                try:
                    app = create_app()
                    web.run_app(app, host="127.0.0.1", port=8080, print=None)
                except KeyboardInterrupt:
                    console.print("\n[cyan]Dashboard stopped.[/cyan]")
            elif choice == "9":
                user = flow_switch_user()
            elif choice in ("0", "q", "exit"):
                console.print("[cyan]Goodbye! Happy writing! 🎬[/cyan]")
                break
            else:
                console.print("[bold red]Invalid option. Please choose a number between 0 and 9.[/bold red]")

            Prompt.ask("\n[dim]Press Enter to return to main menu...[/dim]", default="")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[cyan]Session ended. Goodbye! 🎬[/cyan]")
            break


if __name__ == "__main__":
    interactive_main()

