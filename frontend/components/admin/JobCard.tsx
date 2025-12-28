"use client";

import Image from "next/image";
import Link from "next/link";
import { Clock, CheckCircle, XCircle, Loader2, RotateCcw, FileText } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import type { Job } from "@/lib/types";
import { formatDate, formatDuration } from "@/lib/utils";
import { api } from "@/lib/api";

interface JobCardProps {
  job: Job;
  onUpdate?: () => void;
}

const statusConfig = {
  pending: {
    icon: Clock,
    color: "text-muted-foreground",
    bg: "bg-muted",
    label: "Pending",
  },
  downloading: {
    icon: Loader2,
    color: "text-blue-500",
    bg: "bg-blue-500/10",
    label: "Downloading",
  },
  transcribing: {
    icon: Loader2,
    color: "text-purple-500",
    bg: "bg-purple-500/10",
    label: "Transcribing",
  },
  labeling: {
    icon: Loader2,
    color: "text-orange-500",
    bg: "bg-orange-500/10",
    label: "Labeling Speakers",
  },
  chunking: {
    icon: Loader2,
    color: "text-cyan-500",
    bg: "bg-cyan-500/10",
    label: "Chunking",
  },
  embedding: {
    icon: Loader2,
    color: "text-indigo-500",
    bg: "bg-indigo-500/10",
    label: "Embedding",
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

const stageOrder = ["downloading", "transcribing", "labeling", "chunking", "embedding", "completed"];

export function JobCard({ job, onUpdate }: JobCardProps) {
  const status = statusConfig[job.status as keyof typeof statusConfig] || statusConfig.pending;
  const StatusIcon = status.icon;

  const stageIndex = stageOrder.indexOf(job.status);
  const progress = job.status === "completed"
    ? 100
    : job.status === "failed" || job.status === "pending" || job.status === "cancelled"
    ? 0
    : Math.round(((stageIndex + 1) / stageOrder.length) * 100);

  const handleRetry = async (e: React.MouseEvent) => {
    e.preventDefault();
    await api.retryJob(job.id);
    onUpdate?.();
  };

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="p-4">
        <div className="flex gap-4">
          {/* Thumbnail */}
          {job.episode_thumbnail ? (
            <Image
              src={job.episode_thumbnail}
              alt=""
              width={120}
              height={68}
              className="rounded object-cover shrink-0"
            />
          ) : (
            <div className="w-[120px] h-[68px] bg-muted rounded flex items-center justify-center shrink-0">
              <FileText className="h-6 w-6 text-muted-foreground" />
            </div>
          )}

          <div className="flex-1 min-w-0">
            {/* Header */}
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="min-w-0">
                <Link
                  href={`/podcasts/${job.channel_slug}/episodes/${job.episode_id}`}
                  className="font-semibold hover:underline line-clamp-1"
                >
                  {job.episode_title}
                </Link>
                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                  <span>{job.channel_name}</span>
                  {job.duration_seconds && (
                    <>
                      <span>•</span>
                      <span>{formatDuration(job.duration_seconds)}</span>
                    </>
                  )}
                </div>
              </div>
              <Badge
                variant="secondary"
                className={`shrink-0 ${status.bg} ${status.color}`}
              >
                <StatusIcon
                  className={`h-3 w-3 mr-1 ${
                    !["completed", "failed", "pending", "cancelled"].includes(job.status)
                      ? "animate-spin"
                      : ""
                  }`}
                />
                {status.label}
              </Badge>
            </div>

            {/* Progress */}
            {!["completed", "failed", "pending", "cancelled"].includes(job.status) && (
              <div className="mb-2">
                <Progress value={progress} className="h-1" />
              </div>
            )}

            {/* Error */}
            {job.status === "failed" && job.error_message && (
              <p className="text-xs text-red-500 line-clamp-2 mb-2">
                {job.error_message}
              </p>
            )}

            {/* Footer */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-4 text-xs text-muted-foreground">
                {job.cost && <span>${job.cost.toFixed(3)} cost</span>}
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" />
                  {formatDate(job.updated_at || job.created_at)}
                </span>
              </div>

              {/* Actions */}
              {(job.status === "failed" || job.status === "cancelled") && (
                <Button size="sm" variant="outline" onClick={handleRetry}>
                  <RotateCcw className="h-3 w-3 mr-1" />
                  Retry
                </Button>
              )}
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
