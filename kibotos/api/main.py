"""FastAPI application for Kibotos."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from kibotos import __version__
from kibotos.api.routes import evaluation, health, prompts, scores, submissions
from kibotos.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    await init_db()
    yield
    # Shutdown


app = FastAPI(
    title="Kibotos",
    description="Bittensor subnet for robot video data collection",
    version=__version__,
    lifespan=lifespan,
)

# Include routers
app.include_router(health.router)
app.include_router(prompts.router, prefix="/v1")
app.include_router(submissions.router, prefix="/v1")
app.include_router(evaluation.router, prefix="/v1")
app.include_router(scores.router, prefix="/v1")
