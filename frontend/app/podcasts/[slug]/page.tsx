"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Image from "next/image";
import Link from "next/link";
import { Loader2, Search, Clock, CheckCircle, XCircle, AlertCircle, Plus } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import type { Channel, Episode } from "@/lib/types";

export default function PodcastDetailPage() {
  const params = useParams();
  const slug = params.slug as string;

  const [channel, setChannel] = useState<Channel | null>(null);
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);

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
      case "queued":
        return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
      default:
        return <AlertCircle className="h-4 w-4 text-gray-400" />;
    }
  };

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
          <Image
            src={channel.thumbnail_url}
            alt={channel.name}
            width={120}
            height={120}
            className="rounded-lg"
          />
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
            <span>{Math.floor(channel.total_duration_seconds / 3600)} hours</span>
            <Link href={`/admin/add?channel=${channel.youtube_url || ""}`}>
              <Button size="sm" variant="outline">
                <Plus className="h-4 w-4 mr-1" />
                Add Episodes
              </Button>
            </Link>
          </div>
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
    </div>
  );
}
