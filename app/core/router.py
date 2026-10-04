"""
app/core/router.py
Evaluates preflight findings, profiles, and budget limits to generate an ExecutionPlan.
"""

import json
from pathlib import Path
from rich.console import Console
from app.core.config import config
from app.core.registry import registry
from app.models.state import ConditionReport, ExecutionPlan, TaskPlan

console = Console()


def create_execution_plan(condition_report: ConditionReport, profile_name: str = "default", data_root: str = "data") -> ExecutionPlan:
    """
    Builds plan.json for a given reel based on preflight inspection.
    """
    profile = config.get_profile(profile_name)
    max_budget = profile.get("limits", {}).get("max_usd_per_reel", 0.25)
    plans = {}

    # 1. Routing for Speech Capability
    primary_speech = profile.get("speech", "assemblyai")
    provider_chain = [primary_speech]

    # Add fallback if primary is paid and budget is tight
    provider_cls = registry.get("speech", primary_speech)
    total_cost = 0.0

    if provider_cls:
        provider = provider_cls()
        estimate = provider.estimate({"duration_seconds": condition_report.duration_seconds})
        total_cost = estimate.expected_cost_usd

        # If estimated cost exceeds budget, switch to local provider fallback
        if total_cost > max_budget:
            console.print(f"[yellow]Budget guard triggered:[/yellow] Est cost ${total_cost:.4f} > max ${max_budget:.4f}. Falling back to local.")
            provider_chain = ["mlx_whisper"]
            total_cost = 0.0

        plans["speech"] = TaskPlan(
            capability="speech",
            provider_chain=provider_chain,
            estimated_cost_usd=total_cost,
            estimated_seconds=estimate.expected_seconds,
        )

    execution_plan = ExecutionPlan(
        reel_id=condition_report.reel_id,
        profile=profile_name,
        preflight=condition_report,
        plans=plans,
    )

    # Persist condition report and plan to reel directory
    reel_dir = Path(data_root) / "reels" / condition_report.reel_id
    with open(reel_dir / "condition_report.json", "w", encoding="utf-8") as f:
        json.dump(condition_report.model_dump(), f, indent=2)

    with open(reel_dir / "plan.json", "w", encoding="utf-8") as f:
        json.dump(execution_plan.model_dump(), f, indent=2)

    console.print(f"[bold blue][PLAN READY][/bold blue] Saved condition_report.json and plan.json for [green]{condition_report.reel_id}[/green]")
    return execution_plan