import uuid
import json
import asyncio
from pathlib import Path
from datetime import datetime
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Episode, Channel, Utterance, Chunk, Job, ActivityLog
from app.services.youtube import YouTubeService
from app.services.transcription import get_provider, TranscriptionStatus
from app.services.speaker_labeling import SpeakerLabelingService
from app.services.chunking import ChunkingService
from app.services.embedding import EmbeddingService
from app.services.vector_store import VectorStoreService
from app.services.websocket_manager import publish_job_update, publish_batch_update


class TranscriptionPipeline:
    """
    Full transcription pipeline for a single episode.

    Steps:
    1. Download audio from YouTube
    2. Transcribe with selected provider
    3. Label speakers using Claude
    4. Save utterances to database
    5. Chunk transcript
    6. Generate embeddings
    7. Store in Qdrant
    8. Update episode status
    """

    def __init__(
        self,
        db: AsyncSession,
        provider_name: str = "deepgram",
        speakers: list[str] | None = None,
    ):
        self.db = db
        self.provider_name = provider_name
        self.provider = get_provider(provider_name)
        self.speakers = speakers or []

        self.youtube = YouTubeService()
        self.speaker_labeling = SpeakerLabelingService()
        self.chunking = ChunkingService()
        self.embedding = EmbeddingService()
        self.vector_store = VectorStoreService()

    async def process_episode(
        self,
        job_id: uuid.UUID,
        episode_id: uuid.UUID,
    ) -> bool:
        """
        Process a single episode through the full pipeline.

        Args:
            job_id: The job ID for tracking
            episode_id: The episode to process

        Returns:
            True if successful, False otherwise
        """
        # Get episode and job
        episode = await self._get_episode(episode_id)
        job = await self._get_job(job_id)

        if not episode or not job:
            logger.error(f"Episode or job not found: {episode_id}, {job_id}")
            return False

        # Get channel for speaker config
        channel = await self._get_channel(episode.channel_id)

        try:
            # Update job status
            await self._update_job(job, status="downloading", progress=5, step="Downloading audio")

            # Step 1: Download audio
            audio_path = await self._download_audio(episode)
            await self._log(job, "info", f"Downloaded audio to {audio_path}")

            # Update job status
            await self._update_job(job, status="transcribing", progress=20, step="Transcribing")

            # Step 2: Transcribe
            transcript = await self._transcribe(audio_path, job)
            await self._log(job, "info", f"Transcription complete: {len(transcript.utterances or [])} utterances")
            # Checkpoint commit after transcription (expensive operation) to save progress
            await self.db.commit()

            # Step 3: Speaker labeling
            await self._update_job(job, status="labeling", progress=50, step="Identifying speakers")

            speakers = self.speakers or (channel.speakers if channel else [])
            labeled_utterances = await self._label_speakers(
                transcript.utterances or [],
                speakers,
                episode.title,
            )
            await self._log(job, "info", f"Speaker labeling complete")

            # Step 4: Save utterances
            await self._save_utterances(episode, labeled_utterances)
            await self._log(job, "info", f"Saved {len(labeled_utterances)} utterances")
            # Checkpoint commit after saving utterances (before expensive embedding)
            await self.db.commit()

            # Step 5: Chunking (with contextual headers for better embeddings)
            await self._update_job(job, status="chunking", progress=65, step="Creating chunks")

            from app.services.chunking import EpisodeContext
            episode_context = EpisodeContext(
                episode_title=episode.title,
                channel_name=channel.name if channel else "Unknown",
                published_at=episode.published_at,
            )
            chunks = self.chunking.chunk_transcript(
                labeled_utterances,
                str(episode.id),
                episode_context=episode_context,
            )
            await self._log(job, "info", f"Created {len(chunks)} chunks with contextual headers")

            # Step 6: Embedding
            await self._update_job(job, status="embedding", progress=80, step="Generating embeddings")

            chunk_data = await self._embed_and_store(episode, channel, chunks)
            await self._log(job, "info", f"Stored {len(chunk_data)} vectors")

            # Step 7: Cleanup
            await self.youtube.cleanup_audio(audio_path)

            # Step 8: Save transcript backup
            await self._save_transcript_backup(episode, transcript, labeled_utterances)

            # Step 9: Update episode status
            episode.status = "done"
            episode.processed_at = datetime.utcnow()
            episode.word_count = sum(len(u.get("text", "").split()) for u in labeled_utterances)
            episode.transcript_raw = transcript.raw_response

            # Update channel stats
            if channel:
                channel.transcribed_count += 1

            # Update job
            await self._update_job(
                job,
                status="done",
                progress=100,
                step="Complete",
                cost_cents=transcript.cost_cents,
            )
            job.completed_at = datetime.utcnow()

            await self.db.commit()

            logger.info(f"Successfully processed episode: {episode.title}")
            return True

        except Exception as e:
            logger.error(f"Pipeline failed for episode {episode_id}: {e}")

            # Cleanup audio file on failure to prevent disk exhaustion
            try:
                if 'audio_path' in locals() and audio_path:
                    await self.youtube.cleanup_audio(audio_path)
                    logger.info(f"Cleaned up audio file after failure: {audio_path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup audio file: {cleanup_error}")

            # Update job status
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()

            # Update episode status
            episode.status = "failed"

            await self.db.commit()
            await self._log(job, "error", f"Pipeline failed: {str(e)}")

            return False

    async def _get_episode(self, episode_id: uuid.UUID) -> Episode | None:
        result = await self.db.execute(
            select(Episode).where(Episode.id == episode_id)
        )
        return result.scalar_one_or_none()

    async def _get_job(self, job_id: uuid.UUID) -> Job | None:
        result = await self.db.execute(
            select(Job).where(Job.id == job_id)
        )
        return result.scalar_one_or_none()

    async def _get_channel(self, channel_id: uuid.UUID) -> Channel | None:
        result = await self.db.execute(
            select(Channel).where(Channel.id == channel_id)
        )
        return result.scalar_one_or_none()

    async def _update_job(
        self,
        job: Job,
        status: str | None = None,
        progress: int | None = None,
        step: str | None = None,
        cost_cents: int | None = None,
        commit: bool = False,
    ):
        if status:
            job.status = status
        if progress is not None:
            job.progress = progress
        if step:
            job.current_step = step
        if cost_cents is not None:
            job.cost_cents = cost_cents

        if status == "downloading" and not job.started_at:
            job.started_at = datetime.utcnow()

        # Only commit if explicitly requested to reduce transaction overhead
        if commit:
            await self.db.commit()

        # Publish WebSocket update (fire and forget)
        try:
            await publish_job_update(
                job_id=str(job.id),
                batch_id=str(job.batch_id) if job.batch_id else None,
                episode_id=str(job.episode_id),
                status=job.status,
                progress=job.progress,
                current_step=job.current_step or "",
                error_message=job.error_message,
            )
        except Exception as e:
            logger.warning(f"Failed to publish job update: {e}")

    async def _log(self, job: Job, level: str, message: str, metadata: dict = None, commit: bool = False):
        log = ActivityLog(
            batch_id=job.batch_id,
            job_id=job.id,
            episode_id=job.episode_id,
            level=level,
            message=message,
            metadata=metadata or {},
        )
        self.db.add(log)
        # Only commit if explicitly requested to reduce transaction overhead
        if commit:
            await self.db.commit()

    async def _download_audio(self, episode: Episode) -> Path:
        audio_path = await self.youtube.download_audio(episode.youtube_id)
        return audio_path

    async def _transcribe(self, audio_path: Path, job: Job):
        # Submit and wait for transcription
        result = await self.provider.transcribe(
            audio_path,
            speakers_expected=2,
            language="en",
        )

        if result.status == TranscriptionStatus.FAILED:
            raise Exception(f"Transcription failed: {result.error_message}")

        # Update job with provider job ID (don't commit - let main pipeline commit)
        job.provider_job_id = result.provider_job_id

        return result

    async def _label_speakers(
        self,
        utterances: list,
        known_speakers: list[str],
        episode_title: str,
    ) -> list[dict]:
        if not utterances:
            return []

        # Get speaker mapping
        mapping = await self.speaker_labeling.identify_speakers(
            utterances=utterances,
            known_speakers=known_speakers,
            episode_title=episode_title,
        )

        # Apply labels
        labeled = self.speaker_labeling.apply_speaker_labels(
            utterances=utterances,
            speaker_mapping=mapping,
        )

        return labeled

    async def _save_utterances(self, episode: Episode, utterances: list[dict], commit: bool = False):
        # Delete existing utterances
        from sqlalchemy import delete
        await self.db.execute(
            delete(Utterance).where(Utterance.episode_id == episode.id)
        )

        # Save new utterances
        for utt in utterances:
            db_utterance = Utterance(
                episode_id=episode.id,
                speaker=utt["speaker"],
                speaker_raw=utt.get("speaker_raw"),
                text=utt["text"],
                start_ms=utt["start_ms"],
                end_ms=utt["end_ms"],
                confidence=utt.get("confidence"),
                word_count=len(utt["text"].split()),
            )
            self.db.add(db_utterance)

        # Only commit if explicitly requested
        if commit:
            await self.db.commit()

    async def _embed_and_store(
        self,
        episode: Episode,
        channel: Channel | None,
        chunks: list,
    ) -> list[dict]:
        if not chunks:
            return []

        # Generate embeddings using enriched text with contextual headers
        # This improves retrieval by embedding the full context (episode/speaker/channel)
        # Use parallel embedding for faster processing
        texts = [c.text_for_embedding for c in chunks]
        embeddings = await self.embedding.embed_texts_parallel(texts, max_concurrent=5)

        # Prepare chunk data for Qdrant
        chunk_data = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = uuid.uuid4()

            chunk_dict = {
                "chunk_id": str(chunk_id),
                "episode_id": str(episode.id),
                "channel_id": str(episode.channel_id),
                "text": chunk.text,
                "primary_speaker": chunk.primary_speaker,
                "speakers": chunk.speakers,
                "start_ms": chunk.start_ms,
                "end_ms": chunk.end_ms,
                "chunk_index": chunk.chunk_index,
                "word_count": chunk.word_count,
                "episode_title": episode.title,
                "channel_name": channel.name if channel else "",
                "channel_slug": channel.slug if channel else "",
                "published_at": episode.published_at,
            }
            chunk_data.append(chunk_dict)

        # Store in Qdrant
        point_ids = await self.vector_store.upsert_chunks(chunk_data, embeddings)

        # Save chunks to database
        from sqlalchemy import delete
        await self.db.execute(
            delete(Chunk).where(Chunk.episode_id == episode.id)
        )

        for chunk_dict, point_id in zip(chunk_data, point_ids):
            db_chunk = Chunk(
                episode_id=episode.id,
                qdrant_point_id=uuid.UUID(point_id),
                text=chunk_dict["text"],
                primary_speaker=chunk_dict["primary_speaker"],
                speakers=chunk_dict["speakers"],
                start_ms=chunk_dict["start_ms"],
                end_ms=chunk_dict["end_ms"],
                chunk_index=chunk_dict["chunk_index"],
                word_count=chunk_dict["word_count"],
            )
            self.db.add(db_chunk)

        # Don't commit here - let the main pipeline commit at the end
        return chunk_data

    async def _save_transcript_backup(
        self,
        episode: Episode,
        transcript,
        labeled_utterances: list[dict],
    ):
        """Save transcript as JSON backup."""
        transcripts_dir = Path(settings.TRANSCRIPTS_DIR)
        transcripts_dir.mkdir(parents=True, exist_ok=True)

        backup_data = {
            "episode_id": str(episode.id),
            "youtube_id": episode.youtube_id,
            "title": episode.title,
            "processed_at": datetime.utcnow().isoformat(),
            "provider": self.provider_name,
            "utterances": labeled_utterances,
            "raw_response": transcript.raw_response,
        }

        backup_path = transcripts_dir / f"{episode.youtube_id}.json"
        with open(backup_path, "w") as f:
            json.dump(backup_data, f, indent=2, default=str)

        logger.debug(f"Saved transcript backup to {backup_path}")
