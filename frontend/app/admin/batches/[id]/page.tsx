"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Loader2,
  Play,
  Pause,
  RotateCcw,
  ArrowLeft,
  CheckCircle,
  XCircle,
  Clock,
  AlertCircle,
  Wifi,
  WifiOff,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api";
import { useBatchUpdates, type JobUpdate, type BatchUpdate } from "@/hooks/useWebSocket";
import type { BatchDetail, JobSummary } from "@/lib/types";

export default function BatchDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;

  const [batch, setBatch] = useState<BatchDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);

  // WebSocket for real-time updates
  const handleWsUpdate = useCallback((update: JobUpdate | BatchUpdate) => {
    if (update.type === "job_update") {
      setBatch((prev) => {
        if (!prev) return prev;
        const jobUpdate = update as JobUpdate;
        const updatedJobs = prev.jobs.map((job) =>
          job.id === jobUpdate.job_id
            ? {
                ...job,
                status: jobUpdate.status,
                progress: jobUpdate.progress,
                current_step: jobUpdate.current_step,
                error_message: jobUpdate.error_message,
              }
            : job
        );
        // Update completed/failed counts
        const completed = updatedJobs.filter((j) => j.status === "done").length;
        const failed = updatedJobs.filter((j) => j.status === "failed").length;
        return {
          ...prev,
          jobs: updatedJobs,
          completed_episodes: completed,
          failed_episodes: failed,
          progress_percent: prev.total_episodes > 0
            ? ((completed + failed) / prev.total_episodes) * 100
            : 0,
        };
      });
    } else if (update.type === "batch_update") {
      const batchUpdate = update as BatchUpdate;
      setBatch((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          status: batchUpdate.status,
          completed_episodes: batchUpdate.completed_episodes,
          failed_episodes: batchUpdate.failed_episodes,
          progress_percent: batchUpdate.progress_percent,
        };
      });
    }
  }, []);

  const { isConnected } = useBatchUpdates(id, handleWsUpdate);

  useEffect(() => {
    loadBatch();
  }, [id]);

  const loadBatch = async () => {
    try {
      const response = await api.getBatch(id);
      setBatch(response);
    } catch (error) {
      console.error("Failed to load batch:", error);
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async () => {
    setActionLoading(true);
    try {
      await api.pauseBatch(id);
      await loadBatch();
    } catch (error) {
      console.error("Failed to pause batch:", error);
    } finally {
      setActionLoading(false);
    }
  };

  const handleResume = async () => {
    setActionLoading(true);
    try {
      await api.resumeBatch(id);
      await loadBatch();
    } catch (error) {
      console.error("Failed to resume batch:", error);
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!confirm("Are you sure you want to cancel this batch?")) return;
    setActionLoading(true);
    try {
      await api.cancelBatch(id);
      await loadBatch();
    } catch (error) {
      console.error("Failed to cancel batch:", error);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRetryJob = async (jobId: string) => {
    try {
      await api.retryJob(jobId);
      await loadBatch();
    } catch (error) {
      console.error("Failed to retry job:", error);
    }
  };

  const getJobStatusIcon = (status: string) => {
    switch (status) {
      case "done":
        return <CheckCircle className="h-4 w-4 text-green-500" />;
      case "failed":
        return <XCircle className="h-4 w-4 text-red-500" />;
      case "pending":
        return <Clock className="h-4 w-4 text-gray-400" />;
      default:
        return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
    }
  };

  if (loading) {
    return (
      <div className="container py-12 text-center">
        <Loader2 className="h-8 w-8 animate-spin mx-auto" />
      </div>
    );
  }

  if (!batch) {
    return (
      <div className="container py-12 text-center">
        <p className="text-muted-foreground">Batch not found</p>
      </div>
    );
  }

  return (
    <div className="container py-8">
      {/* Back Link */}
      <Link
        href="/admin/batches"
        className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-6"
      >
        <ArrowLeft className="h-4 w-4 mr-1" />
        Back to Batches
      </Link>

      {/* Header */}
      <div className="flex justify-between items-start mb-8">
        <div>
          <h1 className="text-3xl font-bold mb-2">
            {batch.name || `Batch ${batch.id.slice(0, 8)}`}
          </h1>
          <div className="flex items-center gap-2">
            <Badge
              variant={
                batch.status === "running"
                  ? "default"
                  : batch.status === "completed"
                  ? "secondary"
                  : "outline"
              }
            >
              {batch.status}
            </Badge>
            <Badge variant="outline">{batch.provider}</Badge>
            {batch.channel_name && (
              <span className="text-muted-foreground">{batch.channel_name}</span>
            )}
            {/* WebSocket connection status */}
            <div className="flex items-center gap-1 text-xs">
              {isConnected ? (
                <>
                  <Wifi className="h-3 w-3 text-green-500" />
                  <span className="text-green-600">Live</span>
                </>
              ) : (
                <>
                  <WifiOff className="h-3 w-3 text-gray-400" />
                  <span className="text-gray-500">Offline</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2">
          {batch.status === "running" && (
            <Button
              variant="outline"
              onClick={handlePause}
              disabled={actionLoading}
            >
              {actionLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Pause className="h-4 w-4 mr-2" />
              )}
              Pause
            </Button>
          )}
          {batch.status === "paused" && (
            <Button onClick={handleResume} disabled={actionLoading}>
              {actionLoading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Play className="h-4 w-4 mr-2" />
              )}
              Resume
            </Button>
          )}
          {["running", "paused", "pending"].includes(batch.status) && (
            <Button
              variant="destructive"
              onClick={handleCancel}
              disabled={actionLoading}
            >
              Cancel
            </Button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Progress
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold mb-2">
              {batch.progress_percent.toFixed(0)}%
            </div>
            <Progress value={batch.progress_percent} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Completed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-green-600">
              {batch.completed_episodes}
            </div>
            <p className="text-sm text-muted-foreground">
              of {batch.total_episodes} episodes
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Failed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold text-red-600">
              {batch.failed_episodes}
            </div>
            <p className="text-sm text-muted-foreground">episodes</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Cost
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              ${((batch.actual_cost_cents || 0) / 100).toFixed(2)}
            </div>
            <p className="text-sm text-muted-foreground">
              of ${((batch.estimated_cost_cents || 0) / 100).toFixed(2)}{" "}
              estimated
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Jobs List */}
      <Card>
        <CardHeader>
          <CardTitle>Jobs</CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[500px]">
            <div className="space-y-2">
              {batch.jobs.map((job) => (
                <div
                  key={job.id}
                  className="flex items-center gap-3 p-3 border rounded-lg"
                >
                  {getJobStatusIcon(job.status)}
                  <div className="flex-1 min-w-0">
                    <p className="font-medium truncate">{job.episode_title}</p>
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <Badge variant="outline" className="text-xs">
                        {job.status}
                      </Badge>
                      {job.current_step && (
                        <span>{job.current_step}</span>
                      )}
                      {job.error_message && (
                        <span className="text-red-500 truncate">
                          {job.error_message}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {job.status !== "done" && job.status !== "pending" && (
                      <div className="w-20">
                        <Progress value={job.progress} />
                      </div>
                    )}
                    {job.status === "failed" && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => handleRetryJob(job.id)}
                      >
                        <RotateCcw className="h-3 w-3 mr-1" />
                        Retry
                      </Button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
