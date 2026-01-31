"""Main CLI entry point for Kibotos."""

import asyncio
from typing import Annotated

import typer
from rich.console import Console

from kibotos import __version__

app = typer.Typer(
    name="kibotos",
    help="Bittensor subnet for robot video data collection",
    no_args_is_help=True,
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        console.print(f"kibotos version {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        bool | None,
        typer.Option("--version", "-v", callback=version_callback, is_eager=True),
    ] = None,
) -> None:
    """Kibotos: Bittensor subnet for robot video data collection."""
    pass


# =============================================================================
# API Command
# =============================================================================


@app.command()
def api(
    host: Annotated[str, typer.Option(help="Host to bind to")] = "0.0.0.0",
    port: Annotated[int, typer.Option(help="Port to listen on")] = 8000,
    reload: Annotated[bool, typer.Option(help="Enable auto-reload")] = False,
) -> None:
    """Start the API server."""
    import uvicorn

    console.print(f"[green]Starting API server on {host}:{port}[/green]")
    uvicorn.run(
        "kibotos.api.main:app",
        host=host,
        port=port,
        reload=reload,
    )


# =============================================================================
# Scheduler Command
# =============================================================================


@app.command()
def scheduler(
    cycle_duration: Annotated[int, typer.Option(help="Cycle duration in minutes")] = 60,
    check_interval: Annotated[int, typer.Option(help="Check interval in seconds")] = 30,
    no_auto_start: Annotated[bool, typer.Option(help="Disable auto-starting cycles")] = False,
) -> None:
    """Start the scheduler service."""
    from kibotos.scheduler.main import run_scheduler

    console.print("[green]Starting scheduler service[/green]")
    console.print(f"  Cycle duration: {cycle_duration} minutes")
    console.print(f"  Check interval: {check_interval} seconds")
    console.print(f"  Auto-start: {not no_auto_start}")

    asyncio.run(
        run_scheduler(
            cycle_duration_minutes=cycle_duration,
            check_interval_seconds=check_interval,
            auto_start_cycles=not no_auto_start,
        )
    )


# =============================================================================
# Evaluator Command
# =============================================================================


@app.command()
def evaluator(
    api_url: Annotated[str, typer.Option(help="Backend API URL")] = "http://localhost:8080",
    poll_interval: Annotated[int, typer.Option(help="Polling interval in seconds")] = 10,
    batch_size: Annotated[int, typer.Option(help="Submissions per batch")] = 5,
) -> None:
    """Start the evaluator service."""
    from kibotos.evaluator.main import run_evaluator

    console.print("[green]Starting evaluator service[/green]")
    console.print(f"  API URL: {api_url}")
    console.print(f"  Poll interval: {poll_interval}s")
    console.print(f"  Batch size: {batch_size}")

    asyncio.run(
        run_evaluator(
            api_url=api_url,
            poll_interval=poll_interval,
            batch_size=batch_size,
        )
    )


# =============================================================================
# Validator Command
# =============================================================================


@app.command()
def validate(
    backend_url: Annotated[str, typer.Option(help="Backend API URL")] = "http://localhost:8080",
    netuid: Annotated[int | None, typer.Option(help="Subnet UID")] = None,
    network: Annotated[str, typer.Option(help="Network (finney, test)")] = "test",
    wallet_name: Annotated[str, typer.Option(help="Wallet name")] = "default",
    hotkey_name: Annotated[str, typer.Option(help="Hotkey name")] = "default",
    poll_interval: Annotated[int, typer.Option(help="Poll interval in seconds")] = 60,
) -> None:
    """Start the validator service."""
    from kibotos.validator.main import run_validator

    console.print("[green]Starting validator service[/green]")
    console.print(f"  Backend: {backend_url}")
    console.print(f"  Network: {network}")
    console.print(f"  Netuid: {netuid}")
    console.print(f"  Wallet: {wallet_name}/{hotkey_name}")

    asyncio.run(
        run_validator(
            backend_url=backend_url,
            netuid=netuid,
            network=network,
            wallet_name=wallet_name,
            hotkey_name=hotkey_name,
            poll_interval=poll_interval,
        )
    )


# =============================================================================
# Database Commands
# =============================================================================

db_app = typer.Typer(help="Database management commands")
app.add_typer(db_app, name="db")


@db_app.command("init")
def db_init(
    database_url: Annotated[str | None, typer.Option(help="Database URL (overrides env)")] = None,
) -> None:
    """Initialize the database schema."""
    from kibotos.db import init_db

    async def _init():
        console.print("[blue]Initializing database...[/blue]")
        await init_db()
        console.print("[green]Database initialized successfully[/green]")

    asyncio.run(_init())


@db_app.command("reset")
def db_reset(
    database_url: Annotated[str | None, typer.Option(help="Database URL (overrides env)")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation")] = False,
) -> None:
    """Reset the database (drop and recreate all tables)."""
    from kibotos.db.session import drop_db, init_db

    if not force:
        confirm = typer.confirm("This will delete all data. Continue?")
        if not confirm:
            raise typer.Abort()

    async def _reset():
        console.print("[yellow]Dropping all tables...[/yellow]")
        await drop_db()
        console.print("[blue]Recreating tables...[/blue]")
        await init_db()
        console.print("[green]Database reset successfully[/green]")

    asyncio.run(_reset())


# =============================================================================
# Miner Commands
# =============================================================================

miner_app = typer.Typer(help="Miner commands")
app.add_typer(miner_app, name="miner")


@miner_app.command("prompts")
def miner_prompts(
    api_url: Annotated[str, typer.Option(help="Backend API URL")] = "http://localhost:8080",
    category: Annotated[str | None, typer.Option(help="Filter by category")] = None,
) -> None:
    """List active prompts."""
    from kibotos.miner.commands import list_prompts

    try:
        asyncio.run(list_prompts(api_url, category))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@miner_app.command("upload")
def miner_upload(
    video_path: Annotated[str, typer.Argument(help="Path to video file")],
    api_url: Annotated[str, typer.Option(help="Backend API URL")] = "http://localhost:8080",
) -> None:
    """Upload a video file and get the S3 key."""
    from kibotos.miner.commands import upload_video

    try:
        result = asyncio.run(upload_video(video_path, api_url))
        console.print("\nUse these values to submit:")
        console.print(f"  --video-key '{result['video_key']}'")
        console.print(f"  --video-hash '{result['video_hash']}'")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error uploading: {e}[/red]")
        raise typer.Exit(1)


@miner_app.command("submit")
def miner_submit(
    video_key: Annotated[str, typer.Option(help="S3 video key")],
    video_hash: Annotated[str, typer.Option(help="Video file hash")],
    prompt_id: Annotated[str, typer.Option(help="Prompt ID to fulfill")],
    miner_uid: Annotated[int, typer.Option(help="Miner UID")],
    miner_hotkey: Annotated[str, typer.Option(help="Miner hotkey")],
    camera_type: Annotated[str, typer.Option(help="Camera type (ego_head, ego_wrist, etc.)")],
    actor_type: Annotated[str, typer.Option(help="Actor type (human, robot, human_with_robot)")],
    duration: Annotated[float, typer.Option(help="Video duration in seconds")],
    width: Annotated[int, typer.Option(help="Video width")],
    height: Annotated[int, typer.Option(help="Video height")],
    fps: Annotated[float, typer.Option(help="Video FPS")],
    api_url: Annotated[str, typer.Option(help="Backend API URL")] = "http://localhost:8080",
    action: Annotated[str | None, typer.Option(help="Action description")] = None,
) -> None:
    """Submit video metadata for an uploaded video."""
    from kibotos.miner.commands import submit_metadata

    try:
        asyncio.run(
            submit_metadata(
                api_url=api_url,
                video_key=video_key,
                video_hash=video_hash,
                prompt_id=prompt_id,
                miner_uid=miner_uid,
                miner_hotkey=miner_hotkey,
                camera_type=camera_type,
                actor_type=actor_type,
                duration_sec=duration,
                width=width,
                height=height,
                fps=fps,
                action_description=action,
            )
        )
    except Exception as e:
        console.print(f"[red]Error submitting: {e}[/red]")
        raise typer.Exit(1)


@miner_app.command("submit-video")
def miner_submit_video(
    video_path: Annotated[str, typer.Argument(help="Path to video file")],
    prompt_id: Annotated[str, typer.Option(help="Prompt ID to fulfill")],
    miner_uid: Annotated[int, typer.Option(help="Miner UID")],
    miner_hotkey: Annotated[str, typer.Option(help="Miner hotkey")],
    camera_type: Annotated[str, typer.Option(help="Camera type (ego_head, ego_wrist, etc.)")],
    actor_type: Annotated[str, typer.Option(help="Actor type (human, robot, human_with_robot)")],
    api_url: Annotated[str, typer.Option(help="Backend API URL")] = "http://localhost:8080",
    action: Annotated[str | None, typer.Option(help="Action description")] = None,
) -> None:
    """Upload video and submit in one step."""
    from kibotos.miner.commands import submit_video_oneshot

    try:
        asyncio.run(
            submit_video_oneshot(
                video_path=video_path,
                api_url=api_url,
                prompt_id=prompt_id,
                miner_uid=miner_uid,
                miner_hotkey=miner_hotkey,
                camera_type=camera_type,
                actor_type=actor_type,
                action_description=action,
            )
        )
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@miner_app.command("status")
def miner_status(
    submission_uuid: Annotated[str, typer.Argument(help="Submission UUID")],
    api_url: Annotated[str, typer.Option(help="Backend API URL")] = "http://localhost:8080",
) -> None:
    """Check the status of a submission."""
    from kibotos.miner.commands import check_status

    try:
        asyncio.run(check_status(api_url, submission_uuid))
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


# =============================================================================
# Prompt Commands (Admin)
# =============================================================================

prompts_app = typer.Typer(help="Prompt management commands")
app.add_typer(prompts_app, name="prompts")


@prompts_app.command("generate")
def prompts_generate(
    category: Annotated[str, typer.Option(help="Category to generate prompts for")],
    count: Annotated[int, typer.Option(help="Number of prompts to generate")] = 10,
    output: Annotated[str, typer.Option(help="Output file")] = "prompts.json",
) -> None:
    """Generate prompts from taxonomy using LLM."""
    console.print("[yellow]Prompt generation not yet implemented[/yellow]")
    raise typer.Exit(1)


@prompts_app.command("load")
def prompts_load(
    prompts_file: Annotated[str, typer.Argument(help="JSON file with prompts")],
    api_url: Annotated[str, typer.Option(help="Backend API URL")] = "http://localhost:8000",
) -> None:
    """Load prompts into the database."""
    console.print("[yellow]Prompt loading not yet implemented[/yellow]")
    raise typer.Exit(1)


@prompts_app.command("stats")
def prompts_stats(
    api_url: Annotated[str, typer.Option(help="Backend API URL")] = "http://localhost:8000",
) -> None:
    """Show prompt statistics."""
    import httpx

    url = f"{api_url}/v1/prompts/categories"

    try:
        response = httpx.get(url)
        response.raise_for_status()
        categories = response.json()

        console.print("\n[bold]Prompt Statistics[/bold]")
        total = 0
        for cat in categories:
            console.print(f"  {cat['category']}: {cat['count']} prompts")
            total += cat["count"]
        console.print(f"\n  Total: {total} prompts")

    except httpx.HTTPError as e:
        console.print(f"[red]Error fetching stats: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
