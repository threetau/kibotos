"""SQLAlchemy models for Kibotos."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Base class for all models."""

    type_annotation_map = {
        dict[str, Any]: JSONB,
    }


class CycleStatus(str, Enum):
    """Status of a collection cycle."""

    ACTIVE = "ACTIVE"
    EVALUATING = "EVALUATING"
    COMPLETED = "COMPLETED"


class SubmissionStatus(str, Enum):
    """Status of a video submission."""

    PENDING = "PENDING"
    EVALUATING = "EVALUATING"
    SCORED = "SCORED"
    REJECTED = "REJECTED"


class CameraType(str, Enum):
    """Type of camera used for recording."""

    EGO_HEAD = "ego_head"
    EGO_CHEST = "ego_chest"
    EGO_WRIST = "ego_wrist"
    ROBOT_HEAD = "robot_head"
    ROBOT_WRIST = "robot_wrist"


class ActorType(str, Enum):
    """Type of actor performing the task."""

    HUMAN = "human"
    ROBOT = "robot"
    HUMAN_WITH_ROBOT = "human_with_robot"


class CollectionCycle(Base):
    """A collection cycle for gathering video data."""

    __tablename__ = "collection_cycles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default=CycleStatus.ACTIVE.value)
    n_prompts: Mapped[int] = mapped_column(Integer, default=0)
    n_submissions: Mapped[int] = mapped_column(Integer, default=0)

    # Relationships
    prompts: Mapped[list["Prompt"]] = relationship(back_populates="cycle")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="cycle")
    miner_scores: Mapped[list["MinerScore"]] = relationship(back_populates="cycle")
    computed_weights: Mapped["ComputedWeights | None"] = relationship(back_populates="cycle")


class Prompt(Base):
    """A prompt for miners to fulfill."""

    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("collection_cycles.id"))
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    task: Mapped[str] = mapped_column(String(64), nullable=False)
    scenario: Mapped[str] = mapped_column(Text, nullable=False)
    requirements: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_submissions: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    cycle: Mapped["CollectionCycle | None"] = relationship(back_populates="prompts")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="prompt")

    __table_args__ = (Index("idx_prompts_active", "is_active", "category"),)


class Submission(Base):
    """A video submission from a miner."""

    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_uuid: Mapped[str] = mapped_column(
        UUID(as_uuid=False), default=lambda: str(uuid4()), unique=True
    )
    cycle_id: Mapped[int | None] = mapped_column(ForeignKey("collection_cycles.id"))
    prompt_id: Mapped[str | None] = mapped_column(ForeignKey("prompts.id"))

    # Miner info
    miner_uid: Mapped[int] = mapped_column(Integer, nullable=False)
    miner_hotkey: Mapped[str] = mapped_column(String(48), nullable=False)

    # Video info
    video_key: Mapped[str] = mapped_column(String(256), nullable=False)
    video_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Required metadata
    duration_sec: Mapped[float] = mapped_column(Float, nullable=False)
    resolution_width: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_height: Mapped[int] = mapped_column(Integer, nullable=False)
    fps: Mapped[float] = mapped_column(Float, nullable=False)
    camera_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)

    # Optional metadata
    camera_intrinsics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    robot_model: Mapped[str | None] = mapped_column(String(64))
    environment: Mapped[str | None] = mapped_column(String(64))
    action_description: Mapped[str | None] = mapped_column(Text)
    task_success: Mapped[bool | None] = mapped_column(Boolean)

    # Status
    status: Mapped[str] = mapped_column(String(20), default=SubmissionStatus.PENDING.value)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    cycle: Mapped["CollectionCycle | None"] = relationship(back_populates="submissions")
    prompt: Mapped["Prompt | None"] = relationship(back_populates="submissions")
    evaluation: Mapped["Evaluation | None"] = relationship(
        back_populates="submission",
        uselist=False,
        foreign_keys="[Evaluation.submission_id]",
    )

    __table_args__ = (
        Index("idx_submissions_status", "status", "cycle_id"),
        Index("idx_submissions_miner", "miner_uid", "cycle_id"),
        Index("idx_submissions_prompt", "prompt_id"),
    )


class Evaluation(Base):
    """Evaluation results for a submission."""

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"), unique=True
    )

    # Scores (0-1)
    technical_score: Mapped[float | None] = mapped_column(Float)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    quality_score: Mapped[float | None] = mapped_column(Float)

    # Final computed score
    final_score: Mapped[float] = mapped_column(Float, nullable=False)

    # Metadata
    evaluation_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    duplicate_of: Mapped[int | None] = mapped_column(ForeignKey("submissions.id"))
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    submission: Mapped["Submission"] = relationship(
        back_populates="evaluation",
        foreign_keys=[submission_id],
    )

    __table_args__ = (Index("idx_evaluations_submission", "submission_id"),)


class MinerScore(Base):
    """Aggregated scores for a miner per cycle."""

    __tablename__ = "miner_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("collection_cycles.id"))
    miner_uid: Mapped[int] = mapped_column(Integer, nullable=False)
    miner_hotkey: Mapped[str] = mapped_column(String(48), nullable=False)

    # Aggregated metrics
    total_submissions: Mapped[int] = mapped_column(Integer, default=0)
    accepted_submissions: Mapped[int] = mapped_column(Integer, default=0)
    avg_score: Mapped[float | None] = mapped_column(Float)
    total_score: Mapped[float | None] = mapped_column(Float)

    # Category breakdown
    scores_by_category: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    # Relationships
    cycle: Mapped["CollectionCycle"] = relationship(back_populates="miner_scores")

    __table_args__ = (
        UniqueConstraint("cycle_id", "miner_uid"),
        Index("idx_miner_scores_cycle", "cycle_id", "miner_uid"),
    )


class ComputedWeights(Base):
    """Computed weights for validators to submit."""

    __tablename__ = "computed_weights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cycle_id: Mapped[int] = mapped_column(ForeignKey("collection_cycles.id"), unique=True)
    block_number: Mapped[int] = mapped_column(Integer, nullable=False)
    weights_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    weights_u16_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    cycle: Mapped["CollectionCycle"] = relationship(back_populates="computed_weights")
