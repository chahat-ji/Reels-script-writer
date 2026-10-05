"""
tools/generate_timeline_report.py
Generates an interactive, standalone HTML Multimodal Timeline Dashboard (Option 1).

Visualizes:
- Embedded video playback
- Real-time synchronized multi-track scrubber (Shots, Speech, Faces/MAR, OCR)
- Dynamic playhead tracking & seek-on-click
- Speaker-to-Face resolution matrix
- Video Pacing DNA scorecards
- Live synchronized screenplay dialogue feed

Usage:
    python tools/generate_timeline_report.py DdMkWeaxKTT [--open]
    python tools/generate_timeline_report.py DeEKAEKhx_Z [--open]
    python tools/generate_timeline_report.py all
"""

import html
import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.console import Console

console = Console()

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Reel AI Inspector: __REEL_ID__</title>
  <style>
    :root {
      --bg: #0b0f17;
      --card-bg: rgba(18, 24, 38, 0.85);
      --card-border: rgba(255, 255, 255, 0.08);
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --accent-cyan: #06b6d4;
      --accent-green: #10b981;
      --accent-purple: #8b5cf6;
      --accent-amber: #f59e0b;
      --accent-rose: #f43f5e;
      --accent-blue: #3b82f6;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text-main);
      padding: 24px;
      min-height: 100vh;
      line-height: 1.5;
    }

    .container {
      max-width: 1440px;
      margin: 0 auto;
    }

    /* Header */
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--card-border);
    }

    .title-group h1 {
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 12px;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .badge-primary {
      background: rgba(6, 182, 212, 0.15);
      color: var(--accent-cyan);
      border: 1px solid rgba(6, 182, 212, 0.3);
    }

    .badge-pacing {
      background: __PACING_BG__;
      color: __PACING_COLOR__;
      border: 1px solid __PACING_BORDER__;
    }

    /* KPI Grid */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 14px;
      margin-bottom: 24px;
    }

    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 16px;
      backdrop-filter: blur(12px);
    }

    .card-label {
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 4px;
      display: flex;
      align-items: center;
      gap: 6px;
    }

    .card-value {
      font-size: 24px;
      font-weight: 700;
      letter-spacing: -0.03em;
    }

    .card-subtext {
      font-size: 12px;
      color: var(--text-muted);
      margin-top: 4px;
    }

    /* Main Layout: Video + Screenplay */
    .main-grid {
      display: grid;
      grid-template-columns: 380px 1fr;
      gap: 24px;
      margin-bottom: 24px;
    }

    @media (max-width: 1024px) {
      .main-grid {
        grid-template-columns: 1fr;
      }
    }

    /* Video Player Column */
    .video-panel {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }

    .video-wrapper {
      position: relative;
      background: #000;
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid var(--card-border);
      aspect-ratio: 9 / 16;
      max-height: 560px;
      display: flex;
      justify-content: center;
      align-items: center;
    }

    video {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }

    .video-hud {
      position: absolute;
      top: 12px;
      left: 12px;
      right: 12px;
      display: flex;
      justify-content: space-between;
      pointer-events: none;
      z-index: 10;
    }

    .hud-chip {
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(8px);
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 600;
      border: 1px solid rgba(255, 255, 255, 0.15);
      color: #fff;
    }

    /* Timeline & Screenplay Column */
    .content-panel {
      display: flex;
      flex-direction: column;
      gap: 16px;
    }

    /* Multi-Track Container */
    .tracks-container {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 20px;
      position: relative;
    }

    .tracks-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }

    .tracks-title {
      font-size: 15px;
      font-weight: 700;
      letter-spacing: -0.01em;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .scrubber-timer {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 14px;
      font-weight: 600;
      color: var(--accent-cyan);
    }

    .tracks-viewport {
      position: relative;
      background: #06090e;
      border: 1px solid rgba(255, 255, 255, 0.05);
      border-radius: 10px;
      padding: 12px 0;
      overflow-x: hidden;
      user-select: none;
      cursor: crosshair;
    }

    .playhead {
      position: absolute;
      top: 0;
      bottom: 0;
      width: 2px;
      background: #f43f5e;
      box-shadow: 0 0 8px #f43f5e;
      z-index: 20;
      pointer-events: none;
      transform: translateX(-50%);
      left: 0%;
      transition: left 0.05s linear;
    }

    .playhead-handle {
      position: absolute;
      top: -6px;
      left: -5px;
      width: 12px;
      height: 12px;
      background: #f43f5e;
      border-radius: 50%;
      border: 2px solid #fff;
    }

    .track-lane {
      position: relative;
      height: 36px;
      margin-bottom: 8px;
      border-bottom: 1px dashed rgba(255, 255, 255, 0.05);
    }

    .track-lane:last-child {
      margin-bottom: 0;
      border-bottom: none;
    }

    .lane-label {
      position: absolute;
      left: 8px;
      top: 8px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-muted);
      z-index: 5;
      pointer-events: none;
    }

    .block {
      position: absolute;
      height: 28px;
      top: 4px;
      border-radius: 5px;
      font-size: 11px;
      font-weight: 600;
      display: flex;
      align-items: center;
      padding: 0 6px;
      overflow: hidden;
      white-space: nowrap;
      text-overflow: ellipsis;
      cursor: pointer;
      transition: transform 0.1s, filter 0.1s;
      z-index: 10;
    }

    .block:hover {
      transform: translateY(-2px);
      filter: brightness(1.2);
      z-index: 15;
    }

    /* Track Block Styles */
    .block-shot {
      background: rgba(59, 130, 246, 0.35);
      border: 1px solid rgba(59, 130, 246, 0.7);
      color: #93c5fd;
    }

    .block-face-speaking {
      background: rgba(16, 185, 129, 0.35);
      border: 1px solid #10b981;
      color: #a7f3d0;
      box-shadow: 0 0 6px rgba(16, 185, 129, 0.25);
    }

    .block-face-silent {
      background: rgba(148, 163, 184, 0.2);
      border: 1px dashed rgba(148, 163, 184, 0.5);
      color: #cbd5e1;
    }

    .block-ocr {
      background: rgba(236, 72, 153, 0.3);
      border: 1px solid rgba(236, 72, 153, 0.7);
      color: #fbcfe8;
    }

    /* Resolution Matrix */
    .resolver-section {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 16px;
    }

    .section-title {
      font-size: 14px;
      font-weight: 700;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .resolver-grid {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .resolver-card {
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(255, 255, 255, 0.06);
      border-radius: 8px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .resolver-card.matched {
      border-left: 4px solid var(--accent-green);
    }

    .resolver-card.off-screen {
      border-left: 4px solid var(--accent-amber);
    }

    .resolver-pair {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-weight: 700;
      font-size: 13px;
    }

    .arrow-icon {
      color: var(--text-muted);
      font-size: 12px;
    }

    /* Screenplay / Utterance Feed */
    .screenplay-container {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 14px;
      padding: 20px;
      max-height: 480px;
      overflow-y: auto;
    }

    .dialogue-item {
      padding: 12px 14px;
      border-radius: 8px;
      margin-bottom: 8px;
      border: 1px solid transparent;
      cursor: pointer;
      transition: background 0.15s, border-color 0.15s;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }

    .dialogue-item:hover {
      background: rgba(255, 255, 255, 0.04);
      border-color: rgba(255, 255, 255, 0.08);
    }

    .dialogue-item.active {
      background: rgba(6, 182, 212, 0.12);
      border-color: rgba(6, 182, 212, 0.4);
      box-shadow: 0 0 12px rgba(6, 182, 212, 0.15);
    }

    .dialogue-meta {
      display: flex;
      align-items: center;
      gap: 10px;
      font-size: 12px;
    }

    .speaker-pill {
      padding: 2px 8px;
      border-radius: 4px;
      font-weight: 700;
      font-size: 11px;
    }

    .time-chip {
      font-family: ui-monospace, monospace;
      color: var(--text-muted);
      font-size: 11px;
    }

    .dialogue-text {
      font-size: 15px;
      line-height: 1.4;
      color: #fff;
    }

    /* Tooltip */
    #tooltip {
      position: fixed;
      background: rgba(15, 23, 42, 0.95);
      border: 1px solid rgba(255, 255, 255, 0.2);
      border-radius: 6px;
      padding: 6px 10px;
      font-size: 12px;
      color: #fff;
      pointer-events: none;
      z-index: 1000;
      display: none;
      box-shadow: 0 4px 14px rgba(0,0,0,0.5);
    }
  </style>
</head>
<body>

<div id="tooltip"></div>

<div class="container">

  <!-- Header -->
  <div class="header">
    <div class="title-group">
      <h1>
        🎬 Reel Multimodal AI Inspector
        <span class="badge badge-primary">__REEL_ID__</span>
        <span class="badge badge-pacing">__PACING_LABEL__</span>
      </h1>
    </div>
    <div style="font-size: 13px; color: var(--text-muted);">
      Duration: <strong style="color:#fff;">__DURATION_SEC__s</strong> (__DURATION_MS__ ms)
    </div>
  </div>

  <!-- KPI Grid -->
  <div class="kpi-grid">
    <div class="card">
      <div class="card-label">⚡ Visual Cuts (ASD)</div>
      <div class="card-value" style="color: var(--accent-blue);">__TOTAL_SHOTS__ cuts</div>
      <div class="card-subtext">Avg Shot Duration: <strong>__ASD__s</strong> (Hook: __HOOK_SEC__s)</div>
    </div>

    <div class="card">
      <div class="card-label">🎙️ Speech Delivery</div>
      <div class="card-value" style="color: var(--accent-cyan);">__TOTAL_WORDS__ words</div>
      <div class="card-subtext">Speed: <strong>__WPM__ WPM</strong> (__PRIMARY_ASR__)</div>
    </div>

    <div class="card">
      <div class="card-label">📺 On-Screen Text (OCR)</div>
      <div class="card-value" style="color: var(--accent-rose);">__TOTAL_OCR__ spans</div>
      <div class="card-subtext">Screen coverage: <strong>__OCR_COV__%</strong></div>
    </div>

    <div class="card">
      <div class="card-label">👤 Face Tracking & MAR</div>
      <div class="card-value" style="color: var(--accent-green);">__TOTAL_FACES__ tracks</div>
      <div class="card-subtext">Face on-screen: <strong>__FACE_COV__%</strong> | Speech: <strong>__SPK_COV__%</strong></div>
    </div>

    <div class="card">
      <div class="card-label">👥 Speaker Diarization</div>
      <div class="card-value" style="color: var(--accent-purple);">__UNIQUE_SPEAKERS__ speakers</div>
      <div class="card-subtext">Resolved: <strong>__RESOLVED_COUNT__</strong> acoustic clusters</div>
    </div>
  </div>

  <!-- Main Grid: Video + Content -->
  <div class="main-grid">

    <!-- Video Player Column -->
    <div class="video-panel">
      <div class="video-wrapper">
        <div class="video-hud">
          <div class="hud-chip" id="hud-shot">Shot 1</div>
          <div class="hud-chip" id="hud-speaker">SPEAKER_00</div>
        </div>
        <video id="video-player" controls preload="metadata">
          <source src="video.mp4" type="video/mp4">
          Your browser does not support video playback.
        </video>
      </div>

      <!-- Speaker Resolution Cards -->
      <div class="resolver-section">
        <div class="section-title">🔗 Acoustic Voice ⟷ Visual Face Resolver</div>
        <div class="resolver-grid" id="resolver-container">
          <!-- Populated by JS -->
        </div>
      </div>
    </div>

    <!-- Multi-Track Timeline & Screenplay Column -->
    <div class="content-panel">

      <!-- Multi-Track Scroller -->
      <div class="tracks-container">
        <div class="tracks-header">
          <div class="tracks-title">⏱️ Multimodal Synchronized Timeline (Click to Seek)</div>
          <div class="scrubber-timer" id="time-display">00:00.00 / __DURATION_SEC__s</div>
        </div>

        <div class="tracks-viewport" id="timeline-viewport">
          <div class="playhead" id="playhead">
            <div class="playhead-handle"></div>
          </div>

          <!-- Track 1: Shots -->
          <div class="track-lane" id="lane-shots">
            <div class="lane-label">Shots</div>
          </div>

          <!-- Track 2: Speech Utterances -->
          <div class="track-lane" id="lane-speech">
            <div class="lane-label">Dialogue</div>
          </div>

          <!-- Track 3: Faces & Speaking MAR -->
          <div class="track-lane" id="lane-faces">
            <div class="lane-label">Faces (MAR)</div>
          </div>

          <!-- Track 4: On-Screen OCR -->
          <div class="track-lane" id="lane-ocr">
            <div class="lane-label">On-Screen Text</div>
          </div>
        </div>
      </div>

      <!-- Synchronized Screenplay Feed -->
      <div class="screenplay-container">
        <div class="section-title">📜 Chronological Dialogue & Screenplay Feed</div>
        <div id="dialogue-feed">
          <!-- Populated by JS -->
        </div>
      </div>

    </div>

  </div>

</div>

<script>
  const timelineData = __TIMELINE_DATA_JSON__;
  const totalDurationMs = timelineData.duration_ms || 1000;
  const video = document.getElementById("video-player");
  const playhead = document.getElementById("playhead");
  const timeDisplay = document.getElementById("time-display");
  const viewport = document.getElementById("timeline-viewport");
  const tooltip = document.getElementById("tooltip");

  const hudShot = document.getElementById("hud-shot");
  const hudSpeaker = document.getElementById("hud-speaker");

  // Speaker Color Palette
  const speakerColors = [
    { bg: "rgba(6, 182, 212, 0.25)", border: "#06b6d4", text: "#a5f3fc" },
    { bg: "rgba(139, 92, 246, 0.25)", border: "#8b5cf6", text: "#ddd6fe" },
    { bg: "rgba(245, 158, 11, 0.25)", border: "#f59e0b", text: "#fde68a" },
    { bg: "rgba(236, 72, 153, 0.25)", border: "#ec4899", text: "#fbcfe8" },
    { bg: "rgba(16, 185, 129, 0.25)", border: "#10b981", text: "#a7f3d0" }
  ];

  function getSpeakerStyle(spk) {
    const num = parseInt((spk || "").replace(/\\D/g, "")) || 0;
    return speakerColors[num % speakerColors.length];
  }

  function formatTime(sec) {
    const m = Math.floor(sec / 60);
    const s = (sec % 60).toFixed(2);
    return m.toString().padStart(2, '0') + ":" + s.padStart(5, '0');
  }

  // 1. Populate Speaker Resolution Matrix
  const resolverContainer = document.getElementById("resolver-container");
  const resolutionDetails = timelineData.resolved_speakers?.details || {};
  
  if (Object.keys(resolutionDetails).length === 0) {
    resolverContainer.innerHTML = '<div style="color:var(--text-muted);font-size:13px;">No speaker clusters detected.</div>';
  } else {
    for (const [spk, info] of Object.entries(resolutionDetails)) {
      const isMatched = info.status === "matched";
      const card = document.createElement("div");
      card.className = "resolver-card " + (isMatched ? 'matched' : 'off-screen');
      
      const faceDisplay = info.face_id ? info.face_id : "Off-Screen (Voiceover)";
      const spkOverlapSec = (info.speaking_overlap_ms / 1000).toFixed(1);
      const confPct = Math.round((info.confidence || 0) * 100);

      card.innerHTML = 
        '<div class="resolver-pair">' +
          '<span style="color:var(--accent-cyan);">' + spk + '</span>' +
          '<span class="arrow-icon">➔</span>' +
          '<span style="color:' + (isMatched ? 'var(--accent-green)' : 'var(--accent-amber)') + '">' + faceDisplay + '</span>' +
        '</div>' +
        '<div style="font-size:11px;color:var(--text-muted);display:flex;justify-content:space-between;">' +
          '<span>Speaking overlap: <strong>' + spkOverlapSec + 's</strong></span>' +
          '<span>Match: <strong>' + confPct + '%</strong></span>' +
        '</div>';
      resolverContainer.appendChild(card);
    }
  }

  // 2. Render Multi-Track Lanes
  const laneShots = document.getElementById("lane-shots");
  const laneSpeech = document.getElementById("lane-speech");
  const laneFaces = document.getElementById("lane-faces");
  const laneOcr = document.getElementById("lane-ocr");

  // Track 1: Shots
  (timelineData.tracks.shots || []).forEach((shot, i) => {
    const leftPct = (shot.start_ms / totalDurationMs) * 100;
    const widthPct = Math.max(0.5, ((shot.end_ms - shot.start_ms) / totalDurationMs) * 100);
    const block = document.createElement("div");
    block.className = "block block-shot";
    block.style.left = leftPct + "%";
    block.style.width = widthPct + "%";
    block.innerText = "S" + (i + 1) + " (" + (shot.payload.duration_sec || 0).toFixed(1) + "s)";
    block.onclick = () => seekTo(shot.start_ms);
    block.onmouseenter = (e) => showTooltip(e, "Shot #" + (i + 1) + ": " + (shot.start_ms/1000).toFixed(2) + "s - " + (shot.end_ms/1000).toFixed(2) + "s (" + shot.payload.duration_sec + "s)");
    block.onmouseleave = hideTooltip;
    laneShots.appendChild(block);
  });

  // Track 2: Speech Utterances
  (timelineData.tracks.speech_utterances || []).forEach((utt, i) => {
    const leftPct = (utt.start_ms / totalDurationMs) * 100;
    const widthPct = Math.max(0.5, ((utt.end_ms - utt.start_ms) / totalDurationMs) * 100);
    const spk = utt.payload.speaker_canonical || utt.payload.speaker || "SPEAKER_00";
    const style = getSpeakerStyle(spk);

    const block = document.createElement("div");
    block.className = "block";
    block.style.left = leftPct + "%";
    block.style.width = widthPct + "%";
    block.style.background = style.bg;
    block.style.borderColor = style.border;
    block.style.color = style.text;
    block.innerText = utt.payload.text || spk;
    block.onclick = () => seekTo(utt.start_ms);
    block.onmouseenter = (e) => showTooltip(e, "[" + spk + '] "' + utt.payload.text + '"\\n' + (utt.start_ms/1000).toFixed(2) + "s → " + (utt.end_ms/1000).toFixed(2) + "s");
    block.onmouseleave = hideTooltip;
    laneSpeech.appendChild(block);
  });

  // Track 3: Faces & MAR
  (timelineData.tracks.faces || []).forEach((face, i) => {
    const leftPct = (face.start_ms / totalDurationMs) * 100;
    const widthPct = Math.max(0.5, ((face.end_ms - face.start_ms) / totalDurationMs) * 100);
    const isSpeaking = face.payload.is_speaking;

    const block = document.createElement("div");
    block.className = "block " + (isSpeaking ? 'block-face-speaking' : 'block-face-silent');
    block.style.left = leftPct + "%";
    block.style.width = widthPct + "%";
    block.innerText = face.payload.face_id + " (MAR:" + face.payload.avg_mar + ")";
    block.onclick = () => seekTo(face.start_ms);
    block.onmouseenter = (e) => showTooltip(e, face.payload.face_id + ": " + (isSpeaking ? 'SPEAKING' : 'Silent') + " (MAR: " + face.payload.avg_mar + ")\\n" + (face.start_ms/1000).toFixed(2) + "s → " + (face.end_ms/1000).toFixed(2) + "s");
    block.onmouseleave = hideTooltip;
    laneFaces.appendChild(block);
  });

  // Track 4: OCR
  (timelineData.tracks.ocr || []).forEach((ocr, i) => {
    const leftPct = (ocr.start_ms / totalDurationMs) * 100;
    const widthPct = Math.max(0.5, ((ocr.end_ms - ocr.start_ms) / totalDurationMs) * 100);

    const block = document.createElement("div");
    block.className = "block block-ocr";
    block.style.left = leftPct + "%";
    block.style.width = widthPct + "%";
    block.innerText = ocr.payload.text || "Text";
    block.onclick = () => seekTo(ocr.start_ms);
    block.onmouseenter = (e) => showTooltip(e, 'OCR: "' + ocr.payload.text + '"\\n' + (ocr.start_ms/1000).toFixed(2) + "s → " + (ocr.end_ms/1000).toFixed(2) + "s");
    block.onmouseleave = hideTooltip;
    laneOcr.appendChild(block);
  });

  // 3. Render Screenplay Dialogue Feed
  const feed = document.getElementById("dialogue-feed");
  const dialogueElements = [];

  (timelineData.tracks.speech_utterances || []).forEach((utt, idx) => {
    const spk = utt.payload.speaker_canonical || utt.payload.speaker || "SPEAKER_00";
    const faceId = utt.payload.resolved_face_id || "Off-Screen";
    const style = getSpeakerStyle(spk);

    const item = document.createElement("div");
    item.className = "dialogue-item";
    item.dataset.start = utt.start_ms;
    item.dataset.end = utt.end_ms;
    item.onclick = () => seekTo(utt.start_ms);

    item.innerHTML = 
      '<div class="dialogue-meta">' +
        '<span class="speaker-pill" style="background:' + style.bg + ';border:1px solid ' + style.border + ';color:' + style.text + ';">' +
          spk + ' ➔ ' + faceId +
        '</span>' +
        '<span class="time-chip">' + (utt.start_ms/1000).toFixed(2) + 's → ' + (utt.end_ms/1000).toFixed(2) + 's</span>' +
      '</div>' +
      '<div class="dialogue-text">' + utt.payload.text + '</div>';

    feed.appendChild(item);
    dialogueElements.push(item);
  });

  // 4. Video Sync & Playhead Movement
  video.ontimeupdate = () => {
    const currentMs = video.currentTime * 1000;
    const currentPct = (currentMs / totalDurationMs) * 100;
    playhead.style.left = Math.min(100, Math.max(0, currentPct)) + "%";
    timeDisplay.innerText = formatTime(video.currentTime) + " / " + formatTime(totalDurationMs / 1000);

    // Update HUD
    const activeShot = (timelineData.tracks.shots || []).find(s => currentMs >= s.start_ms && currentMs <= s.end_ms);
    if (activeShot) {
      hudShot.innerText = "Shot " + ((timelineData.tracks.shots || []).indexOf(activeShot) + 1);
    }

    const activeUtt = (timelineData.tracks.speech_utterances || []).find(u => currentMs >= u.start_ms && currentMs <= u.end_ms);
    if (activeUtt) {
      hudSpeaker.innerText = (activeUtt.payload.speaker_canonical || activeUtt.payload.speaker) + " (" + (activeUtt.payload.resolved_face_id || 'Off-Screen') + ")";
    } else {
      hudSpeaker.innerText = "No active speech";
    }

    // Highlight Dialogue Feed
    dialogueElements.forEach(el => {
      const start = parseFloat(el.dataset.start);
      const end = parseFloat(el.dataset.end);
      if (currentMs >= start && currentMs <= end) {
        if (!el.classList.contains("active")) {
          el.classList.add("active");
          el.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }
      } else {
        el.classList.remove("active");
      }
    });
  };

  // Click on Timeline Viewport to Seek
  viewport.onclick = (e) => {
    const rect = viewport.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const pct = Math.max(0, Math.min(1, clickX / rect.width));
    video.currentTime = (pct * totalDurationMs) / 1000;
  };

  function seekTo(ms) {
    video.currentTime = ms / 1000;
    video.play();
  }

  function showTooltip(e, text) {
    tooltip.innerText = text;
    tooltip.style.display = "block";
    tooltip.style.left = (e.clientX + 10) + "px";
    tooltip.style.top = (e.clientY + 10) + "px";
  }

  function hideTooltip() {
    tooltip.style.display = "none";
  }
</script>

</body>
</html>
"""


def generate_html(timeline_data: Dict[str, Any], reel_dir: Path) -> str:
    reel_id = timeline_data.get("reel_id", "Unknown")
    duration_ms = timeline_data.get("duration_ms", 1000)
    duration_sec = timeline_data.get("duration_sec", duration_ms / 1000.0)
    pacing_dna = timeline_data.get("pacing_dna", {})
    pacing = pacing_dna.get("pacing", {})
    speech = pacing_dna.get("speech", {})
    visuals = pacing_dna.get("visuals", {})
    speakers = pacing_dna.get("speakers", {})
    resolved = timeline_data.get("resolved_speakers", {})

    # Compute Pacing Badge
    asd = pacing.get("avg_shot_duration_sec", 0.0)
    if asd > 0 and asd < 1.8:
        pacing_color = "#ef4444"
        pacing_label = "Rapid-Fire / Hyper-Edited"
    elif asd <= 3.2:
        pacing_color = "#f59e0b"
        pacing_label = "Dynamic / Conversational"
    else:
        pacing_color = "#10b981"
        pacing_label = "Cinematic / Relaxed"

    timeline_json_str = json.dumps(timeline_data, ensure_ascii=False)

    rendered = (
        HTML_TEMPLATE
        .replace("__REEL_ID__", html.escape(reel_id))
        .replace("__DURATION_SEC__", f"{duration_sec:.2f}")
        .replace("__DURATION_MS__", str(duration_ms))
        .replace("__PACING_LABEL__", pacing_label)
        .replace("__PACING_COLOR__", pacing_color)
        .replace("__PACING_BG__", f"{pacing_color}22")
        .replace("__PACING_BORDER__", f"{pacing_color}55")
        .replace("__TOTAL_SHOTS__", str(pacing.get("total_shots", 0)))
        .replace("__ASD__", f"{asd:.2f}")
        .replace("__HOOK_SEC__", str(pacing.get("hook_shot_duration_sec", 0.0)))
        .replace("__TOTAL_WORDS__", str(speech.get("total_words", 0)))
        .replace("__WPM__", str(speech.get("words_per_minute", 0.0)))
        .replace("__PRIMARY_ASR__", str(speech.get("primary_asr", "none")))
        .replace("__TOTAL_OCR__", str(visuals.get("total_text_overlays", 0)))
        .replace("__OCR_COV__", str(visuals.get("ocr_coverage_pct", 0.0)))
        .replace("__TOTAL_FACES__", str(visuals.get("total_face_tracks", 0)))
        .replace("__FACE_COV__", str(visuals.get("face_on_screen_pct", 0.0)))
        .replace("__SPK_COV__", str(visuals.get("visual_speech_pct", 0.0)))
        .replace("__UNIQUE_SPEAKERS__", str(speakers.get("unique_speakers_detected", 0)))
        .replace("__RESOLVED_COUNT__", str(len(resolved.get("speaker_to_face", {}))))
        .replace("__TIMELINE_DATA_JSON__", timeline_json_str)
    )

    return rendered


def generate_report_for_reel(reel_id: str, auto_open: bool = False):
    reel_dir = Path("data/reels") / reel_id
    if not reel_dir.exists():
        console.print(f"[bold red]Error: Reel folder not found at {reel_dir}[/bold red]")
        return False

    timeline_path = reel_dir / "timeline.json"
    if not timeline_path.exists():
        console.print(f"[yellow]timeline.json not found for {reel_id}. Running TimelineAligner first...[/yellow]")
        from app.fusion.timeline_aligner import TimelineAligner
        aligner = TimelineAligner()
        aligner.align(reel_id)

    with open(timeline_path, "r", encoding="utf-8") as f:
        timeline_data = json.load(f)

    report_html = generate_html(timeline_data, reel_dir)
    out_path = reel_dir / "timeline_report.html"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(report_html)

    console.print(f"[bold green]✓ Generated interactive report:[/bold green] [cyan]{out_path}[/cyan]")

    if auto_open:
        try:
            webbrowser.open(f"file://{out_path.resolve()}")
            console.print(f"[dim]Opened {out_path.name} in default browser.[/dim]")
        except Exception as e:
            console.print(f"[dim]Could not auto-open browser: {e}[/dim]")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("[yellow]Usage: python tools/generate_timeline_report.py <reel_id|all> [--open][/yellow]")
        console.print("[dim]Example: python tools/generate_timeline_report.py DdMkWeaxKTT --open[/dim]")
        sys.exit(1)

    target = sys.argv[1]
    should_open = "--open" in sys.argv

    if target == "all":
        reels_root = Path("data/reels")
        for r_dir in sorted(reels_root.iterdir()):
            if r_dir.is_dir() and not r_dir.name.startswith("."):
                generate_report_for_reel(r_dir.name, auto_open=should_open)
    else:
        generate_report_for_reel(target, auto_open=should_open)
