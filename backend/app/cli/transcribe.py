"""
Transcription CLI commands.
"""

import asyncio
from typing import Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm

from app.cli.helpers import (
    get_channel_by_name_or_id,
    create_progress,
)

console = Console()
app = typer.Typer()


@app.command("providers")
def list_providers():
    """List available transcription providers."""
    from app.services.transcription import get_available_providers

    providers = get_available_providers()

    table = Table(title="Transcription Providers")
    table.add_column("Name", style="cyan")
    table.add_column("Display Name")
    table.add_column("Cost/hr", justify="right")
    table.add_column("Concurrent", justify="right")
    table.add_column("Available", justify="center")
    table.add_column("Note", style="dim")

    for p in providers:
        available = "[green]Yes[/green]" if p["available"] else "[red]No[/red]"
        cost = (
            f"${p['cost_per_hour_cents']/100:.2f}"
            if p["cost_per_hour_cents"] > 0
            else "FREE"
        )
        table.add_row(
            p["name"],
            p["display_name"],
            cost,
            str(p["max_concurrent"]),
            available,
            p.get("note", ""),
        )

    console.print(table)


@app.command("batch")
def create_batch(
    channel: str = typer.Argument(..., help="Channel name, slug, or ID"),
    provider: str = typer.Option(
        "modal-hybrid", "--provider", "-p", help="Transcription provider"
    ),
    concurrency: int = typer.Option(10, "--concurrency", "-c", help="Concurrent jobs"),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Max episodes to process"
    ),
    start: bool = typer.Option(
        True, "--start/--no-start", help="Start batch immediately"
    ),
):
    """Create a transcription batch for a channel."""
    from uuid import uuid4
    from datetime import datetime
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import Channel, Episode, Batch, Job

    async def _batch():
        ch = await get_channel_by_name_or_id(channel)
        if not ch:
            console.print(f"[red]Channel not found: {channel}[/red]")
            raise typer.Exit(1)

        async with AsyncSessionLocal() as db:
            # Get pending episodes
            query = (
                select(Episode)
                .where(Episode.channel_id == ch.id)
                .where(Episode.status == "pending")
                .order_by(Episode.published_at.desc())
            )
            if limit:
                query = query.limit(limit)

            result = await db.execute(query)
            episodes = result.scalars().all()

            if not episodes:
                console.print(
                    f"[yellow]No pending episodes found for '{ch.name}'[/yellow]"
                )
                return

            console.print(f"\nChannel: [bold]{ch.name}[/bold]")
            console.print(f"Episodes to process: [bold]{len(episodes)}[/bold]")
            console.print(f"Provider: [bold]{provider}[/bold]")

            # Estimate cost
            total_duration = sum(e.duration_seconds or 0 for e in episodes)
            hours = total_duration / 3600
            from app.services.transcription import get_provider

            try:
                prov = get_provider(provider)
                cost_estimate = hours * prov.cost_per_hour_cents / 100
                console.print(f"Estimated cost: [bold]${cost_estimate:.2f}[/bold]")
            except Exception:
                pass

            if not Confirm.ask("\nCreate batch?"):
                raise typer.Exit(0)

            # Create batch
            batch = Batch(
                id=uuid4(),
                channel_id=ch.id,
                name=f"{ch.name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                provider=provider,
                concurrency=concurrency,
                total_episodes=len(episodes),
                status="pending",
                config={"speakers": ch.speakers or []},
            )
            db.add(batch)

            # Create jobs
            for episode in episodes:
                job = Job(
                    id=uuid4(),
                    batch_id=batch.id,
                    episode_id=episode.id,
                    provider=provider,
                    status="pending",
                )
                db.add(job)
                episode.status = "queued"

            await db.commit()

            console.print(f"\n[green]Created batch {batch.id}[/green]")
            console.print(f"Jobs: {len(episodes)}")

            if start:
                # Start the batch
                from app.tasks.transcription import process_batch_task

                process_batch_task.delay(str(batch.id))
                console.print("[green]Batch started![/green]")
            else:
                console.print(
                    "[yellow]Batch created but not started. Use 'jobs start' to begin.[/yellow]"
                )

    asyncio.run(_batch())


@app.command("hybrid")
def hybrid_transcribe(
    channel: str = typer.Argument(..., help="Channel name, slug, or ID"),
    limit: Optional[int] = typer.Option(
        None, "--limit", "-l", help="Max episodes to process"
    ),
    download_workers: int = typer.Option(
        10, "--download-workers", "-d", help="Parallel downloads"
    ),
):
    """
    Run hybrid transcription: download locally, transcribe on Modal.

    This is the fastest way to transcribe a channel:
    1. Downloads audio locally (bypasses YouTube cloud IP blocks)
    2. Uploads to Modal for parallel GPU transcription
    3. Processes results back to database
    """
    from uuid import uuid4
    from pathlib import Path
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models import Episode, Batch, Job
    from app.services.youtube import YouTubeService
    from app.services.transcription.modal_hybrid import ModalHybridProvider

    async def _hybrid():
        ch = await get_channel_by_name_or_id(channel)
        if not ch:
            console.print(f"[red]Channel not found: {channel}[/red]")
            raise typer.Exit(1)

        async with AsyncSessionLocal() as db:
            # Get pending episodes
            query = (
                select(Episode)
                .where(Episode.channel_id == ch.id)
                .where(Episode.status == "pending")
                .order_by(Episode.published_at.desc())
            )
            if limit:
                query = query.limit(limit)

            result = await db.execute(query)
            episodes = list(result.scalars().all())

            if not episodes:
                console.print(f"[yellow]No pending episodes for '{ch.name}'[/yellow]")
                return

        console.print(f"\n[bold]Hybrid Transcription: {ch.name}[/bold]")
        console.print(f"Episodes: {len(episodes)}")

        youtube = YouTubeService()
        audio_dir = Path(youtube.audio_dir)
        audio_dir.mkdir(parents=True, exist_ok=True)

        # Step 1: Download all audio locally
        console.print("\n[bold cyan]Step 1: Downloading audio locally...[/bold cyan]")

        audio_files = {}
        failed_downloads = []

        with create_progress() as progress:
            task = progress.add_task("Downloading...", total=len(episodes))

            def download_one(episode):
                try:
                    audio_path = asyncio.run(youtube.download_audio(episode.youtube_id))
                    return (episode, audio_path, None)
                except Exception as e:
                    return (episode, None, str(e))

            with ThreadPoolExecutor(max_workers=download_workers) as executor:
                for episode, audio_path, error in executor.map(download_one, episodes):
                    progress.advance(task)
                    if audio_path:
                        audio_files[episode.id] = audio_path
                    else:
                        failed_downloads.append((episode, error))

        console.print(f"Downloaded: {len(audio_files)}")
        if failed_downloads:
            console.print(f"[red]Failed: {len(failed_downloads)}[/red]")

        if not audio_files:
            console.print("[red]No audio files downloaded, aborting.[/red]")
            raise typer.Exit(1)

        # Step 2: Transcribe on Modal
        console.print("\n[bold cyan]Step 2: Transcribing on Modal cloud...[/bold cyan]")

        provider = ModalHybridProvider()
        audio_paths = list(audio_files.values())
        episode_map = {str(path): ep_id for ep_id, path in audio_files.items()}

        def on_progress(completed, total, message):
            console.print(f"  {message}")

        results = await provider.transcribe_batch(
            audio_paths,
            language="en",
            on_progress=on_progress,
        )

        # Step 3: Save results
        console.print("\n[bold cyan]Step 3: Saving results...[/bold cyan]")

        async with AsyncSessionLocal() as db:
            success = 0
            for path, result in zip(audio_paths, results):
                episode_id = episode_map.get(str(path))
                if not episode_id:
                    continue

                episode_result = await db.execute(
                    select(Episode).where(Episode.id == episode_id)
                )
                episode = episode_result.scalar_one_or_none()
                if not episode:
                    continue

                if result.status.value == "completed":
                    episode.status = "done"
                    episode.processed_at = datetime.utcnow()
                    success += 1
                else:
                    episode.status = "failed"

            await db.commit()

        console.print(f"\n[bold green]Complete![/bold green]")
        console.print(f"  Transcribed: {success}")
        console.print(f"  Failed: {len(results) - success}")

        # Cleanup audio files
        console.print("\n[dim]Cleaning up audio files...[/dim]")
        for path in audio_files.values():
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass

    asyncio.run(_hybrid())


@app.command("single")
def transcribe_single(
    youtube_id: str = typer.Argument(..., help="YouTube video ID or URL"),
    provider: str = typer.Option("faster-whisper", "--provider", "-p", help="Provider"),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Output file path"
    ),
):
    """Transcribe a single YouTube video."""
    from pathlib import Path
    from app.services.youtube import YouTubeService
    from app.services.transcription import get_provider

    # Extract video ID from URL if needed
    if "youtube.com" in youtube_id or "youtu.be" in youtube_id:
        import re

        match = re.search(r"(?:v=|/)([a-zA-Z0-9_-]{11})", youtube_id)
        if match:
            youtube_id = match.group(1)

    async def _transcribe():
        youtube = YouTubeService()
        prov = get_provider(provider)

        console.print(f"\n[bold]Transcribing: {youtube_id}[/bold]")
        console.print(f"Provider: {provider}")

        with create_progress() as progress:
            task = progress.add_task("Downloading audio...", total=None)

            # Download
            audio_path = await youtube.download_audio(youtube_id)
            progress.update(task, description="Transcribing...")

            # Transcribe
            result = await prov.transcribe(audio_path)

            progress.update(task, completed=True)

        if result.status.value == "failed":
            console.print(f"[red]Transcription failed: {result.error_message}[/red]")
            raise typer.Exit(1)

        console.print(f"\n[green]Transcription complete![/green]")
        console.print(f"Duration: {result.duration_ms / 1000:.0f}s")
        console.print(f"Utterances: {len(result.utterances or [])}")

        # Output
        if output:
            with open(output, "w") as f:
                f.write(result.full_text or "")
            console.print(f"Saved to: {output}")
        else:
            console.print("\n[bold]Transcript:[/bold]")
            console.print(result.full_text or "")

        # Cleanup
        Path(audio_path).unlink(missing_ok=True)

    asyncio.run(_transcribe())
