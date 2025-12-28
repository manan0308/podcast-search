"use client";

import Link from "next/link";
import { Clock, Play, Pause, CheckCircle, XCircle, Loader2, RotateCcw } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import type { Batch } from "@/lib/types";
import { formatDate } from "@/lib/utils";
import { api } from "@/lib/api";

interface BatchCardProps {
  batch: Batch;
  onUpdate?: () => void;
}

const statusConfig = {
  pending: {
    icon: Clock,
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
  paused: {
    icon: Pause,
    color: "text-yellow-500",
    bg: "bg-yellow-500/10",
    label: "Paused",
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
  cancelled: {
    icon: XCircle,
    color: "text-gray-500",
    bg: "bg-gray-500/10",
    label: "Cancelled",
  },
};

export function BatchCard({ batch, onUpdate }: BatchCardProps) {
  const status = statusConfig[batch.status as keyof typeof statusConfig] || statusConfig.pending;
  const StatusIcon = status.icon;

  const progress =
    batch.total_episodes > 0
      ? Math.round((batch.completed_episodes / batch.total_episodes) * 100)
      : 0;

  const handleStart = async (e: React.MouseEvent) => {
    e.preventDefault();
    await api.startBatch(batch.id);
    onUpdate?.();
  };

  const handlePause = async (e: React.MouseEvent) => {
    e.preventDefault();
    await api.pauseBatch(batch.id);
    onUpdate?.();
  };

  const handleResume = async (e: React.MouseEvent) => {
    e.preventDefault();
    await api.resumeBatch(batch.id);
    onUpdate?.();
  };

  const handleCancel = async (e: React.MouseEvent) => {
    e.preventDefault();
    if (confirm("Are you sure you want to cancel this batch?")) {
      await api.cancelBatch(batch.id);
      onUpdate?.();
    }
  };

  const handleRetry = async (e: React.MouseEvent) => {
    e.preventDefault();
    await api.retryBatch(batch.id);
    onUpdate?.();
  };

  return (
    <Link href={`/admin/batches/${batch.id}`}>
      <Card className="hover:shadow-md transition-shadow">
        <CardContent className="p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              {/* Header */}
              <div className="flex items-center gap-2 mb-2">
                <h3 className="font-semibold">{batch.channel_name}</h3>
                <Badge
                  variant="secondary"
                  className={`${status.bg} ${status.color}`}
                >
                  <StatusIcon
                    className={`h-3 w-3 mr-1 ${
                      batch.status === "processing" ? "animate-spin" : ""
                    }`}
                  />
                  {status.label}
                </Badge>
              </div>

              {/* Progress */}
              <div className="mb-2">
                <div className="flex items-center justify-between text-sm mb-1">
                  <span className="text-muted-foreground">
                    {batch.completed_episodes} / {batch.total_episodes} episodes
                  </span>
                  <span className="font-medium">{progress}%</span>
                </div>
                <Progress value={progress} className="h-2" />
              </div>

              {/* Stats */}
              <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                <span>Provider: {batch.provider}</span>
                {batch.failed_episodes > 0 && (
                  <span className="text-red-500">
                    {batch.failed_episodes} failed
                  </span>
                )}
                {batch.total_cost > 0 && (
                  <span>${batch.total_cost.toFixed(2)} spent</span>
                )}
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {formatDate(batch.created_at)}
                </span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex gap-1" onClick={(e) => e.preventDefault()}>
              {batch.status === "pending" && (
                <Button size="sm" variant="outline" onClick={handleStart}>
                  <Play className="h-4 w-4" />
                </Button>
              )}
              {batch.status === "processing" && (
                <Button size="sm" variant="outline" onClick={handlePause}>
                  <Pause className="h-4 w-4" />
                </Button>
              )}
              {batch.status === "paused" && (
                <Button size="sm" variant="outline" onClick={handleResume}>
                  <Play className="h-4 w-4" />
                </Button>
              )}
              {["pending", "processing", "paused"].includes(batch.status) && (
                <Button size="sm" variant="outline" onClick={handleCancel}>
                  <XCircle className="h-4 w-4" />
                </Button>
              )}
              {(batch.status === "failed" || batch.status === "cancelled" || batch.failed_episodes > 0) && (
                <Button size="sm" variant="outline" onClick={handleRetry} title="Retry failed jobs">
                  <RotateCcw className="h-4 w-4" />
                </Button>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
    </Link>
  );
}
