"""
CLI helper functions and utilities.
"""
import asyncio
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from sqlalchemy import select, func

from app.database import AsyncSessionLocal
from app.models import Channel, Episode, Batch, Job

console = Console()


async def get_db():
    """Get async database session."""
    async with AsyncSessionLocal() as session:
        yield session


async def get_system_status():
    """Display system status."""
    async with AsyncSessionLocal() as db:
        # Get counts
        channel_count = await db.scalar(select(func.count(Channel.id)))
        episode_count = await db.scalar(select(func.count(Episode.id)))
        done_episodes = await db.scalar(
            select(func.count(Episode.id)).where(Episode.status == "done")
        )
        pending_episodes = await db.scalar(
            select(func.count(Episode.id)).where(Episode.status == "pending")
        )
        running_batches = await db.scalar(
            select(func.count(Batch.id)).where(Batch.status == "running")
        )
        pending_jobs = await db.scalar(
            select(func.count(Job.id)).where(Job.status == "pending")
        )
        processing_jobs = await db.scalar(
            select(func.count(Job.id)).where(Job.status.in_(["downloading", "transcribing", "labeling", "embedding"]))
        )

    table = Table(title="System Status")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Channels", str(channel_count))
    table.add_row("Total Episodes", str(episode_count))
    table.add_row("Transcribed", str(done_episodes))
    table.add_row("Pending", str(pending_episodes))
    table.add_row("Running Batches", str(running_batches))
    table.add_row("Pending Jobs", str(pending_jobs))
    table.add_row("Processing Jobs", str(processing_jobs))

    console.print(table)


async def get_channel_list():
    """Get list of all channels."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Channel).order_by(Channel.created_at.desc())
        )
        return result.scalars().all()


async def get_channel_by_name_or_id(identifier: str) -> Optional[Channel]:
    """Get channel by name, slug, or ID."""
    async with AsyncSessionLocal() as db:
        # Try by ID first
        try:
            from uuid import UUID
            uuid_id = UUID(identifier)
            result = await db.execute(
                select(Channel).where(Channel.id == uuid_id)
            )
            channel = result.scalar_one_or_none()
            if channel:
                return channel
        except ValueError:
            pass

        # Try by slug
        result = await db.execute(
            select(Channel).where(Channel.slug == identifier)
        )
        channel = result.scalar_one_or_none()
        if channel:
            return channel

        # Try by name (case-insensitive)
        result = await db.execute(
            select(Channel).where(Channel.name.ilike(f"%{identifier}%"))
        )
        return result.scalar_one_or_none()


async def get_batch_status(batch_id: str):
    """Get batch status with job details."""
    from uuid import UUID
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Batch).where(Batch.id == UUID(batch_id))
        )
        batch = result.scalar_one_or_none()
        if not batch:
            return None

        # Get job counts by status
        job_result = await db.execute(
            select(Job.status, func.count(Job.id))
            .where(Job.batch_id == batch.id)
            .group_by(Job.status)
        )
        job_counts = dict(job_result.all())

        return {
            "batch": batch,
            "jobs": job_counts,
        }


def format_duration(seconds: int) -> str:
    """Format duration in human-readable form."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"


def format_datetime(dt: Optional[datetime]) -> str:
    """Format datetime for display."""
    if not dt:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M")


def create_progress() -> Progress:
    """Create a rich progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )
