"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2, Play, Pause, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { api } from "@/lib/api";
import type { Batch } from "@/lib/types";

export default function BatchesPage() {
  const [batches, setBatches] = useState<Batch[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadBatches();
  }, []);

  const loadBatches = async () => {
    try {
      const response = await api.getBatches({});
      setBatches(response.batches);
    } catch (error) {
      console.error("Failed to load batches:", error);
    } finally {
      setLoading(false);
    }
  };

  const formatDate = (date: string | null) => {
    if (!date) return "--";
    return new Date(date).toLocaleString();
  };

  const getStatusBadgeVariant = (status: string) => {
    switch (status) {
      case "running":
        return "default";
      case "completed":
        return "secondary";
      case "failed":
        return "destructive";
      default:
        return "outline";
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
          <h1 className="text-3xl font-bold">Processing Batches</h1>
          <p className="text-muted-foreground">
            View and manage transcription jobs
          </p>
        </div>
      </div>

      {batches.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="text-muted-foreground mb-4">No batches yet</p>
            <Link href="/admin/add">
              <Button>Add a Podcast</Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-4">
          {batches.map((batch) => (
            <Link key={batch.id} href={`/admin/batches/${batch.id}`}>
              <Card className="hover:shadow-md transition-shadow cursor-pointer">
                <CardContent className="flex items-center gap-4 py-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-2">
                      <h3 className="font-semibold truncate">
                        {batch.name || `Batch ${batch.id.slice(0, 8)}`}
                      </h3>
                      <Badge variant={getStatusBadgeVariant(batch.status)}>
                        {batch.status}
                      </Badge>
                      <Badge variant="outline">{batch.provider}</Badge>
                    </div>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                      <span>
                        {batch.completed_episodes} / {batch.total_episodes}{" "}
                        episodes
                      </span>
                      {batch.failed_episodes > 0 && (
                        <span className="text-red-500">
                          {batch.failed_episodes} failed
                        </span>
                      )}
                      <span>
                        Cost: $
                        {((batch.actual_cost_cents || 0) / 100).toFixed(2)}
                      </span>
                    </div>
                    <div className="mt-2">
                      <Progress value={batch.progress_percent} />
                    </div>
                  </div>
                  <div className="text-right text-sm text-muted-foreground">
                    <p>Started: {formatDate(batch.started_at)}</p>
                    {batch.completed_at && (
                      <p>Completed: {formatDate(batch.completed_at)}</p>
                    )}
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
