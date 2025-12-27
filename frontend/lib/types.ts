// Channel types
export interface Channel {
  id: string;
  slug: string;
  name: string;
  description: string | null;
  youtube_channel_id: string | null;
  youtube_url: string | null;
  thumbnail_url: string | null;
  speakers: string[];
  default_unknown_speaker_label: string;
  episode_count: number;
  transcribed_count: number;
  total_duration_seconds: number;
  created_at: string;
  updated_at: string;
}

// Episode types
export interface Episode {
  id: string;
  channel_id: string;
  youtube_id: string;
  title: string;
  description: string | null;
  url: string | null;
  thumbnail_url: string | null;
  published_at: string | null;
  duration_seconds: number | null;
  status: string;
  progress?: number;
  error_message?: string | null;
  word_count: number | null;
  created_at: string;
  updated_at: string;
  processed_at: string | null;
}

export interface Utterance {
  id: string;
  speaker: string;
  speaker_raw: string | null;
  text: string;
  start_ms: number;
  end_ms: number;
  confidence: number | null;
  timestamp: string;
}

export interface EpisodeDetail extends Episode {
  utterances: Utterance[];
  channel_name: string | null;
  channel_slug: string | null;
}

export interface EpisodePreview {
  id: string;
  youtube_id: string;
  title: string;
  duration_seconds: number | null;
  published_at: string | null;
  thumbnail_url: string | null;
  selected: boolean;
}

// Batch types
export interface Batch {
  id: string;
  channel_id: string | null;
  channel_name: string | null;
  name: string | null;
  provider: string;
  concurrency: number;
  config: Record<string, any>;
  total_episodes: number;
  completed_episodes: number;
  failed_episodes: number;
  estimated_cost_cents: number | null;
  actual_cost_cents: number;
  total_cost: number;
  status: string;
  progress_percent: number;
  started_at: string | null;
  paused_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobSummary {
  id: string;
  episode_id: string;
  episode_title: string;
  status: string;
  progress: number;
  current_step: string | null;
  error_message: string | null;
  cost_cents: number | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface Job {
  id: string;
  batch_id: string | null;
  episode_id: string;
  episode_title: string;
  episode_thumbnail: string | null;
  channel_id: string;
  channel_name: string;
  channel_slug: string;
  provider: string;
  status: string;
  progress: number;
  current_step: string | null;
  error_message: string | null;
  cost: number | null;
  duration_seconds: number | null;
  created_at: string;
  updated_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface BatchDetail extends Batch {
  jobs: JobSummary[];
  channel_name: string | null;
}

// Provider types
export interface Provider {
  name: string;
  display_name: string;
  max_concurrent: number;
  cost_per_hour_cents: number;
  supports_diarization: boolean;
  available: boolean;
  note?: string;
}

// Alias for backward compatibility
export type TranscriptionProvider = Provider;

export interface CostEstimate {
  transcription_cost: number;
  speaker_labeling_cost: number;
  embedding_cost: number;
  total_cost: number;
}

// Search types
export interface SearchFilters {
  speaker?: string;
  channel_id?: string;
  channel_slug?: string;
  date_from?: string;
  date_to?: string;
}

export interface ContextUtterance {
  speaker: string;
  text: string;
  start_ms: number;
  end_ms: number;
}

export interface SearchResult {
  chunk_id: string;
  episode_id: string;
  channel_id: string;
  episode_title: string;
  episode_url: string | null;
  episode_thumbnail: string | null;
  channel_name: string;
  channel_slug: string;
  speaker: string | null;
  speakers: string[];
  text: string;
  timestamp: string;
  timestamp_ms: number;
  published_at: string | null;
  score: number;
  context_before: ContextUtterance[];
  context_after: ContextUtterance[];
}

// Chat types
export interface Citation {
  episode_id: string;
  episode_title: string;
  episode_url: string | null;
  channel_name: string;
  channel_slug: string;
  speaker: string | null;
  text: string;
  timestamp: string;
  timestamp_ms: number;
  published_at: string | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  conversation_id: string;
  search_results_used: number;
  processing_time_ms: number;
}

// API Response types
export interface ChannelListResponse {
  channels: Channel[];
  total: number;
}

export interface EpisodeListResponse {
  episodes: Episode[];
  total: number;
  page: number;
  page_size: number;
}

export interface BatchListResponse {
  batches: Batch[];
  total: number;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  query: string;
  processing_time_ms: number;
}

export interface ChannelFetchResponse {
  channel_id: string | null;
  name: string;
  youtube_channel_id: string;
  thumbnail_url: string | null;
  description: string | null;
  episodes: EpisodePreview[];
  total_episodes: number;
  is_new: boolean;
}
