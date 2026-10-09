"""
app/generation/generator.py
Gemini LLM generator producing original comedic screenplays.

Uses Gemini 3.8 Flash to transform the assembled GenerationContext (Style Bible +
10 Reference Memories + Premise) into an original, ready-to-shoot comedy screenplay.
"""

from typing import Optional
from google import genai
from google.genai import types

from app.core.config import console, settings
from app.generation.context import GenerationContext


class ScreenplayGenerator:
    """
    Invokes Gemini text model to synthesize an original screenplay.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        client: Optional[genai.Client] = None,
    ):
        self.model_name = model_name or settings.generation_model
        if client:
            self.client = client
        else:
            resolved_key = api_key or settings.get_gemini_api_key()
            self.client = genai.Client(api_key=resolved_key)

    def generate_screenplay(self, context: GenerationContext) -> str:
        """
        Execute screenplay generation with Gemini.

        Args:
            context: Assembled GenerationContext.

        Returns:
            Sanitized screenplay text.
        """
        console.print(
            f"[bold cyan][SCREENPLAY GENERATOR][/bold cyan] Generating script for "
            f"'{context.style_id}' with [magenta]{self.model_name}[/magenta] "
            f"(Context Mode: [green]{context.retrieval_mode}[/green], Memories: {context.memory_count})..."
        )

        config = types.GenerateContentConfig(
            system_instruction=context.system_instruction,
            temperature=0.7,  # Balanced creative humor and structural adherence
            max_output_tokens=4000,
        )

        import time
        max_attempts = 4
        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=context.user_prompt,
                    config=config,
                )
                break
            except Exception as err:
                last_error = err
                if attempt < max_attempts and ("503" in str(err) or "UNAVAILABLE" in str(err)):
                    console.print(f"[yellow][RETRY][/yellow] Transient 503 spike. Retrying in {attempt * 2}s (attempt {attempt}/{max_attempts})...")
                    time.sleep(attempt * 2)
                else:
                    raise

        raw_script = response.text or ""
        cleaned_script = self._clean_script(raw_script)

        return cleaned_script

    def _clean_script(self, text: str) -> str:
        """Clean markdown wrapping fences from generated script."""
        cleaned = text.strip()
        if cleaned.startswith("```markdown"):
            cleaned = cleaned[len("```markdown") :].strip()
        elif cleaned.startswith("```text"):
            cleaned = cleaned[len("```text") :].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
        return cleaned

