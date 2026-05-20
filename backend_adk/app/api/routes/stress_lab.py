"""Stress Lab APIs for repeatable latency benchmark scenarios."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agents.callcenter.stress_lab import StressLabService
from app.core.config import Settings, get_settings

router = APIRouter()


class StressLabRunRequest(BaseModel):
    """Request body for starting a stress-lab run."""

    scenario_ids: list[str] | None = Field(default=None)
    repeat_count: int = Field(default=1, ge=1, le=20)
    concurrency: int = Field(default=1, ge=1, le=5)


@router.get("/scenarios")
async def list_stress_lab_scenarios(
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """List available stress-lab scenarios and their enablement state."""
    service = StressLabService(settings)
    return {
        "enabled": settings.stress_lab_enabled,
        "real_openai_tools_enabled": settings.stress_lab_real_openai_tools_enabled,
        "scenarios": service.list_scenarios(),
    }


@router.post("/runs")
async def run_stress_lab(
    request: StressLabRunRequest,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Run one scenario or a suite of stress-lab scenarios."""
    service = StressLabService(settings)
    try:
        return await service.run(
            scenario_ids=request.scenario_ids,
            repeat_count=request.repeat_count,
            concurrency=request.concurrency,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{run_id}")
async def get_stress_lab_run(
    run_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Fetch one persisted stress-lab run."""
    service = StressLabService(settings)
    run = await service.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Stress-lab run not found")
    return run
