# Phase 0.1: Foundation

## Objective
Introduce the provider architecture and registry pattern without altering existing v1 behaviour. Migrate existing AssemblyAI transcription to be the first registered provider.

## Scope of Work
1. **Core Abstractions (`app/capabilities/base.py`)**:
   - Define `Provider(ABC)`.
   - Define `health() -> Health` (checks if binary/package is installed, API key exists, RAM sufficiency).
   - Define `estimate(media_info) -> Estimate` (cost in USD, execution time, peak RAM).
   - Define `run(job) -> ProviderResult` returning raw payload and normalized `List[Event]`.
2. **Provider Registry (`app/core/registry.py`)**:
   - Mechanism to register capabilities (`speech`, `diarization`, `shots`, `ocr`, `faces`, `llm`, `embeddings`).
   - Dynamic instantiation based on `config/profiles.yaml`.
3. **Execution & Run Store (`app/core/runner.py`)**:
   - Idempotent execution: Check `data/reels/{reel_id}/` for existing cached results before running.
   - Cache key formulation: `{reel_id}_{capability}_{provider_name}_{version}`.
4. **AssemblyAI Migration**:
   - Move AssemblyAI logic into `app/capabilities/speech/providers/assemblyai.py` implementing `Provider`.

## Acceptance Criteria
- [ ] Current transcription CLI runs entirely through the registry.
- [ ] Results are saved to `data/reels/{reel_id}/` under provider-tagged manifest files.
- [ ] No regression in baseline v1 output.