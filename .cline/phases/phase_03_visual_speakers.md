# Phase 0.3: Visual and Speaker Lanes

## Objective
Extract comprehensive multi-modal evidence across visual and audio tracks and implement multi-provider consensus fusion.

## Scope of Work
1. **Shot Boundary Detection (`app/capabilities/shots/`)**:
   - Provider: `pyscenedetect` (local content/threshold detector).
2. **On-Screen OCR (`app/capabilities/ocr/`)**:
   - Provider: `rapidocr` or `apple_vision` (sample 4-5 fps).
3. **Face & Active Speaker Tracking (`app/capabilities/faces/`)**:
   - Provider: `mediapipe` (extract bounding boxes and Mouth Aspect Ratio / MAR).
4. **Diarization (`app/capabilities/diarization/`)**:
   - Provider: `pyannote` or `speechbrain_ecapa`.
5. **Consensus & Speaker Resolver (`app/fusion/`)**:
   - `timeline_aligner.py`: Align all provider events to a unified millisecond timeline.
   - `speaker_resolver.py`: Correlate voice clusters from diarization with visual mouth movement (MAR) to map voice to face.
   - `consensus.py`: Resolve multi-ASR discrepancies via voting or confidence ranking.

## Acceptance Criteria
- [ ] Pipeline produces an integrated multi-track timeline even if one lane (e.g., OCR or Diarization) fails.
- [ ] Speaker resolver matches audio diarization clusters to visible on-screen speakers.