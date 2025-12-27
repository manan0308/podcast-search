"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import Image from "next/image";
import { ArrowLeft, Loader2, ExternalLink, Clock, Calendar } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TranscriptViewer } from "@/components/podcast/TranscriptViewer";
import { api } from "@/lib/api";
import type { EpisodeDetail } from "@/lib/types";

export default function EpisodeDetailPage() {
  const params = useParams();
  const slug = params.slug as string;
  const id = params.id as string;

  const [episode, setEpisode] = useState<EpisodeDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadEpisode();
  }, [id]);

  const loadEpisode = async () => {
    try {
      const response = await api.getEpisode(id);
      setEpisode(response);
    } catch (error) {
      console.error("Failed to load episode:", error);
    } finally {
      setLoading(false);
    }
  };

  const formatDuration = (seconds: number | null) => {
    if (!seconds) return "--";
    const hours = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (hours > 0) {
      return `${hours}h ${mins}m`;
    }
    return `${mins} min`;
  };

  const formatDate = (date: string | null) => {
    if (!date) return "--";
    return new Date(date).toLocaleDateString("en-US", {
      year: "numeric",
      month: "long",
      day: "numeric",
    });
  };

  if (loading) {
    return (
      <div className="container py-12 text-center">
        <Loader2 className="h-8 w-8 animate-spin mx-auto" />
      </div>
    );
  }

  if (!episode) {
    return (
      <div className="container py-12 text-center">
        <p className="text-muted-foreground">Episode not found</p>
      </div>
    );
  }

  return (
    <div className="container py-8">
      {/* Back Link */}
      <Link
        href={`/podcasts/${slug}`}
        className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-6"
      >
        <ArrowLeft className="h-4 w-4 mr-1" />
        Back to {episode.channel_name}
      </Link>

      {/* Episode Header */}
      <div className="flex flex-col md:flex-row gap-6 mb-8">
        {episode.thumbnail_url && (
          <Image
            src={episode.thumbnail_url}
            alt={episode.title}
            width={320}
            height={180}
            className="rounded-lg object-cover"
          />
        )}
        <div className="flex-1">
          <h1 className="text-2xl font-bold mb-4">{episode.title}</h1>

          <div className="flex flex-wrap gap-4 text-sm text-muted-foreground mb-4">
            <span className="flex items-center gap-1">
              <Clock className="h-4 w-4" />
              {formatDuration(episode.duration_seconds)}
            </span>
            <span className="flex items-center gap-1">
              <Calendar className="h-4 w-4" />
              {formatDate(episode.published_at)}
            </span>
            {episode.word_count && (
              <span>{episode.word_count.toLocaleString()} words</span>
            )}
          </div>

          <div className="flex gap-2 mb-4">
            <Badge
              variant={episode.status === "done" ? "default" : "secondary"}
            >
              {episode.status}
            </Badge>
          </div>

          {episode.url && (
            <a
              href={episode.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center text-sm text-primary hover:underline"
            >
              Watch on YouTube
              <ExternalLink className="h-3 w-3 ml-1" />
            </a>
          )}
        </div>
      </div>

      {/* Description */}
      {episode.description && (
        <Card className="mb-8">
          <CardHeader>
            <CardTitle className="text-lg">Description</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground whitespace-pre-wrap line-clamp-6">
              {episode.description}
            </p>
          </CardContent>
        </Card>
      )}

      {/* Transcript */}
      {episode.utterances && episode.utterances.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Transcript</CardTitle>
          </CardHeader>
          <CardContent>
            <TranscriptViewer
              utterances={episode.utterances}
              episodeUrl={episode.url || undefined}
            />
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground">
              {episode.status === "done"
                ? "No transcript available"
                : "Transcript not yet processed"}
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
