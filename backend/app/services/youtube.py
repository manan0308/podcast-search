import asyncio
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
import yt_dlp
from loguru import logger

from app.config import settings


@dataclass
class VideoInfo:
    """YouTube video metadata."""

    youtube_id: str
    title: str
    description: str | None
    url: str
    thumbnail_url: str | None
    published_at: datetime | None
    duration_seconds: int
    channel_id: str | None = None
    channel_name: str | None = None


@dataclass
class ChannelInfo:
    """YouTube channel metadata."""

    channel_id: str
    name: str
    description: str | None
    thumbnail_url: str | None
    url: str
    video_count: int | None = None


class YouTubeService:
    """Service for fetching YouTube channel and video data."""

    def __init__(self, audio_dir: Path | None = None):
        self.audio_dir = audio_dir or Path(settings.AUDIO_DIR)
        self.audio_dir.mkdir(parents=True, exist_ok=True)

    async def get_channel_info(self, channel_url: str) -> ChannelInfo:
        """
        Get channel metadata from URL.

        Args:
            channel_url: YouTube channel URL (various formats supported)

        Returns:
            ChannelInfo with channel metadata
        """
        logger.info(f"Fetching channel info: {channel_url}")

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlist_items": "0",  # Don't fetch videos yet
        }

        loop = asyncio.get_event_loop()

        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(channel_url, download=False)

        info = await loop.run_in_executor(None, extract)

        if not info:
            raise ValueError(f"Could not fetch channel info from {channel_url}")

        return ChannelInfo(
            channel_id=info.get("channel_id") or info.get("id", ""),
            name=info.get("channel")
            or info.get("uploader")
            or info.get("title", "Unknown"),
            description=info.get("description"),
            thumbnail_url=self._get_best_thumbnail(info.get("thumbnails", [])),
            url=info.get("channel_url") or info.get("webpage_url") or channel_url,
            video_count=info.get("playlist_count"),
        )

    async def fetch_channel_episodes(
        self,
        channel_url: str,
        limit: int | None = None,
        skip_shorts: bool = True,
        min_duration_seconds: int = 300,  # 5 minutes
    ) -> list[VideoInfo]:
        """
        Fetch all video metadata from a YouTube channel.

        Args:
            channel_url: YouTube channel URL
            limit: Maximum number of videos to fetch (None for all)
            skip_shorts: Skip videos shorter than min_duration
            min_duration_seconds: Minimum video duration (default 5 min)

        Returns:
            List of VideoInfo objects sorted by published date (newest first)
        """
        # Ensure we use the /videos tab to get actual videos, not nested playlists
        videos_url = self._get_videos_tab_url(channel_url)
        logger.info(f"Fetching episodes from {videos_url} (limit={limit})")

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "ignoreerrors": True,
        }

        if limit:
            ydl_opts["playlist_items"] = f"1:{limit}"

        loop = asyncio.get_event_loop()

        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(videos_url, download=False)

        info = await loop.run_in_executor(None, extract)

        if not info:
            raise ValueError(f"Could not fetch videos from {videos_url}")

        entries = info.get("entries", [])
        videos = []

        for entry in entries:
            if not entry:
                continue

            duration = entry.get("duration") or 0

            # Skip shorts if requested
            if skip_shorts and duration < min_duration_seconds:
                continue

            # Parse published date
            published_at = None
            upload_date = entry.get("upload_date")
            if upload_date:
                try:
                    published_at = datetime.strptime(upload_date, "%Y%m%d")
                except ValueError:
                    pass

            videos.append(
                VideoInfo(
                    youtube_id=entry.get("id", ""),
                    title=entry.get("title", "Untitled"),
                    description=entry.get("description"),
                    url=entry.get("url")
                    or f"https://www.youtube.com/watch?v={entry.get('id')}",
                    thumbnail_url=self._get_best_thumbnail(entry.get("thumbnails", [])),
                    published_at=published_at,
                    duration_seconds=duration,
                    channel_id=info.get("channel_id"),
                    channel_name=info.get("channel") or info.get("uploader"),
                )
            )

        # Sort by published date (newest first)
        videos.sort(key=lambda v: v.published_at or datetime.min, reverse=True)

        logger.info(f"Found {len(videos)} episodes")
        return videos

    async def get_video_info(self, youtube_id: str) -> VideoInfo:
        """
        Get metadata for a single video.

        Args:
            youtube_id: YouTube video ID

        Returns:
            VideoInfo with video metadata
        """
        url = f"https://www.youtube.com/watch?v={youtube_id}"

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
        }

        loop = asyncio.get_event_loop()

        def extract():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)

        info = await loop.run_in_executor(None, extract)

        if not info:
            raise ValueError(f"Could not fetch video info for {youtube_id}")

        published_at = None
        upload_date = info.get("upload_date")
        if upload_date:
            try:
                published_at = datetime.strptime(upload_date, "%Y%m%d")
            except ValueError:
                pass

        return VideoInfo(
            youtube_id=info.get("id", youtube_id),
            title=info.get("title", "Untitled"),
            description=info.get("description"),
            url=info.get("webpage_url") or url,
            thumbnail_url=self._get_best_thumbnail(info.get("thumbnails", [])),
            published_at=published_at,
            duration_seconds=info.get("duration") or 0,
            channel_id=info.get("channel_id"),
            channel_name=info.get("channel") or info.get("uploader"),
        )

    async def download_audio(
        self, youtube_id: str, output_path: Path | None = None
    ) -> Path:
        """
        Download audio from YouTube video.

        Args:
            youtube_id: YouTube video ID
            output_path: Optional output path (uses temp dir if not specified)

        Returns:
            Path to downloaded audio file (mp3)
        """
        if output_path is None:
            output_path = self.audio_dir / f"{youtube_id}.mp3"

        logger.info(f"Downloading audio for {youtube_id}")

        url = f"https://www.youtube.com/watch?v={youtube_id}"

        ydl_opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "outtmpl": str(output_path.with_suffix("")),
            "quiet": True,
            "no_warnings": True,
            # Options to help avoid 403 errors
            "http_headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            },
            "socket_timeout": 60,
            "retries": 5,
            "fragment_retries": 10,
            "ignoreerrors": False,
        }

        loop = asyncio.get_event_loop()

        def download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

        await loop.run_in_executor(None, download)

        # yt-dlp adds the extension
        if not output_path.exists():
            output_path = output_path.with_suffix(".mp3")

        if not output_path.exists():
            raise FileNotFoundError(
                f"Audio file not found after download: {output_path}"
            )

        logger.info(f"Downloaded audio to {output_path}")
        return output_path

    def _get_videos_tab_url(self, channel_url: str) -> str:
        """
        Convert channel URL to videos tab URL.

        Newer yt-dlp returns nested playlists (Videos, Shorts) for channel URLs.
        We need to explicitly request the /videos tab.
        """
        # Remove trailing slash
        url = channel_url.rstrip("/")

        # If already pointing to a specific tab, return as-is
        if any(tab in url for tab in ["/videos", "/shorts", "/streams", "/playlists"]):
            return url

        # Add /videos to get the videos tab
        return f"{url}/videos"

    def _get_best_thumbnail(self, thumbnails: list[dict]) -> str | None:
        """Get highest quality thumbnail URL."""
        if not thumbnails:
            return None

        # Sort by resolution (width * height), prefer higher
        sorted_thumbs = sorted(
            thumbnails,
            key=lambda t: (t.get("width", 0) or 0) * (t.get("height", 0) or 0),
            reverse=True,
        )

        # Prefer medium quality for reasonable file size
        for thumb in sorted_thumbs:
            if thumb.get("id") in ("maxresdefault", "sddefault", "hqdefault"):
                return thumb.get("url")

        return sorted_thumbs[0].get("url") if sorted_thumbs else None

    async def cleanup_audio(self, audio_path: Path) -> None:
        """Delete audio file after processing."""
        try:
            if audio_path.exists():
                audio_path.unlink()
                logger.debug(f"Deleted audio file: {audio_path}")
        except Exception as e:
            logger.warning(f"Failed to delete audio file {audio_path}: {e}")
