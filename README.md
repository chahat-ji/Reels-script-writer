# Script Writer 🎬

An automated AI pipeline designed to extract dialogue, character dynamics, comedic beats, and screenplay structure from short-form video reels (Instagram / YouTube Shorts).

---

> [!NOTE]
> ### 📖 Project Journey: Why We Paused & How We Resumed
> 
> During our initial development, no AI model existed that could reliably process fast-paced Hindi and Hinglish speech. While English content worked reasonably well, rapid conversational comedy skits in Hindi broke every state-of-the-art model:
> - **Local Whisper** got stuck in repetition loops and missed up to 87% of the words.
> - **Cloud ASR (AssemblyAI)** missed nearly half the dialogue due to rapid slang, cross-talk, and background audio.
> 
> We tried creating our own pipeline with custom voice activity detection (VAD), chunking, and separate speaker diarization models to fix it, but we failed to produce good enough results to move forward. Because of these technical limitations, we had to pause the project.
> 
> **The Breakthrough:**  
> With the arrival of newer multimodal models like **Gemini 3.8** capable of taking both audio and video as input, everything changed. In our benchmarks, it produced results with **up to 98% accuracy**, handled fast-paced Hindi/Hinglish slang effortlessly, and accurately detected context and speaker roles directly from the story. With this breakthrough, we restarted development on the project.

---

## 🚀 How to Use (Simple & Terminal-First)

The pipeline is designed to be run directly from the command line, from URL ingestion all the way to visual dashboard comparison.

### 1. Setup Environment & Dependencies
Clone the repository, create a virtual environment, and install dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Set up your `.env` file (copy from `.env.example`):
```bash
cp .env.example .env
```
Add your API keys inside `.env`:
```env
ASSEMBLYAI_API_KEY=your_assemblyai_key_here
```

---

### 2. Ingest & Analyze a Reel from URL
Feed any Instagram Reel or video URL directly into the ingestion pipeline:
```bash
python analyze_reel.py "https://www.instagram.com/reel/C8xYz123456/"
```
What this does:
- Automatically downloads the video using `yt-dlp`.
- Normalizes and extracts clean 16kHz audio.
- Runs audio health preflight checks and executes initial analysis stages.

---

### 3. Check & Batch Process Reels
Use `batch_process.py` to check missing stages or process multiple reels on disk:

```bash
# Check and process missing pipeline stages across all ingested reels:
python batch_process.py --all

# Or run checking on a specific reel by ID or URL:
python batch_process.py <reel_id_or_url>
```
This automatically verifies what is missing on disk (audio extraction, scene cuts, face tracking, speech manifests) and executes only the missing phases.

---

### 4. Launch the Central Comparison Dashboard
Launch the local web dashboard to review and compare all processed reels side-by-side:
```bash
python tools/dashboard.py
```
Open **`http://localhost:8000/dashboard.html`** in your browser.

**Dashboard Features:**
- **Synchronized Video Playback**: Click any subtitle card to seek the video to that exact millisecond.
- **Auto-Centering Subtitle Feed**: Active dialogue cards smoothly scroll and center in your viewport as the video plays.
- **Side-by-Side Arena**: Compare Local MLX Whisper, Cloud AssemblyAI, Gemini, and human Gold Standard benchmarks side-by-side with Word Error Rate (WER) and Word Recall metrics.
- **Cast & Container Info**: View character directory, resolution, framerate, and duration at a glance.

---

## 🏛️ The Architecture We Planned (And Why It Failed Due to Limitations)

When we initially designed this system, we attempted a multi-step multimodal pipeline:

```
[Video URL] ──► Ingestion (yt-dlp + ffmpeg)
                    │
                    ├─► Audio Track ──► VAD ──► Speech (Whisper / AssemblyAI) ──► Dialogue
                    │                                                               │
                    └─► Video Frames ─► PySceneDetect ─► Face/MAR Tracking ───────► Match Speaker
```

Here is why each component failed when applied to fast-paced short-form reels:

### 1. Traditional Speech Recognition (ASR) Failed on Hindi / Hinglish
- **The Plan**: Use local Apple Silicon Whisper or cloud Conformer models to transcribe speech into text.
- **Why it failed**: Models were tuned on standard English or clean audio. On fast Indian comedy skits with colloquial slang (*"जुगाड़"*, *"अतरंगी"*, *"अंबानी वाली रसोई"*) and overlapping talk, they dropped 50% to 85% of words or looped repeatedly on the same sentence.

### 2. Acoustic Speaker Diarization Couldn't Separate Characters
- **The Plan**: Use acoustic voice fingerprinting (clustering audio frequencies) to distinguish Speaker A from Speaker B.
- **Why it failed**: In comedy skits, actors constantly modulate their pitch—shouting, whispering, acting sarcastic, or doing character impressions. Voice frequency clustering constantly split a single person into multiple speakers, or merged distinct characters into one.

### 3. Visual Face & Lip Motion Tracking (MAR) Failed on Fast Editing Cuts
- **The Plan**: Track faces on screen with MediaPipe and measure Mouth Aspect Ratio (MAR) to detect who is speaking during scene cuts.
- **Why it failed**: Short-form comedy uses heavy **L-cuts and J-cuts**: audio of one character speaking continues while the camera quickly cuts to the second character reacting silently. Lip detectors got confused, matching speech to the wrong face on screen. Fast motion blur and actors turning away also broke face meshes.

### Why Gemini Handled It Seamlessly
Gemini understands **conversational context and story semantics natively**. It doesn't need fragile face-tracking heuristics to guess who is talking: it recognizes that when one character addresses the other with *"जीजा जी"* while talking about tea cups, the speaker is the brother-in-law (*Saala*). It decodes speech, speaker identities, and conversational beats in a single unified step.
