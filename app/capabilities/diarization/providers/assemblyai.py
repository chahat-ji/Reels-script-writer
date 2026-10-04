"""
app/capabilities/diarization/providers/assemblyai.py
AssemblyAI acoustic speaker diarization provider (Sub-Phase 3.4).

Provides robust, production-grade speaker diarization:
- Can reuse pre-computed speech manifest utterances if already present in reel cache.
- Otherwise transcribes audio with `speaker_labels=True` via AssemblyAI API.
- Standardizes speaker tags to `SPEAKER_00`, `SPEAKER_01`, etc.
- Emits standardized CanonicalEvent(track="diarization", type="speaker_turn").
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
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


class AssemblyAIDiarizationProvider(Provider):
    capability = "diarization"
    name = "assemblyai"
    version = "1.0.0"
    tier = "paid"
    requirements = Requirements(
        min_ram_gb=1.0,
        needs_gpu=False,
        api_key_env="ASSEMBLYAI_API_KEY",
    )

    def __init__(self):
        self.api_key = config.get_api_key("ASSEMBLYAI_API_KEY")
        if self.api_key:
            aai.settings.api_key = self.api_key

    def health(self) -> Health:
        if not self.api_key:
            return Health(
                installed=True,
                key_present=False,
                enough_ram=True,
                error="ASSEMBLYAI_API_KEY is not set in environment or .env file.",
            )
        return Health(installed=True, key_present=True, enough_ram=True)

    def estimate(self, media_info: Dict[str, Any]) -> Estimate:
        duration_sec = media_info.get("duration_seconds", 60.0)
        return Estimate(
            expected_cost_usd=round(duration_sec * 0.00025, 4),
            expected_seconds=max(3.0, round(duration_sec * 0.20, 1)),
            peak_ram_gb=0.5,
        )

    def run(self, job: Dict[str, Any]) -> ProviderResult:
        audio_path = job.get("audio_path")
        video_path = job.get("video_path")
        reel_dir = None

        if audio_path and os.path.exists(audio_path):
            reel_dir = Path(audio_path).parent
        elif video_path and os.path.exists(video_path):
            reel_dir = Path(video_path).parent
            audio_path = str(reel_dir / "audio.wav")

        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        console.print(
            f"[bold cyan][DIARIZATION (ASSEMBLYAI)][/bold cyan] Resolving speaker turns for "
            f"[green]{os.path.basename(audio_path)}[/green]..."
        )

        speaker_map: Dict[str, str] = {}
        raw_turns: List[Dict[str, Any]] = []

        # 1. Check if speech manifest from AssemblyAI already exists in reel directory
        cached_speech = None
        if reel_dir and reel_dir.exists():
            for f in reel_dir.glob("manifest_speech_assemblyai_*.json"):
                try:
                    with open(f, "r", encoding="utf-8") as fp:
                        cached_speech = json.load(fp)
                        console.print(f"[dim]  Reusing cached AssemblyAI utterances from {f.name}[/dim]")
                        break
                except Exception:
                    pass

        if cached_speech and "events" in cached_speech:
            # Extract utterance events that contain speaker information
            for ev in cached_speech["events"]:
                if ev.get("type") == "utterance":
                    raw_spk = ev.get("payload", {}).get("speaker") or "A"
                    raw_turns.append({
                        "start_ms": ev["start_ms"],
                        "end_ms": ev["end_ms"],
                        "speaker_raw": raw_spk,
                        "text": ev.get("payload", {}).get("text", ""),
                        "confidence": ev.get("confidence", 1.0),
                    })

        if not raw_turns:
            # Run live AssemblyAI transcription with speaker labels enabled
            transcriber_config = aai.TranscriptionConfig(
                punctuate=True,
                speaker_labels=True,
            )
            transcriber = aai.Transcriber()
            transcript = transcriber.transcribe(audio_path, config=transcriber_config)

            if transcript.status == aai.TranscriptStatus.error:
                raise RuntimeError(f"AssemblyAI diarization failed: {transcript.error}")

            if transcript.utterances:
                for utt in transcript.utterances:
                    raw_turns.append({
                        "start_ms": int(utt.start),
                        "end_ms": int(utt.end),
                        "speaker_raw": getattr(utt, "speaker", "A"),
                        "text": utt.text.strip(),
                        "confidence": round(float(getattr(utt, "confidence", 1.0) or 1.0), 3),
                    })

        # 2. Map speaker letters (A, B, C...) to canonical IDs (SPEAKER_00, SPEAKER_01...)
        def get_canonical_speaker(raw: str) -> str:
            if raw not in speaker_map:
                idx = len(speaker_map)
                speaker_map[raw] = f"SPEAKER_{idx:02d}"
            return speaker_map[raw]

        events: List[CanonicalEvent] = []
        speaker_turns: List[Dict[str, Any]] = []

        for i, turn in enumerate(raw_turns):
            spk_id = get_canonical_speaker(turn["speaker_raw"])
            duration_ms = turn["end_ms"] - turn["start_ms"]

            turn_payload = {
                "turn_index": i,
                "speaker": spk_id,
                "speaker_raw": turn["speaker_raw"],
                "start_ms": turn["start_ms"],
                "end_ms": turn["end_ms"],
                "duration_ms": duration_ms,
                "duration_sec": round(duration_ms / 1000.0, 2),
                "text": turn.get("text", ""),
            }
            speaker_turns.append(turn_payload)

            events.append(
                CanonicalEvent(
                    track="diarization",
                    start_ms=turn["start_ms"],
                    end_ms=turn["end_ms"],
                    type="speaker_turn",
                    payload=turn_payload,
                    confidence=turn.get("confidence", 0.95),
                    provider=self.name,
                    provider_version=self.version,
                )
            )

        unique_speakers = sorted(list(speaker_map.values()))
        total_speech_ms = sum(t["duration_ms"] for t in speaker_turns)

        metrics = {
            "total_speaker_turns": len(events),
            "unique_speakers": unique_speakers,
            "speaker_count": len(unique_speakers),
            "total_speech_duration_ms": total_speech_ms,
            "speaker_mapping": speaker_map,
        }

        console.print(
            f"[bold blue][DIARIZATION COMPLETE][/bold blue] Found [green]{len(unique_speakers)}[/green] speakers "
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
            },
        )
