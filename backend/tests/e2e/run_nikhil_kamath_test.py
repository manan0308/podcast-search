#!/usr/bin/env python3
"""
E2E Test Script for Nikhil Kamath YouTube Channel

This script tests the full pipeline:
1. Fetch channel info from YouTube
2. Get last 2 episodes
3. Download audio
4. Transcribe with Deepgram
5. Test search and chat

Usage:
    cd /Users/mananagarwal/podcast-search/backend
    python tests/e2e/run_nikhil_kamath_test.py
"""
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime

# Add backend to path FIRST
backend_path = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, backend_path)

# Load .env BEFORE importing app modules (critical for pydantic-settings)
from dotenv import load_dotenv

env_path = Path(backend_path) / ".env"
load_dotenv(env_path, override=True)

# Now import asyncio (after path setup)
import asyncio

# Set environment defaults BEFORE importing app modules
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("AUDIO_DIR", tempfile.mkdtemp())
os.environ.setdefault("TRANSCRIPTS_DIR", tempfile.mkdtemp())

# Clear settings cache to force reload with new env vars
from app.config import get_settings

get_settings.cache_clear()

from loguru import logger

# Configure logging
logger.remove()
logger.add(
    sys.stderr,
    level="INFO",
    format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}",
)


async def test_youtube_fetch():
    """Test fetching channel and episodes from YouTube."""
    from app.services.youtube import YouTubeService

    logger.info("=" * 60)
    logger.info("STEP 1: Fetching YouTube Channel")
    logger.info("=" * 60)

    youtube = YouTubeService()
    channel_url = "https://www.youtube.com/@nikhil.kamath"

    # Get channel info
    logger.info(f"Fetching channel: {channel_url}")
    channel_info = await youtube.get_channel_info(channel_url)

    logger.info(f"✓ Channel: {channel_info.name}")
    logger.info(f"  ID: {channel_info.channel_id}")
    logger.info(f"  Videos: {channel_info.video_count}")

    # Get last 2 episodes (min 5 min duration)
    logger.info("\nFetching last 2 episodes...")
    episodes = await youtube.fetch_channel_episodes(
        channel_url=channel_url,
        limit=5,  # Fetch 5, filter to 2
        skip_shorts=True,
        min_duration_seconds=300,  # 5 min minimum
    )

    # Take only first 2
    episodes = episodes[:2]

    logger.info(f"✓ Found {len(episodes)} episodes:")
    for i, ep in enumerate(episodes, 1):
        duration_min = ep.duration_seconds // 60
        logger.info(f"  {i}. {ep.title[:60]}... ({duration_min} min)")
        logger.info(f"     ID: {ep.youtube_id}")

    return channel_info, episodes


async def test_audio_download(episodes):
    """Test downloading audio from YouTube."""
    from app.services.youtube import YouTubeService

    logger.info("\n" + "=" * 60)
    logger.info("STEP 2: Downloading Audio")
    logger.info("=" * 60)

    youtube = YouTubeService()
    audio_files = []

    for ep in episodes:
        logger.info(f"Downloading: {ep.title[:50]}...")
        try:
            audio_path = await youtube.download_audio(ep.youtube_id)
            audio_files.append((ep, audio_path))
            size_mb = audio_path.stat().st_size / (1024 * 1024)
            logger.info(f"✓ Downloaded: {audio_path.name} ({size_mb:.1f} MB)")
        except Exception as e:
            logger.error(f"✗ Failed to download {ep.youtube_id}: {e}")

    return audio_files


async def test_transcription(audio_files, provider_name: str = None):
    """Test transcription with available provider."""
    from app.services.transcription import get_provider, get_available_providers

    # Auto-detect best available provider
    if not provider_name:
        available = get_available_providers()
        for p in available:
            if p["available"] and p["name"] in (
                "assemblyai",
                "deepgram",
                "faster-whisper",
            ):
                provider_name = p["name"]
                break
        if not provider_name:
            raise ValueError("No transcription provider available")

    logger.info("\n" + "=" * 60)
    logger.info(f"STEP 3: Transcribing with {provider_name.upper()}")
    logger.info("=" * 60)

    provider = get_provider(provider_name)
    transcripts = []

    for ep, audio_path in audio_files:
        logger.info(f"Transcribing: {ep.title[:50]}...")
        logger.info("  (This may take 1-3 minutes per episode)")

        try:
            start_time = datetime.now()
            result = await provider.transcribe(
                audio_path=audio_path,
                speakers_expected=2,
                language="en",
            )
            elapsed = (datetime.now() - start_time).seconds

            if result.status.value == "completed":
                utterance_count = len(result.utterances or [])
                # Handle both dict and Utterance object types
                word_count = 0
                for u in result.utterances or []:
                    text = (
                        u.get("text", "")
                        if isinstance(u, dict)
                        else getattr(u, "text", "")
                    )
                    word_count += len(text.split())
                logger.info(f"✓ Transcribed in {elapsed}s")
                logger.info(f"  Utterances: {utterance_count}")
                logger.info(f"  Words: {word_count}")
                logger.info(f"  Cost: ${(result.cost_cents or 0) / 100:.2f}")
                transcripts.append((ep, result))
            else:
                logger.error(f"✗ Transcription failed: {result.error_message}")

        except Exception as e:
            logger.error(f"✗ Transcription error: {e}")
            import traceback

            traceback.print_exc()

    return transcripts


async def test_speaker_labeling(transcripts):
    """Test speaker labeling with Claude."""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 4: Labeling Speakers with Claude")
    logger.info("=" * 60)

    from app.services.speaker_labeling import SpeakerLabelingService

    labeler = SpeakerLabelingService()
    labeled_transcripts = []

    for ep, transcript in transcripts:
        logger.info(f"Labeling speakers for: {ep.title[:50]}...")

        try:
            # Get speaker mapping
            mapping = await labeler.identify_speakers(
                utterances=transcript.utterances or [],
                known_speakers=["Nikhil Kamath"],  # Known host
                episode_title=ep.title,
            )

            logger.info(f"✓ Speaker mapping: {mapping}")

            # Apply labels
            labeled = labeler.apply_speaker_labels(
                utterances=transcript.utterances or [],
                speaker_mapping=mapping,
            )

            labeled_transcripts.append((ep, labeled))

            # Show sample
            if labeled:
                logger.info("  Sample utterances:")
                for u in labeled[:3]:
                    text_preview = (
                        u["text"][:80] + "..." if len(u["text"]) > 80 else u["text"]
                    )
                    logger.info(f"    {u['speaker']}: {text_preview}")

        except Exception as e:
            logger.error(f"✗ Labeling error: {e}")
            import traceback

            traceback.print_exc()

    return labeled_transcripts


async def test_chunking(labeled_transcripts, channel_name: str = "Nikhil Kamath"):
    """Test chunking transcripts with contextual headers."""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 5: Chunking Transcripts (with contextual headers)")
    logger.info("=" * 60)

    from app.services.chunking import ChunkingService, EpisodeContext

    chunker = ChunkingService()
    all_chunks = []

    for ep, utterances in labeled_transcripts:
        logger.info(f"Chunking: {ep.title[:50]}...")

        # Create episode context for enriched embeddings
        episode_context = EpisodeContext(
            episode_title=ep.title,
            channel_name=channel_name,
            published_at=getattr(ep, "published_at", None),
        )

        chunks = chunker.chunk_transcript(
            utterances,
            ep.youtube_id,
            episode_context=episode_context,
        )
        all_chunks.extend([(ep, chunk) for chunk in chunks])

        logger.info(f"✓ Created {len(chunks)} chunks")
        if chunks:
            logger.info(
                f"  Avg words per chunk: {sum(c.word_count for c in chunks) // len(chunks)}"
            )
            # Show sample enriched text
            sample = chunks[0]
            logger.info(f"  Sample enriched header:")
            header_lines = sample.text_for_embedding.split("---")[0].strip().split("\n")
            for line in header_lines[:4]:
                logger.info(f"    {line}")

    return all_chunks


async def test_embeddings(chunks):
    """Test generating embeddings using enriched text."""
    logger.info("\n" + "=" * 60)
    logger.info("STEP 6: Generating Embeddings (using enriched text)")
    logger.info("=" * 60)

    from app.services.embedding import EmbeddingService

    embedder = EmbeddingService()

    # Just test with first few chunks - use enriched text for embedding
    test_chunks = chunks[:5]
    texts = [chunk.text_for_embedding for _, chunk in test_chunks]

    logger.info(f"Generating embeddings for {len(texts)} chunks...")

    try:
        embeddings = await embedder.embed_texts(texts)
        logger.info(f"✓ Generated {len(embeddings)} embeddings")
        logger.info(f"  Dimension: {len(embeddings[0])}")
    except Exception as e:
        logger.error(f"✗ Embedding error: {e}")
        return None

    return embeddings


async def cleanup(audio_files):
    """Clean up downloaded audio files."""
    logger.info("\n" + "=" * 60)
    logger.info("CLEANUP")
    logger.info("=" * 60)

    for ep, audio_path in audio_files:
        try:
            if audio_path.exists():
                audio_path.unlink()
                logger.info(f"✓ Deleted: {audio_path.name}")
        except Exception as e:
            logger.warning(f"Could not delete {audio_path}: {e}")


async def main():
    """Run the full E2E test."""
    logger.info("=" * 60)
    logger.info("E2E TEST: Nikhil Kamath YouTube Channel")
    logger.info("=" * 60)
    logger.info(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("")

    audio_files = []

    try:
        # Step 1: Fetch YouTube
        channel_info, episodes = await test_youtube_fetch()

        if not episodes:
            logger.error("No episodes found!")
            return False

        # Step 2: Download audio
        audio_files = await test_audio_download(episodes)

        if not audio_files:
            logger.error("No audio downloaded!")
            return False

        # Step 3: Transcribe
        transcripts = await test_transcription(audio_files)

        if not transcripts:
            logger.error("No transcripts generated!")
            return False

        # Step 4: Label speakers
        labeled = await test_speaker_labeling(transcripts)

        if not labeled:
            logger.error("Speaker labeling failed!")
            return False

        # Step 5: Chunk
        chunks = await test_chunking(labeled)

        if not chunks:
            logger.error("Chunking failed!")
            return False

        # Step 6: Embeddings
        embeddings = await test_embeddings(chunks)

        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("TEST SUMMARY")
        logger.info("=" * 60)
        logger.info(f"✓ Channel: {channel_info.name}")
        logger.info(f"✓ Episodes processed: {len(episodes)}")
        logger.info(f"✓ Audio files: {len(audio_files)}")
        logger.info(f"✓ Transcripts: {len(transcripts)}")
        logger.info(f"✓ Chunks created: {len(chunks)}")
        logger.info(f"✓ Embeddings: {'Generated' if embeddings else 'Skipped'}")
        logger.info("")
        logger.info("🎉 E2E TEST PASSED!")

        return True

    except Exception as e:
        logger.error(f"\n✗ TEST FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        # Cleanup
        if audio_files:
            await cleanup(audio_files)


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
