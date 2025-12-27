"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import {
  Loader2,
  Search,
  Check,
  X,
  Plus,
  ArrowLeft,
  AlertTriangle,
  Settings,
  Info,
  Cpu,
  Cloud,
  Radio,
  Film,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api";
import type { Provider, EpisodePreview } from "@/lib/types";

type Step = "type" | "url" | "configure";
type ContentType = "channel" | "episode";

function formatDuration(minutes: number): string {
  if (minutes < 1) return "< 1 min";
  if (minutes < 60) return `${Math.round(minutes)} min`;
  const hours = Math.floor(minutes / 60);
  const remainingMins = Math.round(minutes % 60);
  if (remainingMins === 0) return `${hours} hour${hours > 1 ? "s" : ""}`;
  return `${hours}h ${remainingMins}m`;
}

export default function AddPodcastPage() {
  const router = useRouter();
  const [step, setStep] = useState<Step>("type");
  const [contentType, setContentType] = useState<ContentType>("channel");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // URL input
  const [youtubeUrl, setYoutubeUrl] = useState("");

  // Channel data (for channel type)
  const [channelData, setChannelData] = useState<any>(null);
  const [episodes, setEpisodes] = useState<EpisodePreview[]>([]);
  const [searchQuery, setSearchQuery] = useState("");

  // Video data (for single episode type)
  const [videoData, setVideoData] = useState<any>(null);

  // Common config
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selectedProvider, setSelectedProvider] = useState("deepgram");
  const [concurrency, setConcurrency] = useState(20);
  const [speakers, setSpeakers] = useState<string[]>([]);
  const [newSpeaker, setNewSpeaker] = useState("");

  const fetchContent = async () => {
    if (!youtubeUrl.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const providersRes = await api.getProviders();
      setProviders(providersRes.providers);

      // Set default provider
      const availableProviders = providersRes.providers.filter(
        (p: Provider) => p.available
      );
      if (availableProviders.length > 0) {
        setSelectedProvider(availableProviders[0].name);
      } else {
        setSelectedProvider("faster-whisper");
      }

      if (contentType === "channel") {
        const channelRes = await api.fetchChannel(youtubeUrl);
        setChannelData(channelRes);
        setEpisodes(
          channelRes.episodes.map((e: EpisodePreview) => ({
            ...e,
            selected: e.selected !== false,
          }))
        );
      } else {
        const videoRes = await api.fetchVideo(youtubeUrl);
        setVideoData(videoRes);

        // If video already exists, show warning
        if (videoRes.video.already_exists) {
          setError(
            "This episode already exists in your library. You can find it in the Podcasts section."
          );
        }
      }

      setStep("configure");
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to fetch content");
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
    let totalSeconds = 0;
    let episodeCount = 0;

    if (contentType === "channel") {
      const selected = episodes.filter((e) => e.selected);
      totalSeconds = selected.reduce(
        (sum, e) => sum + (e.duration_seconds || 0),
        0
      );
      episodeCount = selected.length;
    } else if (videoData) {
      totalSeconds = videoData.video.duration_seconds || 0;
      episodeCount = 1;
    }

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
      episode_count: episodeCount,
    };
  };

  const startProcessing = async () => {
    setLoading(true);
    setError(null);

    try {
      if (contentType === "channel") {
        const selectedEpisodes = episodes.filter((e) => e.selected);

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

        await api.startBatch(batchRes.id);
        router.push(`/admin/batches/${batchRes.id}`);
      } else {
        // Single episode - create channel if needed, then create batch
        const channelName = videoData.channel.name;
        const channelId = videoData.channel.youtube_channel_id;

        const batchRes = await api.createBatch({
          channel_data: {
            name: channelName,
            youtube_channel_id: channelId,
            youtube_url: `https://www.youtube.com/channel/${channelId}`,
            thumbnail_url: videoData.channel.thumbnail_url,
            description: null,
          },
          episodes_data: [
            {
              youtube_id: videoData.video.youtube_id,
              title: videoData.video.title,
              thumbnail_url: videoData.video.thumbnail_url,
              published_at: videoData.video.published_at,
              duration_seconds: videoData.video.duration_seconds,
            },
          ],
          provider: selectedProvider,
          concurrency: 1,
          speakers,
        });

        await api.startBatch(batchRes.id);
        router.push(`/admin/batches/${batchRes.id}`);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || "Failed to start processing");
      setLoading(false);
    }
  };

  const selectedCount =
    contentType === "channel"
      ? episodes.filter((e) => e.selected).length
      : videoData && !videoData.video.already_exists
      ? 1
      : 0;
  const estimate = calculateEstimate();
  const currentProvider = providers.find((p) => p.name === selectedProvider);

  return (
    <div className="container py-8 max-w-4xl">
      {/* Step 1: Choose Type */}
      {step === "type" && (
        <Card>
          <CardHeader>
            <CardTitle>Add Content</CardTitle>
            <CardDescription>
              Choose what type of content you want to add
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <button
                onClick={() => {
                  setContentType("channel");
                  setStep("url");
                }}
                className="p-6 border rounded-lg hover:border-primary hover:bg-muted/50 transition-colors text-left"
              >
                <Radio className="h-8 w-8 mb-3 text-primary" />
                <h3 className="font-semibold mb-1">YouTube Channel</h3>
                <p className="text-sm text-muted-foreground">
                  Add all episodes from a podcast channel
                </p>
              </button>
              <button
                onClick={() => {
                  setContentType("episode");
                  setStep("url");
                }}
                className="p-6 border rounded-lg hover:border-primary hover:bg-muted/50 transition-colors text-left"
              >
                <Film className="h-8 w-8 mb-3 text-primary" />
                <h3 className="font-semibold mb-1">Single Episode</h3>
                <p className="text-sm text-muted-foreground">
                  Add a single YouTube video as an episode
                </p>
              </button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Step 2: URL Input */}
      {step === "url" && (
        <Card>
          <CardHeader>
            <CardTitle>
              {contentType === "channel" ? "Add YouTube Channel" : "Add Single Episode"}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label>
                {contentType === "channel" ? "YouTube Channel URL" : "YouTube Video URL"}
              </Label>
              <div className="flex gap-2">
                <Input
                  placeholder={
                    contentType === "channel"
                      ? "https://www.youtube.com/@MyFirstMillionPodcast"
                      : "https://www.youtube.com/watch?v=..."
                  }
                  value={youtubeUrl}
                  onChange={(e) => setYoutubeUrl(e.target.value)}
                  disabled={loading}
                />
                <Button onClick={fetchContent} disabled={loading || !youtubeUrl}>
                  {loading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    "Fetch"
                  )}
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                {contentType === "channel"
                  ? "Supports @handle, /channel/, /c/, and /user/ URLs"
                  : "Paste a YouTube video URL (youtube.com/watch?v= or youtu.be/)"}
              </p>
            </div>
            {error && <p className="text-red-500 text-sm">{error}</p>}
            <Button variant="outline" onClick={() => setStep("type")}>
              <ArrowLeft className="h-4 w-4 mr-2" />
              Back
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Step 3: Configure */}
      {step === "configure" && (channelData || videoData) && (
        <div className="space-y-6">
          {/* Content Info */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex items-center gap-4">
                {contentType === "channel" && channelData?.thumbnail_url && (
                  <Image
                    src={channelData.thumbnail_url}
                    alt={channelData.name}
                    width={64}
                    height={64}
                    className="rounded-full"
                  />
                )}
                {contentType === "episode" && videoData?.video?.thumbnail_url && (
                  <Image
                    src={videoData.video.thumbnail_url}
                    alt={videoData.video.title}
                    width={120}
                    height={68}
                    className="rounded"
                  />
                )}
                <div>
                  <h2 className="text-xl font-bold">
                    {contentType === "channel"
                      ? channelData?.name
                      : videoData?.video?.title}
                  </h2>
                  <p className="text-muted-foreground">
                    {contentType === "channel"
                      ? `${channelData?.total_episodes} episodes found`
                      : `From: ${videoData?.channel?.name}`}
                  </p>
                  {contentType === "episode" && videoData?.video?.duration_seconds && (
                    <p className="text-sm text-muted-foreground">
                      Duration: {formatDuration(videoData.video.duration_seconds / 60)}
                    </p>
                  )}
                </div>
              </div>

              {/* Warnings */}
              {contentType === "episode" && videoData?.video?.already_exists && (
                <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg flex items-start gap-2 dark:bg-yellow-950 dark:border-yellow-800">
                  <AlertTriangle className="h-5 w-5 text-yellow-600 shrink-0" />
                  <div className="text-sm">
                    <p className="font-medium text-yellow-800 dark:text-yellow-200">
                      Episode already exists
                    </p>
                    <p className="text-yellow-700 dark:text-yellow-300">
                      This episode is already in your library. You can find it in the
                      Podcasts section.
                    </p>
                  </div>
                </div>
              )}
              {contentType === "episode" && videoData?.channel?.already_exists && (
                <div className="mt-4 p-3 bg-blue-50 border border-blue-200 rounded-lg flex items-start gap-2 dark:bg-blue-950 dark:border-blue-800">
                  <Info className="h-5 w-5 text-blue-600 shrink-0" />
                  <div className="text-sm">
                    <p className="font-medium text-blue-800 dark:text-blue-200">
                      Channel exists
                    </p>
                    <p className="text-blue-700 dark:text-blue-300">
                      This episode will be added to existing channel:{" "}
                      <Link
                        href={`/podcasts/${videoData.channel.existing_channel_slug}`}
                        className="underline"
                      >
                        {videoData.channel.name}
                      </Link>
                    </p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Provider Selection */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Transcription Provider</CardTitle>
                <Link href="/admin/settings">
                  <Button variant="outline" size="sm">
                    <Settings className="h-4 w-4 mr-2" />
                    Configure API Keys
                  </Button>
                </Link>
              </div>
            </CardHeader>
            <CardContent className="space-y-4">
              {/* Provider explanation */}
              <div className="flex gap-4 text-sm p-3 bg-muted/50 rounded-lg">
                <div className="flex items-start gap-2">
                  <Cpu className="h-4 w-4 mt-0.5 text-blue-500" />
                  <div>
                    <span className="font-medium">Local (Faster-Whisper)</span>
                    <p className="text-muted-foreground">
                      Uses your GPU. Free but slower.
                    </p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <Cloud className="h-4 w-4 mt-0.5 text-purple-500" />
                  <div>
                    <span className="font-medium">Cloud (AssemblyAI, Deepgram)</span>
                    <p className="text-muted-foreground">
                      Fast, parallel. Requires API key.
                    </p>
                  </div>
                </div>
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
                      className={`flex items-center justify-between p-4 border rounded-lg ${
                        !provider.available ? "opacity-60 bg-muted/30" : ""
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <RadioGroupItem
                          value={provider.name}
                          id={provider.name}
                          disabled={!provider.available}
                        />
                        <div className="flex items-center gap-2">
                          {isLocal ? (
                            <Cpu className="h-4 w-4 text-blue-500" />
                          ) : (
                            <Cloud className="h-4 w-4 text-purple-500" />
                          )}
                          <div>
                            <Label
                              htmlFor={provider.name}
                              className={`font-medium ${
                                provider.available
                                  ? "cursor-pointer"
                                  : "cursor-not-allowed"
                              }`}
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
                              {provider.note && ` • ${provider.note}`}
                            </p>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {provider.supports_diarization && (
                          <Badge variant="secondary">Speaker Diarization</Badge>
                        )}
                        {!provider.available && (
                          <Badge
                            variant="destructive"
                            className="flex items-center gap-1"
                          >
                            <AlertTriangle className="h-3 w-3" />
                            API Key Missing
                          </Badge>
                        )}
                      </div>
                    </div>
                  );
                })}
              </RadioGroup>

              {contentType === "channel" && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <Label>Concurrent Jobs: {concurrency}</Label>
                    <div className="group relative">
                      <Info className="h-4 w-4 text-muted-foreground cursor-help" />
                      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 px-3 py-2 bg-popover text-popover-foreground text-xs rounded-lg shadow-lg opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-50 border">
                        Number of episodes processed simultaneously.
                        <br />
                        Higher = faster but uses more resources.
                      </div>
                    </div>
                  </div>
                  <Slider
                    value={[concurrency]}
                    onValueChange={(v) => setConcurrency(v[0])}
                    min={1}
                    max={currentProvider?.max_concurrent || 50}
                    step={1}
                  />
                </div>
              )}
            </CardContent>
          </Card>

          {/* Speakers */}
          <Card>
            <CardHeader>
              <CardTitle>Known Speakers (Optional)</CardTitle>
              <CardDescription>
                Add speaker names to improve speaker identification accuracy
              </CardDescription>
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

          {/* Episode Selection (Channel only) */}
          {contentType === "channel" && (
            <Card>
              <CardHeader>
                <CardTitle>Select Episodes</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {/* Quick Select */}
                <div className="flex gap-2 flex-wrap">
                  <Button variant="outline" size="sm" onClick={() => toggleAll(true)}>
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
                    onClick={() => selectLatest(10)}
                  >
                    Latest 10
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => toggleAll(false)}>
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
                        <div onClick={(e) => e.stopPropagation()}>
                          <Checkbox
                            checked={episode.selected}
                            onCheckedChange={() => toggleEpisode(episode.youtube_id)}
                          />
                        </div>
                        {episode.thumbnail_url && (
                          <Image
                            src={episode.thumbnail_url}
                            alt=""
                            width={80}
                            height={45}
                            className="rounded object-cover shrink-0"
                          />
                        )}
                        <div className="flex-1 min-w-0">
                          <p className="font-medium truncate">{episode.title}</p>
                          <p className="text-sm text-muted-foreground">
                            {Math.floor((episode.duration_seconds || 0) / 60)} min
                            {episode.published_at &&
                              ` • ${new Date(
                                episode.published_at
                              ).toLocaleDateString()}`}
                          </p>
                        </div>
                      </div>
                    ))}
                  </ScrollArea>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Cost Estimate */}
          <Card className="bg-blue-50 border-blue-200 dark:bg-blue-950 dark:border-blue-800">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">Estimated Cost & Time</p>
                  <p className="text-sm text-muted-foreground">
                    {estimate?.episode_count || 0} episode
                    {(estimate?.episode_count || 0) !== 1 ? "s" : ""} •{" "}
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
                    ~{formatDuration(estimate?.duration_minutes || 0)} to complete
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
              disabled={
                loading ||
                selectedCount === 0 ||
                (contentType === "episode" && videoData?.video?.already_exists)
              }
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Check className="h-4 w-4 mr-2" />
              )}
              Start Processing{" "}
              {selectedCount > 0 &&
                `${selectedCount} Episode${selectedCount !== 1 ? "s" : ""}`}
            </Button>
          </div>

          {error && <p className="text-red-500 text-center">{error}</p>}
        </div>
      )}
    </div>
  );
}
