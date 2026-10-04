# Creator DNA Engine — Build Progress Tracker

**Current Active Phase:** `Phase 0.1: Foundation`  
**Architecture Version:** v2 (Multi-Provider, Consensus, Benchmark Arena)  
**Target Platform:** Python 3.11+, PyTorch/MLX, FFmpeg

---

## Phase Lifecycle Summary

| Phase | Title | Status | Goal |
|---|---|---|---|
| **v1.0 Baseline** | Legacy Single-Tool Engine | **DONE** | Ingestion, normalization, models, AssemblyAI transcription. |
| **Phase 0.1** | Foundation & Provider Model | **IN PROGRESS** | Typed provider base class, registry, run-store, wrap AssemblyAI. |
| **Phase 0.2** | Multi-Provider Speech | **PENDING** | Local mlx-whisper, fallback chain, preflight v1, budget guard. |
| **Phase 0.3** | Visual & Speaker Lanes | **PENDING** | PySceneDetect, RapidOCR, MediaPipe, pyannote, consensus fusion. |
| **Phase 0.4** | Benchmark & Arena | **PENDING** | 10-reel gold set, WER/DER/F1 metrics, leaderboards, blind arena. |
| **Phase 0.5** | Profiling & Persona | **PENDING** | Canonical reel model, persona aggregator, SQLite vector store. |
| **Phase 0.6** | Synthesis Engine | **PENDING** | Beat planner, screenplay writer, LLM critic loop. |
| **Phase 1.0** | Hardening & RAM Governor | **PENDING** | Dynamic routing rules, RAM queue, edge-case hardening. |

---

## Phase 0.1: Foundation Checklist (CURRENT)
- [ ] Base `Provider` abstract class with `health()`, `estimate()`, and `run()` methods.
- [ ] Typed `Requirements`, `Health`, and `Estimate` schemas.
- [ ] Central `Registry` singleton for registering and resolving capability providers.
- [ ] YAML configuration parsers (`config/providers.yaml`, `config/profiles.yaml`, `config/routing_rules.yaml`).
- [ ] Versioned Run-Store and Caching Runner (`data/reels/{reel_id}/...`).
- [ ] Migrate existing AssemblyAI transcription into `capabilities/speech/providers/assemblyai.py`.
- [ ] Verify that running `analyze_reel.py` runs AssemblyAI through the registry without breaking.

---

## Architectural Log & Decisions
- *2026-10-04*: Initialized v2 roadmap files and Cline context system.
- *2026-10-04*: Selected YAML over JSON for configuration layer to allow human-readable overriding and comments.