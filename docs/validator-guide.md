# Validator Guide

This guide covers running a Kibotos validator to submit miner weights to the Bittensor chain.

## Overview

As a validator, you:
1. Run the validator service that polls the backend for computed weights
2. Submit weights to the Bittensor chain
3. Earn validator rewards for participation

The actual evaluation work is done by the backend (API + Evaluator + Scheduler). Validators simply fetch the computed weights and submit them on-chain.

## Architecture

```
┌─────────────────┐         ┌─────────────────┐
│    Validator    │ ──GET── │  Backend API    │
│    Service      │ weights │  /v1/weights    │
└────────┬────────┘         └─────────────────┘
         │
         │ set_weights()
         ▼
┌─────────────────┐
│   Bittensor     │
│     Chain       │
└─────────────────┘
```

## Prerequisites

- Bittensor wallet with validator hotkey
- Sufficient stake to be a validator on the subnet
- Access to the Kibotos backend API

## Installation

```bash
git clone <repo>
cd robot-data-subnet
uv sync
```

## Wallet Setup

If you don't have a wallet:

```bash
# Create wallet
btcli wallet new_coldkey --wallet.name validator

# Create hotkey
btcli wallet new_hotkey --wallet.name validator --wallet.hotkey default

# Register on subnet (requires TAO)
btcli subnet register --wallet.name validator --wallet.hotkey default --netuid <NETUID>
```

## Running the Validator

```bash
uv run kibotos validate \
    --backend-url http://api.kibotos.example.com:8080 \
    --netuid <SUBNET_UID> \
    --network finney \
    --wallet-name validator \
    --hotkey-name default \
    --poll-interval 60
```

### Options

| Option | Description | Default |
|--------|-------------|---------|
| `--backend-url` | Kibotos API URL | http://localhost:8080 |
| `--netuid` | Subnet UID | None (required) |
| `--network` | Bittensor network | test |
| `--wallet-name` | Wallet name | default |
| `--hotkey-name` | Hotkey name | default |
| `--poll-interval` | Seconds between weight checks | 60 |

### Example Output

```
Starting validator service
  Backend: http://api.kibotos.example.com:8080
  Network: finney
  Netuid: 42
  Wallet: validator/default
  Poll interval: 60s

Validator service started
No weights available yet
No weights available yet
Submitting weights for cycle 5: 12 miners
Successfully submitted weights for cycle 5
Already submitted weights for cycle 5
Already submitted weights for cycle 5
Submitting weights for cycle 6: 15 miners
Successfully submitted weights for cycle 6
```

## Production Setup

### Systemd Service

Create `/etc/systemd/system/kibotos-validator.service`:

```ini
[Unit]
Description=Kibotos Validator
After=network.target

[Service]
Type=simple
User=validator
WorkingDirectory=/home/validator/kibotos
Environment=PATH=/home/validator/kibotos/.venv/bin:/usr/bin
ExecStart=/home/validator/kibotos/.venv/bin/kibotos validate \
    --backend-url http://api.kibotos.example.com:8080 \
    --netuid 42 \
    --network finney \
    --wallet-name validator \
    --hotkey-name default \
    --poll-interval 60
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable kibotos-validator
sudo systemctl start kibotos-validator
```

### Monitoring

View logs:

```bash
journalctl -u kibotos-validator -f
```

Check status:

```bash
systemctl status kibotos-validator
```

## Weight Submission

### How Weights Are Computed

1. **Collection Cycle**: Miners submit videos for ~1 hour
2. **Evaluation**: Backend evaluates all submissions
3. **Scoring**: Each submission gets a score (0-1)
4. **Aggregation**: Miner scores are summed per cycle
5. **Normalization**: Scores normalized to weights (sum to 1)
6. **u16 Conversion**: Weights converted to 0-65535 range

### Weight Formula

```
miner_total = sum(submission_scores)
weight = miner_total / sum(all_miner_totals)
```

This rewards both quality and volume - more high-quality submissions = more weight.

### Fetching Weights Manually

Check current weights via API:

```bash
curl http://api.kibotos.example.com:8080/v1/weights/latest
```

Response:

```json
{
  "cycle_id": 5,
  "block_number": 1234567,
  "created_at": "2024-01-15T11:00:00Z",
  "weights": {
    "123": 0.25,
    "456": 0.35,
    "789": 0.40
  },
  "weights_u16": {
    "uids": [123, 456, 789],
    "weights": [16384, 22938, 26213]
  }
}
```

## Cycle Information

Check cycle status:

```bash
curl http://api.kibotos.example.com:8080/v1/cycles/status
```

Response:

```json
{
  "active_cycle_id": 6,
  "active_cycle_started_at": "2024-01-15T11:00:00Z",
  "evaluating_cycle_id": null,
  "last_completed_cycle_id": 5,
  "total_cycles": 6
}
```

### Cycle States

| State | Description |
|-------|-------------|
| ACTIVE | Accepting submissions |
| EVALUATING | Processing submissions, computing weights |
| COMPLETED | Weights ready for submission |

## Troubleshooting

### "No weights available yet"

- Backend hasn't completed any cycles yet
- Wait for first cycle to complete (~1 hour)

### "Failed to submit weights"

1. Check wallet has sufficient balance for transaction fees
2. Verify hotkey is registered on subnet
3. Confirm netuid is correct
4. Check Bittensor network connectivity

```bash
# Test Bittensor connection
btcli subnet list --network finney
```

### "Already submitted weights for cycle X"

Normal behavior - validator only submits once per cycle to avoid redundant transactions.

### Connection Refused

```
Error fetching weights: Connection refused
```

- Verify backend URL is correct
- Check backend API is running
- Confirm network connectivity to backend

### Wallet Not Found

```
Error: Wallet not found
```

- Check wallet name and hotkey name are correct
- Verify wallet files exist in `~/.bittensor/wallets/`

## Security Considerations

1. **Protect your coldkey**: Never expose coldkey on validator machine
2. **Use dedicated hotkey**: Create a separate hotkey for validation
3. **Firewall**: Restrict inbound connections to validator
4. **Updates**: Keep validator software updated

## Multiple Validators

You can run multiple validators pointing to the same backend. Each will:
- Independently poll for weights
- Submit to chain (redundant but harmless)
- Track which cycles they've submitted

For efficiency, coordinate with other validators to avoid duplicate submissions.

## API Reference

### Get Latest Weights

```bash
GET /v1/weights/latest
```

### Get Weights for Cycle

```bash
GET /v1/weights/{cycle_id}
```

### Get Cycle Status

```bash
GET /v1/cycles/status
```

### Get Miner Scores

```bash
GET /v1/scores/latest
GET /v1/scores/{cycle_id}
```

Response includes per-miner breakdown:

```json
{
  "cycle_id": 5,
  "status": "COMPLETED",
  "n_submissions": 45,
  "miner_scores": [
    {
      "miner_uid": 123,
      "miner_hotkey": "5F3sa...",
      "total_submissions": 4,
      "accepted_submissions": 4,
      "avg_score": 0.82,
      "total_score": 3.28
    }
  ]
}
```
