# Phase 0.4: Benchmark and Arena

## Objective
Establish quantitative evaluation: replace subjective assessments with empirical evidence across accuracy, latency, cost, and RAM.

## Scope of Work
1. **Gold Set Directory (`data/gold/`)**:
   - Ingest 10 representative reels (varied: Hindi/Hinglish, fast speech, heavy music, multi-speaker) with human-verified ground truth.
2. **Metrics Computation (`app/evaluation/metrics.py`)**:
   - Word Error Rate (WER) for ASR.
   - Diarization Error Rate (DER) for speakers.
   - Shot Boundary Cut F1-score.
   - Resource metrics: Wall clock execution time, API cost ($), peak RAM (GB).
3. **Comparison Runner (`benchmark.py compare`)**:
   - Run multiple providers across the gold set without merging outputs.
4. **Leaderboard & Arena CLI (`benchmark.py leaderboard`)**:
   - Generate summary markdown tables ranking providers per capability.
   - Pairwise blind comparison mode with Elo rating updates.

## Acceptance Criteria
- [ ] CLI command `python benchmark.py leaderboard --capability speech` prints a markdown table ranking speech providers by WER, Cost, and RAM.