"""
app/core/config.py
Configuration loader for environments and YAML configuration profiles.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from dotenv import load_dotenv
from rich.console import Console

console = Console()

# Load .env file from project root
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"


def load_yaml(filepath: Path) -> Dict[str, Any]:
    if not filepath.exists():
        console.print(f"[yellow]Warning: Config file not found at {filepath}[/yellow]")
        return {}
    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class EngineConfig:
    def __init__(self):
        self.providers_cfg = load_yaml(CONFIG_DIR / "providers.yaml")
        self.profiles_cfg = load_yaml(CONFIG_DIR / "profiles.yaml")
        self.routing_rules = load_yaml(CONFIG_DIR / "routing_rules.yaml")

    def get_api_key(self, env_var_name: str) -> Optional[str]:
        if not env_var_name:
            return None
        return os.getenv(env_var_name)

    def get_profile(self, profile_name: str = "default") -> Dict[str, Any]:
        profiles = self.profiles_cfg.get("profiles", {})
        return profiles.get(profile_name, profiles.get("default", {}))


config = EngineConfig()