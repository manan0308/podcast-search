"""
Main CLI entry point.

Run with: python -m app.cli
"""
import typer
from rich.console import Console

from app.cli.channel import app as channel_app
from app.cli.jobs import app as jobs_app
from app.cli.transcribe import app as transcribe_app
from app.cli.utils import app as utils_app

console = Console()

app = typer.Typer(
    name="podcast-cli",
    help="Podcast Search CLI - Manage transcription and search",
    add_completion=False,
)

# Add sub-commands
app.add_typer(channel_app, name="channel", help="Channel management commands")
app.add_typer(jobs_app, name="jobs", help="Job management commands")
app.add_typer(transcribe_app, name="transcribe", help="Transcription commands")
app.add_typer(utils_app, name="utils", help="Utility commands")


@app.command()
def version():
    """Show version information."""
    console.print("[bold green]Podcast Search CLI[/bold green] v1.0.0")


@app.command()
def status():
    """Show overall system status."""
    import asyncio
    from app.cli.helpers import get_system_status

    asyncio.run(get_system_status())


if __name__ == "__main__":
    app()
