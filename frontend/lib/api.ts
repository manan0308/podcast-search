const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const ADMIN_SECRET = process.env.NEXT_PUBLIC_ADMIN_SECRET || "change-me-in-production";

class ApiClient {
  private baseUrl: string;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {},
    requiresAdmin: boolean = false
  ): Promise<T> {
    const url = `${this.baseUrl}/api${endpoint}`;

    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (requiresAdmin) {
      headers["X-Admin-Secret"] = ADMIN_SECRET;
    }

    const response = await fetch(url, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw { response: { data: error, status: response.status } };
    }

    return response.json();
  }

  // Channels
  async getChannels() {
    return this.request<{ channels: any[]; total: number }>("/channels");
  }

  async getChannel(id: string) {
    return this.request<any>(`/channels/${id}`);
  }

  async getChannelBySlug(slug: string) {
    return this.request<any>(`/channels/slug/${slug}`);
  }

  async fetchChannel(youtubeUrl: string) {
    return this.request<any>(
      "/channels/fetch",
      {
        method: "POST",
        body: JSON.stringify({ youtube_url: youtubeUrl }),
      },
      true
    );
  }

  async createChannel(data: {
    name: string;
    youtube_channel_id?: string;
    youtube_url?: string;
    thumbnail_url?: string;
    speakers?: string[];
  }) {
    return this.request<any>(
      "/channels",
      {
        method: "POST",
        body: JSON.stringify(data),
      },
      true
    );
  }

  // Episodes
  async getEpisodes(params: {
    channel_id?: string;
    channel_slug?: string;
    status?: string;
    search?: string;
    page?: number;
    page_size?: number;
  }) {
    const searchParams = new URLSearchParams();
    if (params.channel_id) searchParams.set("channel_id", params.channel_id);
    if (params.channel_slug) searchParams.set("channel_slug", params.channel_slug);
    if (params.status) searchParams.set("status", params.status);
    if (params.search) searchParams.set("search", params.search);
    if (params.page) searchParams.set("page", params.page.toString());
    if (params.page_size) searchParams.set("page_size", params.page_size.toString());

    return this.request<any>(`/episodes?${searchParams.toString()}`);
  }

  async getEpisode(id: string) {
    return this.request<any>(`/episodes/${id}`);
  }

  // Batches
  async getBatches(params: { status?: string; page_size?: number }) {
    const searchParams = new URLSearchParams();
    if (params.status) searchParams.set("status", params.status);
    if (params.page_size) searchParams.set("page_size", params.page_size.toString());

    return this.request<any>(`/batches?${searchParams.toString()}`);
  }

  async getBatch(id: string) {
    return this.request<any>(`/batches/${id}`);
  }

  async createBatch(data: {
    // Option 1: Existing channel and episodes
    channel_id?: string;
    episode_ids?: string[];
    // Option 2: New from YouTube fetch
    channel_data?: {
      name: string;
      youtube_channel_id: string;
      youtube_url?: string;
      thumbnail_url?: string | null;
      description?: string | null;
    };
    episodes_data?: {
      youtube_id: string;
      title: string;
      description?: string | null;
      thumbnail_url?: string | null;
      published_at?: string | null;
      duration_seconds?: number | null;
    }[];
    // Common
    provider: string;
    concurrency: number;
    speakers?: string[];
  }) {
    return this.request<any>(
      "/batches",
      {
        method: "POST",
        body: JSON.stringify(data),
      },
      true
    );
  }

  async startBatch(id: string) {
    return this.request<any>(`/batches/${id}/start`, { method: "POST" }, true);
  }

  async pauseBatch(id: string) {
    return this.request<any>(`/batches/${id}/pause`, { method: "POST" }, true);
  }

  async resumeBatch(id: string) {
    return this.request<any>(`/batches/${id}/resume`, { method: "POST" }, true);
  }

  async cancelBatch(id: string) {
    return this.request<any>(`/batches/${id}/cancel`, { method: "POST" }, true);
  }

  async retryBatch(id: string) {
    return this.request<any>(`/batches/${id}/retry`, { method: "POST" }, true);
  }

  // Jobs
  async retryJob(id: string) {
    return this.request<any>(`/jobs/${id}/retry`, { method: "POST" }, true);
  }

  async pauseJob(id: string) {
    return this.request<any>(`/jobs/${id}/pause`, { method: "POST" }, true);
  }

  async resumeJob(id: string) {
    return this.request<any>(`/jobs/${id}/resume`, { method: "POST" }, true);
  }

  async cancelJob(id: string) {
    return this.request<any>(`/jobs/${id}/cancel`, { method: "POST" }, true);
  }

  // Search
  async search(params: {
    query: string;
    filters?: any;
    limit?: number;
    include_context?: boolean;
  }) {
    return this.request<any>("/search", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  async getSearchStats() {
    return this.request<any>("/search/stats");
  }

  async getSpeakers() {
    return this.request<any>("/search/speakers");
  }

  // Chat
  async chat(params: {
    message: string;
    conversation_id?: string;
    conversation_history?: any[];
    channel_slug?: string;
    filters?: any;
  }) {
    return this.request<any>("/chat", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  // Providers
  async getProviders() {
    return this.request<any>("/providers");
  }

  async estimateCost(params: {
    provider: string;
    duration_seconds: number;
    episode_count: number;
  }) {
    return this.request<any>("/providers/estimate", {
      method: "POST",
      body: JSON.stringify(params),
    });
  }

  // Settings - API Keys
  async getApiKeyStatus() {
    return this.request<any[]>("/settings/api-keys", {}, true);
  }

  async validateApiKey(envVar: string, value: string) {
    return this.request<{ valid: boolean; error?: string }>(
      "/settings/api-keys/validate",
      {
        method: "POST",
        body: JSON.stringify({ env_var: envVar, value }),
      },
      true
    );
  }

  async updateApiKey(envVar: string, value: string) {
    return this.request<any>(
      "/settings/api-keys",
      {
        method: "POST",
        body: JSON.stringify({ env_var: envVar, value }),
      },
      true
    );
  }

  async deleteApiKey(envVar: string) {
    return this.request<any>(
      `/settings/api-keys/${envVar}`,
      { method: "DELETE" },
      true
    );
  }

  // Single Episode - fetch video info
  async fetchVideo(youtubeUrl: string) {
    return this.request<any>(
      "/channels/fetch-video",
      {
        method: "POST",
        body: JSON.stringify({ youtube_url: youtubeUrl }),
      },
      true
    );
  }

  // Transcribe episodes from podcast page
  async transcribeEpisodes(params: {
    channel_id: string;
    episode_ids: string[];
    provider: string;
    concurrency: number;
  }) {
    return this.request<any>(
      "/batches",
      {
        method: "POST",
        body: JSON.stringify(params),
      },
      true
    );
  }
}

export const api = new ApiClient(API_URL);
