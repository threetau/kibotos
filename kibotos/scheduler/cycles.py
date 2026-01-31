"""Cycle management for collection cycles."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kibotos.db.models import (
    CollectionCycle,
    CycleStatus,
    Prompt,
    Submission,
    SubmissionStatus,
)


class CycleManager:
    """Manages collection cycles."""

    def __init__(self, cycle_duration_minutes: int = 60):
        self.cycle_duration = timedelta(minutes=cycle_duration_minutes)

    async def get_active_cycle(self, db: AsyncSession) -> CollectionCycle | None:
        """Get the currently active cycle."""
        query = select(CollectionCycle).where(CollectionCycle.status == CycleStatus.ACTIVE.value)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def start_cycle(self, db: AsyncSession) -> CollectionCycle:
        """Start a new collection cycle."""
        # Check if there's already an active cycle
        active = await self.get_active_cycle(db)
        if active:
            raise ValueError(f"Cycle {active.id} is already active")

        # Count active prompts
        prompt_count = await db.execute(
            select(func.count(Prompt.id)).where(Prompt.is_active == True)  # noqa: E712
        )
        n_prompts = prompt_count.scalar() or 0

        # Create new cycle
        cycle = CollectionCycle(
            status=CycleStatus.ACTIVE.value,
            n_prompts=n_prompts,
        )
        db.add(cycle)
        await db.flush()
        await db.refresh(cycle)

        return cycle

    async def complete_cycle(self, db: AsyncSession, cycle_id: int) -> CollectionCycle:
        """
        Complete a cycle and transition to EVALUATING state.

        This marks the cycle as no longer accepting submissions.
        """
        query = select(CollectionCycle).where(CollectionCycle.id == cycle_id)
        result = await db.execute(query)
        cycle = result.scalar_one_or_none()

        if not cycle:
            raise ValueError(f"Cycle {cycle_id} not found")

        if cycle.status != CycleStatus.ACTIVE.value:
            raise ValueError(f"Cycle {cycle_id} is not active (status: {cycle.status})")

        # Count submissions
        sub_count = await db.execute(
            select(func.count(Submission.id)).where(Submission.cycle_id == cycle_id)
        )
        cycle.n_submissions = sub_count.scalar() or 0

        # Transition to EVALUATING
        cycle.status = CycleStatus.EVALUATING.value

        await db.flush()
        await db.refresh(cycle)

        return cycle

    async def finalize_cycle(self, db: AsyncSession, cycle_id: int) -> CollectionCycle:
        """
        Finalize a cycle after all evaluations are complete.

        This marks the cycle as COMPLETED.
        """
        query = select(CollectionCycle).where(CollectionCycle.id == cycle_id)
        result = await db.execute(query)
        cycle = result.scalar_one_or_none()

        if not cycle:
            raise ValueError(f"Cycle {cycle_id} not found")

        if cycle.status != CycleStatus.EVALUATING.value:
            raise ValueError(f"Cycle {cycle_id} is not evaluating (status: {cycle.status})")

        cycle.status = CycleStatus.COMPLETED.value
        cycle.completed_at = datetime.utcnow()

        await db.flush()
        await db.refresh(cycle)

        return cycle

    async def check_cycle_should_complete(
        self,
        db: AsyncSession,
        cycle: CollectionCycle,
    ) -> bool:
        """Check if a cycle has exceeded its duration."""
        if cycle.status != CycleStatus.ACTIVE.value:
            return False

        elapsed = datetime.utcnow() - cycle.started_at.replace(tzinfo=None)
        return elapsed >= self.cycle_duration

    async def check_evaluations_complete(
        self,
        db: AsyncSession,
        cycle_id: int,
    ) -> bool:
        """Check if all submissions in a cycle have been evaluated."""
        # Count pending/evaluating submissions
        pending_count = await db.execute(
            select(func.count(Submission.id)).where(
                Submission.cycle_id == cycle_id,
                Submission.status.in_(
                    [
                        SubmissionStatus.PENDING.value,
                        SubmissionStatus.EVALUATING.value,
                    ]
                ),
            )
        )
        return (pending_count.scalar() or 0) == 0

    async def get_cycle_stats(self, db: AsyncSession, cycle_id: int) -> dict:
        """Get statistics for a cycle."""
        # Total submissions
        total = await db.execute(
            select(func.count(Submission.id)).where(Submission.cycle_id == cycle_id)
        )

        # Scored submissions
        scored = await db.execute(
            select(func.count(Submission.id)).where(
                Submission.cycle_id == cycle_id,
                Submission.status == SubmissionStatus.SCORED.value,
            )
        )

        # Rejected submissions
        rejected = await db.execute(
            select(func.count(Submission.id)).where(
                Submission.cycle_id == cycle_id,
                Submission.status == SubmissionStatus.REJECTED.value,
            )
        )

        # Pending submissions
        pending = await db.execute(
            select(func.count(Submission.id)).where(
                Submission.cycle_id == cycle_id,
                Submission.status.in_(
                    [
                        SubmissionStatus.PENDING.value,
                        SubmissionStatus.EVALUATING.value,
                    ]
                ),
            )
        )

        # Unique miners
        miners = await db.execute(
            select(func.count(func.distinct(Submission.miner_uid))).where(
                Submission.cycle_id == cycle_id
            )
        )

        return {
            "cycle_id": cycle_id,
            "total_submissions": total.scalar() or 0,
            "scored": scored.scalar() or 0,
            "rejected": rejected.scalar() or 0,
            "pending": pending.scalar() or 0,
            "unique_miners": miners.scalar() or 0,
        }


def get_cycle_manager(cycle_duration_minutes: int = 60) -> CycleManager:
    """Get a cycle manager instance."""
    return CycleManager(cycle_duration_minutes)
