"""VLM client for video content analysis."""

import asyncio
import base64
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

import httpx

from kibotos.config import get_settings


@dataclass
class VLMResponse:
    """Response from VLM analysis."""

    content: str
    model: str
    usage: dict | None = None


class VLMClient:
    """Client for OpenAI-compatible vision language models."""

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        model: str | None = None,
    ):
        settings = get_settings()
        self.api_url = (api_url or settings.vlm.api_url).rstrip("/")
        self.api_key = api_key or settings.vlm.api_key
        self.model = model or settings.vlm.model
        self._ffmpeg_path = shutil.which("ffmpeg")

    async def analyze_images(
        self,
        images: list[bytes | str | Path],
        prompt: str,
        max_tokens: int = 1024,
    ) -> VLMResponse:
        """
        Analyze images with a text prompt.

        Args:
            images: List of image bytes, base64 strings, or file paths
            prompt: Text prompt for analysis
            max_tokens: Maximum tokens in response

        Returns:
            VLMResponse with the model's analysis
        """
        # Build content with images
        content = []

        for img in images:
            if isinstance(img, (str, Path)) and Path(img).exists():
                # Read file and encode
                with open(img, "rb") as f:
                    img_data = base64.b64encode(f.read()).decode()
            elif isinstance(img, bytes):
                img_data = base64.b64encode(img).decode()
            else:
                # Assume already base64 encoded
                img_data = str(img)

            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{img_data}",
                        "detail": "low",  # Use low detail for efficiency
                    },
                }
            )

        # Add text prompt
        content.append({"type": "text", "text": prompt})

        # Make API request
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.api_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        return VLMResponse(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", self.model),
            usage=data.get("usage"),
        )

    async def extract_keyframes(
        self,
        video_path: str | Path,
        n_frames: int = 5,
        output_format: str = "jpg",
    ) -> list[Path]:
        """
        Extract keyframes from a video file.

        Args:
            video_path: Path to video file
            n_frames: Number of frames to extract
            output_format: Output image format (jpg, png)

        Returns:
            List of paths to extracted frame images
        """
        if not self._ffmpeg_path:
            raise RuntimeError("ffmpeg not found. Please install ffmpeg.")

        video_path = Path(video_path)
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        # Create temp directory for frames
        temp_dir = Path(tempfile.mkdtemp(prefix="kibotos_frames_"))

        # Get video duration first
        probe_cmd = [
            shutil.which("ffprobe"),
            "-v",
            "quiet",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *probe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        duration = float(stdout.decode().strip())

        # Calculate timestamps for evenly spaced frames
        # Skip first and last 5% to avoid black frames
        start_time = duration * 0.05
        end_time = duration * 0.95
        interval = (end_time - start_time) / (n_frames - 1) if n_frames > 1 else 0

        frames = []
        for i in range(n_frames):
            timestamp = start_time + (i * interval)
            output_path = temp_dir / f"frame_{i:03d}.{output_format}"

            cmd = [
                self._ffmpeg_path,
                "-ss",
                str(timestamp),
                "-i",
                str(video_path),
                "-vframes",
                "1",
                "-q:v",
                "2",  # High quality
                "-y",  # Overwrite
                str(output_path),
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            if output_path.exists():
                frames.append(output_path)

        return frames

    async def analyze_video(
        self,
        video_path: str | Path,
        prompt: str,
        n_frames: int = 5,
        max_tokens: int = 1024,
    ) -> VLMResponse:
        """
        Analyze a video by extracting keyframes and sending to VLM.

        Args:
            video_path: Path to video file
            prompt: Text prompt for analysis
            n_frames: Number of keyframes to extract
            max_tokens: Maximum tokens in response

        Returns:
            VLMResponse with the model's analysis
        """
        # Extract keyframes
        frames = await self.extract_keyframes(video_path, n_frames)

        if not frames:
            raise ValueError("Failed to extract any frames from video")

        try:
            # Analyze frames
            return await self.analyze_images(frames, prompt, max_tokens)
        finally:
            # Cleanup temp frames
            for frame in frames:
                try:
                    frame.unlink()
                except Exception:
                    pass
            # Remove temp directory
            try:
                frames[0].parent.rmdir()
            except Exception:
                pass


# Singleton instance
_client: VLMClient | None = None


def get_vlm_client() -> VLMClient:
    """Get or create the VLM client instance."""
    global _client
    if _client is None:
        _client = VLMClient()
    return _client
