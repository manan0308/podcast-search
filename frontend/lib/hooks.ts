import useSWR, { SWRConfiguration } from 'swr';
import { api } from './api';

// Default SWR config for better performance
const defaultConfig: SWRConfiguration = {
  revalidateOnFocus: false,
  revalidateIfStale: false,
  dedupingInterval: 60000, // 1 minute deduplication
};

// Fetcher functions
const fetchChannels = () => api.getChannels();
const fetchChannel = (id: string) => api.getChannel(id);
const fetchChannelBySlug = (slug: string) => api.getChannelBySlug(slug);
const fetchEpisodes = (params: Parameters<typeof api.getEpisodes>[0]) => api.getEpisodes(params);
const fetchSearchStats = () => api.getSearchStats();
const fetchSpeakers = () => api.getSpeakers();
const fetchProviders = () => api.getProviders();
const fetchBatches = (params: Parameters<typeof api.getBatches>[0]) => api.getBatches(params);
const fetchBatch = (id: string) => api.getBatch(id);

// Channels hooks
export function useChannels(config?: SWRConfiguration) {
  return useSWR('channels', fetchChannels, { ...defaultConfig, ...config });
}

export function useChannel(id: string | null, config?: SWRConfiguration) {
  return useSWR(id ? `channel-${id}` : null, () => fetchChannel(id!), { ...defaultConfig, ...config });
}

export function useChannelBySlug(slug: string | null, config?: SWRConfiguration) {
  return useSWR(
    slug ? `channel-slug-${slug}` : null,
    () => fetchChannelBySlug(slug!),
    { ...defaultConfig, ...config }
  );
}

// Episodes hooks
export function useEpisodes(
  params: Parameters<typeof api.getEpisodes>[0] | null,
  config?: SWRConfiguration
) {
  const key = params ? `episodes-${JSON.stringify(params)}` : null;
  return useSWR(key, () => fetchEpisodes(params!), { ...defaultConfig, ...config });
}

// Search hooks
export function useSearchStats(config?: SWRConfiguration) {
  return useSWR('search-stats', fetchSearchStats, { ...defaultConfig, ...config });
}

export function useSpeakers(config?: SWRConfiguration) {
  return useSWR('speakers', fetchSpeakers, { ...defaultConfig, ...config });
}

// Providers hook
export function useProviders(config?: SWRConfiguration) {
  return useSWR('providers', fetchProviders, { ...defaultConfig, ...config });
}

// Batches hooks
export function useBatches(
  params: Parameters<typeof api.getBatches>[0],
  config?: SWRConfiguration
) {
  const key = `batches-${JSON.stringify(params)}`;
  return useSWR(key, () => fetchBatches(params), { ...defaultConfig, ...config });
}

export function useBatch(id: string | null, config?: SWRConfiguration) {
  return useSWR(
    id ? `batch-${id}` : null,
    () => fetchBatch(id!),
    { ...defaultConfig, ...config }
  );
}

// Combined data hook for homepage - fetches channels and stats in parallel
export function useHomeData(config?: SWRConfiguration) {
  const { data: channelsData, error: channelsError, isLoading: channelsLoading } = useChannels(config);
  const { data: statsData, error: statsError, isLoading: statsLoading } = useSearchStats(config);

  return {
    channels: channelsData?.channels || [],
    stats: statsData,
    isLoading: channelsLoading || statsLoading,
    error: channelsError || statsError,
  };
}

// Combined data hook for chat page
export function useChatData(channelSlug: string | null, config?: SWRConfiguration) {
  const { data: channelsData, error: channelsError, isLoading: channelsLoading } = useChannels(config);
  const { data: episodesData, error: episodesError, isLoading: episodesLoading } = useEpisodes(
    channelSlug ? { channel_slug: channelSlug, status: 'done' } : null,
    config
  );

  return {
    channels: channelsData?.channels || [],
    episodes: episodesData?.episodes || [],
    isLoading: channelsLoading || episodesLoading,
    error: channelsError || episodesError,
  };
}

// Combined data hook for podcast page
export function usePodcastData(slug: string, config?: SWRConfiguration) {
  const { data: channel, error: channelError, isLoading: channelLoading, mutate: mutateChannel } = useChannelBySlug(slug, config);
  const { data: episodesData, error: episodesError, isLoading: episodesLoading, mutate: mutateEpisodes } = useEpisodes(
    slug ? { channel_slug: slug, page_size: 100 } : null,
    config
  );
  const { data: providersData, error: providersError, isLoading: providersLoading } = useProviders(config);

  return {
    channel,
    episodes: episodesData?.episodes || [],
    providers: providersData?.providers || [],
    isLoading: channelLoading || episodesLoading,
    providersLoading,
    error: channelError || episodesError || providersError,
    mutateChannel,
    mutateEpisodes,
  };
}
