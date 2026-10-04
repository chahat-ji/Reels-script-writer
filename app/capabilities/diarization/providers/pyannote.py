"""
app/capabilities/diarization/providers/pyannote.py
PyAnnote Audio implementation for Local Speaker Diarization (Sub-Phase 3.4).

Requirements:
- HF_TOKEN with accepted user conditions on:
  1. https://hf.co/pyannote/speaker-diarization-3.1
  2. https://hf.co/pyannote/segmentation-3.0
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import torch
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

DEFAULT_PIPELINE = "pyannote/speaker-diarization-3.1"


class PyAnnoteDiarizationProvider(Provider):
    capability = "diarization"
    name = "pyannote"
    version = "1.0.0"
    tier = "local"
    requirements = Requirements(
        min_ram_gb=2.0,
        needs_gpu=False,
        api_key_env="HF_TOKEN",
    )

    def __init__(self, pipeline_name: str = DEFAULT_PIPELINE):
        self.pipeline_name = pipeline_name
        self.token = config.get_api_key("HF_TOKEN") or config.get_api_key("HUGGING_FACE_HUB_TOKEN")

    def health(self) -> Health:
        try:
            import pyannote.audio  # noqa: F401
            import torch  # noqa: F401
        except ImportError as e:
            return Health(
                installed=False,
                key_present=bool(self.token),
                enough_ram=True,
                error=f"pyannote.audio dependency missing: {e}",
            )

        if not self.token:
            return Health(
                installed=True,
                key_present=False,
                enough_ram=True,
                error="HF_TOKEN environment variable is not set.",
            )

        return Health(installed=True, key_present=True, enough_ram=True)

    def estimate(self, media_info: Dict[str, Any]) -> Estimate:
        duration_sec = media_info.get("duration_seconds", 60.0)
        expected_sec = max(2.0, round(duration_sec * 0.15, 1))
        return Estimate(
            expected_cost_usd=0.0,
            expected_seconds=expected_sec,
            peak_ram_gb=2.0,
        )

    def run(self, job: Dict[str, Any]) -> ProviderResult:
        from pyannote.audio import Pipeline

        audio_path = job.get("audio_path")
        if not audio_path or not os.path.exists(audio_path):
            video_path = job.get("video_path")
            if video_path and os.path.exists(video_path):
                audio_path = str(Path(video_path).parent / "audio.wav")

        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        console.print(
            f"[bold cyan][DIARIZATION (PYANNOTE)][/bold cyan] Running acoustic clustering on "
            f"[green]{os.path.basename(audio_path)}[/green]..."
        )

        try:
            pipeline = Pipeline.from_pretrained(self.pipeline_name, token=self.token)
        except Exception as e:
            err_msg = str(e)
            if "gated repo" in err_msg.lower() or "401" in err_msg:
                console.print(
                    "[bold red][GATED MODEL ERROR][/bold red] PyAnnote requires accepting user conditions on HF:\n"
                    "  1. https://hf.co/pyannote/speaker-diarization-3.1\n"
                    "  2. https://hf.co/pyannote/segmentation-3.0"
                )
            raise RuntimeError(f"Failed to load PyAnnote pipeline: {e}")

        # Send to Metal MPS or CUDA if available
        if torch.backends.mps.is_available():
            try:
                pipeline.to(torch.device("mps"))
            except Exception:
                pipeline.to(torch.device("cpu"))
        elif torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))

        # Execute diarization
        diarization_output = pipeline(audio_path)

        events: List[CanonicalEvent] = []
        speaker_turns: List[Dict[str, Any]] = []

        # PyAnnote 3.x / 4.x output can be accessed via itertracks
        # Format: (turn, track, speaker)
        raw_tracks = list(diarization_output.itertracks(yield_label=True))

        for i, (turn, _, speaker) in enumerate(raw_tracks):
            start_ms = int(turn.start * 1000)
            end_ms = int(turn.end * 1000)
            duration_ms = end_ms - start_ms

            speaker_id = f"SPEAKER_{speaker}" if not str(speaker).startswith("SPEAKER") else str(speaker)

            turn_data = {
                "turn_index": i,
                "speaker": speaker_id,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_ms": duration_ms,
                "duration_sec": round(duration_ms / 1000.0, 2),
            }
            speaker_turns.append(turn_data)

            events.append(
                CanonicalEvent(
                    track="diarization",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    type="speaker_turn",
                    payload=turn_data,
                    confidence=0.90,
                    provider=self.name,
                    provider_version=self.version,
                )
            )

        unique_speakers = sorted(list({t["speaker"] for t in speaker_turns}))
        total_speech_ms = sum(t["duration_ms"] for t in speaker_turns)

        metrics = {
            "total_speaker_turns": len(events),
            "unique_speakers": unique_speakers,
            "speaker_count": len(unique_speakers),
            "total_speech_duration_ms": total_speech_ms,
        }

        console.print(
            f"[bold blue][DIARIZATION COMPLETE][/bold blue] Detected [green]{len(unique_speakers)}[/green] speakers "
            f"across [yellow]{len(events)}[/yellow] turns: {unique_speakers}"
        )

        return ProviderResult(
            capability=self.capability,
            provider_name=self.name,
            provider_version=self.version,
            events=events,
            raw_payload={
                "metrics": metrics,
                "turns": speaker_turns,
            },
            metadata={
                "audio_path": audio_path,
                "pipeline": self.pipeline_name,
            },
        )
