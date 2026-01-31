# Backend Operator Guide

This guide covers running the Kibotos backend services: API, Evaluator, and Scheduler.

## Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│     API     │     │  Scheduler  │     │  Evaluator  │
│   :8080     │     │             │     │             │
└──────┬──────┘     └──────┬──────┘     └──────┬──────┘
       │                   │                   │
       └───────────────────┼───────────────────┘
                           │
                    ┌──────▼──────┐
                    │  PostgreSQL │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │     S3      │
                    └─────────────┘
```

- **API**: REST endpoints for miners, validators, and admin operations
- **Scheduler**: Manages collection cycles and computes weights
- **Evaluator**: Processes video submissions (technical + VLM analysis)

## Prerequisites

- PostgreSQL 14+
- S3-compatible storage (AWS S3, MinIO, etc.)
- ffmpeg/ffprobe installed
- Chutes.ai API key (for VLM evaluation)

## Installation

```bash
# Clone and install
git clone <repo>
cd robot-data-subnet
uv sync

# Copy environment template
cp .env.example .env
```

## Configuration

Edit `.env` with your settings:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://kibotos:secret@localhost:5432/kibotos

# S3 Storage
S3_BUCKET=kibotos-videos
S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret

# VLM API (Chutes.ai)
VLM_API_URL=https://llm.chutes.ai/v1
VLM_API_KEY=your-chutes-api-key
VLM_MODEL=Qwen/Qwen2.5-VL-72B-Instruct-TEE

# Bittensor (for scheduler block tracking)
NETUID=<your-subnet-id>
NETWORK=finney
```

## Database Setup

```bash
# Create PostgreSQL database
sudo -u postgres psql -c "CREATE USER kibotos WITH PASSWORD 'secret';"
sudo -u postgres psql -c "CREATE DATABASE kibotos OWNER kibotos;"

# Initialize tables
uv run kibotos db init
```

To reset the database (WARNING: deletes all data):

```bash
uv run kibotos db reset --force
```

## Running Services

### API Server

The API server handles all HTTP requests from miners and validators.

```bash
uv run kibotos api --port 8080
```

Options:
- `--host`: Bind address (default: 0.0.0.0)
- `--port`: Port number (default: 8000)
- `--reload`: Enable auto-reload for development

For production, use a process manager:

```bash
# Using systemd
[Unit]
Description=Kibotos API
After=network.target postgresql.service

[Service]
Type=simple
User=kibotos
WorkingDirectory=/opt/kibotos
ExecStart=/opt/kibotos/.venv/bin/kibotos api --port 8080
Restart=always

[Install]
WantedBy=multi-user.target
```

### Scheduler

The scheduler manages collection cycles and computes miner weights.

```bash
uv run kibotos scheduler \
    --cycle-duration 60 \
    --check-interval 30
```

Options:
- `--cycle-duration`: Cycle length in minutes (default: 60)
- `--check-interval`: How often to check cycle status in seconds (default: 30)
- `--no-auto-start`: Disable automatic cycle creation

The scheduler:
1. Starts a new cycle when none is active
2. Completes the cycle after `cycle-duration` minutes
3. Waits for all evaluations to finish
4. Computes and stores miner weights
5. Repeats

### Evaluator

The evaluator processes pending video submissions.

```bash
uv run kibotos evaluator \
    --api-url http://localhost:8080 \
    --poll-interval 10 \
    --batch-size 5
```

Options:
- `--api-url`: Backend API URL
- `--poll-interval`: Seconds between polling for work (default: 10)
- `--batch-size`: Submissions to process per batch (default: 5)

The evaluator:
1. Fetches pending submissions from API
2. Downloads video from S3
3. Runs technical validation (ffprobe)
4. Extracts keyframes and runs VLM analysis
5. Computes final score and submits result

You can run multiple evaluator instances for horizontal scaling.

## API Endpoints

### Health & Status

| Endpoint | Description |
|----------|-------------|
| `GET /health` | Health check |
| `GET /v1/status` | Backend status |
| `GET /v1/cycles/status` | Current cycle information |

### Prompts (Admin)

| Endpoint | Description |
|----------|-------------|
| `GET /v1/prompts` | List active prompts |
| `GET /v1/prompts/{id}` | Get prompt details |
| `GET /v1/prompts/categories` | List categories with counts |
| `POST /v1/admin/prompts` | Create new prompt |

### Submissions

| Endpoint | Description |
|----------|-------------|
| `POST /v1/upload/presign` | Get S3 upload URL |
| `POST /v1/submissions` | Submit video metadata |
| `GET /v1/submissions/{uuid}` | Get submission status |

### Evaluation (Internal)

| Endpoint | Description |
|----------|-------------|
| `POST /v1/evaluate/fetch` | Get pending submissions |
| `POST /v1/evaluate/submit` | Submit evaluation results |

### Scores & Weights

| Endpoint | Description |
|----------|-------------|
| `GET /v1/scores/latest` | Latest cycle scores |
| `GET /v1/scores/{cycle_id}` | Scores for specific cycle |
| `GET /v1/weights/latest` | Latest computed weights |
| `GET /v1/weights/{cycle_id}` | Weights for specific cycle |

## Creating Prompts

Prompts define what videos miners should submit. Create them via API:

```bash
curl -X POST http://localhost:8080/v1/admin/prompts \
  -H "Content-Type: application/json" \
  -d '{
    "id": "manip-001",
    "category": "manipulation",
    "task": "grasp",
    "scenario": "Pick up a mug from a table using one hand",
    "requirements": {
      "min_duration": 5,
      "max_duration": 60
    },
    "weight": 1.0
  }'
```

### Prompt Categories

- `manipulation`: Grasping, placing, pouring, tool use
- `locomotion`: Walking, stairs, terrain navigation
- `navigation`: Indoor/outdoor movement
- `household`: Kitchen, cleaning, organizing tasks
- `industrial`: Warehouse, assembly, logistics

## Monitoring

### Cycle Status

```bash
curl http://localhost:8080/v1/cycles/status
```

Returns:
```json
{
  "active_cycle_id": 5,
  "active_cycle_started_at": "2024-01-15T10:00:00Z",
  "evaluating_cycle_id": null,
  "last_completed_cycle_id": 4,
  "total_cycles": 5
}
```

### Submission Stats

Check pending evaluations:

```bash
curl http://localhost:8080/v1/evaluate/fetch -X POST \
  -H "Content-Type: application/json" \
  -d '{"limit": 0}'
```

### Logs

All services log to stdout. Use your process manager to capture logs:

```bash
# View API logs
journalctl -u kibotos-api -f

# View evaluator logs
journalctl -u kibotos-evaluator -f
```

## Scaling

### Horizontal Scaling

- **API**: Run multiple instances behind a load balancer
- **Evaluator**: Run multiple instances (they coordinate via database)
- **Scheduler**: Single instance only (manages global state)

### Database

For high load:
- Add read replicas for API queries
- Tune PostgreSQL connection pool
- Consider partitioning submissions table by cycle

### S3

- Use CloudFront or similar CDN for video downloads
- Set appropriate lifecycle policies for old videos

## Troubleshooting

### Database Connection Issues

```bash
# Test connection
psql $DATABASE_URL -c "SELECT 1"

# Check pool exhaustion
SELECT count(*) FROM pg_stat_activity WHERE datname = 'kibotos';
```

### Evaluator Not Processing

1. Check VLM API key is valid
2. Verify ffprobe is installed: `which ffprobe`
3. Check S3 credentials can download videos
4. Look for errors in evaluator logs

### Weights Not Computing

1. Ensure scheduler is running
2. Check cycle has completed (status = EVALUATING)
3. Verify all submissions are evaluated (no PENDING status)
4. Check scheduler logs for errors
