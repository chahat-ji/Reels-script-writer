# Video-to-Style Script Generation Platform

An agentic AI pipeline that transforms short-form comedy reference videos into reusable text memories, synthesizes creator **Style Bibles**, and generates original 60-second comedic screenplays using Gemini 3.8 Flash.

---

## 🌟 Interactive Studio (Easiest Way to Use)

You don't need to memorize flags or commands! Simply run:

```bash
python -m app.cli
```

Or run:
```bash
python main.py
```
*(and press Enter to open the interactive studio)*

This launches an interactive menu where you can:
- ✍️ **Generate Scripts**: Select a creator and type your premise.
- 📥 **Upload Videos**: Select a creator and paste an Instagram Reel URL or file path.
- ✨ **Add Creators**: Register new comedic styles.
- 📖 **View Profiles & Bibles**: Inspect creators and synthesize Style Bibles.
- 📜 **View History**: Inspect upload and script history.
- 📊 **View Dashboard**: Check pipeline progression across all library assets.

For full details, see the **[CLI User Guide](CLI_GUIDE.md)**.

---

## 🏗️ Architecture

```
REFERENCE VIDEOS
       │
       ▼
Permanent Object Storage (Local / S3)
       │
       ▼
One-Time Gemini Video Extraction (Phase 2)
       │
       ▼
Video Memory Distillation & 768-dim Vector Embeddings (Phase 3)
       │
       ▼
Style Bible Creative Synthesis (Phase 4)
       │
       ▼
Text-Only Screenplay Generation Context (Phase 5)
  ├── Master Style Bible
  ├── Adaptive 10-Memory Context (<= 10 Direct | > 10 NumPy Cosine Retrieval)
  └── User Premise
       │
       ▼
ORIGINAL 60-SECOND COMEDY SCREENPLAY
```
