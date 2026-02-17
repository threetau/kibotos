# Kibotos

Bittensor subnet for robot video data collection. Miners submit first-person video data of physical tasks, validators assess quality via automated pipelines, and high-quality training data is aggregated for robotics foundation models.

[Project Design Doc](./docs/design-doc.md)

> [!WARNING]  
> This sub-subnet is under development and not usable in its current form.

## Overview

- **Miners** record and submit first-person videos matching requested prompts
- **Evaluators** automatically score videos (technical quality + VLM-based relevance)
- **Validators** submit miner weights to the Bittensor chain
- **Backend** orchestrates cycles, manages prompts, and computes weights

## Quick Start

```bash
# Install
uv sync

# Configure
cp .env.example .env
# Edit .env with your settings

# Initialize database
uv run kibotos db init

# Start services
uv run kibotos api --port 8080
uv run kibotos scheduler
uv run kibotos evaluator
```

## Documentation

| Guide | Description |
|-------|-------------|
| [Backend Guide](docs/backend-guide.md) | Running API, Scheduler, Evaluator |
| [Miner Guide](docs/miner-guide.md) | Submitting videos |
| [Validator Guide](docs/validator-guide.md) | Running validator, submitting weights |
| [PLAN.md](PLAN.md) | Architecture and implementation details |

## CLI Commands

```bash
# Backend services
kibotos api           # Start API server
kibotos scheduler     # Start scheduler (cycle management)
kibotos evaluator     # Start evaluator (video scoring)
kibotos validate      # Start validator (weight submission)

# Database
kibotos db init       # Initialize tables
kibotos db reset      # Reset database (caution!)

# Miner operations
kibotos miner prompts       # List active prompts
kibotos miner upload        # Upload video to S3
kibotos miner submit        # Submit video metadata
kibotos miner submit-video  # Upload + submit in one step
kibotos miner status        # Check submission status
```

## Configuration

Key environment variables (see `.env.example`):

```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/kibotos

# S3 Storage
S3_BUCKET=kibotos-videos
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...

# VLM (Chutes.ai)
VLM_API_URL=https://llm.chutes.ai/v1
VLM_API_KEY=...
VLM_MODEL=Qwen/Qwen2.5-VL-72B-Instruct-TEE

# Bittensor
NETUID=...
NETWORK=finney
```

## Architecture

```
Miners ──► API ◄── Validators
             │
    ┌────────┼────────┐
    ▼        ▼        ▼
Scheduler  PostgreSQL  S3
    │                  │
    └──► Evaluator ◄───┘
             │
             ▼
           VLM
```

## License

MIT
