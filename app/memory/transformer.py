"""
app/memory/transformer.py
Creative Video Memory Markdown Distiller.

Implements Section 9 & 10 of description.txt:
Transforms the compact structured extraction JSON into a standardized,
human-readable creative Markdown document (Video Memory) focused on creative
style, character dynamics, comedic mechanisms, sequence, and pacing.
"""

from typing import List, Optional, Union
from app.models.extraction import VideoExtraction, CompactScene


def select_representative_dialogue(
    scenes: List[CompactScene],
    speakers_map: dict,
    max_turns: int = 5,
) -> List[str]:
    """
    Select high-signal, representative dialogue lines across the video reel.
    Prioritizes turns with distinct emotions or comedic punchlines.
    """
    candidates = []

    for scene in scenes:
        for turn in scene.x:
            # turn format: [start_ms, end_ms, speaker_code, dialogue, emotion?, action?]
            if len(turn) < 4:
                continue
            sp_code = turn[2]
            dialogue = str(turn[3]).strip()
            emotion = turn[4] if len(turn) > 4 and turn[4] else None
            sp_name = speakers_map.get(sp_code, f"Speaker {sp_code}")

            # Prioritize expressive lines with dialogue length > 10 chars
            score = 1
            if emotion and emotion in ("triumphant", "accusing", "scolding", "euphoric", "mocking", "scheming"):
                score += 3
            if len(dialogue) > 20:
                score += 1

            candidates.append((score, f'{sp_name}: "{dialogue}"'))

    # Sort by score descending and take up to max_turns
    candidates.sort(key=lambda item: item[0], reverse=True)
    return [c[1] for c in candidates[:max_turns]]


def transform_to_video_memory(
    video_id: str,
    extraction: Union[VideoExtraction, dict],
) -> str:
    """
    Distill a compact extraction into canonical Video Memory Markdown.

    Args:
        video_id: Unique video identifier (e.g. 'v_eee566bd14').
        extraction: Validated VideoExtraction model or dictionary.

    Returns:
        Formatted Markdown string representing the Video Memory.
    """
    if isinstance(extraction, dict):
        ext = VideoExtraction.model_validate(extraction)
    else:
        ext = extraction

    speakers_map = ext.speakers
    cd = ext.cd
    scenes = ext.sc

    lines = [f"VIDEO {video_id}", ""]

    # 1. CHARACTERS
    lines.append("CHARACTERS")
    if ext.sp:
        for sp in ext.sp:
            desc = sp.desc or "Character in scene"
            lines.append(f"{sp.n} — {desc}.")
    else:
        lines.append("Unknown characters.")
    lines.append("")

    # 2. SETTING
    lines.append("SETTING")
    locations = []
    for sc in scenes:
        if sc.loc and sc.loc not in locations:
            locations.append(sc.loc)
    lines.append(", ".join(locations) if locations else "Domestic setting.")
    lines.append("")

    # 3. SITUATION
    lines.append("SITUATION")
    situation = cd.setup if cd and cd.setup else (scenes[0].sit if scenes and scenes[0].sit else "Comedic interaction.")
    lines.append(situation.rstrip(".") + ".")
    lines.append("")

    # 4. SEQUENCE
    lines.append("SEQUENCE")
    seq_steps = []
    for sc in scenes:
        if sc.sit:
            seq_steps.append(sc.sit.rstrip("."))
    if cd and cd.esc:
        seq_steps.append(f"Escalation: {cd.esc.rstrip('.')}")
    if cd and cd.rev:
        seq_steps.append(f"Reversal: {cd.rev.rstrip('.')}")
    if cd and cd.punch:
        seq_steps.append(f"Punchline: {cd.punch.rstrip('.')}")

    if seq_steps:
        for idx, step in enumerate(seq_steps, 1):
            lines.append(f"{idx}. {step}.")
    else:
        lines.append("Sequential comic beats unfold.")
    lines.append("")

    # 5. DIALOGUE STYLE
    lines.append("DIALOGUE STYLE")
    lang_display = "Colloquial Hindi" if ext.lang == "hi" else f"Colloquial {ext.lang.upper()}"
    lines.append(f"Language: {lang_display}.")
    if cd and cd.rhythm:
        lines.append(f"Rhythm: {cd.rhythm.rstrip('.')}.")
    else:
        lines.append("Rhythm: Short conversational turns, high dialogue density.")
    lines.append("")

    # 6. COMEDIC MECHANISMS
    lines.append("COMEDIC MECHANISMS")
    if cd and cd.mech:
        for m in cd.mech:
            clean_mech = m.replace("-", " ").title()
            lines.append(f"- {clean_mech}")
    else:
        lines.append("- Observational comedy")
    lines.append("")

    # 7. PHYSICAL BEHAVIOR
    lines.append("PHYSICAL BEHAVIOR")
    if cd and cd.phys:
        for p in cd.phys:
            lines.append(f"- {p.rstrip('.')}")
    else:
        lines.append("- Everyday conversational gestures and reactions.")
    lines.append("")

    # 8. PACING
    lines.append("PACING")
    pacing_desc = cd.pace if cd and cd.pace else "Fast"
    lines.append(f"{pacing_desc.rstrip('.')}. Rapid transition from escalation to final punchline.")
    lines.append("")

    # 9. REPRESENTATIVE DIALOGUE
    lines.append("REPRESENTATIVE DIALOGUE")
    rep_dialogue = select_representative_dialogue(scenes, speakers_map)
    if rep_dialogue:
        for d in rep_dialogue:
            lines.append(d)
    else:
        lines.append("No representative dialogue transcribed.")

    return "\n".join(lines).strip()

