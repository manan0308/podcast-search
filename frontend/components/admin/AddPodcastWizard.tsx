"use client";

import { useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import {
  Loader2,
  Search,
  CheckCircle,
  ArrowRight,
  ArrowLeft,
  Youtube,
  DollarSign,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { api } from "@/lib/api";
import type { Provider, EpisodePreview, ChannelFetchResponse, CostEstimate } from "@/lib/types";
import { formatDuration } from "@/lib/utils";

type WizardStep = "search" | "episodes" | "provider" | "review";

export function AddPodcastWizard() {
  const router = useRouter();
  const [step, setStep] = useState<WizardStep>("search");
  const [error, setError] = useState<string | null>(null);

  // Search state
  const [channelUrl, setChannelUrl] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [channelData, setChannelData] = useState<ChannelFetchResponse | null>(null);
  const [episodes, setEpisodes] = useState<EpisodePreview[]>([]);

  // Selection state
  const [selectedEpisodes, setSelectedEpisodes] = useState<Set<string>>(new Set());

  // Provider state
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const [concurrency, setConcurrency] = useState(5);

  // Cost state
  const [costEstimate, setCostEstimate] = useState<CostEstimate | null>(null);
  const [isEstimating, setIsEstimating] = useState(false);

  // Submit state
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSearch = async () => {
    if (!channelUrl.trim()) return;

    setIsSearching(true);
    setError(null);
    try {
      // Fetch channel and episodes from YouTube
      const response = await api.fetchChannel(channelUrl);
      setChannelData(response);
      setEpisodes(response.episodes || []);

      // Pre-select all new episodes (not already transcribed)
      setSelectedEpisodes(new Set(
        (response.episodes || [])
          .filter((e: EpisodePreview) => e.selected)
          .map((e: EpisodePreview) => e.youtube_id)
      ));

      // Fetch available providers and filter by availability
      const providersRes = await api.getProviders();
      const availableProviders = (providersRes.providers || []).filter(
        (p: Provider) => p.available
      );
      setProviders(availableProviders);
      if (availableProviders.length > 0) {
        setSelectedProvider(availableProviders[0].name);
      }

      setStep("episodes");
    } catch (err: any) {
      console.error("Failed to fetch channel:", err);
      const message = err?.response?.data?.detail || "Failed to fetch channel. Please check the URL and try again.";
      setError(message);
    } finally {
      setIsSearching(false);
    }
  };

  const toggleEpisode = (youtubeId: string) => {
    const newSelected = new Set(selectedEpisodes);
    if (newSelected.has(youtubeId)) {
      newSelected.delete(youtubeId);
    } else {
      newSelected.add(youtubeId);
    }
    setSelectedEpisodes(newSelected);
  };

  const selectAll = () => {
    setSelectedEpisodes(new Set(episodes.map((e) => e.youtube_id)));
  };

  const selectNone = () => {
    setSelectedEpisodes(new Set());
  };

  const handleEstimateCost = async () => {
    if (selectedEpisodes.size === 0 || !selectedProvider) return;

    setIsEstimating(true);
    try {
      const selectedEps = episodes.filter((e) => selectedEpisodes.has(e.youtube_id));
      const totalDuration = selectedEps.reduce(
        (acc, e) => acc + (e.duration_seconds || 0),
        0
      );

      const estimate = await api.estimateCost({
        provider: selectedProvider,
        duration_seconds: totalDuration,
        episode_count: selectedEps.length,
      });
      setCostEstimate(estimate);
      setStep("review");
    } catch (error) {
      console.error("Failed to estimate cost:", error);
    } finally {
      setIsEstimating(false);
    }
  };

  const handleSubmit = async () => {
    if (!channelData || selectedEpisodes.size === 0 || !selectedProvider) return;

    setIsSubmitting(true);
    setError(null);
    try {
      // Get selected episodes data
      const selectedEps = episodes.filter((e) => selectedEpisodes.has(e.youtube_id));

      // Create batch with channel and episodes data (backend will create them)
      const batch = await api.createBatch({
        channel_data: {
          name: channelData.name,
          youtube_channel_id: channelData.youtube_channel_id,
          thumbnail_url: channelData.thumbnail_url,
          description: channelData.description,
        },
        episodes_data: selectedEps.map((e) => ({
          youtube_id: e.youtube_id,
          title: e.title,
          thumbnail_url: e.thumbnail_url,
          published_at: e.published_at,
          duration_seconds: e.duration_seconds,
        })),
        provider: selectedProvider,
        concurrency,
      });

      // Start processing
      await api.startBatch(batch.id);

      router.push(`/admin/batches/${batch.id}`);
    } catch (err: any) {
      console.error("Failed to create batch:", err);
      const message = err?.response?.data?.detail || "Failed to start processing. Please try again.";
      setError(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectedCount = selectedEpisodes.size;
  const totalDuration = episodes
    .filter((e) => selectedEpisodes.has(e.youtube_id))
    .reduce((acc, e) => acc + (e.duration_seconds || 0), 0);

  return (
    <div className="max-w-4xl mx-auto">
      {/* Progress Steps */}
      <div className="flex items-center justify-center mb-8">
        {(["search", "episodes", "provider", "review"] as WizardStep[]).map(
          (s, i) => (
            <div key={s} className="flex items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium ${
                  step === s
                    ? "bg-primary text-primary-foreground"
                    : i < ["search", "episodes", "provider", "review"].indexOf(step)
                    ? "bg-green-500 text-white"
                    : "bg-muted text-muted-foreground"
                }`}
              >
                {i < ["search", "episodes", "provider", "review"].indexOf(step) ? (
                  <CheckCircle className="h-4 w-4" />
                ) : (
                  i + 1
                )}
              </div>
              {i < 3 && (
                <div
                  className={`w-16 h-0.5 ${
                    i < ["search", "episodes", "provider", "review"].indexOf(step)
                      ? "bg-green-500"
                      : "bg-muted"
                  }`}
                />
              )}
            </div>
          )
        )}
      </div>

      {/* Step Content */}
      {step === "search" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Youtube className="h-5 w-5" />
              Add YouTube Channel
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-muted-foreground">
              Enter a YouTube channel URL to fetch its episodes for transcription.
            </p>
            <div className="flex gap-2">
              <Input
                placeholder="https://www.youtube.com/@channel or channel ID"
                value={channelUrl}
                onChange={(e) => setChannelUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSearch()}
              />
              <Button onClick={handleSearch} disabled={isSearching}>
                {isSearching ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Search className="h-4 w-4" />
                )}
              </Button>
            </div>
            {error && (
              <div className="p-3 rounded-md bg-destructive/10 text-destructive text-sm">
                {error}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {step === "episodes" && channelData && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-4">
              {channelData.thumbnail_url && (
                <Image
                  src={channelData.thumbnail_url}
                  alt={channelData.name}
                  width={60}
                  height={60}
                  className="rounded-lg"
                />
              )}
              <div>
                <CardTitle>{channelData.name}</CardTitle>
                <p className="text-sm text-muted-foreground">
                  {episodes.length} episodes found
                  {channelData.is_new ? "" : " (some may already be transcribed)"}
                </p>
              </div>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Selection Controls */}
            <div className="flex items-center justify-between">
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={selectAll}>
                  Select All
                </Button>
                <Button variant="outline" size="sm" onClick={selectNone}>
                  Select None
                </Button>
              </div>
              <div className="text-sm text-muted-foreground">
                {selectedCount} selected • {formatDuration(totalDuration)} total
              </div>
            </div>

            {/* Episode List */}
            <div className="max-h-96 overflow-y-auto space-y-2">
              {episodes.map((episode) => (
                <div
                  key={episode.youtube_id}
                  className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                    selectedEpisodes.has(episode.youtube_id)
                      ? "bg-primary/5 border-primary"
                      : "hover:bg-muted"
                  }`}
                  onClick={() => toggleEpisode(episode.youtube_id)}
                >
                  <Checkbox
                    checked={selectedEpisodes.has(episode.youtube_id)}
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
                    <p className="font-medium line-clamp-1">{episode.title}</p>
                    <p className="text-xs text-muted-foreground">
                      {episode.duration_seconds
                        ? formatDuration(episode.duration_seconds)
                        : "Unknown duration"}
                    </p>
                  </div>
                  {!episode.selected && (
                    <Badge variant="secondary" className="bg-green-500/10 text-green-500">
                      Transcribed
                    </Badge>
                  )}
                </div>
              ))}
            </div>

            {/* Navigation */}
            <div className="flex justify-between pt-4">
              <Button variant="outline" onClick={() => setStep("search")}>
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back
              </Button>
              <Button
                onClick={() => setStep("provider")}
                disabled={selectedCount === 0}
              >
                Next
                <ArrowRight className="h-4 w-4 ml-2" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === "provider" && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Zap className="h-5 w-5" />
              Choose Transcription Provider
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Provider Selection */}
            <RadioGroup value={selectedProvider} onValueChange={setSelectedProvider}>
              {providers.map((provider) => (
                <div
                  key={provider.name}
                  className={`flex items-start gap-3 p-4 rounded-lg border cursor-pointer transition-colors ${
                    selectedProvider === provider.name
                      ? "bg-primary/5 border-primary"
                      : "hover:bg-muted"
                  }`}
                  onClick={() => setSelectedProvider(provider.name)}
                >
                  <RadioGroupItem value={provider.name} id={provider.name} />
                  <div className="flex-1">
                    <Label htmlFor={provider.name} className="font-medium cursor-pointer">
                      {provider.display_name}
                    </Label>
                    <p className="text-sm text-muted-foreground mt-1">
                      {provider.note || `${provider.display_name} transcription service`}
                    </p>
                    <div className="flex items-center gap-4 mt-2 text-xs">
                      <span className="flex items-center gap-1">
                        <DollarSign className="h-3 w-3" />
                        ${(provider.cost_per_hour_cents / 100).toFixed(2)}/hour
                      </span>
                      <span>Max {provider.max_concurrent} concurrent</span>
                      {provider.supports_diarization && (
                        <Badge variant="outline">Speaker detection</Badge>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </RadioGroup>

            {/* Concurrency Slider */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label>Concurrency</Label>
                <span className="text-sm text-muted-foreground">
                  {concurrency} parallel jobs
                </span>
              </div>
              <Slider
                value={[concurrency]}
                onValueChange={([v]) => setConcurrency(v)}
                min={1}
                max={
                  providers.find((p) => p.name === selectedProvider)?.max_concurrent ||
                  10
                }
                step={1}
              />
              <p className="text-xs text-muted-foreground">
                Higher concurrency processes faster but may hit rate limits.
              </p>
            </div>

            {/* Navigation */}
            <div className="flex justify-between pt-4">
              <Button variant="outline" onClick={() => setStep("episodes")}>
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back
              </Button>
              <Button onClick={handleEstimateCost} disabled={isEstimating}>
                {isEstimating ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <DollarSign className="h-4 w-4 mr-2" />
                )}
                Estimate Cost
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {step === "review" && costEstimate && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <CheckCircle className="h-5 w-5" />
              Review & Start
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Summary */}
            <div className="grid grid-cols-2 gap-4">
              <Card>
                <CardContent className="p-4">
                  <p className="text-sm text-muted-foreground">Episodes</p>
                  <p className="text-2xl font-bold">{selectedCount}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <p className="text-sm text-muted-foreground">Total Duration</p>
                  <p className="text-2xl font-bold">{formatDuration(totalDuration)}</p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <p className="text-sm text-muted-foreground">Provider</p>
                  <p className="text-2xl font-bold">
                    {providers.find((p) => p.name === selectedProvider)?.display_name}
                  </p>
                </CardContent>
              </Card>
              <Card>
                <CardContent className="p-4">
                  <p className="text-sm text-muted-foreground">Estimated Cost</p>
                  <p className="text-2xl font-bold text-green-600">
                    ${costEstimate.total_cost.toFixed(2)}
                  </p>
                </CardContent>
              </Card>
            </div>

            {/* Cost Breakdown */}
            <div className="p-4 bg-muted rounded-lg">
              <h4 className="font-medium mb-2">Cost Breakdown</h4>
              <div className="space-y-1 text-sm">
                <div className="flex justify-between">
                  <span>Transcription</span>
                  <span>${costEstimate.transcription_cost.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span>Speaker Labeling (Claude)</span>
                  <span>${costEstimate.speaker_labeling_cost.toFixed(2)}</span>
                </div>
                <div className="flex justify-between">
                  <span>Embeddings (OpenAI)</span>
                  <span>${costEstimate.embedding_cost.toFixed(2)}</span>
                </div>
                <div className="flex justify-between font-medium pt-2 border-t">
                  <span>Total</span>
                  <span>${costEstimate.total_cost.toFixed(2)}</span>
                </div>
              </div>
            </div>

            {/* Navigation */}
            <div className="flex justify-between pt-4">
              <Button variant="outline" onClick={() => setStep("provider")}>
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back
              </Button>
              <Button onClick={handleSubmit} disabled={isSubmitting}>
                {isSubmitting ? (
                  <Loader2 className="h-4 w-4 animate-spin mr-2" />
                ) : (
                  <Zap className="h-4 w-4 mr-2" />
                )}
                Start Processing
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
