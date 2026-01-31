"""Weight computation for miner rewards."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kibotos.db.models import (
    ComputedWeights,
    Evaluation,
    MinerScore,
    Submission,
    SubmissionStatus,
)


class WeightComputer:
    """Computes miner weights based on submission scores."""

    # Maximum weight value for u16 (used by Bittensor)
    MAX_U16 = 65535

    async def compute_cycle_weights(
        self,
        db: AsyncSession,
        cycle_id: int,
    ) -> dict[int, float]:
        """
        Compute normalized weights for all miners in a cycle.

        Uses sum of scores (rewards both volume and quality).

        Returns:
            Dict mapping miner_uid to weight (0-1, sums to 1)
        """
        # Get all scored submissions with their evaluations
        query = (
            select(Submission, Evaluation)
            .join(Evaluation, Submission.id == Evaluation.submission_id)
            .where(
                Submission.cycle_id == cycle_id,
                Submission.status == SubmissionStatus.SCORED.value,
            )
        )

        result = await db.execute(query)
        rows = result.all()

        if not rows:
            return {}

        # Aggregate scores by miner
        miner_scores: dict[int, list[float]] = defaultdict(list)
        miner_hotkeys: dict[int, str] = {}

        for submission, evaluation in rows:
            miner_scores[submission.miner_uid].append(evaluation.final_score)
            miner_hotkeys[submission.miner_uid] = submission.miner_hotkey

        # Compute totals (sum of scores)
        miner_totals = {uid: sum(scores) for uid, scores in miner_scores.items()}

        # Normalize to weights (sum to 1)
        total = sum(miner_totals.values())
        if total == 0:
            return {}

        weights = {uid: score / total for uid, score in miner_totals.items()}

        # Store miner scores in database
        await self._store_miner_scores(db, cycle_id, miner_scores, miner_hotkeys, weights)

        return weights

    async def _store_miner_scores(
        self,
        db: AsyncSession,
        cycle_id: int,
        miner_scores: dict[int, list[float]],
        miner_hotkeys: dict[int, str],
        weights: dict[int, float],
    ) -> None:
        """Store aggregated miner scores."""
        for uid, scores in miner_scores.items():
            miner_score = MinerScore(
                cycle_id=cycle_id,
                miner_uid=uid,
                miner_hotkey=miner_hotkeys[uid],
                total_submissions=len(scores),
                accepted_submissions=len(scores),  # All scored = accepted
                avg_score=sum(scores) / len(scores) if scores else 0,
                total_score=sum(scores),
            )
            db.add(miner_score)

    async def store_computed_weights(
        self,
        db: AsyncSession,
        cycle_id: int,
        block_number: int,
        weights: dict[int, float],
    ) -> ComputedWeights:
        """
        Store computed weights for validators to fetch.

        Args:
            db: Database session
            cycle_id: Cycle ID
            block_number: Current block number
            weights: Dict mapping miner_uid to weight (0-1)

        Returns:
            ComputedWeights record
        """
        # Convert to u16 format for Bittensor
        uids = list(weights.keys())
        float_weights = [weights[uid] for uid in uids]

        # Scale to u16
        u16_weights = self._float_to_u16(float_weights)

        computed = ComputedWeights(
            cycle_id=cycle_id,
            block_number=block_number,
            weights_json={str(uid): w for uid, w in weights.items()},
            weights_u16_json={
                "uids": uids,
                "weights": u16_weights,
            },
        )
        db.add(computed)
        await db.flush()
        await db.refresh(computed)

        return computed

    def _float_to_u16(self, weights: list[float]) -> list[int]:
        """
        Convert normalized float weights to u16 values.

        Bittensor uses u16 (0-65535) for weight representation.
        """
        if not weights:
            return []

        # Normalize weights to sum to 1 (should already be, but ensure)
        total = sum(weights)
        if total == 0:
            return [0] * len(weights)

        normalized = [w / total for w in weights]

        # Scale to u16
        u16_weights = [int(w * self.MAX_U16) for w in normalized]

        # Handle rounding errors - adjust largest weight
        diff = self.MAX_U16 - sum(u16_weights)
        if diff != 0 and u16_weights:
            max_idx = u16_weights.index(max(u16_weights))
            u16_weights[max_idx] += diff

        return u16_weights

    async def get_latest_weights(
        self,
        db: AsyncSession,
    ) -> ComputedWeights | None:
        """Get the most recently computed weights."""
        query = select(ComputedWeights).order_by(ComputedWeights.created_at.desc()).limit(1)
        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_weights_for_cycle(
        self,
        db: AsyncSession,
        cycle_id: int,
    ) -> ComputedWeights | None:
        """Get weights for a specific cycle."""
        query = select(ComputedWeights).where(ComputedWeights.cycle_id == cycle_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()


def get_weight_computer() -> WeightComputer:
    """Get a weight computer instance."""
    return WeightComputer()
