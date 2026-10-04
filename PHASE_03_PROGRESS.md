# Phase 0.3: Visual & Speaker Lanes — Implementation Progress

**Current Active Phase:** `Phase 0.3: Visual and Speaker Lanes`  
**Status:** In Progress  
**Target:** Modular, test-driven implementation across 5 sub-phases.

---

## Sub-Phase Breakdown & Roadmap

```text
Phase 0.3: Visual & Speaker Lanes
├── 3.1: Shot Boundary Detection (PySceneDetect) [READY TO START]
├── 3.2: On-Screen OCR & Text Extraction (RapidOCR / Apple Vision) [PENDING]
├── 3.3: Face & Mouth Aspect Ratio Tracking (MediaPipe) [PENDING]
├── 3.4: Dedicated Speaker Diarization (PyAnnote Audio) [PENDING]
└── 3.5: Multimodal Fusion & Speaker Resolver (TimelineAligner + Resolver) [PENDING]
```

---

## Sub-Phase Checklist

### 🔲 Sub-Phase 3.1: Shot Boundary Detection (`shots`) — *CURRENT*
- [ ] Implement `PySceneDetectProvider` in `app/capabilities/shots/providers/pyscenedetect.py`.
- [ ] Register capability in `app/capabilities/shots/__init__.py`.
- [ ] Emit standardized `CanonicalEvent(track="shot", type="scene_cut")` with millisecond start/end and cut transition metrics.
- [ ] Calculate video pacing statistics: `total_shots`, individual shot durations, and Average Shot Duration (`avg_shot_duration_sec`).
- [ ] Create test CLI: `tests/test_shots.py` to verify against real reels (`DdMkWeaxKTT`, `DeEKAEKhx_Z`).
- [ ] Save manifest: `manifest_shots_pyscenedetect_v1.0.0.json`.

---

### 🔲 Sub-Phase 3.2: On-Screen OCR (`ocr`)
- [ ] Implement OCR provider in `app/capabilities/ocr/providers/rapidocr.py` (or `apple_vision.py`).
- [ ] Frame sampling at 4–5 fps to balance speed with text capture.
- [ ] Emit `CanonicalEvent(track="ocr", type="text_overlay")` with detected text, bounding boxes, and timestamp ranges.
- [ ] Filter out transient noise and duplicate adjacent detections.
- [ ] Create test CLI: `tests/test_ocr.py`.

---

### 🔲 Sub-Phase 3.3: Face & Active Speaker Tracking (`faces`)
- [ ] Implement Face Provider in `app/capabilities/faces/providers/mediapipe.py`.
- [ ] Extract face bounding boxes and Mouth Aspect Ratio (MAR) per sampled frame.
- [ ] Classify active speaking intervals (MAR > speaking threshold).
- [ ] Emit `CanonicalEvent(track="faces", type="face_track")` with face ID, coordinates, and speaking state.
- [ ] Create test CLI: `tests/test_faces.py`.

---

### 🔲 Sub-Phase 3.4: Dedicated Speaker Diarization (`diarization`)
- [ ] Implement `PyAnnoteDiarizationProvider` in `app/capabilities/diarization/providers/pyannote.py`.
- [ ] Emit `CanonicalEvent(track="diarization", type="speaker_turn")` with acoustic voice cluster IDs (`SPEAKER_00`, `SPEAKER_01`).
- [ ] Ensure provider works agnostically across any speech backend (Whisper or AssemblyAI).
- [ ] Create test CLI: `tests/test_diarization.py`.

---

### 🔲 Sub-Phase 3.5: Consensus, Speaker Resolver & Multimodal Fusion (`fusion`)
- [ ] Implement `app/fusion/timeline_aligner.py`: Chronologically fuse `speech`, `shots`, `ocr`, `faces`, and `diarization`.
- [ ] Implement `app/fusion/speaker_resolver.py`: Correlate voice clusters from diarization with visual mouth movement (MAR) to pair voice to face.
- [ ] Implement fallback safety: Produce valid `timeline.json` even if optional lanes (e.g. OCR or faces) detect nothing.
- [ ] Create test CLI: `tests/test_fusion.py`.
