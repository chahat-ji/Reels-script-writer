# 🎬 Script Writer – Simple User Guide

The CLI features an **Interactive Studio** with numbered menus and step-by-step prompts. **You don't need to memorize flags or commands!** Just run one command and pick what you want to do.

---

## 🌟 The Simplest Way: Interactive Studio (Recommended)

Just run:
```bash
python -m app.cli
```
*(or run `python main.py` and hit Enter)*

You will see this interactive menu:

```
╭───────────────────── 🎬 Script Writer – Interactive Studio ─────────────────────╮
│ 👤 Logged in as: test_user (usr_test_user)                                      │
╰─────────────────────────────────────────────────────────────────────────────────╯
What would you like to do?
  [1] ✍️  Generate Script        (Write comedy screenplay from premise)
  [2] 📥 Upload Videos          (Ingest Reel URLs or video files)
  [3] 🔄 Sync Pending Videos    (Process pending extractions & embeddings)
  [4] ✨ Add Creator Profile    (Create new comedic style)
  [5] 📖 Creator Profiles & Bibles (View profiles & synthesize)
  [6] 📜 View History           (Uploads & generated screenplays)
  [7] 📊 Pipeline Status        (View reference library status)
  [8] 🌐 Web Studio Dashboard   (Launch browser Reel & Script Reviewer)
  [9] 👤 Switch User / Login    (Change active account)
  [0] 🚪 Exit

Select an option [0-9] (1):
```

### How Each Option Works:

| Option | What it asks you | What it does |
| :--- | :--- | :--- |
| **[1] ✍️ Generate Script** | 1. Select creator from list<br>2. Type premise concept | Synthesizes Style Bible (if needed) & generates a full ready-to-shoot comedy screenplay |
| **[2] 📥 Upload Videos** | 1. Select creator from list<br>2. Paste Instagram Reel URL or file path | Downloads, extracts audio, indexes creative memory & updates creator's Style Bible |
| **[3] 🔄 Sync Videos** | Choose scope: `[1] My Videos`, `[2] By Creator`, `[3] All DB` | Advances pending videos to Phase 2 (Extraction) & Phase 3 (Vector Indexing) |
| **[4] ✨ Add Creator** | 1. Creator display name<br>2. Optional description | Registers a new creator profile under your account |
| **[5] 📖 View Profiles** | 1. Shows table of creators<br>2. Option `[S]` to synthesize Style Bible | Inspects all creators and lets you trigger manual Style Bible synthesis |
| **[6] 📜 View History** | Choose `[1]` Uploads or `[2]` Scripts | Displays full formatted history tables |
| **[7] 📊 Pipeline Status** | No inputs needed | Displays progress dashboard of all library videos in terminal |
| **[8] 🌐 Web Studio** | No inputs needed | Launches local web dashboard on `http://127.0.0.1:8080` for video playback and script review |
| **[9] 👤 Switch User** | Enter username & optional email | Switches active session or registers a new user |
| **[0] 🚪 Exit** | None | Exits cleanly |

---

## ⚡ Superpower: Cross-Creator Video Deduplication
If you upload an Instagram Reel or video that was **already processed under another creator**:
- Video download is **automatically skipped** (0 MB downloaded).
- Gemini video extraction is **automatically skipped** (0 video tokens).
- Gemini embedding is **automatically skipped** (0 embedding tokens).
- The video's creative memory is **instantly linked** to the new creator with zero latency and zero API cost!

---

## 💻 Optional: Direct Command-Line Shortcuts

If you prefer running one-liner commands without the menu, all direct commands are still available:

### 1. Direct Script Generation
```bash
python -m app.cli generate <creator_id> --premise "<your idea>"
```
*Example:*
```bash
python -m app.cli generate nani_comedy --premise "Raju hides his report card inside the fridge"
```

### 2. Direct Video Upload
```bash
# Single Reel
python -m app.cli upload <creator_id> "<url_or_filepath>"

# Batch from file
python -m app.cli upload <creator_id> urls.txt --concurrency 2
```

### 3. Direct Pipeline Sync
```bash
python -m app.cli sync                  # Sync videos for your creators (user scoped)
python -m app.cli sync --creator <id>   # Sync videos for a specific creator
python -m app.cli sync --all            # Sync all library videos in entire DB (global)
```

### 4. Direct Video Intake (Legacy)
```bash
python main.py "<url>" [creator_id]
```

### 5. Direct Account Management
```bash
python -m app.cli user login <username> [--email <email>]
python -m app.cli user whoami
python -m app.cli creator add "<Name>" [--id <id>]
python -m app.cli creator list
python -m app.cli history scripts --creator <creator_id>
```

### 6. Web Studio Dashboard
```bash
python -m app.cli dashboard             # Launches on http://127.0.0.1:8080
python -m app.cli dashboard --port 9000  # Custom port
```

