"use client";

import Image from "next/image";
import Link from "next/link";
import { Podcast, Users, FileText, Clock } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { Channel } from "@/lib/types";
import { formatDate } from "@/lib/utils";

interface PodcastCardProps {
  channel: Channel;
}

export function PodcastCard({ channel }: PodcastCardProps) {
  return (
    <Link href={`/podcasts/${channel.slug}`}>
      <Card className="hover:shadow-md transition-shadow h-full">
        <CardContent className="p-4">
          <div className="flex gap-4">
            {/* Thumbnail */}
            {channel.thumbnail_url ? (
              <Image
                src={channel.thumbnail_url}
                alt={channel.name}
                width={80}
                height={80}
                className="rounded-lg object-cover shrink-0"
              />
            ) : (
              <div className="w-20 h-20 rounded-lg bg-muted flex items-center justify-center shrink-0">
                <Podcast className="h-8 w-8 text-muted-foreground" />
              </div>
            )}

            <div className="flex-1 min-w-0">
              {/* Title */}
              <h3 className="font-semibold line-clamp-1 mb-1">{channel.name}</h3>

              {/* Description */}
              {channel.description && (
                <p className="text-sm text-muted-foreground line-clamp-2 mb-2">
                  {channel.description}
                </p>
              )}

              {/* Stats */}
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                <span className="flex items-center gap-1">
                  <FileText className="h-3 w-3" />
                  {channel.episode_count} episodes
                </span>
                <span className="flex items-center gap-1">
                  <Users className="h-3 w-3" />
                  {channel.transcribed_count} transcribed
                </span>
              </div>

              {/* Speakers */}
              {channel.speakers && channel.speakers.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {channel.speakers.slice(0, 3).map((speaker) => (
                    <Badge key={speaker} variant="outline" className="text-xs">
                      {speaker}
                    </Badge>
                  ))}
                  {channel.speakers.length > 3 && (
                    <Badge variant="outline" className="text-xs">
                      +{channel.speakers.length - 3}
                    </Badge>
                  )}
                </div>
              )}
            </div>
          </div>

          {/* Last Updated */}
          {channel.updated_at && (
            <div className="mt-3 pt-3 border-t text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" />
              Updated {formatDate(channel.updated_at)}
            </div>
          )}
        </CardContent>
      </Card>
    </Link>
  );
}
