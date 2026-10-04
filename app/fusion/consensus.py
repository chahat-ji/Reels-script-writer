"""
app/fusion/consensus.py
Consensus engine to resolve multi-ASR speech outputs into a unified speech track.
"""

from typing import Any, Dict, List, Optional


class SpeechConsensus:
    """
    Selects or merges the best speech transcription representation
    from multiple ASR providers (e.g. MLX Whisper and AssemblyAI).
    """

    def resolve(self, speech_manifests: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Takes one or more speech manifests, prioritizes by confidence,
        completeness, and native script fidelity.
        """
        if not speech_manifests:
            return {"words": [], "utterances": [], "provider_used": "none"}

        # If only one manifest exists, return its events directly
        if len(speech_manifests) == 1:
            m = speech_manifests[0]
            words = [e for e in m.get("events", []) if e.get("type") == "word"]
            utts = [e for e in m.get("events", []) if e.get("type") == "utterance"]
            return {
                "words": words,
                "utterances": utts,
                "provider_used": m.get("provider_name", "unknown"),
            }

        # If multiple manifests exist (e.g. mlx_whisper and assemblyai):
        # We prefer the one with highest average word confidence and utterance segmentation
        def score_manifest(m: Dict[str, Any]) -> float:
            words = [e for e in m.get("events", []) if e.get("type") == "word"]
            utts = [e for e in m.get("events", []) if e.get("type") == "utterance"]
            if not words:
                return 0.0
            avg_conf = sum(w.get("confidence", 0.0) for w in words) / len(words)
            utt_bonus = 0.2 if utts else 0.0
            return avg_conf + utt_bonus

        best_manifest = max(speech_manifests, key=score_manifest)
        words = [e for e in best_manifest.get("events", []) if e.get("type") == "word"]
        utts = [e for e in best_manifest.get("events", []) if e.get("type") == "utterance"]

        return {
            "words": words,
            "utterances": utts,
            "provider_used": best_manifest.get("provider_name", "unknown"),
        }
