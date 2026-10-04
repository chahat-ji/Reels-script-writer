"""
app/capabilities/speech/providers/assemblyai.py
AssemblyAI implementation of the Speech Provider interface.
"""

import os
from typing import Any, Dict, List
import assemblyai as aai
from rich.console import Console

from app.capabilities.base import (
    Provider,
    Requirements,
    Health,
    Estimate,
    ProviderResult,
    CanonicalEvent,
)
from app.core.config import config

console = Console()


class AssemblyAISpeechProvider(Provider):
    capability = "speech"
    name = "assemblyai"
    version = "1.0.0"
    tier = "paid"
    requirements = Requirements(
        min_ram_gb=1.0,
        needs_gpu=False,
        api_key_env="ASSEMBLYAI_API_KEY",
        languages=["en", "hi"],
    )

    def __init__(self):
        self.api_key = config.get_api_key(self.requirements.api_key_env)
        if self.api_key:
            aai.settings.api_key = self.api_key

    def health(self) -> Health:
        """Check if SDK is installed and valid API key is present."""
        if not self.api_key:
            return Health(
                installed=True,
                key_present=False,
                enough_ram=True,
                error="ASSEMBLYAI_API_KEY is not set in environment or .env file",
            )
        return Health(installed=True, key_present=True, enough_ram=True)

    def estimate(self, media_info: Dict[str, Any]) -> Estimate:
        """
        Estimate AssemblyAI cost and duration.
        AssemblyAI base pricing is roughly ~$0.00025 per second ($0.015/min).
        """
        duration_sec = media_info.get("duration_seconds", 60.0)
        expected_cost = duration_sec * 0.00025
        expected_sec = max(5.0, duration_sec * 0.25)  # typically 25% of audio duration
        return Estimate(
            expected_cost_usd=round(expected_cost, 4),
            expected_seconds=round(expected_sec, 1),
            peak_ram_gb=0.2,
        )

    def run(self, job: Dict[str, Any]) -> ProviderResult:
        """
        Transcribe audio file and normalize word/utterance tokens into CanonicalEvents.
        """
        audio_path = job.get("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        language_code = job.get("language_code", None)  # None allows auto-detection

        transcriber_config = aai.TranscriptionConfig(
            language_code=language_code,
            punctuate=True,
            format_text=True,
        )

        transcriber = aai.Transcriber()
        transcript = transcriber.transcribe(audio_path, config=transcriber_config)

        if transcript.status == aai.TranscriptStatus.error:
            raise RuntimeError(f"AssemblyAI transcription failed: {transcript.error}")

        events: List[CanonicalEvent] = []

        # 1. Normalize individual words
        if transcript.words:
            for word in transcript.words:
                events.append(
                    CanonicalEvent(
                        track="speech",
                        start_ms=int(word.start),
                        end_ms=int(word.end),
                        type="word",
                        payload={"text": word.text},
                        confidence=float(word.confidence or 1.0),
                        provider=self.name,
                        provider_version=self.version,
                    )
                )

        # 2. Normalize full utterances / sentences if present
        if transcript.utterances:
            for utt in transcript.utterances:
                events.append(
                    CanonicalEvent(
                        track="speech",
                        start_ms=int(utt.start),
                        end_ms=int(utt.end),
                        type="utterance",
                        payload={"text": utt.text, "speaker": getattr(utt, "speaker", None)},
                        confidence=float(utt.confidence or 1.0),
                        provider=self.name,
                        provider_version=self.version,
                    )
                )

        raw_payload = {
            "transcript_id": transcript.id,
            "text": transcript.text,
            "status": str(transcript.status),
            "words_count": len(transcript.words) if transcript.words else 0,
        }

        return ProviderResult(
            capability=self.capability,
            provider_name=self.name,
            provider_version=self.version,
            events=events,
            raw_payload=raw_payload,
            metadata={"audio_path": audio_path},
        )