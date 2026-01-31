# Miner Guide

This guide covers how to participate in Kibotos as a miner by submitting robot training videos.

## Overview

As a miner, you:
1. Browse available prompts (video requests)
2. Record videos matching the prompt requirements
3. Upload videos and submit metadata
4. Earn rewards based on video quality and relevance

## Prerequisites

- Bittensor wallet with hotkey registered on the subnet
- ffmpeg/ffprobe installed (for video metadata extraction)
- Videos recorded from first-person/robot perspective

## Installation

```bash
git clone <repo>
cd robot-data-subnet
uv sync
```

## Configuration

Set the API URL (get this from subnet operator):

```bash
export KIBOTOS_API_URL=http://api.kibotos.example.com:8080
```

## Workflow

### 1. Browse Prompts

List all active prompts:

```bash
uv run kibotos miner prompts --api-url $KIBOTOS_API_URL
```

Filter by category:

```bash
uv run kibotos miner prompts --api-url $KIBOTOS_API_URL --category manipulation
```

Example output:

```
┌─────────────┬──────────────┬────────┬─────────────────────────────────┬─────────────┐
│ ID          │ Category     │ Task   │ Scenario                        │ Submissions │
├─────────────┼──────────────┼────────┼─────────────────────────────────┼─────────────┤
│ manip-001   │ manipulation │ grasp  │ Pick up a mug from a table      │ 12          │
│ manip-002   │ manipulation │ pour   │ Pour water from bottle to glass │ 5           │
│ loco-001    │ locomotion   │ walk   │ Walk up a flight of stairs      │ 8           │
└─────────────┴──────────────┴────────┴─────────────────────────────────┴─────────────┘
```

### 2. Record Video

Record a video that matches the prompt requirements:

**Camera Types:**
- `ego_head`: Head-mounted camera (first-person view)
- `ego_chest`: Chest-mounted camera
- `ego_wrist`: Wrist-mounted camera
- `robot_head`: Robot's head camera
- `robot_wrist`: Robot's end-effector camera

**Actor Types:**
- `human`: Human performing the task
- `robot`: Robot performing the task
- `human_with_robot`: Human teleoperating a robot

**Video Requirements:**
- Format: MP4, WebM, MOV, AVI, or MKV
- Codec: H.264, H.265, VP8, VP9, or AV1
- Resolution: Minimum 480x360
- FPS: 15-120 fps
- Duration: 1-300 seconds (check prompt for specific requirements)
- Max size: 500 MB

### 3. Submit Video

#### Option A: One-Step Submit (Recommended)

Upload and submit in one command:

```bash
uv run kibotos miner submit-video ./my_video.mp4 \
    --api-url $KIBOTOS_API_URL \
    --prompt-id manip-001 \
    --miner-uid 123 \
    --miner-hotkey 5F3sa2TJAWMqDhXG6jhV4N8ko9rUjC2q7z... \
    --camera-type ego_head \
    --actor-type human \
    --action "Picked up ceramic mug with right hand"
```

#### Option B: Two-Step Submit

First, upload the video:

```bash
uv run kibotos miner upload ./my_video.mp4 --api-url $KIBOTOS_API_URL
```

Output:
```
Extracting video metadata...
  Duration: 12.5s
  Resolution: 1920x1080
  FPS: 30.0
  Size: 45.2 MB
Uploading to S3...
Upload complete!
  Video key: uploads/abc123/my_video.mp4
  Video hash: 7f83b1657ff1fc53b92dc18148a1d65d...

Use these values to submit:
  --video-key 'uploads/abc123/my_video.mp4'
  --video-hash '7f83b1657ff1fc53b92dc18148a1d65d...'
```

Then submit the metadata:

```bash
uv run kibotos miner submit \
    --api-url $KIBOTOS_API_URL \
    --video-key 'uploads/abc123/my_video.mp4' \
    --video-hash '7f83b1657ff1fc53b92dc18148a1d65d...' \
    --prompt-id manip-001 \
    --miner-uid 123 \
    --miner-hotkey 5F3sa2TJAWMqDhXG6jhV4N8ko9rUjC2q7z... \
    --camera-type ego_head \
    --actor-type human \
    --duration 12.5 \
    --width 1920 \
    --height 1080 \
    --fps 30.0 \
    --action "Picked up ceramic mug with right hand"
```

### 4. Check Status

Monitor your submission:

```bash
uv run kibotos miner status <submission-uuid> --api-url $KIBOTOS_API_URL
```

Output:
```
Submission abc123-def456-...
  Prompt: manip-001
  Status: SCORED
  Submitted: 2024-01-15T10:30:00Z
  Evaluated: 2024-01-15T10:32:15Z

Evaluation
  Technical: 0.95
  Relevance: 0.82
  Quality: 1.0
  Final: 0.875
```

### Submission Statuses

| Status | Description |
|--------|-------------|
| `PENDING` | Waiting to be evaluated |
| `EVALUATING` | Currently being processed |
| `SCORED` | Successfully evaluated |
| `REJECTED` | Failed evaluation (see rejection reason) |

## Scoring System

Your final score is computed as:

```
Final Score = 0.2 × Technical + 0.5 × Relevance + 0.3 × Quality
```

### Technical Score (20%)

Automated checks:
- Valid video format and codec
- Meets resolution requirements
- FPS within acceptable range
- Duration within prompt limits
- File not corrupted

### Relevance Score (50%)

VLM-based analysis of video content:
- **Action Match (40%)**: Does the video show the requested action?
- **Perspective (20%)**: Is it first-person/robot viewpoint?
- **Demonstration Quality (20%)**: Is the action clear and complete?
- **Training Utility (20%)**: Would this help train a robot?

### Quality Score (30%)

Currently checks for:
- Duplicate submissions (penalized)
- Future: synthetic video detection

## Tips for High Scores

### Recording

1. **Clear framing**: Keep the action centered and visible
2. **Good lighting**: Ensure the scene is well-lit
3. **Steady camera**: Minimize shake (use stabilization if available)
4. **Complete action**: Show the full task from start to finish
5. **First-person view**: Use head or wrist-mounted cameras

### Submission

1. **Match the prompt**: Read the scenario carefully
2. **Accurate metadata**: Use correct camera/actor types
3. **Descriptive action**: Briefly describe what happens
4. **Check requirements**: Some prompts have specific duration limits

### What to Avoid

- Third-person views (unless specifically requested)
- Partial actions (cut off before completion)
- Blurry or dark footage
- Unrelated content
- Previously submitted videos (duplicates)

## Rate Limits

- **4 submissions per hour** per miner
- Plan your submissions accordingly

## Troubleshooting

### Upload Fails

```
Error: Failed to get presigned URL
```
- Check API URL is correct
- Verify API server is running

### Video Rejected - Technical

```
Rejected: Technical validation failed
```
- Check video format is supported
- Verify resolution meets minimum (480x360)
- Ensure duration is within limits

### Video Rejected - Relevance

```
Final: 0.15 (low relevance)
```
- Video content didn't match prompt
- Wrong perspective (e.g., third-person instead of first-person)
- Action not clearly visible

### ffprobe Not Found

```
Error: ffprobe not found
```
Install ffmpeg:
```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# macOS
brew install ffmpeg
```

## API Reference

For direct API access:

```bash
# List prompts
curl $KIBOTOS_API_URL/v1/prompts

# Get presigned upload URL
curl -X POST $KIBOTOS_API_URL/v1/upload/presign \
  -H "Content-Type: application/json" \
  -d '{"filename": "video.mp4", "content_type": "video/mp4"}'

# Submit metadata
curl -X POST $KIBOTOS_API_URL/v1/submissions \
  -H "Content-Type: application/json" \
  -d '{
    "prompt_id": "manip-001",
    "video_key": "uploads/abc/video.mp4",
    "video_hash": "sha256...",
    "miner_uid": 123,
    "miner_hotkey": "5F3sa...",
    "signature": "sig...",
    "duration_sec": 12.5,
    "resolution_width": 1920,
    "resolution_height": 1080,
    "fps": 30.0,
    "camera_type": "ego_head",
    "actor_type": "human"
  }'

# Check status
curl $KIBOTOS_API_URL/v1/submissions/<uuid>
```
