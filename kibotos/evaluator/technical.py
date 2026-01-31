"""Technical validation of video files using ffprobe."""

import asyncio
import json
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass
class VideoMetadata:
    """Extracted video metadata."""

    duration_sec: float
    width: int
    height: int
    fps: float
    codec: str
    format: str
    file_size_bytes: int
    has_audio: bool
    bit_rate: int | None = None


@dataclass
class TechnicalResult:
    """Result of technical validation."""

    passed: bool
    score: float
    checks: dict[str, bool]
    metadata: VideoMetadata | None
    error: str | None = None


class TechnicalValidator:
    """Validates video files meet technical requirements."""

    # Acceptable video formats and codecs
    VALID_FORMATS = {"mp4", "webm", "mov", "avi", "mkv"}
    VALID_CODECS = {"h264", "h265", "hevc", "vp8", "vp9", "av1"}

    # Default requirements
    DEFAULT_REQUIREMENTS = {
        "min_width": 480,
        "min_height": 360,
        "min_fps": 15,
        "max_fps": 120,
        "min_duration": 1,
        "max_duration": 300,
        "max_file_size_mb": 500,
    }

    def __init__(self):
        self._ffprobe_path = shutil.which("ffprobe")
        if not self._ffprobe_path:
            raise RuntimeError("ffprobe not found. Please install ffmpeg.")

    async def extract_metadata(self, video_path: str | Path) -> VideoMetadata:
        """Extract metadata from a video file using ffprobe."""
        video_path = Path(video_path)

        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        cmd = [
            self._ffprobe_path,
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"ffprobe failed: {stderr.decode()}")

        data = json.loads(stdout.decode())

        # Find video stream
        video_stream = None
        has_audio = False
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video" and video_stream is None:
                video_stream = stream
            elif stream.get("codec_type") == "audio":
                has_audio = True

        if not video_stream:
            raise ValueError("No video stream found in file")

        # Extract FPS from various possible fields
        fps = self._parse_fps(video_stream)

        # Get format info
        format_info = data.get("format", {})

        return VideoMetadata(
            duration_sec=float(format_info.get("duration", 0)),
            width=int(video_stream.get("width", 0)),
            height=int(video_stream.get("height", 0)),
            fps=fps,
            codec=video_stream.get("codec_name", "unknown").lower(),
            format=format_info.get("format_name", "unknown").split(",")[0].lower(),
            file_size_bytes=int(format_info.get("size", 0)),
            has_audio=has_audio,
            bit_rate=int(format_info.get("bit_rate", 0)) if format_info.get("bit_rate") else None,
        )

    def _parse_fps(self, stream: dict) -> float:
        """Parse FPS from stream data."""
        # Try r_frame_rate first (real frame rate)
        if "r_frame_rate" in stream:
            try:
                num, den = stream["r_frame_rate"].split("/")
                if int(den) > 0:
                    return float(num) / float(den)
            except (ValueError, ZeroDivisionError):
                pass

        # Try avg_frame_rate
        if "avg_frame_rate" in stream:
            try:
                num, den = stream["avg_frame_rate"].split("/")
                if int(den) > 0:
                    return float(num) / float(den)
            except (ValueError, ZeroDivisionError):
                pass

        return 0.0

    async def validate(
        self,
        video_path: str | Path,
        requirements: dict | None = None,
    ) -> TechnicalResult:
        """
        Validate a video file against technical requirements.

        Args:
            video_path: Path to the video file
            requirements: Optional dict of requirements to override defaults

        Returns:
            TechnicalResult with pass/fail, score, and details
        """
        reqs = {**self.DEFAULT_REQUIREMENTS, **(requirements or {})}

        try:
            metadata = await self.extract_metadata(video_path)
        except Exception as e:
            return TechnicalResult(
                passed=False,
                score=0.0,
                checks={"readable": False},
                metadata=None,
                error=str(e),
            )

        # Run all checks
        checks = {
            "readable": True,
            "valid_format": self._check_format(metadata),
            "valid_codec": self._check_codec(metadata),
            "resolution": self._check_resolution(metadata, reqs),
            "fps": self._check_fps(metadata, reqs),
            "duration": self._check_duration(metadata, reqs),
            "file_size": self._check_file_size(metadata, reqs),
        }

        # Calculate score (weighted average)
        weights = {
            "readable": 1.0,
            "valid_format": 1.0,
            "valid_codec": 1.0,
            "resolution": 1.0,
            "fps": 0.5,
            "duration": 1.0,
            "file_size": 0.5,
        }

        total_weight = sum(weights.values())
        score = sum(weights[k] * (1.0 if v else 0.0) for k, v in checks.items()) / total_weight

        # Must pass critical checks
        critical_checks = ["readable", "valid_format", "valid_codec", "duration"]
        passed = all(checks[c] for c in critical_checks)

        return TechnicalResult(
            passed=passed,
            score=round(score, 4),
            checks=checks,
            metadata=metadata,
        )

    def _check_format(self, metadata: VideoMetadata) -> bool:
        """Check if format is valid."""
        return metadata.format in self.VALID_FORMATS

    def _check_codec(self, metadata: VideoMetadata) -> bool:
        """Check if codec is valid."""
        return metadata.codec in self.VALID_CODECS

    def _check_resolution(self, metadata: VideoMetadata, reqs: dict) -> bool:
        """Check if resolution meets requirements."""
        return metadata.width >= reqs["min_width"] and metadata.height >= reqs["min_height"]

    def _check_fps(self, metadata: VideoMetadata, reqs: dict) -> bool:
        """Check if FPS is within acceptable range."""
        return reqs["min_fps"] <= metadata.fps <= reqs["max_fps"]

    def _check_duration(self, metadata: VideoMetadata, reqs: dict) -> bool:
        """Check if duration is within acceptable range."""
        return reqs["min_duration"] <= metadata.duration_sec <= reqs["max_duration"]

    def _check_file_size(self, metadata: VideoMetadata, reqs: dict) -> bool:
        """Check if file size is within limit."""
        max_bytes = reqs["max_file_size_mb"] * 1024 * 1024
        return metadata.file_size_bytes <= max_bytes


# Singleton instance
_validator: TechnicalValidator | None = None


def get_technical_validator() -> TechnicalValidator:
    """Get or create the technical validator instance."""
    global _validator
    if _validator is None:
        _validator = TechnicalValidator()
    return _validator
