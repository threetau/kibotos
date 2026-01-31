"""Miner CLI command implementations."""

from pathlib import Path

from rich.console import Console
from rich.table import Table

from kibotos.miner.uploader import get_miner_uploader

console = Console()


async def list_prompts(
    api_url: str,
    category: str | None = None,
) -> None:
    """List active prompts."""
    import httpx

    url = f"{api_url}/v1/prompts"
    params = {}
    if category:
        params["category"] = category

    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params, timeout=30.0)
        response.raise_for_status()
        prompts = response.json()

    if not prompts:
        console.print("[yellow]No active prompts found[/yellow]")
        return

    table = Table(title="Active Prompts")
    table.add_column("ID", style="cyan")
    table.add_column("Category", style="green")
    table.add_column("Task", style="yellow")
    table.add_column("Scenario")
    table.add_column("Submissions", justify="right")

    for prompt in prompts:
        table.add_row(
            prompt["id"],
            prompt["category"],
            prompt["task"],
            prompt["scenario"][:50] + "..." if len(prompt["scenario"]) > 50 else prompt["scenario"],
            str(prompt["total_submissions"]),
        )

    console.print(table)


async def upload_video(
    video_path: str,
    api_url: str,
) -> dict:
    """Upload a video and return upload result."""
    path = Path(video_path)
    if not path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    uploader = get_miner_uploader(api_url)

    console.print("[blue]Extracting video metadata...[/blue]")
    video_info = await uploader.extract_video_info(path)

    console.print(f"  Duration: {video_info.duration_sec:.1f}s")
    console.print(f"  Resolution: {video_info.width}x{video_info.height}")
    console.print(f"  FPS: {video_info.fps:.1f}")
    console.print(f"  Size: {video_info.file_size / 1024 / 1024:.1f} MB")

    console.print("[blue]Uploading to S3...[/blue]")
    result = await uploader.upload_video(path)

    console.print("[green]Upload complete![/green]")
    console.print(f"  Video key: {result.video_key}")
    console.print(f"  Video hash: {result.video_hash[:16]}...")

    return {
        "video_key": result.video_key,
        "video_hash": result.video_hash,
        "duration_sec": video_info.duration_sec,
        "width": video_info.width,
        "height": video_info.height,
        "fps": video_info.fps,
    }


async def submit_metadata(
    api_url: str,
    video_key: str,
    video_hash: str,
    prompt_id: str,
    miner_uid: int,
    miner_hotkey: str,
    camera_type: str,
    actor_type: str,
    duration_sec: float,
    width: int,
    height: int,
    fps: float,
    action_description: str | None = None,
) -> str:
    """Submit video metadata and return submission UUID."""
    # Create signature (placeholder - in production would use wallet)
    # For now, just sign the submission data
    import hashlib

    import httpx

    sig_data = f"{video_key}:{video_hash}:{miner_hotkey}"
    signature = hashlib.sha256(sig_data.encode()).hexdigest()

    payload = {
        "prompt_id": prompt_id,
        "video_key": video_key,
        "video_hash": video_hash,
        "miner_uid": miner_uid,
        "miner_hotkey": miner_hotkey,
        "signature": signature,
        "duration_sec": duration_sec,
        "resolution_width": width,
        "resolution_height": height,
        "fps": fps,
        "camera_type": camera_type,
        "actor_type": actor_type,
        "action_description": action_description,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{api_url}/v1/submissions",
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        result = response.json()

    console.print("[green]Submission created![/green]")
    console.print(f"  UUID: {result['submission_uuid']}")
    console.print(f"  Status: {result['status']}")

    return result["submission_uuid"]


async def submit_video_oneshot(
    video_path: str,
    api_url: str,
    prompt_id: str,
    miner_uid: int,
    miner_hotkey: str,
    camera_type: str,
    actor_type: str,
    action_description: str | None = None,
) -> str:
    """Upload video and submit metadata in one operation."""
    # Upload
    upload_result = await upload_video(video_path, api_url)

    # Submit
    return await submit_metadata(
        api_url=api_url,
        video_key=upload_result["video_key"],
        video_hash=upload_result["video_hash"],
        prompt_id=prompt_id,
        miner_uid=miner_uid,
        miner_hotkey=miner_hotkey,
        camera_type=camera_type,
        actor_type=actor_type,
        duration_sec=upload_result["duration_sec"],
        width=upload_result["width"],
        height=upload_result["height"],
        fps=upload_result["fps"],
        action_description=action_description,
    )


async def check_status(api_url: str, submission_uuid: str) -> None:
    """Check and display submission status."""
    import httpx

    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{api_url}/v1/submissions/{submission_uuid}",
            timeout=30.0,
        )
        response.raise_for_status()
        submission = response.json()

    console.print(f"\n[bold]Submission {submission['submission_uuid']}[/bold]")
    console.print(f"  Prompt: {submission.get('prompt_id', 'N/A')}")
    console.print(f"  Status: {submission['status']}")
    console.print(f"  Submitted: {submission['submitted_at']}")

    if submission.get("evaluated_at"):
        console.print(f"  Evaluated: {submission['evaluated_at']}")

    if submission.get("evaluation"):
        eval_data = submission["evaluation"]
        console.print("\n[bold]Evaluation[/bold]")
        console.print(f"  Technical: {eval_data.get('technical_score', 'N/A')}")
        console.print(f"  Relevance: {eval_data.get('relevance_score', 'N/A')}")
        console.print(f"  Quality: {eval_data.get('quality_score', 'N/A')}")
        console.print(f"  [bold]Final: {eval_data.get('final_score', 'N/A')}[/bold]")

        if eval_data.get("rejection_reason"):
            console.print(f"\n[red]Rejected: {eval_data['rejection_reason']}[/red]")
