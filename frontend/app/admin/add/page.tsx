"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import {
  Loader2,
  Search,
  Check,
  X,
  Plus,
  ArrowLeft,
  ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api";
import type { Provider, EpisodePreview } from "@/lib/types";

type Step = "url" | "configure";

export default function AddPodcastPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("url");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 1
  const [youtubeUrl, setYoutubeUrl] = useState("");

  // Step 2
  const [channelData, setChannelData] = useState<any>(null);
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selectedProvider, setSelectedProvider] = useState("deepgram");
  const [concurrency, setConcurrency] = useState(20);
  const [speakers, setSpeakers] = useState<string[]>([]);
  const [newSpeaker, setNewSpeaker] = useState("");
  const [episodes, setEpisodes] = useState<EpisodePreview[]>([]);
  const [searchQuery, setSearchQuery] = useState("");

  const fetchChannel = async () => {
    if (!youtubeUrl.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const [channelRes, providersRes] = await Promise.all([
        api.fetchChannel(youtubeUrl),
        api.getProviders(),
      ]);

      setChannelData(channelRes);
      setProviders(providersRes.providers.filter((p: Provider) => p.available));
      setEpisodes(
        channelRes.episodes.map((e: EpisodePreview) => ({
          ...e,
          selected: e.selected !== false,
        }))
      );

      // Set default provider
      const defaultProvider = providersRes.providers.find(
        (p: Provider) => p.available && p.name === "deepgram"
      );
      if (defaultProvider) {
        setSelectedProvider(defaultProvider.name);
      }

      setStep("configure");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to fetch channel");
    } finally {
      setLoading(false);
    }
  };

  const toggleEpisode = (youtubeId: string) => {
    setEpisodes((prev) =>
      prev.map((e) =>
        e.youtube_id === youtubeId ? { ...e, selected: !e.selected } : e
      )
    );
  };

  const toggleAll = (selected: boolean) => {
    const filtered = getFilteredEpisodes();
    const filteredIds = new Set(filtered.map((e) => e.youtube_id));
    setEpisodes((prev) =>
      prev.map((e) =>
        filteredIds.has(e.youtube_id) ? { ...e, selected } : e
      )
    );
  };

  const selectLatest = (count: number) => {
    const sorted = [...episodes].sort(
      (a, b) =>
        new Date(b.published_at || 0).getTime() -
        new Date(a.published_at || 0).getTime()
    );
    const latestIds = new Set(sorted.slice(0, count).map((e) => e.youtube_id));
    setEpisodes((prev) =>
      prev.map((e) => ({
        ...e,
        selected: latestIds.has(e.youtube_id),
      }))
    );
  };

  const getFilteredEpisodes = () => {
    return episodes.filter((e) => {
      if (
        searchQuery &&
        !e.title.toLowerCase().includes(searchQuery.toLowerCase())
      ) {
        return false;
      }
      return true;
    });
  };

  const addSpeaker = () => {
    if (newSpeaker.trim() && !speakers.includes(newSpeaker.trim())) {
      setSpeakers([...speakers, newSpeaker.trim()]);
      setNewSpeaker("");
    }
  };

  const removeSpeaker = (speaker: string) => {
    setSpeakers(speakers.filter((s) => s !== speaker));
  };

  const calculateEstimate = () => {
    const selected = episodes.filter((e) => e.selected);
    const totalSeconds = selected.reduce(
      (sum, e) => sum + (e.duration_seconds || 0),
      0
    );
    const provider = providers.find((p) => p.name === selectedProvider);

    if (!provider) return null;

    const costCents = Math.ceil(
      (totalSeconds / 3600) * provider.cost_per_hour_cents
    );
    const durationMinutes = Math.ceil(totalSeconds / 60 / concurrency);

    return {
      cost_cents: costCents,
      duration_minutes: durationMinutes,
      hours: totalSeconds / 3600,
    };
  };

  const startProcessing = async () => {
    setLoading(true);
    setError(null);

    try {
      const selectedEpisodes = episodes.filter((e) => e.selected);

      // Create batch with channel and episodes data (backend auto-creates)
      const batchRes = await api.createBatch({
        channel_data: {
          name: channelData.name,
          youtube_channel_id: channelData.youtube_channel_id,
          youtube_url: youtubeUrl,
          thumbnail_url: channelData.thumbnail_url,
          description: channelData.description,
        },
        episodes_data: selectedEpisodes.map((e) => ({
          youtube_id: e.youtube_id,
          title: e.title,
          thumbnail_url: e.thumbnail_url,
          published_at: e.published_at,
          duration_seconds: e.duration_seconds,
        })),
        provider: selectedProvider,
        concurrency,
        speakers,
      });

      // Start batch
      await api.startBatch(batchRes.id);

      // Redirect to batch page
      router.push(`/admin/batches/${batchRes.id}`);
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to start processing");
      setLoading(false);
    }
  };

  const selectedCount = episodes.filter((e) => e.selected).length;
  const totalDuration = episodes
    .filter((e) => e.selected)
    .reduce((sum, e) => sum + (e.duration_seconds || 0), 0);
  const estimate = calculateEstimate();
  const currentProvider = providers.find((p) => p.name === selectedProvider);

  return (
    <div className="container py-8 max-w-4xl">
      {/* Step 1: URL */}
      {step === "url" && (
        <Card>
          <CardHeader>
            <CardTitle>Add Podcast Channel</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>YouTube Channel URL</Label>
              <div className="flex gap-2">
                <Input
                  placeholder="https://www.youtube.com/@MyFirstMillionPodcast"
                  value={youtubeUrl}
                  onChange={(e) => setYoutubeUrl(e.target.value)}
                  disabled={loading}
                />
                <Button onClick={fetchChannel} disabled={loading || !youtubeUrl}>
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    "Fetch"
                  )}
                </Button>
              </div>
            </div>
            {error && <p className="text-red-500 text-sm">{error}</p>}
          </CardContent>
        </Card>
      )}

      {/* Step 2: Configure */}
      {step === "configure" && channelData && (
        <div className="space-y-6">
          {/* Channel Info */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                {channelData.thumbnail_url && (
                  <Image
                    src={channelData.thumbnail_url}
                    alt={channelData.name}
                    width={64}
                    height={64}
                    className="rounded-full"
                  />
                )}
                <div>
                  <h2 className="text-xl font-bold">{channelData.name}</h2>
                  <p className="text-muted-foreground">
                    {channelData.total_episodes} episodes found
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Provider Selection */}
          <Card>
            <CardHeader>
              <CardTitle>Transcription Provider</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <RadioGroup
                value={selectedProvider}
                onValueChange={setSelectedProvider}
              >
                {providers.map((provider) => (
                  <div
                    key={provider.name}
                    className="flex items-center justify-between p-4 border rounded-lg"
                  >
                    <div className="flex items-center gap-3">
                      <RadioGroupItem
                        value={provider.name}
                        id={provider.name}
                      />
                      <div>
                        <Label
                          htmlFor={provider.name}
                          className="font-medium cursor-pointer"
                        >
                          {provider.display_name}
                        </Label>
                        <p className="text-sm text-muted-foreground">
                          {provider.cost_per_hour_cents === 0
                            ? "Free"
                            : `$${(provider.cost_per_hour_cents / 100).toFixed(
                                2
                              )}/hour`}
                          {" • "}Up to {provider.max_concurrent} parallel
                        </p>
                      </div>
                    </div>
                    {provider.supports_diarization && (
                      <Badge variant="secondary">Speaker Diarization</Badge>
                    )}
                  </div>
                ))}
              </RadioGroup>

              <div className="space-y-2">
                <Label>Concurrent Jobs: {concurrency}</Label>
                <Slider
                  value={[concurrency]}
                  onValueChange={(v) => setConcurrency(v[0])}
                  min={1}
                  max={currentProvider?.max_concurrent || 50}
                  step={1}
                />
              </div>
            </CardContent>
          </Card>

          {/* Speakers */}
          <Card>
            <CardHeader>
              <CardTitle>Known Speakers</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex flex-wrap gap-2">
                {speakers.map((speaker) => (
                  <Badge key={speaker} variant="outline" className="px-3 py-1">
                    {speaker}
                    <button
                      onClick={() => removeSpeaker(speaker)}
                      className="ml-2 hover:text-red-500"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))}
              </div>
              <div className="flex gap-2">
                <Input
                  placeholder="Add speaker name"
                  value={newSpeaker}
                  onChange={(e) => setNewSpeaker(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && addSpeaker()}
                />
                <Button variant="outline" onClick={addSpeaker}>
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>

          {/* Episode Selection */}
          <Card>
            <CardHeader>
              <CardTitle>Select Episodes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Quick Select */}
              <div className="flex gap-2 flex-wrap">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => toggleAll(true)}
                >
                  All {episodes.length}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => selectLatest(100)}
                >
                  Latest 100
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => selectLatest(50)}
                >
                  Latest 50
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => toggleAll(false)}
                >
                  None
                </Button>
              </div>

              {/* Search */}
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <Input
                  placeholder="Search episodes..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>

              {/* Episode List */}
              <div className="border rounded-lg">
                <div className="sticky top-0 bg-background border-b p-2 flex items-center gap-2">
                  <Checkbox
                    checked={getFilteredEpisodes().every((e) => e.selected)}
                    onCheckedChange={(checked) => toggleAll(!!checked)}
                  />
                  <span className="text-sm text-muted-foreground">
                    {selectedCount} of {episodes.length} selected
                  </span>
                </div>
                <ScrollArea className="h-80">
                  {getFilteredEpisodes().map((episode) => (
                    <div
                      key={episode.youtube_id}
                      className="flex items-center gap-3 p-3 border-b hover:bg-muted/50 cursor-pointer"
                      onClick={() => toggleEpisode(episode.youtube_id)}
                    >
                      <Checkbox
                        checked={episode.selected}
                        onCheckedChange={() => toggleEpisode(episode.youtube_id)}
                      />
                      {episode.thumbnail_url && (
                        <Image
                          src={episode.thumbnail_url}
                          alt=""
                          width={80}
                          height={45}
                          className="rounded object-cover"
                        />
                      )}
                      <div className="flex-1 min-w-0">
                        <p className="font-medium truncate">{episode.title}</p>
                        <p className="text-sm text-muted-foreground">
                          {Math.floor((episode.duration_seconds || 0) / 60)} min
                          {episode.published_at &&
                            ` • ${new Date(episode.published_at).toLocaleDateString()}`}
                        </p>
                      </div>
                    </div>
                  ))}
                </ScrollArea>
              </div>
            </CardContent>
          </Card>

          {/* Cost Estimate */}
          <Card className="bg-blue-50 border-blue-200 dark:bg-blue-950 dark:border-blue-800">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">Estimated Cost & Time</p>
                  <p className="text-sm text-muted-foreground">
                    {selectedCount} episodes •{" "}
                    {Math.round((estimate?.hours || 0) * 10) / 10} hours of audio
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-2xl font-bold">
                    {estimate?.cost_cents === 0
                      ? "Free"
                      : `$${((estimate?.cost_cents || 0) / 100).toFixed(2)}`}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    ~{Math.round((estimate?.duration_minutes || 0) / 60)} hours
                    to complete
                  </p>
                </div>
              </div>
            </CardContent>
          </Card>

          {/* Actions */}
          <div className="flex justify-between">
            <Button variant="outline" onClick={() => setStep("url")}>
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back
            </Button>
            <Button
              onClick={startProcessing}
              disabled={loading || selectedCount === 0}
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Check className="h-4 w-4 mr-2" />
              )}
              Start Processing {selectedCount} Episodes
            </Button>
          </div>

          {error && <p className="text-red-500 text-center">{error}</p>}
        </div>
      )}
    </div>
  );
}
