"""
app/style/aggregator.py
Corpus aggregator for style synthesis.

Collects and formats all active Video Memories for a target style_id,
computes aggregate corpus metrics (character counts, comedic mechanisms,
pacing, settings), and prepares the synthesized prompt context for Gemini.
"""

from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from app.core.config import console
from app.core.database import get_db_session
from app.models.schema import StyleReference, VideoMemory


@dataclass
class CorpusStats:
    """Aggregate statistics computed across a style's video memory corpus."""

    total_memories: int = 0
    video_ids: List[str] = field(default_factory=list)
    unique_characters: List[str] = field(default_factory=list)
    common_mechanisms: List[str] = field(default_factory=list)
    common_settings: List[str] = field(default_factory=list)
    pacing_styles: List[str] = field(default_factory=list)
    dominant_language: str = "hi"


@dataclass
class StyleCorpus:
    """Container holding aggregated memories and corpus metadata."""

    style_id: str
    memories: List[Dict[str, Any]]
    stats: CorpusStats
    formatted_prompt_corpus: str


class StyleAggregator:
    """
    Aggregates VideoMemory records for a given style_id from SQLite.
    """

    def aggregate_style_corpus(self, style_id: str) -> StyleCorpus:
        """
        Query and format all VideoMemory records associated with a style_id.

        Args:
            style_id: Target style identifier (e.g. 'default_style', 'desi_comedy').

        Returns:
            StyleCorpus containing memory list, computed metrics, and prompt text.

        Raises:
            ValueError: If no VideoMemory records exist for the specified style_id.
        """
        with get_db_session() as session:
            # Query memories linked by style_id or referenced via StyleReference
            memories_by_style = (
                session.query(VideoMemory)
                .filter(VideoMemory.style_id == style_id)
                .all()
            )

            # Also check if any memories are linked through StyleReference
            referenced_ids = [
                ref.video_id
                for ref in session.query(StyleReference).filter_by(style_id=style_id).all()
            ]

            all_memories = {m.video_id: m for m in memories_by_style}
            if referenced_ids:
                additional_mems = (
                    session.query(VideoMemory)
                    .filter(VideoMemory.video_id.in_(referenced_ids))
                    .all()
                )
                for am in additional_mems:
                    all_memories[am.video_id] = am

            records = list(all_memories.values())

            if not records:
                raise ValueError(
                    f"No VideoMemory records found for style '{style_id}'. "
                    "Ensure videos have been extracted and distilled into memories first."
                )

            # Detach/extract memory data while session is active
            memory_items = []
            for r in records:
                memory_items.append(
                    {
                        "video_id": r.video_id,
                        "style_id": r.style_id or style_id,
                        "memory_text": r.memory_text or "",
                        "metadata": r.metadata_json or {},
                    }
                )

        # Compute aggregate metrics across corpus
        video_ids = [item["video_id"] for item in memory_items]
        characters_counter = Counter()
        mechanisms_counter = Counter()
        settings_counter = Counter()
        pacing_counter = Counter()
        languages_counter = Counter()

        for item in memory_items:
            meta = item["metadata"]
            for ch in meta.get("characters", []):
                characters_counter[ch] += 1
            for mech in meta.get("comedy_mechanisms", []):
                mechanisms_counter[mech] += 1
            for st in meta.get("settings", []):
                settings_counter[st] += 1
            pace = meta.get("pacing")
            if pace:
                pacing_counter[pace] += 1
            lang = meta.get("language", "hi")
            languages_counter[lang] += 1

        dom_lang = languages_counter.most_common(1)[0][0] if languages_counter else "hi"

        stats = CorpusStats(
            total_memories=len(memory_items),
            video_ids=video_ids,
            unique_characters=[name for name, _ in characters_counter.most_common(10)],
            common_mechanisms=[m for m, _ in mechanisms_counter.most_common(10)],
            common_settings=[s for s, _ in settings_counter.most_common(10)],
            pacing_styles=[p for p, _ in pacing_counter.most_common(5)],
            dominant_language=dom_lang,
        )

        # Format prompt corpus text
        corpus_blocks = []
        for idx, item in enumerate(memory_items, 1):
            block = (
                f"--- REFERENCE VIDEO MEMORY {idx}/{len(memory_items)}: {item['video_id']} ---\n"
                f"{item['memory_text'].strip()}"
            )
            corpus_blocks.append(block)

        formatted_corpus = "\n\n".join(corpus_blocks)

        console.print(
            f"[bold cyan][STYLE AGGREGATOR][/bold cyan] Aggregated {len(memory_items)} "
            f"memories for style '[green]{style_id}[/green]'."
        )

        return StyleCorpus(
            style_id=style_id,
            memories=memory_items,
            stats=stats,
            formatted_prompt_corpus=formatted_corpus,
        )

