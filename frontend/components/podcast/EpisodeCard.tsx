"use client";

import Image from "next/image";
import Link from "next/link";
import { Clock, Calendar, ExternalLink, CheckCircle, XCircle, Loader2, Circle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { Episode } from "@/lib/types";
import { formatDate, formatDuration } from "@/lib/utils";

interface EpisodeCardProps {
  episode: Episode;
  channelSlug: string;
}

const statusConfig = {
  pending: {
    icon: Circle,
    color: "text-muted-foreground",
    bg: "bg-muted",
    label: "Pending",
  },
  processing: {
    icon: Loader2,
    color: "text-blue-500",
    bg: "bg-blue-500/10",
    label: "Processing",
  },
  completed: {
    icon: CheckCircle,
    color: "text-green-500",
    bg: "bg-green-500/10",
    label: "Completed",
  },
  failed: {
    icon: XCircle,
    color: "text-red-500",
    bg: "bg-red-500/10",
    label: "Failed",
  },
};

export function EpisodeCard({ episode, channelSlug }: EpisodeCardProps) {
  const status = statusConfig[episode.status as keyof typeof statusConfig] || statusConfig.pending;
  const StatusIcon = status.icon;

  return (
    <Link href={`/podcasts/${channelSlug}/episodes/${episode.id}`}>
      <Card className="hover:shadow-md transition-shadow h-full">
        <CardContent className="p-0">
          <div className="flex">
            {/* Thumbnail */}
            {episode.thumbnail_url ? (
              <div className="relative shrink-0 w-40 aspect-video">
                <Image
                  src={episode.thumbnail_url}
                  alt=""
                  fill
                  className="rounded-l-lg object-cover"
                />
                {episode.duration_seconds && (
                  <span className="absolute bottom-1 right-1 bg-black/80 text-white text-xs px-1 rounded">
                    {formatDuration(episode.duration_seconds)}
                  </span>
                )}
              </div>
            ) : (
              <div className="w-40 aspect-video bg-muted rounded-l-lg flex items-center justify-center shrink-0">
                <span className="text-muted-foreground text-xs">No thumbnail</span>
              </div>
            )}

            {/* Content */}
            <div className="flex-1 p-4 min-w-0">
              <div className="flex items-start justify-between gap-2 mb-2">
                <h3 className="font-semibold line-clamp-2">{episode.title}</h3>
                <Badge
                  variant="secondary"
                  className={`shrink-0 ${status.bg} ${status.color}`}
                >
                  <StatusIcon
                    className={`h-3 w-3 mr-1 ${
                      episode.status === "processing" ? "animate-spin" : ""
                    }`}
                  />
                  {status.label}
                </Badge>
              </div>

              {/* Description */}
              {episode.description && (
                <p className="text-sm text-muted-foreground line-clamp-2 mb-2">
                  {episode.description}
                </p>
              )}

              {/* Meta */}
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                {episode.published_at && (
                  <span className="flex items-center gap-1">
                    <Calendar className="h-3 w-3" />
                    {formatDate(episode.published_at)}
                  </span>
                )}
                {episode.url && (
                  <a
                    href={episode.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center gap-1 hover:text-foreground"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <ExternalLink className="h-3 w-3" />
                    YouTube
                  </a>
                )}
              </div>

              {/* Progress */}
              {episode.status === "processing" && episode.progress !== undefined && (
                <div className="mt-2">
                  <div className="h-1 bg-muted rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 transition-all"
                      style={{ width: `${episode.progress}%` }}
                    />
                  </div>
                  <span className="text-xs text-muted-foreground">{episode.progress}%</span>
                </div>
              )}

              {/* Error */}
              {episode.status === "failed" && episode.error_message && (
                <p className="mt-2 text-xs text-red-500 line-clamp-1">
                  {episode.error_message}
                </p>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
