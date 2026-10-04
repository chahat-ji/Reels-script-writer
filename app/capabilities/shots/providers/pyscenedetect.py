"""
app/capabilities/shots/providers/pyscenedetect.py
PySceneDetect implementation for Shot Boundary Detection and Video Pacing Metrics.
"""

import os
from pathlib import Path
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

DEFAULT_THRESHOLD = 27.0


class PySceneDetectProvider(Provider):
    capability = "shots"
    name = "pyscenedetect"
    version = "1.0.0"
    tier = "local"
    requirements = Requirements(
        min_ram_gb=1.0,
        needs_gpu=False,
        api_key_env=None,
    )

    def __init__(self, threshold: float = DEFAULT_THRESHOLD):
        self.threshold = threshold

    def health(self) -> Health:
        try:
            import scenedetect
            import cv2
            return Health(installed=True, key_present=True, enough_ram=True)
        except ImportError as e:
            return Health(
                installed=False,
                key_present=True,
                enough_ram=True,
                error=f"PySceneDetect/OpenCV dependency missing: {e}",
            )

    def estimate(self, media_info: Dict[str, Any]) -> Estimate:
        duration_sec = media_info.get("duration_seconds", 60.0)
        expected_sec = max(1.0, round(duration_sec * 0.05, 1))
        return Estimate(
            expected_cost_usd=0.0,
            expected_seconds=expected_sec,
            peak_ram_gb=0.8,
        )

    def run(self, job: Dict[str, Any]) -> ProviderResult:
        from scenedetect import detect, ContentDetector

        video_path = job.get("video_path")
        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        threshold = job.get("threshold", self.threshold)
        console.print(
            f"[bold cyan][SHOT DETECTION][/bold cyan] Analyzing cuts for "
            f"[green]{os.path.basename(video_path)}[/green] (Threshold: [yellow]{threshold}[/yellow])..."
        )

        detector = ContentDetector(threshold=threshold)
        scene_list = detect(video_path, detector)

        events: List[CanonicalEvent] = []
        scenes_data: List[Dict[str, Any]] = []

        for i, (start_time, end_time) in enumerate(scene_list):
            start_ms = int(start_time.seconds * 1000)
            end_ms = int(end_time.seconds * 1000)
            duration_ms = end_ms - start_ms
            duration_sec = round(duration_ms / 1000.0, 2)

            scene_payload = {
                "scene_index": i,
                "duration_ms": duration_ms,
                "duration_sec": duration_sec,
                "start_frame": start_time.frame_num,
                "end_frame": end_time.frame_num,
            }
            scenes_data.append(scene_payload)

            events.append(
                CanonicalEvent(
                    track="shot",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    type="scene_cut",
                    payload=scene_payload,
                    confidence=1.0,
                    provider=self.name,
                    provider_version=self.version,
                )
            )

        total_shots = len(scene_list)
        total_duration_sec = round(scene_list[-1][1].seconds, 2) if scene_list else 0.0
        avg_shot_duration = round(total_duration_sec / max(1, total_shots), 2)
        hook_shot_duration = scenes_data[0]["duration_sec"] if scenes_data else 0.0

        pacing_metrics = {
            "total_shots": total_shots,
            "total_duration_sec": total_duration_sec,
            "avg_shot_duration_sec": avg_shot_duration,
            "hook_shot_duration_sec": hook_shot_duration,
        }

        console.print(
            f"[bold blue][SHOTS DETECTED][/bold blue] Found [green]{total_shots}[/green] shots | "
            f"ASD: [yellow]{avg_shot_duration}s[/yellow] | "
            f"Hook Shot: [magenta]{hook_shot_duration}s[/magenta]"
        )

        raw_payload = {
            "metrics": pacing_metrics,
            "scenes": scenes_data,
        }

        return ProviderResult(
            capability=self.capability,
            provider_name=self.name,
            provider_version=self.version,
            events=events,
            raw_payload=raw_payload,
            metadata={"video_path": video_path, "threshold": threshold},
        )
