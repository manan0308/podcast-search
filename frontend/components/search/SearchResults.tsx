"use client";

import { memo, useMemo } from "react";
import Image from "next/image";
import Link from "next/link";
import { ExternalLink, Clock, User } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import type { SearchResult } from "@/lib/types";
import { cn, getSpeakerColor } from "@/lib/utils";

// Loading skeleton for search results
export function SearchResultSkeleton() {
  return (
    <Card className="animate-pulse">
      <CardContent className="p-4">
        <div className="flex gap-4">
          {/* Thumbnail skeleton */}
          <Skeleton className="w-[120px] h-[68px] rounded shrink-0" />

          <div className="flex-1 min-w-0 space-y-3">
            {/* Title skeleton */}
            <div className="space-y-2">
              <Skeleton className="h-5 w-3/4" />
              <Skeleton className="h-4 w-1/2" />
            </div>

            {/* Speaker badge skeleton */}
            <Skeleton className="h-5 w-24" />

            {/* Text skeleton */}
            <div className="space-y-2">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

interface SearchResultsProps {
  results: SearchResult[];
  query: string;
}

export function SearchResults({ results, query }: SearchResultsProps) {
  return (
    <div className="space-y-4">
      {results.map((result) => (
        <SearchResultCard key={result.chunk_id} result={result} query={query} />
      ))}
    </div>
  );
}

// Memoized search result card
const SearchResultCard = memo(function SearchResultCard({
  result,
  query,
}: {
  result: SearchResult;
  query: string;
}) {
  // Memoize highlighted text to avoid recalculation on every render
  const highlightedText = useMemo(() => {
    if (!query) return result.text;

    try {
      const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const parts = result.text.split(new RegExp(`(${escapedQuery})`, "gi"));
      return parts.map((part, i) =>
        part.toLowerCase() === query.toLowerCase() ? (
          <mark key={i} className="bg-yellow-200 dark:bg-yellow-800 rounded px-0.5">
            {part}
          </mark>
        ) : (
          part
        )
      );
    } catch {
      return result.text;
    }
  }, [result.text, query]);

  const youtubeLink = useMemo(() => {
    if (!result.episode_url) return null;
    return `${result.episode_url}&t=${Math.floor(result.timestamp_ms / 1000)}`;
  }, [result.episode_url, result.timestamp_ms]);

  const scorePercent = useMemo(() => (result.score * 100).toFixed(0), [result.score]);

  return (
    <Card className="hover:shadow-md transition-shadow">
      <CardContent className="p-4">
        <div className="flex gap-4">
          {/* Thumbnail */}
          {result.episode_thumbnail && (
            <Link
              href={`/podcasts/${result.channel_slug}/episodes/${result.episode_id}`}
              className="shrink-0"
            >
              <Image
                src={result.episode_thumbnail}
                alt=""
                width={120}
                height={68}
                className="rounded object-cover"
                loading="lazy"
                placeholder="empty"
              />
            </Link>
          )}

          <div className="flex-1 min-w-0">
            {/* Header */}
            <div className="flex items-start justify-between gap-2 mb-2">
              <div>
                <Link
                  href={`/podcasts/${result.channel_slug}/episodes/${result.episode_id}`}
                  className="font-semibold hover:underline line-clamp-1"
                >
                  {result.episode_title}
                </Link>
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Link
                    href={`/podcasts/${result.channel_slug}`}
                    className="hover:underline"
                  >
                    {result.channel_name}
                  </Link>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <Clock className="h-3 w-3" />
                    {result.timestamp}
                  </span>
                </div>
              </div>

              {/* Score Badge */}
              <Badge variant="secondary" className="shrink-0">
                {scorePercent}% match
              </Badge>
            </div>

            {/* Speaker */}
            {result.speaker && (
              <div className="mb-2">
                <Badge
                  variant="outline"
                  className={cn("text-xs", getSpeakerColor(result.speaker))}
                >
                  <User className="h-3 w-3 mr-1" />
                  {result.speaker}
                </Badge>
              </div>
            )}

            {/* Text */}
            <p className="text-sm text-muted-foreground line-clamp-3">
              {highlightedText}
            </p>

            {/* Context */}
            {(result.context_before.length > 0 ||
              result.context_after.length > 0) && (
              <details className="mt-2">
                <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
                  Show context
                </summary>
                <div className="mt-2 space-y-1 text-xs text-muted-foreground border-l-2 pl-2">
                  {result.context_before.map((ctx, i) => (
                    <p key={`before-${i}`}>
                      <span className="font-medium">{ctx.speaker}:</span>{" "}
                      {ctx.text}
                    </p>
                  ))}
                  <p className="font-medium text-foreground">
                    <span className="font-medium">{result.speaker}:</span>{" "}
                    {result.text}
                  </p>
                  {result.context_after.map((ctx, i) => (
                    <p key={`after-${i}`}>
                      <span className="font-medium">{ctx.speaker}:</span>{" "}
                      {ctx.text}
                    </p>
                  ))}
                </div>
              </details>
            )}

            {/* Actions */}
            {youtubeLink && (
              <div className="mt-2">
                <a
                  href={youtubeLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs text-primary hover:underline inline-flex items-center gap-1"
                >
                  Watch at {result.timestamp}
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
});
