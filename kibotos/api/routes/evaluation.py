"""Evaluation endpoints for the evaluator service."""

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, update

from kibotos.api.dependencies import DB
from kibotos.db.models import Evaluation, Prompt, Submission, SubmissionStatus

router = APIRouter(tags=["evaluation"])


class FetchRequest(BaseModel):
    """Request to fetch pending submissions."""

    limit: int = 5


class PendingSubmissionResponse(BaseModel):
    """A pending submission for evaluation."""

    id: int
    submission_uuid: str
    prompt_id: str
    video_key: str
    category: str
    task: str
    scenario: str
    requirements: dict


class FetchResponse(BaseModel):
    """Response with pending submissions."""

    submissions: list[PendingSubmissionResponse]


class SubmitResultRequest(BaseModel):
    """Request to submit evaluation results."""

    submission_id: int
    technical_score: float
    relevance_score: float
    quality_score: float
    final_score: float
    rejection_reason: str | None = None
    metadata: dict | None = None


class SubmitResultResponse(BaseModel):
    """Response after submitting evaluation."""

    success: bool
    submission_uuid: str
    final_score: float


@router.post("/evaluate/fetch")
async def fetch_pending(db: DB, request: FetchRequest) -> FetchResponse:
    """Fetch pending submissions for evaluation."""
    # Get pending submissions with their prompts
    query = (
        select(Submission, Prompt)
        .join(Prompt, Submission.prompt_id == Prompt.id)
        .where(Submission.status == SubmissionStatus.PENDING.value)
        .order_by(Submission.submitted_at)
        .limit(request.limit)
    )

    result = await db.execute(query)
    rows = result.all()

    if not rows:
        return FetchResponse(submissions=[])

    # Mark as evaluating
    submission_ids = [row[0].id for row in rows]
    await db.execute(
        update(Submission)
        .where(Submission.id.in_(submission_ids))
        .values(status=SubmissionStatus.EVALUATING.value)
    )

    return FetchResponse(
        submissions=[
            PendingSubmissionResponse(
                id=sub.id,
                submission_uuid=str(sub.submission_uuid),
                prompt_id=sub.prompt_id,
                video_key=sub.video_key,
                category=prompt.category,
                task=prompt.task,
                scenario=prompt.scenario,
                requirements=prompt.requirements or {},
            )
            for sub, prompt in rows
        ]
    )


@router.post("/evaluate/submit")
async def submit_result(db: DB, request: SubmitResultRequest) -> SubmitResultResponse:
    """Submit evaluation results for a submission."""
    # Get the submission
    query = select(Submission).where(Submission.id == request.submission_id)
    result = await db.execute(query)
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Create evaluation record
    evaluation = Evaluation(
        submission_id=submission.id,
        technical_score=request.technical_score,
        relevance_score=request.relevance_score,
        quality_score=request.quality_score,
        final_score=request.final_score,
        rejection_reason=request.rejection_reason,
        evaluation_metadata=request.metadata,
    )
    db.add(evaluation)

    # Update submission status
    new_status = (
        SubmissionStatus.REJECTED.value
        if request.rejection_reason
        else SubmissionStatus.SCORED.value
    )
    submission.status = new_status
    submission.evaluated_at = datetime.utcnow()

    await db.flush()

    return SubmitResultResponse(
        success=True,
        submission_uuid=str(submission.submission_uuid),
        final_score=request.final_score,
    )
