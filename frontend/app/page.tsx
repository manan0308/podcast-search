"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import Image from "next/image";
import {
  Search,
  Loader2,
  Mic,
  Sparkles,
  Clock,
  User,
  Zap,
  SearchX,
  Plus,
  MessageSquare,
  ArrowRight,
  FileText,
  Radio,
  BarChart3,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SearchResults, SearchResultSkeleton } from "@/components/search/SearchResults";
import { SearchFilters } from "@/components/search/SearchFilters";
import { api } from "@/lib/api";
import type { SearchResult, SearchFilters as Filters, Channel, Episode } from "@/lib/types";

interface Stats {
  total_channels: number;
  total_episodes: number;
  transcribed_episodes: number;
  total_hours: number;
}

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [filters, setFilters] = useState<Filters>({});
  const [processingTime, setProcessingTime] = useState<number | null>(null);

  // Stats and content
  const [stats, setStats] = useState<Stats | null>(null);
  const [recentChannels, setRecentChannels] = useState<Channel[]>([]);
  const [loadingStats, setLoadingStats] = useState(true);

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    try {
      const [channelsRes, statsRes] = await Promise.all([
        api.getChannels(),
        api.getSearchStats().catch(() => null),
      ]);

      setRecentChannels(channelsRes.channels.slice(0, 4));

      // Calculate stats
      const channels = channelsRes.channels;
      const totalEpisodes = channels.reduce(
        (sum: number, c: Channel) => sum + c.episode_count,
        0
      );
      const transcribed = channels.reduce(
        (sum: number, c: Channel) => sum + c.transcribed_count,
        0
      );
      const totalHours = channels.reduce(
        (sum: number, c: Channel) => sum + c.total_duration_seconds / 3600,
        0
      );

      setStats({
        total_channels: channels.length,
        total_episodes: totalEpisodes,
        transcribed_episodes: transcribed,
        total_hours: Math.round(totalHours),
      });
    } catch (error) {
      console.error("Failed to load stats:", error);
    } finally {
      setLoadingStats(false);
    }
  };

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setSearched(true);

    try {
      const response = await api.search({
        query,
        filters,
        limit: 20,
        include_context: true,
      });
      setResults(response.results);
      setProcessingTime(response.processing_time_ms);
    } catch (error) {
      console.error("Search failed:", error);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const hasContent = stats && stats.transcribed_episodes > 0;
  const isEmpty = !loadingStats && stats && stats.total_channels === 0;

  return (
    <div className="container py-8">
      {/* Loading State */}
      {loadingStats && (
        <div className="flex items-center justify-center py-24">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      )}

      {/* Empty State - Onboarding */}
      {isEmpty && (
        <div className="max-w-2xl mx-auto text-center py-16">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-primary/10 mb-6">
            <Mic className="h-10 w-10 text-primary" />
          </div>
          <h1 className="text-4xl font-bold mb-4">Welcome to Podcast Search</h1>
          <p className="text-lg text-muted-foreground mb-8">
            Search through podcast transcripts with AI-powered semantic search.
            Get started by adding your first podcast channel.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link href="/admin/add">
              <Button size="lg" className="gap-2">
                <Plus className="h-5 w-5" />
                Add Your First Podcast
              </Button>
            </Link>
            <Link href="/admin/settings">
              <Button size="lg" variant="outline" className="gap-2">
                Configure API Keys
              </Button>
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-16">
            <div className="p-6 border rounded-lg text-left">
              <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900 flex items-center justify-center mb-4">
                <Radio className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              </div>
              <h3 className="font-semibold mb-2">1. Add a Channel</h3>
              <p className="text-sm text-muted-foreground">
                Paste a YouTube channel URL to import all episodes automatically
              </p>
            </div>
            <div className="p-6 border rounded-lg text-left">
              <div className="w-10 h-10 rounded-full bg-purple-100 dark:bg-purple-900 flex items-center justify-center mb-4">
                <FileText className="h-5 w-5 text-purple-600 dark:text-purple-400" />
              </div>
              <h3 className="font-semibold mb-2">2. Transcribe</h3>
              <p className="text-sm text-muted-foreground">
                AI transcribes your podcasts with speaker identification
              </p>
            </div>
            <div className="p-6 border rounded-lg text-left">
              <div className="w-10 h-10 rounded-full bg-green-100 dark:bg-green-900 flex items-center justify-center mb-4">
                <Search className="h-5 w-5 text-green-600 dark:text-green-400" />
              </div>
              <h3 className="font-semibold mb-2">3. Search & Chat</h3>
              <p className="text-sm text-muted-foreground">
                Find any moment with semantic search or chat with your podcasts
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Has Content - Search Interface */}
      {!loadingStats && !isEmpty && (
        <>
          {/* Hero Section */}
          <div className="text-center mb-8">
            <div className="inline-flex items-center gap-2 mb-4">
              <Mic className="h-10 w-10 text-primary" />
              <h1 className="text-4xl font-bold tracking-tight">
                Podcast Search
              </h1>
            </div>
            <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
              Search through {stats?.transcribed_episodes || 0} transcribed episodes
              <span className="inline-flex items-center gap-1 ml-1">
                <Sparkles className="h-4 w-4 text-yellow-500" />
              </span>
            </p>
          </div>

          {/* Search Form */}
          <form onSubmit={handleSearch} className="max-w-3xl mx-auto mb-8">
            <div className="flex gap-2">
              <div className="relative flex-1">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="Search for topics, quotes, or ideas..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  className="pl-10 h-12 text-lg"
                />
              </div>
              <Button
                type="submit"
                size="lg"
                disabled={loading || !hasContent}
                className="gap-2"
              >
                {loading ? (
                  <Loader2 className="h-5 w-5 animate-spin" />
                ) : (
                  <>
                    <Search className="h-5 w-5" />
                    Search
                  </>
                )}
              </Button>
            </div>
            {hasContent && <SearchFilters filters={filters} onChange={setFilters} />}
          </form>

          {/* No Transcripts Yet Message */}
          {stats && stats.transcribed_episodes === 0 && stats.total_episodes > 0 && (
            <div className="max-w-2xl mx-auto text-center py-8 mb-8 bg-yellow-50 dark:bg-yellow-950 border border-yellow-200 dark:border-yellow-800 rounded-lg">
              <FileText className="h-8 w-8 text-yellow-600 mx-auto mb-3" />
              <h3 className="font-semibold mb-2">Transcription Required</h3>
              <p className="text-sm text-muted-foreground mb-4">
                You have {stats.total_episodes} episodes but none are transcribed yet.
                Search and chat require transcribed content.
              </p>
              <Link href="/podcasts">
                <Button variant="outline">
                  Go to Podcasts to Start Transcription
                </Button>
              </Link>
            </div>
          )}

          {/* Results */}
          {searched && (
            <div className="max-w-4xl mx-auto">
              {loading ? (
                <div className="space-y-4">
                  <div className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Searching transcripts...
                  </div>
                  {[1, 2, 3].map((i) => (
                    <SearchResultSkeleton key={i} />
                  ))}
                </div>
              ) : results.length > 0 ? (
                <>
                  <div className="flex justify-between items-center mb-4">
                    <p className="text-sm text-muted-foreground flex items-center gap-2">
                      <Zap className="h-4 w-4 text-green-500" />
                      Found {results.length} results
                      {processingTime && ` in ${processingTime}ms`}
                    </p>
                  </div>
                  <SearchResults results={results} query={query} />
                </>
              ) : (
                <div className="text-center py-12">
                  <SearchX className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                  <p className="text-muted-foreground">
                    No results found for "{query}"
                  </p>
                  <p className="text-sm text-muted-foreground mt-2">
                    Try different keywords or adjust your filters
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Initial State - Stats & Quick Actions */}
          {!searched && (
            <div className="max-w-5xl mx-auto">
              {/* Stats Cards */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                <Card>
                  <CardContent className="pt-6">
                    <div className="text-3xl font-bold">{stats?.total_channels || 0}</div>
                    <p className="text-sm text-muted-foreground">Podcasts</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <div className="text-3xl font-bold">{stats?.total_episodes || 0}</div>
                    <p className="text-sm text-muted-foreground">Episodes</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <div className="text-3xl font-bold text-green-600">
                      {stats?.transcribed_episodes || 0}
                    </div>
                    <p className="text-sm text-muted-foreground">Transcribed</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent className="pt-6">
                    <div className="text-3xl font-bold">{stats?.total_hours || 0}h</div>
                    <p className="text-sm text-muted-foreground">Audio</p>
                  </CardContent>
                </Card>
              </div>

              {/* Quick Actions */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
                <Link href="/chat">
                  <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
                    <CardContent className="pt-6 flex items-center gap-4">
                      <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                        <MessageSquare className="h-6 w-6 text-primary" />
                      </div>
                      <div className="flex-1">
                        <h3 className="font-semibold">Chat with Podcasts</h3>
                        <p className="text-sm text-muted-foreground">
                          Ask questions and get answers from your transcripts
                        </p>
                      </div>
                      <ArrowRight className="h-5 w-5 text-muted-foreground" />
                    </CardContent>
                  </Card>
                </Link>
                <Link href="/admin/add">
                  <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
                    <CardContent className="pt-6 flex items-center gap-4">
                      <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                        <Plus className="h-6 w-6 text-primary" />
                      </div>
                      <div className="flex-1">
                        <h3 className="font-semibold">Add Content</h3>
                        <p className="text-sm text-muted-foreground">
                          Add a new podcast channel or single episode
                        </p>
                      </div>
                      <ArrowRight className="h-5 w-5 text-muted-foreground" />
                    </CardContent>
                  </Card>
                </Link>
              </div>

              {/* Recent Podcasts */}
              {recentChannels.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-semibold">Your Podcasts</h2>
                    <Link
                      href="/podcasts"
                      className="text-sm text-primary hover:underline"
                    >
                      View all →
                    </Link>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    {recentChannels.map((channel) => (
                      <Link key={channel.id} href={`/podcasts/${channel.slug}`}>
                        <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
                          <CardContent className="pt-6">
                            <div className="flex items-center gap-3 mb-3">
                              {channel.thumbnail_url ? (
                                <Image
                                  src={channel.thumbnail_url}
                                  alt={channel.name}
                                  width={48}
                                  height={48}
                                  className="rounded-full"
                                />
                              ) : (
                                <div className="w-12 h-12 rounded-full bg-muted flex items-center justify-center">
                                  <Mic className="h-6 w-6 text-muted-foreground" />
                                </div>
                              )}
                              <div className="flex-1 min-w-0">
                                <h3 className="font-semibold truncate">
                                  {channel.name}
                                </h3>
                              </div>
                            </div>
                            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                              <span>{channel.episode_count} episodes</span>
                              <span>•</span>
                              <span className="text-green-600">
                                {channel.transcribed_count} ready
                              </span>
                            </div>
                          </CardContent>
                        </Card>
                      </Link>
                    ))}
                  </div>
                </div>
              )}

              {/* Feature Cards (when no podcasts yet but not completely empty) */}
              {recentChannels.length === 0 && stats && stats.total_channels === 0 === false && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
                  <div className="p-6 border rounded-lg hover:border-primary/50 transition-colors">
                    <Sparkles className="h-8 w-8 text-yellow-500 mx-auto mb-3" />
                    <h3 className="font-semibold mb-2 text-center">Semantic Search</h3>
                    <p className="text-sm text-muted-foreground text-center">
                      Find content by meaning, not just keywords
                    </p>
                  </div>
                  <div className="p-6 border rounded-lg hover:border-primary/50 transition-colors">
                    <User className="h-8 w-8 text-blue-500 mx-auto mb-3" />
                    <h3 className="font-semibold mb-2 text-center">Speaker Filtering</h3>
                    <p className="text-sm text-muted-foreground text-center">
                      Filter by specific hosts or guests
                    </p>
                  </div>
                  <div className="p-6 border rounded-lg hover:border-primary/50 transition-colors">
                    <Clock className="h-8 w-8 text-green-500 mx-auto mb-3" />
                    <h3 className="font-semibold mb-2 text-center">Timestamps</h3>
                    <p className="text-sm text-muted-foreground text-center">
                      Jump directly to the moment
                    </p>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
