"""
app/export/beat_sheet.py
Shooting beat sheet and shot list generator for short-form comedy sketches.

Transforms screenplay dialogue and action into a production-ready shooting table:
- Chronological beats with estimated timestamps
- Recommended camera angles and framing (Close-up, Two-shot, Snap zoom)
- Character dialogue cues, physical actor blocking, and prop notes
- Exports to Markdown, CSV, and JSON
"""

import csv
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from app.core.config import console, settings
from app.core.database import get_db_session
from app.generation.parser import parse_screenplay_elements
from app.models.schema import Script, Style


def suggest_camera_framing(beat_index: int, total_beats: int, element_type: str, text: str) -> str:
    """
    Suggest realistic, dynamic camera framing based on comedic escalation beat:
    - First beat: Establishing / Medium shot
    - Rising conflict / heated dialogue: Over-the-shoulder / Rapid Close-ups
    - Shocking revelation: Snap Zoom / Tight Close-up
    - Ending / Button: Wide / Quick Cut
    """
    lower = text.lower()
    if "shriek" in lower or "gasp" in lower or "shock" in lower or "eyes widen" in lower or "voice cracking" in lower:
        return "Tight Close-up / Snap Zoom"
    if "lunging" in lower or "jumps" in lower or "scurries" in lower or "bolt" in lower or "slaps" in lower:
        return "Wide Handheld (Fast Track)"
    if beat_index == 1:
        return "Medium Shot (Hook / Establishing)"
    if beat_index == total_beats or "blackout" in lower or "slam" in lower:
        return "Wide Cut to Blackout"
    if element_type == "dialogue":
        return "Medium Close-up (Two-shot reverse)"
    return "Medium Shot (Handheld)"


def generate_beat_sheet(script_id: str, export_files: bool = True) -> Dict[str, Any]:
    """
    Generate an actionable shooting beat sheet and shot list for a screenplay.

    Args:
        script_id: Unique script identifier.
        export_files: If True, writes Markdown and CSV tables to data/exports/.

    Returns:
        Structured beat sheet payload dictionary.
    """
    with get_db_session() as session:
        script = session.query(Script).filter_by(script_id=script_id).first()
        if not script:
            raise ValueError(f"Script with id '{script_id}' not found.")

        style = session.query(Style).filter_by(style_id=script.style_id).first()
        creator_name = style.name if (style and style.name) else script.style_id
        premise = script.premise
        raw_text = script.script_text

    elements = parse_screenplay_elements(raw_text)

    # Group elements into coherent filming beats
    raw_beats: List[Dict[str, Any]] = []
    current_char = ""
    current_action = ""

    for el in elements:
        t = el.get("type")
        txt = el.get("text", "").strip()
        if not txt:
            continue

        if t == "slugline":
            current_action = f"Location: {txt}"
        elif t == "character":
            current_char = txt
        elif t == "action":
            current_action = txt
        elif t == "dialogue":
            raw_beats.append({
                "character": current_char,
                "dialogue": txt,
                "action": current_action,
                "type": "dialogue",
            })
            current_action = ""
        elif t == "button":
            raw_beats.append({
                "character": "SCENE",
                "dialogue": txt,
                "action": current_action or "Final punchline & blackout",
                "type": "button",
            })
            current_action = ""

    total_items = max(1, len(raw_beats))
    # Target 60 seconds total runtime
    est_total_sec = 60
    sec_per_beat = max(3.0, est_total_sec / float(total_items))

    beats: List[Dict[str, Any]] = []
    current_sec = 0.0

    for idx, item in enumerate(raw_beats, 1):
        start_sec = int(current_sec)
        end_sec = int(min(est_total_sec, current_sec + sec_per_beat))
        current_sec += sec_per_beat

        start_str = f"00:{start_sec:02d}"
        end_str = f"00:{end_sec:02d}"
        time_range = f"{start_str} - {end_str}"

        # Assign comedic pacing phase
        if idx == 1 or idx == 2:
            phase = "Hook / Setup"
        elif idx == total_items:
            phase = "Punchline Button"
        elif idx >= total_items - 2:
            phase = "Climactic Reversal"
        else:
            phase = f"Escalation Beat {idx - 2}"

        framing = suggest_camera_framing(idx, total_items, item["type"], f"{item['dialogue']} {item['action']}")

        beats.append({
            "beat_number": idx,
            "time_range": time_range,
            "phase": phase,
            "framing": framing,
            "character": item["character"],
            "dialogue_cue": item["dialogue"],
            "blocking_notes": item["action"] or "-",
        })

    payload = {
        "script_id": script_id,
        "creator_name": creator_name,
        "premise": premise,
        "total_beats": len(beats),
        "est_total_duration": "60 sec",
        "beats": beats,
    }

    if export_files:
        exports_dir = settings.exports_dir
        exports_dir.mkdir(parents=True, exist_ok=True)

        # 1. Export Markdown Beat Sheet
        md_path = exports_dir / f"{script_id}_beat_sheet.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# Shooting Beat Sheet & Shot List: {script_id}\n\n")
            f.write(f"**Creator Style**: {creator_name}  \n")
            f.write(f"**Premise**: {premise}  \n")
            f.write(f"**Target Runtime**: 60 seconds | **Total Beats**: {len(beats)}\n\n")
            f.write("| Beat # | Time Code | Phase | Camera Framing | Character | Dialogue Cue | Actor Blocking & Props |\n")
            f.write("| :---: | :---: | :---: | :--- | :--- | :--- | :--- |\n")
            for b in beats:
                d_cue = b['dialogue_cue'].replace('|', '–')
                b_notes = b['blocking_notes'].replace('|', '–')
                f.write(f"| {b['beat_number']} | {b['time_range']} | {b['phase']} | {b['framing']} | {b['character']} | \"{d_cue}\" | {b_notes} |\n")

        # 2. Export CSV Shot List
        csv_path = exports_dir / f"{script_id}_shotlist.csv"
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Beat", "TimeCode", "Phase", "Framing", "Character", "DialogueCue", "BlockingAndProps"])
            for b in beats:
                writer.writerow([b["beat_number"], b["time_range"], b["phase"], b["framing"], b["character"], b["dialogue_cue"], b["blocking_notes"]])

        console.print(f"[bold green]✓ Shooting Beat Sheet Generated:[/bold green] [cyan]{md_path}[/cyan]")

    return payload

