"""
app/style/service.py
High-level service orchestrator for Style Bible synthesis and versioning.

Coordinates corpus aggregation, Gemini creative synthesis, version tracking,
and database persistence.
"""

from typing import Optional
from app.core.config import console
from app.models.schema import Style
from app.style.aggregator import StyleAggregator
from app.style.synthesizer import StyleSynthesizer
from app.style.versioning import StyleVersioning


class StyleService:
    """
    Main service coordinating Phase 4 Style Synthesis workflows.
    """

    def __init__(
        self,
        aggregator: Optional[StyleAggregator] = None,
        synthesizer: Optional[StyleSynthesizer] = None,
        versioning: Optional[StyleVersioning] = None,
    ):
        self.aggregator = aggregator or StyleAggregator()
        self.synthesizer = synthesizer or StyleSynthesizer()
        self.versioning = versioning or StyleVersioning()

    def synthesize_style(self, style_id: str = "default_style") -> Style:
        """
        Synthesize or update the Style Bible for a target style_id.

        Gathers all Video Memories associated with style_id, determines the target
        version number (v1 if new, v2 if updating with additional reference videos),
        invokes Gemini 3.8 Flash to synthesize the creative Style Bible, and persists
        the result in SQLite and on disk.

        Args:
            style_id: Unique style identifier.

        Returns:
            The newly created or updated Style database model instance.
        """
        console.print(
            f"\n[bold magenta]════════════════════════════════════════════════════════════[/bold magenta]\n"
            f"[bold cyan]Launching Phase 4 Style Synthesis for '[green]{style_id}[/green]'...[/bold cyan]\n"
            f"[bold magenta]════════════════════════════════════════════════════════════[/bold magenta]"
        )

        # 1. Aggregate memory corpus
        corpus = self.aggregator.aggregate_style_corpus(style_id)

        # 2. Determine target version (v1, v2, ...)
        target_version = self.versioning.determine_target_version(style_id)

        # 3. Synthesize Style Bible Markdown with Gemini
        bible_text = self.synthesizer.synthesize_bible(corpus, target_version=target_version)

        # 4. Persist to SQLite and data/styles/
        video_ids = corpus.stats.video_ids
        persisted_style = self.versioning.persist_style_bible(
            style_id=style_id,
            version=target_version,
            bible_text=bible_text,
            video_ids=video_ids,
        )

        return persisted_style

    def get_style(self, style_id: str = "default_style") -> Optional[Style]:
        """
        Retrieve the latest synthesized Style Bible for a style_id.
        """
        return self.versioning.get_latest_style(style_id)

