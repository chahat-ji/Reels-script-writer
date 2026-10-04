"""
app/capabilities/ocr/providers/rapidocr.py
RapidOCR implementation for On-Screen Text Extraction (Sub-Phase 3.2).

Strategy:
- Sample video frames at a configurable FPS (default: 3.0)
- Run RapidOCR inference on each frame
- Merge consecutive frames with similar text into temporal spans
- Emit CanonicalEvent(track="ocr", type="text_overlay") per unique text region
"""

import os
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

# Defaults
DEFAULT_SAMPLE_FPS = 3.0          # Frames per second to sample
DEFAULT_MIN_CONFIDENCE = 0.60     # Minimum OCR confidence to keep a detection
DEFAULT_SIMILARITY_THRESHOLD = 0.75  # Normalized text overlap to merge across frames
DEFAULT_MIN_DURATION_MS = 200     # Ignore single-frame flickers shorter than this


def _normalize_text(text: str) -> str:
    """Lowercase and collapse whitespace for similarity comparisons."""
    return " ".join(text.lower().split())


def _text_similarity(a: str, b: str) -> float:
    """
    Token-level Jaccard similarity between two strings.
    Returns 0.0 (no overlap) to 1.0 (identical tokens).
    """
    if not a and not b:
        return 1.0
    tokens_a = set(_normalize_text(a).split())
    tokens_b = set(_normalize_text(b).split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


def _merge_spans(
    detections: List[Dict[str, Any]],
    similarity_threshold: float,
    min_duration_ms: int,
    frame_interval_ms: int = 333,
) -> List[Dict[str, Any]]:
    """
    Merge consecutive frame detections with similar text into time spans.

    Each detection: {"frame_ms": int, "text": str, "confidence": float, "bbox": list}

    Returns a list of merged spans:
    {"text": str, "start_ms": int, "end_ms": int, "confidence": float, "frame_count": int, "bbox": list}
    """
    if not detections:
        return []

    spans: List[Dict[str, Any]] = []
    current = dict(detections[0])
    current["start_ms"] = current["frame_ms"]
    current["end_ms"] = current["frame_ms"] + frame_interval_ms
    current["frame_count"] = 1

    for det in detections[1:]:
        sim = _text_similarity(current["text"], det["text"])
        if sim >= similarity_threshold:
            # Extend the current span
            current["end_ms"] = det["frame_ms"] + frame_interval_ms
            current["frame_count"] += 1
            # Update to the highest-confidence text in the span
            if det["confidence"] > current["confidence"]:
                current["text"] = det["text"]
                current["confidence"] = det["confidence"]
                current["bbox"] = det.get("bbox", current.get("bbox", []))
        else:
            # Finalize current span, start new one
            spans.append(current)
            current = dict(det)
            current["start_ms"] = current["frame_ms"]
            current["end_ms"] = current["frame_ms"] + frame_interval_ms
            current["frame_count"] = 1

    spans.append(current)

    # Filter out spans shorter than min_duration_ms
    spans = [s for s in spans if (s["end_ms"] - s["start_ms"]) >= min_duration_ms]

    return spans


class RapidOCRProvider(Provider):
    capability = "ocr"
    name = "rapidocr"
    version = "1.0.0"
    tier = "local"
    requirements = Requirements(
        min_ram_gb=1.0,
        needs_gpu=False,
        api_key_env=None,
    )

    def __init__(
        self,
        sample_fps: float = DEFAULT_SAMPLE_FPS,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
        min_duration_ms: int = DEFAULT_MIN_DURATION_MS,
    ):
        self.sample_fps = sample_fps
        self.min_confidence = min_confidence
        self.similarity_threshold = similarity_threshold
        self.min_duration_ms = min_duration_ms

    def health(self) -> Health:
        try:
            from rapidocr_onnxruntime import RapidOCR  # noqa: F401
            import cv2  # noqa: F401
            return Health(installed=True, key_present=True, enough_ram=True)
        except ImportError as e:
            return Health(
                installed=False,
                key_present=True,
                enough_ram=True,
                error=f"RapidOCR/OpenCV dependency missing: {e}",
            )

    def estimate(self, media_info: Dict[str, Any]) -> Estimate:
        duration_sec = media_info.get("duration_seconds", 60.0)
        total_frames = duration_sec * self.sample_fps
        # ~50ms per frame on CPU with ONNX
        expected_sec = max(2.0, round(total_frames * 0.05, 1))
        return Estimate(
            expected_cost_usd=0.0,
            expected_seconds=expected_sec,
            peak_ram_gb=1.2,
        )

    def run(self, job: Dict[str, Any]) -> ProviderResult:
        import cv2
        from rapidocr_onnxruntime import RapidOCR

        video_path = job.get("video_path")
        if not video_path or not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        sample_fps = float(job.get("sample_fps", self.sample_fps))
        min_confidence = float(job.get("min_confidence", self.min_confidence))
        similarity_threshold = float(job.get("similarity_threshold", self.similarity_threshold))
        min_duration_ms = int(job.get("min_duration_ms", self.min_duration_ms))

        console.print(
            f"[bold cyan][OCR][/bold cyan] Starting text extraction on "
            f"[green]{os.path.basename(video_path)}[/green] "
            f"(Sample: [yellow]{sample_fps} fps[/yellow] | MinConf: [yellow]{min_confidence}[/yellow])"
        )

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")

        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_ms = int((total_frames / video_fps) * 1000)
        frame_interval = max(1, int(video_fps / sample_fps))

        console.print(
            f"[dim]  Video FPS: {video_fps:.1f} | Total Frames: {total_frames} | "
            f"Sampling every {frame_interval} frames ({sample_fps:.1f} fps)[/dim]"
        )

        ocr_engine = RapidOCR()

        # Collect all per-frame detections
        all_detections: List[Dict[str, Any]] = []
        frame_idx = 0
        frames_sampled = 0

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_interval == 0:
                frame_ms = int((frame_idx / video_fps) * 1000)
                result, elapse = ocr_engine(frame)

                if result:
                    for item in result:
                        # result item format: [bbox_points, text, confidence]
                        if len(item) < 3:
                            continue
                        bbox_points, text, confidence = item[0], item[1], item[2]
                        if not text or not isinstance(text, str):
                            continue
                        conf = float(confidence) if confidence is not None else 0.0
                        if conf < min_confidence:
                            continue

                        # Normalize bbox to [ymin, xmin, ymax, xmax] as fractions
                        h, w = frame.shape[:2]
                        try:
                            xs = [p[0] / w for p in bbox_points]
                            ys = [p[1] / h for p in bbox_points]
                            bbox = [round(min(ys), 4), round(min(xs), 4),
                                    round(max(ys), 4), round(max(xs), 4)]
                        except Exception:
                            bbox = []

                        all_detections.append({
                            "frame_ms": frame_ms,
                            "frame_idx": frame_idx,
                            "text": text.strip(),
                            "confidence": conf,
                            "bbox": bbox,
                        })

                frames_sampled += 1

            frame_idx += 1

        cap.release()

        console.print(
            f"[dim]  Sampled {frames_sampled} frames | Raw detections: {len(all_detections)}[/dim]"
        )

        # Sort detections by time then spatial position (top-to-bottom)
        all_detections.sort(key=lambda d: (d["frame_ms"], d.get("bbox", [0])[0] if d.get("bbox") else 0))

        # Merge consecutive detections into spans
        frame_interval_ms = max(min_duration_ms, int((frame_interval / video_fps) * 1000))
        merged_spans = _merge_spans(all_detections, similarity_threshold, min_duration_ms, frame_interval_ms)

        console.print(
            f"[bold blue][OCR MERGED][/bold blue] {len(all_detections)} raw detections → "
            f"[green]{len(merged_spans)}[/green] text spans"
        )

        # Build CanonicalEvents
        events: List[CanonicalEvent] = []
        for i, span in enumerate(merged_spans):
            events.append(
                CanonicalEvent(
                    track="ocr",
                    start_ms=span["start_ms"],
                    end_ms=max(span["end_ms"], span["start_ms"] + min_duration_ms),
                    type="text_overlay",
                    payload={
                        "text": span["text"],
                        "bbox": span.get("bbox", []),
                        "frame_count": span["frame_count"],
                        "span_index": i,
                    },
                    confidence=round(span["confidence"], 4),
                    provider=self.name,
                    provider_version=self.version,
                )
            )

        # Summary statistics
        text_coverage_ms = sum(
            max(e.end_ms, e.start_ms + min_duration_ms) - e.start_ms
            for e in events
        )
        coverage_pct = round((text_coverage_ms / max(1, duration_ms)) * 100, 1)

        raw_payload = {
            "metrics": {
                "total_text_spans": len(events),
                "total_raw_detections": len(all_detections),
                "frames_sampled": frames_sampled,
                "video_duration_ms": duration_ms,
                "text_coverage_ms": text_coverage_ms,
                "text_coverage_pct": coverage_pct,
                "sample_fps": sample_fps,
            },
            "spans": [
                {
                    "span_index": e.payload["span_index"],
                    "text": e.payload["text"],
                    "start_ms": e.start_ms,
                    "end_ms": e.end_ms,
                    "duration_ms": e.end_ms - e.start_ms,
                    "confidence": e.confidence,
                    "bbox": e.payload.get("bbox", []),
                    "frame_count": e.payload["frame_count"],
                }
                for e in events
            ],
        }

        console.print(
            f"[bold green][OCR COMPLETE][/bold green] "
            f"[yellow]{len(events)}[/yellow] text overlay spans | "
            f"Coverage: [magenta]{coverage_pct}%[/magenta] of video"
        )

        return ProviderResult(
            capability=self.capability,
            provider_name=self.name,
            provider_version=self.version,
            events=events,
            raw_payload=raw_payload,
            metadata={
                "video_path": video_path,
                "sample_fps": sample_fps,
                "min_confidence": min_confidence,
                "similarity_threshold": similarity_threshold,
            },
        )
