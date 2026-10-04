"""
app/core/preflight.py
Phase 0 preflight inspection probe to analyze audio health metrics before routing.
"""

import subprocess
import re
from pathlib import Path
from rich.console import Console
from app.models.state import AudioCondition, ConditionReport

console = Console()


def analyze_audio_condition(audio_path: Path, reel_id: str) -> ConditionReport:
    """
    Inspects standard 16kHz mono audio.wav using ffmpeg/ffprobe:
    - Duration
    - Mean and max volume in dBFS (detects silence or clipping)
    - Silence ratio
    - Diagnostic health flags
    """
    console.print(f"[bold yellow][PREFLIGHT][/bold yellow] Analyzing audio profile for [green]{reel_id}[/green]...")

    # 1. Measure overall volume levels
    cmd_vol = [
        "ffmpeg",
        "-i", str(audio_path),
        "-af", "volumedetect",
        "-f", "null",
        "-"
    ]
    res_vol = subprocess.run(cmd_vol, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stderr_vol = res_vol.stderr

    mean_vol_match = re.search(r"mean_volume:\s+([-\d\.]+)\s+dB", stderr_vol)
    max_vol_match = re.search(r"max_volume:\s+([-\d\.]+)\s+dB", stderr_vol)

    mean_volume = float(mean_vol_match.group(1)) if mean_vol_match else -20.0
    max_volume = float(max_vol_match.group(1)) if max_vol_match else 0.0

    # 2. Detect silence intervals (-35dB threshold for >= 0.5s)
    cmd_silence = [
        "ffmpeg",
        "-i", str(audio_path),
        "-af", "silencedetect=noise=-35dB:d=0.5",
        "-f", "null",
        "-"
    ]
    res_silence = subprocess.run(cmd_silence, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stderr_silence = res_silence.stderr

    silence_durations = [float(d) for d in re.findall(r"silence_duration:\s+([\d\.]+)", stderr_silence)]
    total_silence = sum(silence_durations)

    # 3. Get total duration
    cmd_dur = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(audio_path)
    ]
    res_dur = subprocess.run(cmd_dur, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    total_duration = float(res_dur.stdout.strip() or 1.0)

    silence_ratio = round(min(1.0, total_silence / total_duration), 3)

    flags = []
    if mean_volume < -45.0:
        flags.append("EXTREMELY_LOW_VOLUME")
    if max_volume >= -0.1:
        flags.append("AUDIO_PEAK_CLIPPED")
    if silence_ratio > 0.4:
        flags.append("HIGH_SILENCE_RATIO")

    audio_condition = AudioCondition(
        has_heavy_music=False,
        music_energy_ratio=0.0,
        silence_ratio=silence_ratio,
        average_db=mean_volume,
        needs_stem_separation=False,
    )

    return ConditionReport(
        reel_id=reel_id,
        audio_condition=audio_condition,
        duration_seconds=round(total_duration, 2),
        flags=flags,
    )