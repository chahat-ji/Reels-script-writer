"""
app/media/separator.py
Vocal isolation using Demucs (htdemucs) standardized to 16kHz mono WAV.
"""

import subprocess
import shutil
from pathlib import Path
from rich.console import Console

console = Console()


def isolate_vocals(audio_path: Path, output_dir: Path = None, shifts: int = 1) -> Path:
    """
    Separates speech from background music using Demucs (htdemucs)
    and downsamples directly to 16kHz mono PCM WAV without destructive spectral gating.
    """
    if output_dir is None:
        output_dir = audio_path.parent

    clean_vocals_path = output_dir / "vocals.wav"

    if clean_vocals_path.exists():
        console.print(f"[bold cyan][CACHE HIT][/bold cyan] Isolated vocals already exist: [green]{clean_vocals_path.name}[/green]")
        return clean_vocals_path

    console.print(f"[bold yellow][SEPARATING STEMS][/bold yellow] Isolating vocals from [green]{audio_path.name}[/green]...")

    cmd = [
        "demucs",
        "--two-stems=vocals",
        "-n", "htdemucs",
        f"--shifts={shifts}",
        "-o", str(output_dir / "stems"),
        str(audio_path),
    ]

    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        console.print(f"[bold red]Demucs failed:[/bold red] {res.stderr}")
        return audio_path

    track_name = audio_path.stem
    demucs_vocals = output_dir / "stems" / "htdemucs" / track_name / "vocals.wav"

    if demucs_vocals.exists():
        # Standardize directly to 16kHz mono WAV
        convert_cmd = [
            "ffmpeg",
            "-y",
            "-i", str(demucs_vocals),
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            str(clean_vocals_path),
        ]
        subprocess.run(convert_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        shutil.rmtree(output_dir / "stems", ignore_errors=True)
        console.print(f"[bold blue][ISOLATED][/bold blue] Vocal track saved: [green]{clean_vocals_path.name}[/green]")
        return clean_vocals_path

    return audio_path