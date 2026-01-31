"""Scheduler service for cycle management and weight computation."""

import asyncio
from dataclasses import dataclass
from datetime import datetime

from kibotos.db.models import CycleStatus
from kibotos.db.session import get_session
from kibotos.scheduler.cycles import CycleManager, get_cycle_manager
from kibotos.scheduler.weights import WeightComputer, get_weight_computer


@dataclass
class SchedulerConfig:
    """Configuration for the scheduler service."""

    cycle_duration_minutes: int = 60
    check_interval_seconds: int = 30
    auto_start_cycles: bool = True


class SchedulerService:
    """
    Service that manages collection cycles and computes weights.

    Responsibilities:
    - Start new cycles when none is active (if auto_start enabled)
    - Complete cycles when duration is reached
    - Wait for evaluations to finish
    - Compute and store weights when cycle is finalized
    """

    def __init__(
        self,
        config: SchedulerConfig | None = None,
        cycle_manager: CycleManager | None = None,
        weight_computer: WeightComputer | None = None,
    ):
        self.config = config or SchedulerConfig()
        self.cycles = cycle_manager or get_cycle_manager(self.config.cycle_duration_minutes)
        self.weights = weight_computer or get_weight_computer()
        self._running = False

    async def run(self) -> None:
        """Run the scheduler service loop."""
        self._running = True
        print("Scheduler service started")
        print(f"  Cycle duration: {self.config.cycle_duration_minutes} minutes")
        print(f"  Check interval: {self.config.check_interval_seconds} seconds")
        print(f"  Auto-start cycles: {self.config.auto_start_cycles}")

        while self._running:
            try:
                await self._tick()
            except Exception as e:
                print(f"Error in scheduler loop: {e}")

            await asyncio.sleep(self.config.check_interval_seconds)

    def stop(self) -> None:
        """Stop the scheduler service."""
        self._running = False

    async def _tick(self) -> None:
        """Single iteration of the scheduler loop."""
        async with get_session() as db:
            # Check for active cycle
            active_cycle = await self.cycles.get_active_cycle(db)

            if active_cycle:
                # Check if cycle should be completed
                should_complete = await self.cycles.check_cycle_should_complete(db, active_cycle)

                if should_complete:
                    print(f"Completing cycle {active_cycle.id}")
                    await self.cycles.complete_cycle(db, active_cycle.id)
                    await db.commit()
                else:
                    stats = await self.cycles.get_cycle_stats(db, active_cycle.id)
                    print(
                        f"Cycle {active_cycle.id} active: "
                        f"{stats['total_submissions']} submissions, "
                        f"{stats['unique_miners']} miners"
                    )

            else:
                # Check for evaluating cycle
                from sqlalchemy import select

                from kibotos.db.models import CollectionCycle

                query = select(CollectionCycle).where(
                    CollectionCycle.status == CycleStatus.EVALUATING.value
                )
                result = await db.execute(query)
                evaluating_cycle = result.scalar_one_or_none()

                if evaluating_cycle:
                    # Check if evaluations are complete
                    evals_complete = await self.cycles.check_evaluations_complete(
                        db, evaluating_cycle.id
                    )

                    if evals_complete:
                        print(f"Finalizing cycle {evaluating_cycle.id}")
                        await self._finalize_cycle(db, evaluating_cycle.id)
                        await db.commit()
                    else:
                        stats = await self.cycles.get_cycle_stats(db, evaluating_cycle.id)
                        print(
                            f"Cycle {evaluating_cycle.id} evaluating: "
                            f"{stats['pending']} pending, "
                            f"{stats['scored']} scored"
                        )

                elif self.config.auto_start_cycles:
                    # No active or evaluating cycle - start a new one
                    print("Starting new cycle")
                    new_cycle = await self.cycles.start_cycle(db)
                    await db.commit()
                    print(f"Started cycle {new_cycle.id}")

    async def _finalize_cycle(self, db, cycle_id: int) -> None:
        """Finalize a cycle and compute weights."""
        # Compute weights
        weights = await self.weights.compute_cycle_weights(db, cycle_id)

        if weights:
            # Get current block (placeholder - would come from chain)
            block_number = int(datetime.utcnow().timestamp())

            # Store computed weights
            await self.weights.store_computed_weights(
                db, cycle_id, block_number, weights
            )
            print(f"Computed weights for {len(weights)} miners")

        # Finalize the cycle
        await self.cycles.finalize_cycle(db, cycle_id)
        print(f"Cycle {cycle_id} finalized")


async def run_scheduler(
    cycle_duration_minutes: int = 60,
    check_interval_seconds: int = 30,
    auto_start_cycles: bool = True,
) -> None:
    """Run the scheduler service."""
    config = SchedulerConfig(
        cycle_duration_minutes=cycle_duration_minutes,
        check_interval_seconds=check_interval_seconds,
        auto_start_cycles=auto_start_cycles,
    )
    service = SchedulerService(config)

    try:
        await service.run()
    except KeyboardInterrupt:
        service.stop()
        print("Scheduler stopped")
