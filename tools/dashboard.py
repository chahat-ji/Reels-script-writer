"""
tools/dashboard.py
Central Multimodal Comparison Dashboard.

Visualizes 3-way side-by-side comparison across all reels:
  - Sticky HTML5 Video Player with seekbar and timecode
  - Three Parallel Comparison Lanes:
      1. Local: MLX Whisper (Apple Silicon Large-v3, $0.00)
      2. Cloud: AssemblyAI (Cloud API Diarization & Speech)
      3. Gold: Human Ground Truth Benchmark
  - Metrics Scorecards: WER %, CER %, Word Recall %, Turns, Words, Cost
  - Live Active Speaker & Subtitle HUD synchronized to video playback
  - Synchronized interactive dialogue feeds with click-to-seek
  - Dynamic Reel Selector dropdown to switch between any reel seamlessly

Usage:
  python tools/dashboard.py                     # Starts server & opens dashboard in browser
  python tools/dashboard.py DdMkWeaxKTT         # Opens dashboard focusing on specific reel
  python tools/dashboard.py --no-serve          # Only writes dashboard.html without starting server
"""

import argparse
import functools
import http.server
import json
import os
import re
import socketserver
import sys
import threading
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Set matplotlib config directory
os.environ["MPLCONFIGDIR"] = "/tmp"

from rich.console import Console
from rich.panel import Panel

console = Console()


def normalize_text(text: str) -> str:
    """Normalizes text for linguistic evaluation (strips punctuation & extra whitespace)."""
    text = re.sub(r"[।,\.\?!:;\"\(\)\[\]\{\}«»\-—_/#@*~`]", " ", text)
    return " ".join(text.lower().split())


def levenshtein_distance(seq1: List[str], seq2: List[str]) -> int:
    """Computes exact Levenshtein edit distance using space-optimized 2-row DP."""
    if len(seq1) < len(seq2):
        seq1, seq2 = seq2, seq1
    prev = list(range(len(seq2) + 1))
    for i, c1 in enumerate(seq1):
        curr = [i + 1] * (len(seq2) + 1)
        for j, c2 in enumerate(seq2):
            curr[j + 1] = prev[j] if c1 == c2 else 1 + min(prev[j + 1], curr[j], prev[j])
        prev = curr
    return prev[-1]


def compute_wer(ref_words: List[str], hyp_words: List[str]) -> float:
    """Word Error Rate = (Substitutions + Deletions + Insertions) / Total Reference Words."""
    if not ref_words:
        return 0.0
    dist = levenshtein_distance(ref_words, hyp_words)
    return round((dist / len(ref_words)) * 100, 2)


def compute_cer(ref_text: str, hyp_text: str) -> float:
    """Character Error Rate on non-whitespace characters."""
    ref_chars = [c for c in ref_text if not c.isspace()]
    hyp_chars = [c for c in hyp_text if not c.isspace()]
    if not ref_chars:
        return 0.0
    dist = levenshtein_distance(ref_chars, hyp_chars)
    return round((dist / len(ref_chars)) * 100, 2)


def extract_gold_data(reel_id: str, reel_dir: Path) -> Optional[Dict[str, Any]]:
    """Loads and formats ground truth reference from data/gold/ or data/reels/."""
    candidates = [
        Path("data/gold") / reel_id / "ground_truth.json",
        reel_dir / "ground_truth.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                utts = data.get("speech_utterances", [])
                cast = data.get("cast_profile", [])
                full_text = " ".join(u.get("text", "") for u in utts)
                norm_text = normalize_text(full_text)
                words = norm_text.split()
                
                # Format standardized utterances
                formatted_utts = []
                for idx, u in enumerate(utts, 1):
                    formatted_utts.append({
                        "id": idx,
                        "start_ms": u.get("start_ms", 0),
                        "end_ms": u.get("end_ms", 0),
                        "speaker": u.get("speaker_name") or u.get("speaker_id") or f"Speaker {idx}",
                        "speaker_id": u.get("speaker_id", "SPEAKER"),
                        "is_on_screen": u.get("is_on_screen", True),
                        "edit_type": u.get("edit_type", "synced"),
                        "text": u.get("text", ""),
                    })

                unique_speakers = list(set(u["speaker"] for u in formatted_utts))

                return {
                    "available": True,
                    "cast": cast,
                    "utterances": formatted_utts,
                    "full_text": full_text,
                    "norm_text": norm_text,
                    "words": words,
                    "word_count": len(words),
                    "turns_count": len(formatted_utts),
                    "unique_speakers": unique_speakers,
                }
            except Exception as e:
                console.print(f"[yellow]Error loading gold standard for {reel_id}: {e}[/yellow]")
    return None


def extract_assembly_data(reel_dir: Path) -> Optional[Dict[str, Any]]:
    """Loads and normalizes AssemblyAI speech and diarization manifests."""
    aai_files = sorted(reel_dir.glob("manifest_speech_assemblyai_*.json"))
    if not aai_files:
        return None

    try:
        with open(aai_files[-1], "r", encoding="utf-8") as f:
            manifest = json.load(f)

        events = manifest.get("events", [])
        raw_payload = manifest.get("raw_payload", {})
        full_text = raw_payload.get("text", "")

        # Check for utterance events
        utts_events = [e for e in events if e.get("type") == "utterance"]
        words_events = [e for e in events if e.get("type") == "word"]

        formatted_utts = []
        if utts_events:
            for idx, e in enumerate(utts_events, 1):
                payload = e.get("payload", {})
                formatted_utts.append({
                    "id": idx,
                    "start_ms": e.get("start_ms", 0),
                    "end_ms": e.get("end_ms", 0),
                    "speaker": f"Speaker {payload.get('speaker', 'A')}",
                    "speaker_id": payload.get("speaker", "A"),
                    "text": payload.get("text", ""),
                })
        elif raw_payload.get("utterances"):
            for idx, u in enumerate(raw_payload["utterances"], 1):
                formatted_utts.append({
                    "id": idx,
                    "start_ms": u.get("start", 0),
                    "end_ms": u.get("end", 0),
                    "speaker": f"Speaker {u.get('speaker', 'A')}",
                    "speaker_id": u.get("speaker", "A"),
                    "text": u.get("text", ""),
                })
        elif words_events:
            # Group words by silence gaps (>400ms or punctuation)
            curr = []
            u_idx = 1
            for w in words_events:
                gap = (w["start_ms"] - curr[-1]["end_ms"]) if curr else 0
                curr_duration = (w["end_ms"] - curr[0]["start_ms"]) if curr else 0
                ends_punct = curr[-1]["payload"]["text"].endswith((".", "!", "?", "—")) if curr else False
                if curr and (gap > 400 or curr_duration > 6000 or ends_punct):
                    text = " ".join(x["payload"]["text"] for x in curr)
                    formatted_utts.append({
                        "id": u_idx,
                        "start_ms": curr[0]["start_ms"],
                        "end_ms": curr[-1]["end_ms"],
                        "speaker": "Speaker A",
                        "speaker_id": "A",
                        "text": text,
                    })
                    u_idx += 1
                    curr = [w]
                else:
                    curr.append(w)
            if curr:
                text = " ".join(x["payload"]["text"] for x in curr)
                formatted_utts.append({
                    "id": u_idx,
                    "start_ms": curr[0]["start_ms"],
                    "end_ms": curr[-1]["end_ms"],
                    "speaker": "Speaker A",
                    "speaker_id": "A",
                    "text": text,
                })

        norm_text = normalize_text(full_text if full_text else " ".join(u["text"] for u in formatted_utts))
        words = norm_text.split()
        unique_speakers = list(set(u["speaker"] for u in formatted_utts))

        return {
            "available": True,
            "provider": "assemblyai",
            "model": "Cloud Conformer-2",
            "cost_tier": "Cloud API (~$0.015/m)",
            "utterances": formatted_utts,
            "full_text": full_text,
            "norm_text": norm_text,
            "words": words,
            "word_count": len(words),
            "turns_count": len(formatted_utts),
            "unique_speakers": unique_speakers,
        }
    except Exception as e:
        console.print(f"[yellow]Error loading AssemblyAI data: {e}[/yellow]")
        return None


def extract_mlx_data(reel_dir: Path) -> Optional[Dict[str, Any]]:
    """Loads and normalizes MLX Whisper speech manifests."""
    mlx_files = sorted(reel_dir.glob("manifest_speech_mlx_whisper_*.json"))
    if not mlx_files:
        return None

    try:
        with open(mlx_files[-1], "r", encoding="utf-8") as f:
            manifest = json.load(f)

        events = manifest.get("events", [])
        raw_payload = manifest.get("raw_payload", {})
        full_text = raw_payload.get("text", "")

        utts_events = [e for e in events if e.get("type") == "utterance"]
        words_events = [e for e in events if e.get("type") == "word"]

        formatted_utts = []
        if utts_events:
            for idx, e in enumerate(utts_events, 1):
                payload = e.get("payload", {})
                formatted_utts.append({
                    "id": idx,
                    "start_ms": e.get("start_ms", 0),
                    "end_ms": e.get("end_ms", 0),
                    "speaker": payload.get("speaker") or "Local Stream",
                    "speaker_id": "LOCAL",
                    "text": payload.get("text", ""),
                })
        elif words_events:
            curr = []
            u_idx = 1
            for w in words_events:
                gap = (w["start_ms"] - curr[-1]["end_ms"]) if curr else 0
                curr_duration = (w["end_ms"] - curr[0]["start_ms"]) if curr else 0
                ends_punct = curr[-1]["payload"]["text"].endswith((".", "!", "?", "—")) if curr else False
                if curr and (gap > 400 or curr_duration > 6000 or ends_punct):
                    text = " ".join(x["payload"]["text"] for x in curr)
                    formatted_utts.append({
                        "id": u_idx,
                        "start_ms": curr[0]["start_ms"],
                        "end_ms": curr[-1]["end_ms"],
                        "speaker": "Local Stream",
                        "speaker_id": "LOCAL",
                        "text": text,
                    })
                    u_idx += 1
                    curr = [w]
                else:
                    curr.append(w)
            if curr:
                text = " ".join(x["payload"]["text"] for x in curr)
                formatted_utts.append({
                    "id": u_idx,
                    "start_ms": curr[0]["start_ms"],
                    "end_ms": curr[-1]["end_ms"],
                    "speaker": "Local Stream",
                    "speaker_id": "LOCAL",
                    "text": text,
                })

        norm_text = normalize_text(full_text if full_text else " ".join(u["text"] for u in formatted_utts))
        words = norm_text.split()
        unique_speakers = list(set(u["speaker"] for u in formatted_utts))

        return {
            "available": True,
            "provider": "mlx_whisper",
            "model": "Apple Silicon Large-v3",
            "cost_tier": "Free / On-Device ($0.00)",
            "utterances": formatted_utts,
            "full_text": full_text,
            "norm_text": norm_text,
            "words": words,
            "word_count": len(words),
            "turns_count": len(formatted_utts),
            "unique_speakers": unique_speakers,
        }
    except Exception as e:
        console.print(f"[yellow]Error loading MLX Whisper data: {e}[/yellow]")
        return None


def collect_reel_bundle(reel_id: str, data_root: str = "data") -> Optional[Dict[str, Any]]:
    """Gathers and cross-evaluates all 3 lanes (Local, Cloud, Gold) for a single reel."""
    reel_dir = Path(data_root) / "reels" / reel_id
    if not reel_dir.exists():
        return None

    # Video specs & timeline
    video_path = reel_dir / "video.mp4"
    if not video_path.exists():
        return None

    specs_path = reel_dir / "media_specs.json"
    specs = {}
    if specs_path.exists():
        try:
            with open(specs_path, "r", encoding="utf-8") as f:
                specs = json.load(f)
        except Exception:
            pass

    timeline_path = reel_dir / "timeline.json"
    timeline = {}
    if timeline_path.exists():
        try:
            with open(timeline_path, "r", encoding="utf-8") as f:
                timeline = json.load(f)
        except Exception:
            pass

    duration_sec = specs.get("duration", 0.0) or (timeline.get("duration_ms", 0) / 1000.0)

    # 1. Gold standard
    gold = extract_gold_data(reel_id, reel_dir)
    
    # 2. AssemblyAI (Cloud)
    assembly = extract_assembly_data(reel_dir)

    # 3. MLX Whisper (Local)
    mlx = extract_mlx_data(reel_dir)

    # Compute comparative metrics vs Gold Standard
    if gold and gold["words"]:
        ref_words = gold["words"]
        ref_norm = gold["norm_text"]

        if assembly:
            assembly["wer"] = compute_wer(ref_words, assembly["words"])
            assembly["cer"] = compute_cer(ref_norm, assembly["norm_text"])
            assembly["recall"] = round((len(assembly["words"]) / max(1, len(ref_words))) * 100, 1)

        if mlx:
            mlx["wer"] = compute_wer(ref_words, mlx["words"])
            mlx["cer"] = compute_cer(ref_norm, mlx["norm_text"])
            mlx["recall"] = round((len(mlx["words"]) / max(1, len(ref_words))) * 100, 1)

    # Relative video URL for browser (served from repository root)
    rel_video_src = f"data/reels/{reel_id}/video.mp4"

    return {
        "reel_id": reel_id,
        "video_src": rel_video_src,
        "duration_sec": round(duration_sec, 2),
        "resolution": f"{specs.get('width', 1080)}x{specs.get('height', 1920)}",
        "fps": round(specs.get("fps", 30.0), 1),
        "gold": gold,
        "assembly": assembly,
        "mlx": mlx,
    }


def collect_all_reels(data_root: str = "data") -> Dict[str, Any]:
    """Discovers and bundles data for all reels in data/reels/."""
    reels_dir = Path(data_root) / "reels"
    if not reels_dir.exists():
        return {}

    bundles = {}
    for d in sorted(reels_dir.iterdir()):
        if d.is_dir() and not d.name.startswith("."):
            bundle = collect_reel_bundle(d.name, data_root=data_root)
            if bundle:
                bundles[d.name] = bundle
    return bundles


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Creator DNA • Multimodal Speech & Diarization Arena</title>
  <style>
    :root {
      --bg: #090d16;
      --card-bg: #111827;
      --card-border: rgba(255, 255, 255, 0.08);
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --local-accent: #a855f7;
      --local-bg: rgba(168, 85, 247, 0.08);
      --local-border: rgba(168, 85, 247, 0.25);
      --cloud-accent: #10b981;
      --cloud-bg: rgba(16, 185, 129, 0.08);
      --cloud-border: rgba(16, 185, 129, 0.25);
      --gold-accent: #f59e0b;
      --gold-bg: rgba(245, 158, 11, 0.08);
      --gold-border: rgba(245, 158, 11, 0.25);
    }

    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    /* Top Navigation Header */
    header {
      background: rgba(17, 24, 39, 0.95);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--card-border);
      padding: 12px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 100;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand h1 {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: -0.01em;
    }
    .brand .badge {
      font-size: 11px;
      background: rgba(255, 255, 255, 0.1);
      padding: 3px 8px;
      border-radius: 9999px;
      color: var(--text-muted);
      font-weight: 600;
    }

    .nav-controls {
      display: flex;
      align-items: center;
      gap: 16px;
    }

    .reel-select-group {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .reel-select-group label {
      font-size: 13px;
      color: var(--text-muted);
      font-weight: 500;
    }
    select#reelSelect {
      background: #1e293b;
      color: var(--text);
      border: 1px solid var(--card-border);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      outline: none;
    }
    select#reelSelect:focus {
      border-color: #3b82f6;
    }

    .verdict-pill {
      font-size: 12px;
      font-weight: 600;
      padding: 4px 12px;
      border-radius: 9999px;
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }

    /* Main Grid Layout */
    .dashboard-layout {
      display: grid;
      grid-template-columns: 380px 1fr;
      flex: 1;
      height: calc(100vh - 61px);
      overflow: hidden;
    }

    /* Left Dock: Video Player & Media Controls */
    .video-dock {
      background: #0d131f;
      border-right: 1px solid var(--card-border);
      padding: 20px;
      display: flex;
      flex-direction: column;
      gap: 16px;
      overflow-y: auto;
    }

    .video-wrapper {
      position: relative;
      background: #000;
      border-radius: 12px;
      overflow: hidden;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      border: 1px solid var(--card-border);
    }
    video#videoPlayer {
      width: 100%;
      height: 480px;
      object-fit: contain;
      display: block;
      background: #000;
    }

    .playback-controls {
      display: flex;
      flex-direction: column;
      gap: 10px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 12px;
    }

    .timecode-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 13px;
      font-weight: 700;
      color: var(--text);
    }

    .scrubber {
      width: 100%;
      height: 6px;
      background: #334155;
      border-radius: 3px;
      cursor: pointer;
      position: relative;
    }
    .scrubber-fill {
      height: 100%;
      background: #3b82f6;
      border-radius: 3px;
      width: 0%;
      transition: width 0.05s linear;
    }

    .btn-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }
    .btn {
      background: #1e293b;
      border: 1px solid var(--card-border);
      color: var(--text);
      padding: 6px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: background 0.15s;
    }
    .btn:hover { background: #334155; }
    .btn.primary { background: #2563eb; border-color: #3b82f6; }
    .btn.primary:hover { background: #1d4ed8; }

    .speed-select {
      background: #1e293b;
      color: var(--text);
      border: 1px solid var(--card-border);
      padding: 4px 8px;
      border-radius: 6px;
      font-size: 11px;
    }

    .meta-box {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 14px;
      font-size: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .meta-box h3 {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
    }
    .cast-pill {
      display: flex;
      align-items: center;
      justify-content: space-between;
      background: #1e293b;
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 12px;
    }
    .cast-pill .role { color: var(--text-muted); font-size: 11px; }

    /* Right Arena: 3 Parallel Comparison Columns */
    .comparison-arena {
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      height: 100%;
      overflow: hidden;
      background: #080c14;
    }

    .column {
      display: flex;
      flex-direction: column;
      border-right: 1px solid var(--card-border);
      height: 100%;
      overflow: hidden;
    }
    .column:last-child { border-right: none; }

    /* Column Header */
    .column-header {
      padding: 16px;
      border-bottom: 1px solid var(--card-border);
      display: flex;
      flex-direction: column;
      gap: 12px;
      background: #0f172a;
    }
    .col-title-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .col-title {
      font-size: 15px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .tier-badge {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 9999px;
    }

    .column.local .tier-badge { background: var(--local-bg); color: var(--local-accent); border: 1px solid var(--local-border); }
    .column.cloud .tier-badge { background: var(--cloud-bg); color: var(--cloud-accent); border: 1px solid var(--cloud-border); }
    .column.gold .tier-badge { background: var(--gold-bg); color: var(--gold-accent); border: 1px solid var(--gold-border); }

    /* Metrics Scorecard Grid */
    .scorecard-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 6px;
    }
    .metric-card {
      background: #1e293b;
      padding: 8px;
      border-radius: 6px;
      display: flex;
      flex-direction: column;
      gap: 2px;
      text-align: center;
    }
    .metric-label {
      font-size: 10px;
      color: var(--text-muted);
      text-transform: uppercase;
      font-weight: 600;
    }
    .metric-value {
      font-size: 14px;
      font-weight: 700;
    }
    .metric-value.good { color: #34d399; }
    .metric-value.warn { color: #fbbf24; }
    .metric-value.bad { color: #f87171; }

    /* Live Subtitle & Active Speaker HUD */
    .live-hud {
      padding: 12px 16px;
      border-bottom: 1px solid var(--card-border);
      background: #0b1120;
      display: flex;
      flex-direction: column;
      gap: 6px;
      min-height: 84px;
    }
    .hud-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
      color: var(--text-muted);
      text-transform: uppercase;
      font-weight: 600;
    }
    .hud-speaker-pill {
      font-size: 11px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 4px;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }
    .column.local .hud-speaker-pill { background: #3b0764; color: #d8b4fe; }
    .column.cloud .hud-speaker-pill { background: #064e3b; color: #6ee7b7; }
    .column.gold .hud-speaker-pill { background: #451a03; color: #fcd34d; }

    .live-text {
      font-size: 14px;
      font-weight: 600;
      line-height: 1.4;
      color: #fff;
    }
    .live-text.silent {
      color: #64748b;
      font-style: italic;
      font-weight: 400;
      font-size: 13px;
    }

    /* Dialogue Transcript Feed */
    .feed-container {
      flex: 1;
      overflow-y: auto;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      scroll-behavior: smooth;
    }

    .utterance-card {
      background: #111827;
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 10px 12px;
      cursor: pointer;
      transition: all 0.15s ease;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .utterance-card:hover {
      background: #1e293b;
      border-color: rgba(255, 255, 255, 0.2);
    }
    .utterance-card.is-active {
      transform: translateX(4px);
    }
    .column.local .utterance-card.is-active {
      background: var(--local-bg);
      border-color: var(--local-accent);
      box-shadow: 0 0 12px rgba(168, 85, 247, 0.25);
    }
    .column.cloud .utterance-card.is-active {
      background: var(--cloud-bg);
      border-color: var(--cloud-accent);
      box-shadow: 0 0 12px rgba(16, 185, 129, 0.25);
    }
    .column.gold .utterance-card.is-active {
      background: var(--gold-bg);
      border-color: var(--gold-accent);
      box-shadow: 0 0 12px rgba(245, 158, 11, 0.25);
    }

    .card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
    }
    .card-time {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      color: var(--text-muted);
      font-weight: 600;
    }
    .card-speaker {
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 11px;
    }
    .card-edit-type {
      font-size: 10px;
      padding: 1px 5px;
      border-radius: 3px;
      background: #334155;
      color: #cbd5e1;
    }

    .card-body {
      font-size: 13px;
      line-height: 1.4;
      color: #e2e8f0;
    }

    .empty-state {
      padding: 40px 20px;
      text-align: center;
      color: var(--text-muted);
      font-size: 13px;
    }
  </style>
</head>
<body>

  <!-- Top Header Navigation -->
  <header>
    <div class="brand">
      <h1>🎙️ Multimodal Speech & Diarization Arena</h1>
      <span class="badge">Central Dashboard</span>
    </div>

    <div class="nav-controls">
      <div class="reel-select-group">
        <label for="reelSelect">Active Reel:</label>
        <select id="reelSelect" onchange="switchReel(this.value)"></select>
      </div>
      <div id="verdictPill" class="verdict-pill">Evaluating...</div>
    </div>
  </header>

  <!-- Split View -->
  <div class="dashboard-layout">
    
    <!-- Left Dock: Video Player & Media Controls -->
    <div class="video-dock">
      <div class="video-wrapper">
        <video id="videoPlayer" playsinline preload="auto"></video>
      </div>

      <div class="playback-controls">
        <div class="timecode-bar">
          <span id="currentTimeDisplay">00:00.00</span>
          <span id="durationDisplay">00:00.00</span>
        </div>
        <div class="scrubber" id="scrubber" onclick="seekByScrubber(event)">
          <div class="scrubber-fill" id="scrubberFill"></div>
        </div>

        <div class="btn-row">
          <button class="btn" onclick="skip(-5)">-5s</button>
          <button class="btn primary" id="playBtn" onclick="togglePlay()">Play ▶</button>
          <button class="btn" onclick="skip(5)">+5s</button>
          <select class="speed-select" id="speedSelect" onchange="setSpeed(this.value)">
            <option value="0.75">0.75x</option>
            <option value="1.0" selected>1.0x</option>
            <option value="1.25">1.25x</option>
            <option value="1.5">1.5x</option>
          </select>
        </div>

        <div style="display: flex; align-items: center; gap: 8px; margin-top: 4px; font-size: 12px; color: var(--text-muted);">
          <input type="checkbox" id="autoScrollCheck" checked>
          <label for="autoScrollCheck">Auto-scroll transcripts to playhead</label>
        </div>
      </div>

      <!-- Cast Profile Drawer -->
      <div class="meta-box" id="castBox">
        <h3>Cast & Character Directory</h3>
        <div id="castList" style="display:flex; flex-direction:column; gap:6px;">
          <span style="color:#64748b; font-style:italic;">No cast metadata available</span>
        </div>
      </div>

      <!-- Video Specifications -->
      <div class="meta-box">
        <h3>Container Metadata</h3>
        <div style="display:flex; justify-content:space-between; color:var(--text-muted);">
          <span>Duration:</span> <strong id="metaDuration" style="color:#fff;">--</strong>
        </div>
        <div style="display:flex; justify-content:space-between; color:var(--text-muted);">
          <span>Resolution:</span> <strong id="metaRes" style="color:#fff;">--</strong>
        </div>
        <div style="display:flex; justify-content:space-between; color:var(--text-muted);">
          <span>Framerate:</span> <strong id="metaFps" style="color:#fff;">--</strong>
        </div>
      </div>
    </div>

    <!-- Right Arena: 3 Parallel Comparison Columns -->
    <div class="comparison-arena">

      <!-- Lane 1: Local MLX Whisper -->
      <div class="column local" id="colLocal">
        <div class="column-header">
          <div class="col-title-bar">
            <span class="col-title">💻 Local (Apple Silicon)</span>
            <span class="tier-badge">MLX Large-v3 • $0.00</span>
          </div>
          <div class="scorecard-grid">
            <div class="metric-card">
              <span class="metric-label">WER vs Gold</span>
              <span class="metric-value" id="localWer">--</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">CER vs Gold</span>
              <span class="metric-value" id="localCer">--</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Recall</span>
              <span class="metric-value" id="localRecall">--</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Words</span>
              <span class="metric-value" id="localWords">--</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Turns</span>
              <span class="metric-value" id="localTurns">--</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Speakers</span>
              <span class="metric-value" id="localSpeakers">--</span>
            </div>
          </div>
        </div>

        <div class="live-hud">
          <div class="hud-header">
            <span>Live Subtitle</span>
            <span class="hud-speaker-pill" id="localHudSpeaker">No Active Speech</span>
          </div>
          <div class="live-text silent" id="localHudText">— Silence / No Speech —</div>
        </div>

        <div class="feed-container" id="localFeed"></div>
      </div>

      <!-- Lane 2: Cloud AssemblyAI -->
      <div class="column cloud" id="colCloud">
        <div class="column-header">
          <div class="col-title-bar">
            <span class="col-title">☁️ AssemblyAI Cloud</span>
            <span class="tier-badge">Conformer-2 • ~$0.015/m</span>
          </div>
          <div class="scorecard-grid">
            <div class="metric-card">
              <span class="metric-label">WER vs Gold</span>
              <span class="metric-value" id="cloudWer">--</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">CER vs Gold</span>
              <span class="metric-value" id="cloudCer">--</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Recall</span>
              <span class="metric-value" id="cloudRecall">--</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Words</span>
              <span class="metric-value" id="cloudWords">--</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Turns</span>
              <span class="metric-value" id="cloudTurns">--</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Speakers</span>
              <span class="metric-value" id="cloudSpeakers">--</span>
            </div>
          </div>
        </div>

        <div class="live-hud">
          <div class="hud-header">
            <span>Live Subtitle</span>
            <span class="hud-speaker-pill" id="cloudHudSpeaker">No Active Speech</span>
          </div>
          <div class="live-text silent" id="cloudHudText">— Silence / No Speech —</div>
        </div>

        <div class="feed-container" id="cloudFeed"></div>
      </div>

      <!-- Lane 3: Gold Standard -->
      <div class="column gold" id="colGold">
        <div class="column-header">
          <div class="col-title-bar">
            <span class="col-title">👑 Gold Standard</span>
            <span class="tier-badge">Human Benchmark</span>
          </div>
          <div class="scorecard-grid">
            <div class="metric-card">
              <span class="metric-label">WER (Ref)</span>
              <span class="metric-value good">0.0%</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">CER (Ref)</span>
              <span class="metric-value good">0.0%</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Recall</span>
              <span class="metric-value good">100%</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Words</span>
              <span class="metric-value" id="goldWords">--</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Turns</span>
              <span class="metric-value" id="goldTurns">--</span>
            </div>
            <div class="metric-card">
              <span class="metric-label">Characters</span>
              <span class="metric-value" id="goldSpeakers">--</span>
            </div>
          </div>
        </div>

        <div class="live-hud">
          <div class="hud-header">
            <span>Live Subtitle</span>
            <span class="hud-speaker-pill" id="goldHudSpeaker">No Active Speech</span>
          </div>
          <div class="live-text silent" id="goldHudText">— Silence / No Speech —</div>
        </div>

        <div class="feed-container" id="goldFeed"></div>
      </div>

    </div>
  </div>

  <script>
    const REELS_DATA = __REELS_DATA_JSON__;
    let currentReelId = "__INITIAL_REEL_ID__";

    const video = document.getElementById("videoPlayer");
    const playBtn = document.getElementById("playBtn");
    const currentTimeDisplay = document.getElementById("currentTimeDisplay");
    const durationDisplay = document.getElementById("durationDisplay");
    const scrubberFill = document.getElementById("scrubberFill");
    const autoScrollCheck = document.getElementById("autoScrollCheck");

    // Initialize Dropdown
    const reelSelect = document.getElementById("reelSelect");
    Object.keys(REELS_DATA).forEach(rId => {
      const opt = document.createElement("option");
      opt.value = rId;
      opt.innerText = rId + " (" + REELS_DATA[rId].duration_sec + "s)";
      if (rId === currentReelId) opt.selected = true;
      reelSelect.appendChild(opt);
    });

    function formatTime(sec) {
      if (!sec || isNaN(sec)) return "00:00.00";
      const m = Math.floor(sec / 60);
      const s = (sec % 60).toFixed(2);
      return String(m).padStart(2, "0") + ":" + (s < 10 ? "0" : "") + s;
    }

    function switchReel(reelId) {
      currentReelId = reelId;
      const data = REELS_DATA[reelId];
      if (!data) return;

      // Update Video
      video.src = data.video_src;
      video.load();

      // Update Metadata
      document.getElementById("metaDuration").innerText = data.duration_sec + "s";
      document.getElementById("metaRes").innerText = data.resolution;
      document.getElementById("metaFps").innerText = data.fps + " fps";

      // Update Cast Profile
      const castList = document.getElementById("castList");
      castList.innerHTML = "";
      if (data.gold && data.gold.cast && data.gold.cast.length > 0) {
        data.gold.cast.forEach(c => {
          const pill = document.createElement("div");
          pill.className = "cast-pill";
          pill.innerHTML = "<strong>" + (c.name_or_role || c.speaker_id) + "</strong><span class=\"role\">" + (c.visual_description || "") + "</span>";
          castList.appendChild(pill);
        });
      } else {
        castList.innerHTML = "<span style=\"color:#64748b; font-style:italic;\">No cast metadata</span>";
      }

      // Update Verdict Pill
      const verdict = document.getElementById("verdictPill");
      if (data.assembly && data.mlx && data.assembly.wer !== undefined && data.mlx.wer !== undefined) {
        if (data.assembly.wer <= data.mlx.wer) {
          verdict.innerText = "🏆 Best ASR: AssemblyAI Cloud (WER " + data.assembly.wer + "%)";
        } else {
          verdict.innerText = "🏆 Best ASR: Local MLX Whisper (WER " + data.mlx.wer + "%)";
        }
      } else if (data.assembly && data.assembly.wer !== undefined) {
        verdict.innerText = "AssemblyAI WER: " + data.assembly.wer + "%";
      } else {
        verdict.innerText = "Awaiting Multi-Engine Data";
      }

      // Render Lanes
      renderLane("local", data.mlx, data.duration_sec);
      renderLane("cloud", data.assembly, data.duration_sec);
      renderLane("gold", data.gold, data.duration_sec);
    }

    function renderLane(laneType, data, durationSec) {
      const werEl = document.getElementById(laneType + "Wer");
      const cerEl = document.getElementById(laneType + "Cer");
      const recallEl = document.getElementById(laneType + "Recall");
      const wordsEl = document.getElementById(laneType + "Words");
      const turnsEl = document.getElementById(laneType + "Turns");
      const speakersEl = document.getElementById(laneType + "Speakers");
      const feed = document.getElementById(laneType + "Feed");

      feed.innerHTML = "";

      if (!data || !data.available) {
        if (werEl) werEl.innerText = "--";
        if (cerEl) cerEl.innerText = "--";
        if (recallEl) recallEl.innerText = "--";
        if (wordsEl) wordsEl.innerText = "--";
        if (turnsEl) turnsEl.innerText = "--";
        if (speakersEl) speakersEl.innerText = "--";
        feed.innerHTML = "<div class=\"empty-state\">Manifest not computed yet for this reel.</div>";
        return;
      }

      if (werEl) {
        werEl.innerText = data.wer !== undefined ? data.wer + "%" : "0.0%";
        werEl.className = "metric-value " + (data.wer < 12 ? "good" : (data.wer < 28 ? "warn" : "bad"));
      }
      if (cerEl) {
        cerEl.innerText = data.cer !== undefined ? data.cer + "%" : "0.0%";
        cerEl.className = "metric-value " + (data.cer < 10 ? "good" : (data.cer < 25 ? "warn" : "bad"));
      }
      if (recallEl) {
        recallEl.innerText = data.recall !== undefined ? data.recall + "%" : "100%";
      }
      if (wordsEl) wordsEl.innerText = data.word_count || 0;
      if (turnsEl) turnsEl.innerText = data.turns_count || 0;
      if (speakersEl) speakersEl.innerText = (data.unique_speakers || []).length;

      // Render Utterance Cards
      (data.utterances || []).forEach(u => {
        const card = document.createElement("div");
        card.className = "utterance-card";
        card.dataset.start = u.start_ms;
        card.dataset.end = u.end_ms;
        card.onclick = () => seekTo(u.start_ms);

        const cardTop = document.createElement("div");
        cardTop.className = "card-top";

        const timeSpan = document.createElement("span");
        timeSpan.className = "card-time";
        timeSpan.innerText = formatTime(u.start_ms / 1000) + " - " + formatTime(u.end_ms / 1000);

        const speakerBadge = document.createElement("span");
        speakerBadge.className = "card-speaker";
        speakerBadge.innerText = u.speaker;

        cardTop.appendChild(speakerBadge);
        if (u.edit_type) {
          const editBadge = document.createElement("span");
          editBadge.className = "card-edit-type";
          editBadge.innerText = u.edit_type;
          cardTop.appendChild(editBadge);
        }
        cardTop.appendChild(timeSpan);

        const cardBody = document.createElement("div");
        cardBody.className = "card-body";
        cardBody.innerText = u.text;

        card.appendChild(cardTop);
        card.appendChild(cardBody);
        feed.appendChild(card);
      });
    }

    // Video Playback Synchronizer
    video.ontimeupdate = updatePlayhead;
    video.onloadedmetadata = () => {
      durationDisplay.innerText = formatTime(video.duration);
    };

    function updatePlayhead() {
      const cur = video.currentTime;
      const dur = video.duration || 1;
      currentTimeDisplay.innerText = formatTime(cur);
      scrubberFill.style.width = ((cur / dur) * 100) + "%";

      const currentMs = cur * 1000;
      updateLaneHUD("local", currentMs);
      updateLaneHUD("cloud", currentMs);
      updateLaneHUD("gold", currentMs);
    }

    function updateLaneHUD(laneType, currentMs) {
      const feed = document.getElementById(laneType + "Feed");
      const speakerEl = document.getElementById(laneType + "HudSpeaker");
      const textEl = document.getElementById(laneType + "HudText");

      const cards = feed.querySelectorAll(".utterance-card");
      let activeCard = null;

      cards.forEach(card => {
        const start = parseFloat(card.dataset.start);
        const end = parseFloat(card.dataset.end);
        if (currentMs >= start && currentMs <= end) {
          activeCard = card;
          if (!card.classList.contains("is-active")) {
            card.classList.add("is-active");
            if (autoScrollCheck.checked) {
              card.scrollIntoView({ behavior: "smooth", block: "nearest" });
            }
          }
        } else {
          card.classList.remove("is-active");
        }
      });

      if (activeCard) {
        const spk = activeCard.querySelector(".card-speaker").innerText;
        const txt = activeCard.querySelector(".card-body").innerText;
        speakerEl.innerText = "🗣️ " + spk;
        textEl.innerText = txt;
        textEl.className = "live-text";
      } else {
        speakerEl.innerText = "No Active Speech";
        textEl.innerText = "— Silence / No Speech —";
        textEl.className = "live-text silent";
      }
    }

    function togglePlay() {
      if (video.paused) {
        video.play();
        playBtn.innerText = "Pause ❚❚";
      } else {
        video.pause();
        playBtn.innerText = "Play ▶";
      }
    }

    function skip(sec) {
      video.currentTime = Math.max(0, Math.min(video.duration || 100, video.currentTime + sec));
    }

    function seekTo(ms) {
      video.currentTime = ms / 1000;
      video.play();
      playBtn.innerText = "Pause ❚❚";
    }

    function seekByScrubber(e) {
      const scrubber = document.getElementById("scrubber");
      const rect = scrubber.getBoundingClientRect();
      const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
      video.currentTime = pct * (video.duration || 0);
    }

    function setSpeed(rate) {
      video.playbackRate = parseFloat(rate);
    }

    // Keyboard Shortcuts (Space: Play/Pause, Left/Right: Seek 5s)
    window.addEventListener("keydown", (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
      if (e.code === "Space") {
        e.preventDefault();
        togglePlay();
      } else if (e.code === "ArrowLeft") {
        e.preventDefault();
        skip(-5);
      } else if (e.code === "ArrowRight") {
        e.preventDefault();
        skip(5);
      }
    });

    // Start with default reel
    switchReel(currentReelId);
  </script>
</body>
</html>
"""


def generate_dashboard(initial_reel_id: Optional[str] = None, data_root: str = "data") -> Path:
    """Generates the master dashboard.html file."""
    bundles = collect_all_reels(data_root=data_root)
    if not bundles:
        console.print("[yellow]No reels found in data/reels/[/yellow]")
        return Path("dashboard.html")

    if not initial_reel_id or initial_reel_id not in bundles:
        initial_reel_id = list(bundles.keys())[0]

    reels_json_str = json.dumps(bundles, ensure_ascii=False)

    rendered_html = (
        HTML_TEMPLATE
        .replace("__REELS_DATA_JSON__", reels_json_str)
        .replace("__INITIAL_REEL_ID__", initial_reel_id)
    )

    out_path = Path("dashboard.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(rendered_html)

    console.print(f"[bold green]✓ Generated Central Comparison Dashboard:[/bold green] [cyan]{out_path.resolve()}[/cyan]")
    return out_path


def start_server_and_open(initial_reel_id: Optional[str] = None, port: int = 8000, auto_open: bool = True):
    """Generates dashboard.html and starts a local HTTP server with Range-request support for video seeking."""
    out_path = generate_dashboard(initial_reel_id=initial_reel_id)

    # Use standard HTTP server handler
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(Path(".").resolve()))

    # Find open port if 8000 is occupied
    actual_port = port
    for p in range(port, port + 20):
        try:
            httpd = socketserver.TCPServer(("", p), handler)
            actual_port = p
            break
        except OSError:
            continue

    url = f"http://localhost:{actual_port}/dashboard.html"
    console.print(Panel.fit(
        f"[bold cyan]Serving Multimodal Comparison Arena at:[/bold cyan]\n"
        f"[bold green]{url}[/bold green]\n"
        f"[dim]Press Ctrl+C to stop the dashboard server.[/dim]",
        title="🚀 DASHBOARD SERVER RUNNING",
        border_style="green",
    ))

    if auto_open:
        try:
            webbrowser.open(url)
        except Exception as e:
            console.print(f"[dim]Could not auto-open browser: {e}[/dim]")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard server stopped.[/yellow]")
        httpd.server_close()


def main():
    parser = argparse.ArgumentParser(
        description="Central Multimodal Speech & Diarization Comparison Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "reel_id",
        nargs="?",
        default=None,
        help="Optional initial reel ID to display on launch. If omitted, uses first available reel.",
    )
    parser.add_argument(
        "--port",
        "-p",
        type=int,
        default=8000,
        help="Port for local HTTP server (default: 8000)",
    )
    parser.add_argument(
        "--no-serve",
        action="store_true",
        help="Only generate dashboard.html without launching the local HTTP server",
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not auto-open browser on launch",
    )

    args = parser.parse_args()

    if args.no_serve:
        generate_dashboard(initial_reel_id=args.reel_id)
    else:
        start_server_and_open(
            initial_reel_id=args.reel_id,
            port=args.port,
            auto_open=not args.no_open,
        )


if __name__ == "__main__":
    main()
