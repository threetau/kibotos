# Kibotos - Design Doc

## 1. Overview

### Background

Training capable robot manipulation policies at scale requires large quantities of diverse, high-quality demonstration data. Collecting this data through centralized lab pipelines is slow and expensive, which creates a natural opportunity for decentralized, incentivized data collection, where a network of miners capture and submit robot demonstrations in exchange for rewards.

However, decentralized data collection introduces verification challenges that don't exist in controlled settings. Miners may submit low-effort, duplicated, physically implausible, or entirely fabricated demonstrations. Unlike traditional supervised learning datasets where labels can be manually reviewed, kinematic trajectories are high-dimensional and difficult to validate by inspection alone. The reward signal must therefore be grounded in **objective, automated verification** that is robust to a wide range of submission quality and adversarial behavior.

The core tension this system must resolve is that **kinematic action data is inherently noisy**. Even genuine, well-intentioned submissions contain retargeting artifacts, sensor noise, and sync imprecision. A verification system that treats submitted joint angles as perfect ground truth will reject legitimate data and fail to capture meaningful quality gradients. Equally, a system that is too permissive will be gamed by low-effort or synthetic submissions that waste training compute downstream.

### Problem Statement

Given a miner-submitted bundle containing source video and retargeted kinematic trajectories, the system must answer three questions:

1. **Is this data real and intact?** The submission should represent a genuine robot episode, not fabricated, duplicated, edited, or corrupted.
2. **Is this data physically plausible and consistent?** The kinematic trajectory should be consistent with what the video shows, and consistent with the physical constraints of the declared robot model.
3. **Is this data useful for training?** The episode should complete a recognizable task, have sufficient alignment between modalities, and contribute novel information to the dataset.

The system must answer these questions efficiently, at scale, without access to privileged ground truth, and in a way that is resistant to gaming.

### Purpose

This document defines the end-to-end design for verifying miner submissions and rewarding high-quality training data. Each submission contains **source video** paired with **retargeted kinematics**. Verification assesses submissions across four dimensions: **integrity**, **physical plausibility**, **cross-modal alignment**, and **task correctness**.

### Core Principles

The system treats action signals as **noisy labels** rather than ground truth. Verification uses **gating and confidence-weighting** rather than binary pass/fail wherever possible. Key design decisions:

- **IK residual is a confidence metric, not a truth signal.** Hard rejection is reserved only for extreme infeasibility.
- **Provenance is not scored.** Correctness is determined by alignment and task completion evidence.
- **Tagless capture is supported.** Missing optional streams are not penalized.
- **Gates are ordered cheapest-first** to minimize compute on submissions that will be rejected anyway.

### Goal

Accept submissions that are real, task-correct, physically plausible, and useful for training policies. Reward miners based on verified quality and confidence.

---

## 2. Submission Bundle

### Container Format

All submissions are packaged as a **Zarr archive** (the "submission bundle").

### Manifest

The manifest is the authoritative source of metadata for a submission. All fields below are required unless marked optional.

| Path | Type | Description |
|---|---|---|
| `/manifest/schema_version` | string (semver) | Version of the manifest schema |
| `/manifest/bundle_version` | string (semver) | Version of this specific bundle |
| `/manifest/submission_id` | UUID | Unique ID for this submission |
| `/manifest/episode_id` | UUID | Unique ID for the episode |
| `/manifest/miner_id` | string | Submitting miner identity |
| `/manifest/created_at` | ISO 8601 | Submission creation timestamp |
| `/manifest/robot_model_id` | string | Robot model identifier |
| `/manifest/robot_model_revision` | string | Robot model revision |
| `/manifest/joint_names` | string[J] | Ordered list of joint names |
| `/manifest/sampling_rate_hz` | float | Kinematic sampling rate |
| `/manifest/time_base` | string | Must be `"relative"` |
| `/manifest/time_units` | string | Must be `"ms"` |
| `/manifest/units/joint_pos` | string | Must be `"rad"` |
| `/manifest/units/joint_vel` | string | Must be `"rad/s"` |
| `/manifest/camera/primary/intrinsics` | JSON or array | Camera intrinsic parameters |
| `/manifest/camera/primary/extrinsics` | JSON or array | Camera extrinsic parameters |
| `/manifest/video/primary/fps` | float | Video frame rate |
| `/manifest/video/primary/frame_count` | int | Total frame count |
| `/manifest/sync/sync_offset_ms_claimed` | int | Miner-claimed A/V sync offset in ms |

### Kinematic Streams

| Path | Shape | Type | Notes |
|---|---|---|---|
| `/kinematics/timestamps_ms` | (T,) | int64 | Must be strictly increasing |
| `/kinematics/joint_pos` | (T, J) | float32 | Joint positions in radians |
| `/kinematics/joint_vel` | (T, J) | float32 | Joint velocities in rad/s |

> `joint_vel` is optional. If absent, the validator will compute it from `joint_pos` and flag the submission accordingly.

### Video Streams

Choose one approach and use it consistently:

- **Raw frames:** `/video/primary/frames`, shape `(N, H, W, C)`, dtype `uint8`
- **Encoded:** `/video/primary/encoded` (bytes) with accompanying metadata

### Optional Streams

| Path | Description |
|---|---|
| `/video/secondary_*/*` | Additional camera angles |
| `/objects/*` | Object pose streams (tag- or vision-derived) |
| `/imu/*` | IMU data |
| `/torques/*` | Joint torque data |
| `/contacts/*` | Contact state data |
| `/pose/*` | Miner-supplied pose estimation outputs |

### Submission Invariants

Before any gate processing, the following must hold:

- Array shapes for T and J must match manifest declarations.
- No `NaN` or `Inf` values in any numeric array.
- If both `joint_vel` and `joint_pos` are present: `joint_vel ≈ d(joint_pos)/dt` within tolerance.

---

## 3. Miner Capture Pipeline

### Capture Requirements

- Produce source video and kinematics consistent with the declared `robot_model_id` and `revision`.
- Timestamps must be reliable and monotonic. An initial **sync pose** or **sync event** is strongly recommended.
- Camera should be aligned to the task. Egocentric viewpoint is preferred.

### Capture Protocol

| Requirement | Detail |
|---|---|
| Episode completeness | Record from start to finish, no editing or splicing |
| Calibration | Include intrinsics and extrinsics in the manifest |
| Markers/tags | Optional; tagless capture is fully supported |
| Trajectory quality | Smooth joint trajectories, stable framerate, clear viewpoint |

> Prefer action representations that remain useful under noise. Noisy-but-structured data is preferable to clean-but-uninformative data.

---

## 4. Ingestion and Storage

### Upload Flow

- Bundles are uploaded via **presigned URLs** to Zarr storage.
- On receipt, the system stores:
  - Bundle hash tree
  - Manifest hash
  - Submission metadata in the database

### Pre-Verification Integrity Checks

These checks run immediately on upload, before the verification pipeline:

| Check | Action on Failure |
|---|---|
| Hash verification | Reject |
| Size and shape checks | Reject |
| Schema and required field presence | Reject |
| Malformed bundle structure | Reject immediately |

---

## 5. Verification Pipeline

### 5.1 Gate Ordering

Gates are evaluated **cheapest first** to minimize wasted compute on submissions that will ultimately be rejected.

| Order | Gate | Cost |
|---|---|---|
| 1 | Schema / shape / units + NaN/Inf + flatline | Very cheap |
| 2 | Timestamp monotonicity + gaps + duration | Cheap |
| 3 | Video ↔ kinematics overlap + sync sanity | Cheap |
| 4 | Joint limits + basic physical plausibility | Moderate |
| 5 | Pose estimation quality (if validator-computed) | Moderate |
| 6 | IK residual | Expensive |
| 7 | VLM cross-modal alignment | Expensive |
| 8 | Task completion evaluation | Expensive |

---

### 5.2 Hard Gates

A submission is **rejected** if it fails any hard gate. Failures are recorded with a reason code in the verification report.

#### Gate A, Data Integrity and Shapes

- All required datasets must exist.
- Array shapes must match `(T, J)` and `len(joint_names)` from the manifest.
- No `NaN` or `Inf` values anywhere in numeric arrays.
- Reject constant/flatline streams (near-zero variance over more than X% of frames).

#### Gate B, Timestamps

- `timestamps_ms` must be strictly increasing.
- `dt` must be close to the nominal value `1000 / sampling_rate_hz`.

**Reject if any of:**

- Any negative or zero `dt`
- Maximum gap exceeds 200 ms
- Missing samples exceed 5% of the total sequence

#### Gate C, Video ↔ Kinematics Overlap and Sync Sanity

The validator computes:

```
video_duration  = frame_count / fps
kin_duration    = timestamps_ms[-1] - timestamps_ms[0]
```

The validator also independently estimates sync offset:

- `sync_offset_ms_estimated`, via event alignment (e.g., motion-peak correlation, gripper events)
- `sync_confidence`, confidence in the estimate

**Reject if:**

- Overlap < 90% of either stream, **or**
- `|claimed_offset - estimated_offset| > 250 ms` **when** `sync_confidence` is high

Both claimed and estimated offsets (plus confidence) are stored in the verification report.

#### Gate D, Joint Limits and Unit Validity

- Load joint limits for the `(robot_model_id, revision)` pair from the robot model registry.
- Reject submissions with unit mismatches.
- Reject if joint limit violations exceed the tolerance margin.

#### Gate E, Physical Plausibility

Reject extreme implausibility:

- Joint speed, acceleration, or jerk above model-specific bounds for more than X% of frames.
- Positional discontinuities ("teleport" events) beyond the threshold.

> This gate provides the primary protection against noisy-but-useless action labels slipping through.

#### Gate F, Pose Estimation Quality

*Applies only when the validator computes pose/keypoint estimates.*

| Metric | Threshold |
|---|---|
| Mean keypoint confidence | ≥ 0.70 |
| Frames above confidence 0.50 | ≥ 90% |
| Missing frames | ≤ 5% |
| Max continuous dropout | ≤ 200 ms |
| Mean reprojection error (at 720p) | ≤ 5 px |
| p95 reprojection error (at 720p) | ≤ 8 px |

---

### 5.3 IK Residual Gate

**Design intent:** Detect trajectories that are kinematically inconsistent or infeasible, and produce a **confidence signal**. This gate does *not* assume submitted joint angles are perfect ground truth.

> **Important:** IK residual is only meaningful when the IK target is **independent** of the submitted joint stream (e.g., derived from video pose, object state, or task constraints). If the target is derived from the same joints, residuals will be trivially near-zero and uninformative.

#### Computation

Define the desired end-effector / tool pose trajectory `T*_t` from one of:

1. Object pose + grasp constraints + video evidence *(preferred)*
2. Pose-estimation derived end-effector path
3. Task-defined waypoints

Solve IK under constraints (joint limits, smoothness), then compute:

| Metric | Description |
|---|---|
| `rms_pos_error` | RMS position error (meters) |
| `peak_pos_error` | Peak position error (meters) |
| `orientation_error` | Quaternion distance statistics (degrees) |

#### Hard Reject Threshold

Reject only if clearly infeasible:

| Condition | Threshold |
|---|---|
| RMS end-effector position error | > 8 cm |
| Peak end-effector position error | > 12 cm |
| Orientation error | > 30° for more than 15% of frames |

#### Soft Signal

All other IK residuals feed into `S_retarget` as a **soft confidence score**, higher residual means lower confidence, not automatic rejection.

---

## 6. Simulation and Alignment

### Genesis Playback

1. Load the robot model by `(robot_model_id, revision)`.
2. Apply the submitted joint trajectory over time.
3. Render keyframes aligned to video timestamps using `sync_offset_ms_estimated`.

### Keyframe Selection Strategy

| Type | Purpose |
|---|---|
| Uniform sampling | Baseline coverage |
| Motion-peak frames | Capture high-activity moments |
| Task-phase boundaries | Ensure key events are evaluated |

Chosen frame indices are stored in the verification report for auditability.

> Optionally, short clip comparisons around key events may be used in place of single frames to reduce noise.

---

## 7. Scoring and Rewards

### 7.1 Soft Score Components

Each component is normalized to **[0, 1]**.

| Component | Description |
|---|---|
| `S_pose` | Pose confidence, reprojection error, and jitter |
| `S_retarget` | IK residual (as confidence), smoothness, joint limit margins |
| `S_align` | VLM similarity on paired frames/clips + consistency checks |
| `S_task` | Task completion checklist, phase order, and confidence |
| `S_object` | Object state consistency (neutral if stream is missing) |
| `S_novel` | Novelty/duplication score + video quality/viewpoint compliance |

### 7.2 Weights and Missing Stream Handling

**Base weights (tunable):**

| Component | Weight |
|---|---|
| `S_align` | 0.25 |
| `S_task` | 0.20 |
| `S_retarget` | 0.20 |
| `S_pose` | 0.15 |
| `S_object` | 0.10 |
| `S_novel` | 0.10 |

**Missing stream policy:**

- If object streams are absent: treat `S_object` as neutral (0.5), *or* renormalize remaining weights.
- Tagless pipelines are not penalized.

### 7.3 Final Score and Reward Curve

**Final score:**

```
S = Σ (w_i × S_i)    [after missing-stream adjustment]
```

**Reward function:**

```
R = R_base × I(pass_all_hard_gates) + R_scale × f(S)
```

**Piecewise reward shaping `f(S)`:**

| Range | Output |
|---|---|
| `S < 0.30` | 0 |
| `0.30 ≤ S ≤ 0.80` | Linear: 0 → 1 |
| `S > 0.80` | `1 + bonus × (S − 0.80)` |

A small bonus is awarded for high-confidence, high-quality submissions above the 0.80 threshold.

### 7.4 Multi-Angle Bonus

- One primary egocentric stream is required.
- Secondary camera angles add a quality-weighted multiplier.
- No penalty for mono submissions.

```
R *= (1 + k × angle_quality_sum)
```

---

## 8. Novelty and Duplication

### Detection Method

Compute perceptual hashes and embeddings for both video and simulation renders. Compare against:

- **Per-miner recent window**, strong penalty for repeated content from the same miner.
- **Global window**, downweight near-duplicates across all miners.

### Penalized Behaviors

| Behavior | Response |
|---|---|
| Repeated content from same miner | Strong penalty to `S_novel` |
| Low diversity across submissions | Downweighting |
| "Slight perturbation" attempts | Caught via embedding similarity |

---

## 9. Task Schemas

### Schema Fields

Each task is identified by `task_id` and `task_version`, and defines:

| Field | Description |
|---|---|
| Expected phases | Ordered sequence of task phases |
| Success predicates | e.g., object moved to region, grasp detected |
| Tolerances | Time offsets and spatial thresholds |

### VLM as Evidence

The VLM is used to evaluate task completion by:

1. Outputting structured JSON against the task schema.
2. Storing the prompt version, model version, and calibration statistics with each evaluation.

The VLM is treated as a **calibrated instrument**, its outputs are evidence, not ground truth.

---

## 10. Observability and Auditability

### Verification Report

A per-submission **Verification Report** is stored containing:

| Section | Contents |
|---|---|
| Gate results | `{name, pass, metrics, thresholds, reason_code}` for each gate |
| Sync data | `{claimed_offset, estimated_offset, sync_confidence}` |
| Scores | All component scores, weights, and final composite score |
| VLM outputs | Structured JSON + prompt version + model version |
| Frame references | Keyframe indices + references to stored real/sim frame pairs |

### Inspection Tools

A CLI and/or API endpoint allows validators and miners to fetch the full report and all associated artifacts for any episode by `submission_id`.

---

## 11. Security and Abuse Prevention

### Bundle Signing

All bundles are signed by the miner's identity. The signature covers:

- Manifest hash
- All dataset hashes

### Rate Limiting

- Per-miner rate limits are enforced at ingestion.
- Duplicate detection penalties are applied at scoring.

### Synthetic Artifact Detection

| Check | Method |
|---|---|
| Watermarks and overlays | Heuristic detection pass |
| "Render-of-render" artifacts | Sim-like artifact detection heuristics |
| Compression anomalies | Statistical anomaly checks on encoded video |

---

## 12. Open Decisions

The following design decisions have recommended defaults, but are not yet finalized.

| Decision | Default / Status |
|---|---|
| Robot model registry | Versioned canonical list with joint limits and reference frames |
| Calibration handling | Cached per-device + per-submission override + calibration hash |
| Minimum sensor set | Positions + timestamps required; velocities optional (computed + flagged if absent) |
| VLM provider | Freeze model versions; treat as calibrated instrument with fixed prompt versions |
| Reward policy | Piecewise curve with confidence bonuses; not purely linear |
