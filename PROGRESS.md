# System Architecture & Technical Progress Report: `script-writer`

This document details the architecture, design contracts, class hierarchies, and execution workflows implemented to date. It is structured to provide full architectural context for AI reasoning, downstream module implementation, and pipeline extension.

---

## 1. System Overview & Core Objectives

The `script-writer` system processes short-form video content (Instagram Reels, local MP4 files) into standardized, multimodal timelines (`timeline.json`). It solves several domain-specific challenges:

* **Audio Standardization & Ingestion**: Extracts pristine 16 kHz mono 16-bit PCM WAV tracks (`audio.wav`) directly from input media using `ffmpeg`/`ffprobe`. Destructive spectral noise reduction (`noisereduce`) has been removed, and heavy stem separation (`demucs`) is bypassed by default to avoid vocal phase distortion and speed up ingestion by 30+ seconds per reel.
* **Multi-Provider Speech Architecture (v1.3.0)**: Implements a unified interface for cloud-based speech recognition (AssemblyAI) and local Apple Silicon inference (`mlx-whisper`), complete with disk caching, automated failover, and speaker diarization.
* **Native Script Fidelity**: Preserves authentic native script (Devanagari for Hindi, Latin for English) with exact word- and utterance-level timestamps. Brittle rule-based ITRANS and regex schwa deletion have been eliminated from the speech pipeline to preserve linguistic integrity.
* **Local Whisper Anti-Loop Optimization**: Uses `mlx-community/whisper-large-v3-mlx` with multi-temperature fallback (`0.0` to `0.8`), silence hallucination filtering, and consecutive token deduplication to prevent repetition loops.
* **Preflight Profiling & Dynamic Routing**: Inspects duration, volume health (clipping/low-level detection), and silence ratios prior to model execution to configure cost- and profile-constrained execution plans.

---

## 2. Directory Layout & File Organization

```text
script-writer/
├── config/
│   └── profiles.yaml                       # Runtime execution profiles and budget ceilings
├── data/
│   └── reels/
│       └── <reel_id>/                      # Run-store per reel
│           ├── video.mp4                   # Downloaded/copied raw video
│           ├── audio.wav                   # Extracted 16 kHz mono WAV (pristine mix)
│           ├── metadata.json               # Platform/source metadata
│           ├── media_specs.json            # ffprobe container & codec parameters
│           ├── condition_report.json       # Preflight audio health analysis output
│           ├── plan.json                   # Router execution blueprint
│           ├── manifest_speech_<prov>_<ver>.json  # Provider execution result
│           └── timeline.json               # Integrated multimodal event sequence
├── app/
│   ├── capabilities/
│   │   ├── base.py                         # Abstract Provider contracts & CanonicalEvent schemas
│   │   ├── speech/
│   │   │   ├── __init__.py                 # Capability registration hook
│   │   │   └── providers/
│   │   │       ├── assemblyai.py           # AssemblyAI cloud implementation (v1.3.0, diarization)
│   │   │       └── mlx_whisper.py          # MLX Whisper local Large-v3 implementation (v1.3.0)
│   │   └── shots/
│   │       ├── __init__.py                 # Shot detection registration hook
│   │       └── providers/
│   │           └── pyscenedetect.py        # PySceneDetect boundary detection implementation
│   ├── core/
│   │   ├── config.py                       # Configuration & environment variable loader
│   │   ├── registry.py                     # Provider service locator / registry
│   │   ├── preflight.py                    # Audio metrics analysis & volume health probe
│   │   ├── router.py                       # Plan creation & budget checks
│   │   └── runner.py                       # TaskRunner: caching & fallback chain execution
│   ├── fusion/
│   │   └── timeline_aligner.py             # Event fusion & timeline aggregation
│   ├── ingestion/
│   │   ├── coordinator.py                  # Ingestion orchestrator (standard audio.wav)
│   │   └── instagram.py                    # yt-dlp download wrapper
│   ├── media/
│   │   ├── normalizer.py                   # ffprobe inspection & ffmpeg audio extraction
│   │   ├── separator.py                    # Demucs stem isolation (optional utility)
│   │   └── text_normalizer.py              # Text utilities
│   └── models/
│       ├── media.py                        # Pydantic models for media container specs
│       └── state.py                        # Pydantic models for preflight and execution state
├── compare_speech.py                       # Side-by-side provider verification script
├── test_speech_pipeline.py                 # End-to-end pipeline verification CLI
├── analyze_reel.py                         # Single-provider analysis CLI
├── requirements.txt                        # Python dependencies
└── .env                                    # API credentials
```

---

## 3. Data Models & Schemas

### `app.models.media`

* **`VideoSpecs(BaseModel)`**: Container for video stream metadata.
  * Fields: `width: int`, `height: int`, `fps: float`, `duration_seconds: float`, `codec: str`.
* **`AudioSpecs(BaseModel)`**: Container for audio stream metadata.
  * Fields: `sample_rate: int`, `channels: int`, `duration_seconds: float`, `codec: str`.
* **`IngestedMedia(BaseModel)`**: Aggregate returned by `ingest_media`.
  * Fields: `reel_id: str`, `source_url: Optional[str]`, `video_path: Path`, `audio_path: Path`, `metadata_path: Path`, `audio_specs: AudioSpecs`, `video_specs: Optional[VideoSpecs]`, `raw_metadata: Dict[str, Any]`.

### `app.models.state`

* **`AudioCondition(BaseModel)`**: Low-level audio characteristics from preflight checks.
  * Fields: `has_heavy_music: bool`, `music_energy_ratio: float`, `silence_ratio: float`, `average_db: float`, `needs_stem_separation: bool`.
* **`ConditionReport(BaseModel)`**: Overall preflight health and attribute assessment.
  * Fields: `reel_id: str`, `audio_condition: AudioCondition`, `duration_seconds: float`, `flags: List[str]`.
* **`TaskPlan(BaseModel)`**: Execution instructions for an individual capability.
  * Fields: `capability: str`, `provider_chain: List[str]`, `estimated_cost_usd: float`, `estimated_seconds: float`.
* **`ExecutionPlan(BaseModel)`**: Top-level execution plan persisted to `plan.json`.
  * Fields: `reel_id: str`, `profile: str`, `preflight: ConditionReport`, `plans: Dict[str, TaskPlan]`.

### `app.capabilities.base`

* **`CanonicalEvent(BaseModel)`**: Normalized event schema across all pipeline tracks.
  * Fields:
    * `track: str`: Domain track identifier (`"speech"`, `"shot"`, `"diarization"`).
    * `start_ms: int`: Event start time in milliseconds.
    * `end_ms: int`: Event end time in milliseconds.
    * `type: str`: Event subclass (`"word"`, `"utterance"`, `"scene_cut"`).
    * `payload: Dict[str, Any]`: Payload data (e.g., `{"text": "खाना", "raw": "खाना", "speaker": "A"}`).
    * `confidence: float`: Provider confidence score (`0.0` to `1.0`).
    * `provider: str`: Provider name that emitted the event.
    * `provider_version: str`: Semantic version of the provider (`"1.3.0"`).

* **`ProviderResult(BaseModel)`**: Container persisted to `manifest_<capability>_<provider>_v<version>.json`.
  * Fields: `capability: str`, `provider_name: str`, `provider_version: str`, `events: List[CanonicalEvent]`, `raw_payload: Dict[str, Any]`, `metadata: Dict[str, Any]`.

---

## 4. Class & Method Catalog

### 4.1 Ingestion & Media Processing

#### `app.ingestion.instagram`
* **`download_instagram_reel(url: str, output_root: str = "data/reels") -> Tuple[str, Path, dict]`**: Uses `yt-dlp` to download media and metadata without re-downloading existing files.

#### `app.media.normalizer`
* **`probe_media(file_path: Path) -> dict`**: Invokes `ffprobe` in JSON mode to inspect streams and format container tags.
* **`extract_media_specs(probe_data: dict) -> Tuple[Optional[VideoSpecs], AudioSpecs]`**: Parses ffprobe JSON into typed models.
* **`normalize_audio(video_path: Path, output_audio_path: Path) -> AudioSpecs`**: Converts video audio track into standard 16-bit, 16 kHz mono PCM WAV (`audio.wav`).

#### `app.ingestion.coordinator`
* **`ingest_media(source: str, data_root: str = "data", separate_stems: bool = False) -> IngestedMedia`**: Orchestrates media acquisition $\to$ container probing $\to$ 16 kHz audio extraction $\to$ metadata serialization. Sets `audio_path` to `audio.wav` by default for pristine speech transcription.

#### `app.media.separator`
* **`isolate_vocals(audio_path: Path, output_dir: Path = None, shifts: int = 1) -> Path`**: Utility to run Demucs (`htdemucs`) and downsample directly to 16 kHz mono WAV without destructive spectral gating.

---

### 4.2 Core Engine & Orchestration

#### `app.core.config.ConfigManager`
* Resolves API keys from environment/`.env` and reads profiles/budget limits from `config/profiles.yaml`.

#### `app.core.registry.CapabilityRegistry`
* Central service locator: registers and dynamic resolves providers (`speech`, `shots`, `diarization`, etc.).

#### `app.core.preflight`
* **`analyze_audio_condition(audio_path: Path, reel_id: str) -> ConditionReport`**: Measures duration, dynamic range, mean/max volume dBFS, and silence ratios via `ffmpeg volumedetect` and `silencedetect`. Flags `EXTREMELY_LOW_VOLUME`, `AUDIO_PEAK_CLIPPED`, and `HIGH_SILENCE_RATIO`.

#### `app.core.router`
* **`create_execution_plan(condition_report: ConditionReport, profile_name: str = "default", data_root: str = "data") -> ExecutionPlan`**: Evaluates conditions and profiles against budget caps (`limits.max_usd_per_reel`) and constructs fallback chains.

#### `app.core.runner.TaskRunner`
* **`execute(reel_id: str, provider: Provider, job: Dict[str, Any]) -> ProviderResult`**: Enforces idempotency via disk caching (`manifest_<cap>_<prov>_v<ver>.json`), verifies provider health, executes inference, and serializes results.
* **`execute_chain(reel_id: str, capability: str, provider_names: List[str], job: Dict[str, Any]) -> ProviderResult`**: Automatically executes candidate providers in order, falling back to the next on failure.

---

### 4.3 Capability Providers (v1.3.0)

#### `app.capabilities.speech.providers.assemblyai.AssemblyAISpeechProvider`
* **Capability**: `"speech"` | **Tier**: `"paid"` | **Version**: `"1.3.0"`
* Uploads clean `audio.wav` to AssemblyAI.
* Supports **speaker diarization labels** (`speaker_labels=True`), populating `speaker` on words and utterances.
* Emits authentic native script (Devanagari for Hindi, Latin for English) with millisecond timestamps and confidence scores.

#### `app.capabilities.speech.providers.mlx_whisper.MLXWhisperProvider`
* **Capability**: `"speech"` | **Tier**: `"local"` | **Version**: `"1.3.0"`
* Uses `mlx-community/whisper-large-v3-mlx` (Full Large v3 architecture, 1.54B parameters) for Apple Silicon Metal inference.
* Multi-temperature fallback: `temperature=(0.0, 0.2, 0.4, 0.6, 0.8)` preventing token deadlocks.
* Anti-hallucination guards: `hallucination_silence_threshold=2.0`, `compression_ratio_threshold=2.2`, and consecutive token deduplication (`suppress_repetition_loops`).
* Emits authentic native script directly into `CanonicalEvent` tokens.

#### `app.capabilities.shots.providers.pyscenedetect.PySceneDetectProvider`
* **Capability**: `"shots"` | **Tier**: `"local"` | **Version**: `"1.0.0"`
* Uses `scenedetect.ContentDetector(threshold=27.0)` to detect visual shot boundaries and cuts.

---

## 5. End-to-End Pipeline Execution Flow

```text
[Input URL / Local Path]
           │
           ▼
1. INGESTION (app.ingestion.coordinator)
   ├── Fetch Video via yt-dlp (instagram.py)
   ├── Extract Container Specs via ffprobe (normalizer.py)
   └── Standardize Audio mix -> audio.wav via ffmpeg (normalizer.py)
           │
           ▼
2. PREFLIGHT & ROUTING (app.core.preflight & app.core.router)
   ├── Probe volume health (clipping, silence ratio, mean/max dBFS)
   ├── Validate budget ceilings in profiles.yaml
   └── Serialize condition_report.json and plan.json
           │
           ▼
3. EXECUTION CHAIN (app.core.runner)
   ├── Check disk cache for manifest_<cap>_<prov>_v1.3.0.json
   ├── Execute primary provider (with automatic fallback on error)
   │     ├── Paid Cloud: AssemblyAISpeechProvider (native script + diarization)
   │     └── Local Metal: MLXWhisperProvider (large-v3-mlx + anti-loop guards)
   └── Output clean native script (Devanagari / English)
           │
           ▼
4. MULTIMODAL FUSION (app.fusion.timeline_aligner)
   ├── Run PySceneDetectProvider on video.mp4
   ├── Collate speech tokens, diarization turns, and scene cuts
   ├── Sort events chronologically into unified timeline
   └── Calculate Average Shot Duration (ASD) -> timeline.json
```

---

## 6. Manifest Output Schema Example (v1.3.0)

### Native Script Manifest Output (`manifest_speech_assemblyai_v1.3.0.json`)

```json
{
  "capability": "speech",
  "provider_name": "assemblyai",
  "provider_version": "1.3.0",
  "events": [
    {
      "track": "speech",
      "start_ms": 1210,
      "end_ms": 1960,
      "type": "word",
      "payload": {
        "text": "ओए",
        "raw": "ओए",
        "speaker": "A"
      },
      "confidence": 0.98,
      "provider": "assemblyai",
      "provider_version": "1.3.0"
    },
    {
      "track": "speech",
      "start_ms": 3680,
      "end_ms": 4000,
      "type": "word",
      "payload": {
        "text": "खाना",
        "raw": "खाना",
        "speaker": "A"
      },
      "confidence": 0.99,
      "provider": "assemblyai",
      "provider_version": "1.3.0"
    }
  ],
  "raw_payload": {
    "text": "ओए देख तेरे डब्बे में खाना खा गया...",
    "raw_text": "ओए देख तेरे डब्बे में खाना खा गया...",
    "status": "TranscriptStatus.completed",
    "words_count": 179
  },
  "metadata": {
    "audio_path": "data/reels/DeEKAEKhx_Z/audio.wav",
    "language_code": "hi"
  }
}
```

---

## 7. Current Project State & Next Steps

### Completed Milestones

1. **Robust Media Ingestion**: Automatic container probing via `ffprobe`, audio normalization to standard 16 kHz mono WAV (`audio.wav`), and metadata persistence for URLs and local MP4s.
2. **Streamlined Audio Pipeline**: Removed destructive spectral gating (`noisereduce`) and bypassed Demucs stem separation by default for speech transcription, saving 30+ seconds per reel and preserving audio fidelity.
3. **Preflight Health Inspection**: Probes duration, dynamic range, volume clipping/sanity, and silence ratio before generating budget-guarded task plans.
4. **Idempotent TaskRunner**: Supports disk caching (`manifest_<cap>_<prov>_v<ver>.json`) and automatic fallback chains.
5. **Dual Speech Transcription (v1.3.0)**:
   - **AssemblyAI Cloud**: Native script output (Devanagari for Hindi, Latin for English) with word-level timestamps and speaker diarization.
   - **MLX Whisper Local**: Upgraded to `mlx-community/whisper-large-v3-mlx` with multi-temperature fallback (`(0.0, 0.2, 0.4, 0.6, 0.8)`), silence hallucination thresholds, and anti-repetition deduplication (completely eliminating token loops).
6. **Native Script Preservation**: Removed brittle rule-based ITRANS and regex schwa deletion from Phase 2, preserving authentic transcripts directly.
7. **Clean Cache Management**: Purged unused test weights (`whisper-tiny-mlx`, `whisper-large-v3-turbo`) from HuggingFace cache while retaining active models (`large-v3-mlx`, `HTDemucs`).

### Next Implementation Steps (Phase 0.3: Visual & Speaker Lanes)

1. **Shot Boundary Detection**: PySceneDetect boundary detection integration (`app/capabilities/shots/providers/pyscenedetect.py`).
2. **Speaker Diarization Track**: Add dedicated local `diarization` capability using `pyannote-audio` to segment and cluster speaker voices across any ASR backend.
3. **On-Screen OCR**: Add local OCR (`apple_vision` / `rapidocr`) to extract on-screen caption overlays.
4. **Active Speaker Resolver**: Correlate face bounding boxes & mouth aspect ratio (MAR) with audio diarization clusters.