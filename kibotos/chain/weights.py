"""Bittensor chain integration for weight submission."""

import asyncio
from dataclasses import dataclass


@dataclass
class ChainConfig:
    """Bittensor chain configuration."""

    netuid: int | None
    network: str
    wallet_name: str
    hotkey_name: str


class WeightSubmitter:
    """Submits weights to the Bittensor chain."""

    def __init__(self, config: ChainConfig):
        self.config = config
        self._subtensor = None
        self._wallet = None

    def _init_bittensor(self) -> None:
        """Initialize Bittensor subtensor and wallet."""
        if self._subtensor is not None:
            return

        import bittensor as bt

        # Initialize subtensor
        self._subtensor = bt.subtensor(network=self.config.network)

        # Initialize wallet
        self._wallet = bt.wallet(
            name=self.config.wallet_name,
            hotkey=self.config.hotkey_name,
        )

    async def submit_weights(
        self,
        uids: list[int],
        weights: list[int],
    ) -> bool:
        """
        Submit weights to the Bittensor chain.

        Args:
            uids: List of miner UIDs
            weights: List of weights (u16 values, 0-65535)

        Returns:
            True if submission was successful
        """
        if self.config.netuid is None:
            print("Warning: netuid not set, skipping weight submission")
            return False

        # Run in thread pool since bittensor is synchronous
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self._submit_weights_sync,
            uids,
            weights,
        )

    def _submit_weights_sync(
        self,
        uids: list[int],
        weights: list[int],
    ) -> bool:
        """Synchronous weight submission."""
        try:
            self._init_bittensor()

            import torch

            # Convert to tensors
            uids_tensor = torch.tensor(uids, dtype=torch.int64)
            weights_tensor = torch.tensor(weights, dtype=torch.float32)

            # Normalize weights (Bittensor expects normalized floats)
            weights_tensor = weights_tensor / weights_tensor.sum()

            # Submit weights
            success = self._subtensor.set_weights(
                netuid=self.config.netuid,
                wallet=self._wallet,
                uids=uids_tensor,
                weights=weights_tensor,
                wait_for_inclusion=True,
                wait_for_finalization=False,
            )

            return success

        except Exception as e:
            print(f"Error in weight submission: {e}")
            return False

    async def get_current_block(self) -> int:
        """Get the current block number."""
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self._get_current_block_sync,
        )

    def _get_current_block_sync(self) -> int:
        """Synchronous block fetch."""
        self._init_bittensor()
        return self._subtensor.block

    async def get_metagraph(self) -> dict:
        """Get the metagraph for this subnet."""
        return await asyncio.get_event_loop().run_in_executor(
            None,
            self._get_metagraph_sync,
        )

    def _get_metagraph_sync(self) -> dict:
        """Synchronous metagraph fetch."""
        self._init_bittensor()
        metagraph = self._subtensor.metagraph(netuid=self.config.netuid)
        return {
            "n": metagraph.n.item(),
            "uids": metagraph.uids.tolist(),
            "hotkeys": metagraph.hotkeys,
            "stakes": metagraph.stake.tolist(),
        }


def get_weight_submitter(
    netuid: int | None = None,
    network: str = "test",
    wallet_name: str = "default",
    hotkey_name: str = "default",
) -> WeightSubmitter:
    """Get a weight submitter instance."""
    config = ChainConfig(
        netuid=netuid,
        network=network,
        wallet_name=wallet_name,
        hotkey_name=hotkey_name,
    )
    return WeightSubmitter(config)
