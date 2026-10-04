"""
app/capabilities/speech/providers/mlx_whisper.py
Local Apple Silicon Whisper transcription via MLX with native script output and anti-loop guards.
"""

import os
import re
from typing import Any, Dict, List, Optional
from rich.console import Console

from app.capabilities.base import (
    Provider,
    Requirements,
    Health,
    Estimate,
    ProviderResult,
    CanonicalEvent,
)

console = Console()

DEFAULT_MLX_MODEL = "mlx-community/whisper-large-v3-mlx"


def suppress_repetition_loops(text: str, max_repeat: int = 2) -> str:
    """
    Collapses runaway token/word repetition loops (e.g. 'जो जो जो जो...')
    caused by Whisper decoding on non-speech or background silence.
    """
    if not text:
        return text
    # Matches any word repeated more than max_repeat times consecutively
    pattern = re.compile(r"(\b\S+\b)(?:\s+\1){" + str(max_repeat) + r",}")
    return pattern.sub(r"\1", text).strip()


class MLXWhisperProvider(Provider):
    capability = "speech"
    name = "mlx_whisper"
    version = "1.3.0"
    tier = "local"
    requirements = Requirements(
        min_ram_gb=4.0,
        needs_gpu=True,
        api_key_env=None,
        languages=["en", "hi"],
    )

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or os.getenv("MLX_WHISPER_MODEL", DEFAULT_MLX_MODEL)

    def health(self) -> Health:
        try:
            import mlx_whisper
            return Health(installed=True, key_present=True, enough_ram=True)
        except ImportError as e:
            return Health(
                installed=False,
                key_present=True,
                enough_ram=True,
                error=f"mlx-whisper not installed: {e}",
            )

    def estimate(self, media_info: Dict[str, Any]) -> Estimate:
        duration_sec = media_info.get("duration_seconds", 60.0)
        expected_sec = max(3.0, duration_sec * 0.25)
        return Estimate(
            expected_cost_usd=0.0,
            expected_seconds=round(expected_sec, 1),
            peak_ram_gb=3.0,
        )

    def run(self, job: Dict[str, Any]) -> ProviderResult:
        import mlx_whisper

        audio_path = job.get("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        language = job.get("language")  # Can be "hi", "en", or None (auto)

        console.print(
            f"[bold magenta][MLX INFERENCE][/bold magenta] Model: [cyan]{self.model_name}[/cyan] "
            f"(Task: [yellow]transcribe[/yellow], Lang: [yellow]{language or 'auto'}[/yellow])"
        )

        # Build options dictionary with temperature fallback and hallucination suppression
        transcribe_kwargs = {
            "path_or_hf_repo": self.model_name,
            "task": "transcribe",
            "word_timestamps": True,
            "condition_on_previous_text": False,
            "compression_ratio_threshold": 2.2,
            "no_speech_threshold": 0.6,
            "logprob_threshold": -1.0,
            "temperature": (0.0, 0.2, 0.4, 0.6, 0.8),
            "hallucination_silence_threshold": 2.0,
            "initial_prompt": "Conversational Hindi and English dialogue in Indian context.",
        }
        if language:
            transcribe_kwargs["language"] = language

        result = mlx_whisper.transcribe(audio_path, **transcribe_kwargs)

        detected_language = result.get("language", language or "unknown")
        console.print(f"[dim]Language Used: {detected_language}[/dim]")

        events: List[CanonicalEvent] = []
        punctuation_chars = ".,!?;:\"'()[]{}<>।॥«»“”"

        for segment in result.get("segments", []):
            raw_utt_text = segment.get("text", "").strip()
            if not raw_utt_text:
                continue

            clean_utt_text = suppress_repetition_loops(raw_utt_text)

            events.append(
                CanonicalEvent(
                    track="speech",
                    start_ms=int(segment["start"] * 1000),
                    end_ms=int(segment["end"] * 1000),
                    type="utterance",
                    payload={"text": clean_utt_text, "raw_text": raw_utt_text, "language": detected_language},
                    confidence=round(float(1.0 - segment.get("no_speech_prob", 0.0)), 3),
                    provider=self.name,
                    provider_version=self.version,
                )
            )

            consecutive_word = ""
            repeat_count = 0

            for word_obj in segment.get("words", []):
                raw_word = word_obj.get("word", "").strip()
                if not raw_word:
                    continue

                clean_token = raw_word.strip(punctuation_chars).strip()

                # Skip runaway repeating tokens in word stream
                if clean_token.lower() == consecutive_word.lower():
                    repeat_count += 1
                    if repeat_count > 2:
                        continue
                else:
                    consecutive_word = clean_token
                    repeat_count = 1

                events.append(
                    CanonicalEvent(
                        track="speech",
                        start_ms=int(word_obj["start"] * 1000),
                        end_ms=int(word_obj["end"] * 1000),
                        type="word",
                        payload={"text": clean_token or raw_word, "raw": raw_word},
                        confidence=round(float(word_obj.get("probability", 1.0)), 3),
                        provider=self.name,
                        provider_version=self.version,
                    )
                )

        full_text = suppress_repetition_loops(result.get("text", "").strip())
        raw_payload = {
            "text": full_text,
            "raw_text": result.get("text", "").strip(),
            "language": detected_language,
            "segment_count": len(result.get("segments", [])),
        }

        return ProviderResult(
            capability=self.capability,
            provider_name=self.name,
            provider_version=self.version,
            events=events,
            raw_payload=raw_payload,
            metadata={"audio_path": audio_path, "model": self.model_name},
        )