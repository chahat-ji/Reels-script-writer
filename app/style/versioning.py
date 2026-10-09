"""
app/style/versioning.py
Version lifecycle manager and artifact persistence for Style Bibles.

Implements Sections 21 & 22 of description.txt:
- Determines next version integer (v1 -> v2 -> v3) when new reference videos are added.
- Updates or inserts Style record in SQLite with bible_text and timestamps.
- Records StyleReference links between the style and its constituent videos.
- Persists canonical Markdown files to data/styles/{style_id}_v{version}.md to guarantee
  existing versions remain reproducible.
"""

from pathlib import Path
from typing import List, Optional
from app.core.config import console, settings
from app.core.database import get_db_session
from app.models.schema import Style, StyleReference, utc_now


class StyleVersioning:
    """
    Manages Style versioning, database persistence, and disk archival.
    """

    def __init__(self, styles_dir: Optional[Path] = None):
        self.styles_dir = styles_dir or settings.styles_dir
        self.styles_dir.mkdir(parents=True, exist_ok=True)

    def determine_target_version(self, style_id: str) -> int:
        """
        Determine the next version number for a style_id.
        If no style exists yet, returns 1. If v1 exists, returns 2, etc.
        """
        with get_db_session() as session:
            existing = session.query(Style).filter_by(style_id=style_id).first()
            if not existing or not existing.bible_text:
                return 1
            return existing.version + 1

    def persist_style_bible(
        self,
        style_id: str,
        version: int,
        bible_text: str,
        video_ids: List[str],
    ) -> Style:
        """
        Persist a synthesized Style Bible to SQLite and disk.

        Args:
            style_id: Style identifier.
            version: Version integer (e.g. 1, 2).
            bible_text: Full synthesized Style Bible Markdown text.
            video_ids: List of video IDs that contributed to this Style Bible.

        Returns:
            The persisted Style model instance.
        """
        # 1. Save canonical reproducible file to disk: data/styles/{style_id}_v{version}.md
        version_filename = f"{style_id}_v{version}.md"
        version_filepath = self.styles_dir / version_filename
        with open(version_filepath, "w", encoding="utf-8") as f:
            f.write(bible_text)

        # Also write the latest pointer: data/styles/{style_id}_latest.md
        latest_filepath = self.styles_dir / f"{style_id}_latest.md"
        with open(latest_filepath, "w", encoding="utf-8") as f:
            f.write(bible_text)

        # 2. Persist in SQLite
        with get_db_session() as session:
            style_record = session.query(Style).filter_by(style_id=style_id).first()
            if not style_record:
                style_record = Style(
                    style_id=style_id,
                    version=version,
                    bible_text=bible_text,
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
                session.add(style_record)
            else:
                style_record.version = version
                style_record.bible_text = bible_text
                style_record.updated_at = utc_now()

            # 3. Maintain StyleReference associations for all contributing videos
            for vid in video_ids:
                existing_ref = (
                    session.query(StyleReference)
                    .filter_by(style_id=style_id, video_id=vid)
                    .first()
                )
                if not existing_ref:
                    new_ref = StyleReference(
                        style_id=style_id,
                        video_id=vid,
                        relevance=1.0,
                    )
                    session.add(new_ref)

            session.flush()
            # Eagerly access fields to avoid DetachedInstanceError outside session
            _ = (style_record.style_id, style_record.version, style_record.bible_text)
            session.expunge(style_record)

        console.print(
            f"[bold green][STYLE VERSIONED][/bold green] Style Bible v{version} saved to "
            f"SQLite & [cyan]{version_filepath.name}[/cyan] ({len(video_ids)} reference videos linked)."
        )

        return style_record

    def get_latest_style(self, style_id: str) -> Optional[Style]:
        """Retrieve the currently active Style record from SQLite."""
        with get_db_session() as session:
            style_record = session.query(Style).filter_by(style_id=style_id).first()
            if style_record:
                _ = (style_record.style_id, style_record.version, style_record.bible_text)
                session.expunge(style_record)
                return style_record
        return None

