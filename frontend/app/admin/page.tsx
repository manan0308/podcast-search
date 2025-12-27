"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Plus, Loader2, Play, Pause, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { api } from "@/lib/api";
import type { Batch, Channel } from "@/lib/types";

export default function AdminPage() {
  const [stats, setStats] = useState<any>(null);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [statsRes, batchesRes, channelsRes] = await Promise.all([
        api.getSearchStats(),
        api.getBatches({ page_size: 5 }),
        api.getChannels(),
      ]);
      setStats(statsRes);
      setBatches(batchesRes.batches);
      setChannels(channelsRes.channels);
    } catch (error) {
      console.error("Failed to load data:", error);
    } finally {
      setLoading(false);
    }
  };

  const getBatchStatusColor = (status: string) => {
    switch (status) {
      case "running":
        return "bg-blue-500";
      case "completed":
        return "bg-green-500";
      case "failed":
        return "bg-red-500";
      case "paused":
        return "bg-yellow-500";
      default:
        return "bg-gray-500";
    }
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
          <h1 className="text-3xl font-bold">Podcast Studio</h1>
          <p className="text-muted-foreground">
            Manage podcasts and transcription jobs
          </p>
        </div>
        <Link href="/admin/add">
          <Button>
            <Plus className="h-4 w-4 mr-2" />
            Add Podcast
          </Button>
        </Link>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Podcasts
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{stats?.channels || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Episodes
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{stats?.episodes || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Transcribed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {stats?.transcribed_episodes || 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Vectors
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {(stats?.vectors || 0).toLocaleString()}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Recent Batches */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Recent Batches</CardTitle>
            <Link href="/admin/batches">
              <Button variant="ghost" size="sm">
                View All
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {batches.length === 0 ? (
              <p className="text-muted-foreground text-center py-8">
                No batches yet
              </p>
            ) : (
              <div className="space-y-4">
                {batches.map((batch) => (
                  <Link
                    key={batch.id}
                    href={`/admin/batches/${batch.id}`}
                    className="block"
                  >
                    <div className="flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <div
                            className={`w-2 h-2 rounded-full ${getBatchStatusColor(
                              batch.status
                            )}`}
                          />
                          <span className="font-medium truncate">
                            {batch.name || `Batch ${batch.id.slice(0, 8)}`}
                          </span>
                        </div>
                        <div className="text-sm text-muted-foreground mt-1">
                          {batch.completed_episodes} / {batch.total_episodes}{" "}
                          episodes
                        </div>
                      </div>
                      <div className="text-right">
                        <Badge variant="outline">{batch.provider}</Badge>
                        <div className="text-sm text-muted-foreground mt-1">
                          {batch.progress_percent.toFixed(0)}%
                        </div>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Channels */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Podcasts</CardTitle>
            <Link href="/podcasts">
              <Button variant="ghost" size="sm">
                View All
              </Button>
            </Link>
          </CardHeader>
          <CardContent>
            {channels.length === 0 ? (
              <div className="text-center py-8">
                <p className="text-muted-foreground mb-4">
                  No podcasts added yet
                </p>
                <Link href="/admin/add">
                  <Button>Add Your First Podcast</Button>
                </Link>
              </div>
            ) : (
              <div className="space-y-4">
                {channels.slice(0, 5).map((channel) => (
                  <div
                    key={channel.id}
                    className="flex items-center justify-between p-3 border rounded-lg"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">{channel.name}</div>
                      <div className="text-sm text-muted-foreground">
                        {channel.transcribed_count} / {channel.episode_count}{" "}
                        transcribed
                      </div>
                    </div>
                    <Progress
                      value={
                        (channel.transcribed_count / channel.episode_count) *
                        100
                      }
                      className="w-20"
                    />
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
