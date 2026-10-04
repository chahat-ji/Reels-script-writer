# Phase 0.5: Profiling and Persona Aggregation

## Objective
Convert raw multi-modal timeline events into high-level creator profiles and aggregate 10–30 reels into a persistent creator persona.

## Scope of Work
1. **Reel Profiling (`app/analysis/`)**:
   - `hook_profiler.py`: Classify hook type (visual cut timing, question, shock claim, text card) within first 3000ms.
   - `pacing_analyzer.py`: Words-per-minute (WPM), average shot duration (ASD), silence ratio.
2. **Canonical Reel Model (`app/models/canonical.py`)**:
   - Standardized structured JSON per reel summarizing narrative structure, emotional arc, vocabulary quirks, and visual rhythm.
3. **Persona Builder (`app/synthesis/persona_builder.py`)**:
   - Aggregate statistical averages across 10–30 analyzed reels of a creator.
   - Extract recurring catchphrases, humor cadence, Hinglish code-switching frequency, and rhetorical strategies.
4. **Embedding Storage (`data/creators/{creator_id}/corpus.sqlite`)**:
   - Provider-backed vector embeddings (`e5-small`, `bge-m3`, or `openai`) storing reel beats for retrieval.

## Acceptance Criteria
- [ ] Running batch profiling yields a `persona.json` that captures hook preferences, delivery cadence, and signature tropes.