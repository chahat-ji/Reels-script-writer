"""
app/core/config.py
Centralized configuration management for Video-to-Style Script Generation.

Loads environment variables from .env and exposes canonical filesystem
paths for permanent object storage, SQLite database, and Gemini credentials.
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from rich.console import Console

# Shared Rich console for formatted, elegant terminal reporting across the app
console = Console()

# Resolve workspace root directory
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load local environment variables from .env file if present
load_dotenv(BASE_DIR / ".env")

# Canonical data directories
DATA_DIR = BASE_DIR / "data"
VIDEOS_DIR = DATA_DIR / "videos"
AUDIO_DIR = DATA_DIR / "audio"
EXTRACTIONS_DIR = DATA_DIR / "extractions"

# Ensure essential directories exist at startup
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)


class Settings:
    """Application runtime settings and environment parameter provider."""

    def __init__(self):
        # Database connection string: defaults to SQLite at data/app.db
        default_db_path = (DATA_DIR / "app.db").resolve()
        self.database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{default_db_path}")

        # Google Gemini API key
        self.gemini_api_key: Optional[str] = os.getenv("GEMINI_API_KEY")

        # Default model identifiers (User configured: gemini-3.8-flash)
        self.extraction_model: str = os.getenv("EXTRACTION_MODEL", "gemini-3.8-flash")
        self.synthesis_model: str = os.getenv("SYNTHESIS_MODEL", "gemini-3.8-flash")
        self.generation_model: str = os.getenv("GENERATION_MODEL", "gemini-3.8-flash")
        self.embedding_model: str = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")

        # Storage paths
        self.base_dir: Path = BASE_DIR
        self.data_dir: Path = DATA_DIR
        self.videos_dir: Path = VIDEOS_DIR
        self.audio_dir: Path = AUDIO_DIR
        self.extractions_dir: Path = EXTRACTIONS_DIR

    def get_gemini_api_key(self) -> str:
        """
        Retrieve the Gemini API key or raise an informative configuration error.
        """
        key = self.gemini_api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please set it in your environment or in a .env file."
            )
        return key


# Global singleton settings instance
settings = Settings()
config = settings