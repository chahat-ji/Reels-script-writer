# Script Writer Pipeline: Architecture Roadmap & Strategic Decisions

This document summarizes the strategic architectural decisions for the **Script Writer** pipeline, outlining components to implement, legacy components to deprecate/discard, and experimental tracks pending further exploration.

---

## 1. Executive Summary & Core Pivot

Our empirical benchmarks across rapid Hindi, Hinglish, and comedic skits revealed that:
1. **Google Gemini Flash Audio Transcription** achieved **94.0% – 98.8% recall** and inferred real speaker roles (e.g., *Jija* vs *Saala*, *Mother* vs *Boy*) with zero prompt fine-tuning.
2. Traditional ASR engines (**Local MLX Whisper** and **Cloud AssemblyAI**) struggled with rapid Hindi conversational speech (failing with 13%–51% recall on fast conversational skits).
3. Gemini's cost is **$0.0003 – $0.0013 per reel** (~25x cheaper than AssemblyAI and with 3x higher recall).

**Conclusion**: We are pivoting the core speech and diarization ingestion to **Gemini Multimodal Speech** and designing a **Hybrid RAG + Context Caching** generation system to reproduce high-retention creator scripts at minimal cost.

---

## 2. Components to Implement (The New Pipeline)

```
[Incoming Reel] ──> [Audio Extraction] ──> [Gemini Multimodal Ingestion]
                                                    │
                                                    ▼
                                    [manifest_speech_gemini_v1.0.0.json]
                                                    │
                     ┌──────────────────────────────┴──────────────────────────────┐
                     ▼                                                             ▼
         [Local Granular Exemplar Store]                               [Gemini Cloud Context Cache]
         - Full Raw Transcripts & Beats                                - Creator Persona & Archetypes
         - Exact Hook Bank (0–3s lines)                                - Colloquial Dictionary / Slang
         - Signature Vocabulary Bank                                   - Mathematical Pacing Specs
                     │                                                             │
                     └──────────────────────────────┬──────────────────────────────┘
                                                    ▼
                                    [Hybrid Few-Shot RAG Generator]
                                                    │
                                                    ▼
                                    [Authentic Creator Reel Script]
```

### 2.1 Core Speech Pipeline (`app/pipelines/speech_gemini.py`)
- Official pipeline component implementing the standard manifest interface.
- Transcribes speech and diarizes conversational turns directly via `google-genai` SDK.
- Emits versioned manifests: `manifest_speech_gemini_v1.0.0.json`.
- Integrates directly into `batch_process.py`.

### 2.2 Granular Creator Exemplar Store (`app/rag/`)
- Stores 100% of the raw, uncompressed transcripts, turns, and character actions on disk (`data/creators/<creator_id>/exemplars/`).
- Prevents context and texture loss by preserving original phrasing, punctuation, and comedic beats.
- Indexes reels by topic/theme for semantic similarity retrieval.

### 2.3 Gemini Context Caching (`app/services/cache_manager.py`)
- Leverages Gemini's native `CachedContent` API (`client.caches.create`) for static creator profiles.
- Pre-warms Creator Archetypes, Slang Banks, and Pacing Specs in Gemini's RAM.
- Reduces token costs by **75%** ($0.025 / 1M cached tokens) and delivers sub-second prompt execution.

### 2.4 Hybrid Few-Shot RAG Generator (`app/generators/script_writer.py`)
- When generating a new script for a target topic, dynamically retrieves the **2 most relevant full reel exemplars** via local RAG.
- Combines the 2 exemplars with the cloud-cached creator profile.
- Prompts Gemini Flash to generate an authentic screenplay matching the creator's exact timing, humor, and dialogue cadence.

---

## 3. Components to Discard / Deprecate

| Component | Status | Rationale for Removal |
| :--- | :---: | :--- |
| **Mandatory AssemblyAI Cloud Transcription** | **Discarded from Critical Path** | At ~$0.015/min, AssemblyAI is 25x more expensive than Gemini Flash while missing 48% of words on rapid Hindi skits (`DdrIIFTCWdx`). Retained only as an optional diagnostic tool. |
| **Mandatory Local MLX Whisper Pipeline** | **Discarded from Critical Path** | Whisper Large-v3 crashed into repetition loops on 3-minute fast conversational reels (capturing only 13% recall). Keeping it as a mandatory fallback adds unnecessary latency. |
| **Heavy Unconditional Video Processing (OCR / Full-Frame Vision)** | **Discarded** | Running continuous video frame ingestion or local OCR across every second adds 10x–20x compute and API cost. Audio alone extracts dialogue and character roles accurately. |
| **Naive Text Summarization / Aggressive Distillation** | **Discarded** | Compressing 20 reels into generic summary paragraphs creates bland, robotic scripts ("AI slop") by stripping out the creator's unique phrasing, slang, and micro-jokes. |

---

## 4. Experimental Tracks (Pending Discussion)

### 4.1 Sentiment & Emotional Trajectory Analysis
* **Concept**: Analyze the emotional velocity and pitch dynamics across dialogue turns (e.g., escalating frustration, mock innocence, deadpan sarcasm).
* **Objective**: Short-form comedy relies heavily on emotional contrast (e.g., Character A starts calm $\rightarrow$ Character B acts irrational $\rightarrow$ Explosive confrontation at $t = 18\text{s}$).
* **Questions for Discussion**:
  1. Should sentiment be extracted purely from dialogue text, or should we incorporate audio pitch/prosody cues?
  2. How do we formalize sarcasm vs genuine anger in Hinglish skits where literal text says one thing but delivery means the opposite?
  3. What format should the sentiment manifest take: per-turn emotional tags (`[sarcastic]`, `[accusatory]`) or a numerical emotional curve?

### 4.2 Creator DNA & Style Profiling Engine
* **Concept**: A formalized statistical and qualitative schema capturing a creator's unique fingerprint across a batch of 10–50 analyzed reels.
* **Key Dimensions Under Consideration**:
  1. **Hook Archetypes**: Categorizing opening patterns (e.g., "In Media Res Accusation", "Contrarian Statement", "Visual Gag Shock").
  2. **Mathematical Pacing Blueprint**:
     - Average turn duration (seconds per speaker).
     - Words-per-turn density (rapid dialogue vs narrative monologue).
     - Cut cadence and punchline frequency (jokes per 15 seconds).
  3. **Character Archetype Matrix**: Defining persistent relational dynamics (e.g., Complaining In-law vs Obliging Host; Strict Indian Mom vs Cunning Son).
  4. **Signature Vocabulary / Slang Lexicon**: Explicit banks of colloquial keywords, idioms, and catchphrases that distinguish the creator from generic language models.
* **Questions for Discussion**:
  - Should the Creator DNA profile be updated incrementally with each new processed reel, or generated as a batch run after $N$ reels?
  - How do we validate that a newly generated script adheres to the Creator DNA profile before presenting it to human writers?
