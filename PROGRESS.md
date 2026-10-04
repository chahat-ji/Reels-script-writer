# System Architecture & Technical Progress Report: `script-writer`

This document details the architecture, design contracts, class hierarchies, and execution workflows implemented to date. It is structured to provide full architectural context for AI reasoning, downstream module implementation, and pipeline extension.

---

## 1. System Overview & Core Objectives

The `script-writer` system processes short-form video content (Instagram Reels, local MP4 files) into standardized, multimodal timelines (`timeline.json`). It solves several domain-specific challenges:

* **Audio Standardization & Stem Isolation**: Separates vocal tracks from background music and sound effects (SFX) using deep neural stem separation (`demucs`) and spectral noise reduction (`noisereduce`).
* **Multi-Provider Speech Architecture**: Implements a unified interface for cloud-based speech recognition (AssemblyAI) and local Apple Silicon inference (`mlx-whisper`), complete with disk caching and automated failover.
* **Dialect Handling (Hinglish/Devanagari)**: Normalizes Devanagari script to colloquial Roman text using rule-based morphological normalization and Hindi schwa deletion.
* **Preflight Profiling & Dynamic Routing**: Inspects audio attributes prior to heavy model execution to configure cost- and profile-constrained execution plans.

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
│           ├── audio.wav                   # Extracted 16 kHz mono WAV (full mix)
│           ├── vocals.wav                  # Demucs-isolated speech track
│           ├── metadata.json               # Platform/source metadata
│           ├── media_specs.json            # ffprobe container & codec parameters
│           ├── condition_report.json       # Preflight analysis output
│           ├── plan.json                   # Router execution blueprint
│           ├── manifest_speech_<prov>_<ver>.json  # Provider execution result
│           └── timeline.json               # Integrated multimodal event sequence
├── app/
│   ├── capabilities/
│   │   ├── base.py                         # Abstract Provider contracts & CanonicalEvent schemas
│   │   ├── speech/
│   │   │   ├── __init__.py                 # Capability registration hook
│   │   │   └── providers/
│   │   │       ├── assemblyai.py           # AssemblyAI cloud implementation
│   │   │       └── mlx_whisper.py          # MLX Whisper local Apple Silicon implementation
│   │   └── shots/
│   │       ├── __init__.py                 # Shot detection registration hook
│   │       └── providers/
│   │           └── pyscenedetect.py        # PySceneDetect boundary detection implementation
│   ├── core/
│   │   ├── config.py                       # Configuration & environment variable loader
│   │   ├── registry.py                     # Provider service locator / registry
│   │   ├── preflight.py                    # Audio metrics analysis & language identification
│   │   ├── router.py                       # Plan creation & budget checks
│   │   └── runner.py                       # TaskRunner: caching & fallback chain execution
│   ├── fusion/
│   │   └── timeline_aligner.py             # Event fusion & timeline aggregation
│   ├── ingestion/
│   │   ├── coordinator.py                  # Ingestion orchestrator
│   │   └── instagram.py                    # yt-dlp download wrapper
│   ├── media/
│   │   ├── normalizer.py                   # ffprobe inspection & ffmpeg audio conversion
│   │   ├── separator.py                    # Demucs stem separation & spectral gating
│   │   └── text_normalizer.py              # Devanagari-to-Roman transliteration & schwa deletion
│   └── models/
│       ├── media.py                        # Pydantic models for media container specs
│       └── state.py                        # Pydantic models for preflight and execution state
├── compare_speech.py                       # Side-by-side provider verification script
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

* **`CanonicalEvent(BaseModel)`**: Normalized event schema for all pipeline outputs.
* Fields:
* `track: str`: Domain track identifier (`"speech"`, `"shot"`, `"diarization"`).
* `start_ms: int`: Event start time in milliseconds.
* `end_ms: int`: Event end time in milliseconds.
* `type: str`: Event subclass (`"word"`, `"utterance"`, `"scene_cut"`).
* `payload: Dict[str, Any]`: Payload data (e.g., `{"text": "dekh", "raw": "देख"}`).
* `confidence: float`: Provider confidence score (`0.0` to `1.0`).
* `provider: str`: Provider name that emitted the event.
* `provider_version: str`: Semantic version of the provider.




* **`ProviderResult(BaseModel)`**: Container persisted to `manifest_<capability>_<provider>_v<version>.json`.
* Fields: `capability: str`, `provider_name: str`, `provider_version: str`, `events: List[CanonicalEvent]`, `raw_payload: Dict[str, Any]`, `metadata: Dict[str, Any]`.



---

## 4. Class & Method Catalog

### 4.1 Ingestion & Media Processing

#### `app.ingestion.instagram`

* **`download_instagram_reel(url: str, output_root: str = "data/reels") -> Tuple[str, Path, dict]`**
* Uses `yt-dlp` to download media and extract metadata without re-downloading existing content.
* Returns `(reel_id, video_path, metadata_dict)`.



#### `app.media.normalizer`

* **`probe_media(file_path: Path) -> dict`**
* Invokes `ffprobe` as a subprocess with `-show_format` and `-show_streams` in JSON mode.


* **`extract_media_specs(probe_data: dict) -> Tuple[Optional[VideoSpecs], AudioSpecs]`**
* Parses raw `ffprobe` output into typed `VideoSpecs` and `AudioSpecs` models.


* **`normalize_audio(video_path: Path, output_audio_path: Path) -> AudioSpecs`**
* Executes `ffmpeg` to extract a 16-bit, 16 kHz mono PCM WAV file (`audio.wav`).



#### `app.media.separator`

* **`clean_residual_noise(vocal_wav_path: Path, output_path: Path) -> Path`**
* Applies non-stationary spectral gating using `noisereduce` to suppress transient SFX and residual noise.


* **`isolate_vocals(audio_path: Path, output_dir: Path = None, shifts: int = 2) -> Path`**
* Runs Demucs (`htdemucs`) using `--two-stems=vocals` and `--shifts=<shifts>`.
* Post-processes output to 16 kHz mono WAV via `ffmpeg`, applies `clean_residual_noise`, and outputs `vocals.wav`.



#### `app.ingestion.coordinator`

* **`ingest_media(source: str, data_root: str = "data", separate_stems: bool = True) -> IngestedMedia`**
* Orchestrates the entire input pipeline: media acquisition $\to$ container probing $\to$ audio extraction $\to$ stem isolation $\to$ metadata serialization.
* Sets `audio_path` to `vocals.wav` when stem separation is enabled, falling back to `audio.wav` otherwise.



---

### 4.2 Text & Script Normalization

#### `app.media.text_normalizer`

* **`contains_devanagari(text: str) -> bool`**
* Regex validation against the Unicode range `[\u0900-\u097F]`.


* **`devanagari_to_roman(text: str) -> str`**
* Normalizes Devanagari input via `indicnlp.normalize.DevanagariNormalizer`.
* Transliterates to Latin characters via `indic_transliteration.sanscript`.
* Applies automated Hindi schwa deletion (`[consonant]a\b` $\to$ `[consonant]`) to prevent Sanskrit-style trailing vowels (e.g., converting `dekha` to `dekh`).
* Normalizes nasals (`mem` $\to$ `me`, `haim` $\to$ `hain`, `hu.n` $\to$ `hoon`).



---

### 4.3 Core Execution Engine & Architecture

#### `app.core.config.ConfigManager`

* **`get_api_key(key_name: str) -> Optional[str]`**: Resolves secrets from environment variables or `.env`.
* **`get_profile(profile_name: str) -> dict`**: Reads configuration profiles and budget thresholds from `config/profiles.yaml`.

#### `app.core.registry.CapabilityRegistry`

* Implements a central service locator for capability providers:
* **`register(capability: str, name: str, provider_cls: Type[Provider]) -> None`**
* **`get(capability: str, name: str) -> Optional[Type[Provider]]`**
* **`list_providers(capability: Optional[str] = None) -> Dict[str, List[str]]`**



#### `app.core.preflight`

* **`detect_spoken_language(audio_path: Path) -> str`**
* Reads an initial 15-second slice of audio using `ffmpeg` and infers the spoken language via `mlx_whisper` to output an ISO 639-1 code (`"hi"`, `"en"`).


* **`analyze_audio_condition(audio_path: Path, reel_id: str) -> ConditionReport`**
* Runs `ffmpeg volumedetect` and `silencedetect` filters to calculate dynamic range, mean volume, and silence ratios.
* Adds diagnostic flags (`LANG_HI`, `HEAVY_BACKGROUND_MUSIC`, `HIGH_SILENCE_RATIO`).



#### `app.core.router`

* **`create_execution_plan(condition_report: ConditionReport, profile_name: str = "default", data_root: str = "data") -> ExecutionPlan`**
* Evaluates preflight condition flags and estimates execution costs against `limits.max_usd_per_reel`.
* Configures fallback provider chains (e.g., falling back from `assemblyai` to local `mlx_whisper` if budget is exceeded).
* Writes `condition_report.json` and `plan.json` to the reel directory.



#### `app.core.runner.TaskRunner`

* **`execute(reel_id: str, provider: Provider, job: Dict[str, Any]) -> ProviderResult`**
* Checks for an existing `manifest_<capability>_<provider>_v<version>.json` on disk to return cached results when available.
* Runs `provider.health()` checks before execution.
* Persists execution results to disk upon completion.


* **`execute_chain(reel_id: str, capability: str, provider_names: List[str], job: Dict[str, Any]) -> ProviderResult`**
* Iterates through an ordered provider list, executing each sequentially and falling back to the next candidate if an error occurs.



---

### 4.4 Capability Providers

#### `app.capabilities.base.Provider (ABC)`

All providers implement this abstract interface:

* **`health() -> Health`**: Validates dependencies, drivers, and API keys.
* **`estimate(media_info: Dict[str, Any]) -> Estimate`**: Projects cost in USD, runtime duration, and RAM consumption.
* **`run(job: Dict[str, Any]) -> ProviderResult`**: Executes inference and returns normalized `CanonicalEvent` models.

#### `app.capabilities.speech.providers.assemblyai.AssemblyAISpeechProvider`

* **Capability**: `"speech"` | **Tier**: `"paid"` | **Version**: `"1.2.0"`
* Uploads target audio to AssemblyAI, applies language settings, and parses responses into `utterance` and `word` canonical events.
* Passes all output text through `devanagari_to_roman` to produce standardized Roman script.

#### `app.capabilities.speech.providers.mlx_whisper.MLXWhisperProvider`

* **Capability**: `"speech"` | **Tier**: `"local"` | **Version**: `"1.2.0"`
* Uses `mlx-community/whisper-large-v3-turbo` for GPU-accelerated local transcription on Apple Silicon.
* Sets `task="transcribe"`, `condition_on_previous_text=False`, and `compression_ratio_threshold=2.2` to mitigate repetition loops during audio transitions.
* Converts token payloads to Roman Hinglish via `devanagari_to_roman`.

#### `app.capabilities.shots.providers.pyscenedetect.PySceneDetectProvider`

* **Capability**: `"shots"` | **Tier**: `"local"` | **Version**: `"1.0.0"`
* Uses `scenedetect.ContentDetector(threshold=27.0)` to detect visual shot boundaries and cuts.
* Emits `"scene_cut"` events with start and end timestamps in milliseconds, scene indices, and durations.

---

### 4.5 Fusion & Timeline Integration

#### `app.fusion.timeline_aligner.TimelineAligner`

* **`fuse(reel_id: str, results: List[ProviderResult], data_root: str = "data") -> Dict[str, Any]`**
* Merges disparate `CanonicalEvent` streams across different tracks (`"speech"`, `"shot"`).
* Sorts all events chronologically by `(start_ms, end_ms)`.
* Computes video-level pacing metrics, including total shot counts, total spoken words, and **Average Shot Duration (ASD)**.
* Saves the consolidated output to `data/reels/<reel_id>/timeline.json`.



---

## 5. End-to-End Pipeline Execution Flow

```text
[Input URL / Local Path]
           │
           ▼
1. INGESTION (app.ingestion.coordinator)
   ├── Fetch Video via yt-dlp (instagram.py)
   ├── Extract Container Specs via ffprobe (normalizer.py)
   ├── Standardize Audio mix -> audio.wav via ffmpeg (normalizer.py)
   └── Separate Vocals -> vocals.wav via Demucs & Noisereduce (separator.py)
           │
           ▼
2. PREFLIGHT & ROUTING (app.core.preflight & app.core.router)
   ├── Compute volume, dynamic range, and silence ratios
   ├── Run 15-second acoustic language identification
   ├── Check budget constraints from profiles.yaml
   └── Serialize condition_report.json and plan.json
           │
           ▼
3. EXECUTION CHAIN (app.core.runner)
   ├── Read task plan from plan.json
   ├── Check disk cache for existing manifest files
   ├── Execute primary provider (fallback to secondary on error)
   │     ├── Paid Cloud: AssemblyAISpeechProvider
   │     └── Local Metal: MLXWhisperProvider
   └── Transliterate text to Roman Hinglish via text_normalizer.py
           │
           ▼
4. MULTIMODAL FUSION (app.fusion.timeline_aligner)
   ├── Run PySceneDetectProvider on video.mp4
   ├── Collate speech tokens and scene cuts
   ├── Sort events chronologically into a unified index
   └── Calculate Average Shot Duration (ASD) -> timeline.json

```

---

## 6. Manifest & Timeline Output Structure

### Provider Manifest Output: `manifest_speech_mlx_whisper_v1.2.0.json`

```json
{
  "capability": "speech",
  "provider_name": "mlx_whisper",
  "provider_version": "1.2.0",
  "events": [
    {
      "track": "speech",
      "start_ms": 1219,
      "end_ms": 1960,
      "type": "word",
      "payload": {
        "text": "oye",
        "raw": "ओए"
      },
      "confidence": 0.95,
      "provider": "mlx_whisper",
      "provider_version": "1.2.0"
    }
  ],
  "raw_payload": {
    "text": "oye dekh tere dabbe me khana kha gaya",
    "language": "hi",
    "segment_count": 12
  },
  "metadata": {
    "audio_path": "data/reels/DeEKAEKhx_Z/vocals.wav",
    "model": "mlx-community/whisper-large-v3-turbo"
  }
}

```

### Fused Timeline Output: `timeline.json`

```json
{
  "reel_id": "DeEKAEKhx_Z",
  "metrics": {
    "total_shots": 14,
    "total_words": 178,
    "avg_shot_duration_sec": 2.14
  },
  "events": [
    {
      "track": "shot",
      "start_ms": 0,
      "end_ms": 1850,
      "type": "scene_cut",
      "payload": {
        "scene_index": 0,
        "duration_ms": 1850,
        "duration_sec": 1.85
      },
      "confidence": 1.0,
      "provider": "pyscenedetect",
      "provider_version": "1.0.0"
    },
    {
      "track": "speech",
      "start_ms": 1219,
      "end_ms": 1960,
      "type": "word",
      "payload": {
        "text": "oye"
      },
      "confidence": 0.95,
      "provider": "mlx_whisper",
      "provider_version": "1.2.0"
    }
  ]
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
   - **AssemblyAI Cloud**: Native script output (Devanagari for Hindi, Latin for English) with word-level timestamps.
   - **MLX Whisper Local**: Upgraded to `mlx-community/whisper-large-v3-mlx` with multi-temperature fallback (`(0.0, 0.2, 0.4, 0.6, 0.8)`), silence hallucination thresholds, and anti-repetition deduplication (completely eliminating token loops).
6. **Native Script Preservation**: Removed brittle rule-based ITRANS and regex schwa deletion from Phase 2, preserving authentic transcripts directly.

### Next Implementation Steps (Phase 0.3: Visual & Speaker Lanes)

1. **Shot Boundary Detection**: PySceneDetect boundary detection integration (`app/capabilities/shots/providers/pyscenedetect.py`).
2. **Speaker Diarization Track**: Add `diarization` capability using `pyannote-audio` to segment and cluster speaker voices.
3. **On-Screen OCR**: Add local OCR (`apple_vision` / `rapidocr`) to extract on-screen caption overlays.
4. **Active Speaker Resolver**: Correlate face bounding boxes & mouth aspect ratio (MAR) with audio diarization clusters.