"""
app/fusion/timeline_aligner.py
Multimodal Timeline Aligner (Sub-Phase 3.5).

Loads evidence manifests across all modalities:
- Speech (ASR words & utterances)
- Shots (Scene cuts and visual rhythm)
- OCR (On-screen text overlays & hook text)
- Faces (Face tracks, bounding boxes & MAR speaking state)
- Diarization (Acoustic speaker turns)

Performs consensus, resolves acoustic speakers to visual face IDs,
and synthesizes the master chronological `timeline.json`.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from rich.console import Console

from app.fusion.consensus import SpeechConsensus
from app.fusion.speaker_resolver import SpeakerResolver

console = Console()


class TimelineAligner:
    """
    Fuses multimodal events from independent capability manifests into
    a unified, synchronized master timeline.
    """

    def __init__(self, data_root: str = "data"):
        self.data_root = Path(data_root)
        self.consensus = SpeechConsensus()
        self.speaker_resolver = SpeakerResolver()

    def load_manifests(self, reel_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Discover and load all capability manifests for a given reel."""
        reel_dir = self.data_root / "reels" / reel_id
        if not reel_dir.exists():
            raise FileNotFoundError(f"Reel directory not found: {reel_dir}")

        manifests: Dict[str, List[Dict[str, Any]]] = {
            "speech": [],
            "shots": [],
            "ocr": [],
            "faces": [],
            "diarization": [],
        }

        for path in reel_dir.glob("manifest_*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cap = data.get("capability")
                    if cap in manifests:
                        manifests[cap].append(data)
            except Exception as e:
                console.print(f"[yellow]Warning: Could not read {path.name}: {e}[/yellow]")

        return manifests

    def align(self, reel_id: str) -> Dict[str, Any]:
        """
        Execute multimodal alignment and generate master timeline.json.
        """
        reel_dir = self.data_root / "reels" / reel_id
        console.print(f"[bold cyan][MULTIMODAL FUSION][/bold cyan] Aligning lanes for [green]{reel_id}[/green]...")

        manifests = self.load_manifests(reel_id)

        # 1. Resolve speech consensus
        speech_result = self.consensus.resolve(manifests["speech"])
        words = speech_result.get("words", [])
        utterances = speech_result.get("utterances", [])

        # 2. Extract shots
        shot_events: List[Dict[str, Any]] = []
        shot_metrics: Dict[str, Any] = {}
        if manifests["shots"]:
            best_shot_manifest = manifests["shots"][0]
            shot_events = best_shot_manifest.get("events", [])
            shot_metrics = best_shot_manifest.get("raw_payload", {}).get("metrics", {})

        # 3. Extract OCR overlays
        ocr_events: List[Dict[str, Any]] = []
        ocr_metrics: Dict[str, Any] = {}
        if manifests["ocr"]:
            best_ocr_manifest = manifests["ocr"][0]
            ocr_events = best_ocr_manifest.get("events", [])
            ocr_metrics = best_ocr_manifest.get("raw_payload", {}).get("metrics", {})

        # 4. Extract Face tracks
        face_events: List[Dict[str, Any]] = []
        face_metrics: Dict[str, Any] = {}
        if manifests["faces"]:
            best_face_manifest = manifests["faces"][0]
            face_events = best_face_manifest.get("events", [])
            face_metrics = best_face_manifest.get("raw_payload", {}).get("metrics", {})

        # 5. Extract Diarization turns
        diarization_events: List[Dict[str, Any]] = []
        if manifests["diarization"]:
            best_diar_manifest = manifests["diarization"][0]
            diarization_events = best_diar_manifest.get("events", [])

        # 6. Speaker Resolver: Correlate audio diarization with visual faces
        resolution = self.speaker_resolver.resolve(diarization_events, face_events)
        speaker_to_face = resolution.get("speaker_to_face", {})

        # 7. Annotate speech utterances and words with resolved face identities
        annotated_utterances = []
        for utt in utterances:
            u = dict(utt)
            p = dict(u.get("payload", {}))
            spk = p.get("speaker")
            # Map raw speaker (e.g. 'A', 'B') to canonical (e.g. 'SPEAKER_00', 'SPEAKER_01')
            canonical_spk = spk
            if spk and not str(spk).startswith("SPEAKER"):
                if len(str(spk)) == 1 and str(spk).isalpha():
                    idx = ord(str(spk).upper()) - ord('A')
                    canonical_spk = f"SPEAKER_{idx:02d}"
                else:
                    canonical_spk = f"SPEAKER_00"
            matched_face = speaker_to_face.get(canonical_spk) or speaker_to_face.get(spk)
            p["speaker_canonical"] = canonical_spk
            p["resolved_face_id"] = matched_face
            p["is_on_screen"] = matched_face is not None
            u["payload"] = p
            annotated_utterances.append(u)

        # 8. Calculate unified duration & Pacing DNA
        max_ts = 0
        for track_list in [words, utterances, shot_events, ocr_events, face_events, diarization_events]:
            for ev in track_list:
                max_ts = max(max_ts, ev.get("end_ms", 0))

        duration_ms = max_ts
        duration_sec = duration_ms / 1000.0 if duration_ms > 0 else 1.0

        total_words = len(words)
        wpm = round((total_words / (duration_sec / 60.0)), 1) if duration_sec > 0 else 0.0

        pacing_dna = {
            "duration_ms": duration_ms,
            "duration_sec": round(duration_sec, 2),
            "pacing": {
                "total_shots": shot_metrics.get("total_shots", len(shot_events)),
                "avg_shot_duration_sec": shot_metrics.get("avg_shot_duration_sec", round(duration_sec / max(1, len(shot_events)), 2)),
                "hook_shot_duration_sec": shot_metrics.get("hook_shot_duration_sec", 0.0),
            },
            "speech": {
                "total_words": total_words,
                "words_per_minute": wpm,
                "primary_asr": speech_result.get("provider_used", "none"),
                "total_utterances": len(annotated_utterances),
            },
            "visuals": {
                "ocr_coverage_pct": ocr_metrics.get("text_coverage_pct", 0.0),
                "total_text_overlays": len(ocr_events),
                "face_on_screen_pct": face_metrics.get("face_coverage_pct", 0.0),
                "visual_speech_pct": face_metrics.get("speaking_coverage_pct", 0.0),
                "total_face_tracks": len(face_events),
            },
            "speakers": {
                "unique_speakers_detected": len(speaker_to_face),
                "speaker_resolution": resolution.get("details", {}),
            },
        }

        # 9. Master Timeline Object
        timeline = {
            "reel_id": reel_id,
            "version": "1.0.0",
            "duration_ms": duration_ms,
            "duration_sec": round(duration_sec, 2),
            "pacing_dna": pacing_dna,
            "resolved_speakers": resolution,
            "tracks": {
                "speech_words": words,
                "speech_utterances": annotated_utterances,
                "shots": shot_events,
                "ocr": ocr_events,
                "faces": face_events,
                "diarization": diarization_events,
            },
        }

        # 10. Save to disk
        out_path = reel_dir / "timeline.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(timeline, f, indent=2, ensure_ascii=False)

        console.print(f"[bold green]✓ Master timeline generated & saved to {out_path.name}[/bold green]")
        return timeline
