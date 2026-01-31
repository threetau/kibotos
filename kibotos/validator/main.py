"""Validator service for submitting weights to Bittensor chain."""

import asyncio
from dataclasses import dataclass

import httpx

from kibotos.chain.weights import WeightSubmitter, get_weight_submitter


@dataclass
class ValidatorConfig:
    """Configuration for the validator service."""

    backend_url: str = "http://localhost:8080"
    netuid: int | None = None
    network: str = "test"
    wallet_name: str = "default"
    hotkey_name: str = "default"
    poll_interval: int = 60  # seconds
    min_interval_blocks: int = 100  # Minimum blocks between weight sets


class ValidatorService:
    """
    Service that fetches weights from backend and submits to chain.

    Validators poll the backend API for computed weights and submit
    them to the Bittensor chain.
    """

    def __init__(
        self,
        config: ValidatorConfig,
        weight_submitter: WeightSubmitter | None = None,
    ):
        self.config = config
        self.submitter = weight_submitter or get_weight_submitter(
            netuid=config.netuid,
            network=config.network,
            wallet_name=config.wallet_name,
            hotkey_name=config.hotkey_name,
        )
        self._running = False
        self._last_submitted_cycle: int | None = None

    async def run(self) -> None:
        """Run the validator service loop."""
        self._running = True
        print("Validator service started")
        print(f"  Backend: {self.config.backend_url}")
        print(f"  Network: {self.config.network}")
        print(f"  Netuid: {self.config.netuid}")
        print(f"  Poll interval: {self.config.poll_interval}s")

        while self._running:
            try:
                await self._tick()
            except Exception as e:
                print(f"Error in validator loop: {e}")

            await asyncio.sleep(self.config.poll_interval)

    def stop(self) -> None:
        """Stop the validator service."""
        self._running = False

    async def _tick(self) -> None:
        """Single iteration of the validator loop."""
        # Fetch latest weights from backend
        weights_data = await self._fetch_weights()

        if not weights_data:
            print("No weights available yet")
            return

        cycle_id = weights_data["cycle_id"]

        # Check if we already submitted for this cycle
        if self._last_submitted_cycle == cycle_id:
            print(f"Already submitted weights for cycle {cycle_id}")
            return

        # Extract weights in u16 format
        uids = weights_data["weights_u16"]["uids"]
        weights = weights_data["weights_u16"]["weights"]

        if not uids:
            print("No miners to set weights for")
            return

        print(f"Submitting weights for cycle {cycle_id}: {len(uids)} miners")

        # Submit to chain
        try:
            success = await self.submitter.submit_weights(uids, weights)

            if success:
                self._last_submitted_cycle = cycle_id
                print(f"Successfully submitted weights for cycle {cycle_id}")
            else:
                print(f"Failed to submit weights for cycle {cycle_id}")

        except Exception as e:
            print(f"Error submitting weights: {e}")

    async def _fetch_weights(self) -> dict | None:
        """Fetch latest weights from backend API."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.config.backend_url}/v1/weights/latest",
                    timeout=30.0,
                )

                if response.status_code == 404:
                    return None

                response.raise_for_status()
                return response.json()

        except httpx.HTTPError as e:
            print(f"Error fetching weights: {e}")
            return None


async def run_validator(
    backend_url: str = "http://localhost:8080",
    netuid: int | None = None,
    network: str = "test",
    wallet_name: str = "default",
    hotkey_name: str = "default",
    poll_interval: int = 60,
) -> None:
    """Run the validator service."""
    config = ValidatorConfig(
        backend_url=backend_url,
        netuid=netuid,
        network=network,
        wallet_name=wallet_name,
        hotkey_name=hotkey_name,
        poll_interval=poll_interval,
    )
    service = ValidatorService(config)

    try:
        await service.run()
    except KeyboardInterrupt:
        service.stop()
        print("Validator stopped")
