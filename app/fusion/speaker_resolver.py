"""
app/fusion/speaker_resolver.py
Resolves audio speaker diarization clusters to visible on-screen face tracks
by cross-correlating temporal overlap and Mouth Aspect Ratio (MAR).
"""

from typing import Any, Dict, List, Optional
from collections import defaultdict


class SpeakerResolver:
    """
    Correlates acoustic speaker turns with visual face tracks to determine
    which on-screen face corresponds to which acoustic voice cluster.
    """

    def resolve(
        self,
        diarization_events: List[Dict[str, Any]],
        face_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Takes diarization events and face events, calculates temporal and MAR overlap,
        and produces a 1-to-1 or 1-to-N mapping between speakers and faces.

        Returns:
            {
                "speaker_to_face": {"SPEAKER_00": "face_1", ...},
                "face_to_speaker": {"face_1": "SPEAKER_00", ...},
                "details": {
                    "SPEAKER_00": {
                        "face_id": "face_1",
                        "status": "matched" | "off_screen",
                        "overlap_ms": int,
                        "speaking_overlap_ms": int,
                        "confidence": float
                    }
                }
            }
        """
        if not diarization_events:
            return {"speaker_to_face": {}, "face_to_speaker": {}, "details": {}}

        # Affinity scores: affinity[speaker_id][face_id] = float
        affinity: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
        overlap_stats: Dict[str, Dict[str, Dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: {"total_ms": 0, "speaking_ms": 0}))

        all_speakers = set()
        all_faces = set()

        for d_ev in diarization_events:
            d_start = d_ev.get("start_ms", 0)
            d_end = d_ev.get("end_ms", 0)
            d_payload = d_ev.get("payload", {})
            spk_id = d_payload.get("speaker") or "SPEAKER_00"
            all_speakers.add(spk_id)

            for f_ev in face_events:
                f_start = f_ev.get("start_ms", 0)
                f_end = f_ev.get("end_ms", 0)
                f_payload = f_ev.get("payload", {})
                face_id = f_payload.get("face_id")
                if not face_id:
                    continue
                all_faces.add(face_id)

                # Compute temporal intersection
                overlap_start = max(d_start, f_start)
                overlap_end = min(d_end, f_end)
                overlap_ms = max(0, overlap_end - overlap_start)

                if overlap_ms > 0:
                    is_speaking = f_payload.get("is_speaking", False)
                    avg_mar = f_payload.get("avg_mar", 0.1)

                    overlap_stats[spk_id][face_id]["total_ms"] += overlap_ms
                    if is_speaking:
                        overlap_stats[spk_id][face_id]["speaking_ms"] += overlap_ms

                    # Weight by speaking state and mouth activity
                    weight = (3.0 if is_speaking else 0.5) * (1.0 + avg_mar * 2.0)
                    affinity[spk_id][face_id] += overlap_ms * weight

        # Greedy match: map each speaker to face with highest affinity
        speaker_to_face: Dict[str, Optional[str]] = {}
        face_to_speaker: Dict[str, Optional[str]] = {}
        details: Dict[str, Any] = {}

        for spk in sorted(all_speakers):
            face_scores = affinity[spk]
            if not face_scores:
                speaker_to_face[spk] = None
                details[spk] = {
                    "face_id": None,
                    "status": "off_screen",
                    "overlap_ms": 0,
                    "speaking_overlap_ms": 0,
                    "confidence": 0.0,
                }
                continue

            # Pick face with maximum affinity
            best_face = max(face_scores.items(), key=lambda item: item[1])[0]
            best_score = face_scores[best_face]
            stats = overlap_stats[spk][best_face]

            # Confidence based on speaking overlap vs total turn duration
            total_spk_duration = sum(
                ev.get("end_ms", 0) - ev.get("start_ms", 0)
                for ev in diarization_events
                if ev.get("payload", {}).get("speaker") == spk
            )
            ratio = stats["speaking_ms"] / max(1, total_spk_duration)
            conf = min(1.0, round(0.50 + ratio * 0.50, 2))

            # Threshold for considering off-screen
            if stats["total_ms"] < 200:
                speaker_to_face[spk] = None
                details[spk] = {
                    "face_id": None,
                    "status": "off_screen",
                    "overlap_ms": stats["total_ms"],
                    "speaking_overlap_ms": stats["speaking_ms"],
                    "confidence": 0.0,
                }
            else:
                speaker_to_face[spk] = best_face
                face_to_speaker[best_face] = spk
                details[spk] = {
                    "face_id": best_face,
                    "status": "matched",
                    "overlap_ms": stats["total_ms"],
                    "speaking_overlap_ms": stats["speaking_ms"],
                    "confidence": conf,
                }

        return {
            "speaker_to_face": speaker_to_face,
            "face_to_speaker": face_to_speaker,
            "details": details,
        }
