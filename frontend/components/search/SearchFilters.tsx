"use client";

import { useEffect, useState } from "react";
import { Filter, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import type { SearchFilters as Filters, Channel } from "@/lib/types";

interface SearchFiltersProps {
  filters: Filters;
  onChange: (filters: Filters) => void;
}

export function SearchFilters({ filters, onChange }: SearchFiltersProps) {
  const [speakers, setSpeakers] = useState<string[]>([]);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [showFilters, setShowFilters] = useState(false);

  useEffect(() => {
    loadFilterOptions();
  }, []);

  const loadFilterOptions = async () => {
    try {
      const [speakersRes, channelsRes] = await Promise.all([
        api.getSpeakers(),
        api.getChannels(),
      ]);
      setSpeakers(speakersRes.speakers || []);
      setChannels(channelsRes.channels || []);
    } catch (error) {
      console.error("Failed to load filter options:", error);
    }
  };

  const hasActiveFilters = filters.speaker || filters.channel_slug;

  const clearFilters = () => {
    onChange({});
  };

  return (
    <div className="mt-4">
      {/* Toggle Button */}
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setShowFilters(!showFilters)}
          className="text-muted-foreground"
        >
          <Filter className="h-4 w-4 mr-2" />
          Filters
          {hasActiveFilters && (
            <Badge variant="secondary" className="ml-2">
              Active
            </Badge>
          )}
        </Button>

        {hasActiveFilters && (
          <Button
            variant="ghost"
            size="sm"
            onClick={clearFilters}
            className="text-muted-foreground"
          >
            <X className="h-4 w-4 mr-1" />
            Clear
          </Button>
        )}
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="flex flex-wrap gap-4 mt-4 p-4 border rounded-lg bg-muted/50">
          {/* Speaker Filter */}
          <div className="w-48">
            <label className="text-sm font-medium mb-1 block">Speaker</label>
            <Select
              value={filters.speaker || "all"}
              onValueChange={(value) =>
                onChange({
                  ...filters,
                  speaker: value === "all" ? undefined : value,
                })
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="All speakers" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All speakers</SelectItem>
                {speakers.map((speaker) => (
                  <SelectItem key={speaker} value={speaker}>
                    {speaker}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Channel Filter */}
          <div className="w-48">
            <label className="text-sm font-medium mb-1 block">Podcast</label>
            <Select
              value={filters.channel_slug || "all"}
              onValueChange={(value) =>
                onChange({
                  ...filters,
                  channel_slug: value === "all" ? undefined : value,
                })
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="All podcasts" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All podcasts</SelectItem>
                {channels.map((channel) => (
                  <SelectItem key={channel.slug} value={channel.slug}>
                    {channel.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
      )}
    </div>
  );
}
