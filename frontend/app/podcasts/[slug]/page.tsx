"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import {
  Loader2,
  Search,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Plus,
  Play,
  RotateCcw,
  Settings,
  Cpu,
  Cloud,
} from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import type { Channel, Episode, Provider } from "@/lib/types";

export default function PodcastDetailPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params.slug as string;

  const [channel, setChannel] = useState<Channel | null>(null);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

  // Transcription dialog state
  const [showTranscribeDialog, setShowTranscribeDialog] = useState(false);
  const [selectedEpisodes, setSelectedEpisodes] = useState<Set<string>>(new Set());
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selectedProvider, setSelectedProvider] = useState("deepgram");
  const [concurrency, setConcurrency] = useState(10);
  const [transcribing, setTranscribing] = useState(false);

  useEffect(() => {
    loadChannel();
  }, [slug]);

  useEffect(() => {
    if (channel) {
      loadEpisodes();
    }
  }, [channel, search, statusFilter, page]);

  const loadChannel = async () => {
    try {
      const response = await api.getChannelBySlug(slug);
      setChannel(response);
    } catch (error) {
      console.error("Failed to load channel:", error);
    }
  };

  const loadEpisodes = async () => {
    if (!channel) return;

    try {
      const response = await api.getEpisodes({
        channel_slug: slug,
        status: statusFilter !== "all" ? statusFilter : undefined,
        search: search || undefined,
        page,
        page_size: 20,
      });
      setEpisodes(response.episodes);
      setTotal(response.total);
    } catch (error) {
      console.error("Failed to load episodes:", error);
    } finally {
      setLoading(false);
    }
  };

  const loadProviders = async () => {
    try {
      const response = await api.getProviders();
      setProviders(response.providers);
      const available = response.providers.filter((p: Provider) => p.available);
      if (available.length > 0) {
        setSelectedProvider(available[0].name);
      }
    } catch (error) {
      console.error("Failed to load providers:", error);
    }
  };

  const openTranscribeDialog = () => {
    // Pre-select all pending/queued/failed episodes
    const toTranscribe = episodes.filter((e) =>
      ["pending", "queued", "failed"].includes(e.status)
    );
    setSelectedEpisodes(new Set(toTranscribe.map((e) => e.id)));
    loadProviders();
    setShowTranscribeDialog(true);
  };

  const toggleEpisodeSelection = (episodeId: string) => {
    const newSet = new Set(selectedEpisodes);
    if (newSet.has(episodeId)) {
      newSet.delete(episodeId);
    } else {
      newSet.add(episodeId);
    }
    setSelectedEpisodes(newSet);
  };

  const selectAllPending = () => {
    const pending = episodes.filter((e) =>
      ["pending", "queued", "failed"].includes(e.status)
    );
    setSelectedEpisodes(new Set(pending.map((e) => e.id)));
  };

  const startTranscription = async () => {
    if (selectedEpisodes.size === 0 || !channel) return;

    setTranscribing(true);
    try {
      const batchRes = await api.transcribeEpisodes({
        channel_id: channel.id,
        episode_ids: Array.from(selectedEpisodes),
        provider: selectedProvider,
        concurrency,
      });

      await api.startBatch(batchRes.id);
      setShowTranscribeDialog(false);
      router.push(`/admin/batches/${batchRes.id}`);
    } catch (error) {
      console.error("Failed to start transcription:", error);
    } finally {
      setTranscribing(false);
    }
  };

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return "--";
    const mins = Math.floor(seconds / 60);
    if (mins < 60) return `${mins} min`;
    const hours = Math.floor(mins / 60);
    const remainingMins = mins % 60;
    return `${hours}h ${remainingMins}m`;
  };

  const formatDate = (date: string | null) => {
    if (!date) return "--";
    return new Date(date).toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "done":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "failed":
        return <XCircle className="h-4 w-4 text-red-500" />;
      case "processing":
      case "transcribing":
      case "downloading":
      case "embedding":
        return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
      case "queued":
        return <Clock className="h-4 w-4 text-orange-500" />;
      default:
        return <AlertCircle className="h-4 w-4 text-gray-400" />;
    }
  };

  const pendingCount = episodes.filter((e) =>
    ["pending", "queued", "failed"].includes(e.status)
  ).length;

  const currentProvider = providers.find((p) => p.name === selectedProvider);

  if (loading && !channel) {
    return (
      <div className="container py-12 text-center">
        <Loader2 className="h-8 w-8 animate-spin mx-auto" />
      </div>
    );
  }

  if (!channel) {
    return (
      <div className="container py-12 text-center">
        <p className="text-muted-foreground">Podcast not found</p>
      </div>
    );
  }

  return (
    <div className="container py-8">
      {/* Channel Header */}
      <div className="flex items-start gap-6 mb-8">
        {channel.thumbnail_url && (
          <div className="relative w-[120px] h-[120px] shrink-0">
            <Image
              src={channel.thumbnail_url}
              alt={channel.name}
              fill
              className="rounded-lg object-cover"
            />
          </div>
        )}
        <div className="flex-1">
          <h1 className="text-3xl font-bold mb-2">{channel.name}</h1>
          {channel.description && (
            <p className="text-muted-foreground mb-4 line-clamp-2">
              {channel.description}
            </p>
          )}
          <div className="flex flex-wrap gap-2 mb-4">
            {channel.speakers.map((speaker) => (
              <Badge key={speaker} variant="secondary">
                {speaker}
              </Badge>
            ))}
          </div>
          <div className="flex items-center gap-4 text-sm text-muted-foreground">
            <span>{channel.episode_count} episodes</span>
            <span>{channel.transcribed_count} transcribed</span>
            <span>
              {Math.floor(channel.total_duration_seconds / 3600)} hours
            </span>
          </div>
        </div>
        <div className="flex gap-2">
          {pendingCount > 0 && (
            <Button onClick={openTranscribeDialog}>
              <Play className="h-4 w-4 mr-2" />
              Transcribe ({pendingCount})
            </Button>
          )}
          <Link href={`/admin/add?channel=${channel.youtube_url || ""}`}>
            <Button size="sm" variant="outline">
              <Plus className="h-4 w-4 mr-1" />
              Add Episodes
            </Button>
          </Link>
        </div>
      </div>

      {/* Filters */}
      <div className="flex gap-4 mb-6">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search episodes..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            className="pl-9"
          />
        </div>
        <Select
          value={statusFilter}
          onValueChange={(value) => {
            setStatusFilter(value);
            setPage(1);
          }}
        >
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All</SelectItem>
            <SelectItem value="done">Transcribed</SelectItem>
            <SelectItem value="pending">Pending</SelectItem>
            <SelectItem value="queued">Queued</SelectItem>
            <SelectItem value="processing">Processing</SelectItem>
            <SelectItem value="failed">Failed</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Episodes List */}
      <div className="space-y-4">
        {episodes.map((episode) => (
          <Link
            key={episode.id}
            href={`/podcasts/${slug}/episodes/${episode.id}`}
          >
            <Card className="hover:shadow-md transition-shadow cursor-pointer">
              <CardContent className="flex items-center gap-4 py-4">
                {episode.thumbnail_url && (
                  <Image
                    src={episode.thumbnail_url}
                    alt={episode.title}
                    width={120}
                    height={68}
                    className="rounded object-cover"
                  />
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    {getStatusIcon(episode.status)}
                    <h3 className="font-semibold truncate">{episode.title}</h3>
                  </div>
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1">
                      <Clock className="h-3 w-3" />
                      {formatDuration(episode.duration_seconds)}
                    </span>
                    <span>{formatDate(episode.published_at)}</span>
                    {episode.word_count && (
                      <span>{episode.word_count.toLocaleString()} words</span>
                    )}
                  </div>
                </div>
                <Badge
                  variant={episode.status === "done" ? "default" : "secondary"}
                >
                  {episode.status}
                </Badge>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {/* Empty State */}
      {episodes.length === 0 && !loading && (
        <div className="text-center py-12">
          <AlertCircle className="h-12 w-12 mx-auto mb-4 text-muted-foreground" />
          <p className="text-muted-foreground">No episodes found</p>
        </div>
      )}

      {/* Pagination */}
      {total > 20 && (
        <div className="flex justify-center gap-2 mt-8">
          <Button
            variant="outline"
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </Button>
          <span className="flex items-center px-4 text-sm text-muted-foreground">
            Page {page} of {Math.ceil(total / 20)}
          </span>
          <Button
            variant="outline"
            disabled={page >= Math.ceil(total / 20)}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}

      {/* Transcription Dialog */}
      <Dialog open={showTranscribeDialog} onOpenChange={setShowTranscribeDialog}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Start Transcription</DialogTitle>
            <DialogDescription>
              Select episodes to transcribe and configure transcription settings.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-6 py-4">
            {/* Episode Selection */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <Label>Episodes to Transcribe</Label>
                <Button variant="ghost" size="sm" onClick={selectAllPending}>
                  Select All Pending
                </Button>
              </div>
              <div className="border rounded-lg max-h-48 overflow-y-auto">
                {episodes
                  .filter((e) => ["pending", "queued", "failed"].includes(e.status))
                  .map((episode) => (
                    <div
                      key={episode.id}
                      className="flex items-center gap-3 p-3 border-b last:border-b-0 hover:bg-muted/50"
                    >
                      <Checkbox
                        checked={selectedEpisodes.has(episode.id)}
                        onCheckedChange={() => toggleEpisodeSelection(episode.id)}
                      />
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium truncate">
                          {episode.title}
                        </p>
                        <p className="text-xs text-muted-foreground">
                          {formatDuration(episode.duration_seconds)} •{" "}
                          <span
                            className={
                              episode.status === "failed"
                                ? "text-red-500"
                                : ""
                            }
                          >
                            {episode.status}
                          </span>
                        </p>
                      </div>
                    </div>
                  ))}
                {episodes.filter((e) =>
                  ["pending", "queued", "failed"].includes(e.status)
                ).length === 0 && (
                  <p className="p-4 text-sm text-muted-foreground text-center">
                    No pending episodes to transcribe
                  </p>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-2">
                {selectedEpisodes.size} episode(s) selected
              </p>
            </div>

            {/* Provider Selection */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <Label>Transcription Provider</Label>
                <Link href="/admin/settings">
                  <Button variant="ghost" size="sm">
                    <Settings className="h-3 w-3 mr-1" />
                    Configure
                  </Button>
                </Link>
              </div>
              <RadioGroup
                value={selectedProvider}
                onValueChange={(value) => {
                  const provider = providers.find((p) => p.name === value);
                  if (provider?.available) {
                    setSelectedProvider(value);
                  }
                }}
              >
                {providers.map((provider) => {
                  const isLocal = ["faster-whisper", "whisper"].includes(
                    provider.name
                  );
                  return (
                    <div
                      key={provider.name}
                      className={`flex items-center justify-between p-3 border rounded-lg ${
                        !provider.available ? "opacity-50" : ""
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <RadioGroupItem
                          value={provider.name}
                          id={`dialog-${provider.name}`}
                          disabled={!provider.available}
                        />
                        <div className="flex items-center gap-2">
                          {isLocal ? (
                            <Cpu className="h-4 w-4 text-blue-500" />
                          ) : (
                            <Cloud className="h-4 w-4 text-purple-500" />
                          )}
                          <Label
                            htmlFor={`dialog-${provider.name}`}
                            className="text-sm"
                          >
                            {provider.display_name}
                          </Label>
                        </div>
                      </div>
                      <span className="text-xs text-muted-foreground">
                        {provider.cost_per_hour_cents === 0
                          ? "Free"
                          : `$${(provider.cost_per_hour_cents / 100).toFixed(2)}/hr`}
                      </span>
                    </div>
                  );
                })}
              </RadioGroup>
            </div>

            {/* Concurrency */}
            <div>
              <Label>Concurrent Jobs: {concurrency}</Label>
              <Slider
                value={[concurrency]}
                onValueChange={(v) => setConcurrency(v[0])}
                min={1}
                max={currentProvider?.max_concurrent || 20}
                step={1}
                className="mt-2"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setShowTranscribeDialog(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={startTranscription}
              disabled={selectedEpisodes.size === 0 || transcribing}
            >
              {transcribing ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Play className="h-4 w-4 mr-2" />
              )}
              Start Transcription
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
