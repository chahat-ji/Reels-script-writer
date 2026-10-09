"""
batch_process.py
Backwards-compatibility forwarder for app.ingestion.sync.
All batch and sync features are integrated into app.ingestion.sync and python -m app.cli batch / sync.
"""

from app.ingestion.sync import (
    display_dashboard,
    main,
    process_url_file,
    sync_all_videos,
    synthesize_style_corpus,
)

if __name__ == "__main__":
    main()
