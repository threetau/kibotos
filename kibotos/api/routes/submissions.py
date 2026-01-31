"""Submission endpoints."""

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from kibotos.api.dependencies import DB
from kibotos.db.models import Evaluation, Prompt, Submission, SubmissionStatus

router = APIRouter(tags=["submissions"])


class PresignRequest(BaseModel):
    """Request for presigned upload URL."""

    filename: str
    content_type: str = "video/mp4"


class PresignResponse(BaseModel):
    """Presigned upload URL response."""

    upload_url: str
    video_key: str
    expires_in: int


class SubmissionCreateRequest(BaseModel):
    """Request to create a submission."""

    prompt_id: str
    video_key: str
    video_hash: str

    # Miner info
    miner_uid: int
    miner_hotkey: str
    signature: str  # Signature of payload for auth

    # Video metadata
    duration_sec: float
    resolution_width: int
    resolution_height: int
    fps: float
    camera_type: str
    actor_type: str

    # Optional metadata
    camera_intrinsics: dict | None = None
    robot_model: str | None = None
    environment: str | None = None
    action_description: str | None = None
    task_success: bool | None = None


class EvaluationResponse(BaseModel):
    """Evaluation result."""

    technical_score: float | None
    relevance_score: float | None
    quality_score: float | None
    final_score: float
    rejection_reason: str | None
    evaluated_at: datetime


class SubmissionResponse(BaseModel):
    """Submission response model."""

    submission_uuid: str
    prompt_id: str | None
    miner_uid: int
    video_key: str
    status: str
    submitted_at: datetime
    evaluated_at: datetime | None
    evaluation: EvaluationResponse | None


class SubmissionCreateResponse(BaseModel):
    """Response after creating a submission."""

    submission_uuid: str
    status: str


@router.post("/upload/presign")
async def get_presigned_url(request: PresignRequest) -> PresignResponse:
    """Get a presigned URL for uploading a video."""
    from kibotos.storage.s3 import get_s3_client

    s3 = get_s3_client()

    # Generate unique key
    video_key = f"uploads/{uuid4()}/{request.filename}"

    upload_url, expires_in = s3.generate_presigned_upload(
        key=video_key,
        content_type=request.content_type,
    )

    return PresignResponse(
        upload_url=upload_url,
        video_key=video_key,
        expires_in=expires_in,
    )


@router.post("/submissions")
async def create_submission(
    db: DB,
    request: SubmissionCreateRequest,
) -> SubmissionCreateResponse:
    """Create a new submission."""
    # Verify prompt exists and is active
    prompt_query = select(Prompt).where(Prompt.id == request.prompt_id)
    result = await db.execute(prompt_query)
    prompt = result.scalar_one_or_none()

    if not prompt:
        raise HTTPException(status_code=404, detail="Prompt not found")

    if not prompt.is_active:
        raise HTTPException(status_code=400, detail="Prompt is no longer active")

    # TODO: Verify miner signature
    # TODO: Check rate limiting (4 submissions per hour)

    # Create submission
    submission = Submission(
        prompt_id=request.prompt_id,
        cycle_id=prompt.cycle_id,
        miner_uid=request.miner_uid,
        miner_hotkey=request.miner_hotkey,
        video_key=request.video_key,
        video_hash=request.video_hash,
        duration_sec=request.duration_sec,
        resolution_width=request.resolution_width,
        resolution_height=request.resolution_height,
        fps=request.fps,
        camera_type=request.camera_type,
        actor_type=request.actor_type,
        camera_intrinsics=request.camera_intrinsics,
        robot_model=request.robot_model,
        environment=request.environment,
        action_description=request.action_description,
        task_success=request.task_success,
        status=SubmissionStatus.PENDING.value,
    )

    db.add(submission)
    await db.flush()
    await db.refresh(submission)

    # Update prompt submission count
    prompt.total_submissions += 1

    return SubmissionCreateResponse(
        submission_uuid=str(submission.submission_uuid),
        status=submission.status,
    )


@router.get("/submissions/{submission_uuid}")
async def get_submission(db: DB, submission_uuid: str) -> SubmissionResponse:
    """Get a submission by UUID."""
    query = select(Submission).where(Submission.submission_uuid == submission_uuid)
    result = await db.execute(query)
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Get evaluation if exists
    eval_query = select(Evaluation).where(Evaluation.submission_id == submission.id)
    eval_result = await db.execute(eval_query)
    evaluation = eval_result.scalar_one_or_none()

    eval_response = None
    if evaluation:
        eval_response = EvaluationResponse(
            technical_score=evaluation.technical_score,
            relevance_score=evaluation.relevance_score,
            quality_score=evaluation.quality_score,
            final_score=evaluation.final_score,
            rejection_reason=evaluation.rejection_reason,
            evaluated_at=evaluation.evaluated_at,
        )

    return SubmissionResponse(
        submission_uuid=str(submission.submission_uuid),
        prompt_id=submission.prompt_id,
        miner_uid=submission.miner_uid,
        video_key=submission.video_key,
        status=submission.status,
        submitted_at=submission.submitted_at,
        evaluated_at=submission.evaluated_at,
        evaluation=eval_response,
    )
