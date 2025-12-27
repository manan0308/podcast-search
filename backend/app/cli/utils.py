"""
Utility CLI commands.
"""
import asyncio
from pathlib import Path
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from app.cli.helpers import (
    get_channel_by_name_or_id,
    format_datetime,
)
from app.config import settings

console = Console()
app = typer.Typer()


@app.command("cleanup-audio")
def cleanup_audio(
    channel: Optional[str] = typer.Option(None, "--channel", "-c", help="Cleanup specific channel"),
    all_files: bool = typer.Option(False, "--all", "-a", help="Cleanup all audio files"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Show what would be deleted"),
):
    """Clean up downloaded audio files."""
    audio_dir = Path(settings.AUDIO_DIR)

    if not audio_dir.exists():
        console.print("[yellow]Audio directory not found.[/yellow]")
        return

    files = list(audio_dir.glob("*.mp3")) + list(audio_dir.glob("*.m4a")) + list(audio_dir.glob("*.webm"))

    if not files:
        console.print("[green]No audio files to clean up.[/green]")
        return

    total_size = sum(f.stat().st_size for f in files)
    size_mb = total_size / (1024 * 1024)

    console.print(f"\nFound {len(files)} audio files ({size_mb:.1f} MB)")

    if dry_run:
        console.print("\n[yellow]Dry run - files that would be deleted:[/yellow]")
        for f in files[:20]:
            console.print(f"  {f.name}")
        if len(files) > 20:
            console.print(f"  ... and {len(files) - 20} more")
        return

    if not all_files and not Confirm.ask("Delete all audio files?"):
        return

    deleted = 0
    for f in files:
        try:
            f.unlink()
            deleted += 1
        except Exception as e:
            console.print(f"[red]Failed to delete {f.name}: {e}[/red]")

    console.print(f"[green]Deleted {deleted} files ({size_mb:.1f} MB freed)[/green]")


@app.command("cleanup-transcripts")
def cleanup_transcripts(
    channel: Optional[str] = typer.Option(None, "--channel", "-c", help="Cleanup specific channel"),
    duplicates_only: bool = typer.Option(False, "--duplicates", "-d", help="Only remove duplicates"),
):
    """Clean up transcript backup files."""
    transcripts_dir = Path(settings.TRANSCRIPTS_DIR)

    if not transcripts_dir.exists():
        console.print("[yellow]Transcripts directory not found.[/yellow]")
        return

    files = list(transcripts_dir.glob("*.json"))

    if not files:
        console.print("[green]No transcript files found.[/green]")
        return

    console.print(f"Found {len(files)} transcript files")

    if duplicates_only:
        # Find duplicates by youtube_id
        import json
        youtube_ids = {}
        duplicates = []

        for f in files:
            try:
                with open(f) as fp:
                    data = json.load(fp)
                    yt_id = data.get("youtube_id")
                    if yt_id:
                        if yt_id in youtube_ids:
                            duplicates.append(f)
                        else:
                            youtube_ids[yt_id] = f
            except Exception:
                pass

        if duplicates:
            console.print(f"[yellow]Found {len(duplicates)} duplicate transcripts[/yellow]")
            if Confirm.ask("Delete duplicates?"):
                for f in duplicates:
                    f.unlink()
                console.print(f"[green]Deleted {len(duplicates)} duplicates[/green]")
        else:
            console.print("[green]No duplicates found.[/green]")


@app.command("verify-transcripts")
def verify_transcripts(
    channel: Optional[str] = typer.Option(None, "--channel", "-c", help="Verify specific channel"),
):
    """Verify transcript integrity."""
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import Episode, Chunk

    async def _verify():
        ch = None
        if channel:
            ch = await get_channel_by_name_or_id(channel)
            if not ch:
                console.print(f"[red]Channel not found: {channel}[/red]")
                raise typer.Exit(1)

        async with AsyncSessionLocal() as db:
            query = select(Episode).where(Episode.status == "done")
            if ch:
                query = query.where(Episode.channel_id == ch.id)

            result = await db.execute(query)
            episodes = result.scalars().all()

            issues = []
            for ep in episodes:
                # Check if has chunks
                chunk_count = await db.scalar(
                    select(Chunk.id).where(Chunk.episode_id == ep.id).limit(1)
                )
                if not chunk_count:
                    issues.append((ep, "No chunks"))

            if issues:
                console.print(f"\n[red]Found {len(issues)} issues:[/red]")
                for ep, issue in issues[:20]:
                    console.print(f"  {ep.title[:50]}: {issue}")
                if len(issues) > 20:
                    console.print(f"  ... and {len(issues) - 20} more")
            else:
                console.print(f"[green]All {len(episodes)} transcripts verified![/green]")

    asyncio.run(_verify())


@app.command("stats")
def show_stats():
    """Show detailed system statistics."""
    from sqlalchemy import select, func
    from app.database import AsyncSessionLocal
    from app.models import Channel, Episode, Batch, Job, Chunk, Utterance

    async def _stats():
        async with AsyncSessionLocal() as db:
            # Basic counts
            channels = await db.scalar(select(func.count(Channel.id)))
            episodes = await db.scalar(select(func.count(Episode.id)))
            chunks = await db.scalar(select(func.count(Chunk.id)))
            utterances = await db.scalar(select(func.count(Utterance.id)))

            # Episode status
            status_result = await db.execute(
                select(Episode.status, func.count(Episode.id)).group_by(Episode.status)
            )
            episode_status = dict(status_result.all())

            # Job stats
            job_result = await db.execute(
                select(Job.status, func.count(Job.id)).group_by(Job.status)
            )
            job_status = dict(job_result.all())

            # Total duration
            total_duration = await db.scalar(
                select(func.sum(Episode.duration_seconds)).where(Episode.status == "done")
            ) or 0

            # Cost
            total_cost = await db.scalar(select(func.sum(Job.cost_cents))) or 0

        console.print("\n[bold cyan]System Statistics[/bold cyan]\n")

        table = Table(title="Overview")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")

        table.add_row("Channels", str(channels))
        table.add_row("Episodes", str(episodes))
        table.add_row("Chunks", str(chunks))
        table.add_row("Utterances", str(utterances))
        hours = total_duration / 3600
        table.add_row("Total Audio", f"{hours:.1f} hours")
        table.add_row("Total Cost", f"${total_cost/100:.2f}")

        console.print(table)

        # Episode breakdown
        ep_table = Table(title="\nEpisode Status")
        ep_table.add_column("Status", style="cyan")
        ep_table.add_column("Count", justify="right")

        for status, count in sorted(episode_status.items()):
            color = "green" if status == "done" else "yellow" if status == "pending" else "red"
            ep_table.add_row(f"[{color}]{status}[/{color}]", str(count))

        console.print(ep_table)

        # Job breakdown
        if job_status:
            job_table = Table(title="\nJob Status")
            job_table.add_column("Status", style="cyan")
            job_table.add_column("Count", justify="right")

            for status, count in sorted(job_status.items()):
                color = "green" if status == "done" else "yellow" if status == "pending" else "red" if status == "failed" else "blue"
                job_table.add_row(f"[{color}]{status}[/{color}]", str(count))

            console.print(job_table)

    asyncio.run(_stats())


@app.command("export-errors")
def export_errors(
    output: str = typer.Argument("errors.csv", help="Output file path"),
    batch_id: Optional[str] = typer.Option(None, "--batch", "-b", help="Filter by batch"),
):
    """Export failed jobs to CSV."""
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import Job, Episode

    async def _export():
        async with AsyncSessionLocal() as db:
            query = (
                select(Job, Episode)
                .join(Episode)
                .where(Job.status == "failed")
            )

            if batch_id:
                from uuid import UUID
                query = query.where(Job.batch_id == UUID(batch_id))

            result = await db.execute(query)
            rows = result.all()

            if not rows:
                console.print("[green]No failed jobs to export.[/green]")
                return

            import csv
            with open(output, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["job_id", "episode_id", "youtube_id", "title", "error_message", "retry_count"])

                for job, episode in rows:
                    writer.writerow([
                        str(job.id),
                        str(episode.id),
                        episode.youtube_id,
                        episode.title,
                        job.error_message or "",
                        job.retry_count,
                    ])

            console.print(f"[green]Exported {len(rows)} errors to {output}[/green]")

    asyncio.run(_export())


@app.command("reindex")
def reindex_vectors(
    channel: Optional[str] = typer.Option(None, "--channel", "-c", help="Reindex specific channel"),
    force: bool = typer.Option(False, "--force", "-f", help="Force reindex all"),
):
    """Rebuild vector index for search."""
    console.print("[yellow]Vector reindexing not yet implemented.[/yellow]")
    console.print("Use the web admin interface to manage vectors.")
