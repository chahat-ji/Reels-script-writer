"""
app/core/runner.py
Idempotent task execution runner with fallback chain support and disk cache.
"""

import json
from pathlib import Path
from typing import Any, Dict, List
from rich.console import Console

from app.capabilities.base import Provider, ProviderResult
from app.core.registry import registry

console = Console()


class TaskRunner:
    def __init__(self, data_root: str = "data"):
        self.data_root = Path(data_root)

    def execute(self, reel_id: str, provider: Provider, job: Dict[str, Any], force: bool = False) -> ProviderResult:
        reel_dir = self.data_root / "reels" / reel_id
        reel_dir.mkdir(parents=True, exist_ok=True)

        cache_filename = f"manifest_{provider.capability}_{provider.name}_v{provider.version}.json"
        cache_path = reel_dir / cache_filename

        # 1. Return cached results if available and not forced
        if cache_path.exists() and not force:
            console.print(
                f"[bold cyan][CACHE HIT][/bold cyan] {provider.capability} -> "
                f"[magenta]{provider.name}[/magenta] for [green]{reel_id}[/green]"
            )
            with open(cache_path, "r", encoding="utf-8") as f:
                cached_data = json.load(f)
                return ProviderResult(**cached_data)

        # 2. Check health prerequisites
        health = provider.health()
        if not health.installed or not health.key_present:
            raise RuntimeError(f"Provider '{provider.name}' unhealthy: {health.error}")

        # 3. Execute
        console.print(
            f"[bold green][RUNNING][/bold green] {provider.capability} -> "
            f"[magenta]{provider.name}[/magenta] ({provider.tier}) on [green]{reel_id}[/green]"
        )
        result = provider.run(job)

        # 4. Save manifest
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, indent=2, ensure_ascii=False)

        console.print(f"[bold blue][SAVED][/bold blue] Manifest saved to {cache_path.name}")
        return result

    def execute_chain(
        self,
        reel_id: str,
        capability: str,
        provider_names: List[str],
        job: Dict[str, Any],
        force: bool = False,
    ) -> ProviderResult:
        """
        Attempts each provider in order. If one fails, gracefully falls back to the next.
        """
        last_error = None

        for name in provider_names:
            provider_cls = registry.get(capability, name)
            if not provider_cls:
                console.print(f"[yellow]Provider '{name}' not found in registry. Skipping...[/yellow]")
                continue

            provider = provider_cls()
            try:
                return self.execute(reel_id, provider, job, force=force)
            except Exception as e:
                console.print(f"[bold red][FALLBACK][/bold red] Provider '{name}' failed: {e}. Trying next provider in chain...")
                last_error = e

        raise RuntimeError(f"All providers in chain {provider_names} failed for capability '{capability}'. Last error: {last_error}")


runner = TaskRunner()