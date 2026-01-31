"""Video uploader for miners."""

import asyncio
import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass
class VideoInfo:
    """Extracted video information."""

    path: Path
    file_hash: str
    duration_sec: float
    width: int
    height: int
    fps: float
    file_size: int


@dataclass
class UploadResult:
    """Result of video upload."""

    video_key: str
    video_hash: str
    video_info: VideoInfo


class MinerUploader:
    """Handles video upload and submission for miners."""

    def __init__(self, api_url: str = "http://localhost:8080"):
        self.api_url = api_url.rstrip("/")
        self._ffprobe_path = shutil.which("ffprobe")

    async def extract_video_info(self, video_path: Path) -> VideoInfo:
        """Extract metadata from video file."""
        if not video_path.exists():
            raise FileNotFoundError(f"Video not found: {video_path}")

        if not self._ffprobe_path:
            raise RuntimeError("ffprobe not found. Please install ffmpeg.")

        # Get file hash
        file_hash = await self._compute_hash(video_path)

        # Get video metadata
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
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        if not video_stream:
            raise ValueError("No video stream found")

        # Parse FPS
        fps = 0.0
        if "r_frame_rate" in video_stream:
            try:
                num, den = video_stream["r_frame_rate"].split("/")
                if int(den) > 0:
                    fps = float(num) / float(den)
            except (ValueError, ZeroDivisionError):
                pass

        format_info = data.get("format", {})

        return VideoInfo(
            path=video_path,
            file_hash=file_hash,
            duration_sec=float(format_info.get("duration", 0)),
            width=int(video_stream.get("width", 0)),
            height=int(video_stream.get("height", 0)),
            fps=fps,
            file_size=int(format_info.get("size", 0)),
        )

    async def _compute_hash(self, file_path: Path) -> str:
        """Compute SHA256 hash of file."""
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    async def upload_video(self, video_path: Path) -> UploadResult:
        """
        Upload video to S3 via presigned URL.

        Returns:
            UploadResult with S3 key and video info
        """
        video_path = Path(video_path)
        video_info = await self.extract_video_info(video_path)

        # Get presigned upload URL
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/v1/upload/presign",
                json={
                    "filename": video_path.name,
                    "content_type": "video/mp4",
                },
                timeout=30.0,
            )
            response.raise_for_status()
            presign_data = response.json()

        upload_url = presign_data["upload_url"]
        video_key = presign_data["video_key"]

        # Upload video
        with open(video_path, "rb") as f:
            video_data = f.read()

        async with httpx.AsyncClient() as client:
            response = await client.put(
                upload_url,
                content=video_data,
                headers={"Content-Type": "video/mp4"},
                timeout=300.0,  # 5 min timeout for large files
            )
            response.raise_for_status()

        return UploadResult(
            video_key=video_key,
            video_hash=video_info.file_hash,
            video_info=video_info,
        )

    async def submit_video(
        self,
        video_key: str,
        video_hash: str,
        video_info: VideoInfo,
        prompt_id: str,
        miner_uid: int,
        miner_hotkey: str,
        camera_type: str,
        actor_type: str,
        signature: str,
        action_description: str | None = None,
    ) -> dict:
        """
        Submit video metadata to API.

        Returns:
            Submission response with UUID
        """
        payload = {
            "prompt_id": prompt_id,
            "video_key": video_key,
            "video_hash": video_hash,
            "miner_uid": miner_uid,
            "miner_hotkey": miner_hotkey,
            "signature": signature,
            "duration_sec": video_info.duration_sec,
            "resolution_width": video_info.width,
            "resolution_height": video_info.height,
            "fps": video_info.fps,
            "camera_type": camera_type,
            "actor_type": actor_type,
            "action_description": action_description,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self.api_url}/v1/submissions",
                json=payload,
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()

    async def check_status(self, submission_uuid: str) -> dict:
        """Check submission status."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/v1/submissions/{submission_uuid}",
                timeout=30.0,
            )
            response.raise_for_status()
            return response.json()


def get_miner_uploader(api_url: str = "http://localhost:8080") -> MinerUploader:
    """Get a miner uploader instance."""
    return MinerUploader(api_url)
