"""
tools/export_annotated_video.py
Generates an Annotated Debug Video (.mp4) with real-time visual overlays (Option 2).

Overlays:
- Face bounding boxes with speaking status (Green = TALKING, Gray = SILENT)
- Live Mouth Aspect Ratio (MAR) scores and resolved speaker tag
- On-screen OCR bounding boxes with recognized text labels
- Real-time shot cuts, cut counter, and ASD pacing header
- Lower-third speech subtitles with active speaker and native script rendering
- High-fidelity audio re-muxed via ffmpeg

Usage:
    python tools/export_annotated_video.py DdMkWeaxKTT [--open] [--max-sec 20]
    python tools/export_annotated_video.py DeEKAEKhx_Z [--open]
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from rich.console import Console
from rich.progress import track

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

console = Console()

# Resolve system fonts for PIL (macOS native Unicode & Devanagari)
FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/DevanagariMT.ttc",
    "/System/Library/Fonts/Kohinoor.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
]

SELECTED_FONT_PATH = None
for p in FONT_PATHS:
    if os.path.exists(p):
        SELECTED_FONT_PATH = p
        break


def get_font(size: int = 18):
    if SELECTED_FONT_PATH:
        try:
            return ImageFont.truetype(SELECTED_FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()


def draw_hud_header(
    draw: ImageDraw.ImageDraw,
    width: int,
    current_ms: int,
    total_ms: int,
    active_shot_idx: int,
    total_shots: int,
    asd: float,
    is_cut_flash: bool,
    font_bold: ImageFont.ImageFont,
    font_sm: ImageFont.ImageFont,
):
    # Header bar background
    bar_h = 44
    draw.rectangle([(0, 0), (width, bar_h)], fill=(11, 15, 23, 210))
    draw.line([(0, bar_h), (width, bar_h)], fill=(255, 255, 255, 30), width=1)

    # Left: Shot info
    shot_text = f"SHOT {active_shot_idx}/{total_shots}  |  ASD: {asd:.1f}s"
    if is_cut_flash:
        # Cut indicator tag
        draw.rectangle([(12, 10), (70, 34)], fill=(239, 68, 68, 240))
        draw.text((22, 14), "CUT ⚡", fill=(255, 255, 255), font=font_sm)
        draw.text((78, 14), shot_text, fill=(241, 245, 249), font=font_sm)
    else:
        draw.text((14, 14), shot_text, fill=(147, 197, 253), font=font_sm)

    # Right: Timecode
    cur_sec = current_ms / 1000.0
    tot_sec = total_ms / 1000.0
    tc_text = f"{int(cur_sec//60):02d}:{cur_sec%60:05.2f} / {int(tot_sec//60):02d}:{tot_sec%60:05.2f}"
    bbox = font_sm.getbbox(tc_text)
    tc_w = bbox[2] - bbox[0]
    draw.text((width - tc_w - 14, 14), tc_text, fill=(6, 182, 212), font=font_sm)


def draw_face_box(
    draw: ImageDraw.ImageDraw,
    bbox: List[float],
    width: int,
    height: int,
    label: str,
    mar: float,
    is_speaking: bool,
    font: ImageFont.ImageFont,
):
    ymin, xmin, ymax, xmax = bbox
    x1 = int(xmin * width)
    y1 = int(ymin * height)
    x2 = int(xmax * width)
    y2 = int(ymax * height)

    if x2 <= x1 or y2 <= y1:
        return

    # Colors (RGB)
    if is_speaking:
        box_color = (16, 185, 129, 240)    # Emerald green
        fill_tint = (16, 185, 129, 30)
        tag_bg = (16, 185, 129, 230)
        tag_text = (255, 255, 255)
        status_str = f"TALKING (MAR:{mar:.2f})"
    else:
        box_color = (148, 163, 184, 180)   # Slate gray
        fill_tint = (148, 163, 184, 15)
        tag_bg = (30, 41, 59, 220)
        tag_text = (203, 213, 225)
        status_str = f"SILENT (MAR:{mar:.2f})"

    # Draw face rectangle
    draw.rectangle([(x1, y1), (x2, y2)], outline=box_color, width=3)

    # Corner accents
    c_len = min(16, max(6, (x2 - x1) // 5))
    accent_color = (255, 255, 255, 255) if is_speaking else (200, 200, 200, 200)
    # Top-left
    draw.line([(x1, y1), (x1 + c_len, y1)], fill=accent_color, width=4)
    draw.line([(x1, y1), (x1, y1 + c_len)], fill=accent_color, width=4)
    # Top-right
    draw.line([(x2, y1), (x2 - c_len, y1)], fill=accent_color, width=4)
    draw.line([(x2, y1), (x2, y1 + c_len)], fill=accent_color, width=4)
    # Bottom-left
    draw.line([(x1, y2), (x1 + c_len, y2)], fill=accent_color, width=4)
    draw.line([(x1, y2), (x1, y2 - c_len)], fill=accent_color, width=4)
    # Bottom-right
    draw.line([(x2, y2), (x2 - c_len, y2)], fill=accent_color, width=4)
    draw.line([(x2, y2), (x2, y2 - c_len)], fill=accent_color, width=4)

    # Tag Banner above or below box
    full_tag = f"{label}  {status_str}"
    t_box = font.getbbox(full_tag)
    tw = t_box[2] - t_box[0] + 12
    th = t_box[3] - t_box[1] + 8

    tag_y1 = max(48, y1 - th)
    tag_x1 = max(4, min(x1, width - tw - 4))
    draw.rectangle([(tag_x1, tag_y1), (tag_x1 + tw, tag_y1 + th)], fill=tag_bg)
    draw.text((tag_x1 + 6, tag_y1 + 4), full_tag, fill=tag_text, font=font)


def draw_ocr_box(
    draw: ImageDraw.ImageDraw,
    bbox: List[float],
    width: int,
    height: int,
    text: str,
    font: ImageFont.ImageFont,
):
    ymin, xmin, ymax, xmax = bbox
    x1 = int(xmin * width)
    y1 = int(ymin * height)
    x2 = int(xmax * width)
    y2 = int(ymax * height)

    if x2 <= x1 or y2 <= y1:
        return

    # OCR color: vibrant Pink/Cyan
    box_color = (236, 72, 153, 230)
    tag_bg = (236, 72, 153, 220)

    draw.rectangle([(x1, y1), (x2, y2)], outline=box_color, width=2)

    # Label
    display_text = f'OCR: "{text}"' if len(text) <= 30 else f'OCR: "{text[:27]}..."'
    t_box = font.getbbox(display_text)
    tw = t_box[2] - t_box[0] + 10
    th = t_box[3] - t_box[1] + 6

    tag_y1 = max(48, y1 - th)
    tag_x1 = max(4, min(x1, width - tw - 4))
    draw.rectangle([(tag_x1, tag_y1), (tag_x1 + tw, tag_y1 + th)], fill=tag_bg)
    draw.text((tag_x1 + 5, tag_y1 + 3), display_text, fill=(255, 255, 255), font=font)


def draw_subtitle_banner(
    draw: ImageDraw.ImageDraw,
    width: int,
    height: int,
    speaker_label: str,
    dialogue_text: str,
    font_bold: ImageFont.ImageFont,
    font_text: ImageFont.ImageFont,
):
    if not dialogue_text:
        return

    banner_pad = 16
    banner_h = 76
    y1 = height - banner_h - 24
    y2 = height - 24
    x1 = banner_pad
    x2 = width - banner_pad

    # Background card
    draw.rectangle([(x1, y1), (x2, y2)], fill=(11, 15, 23, 230))
    draw.rectangle([(x1, y1), (x2, y2)], outline=(6, 182, 212, 160), width=1)

    # Speaker chip
    chip_h = 22
    s_box = font_bold.getbbox(speaker_label)
    cw = s_box[2] - s_box[0] + 16
    draw.rectangle([(x1 + 12, y1 + 8), (x1 + 12 + cw, y1 + 8 + chip_h)], fill=(6, 182, 212, 240))
    draw.text((x1 + 20, y1 + 10), speaker_label, fill=(0, 0, 0), font=font_bold)

    # Dialogue text (clean native script)
    # Truncate if ultra long
    max_chars = 70
    render_text = dialogue_text if len(dialogue_text) <= max_chars else dialogue_text[:max_chars-3] + "..."
    draw.text((x1 + 12, y1 + 36), render_text, fill=(255, 255, 255), font=font_text)


def export_annotated_video(
    reel_id: str,
    max_seconds: Optional[float] = None,
    auto_open: bool = False,
) -> Path:
    reel_dir = Path("data/reels") / reel_id
    if not reel_dir.exists():
        raise FileNotFoundError(f"Reel folder not found: {reel_dir}")

    video_path = reel_dir / "video.mp4"
    audio_path = reel_dir / "audio.wav"
    timeline_path = reel_dir / "timeline.json"

    if not video_path.exists():
        raise FileNotFoundError(f"video.mp4 not found in {reel_dir}")

    # Ensure timeline.json exists
    if not timeline_path.exists():
        console.print(f"[yellow]timeline.json missing for {reel_id}. Running TimelineAligner...[/yellow]")
        from app.fusion.timeline_aligner import TimelineAligner
        aligner = TimelineAligner()
        aligner.align(reel_id)

    with open(timeline_path, "r", encoding="utf-8") as f:
        timeline = json.load(f)

    pacing_dna = timeline.get("pacing_dna", {})
    asd = pacing_dna.get("pacing", {}).get("avg_shot_duration_sec", 0.0)
    resolved_speakers = timeline.get("resolved_speakers", {})
    speaker_to_face = resolved_speakers.get("speaker_to_face", {})

    tracks = timeline.get("tracks", {})
    shots = tracks.get("shots", [])
    utterances = tracks.get("speech_utterances", [])
    faces = tracks.get("faces", [])
    ocr_list = tracks.get("ocr", [])

    total_duration_ms = timeline.get("duration_ms", 1000)

    # Open video capture
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if max_seconds and max_seconds > 0:
        frames_to_process = min(total_frames, int(max_seconds * fps))
    else:
        frames_to_process = total_frames

    console.print(
        f"[bold cyan][ANNOTATED VIDEO EXPORTER][/bold cyan] Rendering debug visual overlays for "
        f"[green]{reel_id}[/green]\n"
        f"  Resolution: [yellow]{width}x{height}[/yellow] | FPS: [yellow]{fps:.1f}[/yellow] | "
        f"Frames: [yellow]{frames_to_process}[/yellow] (~{frames_to_process/fps:.1f}s)"
    )

    # Fonts
    font_bold = get_font(size=max(13, int(height * 0.016)))
    font_sm = get_font(size=max(12, int(height * 0.014)))
    font_sub = get_font(size=max(16, int(height * 0.021)))

    # Temp video writer (without audio)
    temp_video_path = reel_dir / "annotated_temp_video.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(str(temp_video_path), fourcc, fps, (width, height))

    # Pre-index shot cuts for flash effects
    cut_timestamps_ms = {s.get("start_ms", 0) for s in shots if s.get("start_ms", 0) > 0}

    frame_idx = 0
    for _ in track(range(frames_to_process), description="[cyan]Rendering visual overlays...[/cyan]"):
        ret, frame = cap.read()
        if not ret:
            break

        current_ms = int((frame_idx / fps) * 1000)

        # Convert OpenCV BGR frame to PIL RGB Image
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(frame_rgb)
        draw = ImageDraw.Draw(pil_img, "RGBA")

        # 1. Shot info & Cut flash
        active_shot_idx = 1
        for i, s in enumerate(shots):
            if current_ms >= s.get("start_ms", 0) and current_ms <= s.get("end_ms", 0):
                active_shot_idx = i + 1
                break

        # Check if cut happened in last 180ms
        is_cut_flash = any(0 <= (current_ms - c_ms) <= 180 for c_ms in cut_timestamps_ms)

        draw_hud_header(
            draw=draw,
            width=width,
            current_ms=current_ms,
            total_ms=total_duration_ms,
            active_shot_idx=active_shot_idx,
            total_shots=max(1, len(shots)),
            asd=asd,
            is_cut_flash=is_cut_flash,
            font_bold=font_bold,
            font_sm=font_sm,
        )

        # 2. Draw OCR overlays
        for ocr in ocr_list:
            if ocr.get("start_ms", 0) <= current_ms <= ocr.get("end_ms", 0):
                p = ocr.get("payload", {})
                bbox = p.get("bbox", [])
                if len(bbox) == 4:
                    draw_ocr_box(
                        draw=draw,
                        bbox=bbox,
                        width=width,
                        height=height,
                        text=p.get("text", ""),
                        font=font_sm,
                    )

        # 3. Draw Faces & MAR
        for face in faces:
            if face.get("start_ms", 0) <= current_ms <= face.get("end_ms", 0):
                p = face.get("payload", {})
                bbox = p.get("bbox", [])
                if len(bbox) == 4:
                    face_id = p.get("face_id", "face")
                    mar = p.get("avg_mar", 0.0)
                    is_speaking = p.get("is_speaking", False)

                    # Look up bound acoustic speaker
                    bound_spk = next((spk for spk, fid in speaker_to_face.items() if fid == face_id), None)
                    spk_tag = f"[{bound_spk}] {face_id}" if bound_spk else face_id

                    draw_face_box(
                        draw=draw,
                        bbox=bbox,
                        width=width,
                        height=height,
                        label=spk_tag,
                        mar=mar,
                        is_speaking=is_speaking,
                        font=font_sm,
                    )

        # 4. Draw Subtitle Lower-Third
        active_utt = None
        for utt in utterances:
            if utt.get("start_ms", 0) <= current_ms <= utt.get("end_ms", 0):
                active_utt = utt
                break

        if active_utt:
            up = active_utt.get("payload", {})
            spk_label = up.get("speaker_canonical") or up.get("speaker") or "SPEAKER"
            face_label = up.get("resolved_face_id") or "Off-Screen"
            full_spk_display = f"{spk_label} ({face_label})"

            draw_subtitle_banner(
                draw=draw,
                width=width,
                height=height,
                speaker_label=full_spk_display,
                dialogue_text=up.get("text", ""),
                font_bold=font_bold,
                font_text=font_sub,
            )

        # Convert back to OpenCV BGR and write
        annotated_bgr = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        out.write(annotated_bgr)
        frame_idx += 1

    cap.release()
    out.release()

    # Mux audio back with ffmpeg
    final_output_path = reel_dir / "annotated_debug.mp4"
    console.print(f"[dim]Muxing original audio onto annotated video with ffmpeg...[/dim]")

    if audio_path.exists():
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-i", str(temp_video_path),
            "-i", str(audio_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-shortest",
            str(final_output_path),
        ]
    else:
        # Just rename if no audio
        ffmpeg_cmd = [
            "ffmpeg",
            "-y",
            "-i", str(temp_video_path),
            "-c:v", "copy",
            str(final_output_path),
        ]

    res = subprocess.run(ffmpeg_cmd, capture_output=True, text=True)
    if res.returncode != 0:
        console.print(f"[yellow]Warning: ffmpeg audio mux returned code {res.returncode}. Keeping raw video.[/yellow]")
        temp_video_path.rename(final_output_path)
    else:
        if temp_video_path.exists():
            temp_video_path.unlink()

    console.print(f"[bold green]✓ Annotated debug video exported:[/bold green] [cyan]{final_output_path}[/cyan]")

    if auto_open:
        try:
            subprocess.run(["open", str(final_output_path)])
            console.print(f"[dim]Opened video in default player.[/dim]")
        except Exception as e:
            console.print(f"[dim]Could not auto-open: {e}[/dim]")

    return final_output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python tools/export_annotated_video.py <reel_id> [--open] [--max-sec <float>][/yellow]")
        console.print("[dim]Example: python tools/export_annotated_video.py DdMkWeaxKTT --open --max-sec 15[/dim]")
        sys.exit(1)

    target_reel = sys.argv[1]
    should_open = "--open" in sys.argv
    max_s = None

    if "--max-sec" in sys.argv:
        idx = sys.argv.index("--max-sec")
        if idx + 1 < len(sys.argv):
            max_s = float(sys.argv[idx + 1])

    export_annotated_video(target_reel, max_seconds=max_s, auto_open=should_open)
