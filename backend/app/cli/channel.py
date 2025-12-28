"""
Channel management CLI commands.
"""

import asyncio
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from app.cli.helpers import (
    get_channel_list,
    get_channel_by_name_or_id,
    format_datetime,
    create_progress,
)

console = Console()
app = typer.Typer()


@app.command("list")
def list_channels():
    """List all channels."""

    async def _list():
        channels = await get_channel_list()

        if not channels:
            console.print("[yellow]No channels found.[/yellow]")
            return

        table = Table(title="Channels")
        table.add_column("Name", style="cyan")
        table.add_column("Slug", style="dim")
        table.add_column("Episodes", justify="right")
        table.add_column("Transcribed", justify="right")
        table.add_column("Created", style="dim")

        for ch in channels:
            table.add_row(
                ch.name,
                ch.slug,
                str(ch.episode_count or 0),
                str(ch.transcribed_count or 0),
                format_datetime(ch.created_at),
            )

        console.print(table)

    asyncio.run(_list())


@app.command("scrape")
def scrape_channel(
    url: str = typer.Argument(..., help="YouTube channel URL"),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Maximum episodes to fetch"
    ),
    min_duration: int = typer.Option(
        300, "--min-duration", "-m", help="Minimum video duration in seconds"
    ),
    create: bool = typer.Option(
        False, "--create", "-c", help="Create channel in database"
    ),
):
    """Scrape a YouTube channel and list its videos."""
    from app.services.youtube import YouTubeService

    async def _scrape():
        youtube = YouTubeService()

        with create_progress() as progress:
            task = progress.add_task("Fetching channel info...", total=None)

            # Get channel info
            channel_info = await youtube.get_channel_info(url)
            progress.update(task, description="Fetching videos...")

            # Get videos
            videos = await youtube.fetch_channel_episodes(
                url,
                limit=limit,
                min_duration_seconds=min_duration,
            )

            progress.update(task, completed=True)

        console.print(f"\n[bold green]Channel:[/bold green] {channel_info.name}")
        console.print(f"[dim]ID: {channel_info.channel_id}[/dim]")
        console.print(f"[dim]URL: {channel_info.url}[/dim]")
        console.print(f"\n[bold]Found {len(videos)} videos[/bold]\n")

        # Show video list
        table = Table(title="Videos")
        table.add_column("#", style="dim", width=4)
        table.add_column("Title", style="cyan", max_width=60)
        table.add_column("Duration", justify="right")
        table.add_column("Published", style="dim")

        for i, video in enumerate(videos[:50], 1):  # Show first 50
            duration_min = video.duration_seconds // 60
            table.add_row(
                str(i),
                video.title[:57] + "..." if len(video.title) > 60 else video.title,
                f"{duration_min}m",
                format_datetime(video.published_at),
            )

        console.print(table)

        if len(videos) > 50:
            console.print(f"\n[dim]... and {len(videos) - 50} more videos[/dim]")

        # Create in database if requested
        if create:
            if Confirm.ask("\nCreate this channel in the database?"):
                await _create_channel(channel_info, videos)

    async def _create_channel(channel_info, videos):
        from uuid import uuid4
        from slugify import slugify
        from app.database import AsyncSessionLocal
        from app.models import Channel, Episode

        async with AsyncSessionLocal() as db:
            # Create channel
            channel = Channel(
                id=uuid4(),
                name=channel_info.name,
                slug=slugify(channel_info.name),
                youtube_channel_id=channel_info.channel_id,
                youtube_url=channel_info.url,
                thumbnail_url=channel_info.thumbnail_url,
                description=channel_info.description,
                episode_count=len(videos),
            )
            db.add(channel)

            # Create episodes
            for video in videos:
                episode = Episode(
                    id=uuid4(),
                    channel_id=channel.id,
                    youtube_id=video.youtube_id,
                    title=video.title,
                    description=video.description,
                    thumbnail_url=video.thumbnail_url,
                    published_at=video.published_at,
                    duration_seconds=video.duration_seconds,
                    status="pending",
                )
                db.add(episode)

            await db.commit()
            console.print(
                f"\n[green]Created channel '{channel.name}' with {len(videos)} episodes[/green]"
            )

    asyncio.run(_scrape())


@app.command("status")
def channel_status(
    identifier: str = typer.Argument(..., help="Channel name, slug, or ID"),
):
    """Show detailed status for a channel."""

    async def _status():
        from sqlalchemy import select, func
        from app.database import AsyncSessionLocal
        from app.models import Episode

        channel = await get_channel_by_name_or_id(identifier)
        if not channel:
            console.print(f"[red]Channel not found: {identifier}[/red]")
            raise typer.Exit(1)

        # Get episode stats
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(Episode.status, func.count(Episode.id))
                .where(Episode.channel_id == channel.id)
                .group_by(Episode.status)
            )
            status_counts = dict(result.all())

        console.print(f"\n[bold cyan]{channel.name}[/bold cyan]")
        console.print(f"[dim]Slug: {channel.slug}[/dim]")
        console.print(f"[dim]YouTube: {channel.youtube_url}[/dim]")

        table = Table(title="\nEpisode Status")
        table.add_column("Status", style="cyan")
        table.add_column("Count", justify="right")

        total = 0
        for status, count in sorted(status_counts.items()):
            color = (
                "green"
                if status == "done"
                else "yellow" if status == "pending" else "red"
            )
            table.add_row(f"[{color}]{status}[/{color}]", str(count))
            total += count

        table.add_row("[bold]Total[/bold]", f"[bold]{total}[/bold]")
        console.print(table)

        if channel.speakers:
            console.print(f"\n[bold]Speakers:[/bold] {', '.join(channel.speakers)}")

    asyncio.run(_status())


@app.command("reset")
def reset_channel(
    identifier: str = typer.Argument(..., help="Channel name, slug, or ID"),
    episodes_only: bool = typer.Option(
        False, "--episodes-only", help="Only reset episodes, keep channel"
    ),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
):
    """Reset a channel (delete all data and re-import)."""

    async def _reset():
        from sqlalchemy import delete
        from app.database import AsyncSessionLocal
        from app.models import Episode, Job, Utterance, Chunk

        channel = await get_channel_by_name_or_id(identifier)
        if not channel:
            console.print(f"[red]Channel not found: {identifier}[/red]")
            raise typer.Exit(1)

        if not force and not Confirm.ask(
            f"Reset channel '{channel.name}'? This will delete all transcription data."
        ):
            raise typer.Exit(0)

        async with AsyncSessionLocal() as db:
            # Delete related data
            episode_ids = await db.scalars(
                select(Episode.id).where(Episode.channel_id == channel.id)
            )
            episode_ids = list(episode_ids)

            if episode_ids:
                # Delete chunks
                await db.execute(delete(Chunk).where(Chunk.episode_id.in_(episode_ids)))
                # Delete utterances
                await db.execute(
                    delete(Utterance).where(Utterance.episode_id.in_(episode_ids))
                )
                # Delete jobs
                await db.execute(delete(Job).where(Job.episode_id.in_(episode_ids)))

            # Reset episodes
            await db.execute(delete(Episode).where(Episode.channel_id == channel.id))

            if not episodes_only:
                from app.models import Channel

                await db.execute(delete(Channel).where(Channel.id == channel.id))

            await db.commit()

        if episodes_only:
            console.print(
                f"[green]Reset {len(episode_ids)} episodes for '{channel.name}'[/green]"
            )
        else:
            console.print(
                f"[green]Deleted channel '{channel.name}' and {len(episode_ids)} episodes[/green]"
            )

    asyncio.run(_reset())
