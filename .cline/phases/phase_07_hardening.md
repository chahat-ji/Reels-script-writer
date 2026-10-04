# Phase 1.0: Hardening & Production Readiness

## Objective
Harden the entire engine against wild edge cases, manage system resources gracefully, and tune routing rules from benchmark data.

## Scope of Work
1. **Dynamic RAM Governor (`app/core/runner.py`)**:
   - Enforce sequential execution of heavy local neural models (e.g., Demucs, PyAnnote, Whisper) to avoid OOM crashes.
2. **Routing Rule Calibration (`config/routing_rules.yaml`)**:
   - Codify automatic provider selection based on benchmark thresholds (e.g., use AssemblyAI if Hinglish score > 0.6; use Demucs only if music energy > 0.45).
3. **Review Queue & Fallback Safety (`app/fusion/`)**:
   - Flag uncertain outputs (e.g., low face-to-voice match confidence) for optional human review without halting the pipeline.
4. **Stress Testing (`tests/`)**:
   - Run end-to-end stress tests across edge cases: reels without speech, reels without faces, extreme background audio, and corrupted downloads.

## Acceptance Criteria
- [ ] Full pipeline completes unattended on a diverse test set with zero memory exhaustion errors.
- [ ] System degrades gracefully to fallback providers upon API timeouts or rate limits.