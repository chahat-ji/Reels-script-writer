"""
app/style/synthesizer.py
Gemini LLM synthesizer for distilling a corpus of Video Memories into a canonical Style Bible.

Implements Sections 11 & 12 of description.txt:
Extracts common creative characteristics (Language, Register, Dialogue,
Character Dynamic, Comedy Engine, Common Devices, Pacing, Physical Comedy,
and Endings) into a versioned Style Bible Markdown artifact.
"""

import re
from typing import List, Optional
from google import genai
from google.genai import types

from app.core.config import console, settings
from app.style.aggregator import StyleCorpus

# The 8 canonical sections required by Section 11 of description.txt
REQUIRED_STYLE_SECTIONS: List[str] = [
    "LANGUAGE",
    "REGISTER",
    "DIALOGUE",
    "CHARACTER DYNAMIC",
    "COMEDY ENGINE",
    "COMMON COMEDIC DEVICES",
    "PACING",
    "PHYSICAL COMEDY",
    "ENDINGS",
]

STYLE_SYNTHESIS_SYSTEM_PROMPT = """You are an expert comedic dramaturg, script analyst, and showrunner.
Your task is to analyze a collection of creative "Video Memories" from a video reference library and synthesize a global "Style Bible".

A Style Bible captures the shared comedic, linguistic, and structural DNA across all reference videos in a concise, authoritative creative guide.

You MUST produce clean Markdown in the exact format below, with NO extra conversational chatter, introductory remarks, or concluding remarks:

STYLE BIBLE v{version}
STYLE ID: {style_id}

LANGUAGE
[State the predominant language, dialect, slang register, and code-switching patterns observed.]

REGISTER
[Describe the tone, conversational register, relationship dynamics, and formality level.]

DIALOGUE
[Describe the turn length, dialogue density, interruption behavior, rhythm, and exposition rules.]

CHARACTER DYNAMIC
[Describe the recurring character archetypes, status relationships, and conflict patterns.]

COMEDY ENGINE
[Outline the standard turn-by-turn comic progression using arrow steps:
Normal situation
→ confident assertion
→ reaction
→ objection
→ escalation
→ reversal/punchline.]

COMMON COMEDIC DEVICES
[Bulleted or line-by-line list of recurring comedic tropes, e.g., Teasing, Status reversal, Moral hypocrisy, Con-escalation, etc.]

PACING
[Describe the tempo, beat frequency, pause patterns, and comedic escalation speed.]

PHYSICAL COMEDY
[Describe the typical everyday physical actions, prop interactions, and visual comedic gestures.]

ENDINGS
[Describe how sketches typically conclude: reversals, sudden punchlines, status collapses, etc.]

Strictly adhere to the section headers in uppercase. Do not omit any section.
"""


class StyleSynthesizer:
    """
    Synthesizes a canonical Style Bible from an aggregated StyleCorpus using Gemini.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        client: Optional[genai.Client] = None,
    ):
        self.model_name = model_name or settings.synthesis_model
        if client:
            self.client = client
        else:
            resolved_key = api_key or settings.get_gemini_api_key()
            self.client = genai.Client(api_key=resolved_key)

    def synthesize_bible(self, corpus: StyleCorpus, target_version: int = 1) -> str:
        """
        Execute Gemini LLM synthesis to produce a canonical Style Bible.

        Args:
            corpus: Aggregated StyleCorpus containing memories and statistics.
            target_version: Version integer to brand the Style Bible with.

        Returns:
            Clean Markdown string adhering to Section 11 of description.txt.
        """
        system_instruction = STYLE_SYNTHESIS_SYSTEM_PROMPT.format(
            version=target_version,
            style_id=corpus.style_id,
        )

        user_prompt = (
            f"Synthesize the STYLE BIBLE v{target_version} for style '{corpus.style_id}'.\n\n"
            f"LIBRARY METRICS SUMMARY:\n"
            f"- Total Reference Videos: {corpus.stats.total_memories}\n"
            f"- Observed Characters: {', '.join(corpus.stats.unique_characters[:6])}\n"
            f"- Dominant Language: {corpus.stats.dominant_language}\n"
            f"- Top Comedy Mechanisms: {', '.join(corpus.stats.common_mechanisms[:6])}\n"
            f"- Pacing Styles: {', '.join(corpus.stats.pacing_styles[:3])}\n\n"
            f"REFERENCE VIDEO MEMORIES CORPUS:\n\n"
            f"{corpus.formatted_prompt_corpus}\n\n"
            f"Now output the complete STYLE BIBLE v{target_version} in the requested canonical format."
        )

        console.print(
            f"[bold cyan][STYLE SYNTHESIZER][/bold cyan] Synthesizing Style Bible v{target_version} "
            f"for '[green]{corpus.style_id}[/green]' with [magenta]{self.model_name}[/magenta]..."
        )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.3,
            max_output_tokens=3000,
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=user_prompt,
            config=config,
        )

        raw_text = response.text or ""
        cleaned_markdown = self._clean_markdown(raw_text, target_version, corpus.style_id)
        self._validate_sections(cleaned_markdown)

        return cleaned_markdown

    def _clean_markdown(self, text: str, version: int, style_id: str) -> str:
        """Strip enclosing code fences and normalize header formatting."""
        cleaned = text.strip()
        # Remove markdown code block wrappers if generated
        if cleaned.startswith("```markdown"):
            cleaned = cleaned[len("```markdown") :].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

        # Ensure header is present
        header = f"STYLE BIBLE v{version}\nSTYLE ID: {style_id}"
        if not cleaned.startswith(f"STYLE BIBLE v{version}"):
            cleaned = f"{header}\n\n{cleaned}"

        return cleaned

    def _validate_sections(self, markdown_text: str) -> None:
        """Check that all mandatory Section 11 headers exist in the output."""
        missing = []
        for sec in REQUIRED_STYLE_SECTIONS:
            pattern = rf"(?m)^#*\s*{re.escape(sec)}"
            if not re.search(pattern, markdown_text):
                missing.append(sec)

        if missing:
            console.print(
                f"[yellow][WARN][/yellow] Style Bible output is missing sections: {missing}"
            )

