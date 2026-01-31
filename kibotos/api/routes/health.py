"""Health check endpoints."""

from fastapi import APIRouter
from pydantic import BaseModel

from kibotos import __version__

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str


class StatusResponse(BaseModel):
    """Backend status response."""

    status: str
    version: str
    active_cycle_id: int | None
    total_prompts: int
    total_submissions: int


@router.get("/health")
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", version=__version__)


@router.get("/v1/status")
async def status() -> StatusResponse:
    """Get backend status."""
    # TODO: Fetch actual stats from database
    return StatusResponse(
        status="ok",
        version=__version__,
        active_cycle_id=None,
        total_prompts=0,
        total_submissions=0,
    )
