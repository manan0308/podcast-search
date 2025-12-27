"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import type { Channel } from "@/lib/types";

export default function PodcastsPage() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadChannels();
  }, []);

  const loadChannels = async () => {
    try {
      const response = await api.getChannels();
      setChannels(response.channels);
    } catch (error) {
      console.error("Failed to load channels:", error);
    } finally {
      setLoading(false);
    }
  };

  const formatDuration = (seconds: number) => {
    const hours = Math.floor(seconds / 3600);
    return `${hours} hours`;
  };

  if (loading) {
    return (
      <div className="container py-12 text-center">
        <Loader2 className="h-8 w-8 animate-spin mx-auto" />
      </div>
    );
  }

  return (
    <div className="container py-8">
      <div className="flex justify-between items-center mb-8">
        <div>
          <h1 className="text-3xl font-bold">Podcasts</h1>
          <p className="text-muted-foreground">
            Browse all transcribed podcasts
          </p>
        </div>
        <Link href="/admin/add">
          <Button>
            <Plus className="h-4 w-4 mr-2" />
            Add Podcast
          </Button>
        </Link>
      </div>

      {channels.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground mb-4">
              No podcasts added yet
            </p>
            <Link href="/admin/add">
              <Button>Add Your First Podcast</Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {channels.map((channel) => (
            <Link key={channel.id} href={`/podcasts/${channel.slug}`}>
              <Card className="hover:shadow-lg transition-shadow cursor-pointer h-full">
                <CardHeader className="flex flex-row items-center gap-4">
                  {channel.thumbnail_url && (
                    <Image
                      src={channel.thumbnail_url}
                      alt={channel.name}
                      width={64}
                      height={64}
                      className="rounded-full"
                    />
                  )}
                  <div className="flex-1 min-w-0">
                    <CardTitle className="truncate">{channel.name}</CardTitle>
                    <p className="text-sm text-muted-foreground">
                      {channel.episode_count} episodes
                    </p>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="flex flex-wrap gap-2 mb-4">
                    {channel.speakers.map((speaker) => (
                      <Badge key={speaker} variant="secondary">
                        {speaker}
                      </Badge>
                    ))}
                  </div>
                  <div className="flex justify-between text-sm text-muted-foreground">
                    <span>
                      {channel.transcribed_count} / {channel.episode_count} transcribed
                    </span>
                    <span>{formatDuration(channel.total_duration_seconds)}</span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
