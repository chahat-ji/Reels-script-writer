# Phase 0.2: Multi-Provider Speech & Preflight

## Objective
Prove that providers can be hot-swapped via configuration without code changes. Introduce Phase 0 preflight inspection, fallback routing, and budget validation.

## Scope of Work
1. **Local Speech Provider (`app/capabilities/speech/providers/mlx_whisper.py`)**:
   - Implement local transcription using `mlx-whisper` (or `whisper.cpp`/`whisperx` for non-Apple Silicon).
2. **Secondary Paid Provider (`app/capabilities/speech/providers/deepgram.py` or `gemini.py`)**:
   - Implement Deepgram or Gemini 1.5 Flash transcription wrapper.
3. **Phase 0 Preflight Probe (`app/core/preflight.py`)**:
   - Detect audio conditions: Music-to-voice energy ratio (check if background music is heavy).
   - Check language/accent markers (Hindi/Hinglish detection).
4. **Router Fallback Execution (`app/core/router.py`)**:
   - Execute fallback chain (e.g., attempt `mlx_whisper` first; if it errors or confidence < threshold, escalate to `assemblyai`).
5. **Budget Guard (`app/core/budget.py`)**:
   - Check `limits.max_usd_per_reel` before invoking paid APIs.

## Acceptance Criteria
- [ ] Switching `profiles.yaml` from `local-only` to `balanced` switches provider execution seamlessly.
- [ ] Preflight detects heavy music and flags stem separation need.
- [ ] Budget guard aborts or skips paid API calls if limit is exceeded.