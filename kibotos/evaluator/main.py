"""Evaluator service for processing video submissions."""

import asyncio
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from kibotos.evaluator.relevance import RelevanceEvaluator, get_relevance_evaluator
from kibotos.evaluator.technical import TechnicalValidator, get_technical_validator
from kibotos.storage.s3 import S3Client, get_s3_client


@dataclass
class EvaluationConfig:
    """Configuration for the evaluator service."""

    api_url: str = "http://localhost:8080"
    poll_interval: int = 10  # seconds
    batch_size: int = 5
    n_keyframes: int = 5
    download_timeout: int = 300  # seconds


@dataclass
class PendingSubmission:
    """A submission pending evaluation."""

    id: int
    submission_uuid: str
    prompt_id: str
    video_key: str
    category: str
    task: str
    scenario: str
    requirements: dict


class EvaluatorService:
    """Service that evaluates video submissions."""

    def __init__(
        self,
        config: EvaluationConfig | None = None,
        technical_validator: TechnicalValidator | None = None,
        relevance_evaluator: RelevanceEvaluator | None = None,
        s3_client: S3Client | None = None,
    ):
        self.config = config or EvaluationConfig()
        self.technical = technical_validator or get_technical_validator()
        self.relevance = relevance_evaluator or get_relevance_evaluator()
        self.s3 = s3_client or get_s3_client()
        self._running = False

    async def run(self) -> None:
        """Run the evaluator service loop."""
        self._running = True
        print(f"Evaluator service started. Polling {self.config.api_url}")

        while self._running:
            try:
                # Fetch pending submissions
                submissions = await self._fetch_pending()

                if submissions:
                    print(f"Processing {len(submissions)} submissions")
                    for sub in submissions:
                        await self._process_submission(sub)
                else:
                    print("No pending submissions")

            except Exception as e:
                print(f"Error in evaluator loop: {e}")

            await asyncio.sleep(self.config.poll_interval)

    def stop(self) -> None:
        """Stop the evaluator service."""
        self._running = False

    async def _fetch_pending(self) -> list[PendingSubmission]:
        """Fetch pending submissions from API."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.config.api_url}/v1/evaluate/fetch",
                json={"limit": self.config.batch_size},
                timeout=30.0,
            )

            if response.status_code == 404:
                return []

            response.raise_for_status()
            data = response.json()

            return [
                PendingSubmission(
                    id=s["id"],
                    submission_uuid=s["submission_uuid"],
                    prompt_id=s["prompt_id"],
                    video_key=s["video_key"],
                    category=s["category"],
                    task=s["task"],
                    scenario=s["scenario"],
                    requirements=s.get("requirements", {}),
                )
                for s in data.get("submissions", [])
            ]

    async def _process_submission(self, submission: PendingSubmission) -> None:
        """Process a single submission."""
        print(f"Evaluating submission {submission.submission_uuid}")

        # Create temp directory for video
        with tempfile.TemporaryDirectory(prefix="kibotos_eval_") as temp_dir:
            video_path = Path(temp_dir) / "video.mp4"

            try:
                # Download video from S3
                await self._download_video(submission.video_key, video_path)

                # Run technical validation
                technical_result = await self.technical.validate(
                    video_path,
                    submission.requirements,
                )

                if not technical_result.passed:
                    # Submit rejection
                    await self._submit_result(
                        submission_id=submission.id,
                        technical_score=technical_result.score,
                        relevance_score=0.0,
                        quality_score=0.0,
                        final_score=0.0,
                        rejection_reason=f"Technical validation failed: {technical_result.error or technical_result.checks}",
                        metadata={
                            "technical_checks": technical_result.checks,
                            "video_metadata": self._metadata_to_dict(technical_result.metadata),
                        },
                    )
                    return

                # Run relevance evaluation
                relevance_result = await self.relevance.evaluate(
                    video_path=str(video_path),
                    category=submission.category,
                    task=submission.task,
                    scenario=submission.scenario,
                    n_frames=self.config.n_keyframes,
                )

                # Compute final score
                # Technical: 20%, Relevance: 50%, Quality: 30% (quality is 1.0 for now)
                quality_score = 1.0  # TODO: Implement quality checks (duplicate detection, etc.)
                final_score = (
                    0.2 * technical_result.score
                    + 0.5 * relevance_result.score
                    + 0.3 * quality_score
                )

                # Submit result
                await self._submit_result(
                    submission_id=submission.id,
                    technical_score=technical_result.score,
                    relevance_score=relevance_result.score,
                    quality_score=quality_score,
                    final_score=round(final_score, 4),
                    rejection_reason=None,
                    metadata={
                        "technical_checks": technical_result.checks,
                        "video_metadata": self._metadata_to_dict(technical_result.metadata),
                        "relevance_scores": {
                            "action_match": relevance_result.scores.action_match,
                            "perspective_correct": relevance_result.scores.perspective_correct,
                            "demonstration_quality": relevance_result.scores.demonstration_quality,
                            "training_utility": relevance_result.scores.training_utility,
                        },
                        "relevance_reasoning": relevance_result.reasoning,
                    },
                )

                print(f"Submission {submission.submission_uuid} scored {final_score:.4f}")

            except Exception as e:
                print(f"Error processing {submission.submission_uuid}: {e}")
                # Submit error result
                await self._submit_result(
                    submission_id=submission.id,
                    technical_score=0.0,
                    relevance_score=0.0,
                    quality_score=0.0,
                    final_score=0.0,
                    rejection_reason=f"Evaluation error: {str(e)}",
                    metadata={"error": str(e)},
                )

    async def _download_video(self, video_key: str, output_path: Path) -> None:
        """Download video from S3."""
        download_url = self.s3.generate_presigned_download(video_key)

        async with httpx.AsyncClient() as client:
            response = await client.get(
                download_url,
                timeout=self.config.download_timeout,
                follow_redirects=True,
            )
            response.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(response.content)

    async def _submit_result(
        self,
        submission_id: int,
        technical_score: float,
        relevance_score: float,
        quality_score: float,
        final_score: float,
        rejection_reason: str | None,
        metadata: dict,
    ) -> None:
        """Submit evaluation result to API."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.config.api_url}/v1/evaluate/submit",
                json={
                    "submission_id": submission_id,
                    "technical_score": technical_score,
                    "relevance_score": relevance_score,
                    "quality_score": quality_score,
                    "final_score": final_score,
                    "rejection_reason": rejection_reason,
                    "metadata": metadata,
                },
                timeout=30.0,
            )
            response.raise_for_status()

    def _metadata_to_dict(self, metadata) -> dict | None:
        """Convert video metadata to dict."""
        if metadata is None:
            return None
        return {
            "duration_sec": metadata.duration_sec,
            "width": metadata.width,
            "height": metadata.height,
            "fps": metadata.fps,
            "codec": metadata.codec,
            "format": metadata.format,
            "file_size_bytes": metadata.file_size_bytes,
            "has_audio": metadata.has_audio,
        }


async def run_evaluator(
    api_url: str = "http://localhost:8080",
    poll_interval: int = 10,
    batch_size: int = 5,
) -> None:
    """Run the evaluator service."""
    config = EvaluationConfig(
        api_url=api_url,
        poll_interval=poll_interval,
        batch_size=batch_size,
    )
    service = EvaluatorService(config)

    try:
        await service.run()
    except KeyboardInterrupt:
        service.stop()
        print("Evaluator stopped")
