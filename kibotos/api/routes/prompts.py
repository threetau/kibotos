"""Prompt endpoints."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select

from kibotos.api.dependencies import DB
from kibotos.db.models import Prompt

router = APIRouter(tags=["prompts"])


class PromptResponse(BaseModel):
    """Prompt response model."""

    id: str
    category: str
    task: str
    scenario: str
    requirements: dict
    weight: float
    created_at: datetime
    expires_at: datetime | None
    total_submissions: int
    is_active: bool


class CategoryStats(BaseModel):
    """Category statistics."""

    category: str
    count: int


class PromptCreateRequest(BaseModel):
    """Request to create a prompt."""

    id: str
    category: str
    task: str
    scenario: str
    requirements: dict = {}
    weight: float = 1.0
    expires_at: datetime | None = None


@router.get("/prompts")
async def list_prompts(
    db: DB,
    category: str | None = None,
    active_only: bool = True,
) -> list[PromptResponse]:
    """List prompts, optionally filtered by category."""
    query = select(Prompt)

    if active_only:
        query = query.where(Prompt.is_active == True)  # noqa: E712

    if category:
        query = query.where(Prompt.category == category)

    query = query.order_by(Prompt.created_at.desc())

    result = await db.execute(query)
    prompts = result.scalars().all()

    return [
        PromptResponse(
            id=p.id,
            category=p.category,
            task=p.task,
            scenario=p.scenario,
            requirements=p.requirements or {},
            weight=p.weight,
            created_at=p.created_at,
            expires_at=p.expires_at,
            total_submissions=p.total_submissions,
            is_active=p.is_active,
        )
        for p in prompts
    ]


@router.get("/prompts/categories")
async def list_categories(db: DB) -> list[CategoryStats]:
    """List prompt categories with counts."""
    query = (
        select(Prompt.category, func.count(Prompt.id).label("count"))
        .where(Prompt.is_active == True)  # noqa: E712
        .group_by(Prompt.category)
        .order_by(Prompt.category)
    )

    result = await db.execute(query)
    rows = result.all()

    return [CategoryStats(category=row.category, count=row.count) for row in rows]


@router.get("/prompts/{prompt_id}")
async def get_prompt(db: DB, prompt_id: str) -> PromptResponse:
    """Get a specific prompt by ID."""
    query = select(Prompt).where(Prompt.id == prompt_id)
    result = await db.execute(query)
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    return PromptResponse(
        id=prompt.id,
        category=prompt.category,
        task=prompt.task,
        scenario=prompt.scenario,
        requirements=prompt.requirements or {},
        weight=prompt.weight,
        created_at=prompt.created_at,
        expires_at=prompt.expires_at,
        total_submissions=prompt.total_submissions,
        is_active=prompt.is_active,
    )


@router.post("/admin/prompts")
async def create_prompt(db: DB, request: PromptCreateRequest) -> PromptResponse:
    """Create a new prompt (admin only)."""
    # Check if prompt ID already exists
    existing = await db.execute(select(Prompt).where(Prompt.id == request.id))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Prompt ID already exists")

    prompt = Prompt(
        id=request.id,
        category=request.category,
        task=request.task,
        scenario=request.scenario,
        requirements=request.requirements,
        weight=request.weight,
        expires_at=request.expires_at,
    )

    db.add(prompt)
    await db.flush()
    await db.refresh(prompt)

    return PromptResponse(
        id=prompt.id,
        category=prompt.category,
        task=prompt.task,
        scenario=prompt.scenario,
        requirements=prompt.requirements or {},
        weight=prompt.weight,
        created_at=prompt.created_at,
        expires_at=prompt.expires_at,
        total_submissions=prompt.total_submissions,
        is_active=prompt.is_active,
    )
