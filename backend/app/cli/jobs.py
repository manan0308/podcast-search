"""
Job management CLI commands.
"""

import asyncio
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table

from app.cli.helpers import (
    get_channel_by_name_or_id,
    format_datetime,
)

console = Console()
app = typer.Typer()


@app.command("status")
def jobs_status(
    batch_id: Optional[str] = typer.Option(
        None, "--batch", "-b", help="Filter by batch ID"
    ),
    channel: Optional[str] = typer.Option(
        None, "--channel", "-c", help="Filter by channel"
    ),
    status_filter: Optional[str] = typer.Option(
        None, "--status", "-s", help="Filter by status"
    ),
    limit: int = typer.Option(20, "--limit", "-l", help="Max jobs to show"),
):
    """Show job status."""
    from sqlalchemy import select, func
    from app.database import AsyncSessionLocal
    from app.models import Job, Episode

    async def _status():
        async with AsyncSessionLocal() as db:
            query = select(Job).order_by(Job.updated_at.desc()).limit(limit)

            if batch_id:
                from uuid import UUID

                query = query.where(Job.batch_id == UUID(batch_id))

            if channel:
                ch = await get_channel_by_name_or_id(channel)
                if ch:
                    episode_ids = await db.scalars(
                        select(Episode.id).where(Episode.channel_id == ch.id)
                    )
                    query = query.where(Job.episode_id.in_(list(episode_ids)))

            if status_filter:
                query = query.where(Job.status == status_filter)

            result = await db.execute(query)
            jobs = result.scalars().all()

            if not jobs:
                console.print("[yellow]No jobs found.[/yellow]")
                return

            # Get summary counts
            count_result = await db.execute(
                select(Job.status, func.count(Job.id)).group_by(Job.status)
            )
            counts = dict(count_result.all())

            console.print("\n[bold]Job Summary[/bold]")
            for status, count in sorted(counts.items()):
                color = {
                    "done": "green",
                    "failed": "red",
                    "pending": "yellow",
                }.get(status, "blue")
                console.print(f"  [{color}]{status}[/{color}]: {count}")

            # Show jobs table
            table = Table(title=f"\nRecent Jobs (showing {len(jobs)})")
            table.add_column("ID", style="dim", width=8)
            table.add_column("Status", width=12)
            table.add_column("Progress", justify="right", width=8)
            table.add_column("Step", width=20)
            table.add_column("Updated", style="dim", width=16)

            for job in jobs:
                status_color = {
                    "done": "green",
                    "failed": "red",
                    "pending": "yellow",
                }.get(job.status, "blue")

                table.add_row(
                    str(job.id)[:8],
                    f"[{status_color}]{job.status}[/{status_color}]",
                    f"{job.progress}%",
                    job.current_step or "-",
                    format_datetime(job.updated_at),
                )

            console.print(table)

    asyncio.run(_status())


@app.command("retry")
def retry_jobs(
    batch_id: Optional[str] = typer.Option(
        None, "--batch", "-b", help="Retry all failed in batch"
    ),
    job_id: Optional[str] = typer.Option(
        None, "--job", "-j", help="Retry specific job"
    ),
    channel: Optional[str] = typer.Option(
        None, "--channel", "-c", help="Retry all failed in channel"
    ),
):
    """Retry failed jobs."""
    from uuid import UUID
    from sqlalchemy import select, update
    from app.database import AsyncSessionLocal
    from app.models import Job, Episode

    if not any([batch_id, job_id, channel]):
        console.print("[red]Specify --batch, --job, or --channel[/red]")
        raise typer.Exit(1)

    async def _retry():
        async with AsyncSessionLocal() as db:
            if job_id:
                # Retry single job
                await db.execute(
                    update(Job)
                    .where(Job.id == UUID(job_id))
                    .values(
                        status="pending",
                        error_message=None,
                        retry_count=Job.retry_count + 1,
                    )
                )
                await db.commit()
                console.print(f"[green]Queued job {job_id} for retry[/green]")

            elif batch_id:
                # Retry all failed in batch
                result = await db.execute(
                    update(Job)
                    .where(Job.batch_id == UUID(batch_id), Job.status == "failed")
                    .values(
                        status="pending",
                        error_message=None,
                        retry_count=Job.retry_count + 1,
                    )
                )
                await db.commit()
                console.print(
                    f"[green]Queued {result.rowcount} failed jobs for retry[/green]"
                )

            elif channel:
                ch = await get_channel_by_name_or_id(channel)
                if not ch:
                    console.print(f"[red]Channel not found: {channel}[/red]")
                    raise typer.Exit(1)

                episode_ids = await db.scalars(
                    select(Episode.id).where(Episode.channel_id == ch.id)
                )
                result = await db.execute(
                    update(Job)
                    .where(
                        Job.episode_id.in_(list(episode_ids)), Job.status == "failed"
                    )
                    .values(
                        status="pending",
                        error_message=None,
                        retry_count=Job.retry_count + 1,
                    )
                )
                await db.commit()
                console.print(
                    f"[green]Queued {result.rowcount} failed jobs for retry[/green]"
                )

    asyncio.run(_retry())


@app.command("errors")
def show_errors(
    batch_id: Optional[str] = typer.Option(
        None, "--batch", "-b", help="Filter by batch"
    ),
    channel: Optional[str] = typer.Option(
        None, "--channel", "-c", help="Filter by channel"
    ),
    limit: int = typer.Option(20, "--limit", "-l", help="Max errors to show"),
):
    """Show failed jobs with error messages."""
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import Job, Episode

    async def _errors():
        async with AsyncSessionLocal() as db:
            query = (
                select(Job, Episode)
                .join(Episode)
                .where(Job.status == "failed")
                .order_by(Job.updated_at.desc())
                .limit(limit)
            )

            if batch_id:
                from uuid import UUID

                query = query.where(Job.batch_id == UUID(batch_id))

            if channel:
                ch = await get_channel_by_name_or_id(channel)
                if ch:
                    query = query.where(Episode.channel_id == ch.id)

            result = await db.execute(query)
            rows = result.all()

            if not rows:
                console.print("[green]No failed jobs found.[/green]")
                return

            table = Table(title="Failed Jobs")
            table.add_column("Episode", style="cyan", max_width=40)
            table.add_column("Error", style="red", max_width=60)
            table.add_column("Retries", justify="right")

            for job, episode in rows:
                table.add_row(
                    (
                        episode.title[:37] + "..."
                        if len(episode.title) > 40
                        else episode.title
                    ),
                    (
                        (job.error_message or "Unknown")[:57] + "..."
                        if len(job.error_message or "") > 60
                        else (job.error_message or "Unknown")
                    ),
                    str(job.retry_count),
                )

            console.print(table)

    asyncio.run(_errors())


@app.command("find-missing")
def find_missing(
    channel: str = typer.Argument(..., help="Channel name, slug, or ID"),
):
    """Find episodes that haven't been transcribed yet."""
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import Episode

    async def _find():
        ch = await get_channel_by_name_or_id(channel)
        if not ch:
            console.print(f"[red]Channel not found: {channel}[/red]")
            raise typer.Exit(1)

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Episode)
                .where(Episode.channel_id == ch.id)
                .where(Episode.status != "done")
                .order_by(Episode.published_at.desc())
            )
            episodes = result.scalars().all()

            if not episodes:
                console.print(
                    f"[green]All episodes in '{ch.name}' are transcribed![/green]"
                )
                return

            table = Table(title=f"Missing Transcriptions ({len(episodes)} episodes)")
            table.add_column("Title", style="cyan", max_width=50)
            table.add_column("Status", width=12)
            table.add_column("Published", style="dim")

            for ep in episodes:
                status_color = "yellow" if ep.status == "pending" else "red"
                table.add_row(
                    ep.title[:47] + "..." if len(ep.title) > 50 else ep.title,
                    f"[{status_color}]{ep.status}[/{status_color}]",
                    format_datetime(ep.published_at),
                )

            console.print(table)

    asyncio.run(_find())
