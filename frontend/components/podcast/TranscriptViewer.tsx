"use client";

import { useState, useRef, useEffect } from "react";
import { ExternalLink, Play, User, Search, ChevronDown, ChevronUp } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { Utterance } from "@/lib/types";
import { cn, formatDuration, getSpeakerColor } from "@/lib/utils";

interface TranscriptViewerProps {
  utterances: Utterance[];
  episodeUrl?: string;
}

export function TranscriptViewer({ utterances, episodeUrl }: TranscriptViewerProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedSpeakers, setExpandedSpeakers] = useState<Set<string>>(new Set());
  const [jumpToTime, setJumpToTime] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const speakers = Array.from(new Set(utterances.map((u) => u.speaker)));

  const filteredUtterances = utterances.filter((utterance) => {
    const matchesSearch = searchQuery
      ? utterance.text.toLowerCase().includes(searchQuery.toLowerCase()) ||
        utterance.speaker.toLowerCase().includes(searchQuery.toLowerCase())
      : true;

    const matchesSpeaker =
      expandedSpeakers.size === 0 || expandedSpeakers.has(utterance.speaker);

    return matchesSearch && matchesSpeaker;
  });

  const toggleSpeaker = (speaker: string) => {
    const newExpanded = new Set(expandedSpeakers);
    if (newExpanded.has(speaker)) {
      newExpanded.delete(speaker);
    } else {
      newExpanded.add(speaker);
    }
    setExpandedSpeakers(newExpanded);
  };

  const clearFilters = () => {
    setExpandedSpeakers(new Set());
    setSearchQuery("");
  };

  const getYouTubeLink = (timestampMs: number) => {
    if (!episodeUrl) return null;
    const seconds = Math.floor(timestampMs / 1000);
    return `${episodeUrl}&t=${seconds}`;
  };

  const highlightText = (text: string, query: string) => {
    if (!query) return text;

    const parts = text.split(new RegExp(`(${query})`, "gi"));
    return parts.map((part, i) =>
      part.toLowerCase() === query.toLowerCase() ? (
        <mark key={i} className="bg-yellow-200 dark:bg-yellow-800 rounded px-0.5">
          {part}
        </mark>
      ) : (
        part
      )
    );
  };

  return (
    <div className="flex flex-col h-full">
      {/* Controls */}
      <div className="flex flex-wrap gap-4 mb-4 p-4 border rounded-lg bg-muted/50">
        {/* Search */}
        <div className="flex-1 min-w-[200px]">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Search transcript..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        {/* Speaker Filters */}
        <div className="flex flex-wrap gap-2 items-center">
          <span className="text-sm text-muted-foreground">Speakers:</span>
          {speakers.map((speaker) => (
            <Badge
              key={speaker}
              variant={expandedSpeakers.has(speaker) ? "default" : "outline"}
              className={cn(
                "cursor-pointer transition-colors",
                expandedSpeakers.has(speaker) && getSpeakerColor(speaker)
              )}
              onClick={() => toggleSpeaker(speaker)}
            >
              {speaker}
            </Badge>
          ))}
          {(expandedSpeakers.size > 0 || searchQuery) && (
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              Clear
            </Button>
          )}
        </div>
      </div>

      {/* Stats */}
      <div className="flex items-center gap-4 mb-4 text-sm text-muted-foreground">
        <span>
          {filteredUtterances.length} of {utterances.length} segments
        </span>
        <span>•</span>
        <span>{speakers.length} speakers</span>
      </div>

      {/* Transcript */}
      <ScrollArea className="flex-1 border rounded-lg" ref={scrollRef}>
        <div className="p-4 space-y-4">
          {filteredUtterances.map((utterance, index) => (
            <UtteranceItem
              key={utterance.id}
              utterance={utterance}
              youtubeLink={getYouTubeLink(utterance.start_ms)}
              searchQuery={searchQuery}
              highlightText={highlightText}
            />
          ))}

          {filteredUtterances.length === 0 && (
            <div className="text-center py-8 text-muted-foreground">
              No matching segments found
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

function UtteranceItem({
  utterance,
  youtubeLink,
  searchQuery,
  highlightText,
}: {
  utterance: Utterance;
  youtubeLink: string | null;
  searchQuery: string;
  highlightText: (text: string, query: string) => React.ReactNode;
}) {
  const [expanded, setExpanded] = useState(false);
  const isLong = utterance.text.length > 300;

  return (
    <div className="group flex gap-3 p-3 rounded-lg hover:bg-muted/50 transition-colors">
      {/* Timestamp */}
      <div className="shrink-0 w-16 text-right">
        {youtubeLink ? (
          <a
            href={youtubeLink}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-primary hover:underline inline-flex items-center gap-1"
          >
            <Play className="h-3 w-3" />
            {formatDuration(Math.floor(utterance.start_ms / 1000))}
          </a>
        ) : (
          <span className="text-xs text-muted-foreground">
            {formatDuration(Math.floor(utterance.start_ms / 1000))}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0">
        {/* Speaker */}
        <Badge
          variant="outline"
          className={cn("text-xs mb-1", getSpeakerColor(utterance.speaker))}
        >
          <User className="h-3 w-3 mr-1" />
          {utterance.speaker}
        </Badge>

        {/* Text */}
        <p className="text-sm leading-relaxed">
          {isLong && !expanded ? (
            <>
              {highlightText(utterance.text.slice(0, 300), searchQuery)}...
              <button
                onClick={() => setExpanded(true)}
                className="text-primary hover:underline ml-1 inline-flex items-center gap-0.5"
              >
                more <ChevronDown className="h-3 w-3" />
              </button>
            </>
          ) : (
            <>
              {highlightText(utterance.text, searchQuery)}
              {isLong && expanded && (
                <button
                  onClick={() => setExpanded(false)}
                  className="text-primary hover:underline ml-1 inline-flex items-center gap-0.5"
                >
                  less <ChevronUp className="h-3 w-3" />
                </button>
              )}
            </>
          )}
        </p>

        {/* Duration */}
        <span className="text-xs text-muted-foreground mt-1 block">
          Duration: {((utterance.end_ms - utterance.start_ms) / 1000).toFixed(1)}s
        </span>
      </div>

      {/* YouTube Link */}
      {youtubeLink && (
        <div className="shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <a
            href={youtubeLink}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground"
            title="Watch on YouTube"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
        </div>
      )}
    </div>
  );
}
