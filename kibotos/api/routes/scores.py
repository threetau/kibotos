"""Scores and weights endpoints for validators."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from kibotos.api.dependencies import DB
from kibotos.db.models import (
    CollectionCycle,
    ComputedWeights,
    CycleStatus,
    MinerScore,
)

router = APIRouter(tags=["scores"])


class MinerScoreResponse(BaseModel):
    """Miner score for a cycle."""

    miner_uid: int
    miner_hotkey: str
    total_submissions: int
    accepted_submissions: int
    avg_score: float | None
    total_score: float | None


class CycleScoresResponse(BaseModel):
    """Scores for a cycle."""

    cycle_id: int
    status: str
    started_at: datetime
    completed_at: datetime | None
    n_submissions: int
    miner_scores: list[MinerScoreResponse]


class WeightsResponse(BaseModel):
    """Computed weights for validators."""

    cycle_id: int
    block_number: int
    created_at: datetime
    weights: dict[str, float]  # uid -> weight (float)
    weights_u16: dict  # {uids: [], weights: []}


class CycleStatusResponse(BaseModel):
    """Current cycle status."""

    active_cycle_id: int | None
    active_cycle_started_at: datetime | None
    evaluating_cycle_id: int | None
    last_completed_cycle_id: int | None
    total_cycles: int


@router.get("/cycles/status")
async def get_cycle_status(db: DB) -> CycleStatusResponse:
    """Get current cycle status."""
    # Active cycle
    active_query = select(CollectionCycle).where(CollectionCycle.status == CycleStatus.ACTIVE.value)
    active_result = await db.execute(active_query)
    active = active_result.scalar_one_or_none()

    # Evaluating cycle
    eval_query = select(CollectionCycle).where(
        CollectionCycle.status == CycleStatus.EVALUATING.value
    )
    eval_result = await db.execute(eval_query)
    evaluating = eval_result.scalar_one_or_none()

    # Last completed cycle
    completed_query = (
        select(CollectionCycle)
        .where(CollectionCycle.status == CycleStatus.COMPLETED.value)
        .order_by(CollectionCycle.completed_at.desc())
        .limit(1)
    )
    completed_result = await db.execute(completed_query)
    last_completed = completed_result.scalar_one_or_none()

    # Total cycles
    from sqlalchemy import func

    total_query = select(func.count(CollectionCycle.id))
    total_result = await db.execute(total_query)
    total = total_result.scalar() or 0

    return CycleStatusResponse(
        active_cycle_id=active.id if active else None,
        active_cycle_started_at=active.started_at if active else None,
        evaluating_cycle_id=evaluating.id if evaluating else None,
        last_completed_cycle_id=last_completed.id if last_completed else None,
        total_cycles=total,
    )


@router.get("/scores/latest")
async def get_latest_scores(db: DB) -> CycleScoresResponse:
    """Get scores from the most recently completed cycle."""
    # Get latest completed cycle
    query = (
        select(CollectionCycle)
        .where(CollectionCycle.status == CycleStatus.COMPLETED.value)
        .order_by(CollectionCycle.completed_at.desc())
        .limit(1)
    )
    result = await db.execute(query)
    cycle = result.scalar_one_or_none()

    if not cycle:
        raise HTTPException(status_code=404, detail="No completed cycles found")

    return await _get_cycle_scores(db, cycle)


@router.get("/scores/{cycle_id}")
async def get_cycle_scores(db: DB, cycle_id: int) -> CycleScoresResponse:
    """Get scores for a specific cycle."""
    query = select(CollectionCycle).where(CollectionCycle.id == cycle_id)
    result = await db.execute(query)
    cycle = result.scalar_one_or_none()

    if not cycle:
        raise HTTPException(status_code=404, detail="Cycle not found")

    return await _get_cycle_scores(db, cycle)


async def _get_cycle_scores(db: DB, cycle: CollectionCycle) -> CycleScoresResponse:
    """Helper to build cycle scores response."""
    # Get miner scores
    scores_query = (
        select(MinerScore)
        .where(MinerScore.cycle_id == cycle.id)
        .order_by(MinerScore.total_score.desc())
    )
    scores_result = await db.execute(scores_query)
    miner_scores = scores_result.scalars().all()

    return CycleScoresResponse(
        cycle_id=cycle.id,
        status=cycle.status,
        started_at=cycle.started_at,
        completed_at=cycle.completed_at,
        n_submissions=cycle.n_submissions,
        miner_scores=[
            MinerScoreResponse(
                miner_uid=ms.miner_uid,
                miner_hotkey=ms.miner_hotkey,
                total_submissions=ms.total_submissions,
                accepted_submissions=ms.accepted_submissions,
                avg_score=ms.avg_score,
                total_score=ms.total_score,
            )
            for ms in miner_scores
        ],
    )


@router.get("/weights/latest")
async def get_latest_weights(db: DB) -> WeightsResponse:
    """Get the most recently computed weights."""
    query = select(ComputedWeights).order_by(ComputedWeights.created_at.desc()).limit(1)
    result = await db.execute(query)
    weights = result.scalar_one_or_none()

    if not weights:
        raise HTTPException(status_code=404, detail="No computed weights found")

    return WeightsResponse(
        cycle_id=weights.cycle_id,
        block_number=weights.block_number,
        created_at=weights.created_at,
        weights=weights.weights_json,
        weights_u16=weights.weights_u16_json,
    )


@router.get("/weights/{cycle_id}")
async def get_weights_for_cycle(db: DB, cycle_id: int) -> WeightsResponse:
    """Get weights for a specific cycle."""
    query = select(ComputedWeights).where(ComputedWeights.cycle_id == cycle_id)
    result = await db.execute(query)
    weights = result.scalar_one_or_none()

    if not weights:
        raise HTTPException(status_code=404, detail="Weights not found for cycle")

    return WeightsResponse(
        cycle_id=weights.cycle_id,
        block_number=weights.block_number,
        created_at=weights.created_at,
        weights=weights.weights_json,
        weights_u16=weights.weights_u16_json,
    )
