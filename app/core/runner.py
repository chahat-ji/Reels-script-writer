"""
app/core/runner.py
Idempotent task execution runner and disk cache.
"""

import json
from pathlib import Path
from typing import Any, Dict
from rich.console import Console
from app.capabilities.base import Provider, ProviderResult

console = Console()


class TaskRunner:
    def __init__(self, data_root: str = "data"):
        self.data_root = Path(data_root)

    def execute(self, reel_id: str, provider: Provider, job: Dict[str, Any]) -> ProviderResult:
        reel_dir = self.data_root / "reels" / reel_id
        reel_dir.mkdir(parents=True, exist_ok=True)

        cache_filename = f"manifest_{provider.capability}_{provider.name}_v{provider.version}.json"
        cache_path = reel_dir / cache_filename

        # 1. Return cached results if available
        if cache_path.exists():
            console.print(
                f"[bold cyan][CACHE HIT][/bold cyan] {provider.capability} -> "
                f"[magenta]{provider.name}[/magenta] for [green]{reel_id}[/green]"
            )
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                return ProviderResult(**cached_data)

        # 2. Check health prerequisites before executing
        health = provider.health()
        if not health.installed or not health.key_present:
            console.print(f"[bold red][HEALTH FAILED][/bold red] Provider '{provider.name}': {health.error}")
            raise RuntimeError(f"Provider '{provider.name}' unhealthy: {health.error}")

        # 3. Execute job
        console.print(
            f"[bold green][RUNNING][/bold green] {provider.capability} -> "
            f"[magenta]{provider.name}[/magenta] ({provider.tier}) on [green]{reel_id}[/green]"
        )
        result = provider.run(job)

        # 4. Save to run store
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)

        console.print(f"[bold blue][SAVED][/bold blue] Manifest saved to {cache_path.relative_to(self.data_root.parent if self.data_root.is_absolute() else '.')}")
        return result


runner = TaskRunner()