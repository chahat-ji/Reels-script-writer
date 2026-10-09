"""
app/generation/context.py
Adaptive generation context assembler.

Implements the hybrid context strategy:
- Default Ground Model (<= 10 videos): Direct all-in-context (0 embedding API calls).
- Dynamic Vector Model (> 10 videos): NumPy cosine similarity retrieves the Top 10
  most relevant Video Memories for the premise.
Enforces comedic structure and strict negative anti-plagiarism guardrails.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from app.core.config import console
from app.core.database import get_db_session
from app.memory.index import VectorRetriever
from app.models.schema import Style, VideoMemory


SCRIPT_GENERATION_SYSTEM_PROMPT = """You are an elite television and digital sketch comedy writer.
Your job is to write an original, high-energy 60-second comedy screenplay based on a NEW USER PREMISE.

You are provided with:
1. The creator's master STYLE BIBLE (defining language register, dialogue rhythm, comedic escalation engine, and endings).
2. Up to 10 REFERENCE VIDEO MEMORIES (demonstrating previous successful sketches in this style).

CRITICAL CREATIVE MANDATES:
1. ORIGINALITY & ANTI-PLAGIARISM:
   - Create a completely brand-new, original scenario based strictly on the NEW PREMISE.
   - DO NOT copy, reuse, or parody the specific plot, theft, secret, or con from the reference memories.
   - The reference memories are for TONE, DIALOGUE DENSITY, PACING, and COMEDIC REACTION TIMING only.

2. STYLE EXECUTION:
   - Apply the COMEDY ENGINE from the Style Bible (Normal situation → Confident assertion → Reaction → Objection → Escalation → Reversal).
   - Match the LANGUAGE & REGISTER specified (e.g., snappy colloquial Hindi/Hinglish, short lines, rapid interruptions).
   - Keep dialogue turns brief (1-2 sentences maximum per turn).

3. SCREENPLAY FORMAT:
   - Include clear Scene Sluglines (e.g. INT. LIVING ROOM - DAY).
   - Include character action descriptions and physical comedy cues.
   - Deliver a punchy, abrupt ending punchline.
"""


@dataclass
class GenerationContext:
    """Encapsulates the assembled generation prompt and retrieval metadata."""

    style_id: str
    premise: str
    retrieval_mode: str  # 'direct_all' or 'dynamic_vector_top10'
    memory_count: int
    system_instruction: str
    user_prompt: str


class ContextBuilder:
    """
    Assembles the RAG context for screenplay generation.
    """

    def __init__(self, retriever: Optional[VectorRetriever] = None):
        self.retriever = retriever or VectorRetriever()

    def build_context(self, style_id: str, premise: str) -> GenerationContext:
        """
        Build the generation prompt context using adaptive memory selection.

        Args:
            style_id: Target creator style ID.
            premise: User's concept or premise for the new sketch.

        Returns:
            GenerationContext ready for LLM execution.
        """
        clean_premise = premise.strip()
        if not clean_premise:
            raise ValueError("Premise cannot be empty.")

        with get_db_session() as session:
            style = session.query(Style).filter_by(style_id=style_id).first()
            if not style or not style.bible_text:
                raise ValueError(
                    f"Creator style '{style_id}' does not have a synthesized Style Bible yet. "
                    "Run style synthesis before generating scripts."
                )
            bible_text = style.bible_text
            creator_name = style.name or style_id

            # Count total memories for this style
            total_memories = session.query(VideoMemory).filter_by(style_id=style_id).count()

        if total_memories == 0:
            raise ValueError(
                f"No Video Memories found for style '{style_id}'. "
                "Upload and index reference videos before generating scripts."
            )

        # Adaptive Retrieval Strategy
        if total_memories <= 10:
            # Default Ground Model: Load all available memories directly (0 embedding calls)
            retrieval_mode = "direct_all"
            with get_db_session() as session:
                memories = session.query(VideoMemory).filter_by(style_id=style_id).all()
                memory_texts = [
                    f"--- REFERENCE MEMORY {idx}/{len(memories)}: {m.video_id} ---\n{m.memory_text.strip()}"
                    for idx, m in enumerate(memories, 1)
                ]
            console.print(
                f"[bold cyan][CONTEXT BUILDER][/bold cyan] Creator '{creator_name}' has {total_memories} videos "
                f"(<= 10). Using [green]Default Ground Model[/green] (all {len(memory_texts)} memories in context, 0 embedding calls)."
            )
        else:
            # Dynamic Retrieval Model: Use NumPy cosine similarity to get top 10 matching memories
            retrieval_mode = "dynamic_vector_top10"
            matches = self.retriever.search_memories(style_id=style_id, query=clean_premise, top_k=10)
            memory_texts = [
                f"--- REFERENCE MEMORY {idx}/{len(matches)}: {m.video_id} (Score: {m.score:.3f}) ---\n{m.memory_text.strip()}"
                for idx, m in enumerate(matches, 1)
            ]
            console.print(
                f"[bold cyan][CONTEXT BUILDER][/bold cyan] Creator '{creator_name}' has {total_memories} videos "
                f"(> 10). Using [magenta]Dynamic Vector Model[/magenta] (retrieved Top {len(memory_texts)} relevant memories)."
            )

        examples_section = "\n\n".join(memory_texts)

        user_prompt = (
            f"STYLE BIBLE (CREATOR: {creator_name.upper()} | STYLE ID: {style_id}):\n"
            f"============================================================\n"
            f"{bible_text.strip()}\n\n"
            f"REFERENCE EXAMPLES FROM THIS CREATOR (DO NOT COPY PLOTS):\n"
            f"============================================================\n"
            f"{examples_section}\n\n"
            f"NEW SKETCH PREMISE:\n"
            f"============================================================\n"
            f"{clean_premise}\n\n"
            f"ASSIGNMENT:\n"
            f"Write a complete, original 60-second comedy screenplay following the Style Bible rules. "
            f"Output the formatted screenplay now:"
        )

        return GenerationContext(
            style_id=style_id,
            premise=clean_premise,
            retrieval_mode=retrieval_mode,
            memory_count=len(memory_texts),
            system_instruction=SCRIPT_GENERATION_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

