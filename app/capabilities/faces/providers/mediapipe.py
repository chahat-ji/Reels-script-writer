"""
app/capabilities/faces/providers/mediapipe.py
MediaPipe FaceLandmarker implementation for Face & Active Speaker Tracking (Sub-Phase 3.3).

Features:
- Frame sampling at configurable rate (default: 5.0 fps)
- Face bounding box extraction [ymin, xmin, ymax, xmax] (normalized 0.0 - 1.0)
- Mouth Aspect Ratio (MAR) computation via inner/outer lip landmarks
- Active speaking classification (MAR > threshold or jawOpen blendshape)
- Multi-frame temporal tracking and speaking interval aggregation
- Standardized CanonicalEvent(track="face", type="face_track") emission
"""

import math
import os
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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

MODEL_URL = "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
MODEL_PATH = "data/models/face_landmarker.task"

DEFAULT_SAMPLE_FPS = 5.0             # 5 fps = 200ms per sample
DEFAULT_SPEAKING_MAR_THRESHOLD = 0.18 # MAR above this indicates open mouth/speech
DEFAULT_MAX_NUM_FACES = 4
DEFAULT_MIN_FACE_SIZE = 0.04         # Minimum face height/width as fraction of frame


def _ensure_model_downloaded() -> str:
    """Ensure the MediaPipe face_landmarker.task bundle is available locally."""
    model_file = Path(MODEL_PATH)
    if not model_file.exists():
        model_file.parent.mkdir(parents=True, exist_ok=True)
        console.print(f"[bold cyan][FACELANDMARKER][/bold cyan] Downloading model bundle to {model_file}...")
        urllib.request.urlretrieve(MODEL_URL, str(model_file))
        console.print(f"[green]✓ Model downloaded successfully ({model_file.stat().st_size // 1024} KB).[/green]")
    return str(model_file)


def _compute_bbox(landmarks, frame_w: int, frame_h: int) -> List[float]:
    """Compute normalized [ymin, xmin, ymax, xmax] bounding box from face landmarks."""
    xs = [lm.x for lm in landmarks]
    ys = [lm.y for lm in landmarks]
    ymin = max(0.0, round(min(ys), 4))
    xmin = max(0.0, round(min(xs), 4))
    ymax = min(1.0, round(max(ys), 4))
    xmax = min(1.0, round(max(xs), 4))
    return [ymin, xmin, ymax, xmax]


def _compute_mar(landmarks) -> float:
    """
    Compute Mouth Aspect Ratio (MAR):
    Vertical distance (landmark 13 to 14) / Horizontal distance (landmark 61 to 291).
    """
    try:
        p13 = (landmarks[13].x, landmarks[13].y)
        p14 = (landmarks[14].x, landmarks[14].y)
        p61 = (landmarks[61].x, landmarks[61].y)
        p291 = (landmarks[291].x, landmarks[291].y)

        vert = math.hypot(p13[0] - p14[0], p13[1] - p14[1])
        horiz = math.hypot(p61[0] - p291[0], p61[1] - p291[1])
        return round(vert / max(1e-6, horiz), 4)
    except (IndexError, AttributeError):
        return 0.0


def _bbox_center_dist(b1: List[float], b2: List[float]) -> float:
    """Euclidean distance between normalized centers of two bounding boxes."""
    c1 = ((b1[0] + b1[2]) / 2.0, (b1[1] + b1[3]) / 2.0)
    c2 = ((b2[0] + b2[2]) / 2.0, (b2[1] + b2[3]) / 2.0)
    return math.hypot(c1[0] - c2[0], c1[1] - c2[1])


class MediaPipeFaceProvider(Provider):
    capability = "faces"
    name = "mediapipe"
    version = "1.0.0"
    tier = "local"
    requirements = Requirements(
        min_ram_gb=1.5,
        needs_gpu=False,
        api_key_env=None,
    )

    def __init__(
        self,
        sample_fps: float = DEFAULT_SAMPLE_FPS,
        speaking_mar_threshold: float = DEFAULT_SPEAKING_MAR_THRESHOLD,
        max_num_faces: int = DEFAULT_MAX_NUM_FACES,
    ):
        self.sample_fps = sample_fps
        self.speaking_mar_threshold = speaking_mar_threshold
        self.max_num_faces = max_num_faces

    def health(self) -> Health:
        try:
            import cv2  # noqa: F401
            import mediapipe as mp  # noqa: F401
            from mediapipe.tasks.python.vision import FaceLandmarker  # noqa: F401
            return Health(installed=True, key_present=True, enough_ram=True)
        except ImportError as e:
            return Health(
                installed=False,
                key_present=True,
                enough_ram=True,
                error=f"MediaPipe/OpenCV dependency missing: {e}",
            )

    def estimate(self, media_info: Dict[str, Any]) -> Estimate:
        duration_sec = media_info.get("duration_seconds", 60.0)
        total_frames = duration_sec * self.sample_fps
        expected_sec = max(2.0, round(total_frames * 0.03, 1))
        return Estimate(
            expected_cost_usd=0.0,
            expected_seconds=expected_sec,
            peak_ram_gb=1.5,
        )

    def run(self, job: Dict[str, Any]) -> ProviderResult:
        os.environ["MPLCONFIGDIR"] = "/tmp"

        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

        video_path = job.get("video_path")
        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        sample_fps = float(job.get("sample_fps", self.sample_fps))
        mar_thresh = float(job.get("speaking_mar_threshold", self.speaking_mar_threshold))
        max_faces = int(job.get("max_num_faces", self.max_num_faces))

        model_file = _ensure_model_downloaded()

        console.print(
            f"[bold cyan][FACE TRACKING][/bold cyan] Analyzing faces & active speaker on "
            f"[green]{os.path.basename(video_path)}[/green] "
            f"(FPS: [yellow]{sample_fps}[/yellow] | MAR Threshold: [yellow]{mar_thresh}[/yellow])"
        )

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")

        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_ms = int((total_frames / video_fps) * 1000)
        frame_interval = max(1, int(video_fps / sample_fps))
        frame_interval_ms = int((frame_interval / video_fps) * 1000)

        # Initialize MediaPipe FaceLandmarker
        base_options = BaseOptions(model_asset_path=model_file)
        options = FaceLandmarkerOptions(
            base_options=base_options,
            output_face_blendshapes=True,
            num_faces=max_faces,
            running_mode=RunningMode.IMAGE,
        )
        detector = FaceLandmarker.create_from_options(options)

        # Track active face tracks: {track_id: list of per-frame detections}
        # Detection: {"frame_ms": int, "bbox": [...], "mar": float, "is_speaking": bool, "jaw_open": float}
        active_tracks: List[Dict[str, Any]] = []
        completed_tracks: List[Dict[str, Any]] = []
        next_track_id = 0

        frame_idx = 0
        frames_sampled = 0
        total_detections = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_interval == 0:
                frame_ms = int((frame_idx / video_fps) * 1000)
                h, w = frame.shape[:2]

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
                detection_result = detector.detect(mp_image)

                frame_faces = []
                if detection_result.face_landmarks:
                    for f_idx, lms in enumerate(detection_result.face_landmarks):
                        bbox = _compute_bbox(lms, w, h)
                        # Filter out tiny detections
                        if (bbox[2] - bbox[0]) < DEFAULT_MIN_FACE_SIZE or (bbox[3] - bbox[1]) < DEFAULT_MIN_FACE_SIZE:
                            continue

                        mar = _compute_mar(lms)
                        jaw_open = 0.0
                        if detection_result.face_blendshapes and f_idx < len(detection_result.face_blendshapes):
                            for b in detection_result.face_blendshapes[f_idx]:
                                if b.category_name == "jawOpen":
                                    jaw_open = round(b.score, 4)
                                    break

                        is_speaking = (mar >= mar_thresh) or (jaw_open >= 0.15)
                        frame_faces.append({
                            "frame_ms": frame_ms,
                            "bbox": bbox,
                            "mar": mar,
                            "jaw_open": jaw_open,
                            "is_speaking": is_speaking,
                        })

                total_detections += len(frame_faces)

                # Associate current frame faces with active tracks
                matched_tracks = set()
                unmatched_faces = list(frame_faces)

                for track in active_tracks:
                    last_det = track["detections"][-1]
                    # Find closest face in current frame
                    best_match = None
                    best_dist = 0.20  # Max center distance to match across frames

                    for face in unmatched_faces:
                        dist = _bbox_center_dist(last_det["bbox"], face["bbox"])
                        if dist < best_dist:
                            best_dist = dist
                            best_match = face

                    if best_match:
                        track["detections"].append(best_match)
                        matched_tracks.add(track["track_id"])
                        unmatched_faces.remove(best_match)

                # Move tracks that lost tracking to completed
                still_active = []
                for track in active_tracks:
                    if track["track_id"] in matched_tracks:
                        still_active.append(track)
                    else:
                        completed_tracks.append(track)
                active_tracks = still_active

                # Start new tracks for unmatched faces
                for face in unmatched_faces:
                    new_track = {
                        "track_id": f"face_{next_track_id}",
                        "detections": [face],
                    }
                    next_track_id += 1
                    active_tracks.append(new_track)

                frames_sampled += 1

            frame_idx += 1

        cap.release()
        detector.close()

        # Finalize remaining active tracks
        completed_tracks.extend(active_tracks)

        # Merge each track's detections into consolidated face spans
        events: List[CanonicalEvent] = []
        track_summaries: List[Dict[str, Any]] = []

        for track in completed_tracks:
            dets = track["detections"]
            if not dets:
                continue

            start_ms = dets[0]["frame_ms"]
            end_ms = dets[-1]["frame_ms"] + frame_interval_ms
            duration_track_ms = end_ms - start_ms

            # Filter tracks that appeared for only 1 frame if too short
            if len(dets) < 2 and duration_track_ms < 300:
                continue

            avg_mar = round(sum(d["mar"] for d in dets) / len(dets), 4)
            avg_jaw_open = round(sum(d["jaw_open"] for d in dets) / len(dets), 4)
            speaking_frames = sum(1 for d in dets if d["is_speaking"])
            speaking_ratio = round(speaking_frames / len(dets), 2)
            is_speaking = speaking_ratio >= 0.25

            # Compute median/average bounding box
            avg_bbox = [
                round(sum(d["bbox"][0] for d in dets) / len(dets), 4),
                round(sum(d["bbox"][1] for d in dets) / len(dets), 4),
                round(sum(d["bbox"][2] for d in dets) / len(dets), 4),
                round(sum(d["bbox"][3] for d in dets) / len(dets), 4),
            ]

            payload = {
                "face_id": track["track_id"],
                "bbox": avg_bbox,
                "is_speaking": is_speaking,
                "avg_mar": avg_mar,
                "avg_jaw_open": avg_jaw_open,
                "speaking_ratio": speaking_ratio,
                "speaking_frames": speaking_frames,
                "total_frames": len(dets),
                "duration_ms": duration_track_ms,
            }

            events.append(
                CanonicalEvent(
                    track="face",
                    start_ms=start_ms,
                    end_ms=end_ms,
                    type="face_track",
                    payload=payload,
                    confidence=round(min(1.0, 0.70 + (len(dets) * 0.05)), 2),
                    provider=self.name,
                    provider_version=self.version,
                )
            )

            track_summaries.append({
                "face_id": track["track_id"],
                "start_ms": start_ms,
                "end_ms": end_ms,
                "duration_sec": round(duration_track_ms / 1000.0, 2),
                "is_speaking": is_speaking,
                "avg_mar": avg_mar,
                "speaking_ratio": speaking_ratio,
                "bbox": avg_bbox,
            })

        # Pacing & Speaking Metrics
        total_face_duration_ms = sum(e.end_ms - e.start_ms for e in events)
        speaking_events = [e for e in events if e.payload.get("is_speaking", False)]
        total_speaking_duration_ms = sum(e.end_ms - e.start_ms for e in speaking_events)

        face_coverage_pct = round((total_face_duration_ms / max(1, duration_ms)) * 100, 1)
        speaking_coverage_pct = round((total_speaking_duration_ms / max(1, duration_ms)) * 100, 1)

        metrics = {
            "total_face_tracks": len(events),
            "speaking_face_tracks": len(speaking_events),
            "frames_sampled": frames_sampled,
            "total_raw_detections": total_detections,
            "video_duration_ms": duration_ms,
            "face_coverage_pct": face_coverage_pct,
            "speaking_coverage_pct": speaking_coverage_pct,
            "sample_fps": sample_fps,
            "speaking_mar_threshold": mar_thresh,
        }

        console.print(
            f"[bold blue][FACE TRACKING COMPLETE][/bold blue] "
            f"Found [green]{len(events)}[/green] face tracks "
            f"([yellow]{len(speaking_events)}[/yellow] actively speaking) | "
            f"Face On-Screen: [cyan]{face_coverage_pct}%[/cyan] | "
            f"Active Speech: [magenta]{speaking_coverage_pct}%[/magenta]"
        )

        return ProviderResult(
            capability=self.capability,
            provider_name=self.name,
            provider_version=self.version,
            events=events,
            raw_payload={
                "metrics": metrics,
                "tracks": track_summaries,
            },
            metadata={
                "video_path": video_path,
                "sample_fps": sample_fps,
                "speaking_mar_threshold": mar_thresh,
            },
        )
