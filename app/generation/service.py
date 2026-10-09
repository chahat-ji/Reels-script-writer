"""
app/generation/service.py
High-level service orchestrating screenplay generation and persistence.

Coordinates adaptive context assembly, LLM creative synthesis, SQLite
record logging, and disk artifact persistence.
"""

from pathlib import Path
import uuid
from typing import Optional
from app.core.config import console, settings
from app.core.database import get_db_session
from app.generation.context import ContextBuilder
from app.generation.generator import ScreenplayGenerator
from app.models.schema import Script, utc_now


class ScriptService:
    """
    Main service coordinating screenplay generation workflows.
    """

    def __init__(
        self,
        context_builder: Optional[ContextBuilder] = None,
        generator: Optional[ScreenplayGenerator] = None,
        scripts_dir: Optional[Path] = None,
    ):
        self.context_builder = context_builder or ContextBuilder()
        self.generator = generator or ScreenplayGenerator()
        self.scripts_dir = scripts_dir or settings.scripts_dir
        self.scripts_dir.mkdir(parents=True, exist_ok=True)

    def generate_script(
        self,
        style_id: str,
        premise: str,
        user_id: Optional[str] = None,
    ) -> Script:
        """
        Generate an original screenplay in a creator's style and save it permanently.

        Args:
            style_id: Creator style identifier.
            premise: User's concept or premise for the new sketch.
            user_id: Optional user identifier for account history.

        Returns:
            Persisted Script model instance.
        """
        console.print(
            f"\n[bold magenta]════════════════════════════════════════════════════════════[/bold magenta]\n"
            f"[bold cyan]Launching Script Generation for '[green]{style_id}[/green]'...[/bold cyan]\n"
            f"[bold magenta]════════════════════════════════════════════════════════════[/bold magenta]"
        )

        # 1. Build adaptive context (checks if <= 10 or > 10)
        context = self.context_builder.build_context(style_id=style_id, premise=premise)

        # 2. Synthesize original screenplay with Gemini
        script_text = self.generator.generate_screenplay(context)

        # 3. Create persistent identifiers and paths
        script_id = f"scr_{uuid.uuid4().hex[:8]}"
        script_filepath = self.scripts_dir / f"{script_id}.txt"

        # 4. Save screenplay to disk
        with open(script_filepath, "w", encoding="utf-8") as f:
            f.write(
                f"# SCREENPLAY: {script_id}\n"
                f"# CREATOR STYLE: {style_id}\n"
                f"# PREMISE: {premise}\n"
                f"# ============================================================\n\n"
                f"{script_text}\n"
            )

        # 5. Persist record in SQLite
        with get_db_session() as session:
            script_record = Script(
                script_id=script_id,
                user_id=user_id,
                style_id=style_id,
                premise=premise,
                script_text=script_text,
                created_at=utc_now(),
            )
            session.add(script_record)
            session.flush()
            _ = (
                script_record.script_id,
                script_record.user_id,
                script_record.style_id,
                script_record.premise,
                script_record.script_text,
                script_record.created_at,
            )
            session.expunge(script_record)

        console.print(
            f"[bold green]✓ Screenplay Generated & Saved![/bold green] "
            f"ID: [cyan]{script_id}[/cyan] -> [dim]{script_filepath}[/dim]"
        )

        return script_record

    def get_script(self, script_id: str) -> Optional[Script]:
        """Retrieve a specific screenplay record by ID."""
        with get_db_session() as session:
            record = session.query(Script).filter_by(script_id=script_id).first()
            if record:
                _ = (record.script_id, record.user_id, record.style_id, record.premise, record.script_text)
                session.expunge(record)
                return record
        return None

