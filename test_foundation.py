"""
test_foundation.py
Verification test for Phase 0.1 Foundation.
"""

from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from app.capabilities.base import (
    Provider,
    Health,
    Estimate,
    ProviderResult,
    CanonicalEvent
)
from app.core.registry import registry
from app.core.runner import runner
from app.core.config import config

console = Console()


class MockSpeechProvider(Provider):
    capability = "speech"
    name = "mock_speech"
    version = "1.0.0"
    tier = "free"

    def health(self) -> Health:
        return Health(installed=True, key_present=True, enough_ram=True)

    def estimate(self, media_info: dict) -> Estimate:
        return Estimate(expected_cost_usd=0.0, expected_seconds=1.2, peak_ram_gb=0.5)

    def run(self, job: dict) -> ProviderResult:
        event = CanonicalEvent(
            track="speech",
            start_ms=0,
            end_ms=1500,
            type="word",
            payload={"text": "Namaste Dosto"},
            confidence=0.99,
            provider=self.name,
            provider_version=self.version
        )
        return ProviderResult(
            capability=self.capability,
            provider_name=self.name,
            provider_version=self.version,
            events=[event]
        )


def main():
    console.print(Panel.fit("[bold green]Phase 0.1: Foundation Verification[/bold green]"))

    # 1. Register mock provider
    registry.register("speech", "mock_speech", MockSpeechProvider)
    
    # 2. Inspect Registry
    reg_table = Table(title="Registered Capabilities & Providers")
    reg_table.add_column("Capability", style="cyan")
    reg_table.add_column("Available Providers", style="magenta")
    
    for cap, provs in registry.list_providers().items():
        reg_table.add_row(cap, ", ".join(provs))
    console.print(reg_table)

    # 3. Retrieve and run
    provider_cls = registry.get("speech", "mock_speech")
    provider_instance = provider_cls()

    reel_id = "test_reel_123"
    result = runner.execute(reel_id, provider_instance, {"audio_path": "dummy.wav"})

    # 4. Display result summary
    res_table = Table(title=f"Execution Manifest ({reel_id})")
    res_table.add_column("Track", style="yellow")
    res_table.add_column("Time (ms)", style="cyan")
    res_table.add_column("Type", style="green")
    res_table.add_column("Payload", style="white")
    res_table.add_column("Confidence", style="magenta")

    for ev in result.events:
        res_table.add_row(
            ev.track,
            f"{ev.start_ms} - {ev.end_ms}",
            ev.type,
            str(ev.payload),
            f"{ev.confidence:.2f}"
        )
    console.print(res_table)

    # 5. Display loaded config profiles
    default_profile = config.get_profile("default")
    console.print(Panel(f"[bold]Default Profile Settings:[/bold]\n{default_profile}", title="Configuration Loader"))


if __name__ == "__main__":
    main()