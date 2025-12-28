"use client";

import { useState, useCallback, memo } from "react";
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
import { useChannels, useSpeakers } from "@/lib/hooks";
import type { SearchFilters as Filters } from "@/lib/types";

interface SearchFiltersProps {
  filters: Filters;
  onChange: (filters: Filters) => void;
}

function SearchFiltersComponent({ filters, onChange }: SearchFiltersProps) {
  const [showFilters, setShowFilters] = useState(false);

  // Use SWR hooks - data is cached and deduplicated
  const { data: speakersData } = useSpeakers();
  const { data: channelsData } = useChannels();

  const speakers = speakersData?.speakers || [];
  const channels = channelsData?.channels || [];

  const hasActiveFilters = filters.speaker || filters.channel_slug;

  const clearFilters = useCallback(() => {
    onChange({});
  }, [onChange]);

  const handleSpeakerChange = useCallback((value: string) => {
    onChange({
      ...filters,
      speaker: value === "all" ? undefined : value,
    });
  }, [filters, onChange]);

  const handleChannelChange = useCallback((value: string) => {
    onChange({
      ...filters,
      channel_slug: value === "all" ? undefined : value,
    });
  }, [filters, onChange]);

  const toggleFilters = useCallback(() => {
    setShowFilters(prev => !prev);
  }, []);

  return (
    <div className="mt-4">
      {/* Toggle Button */}
      <div className="flex items-center gap-2">
        <Button
          variant="ghost"
          size="sm"
          onClick={toggleFilters}
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
              onValueChange={handleSpeakerChange}
            >
              <SelectTrigger>
                <SelectValue placeholder="All speakers" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All speakers</SelectItem>
                {speakers.map((speaker: string) => (
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
              onValueChange={handleChannelChange}
            >
              <SelectTrigger>
                <SelectValue placeholder="All podcasts" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All podcasts</SelectItem>
                {channels.map((channel: any) => (
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

// Memoize to prevent unnecessary re-renders
export const SearchFilters = memo(SearchFiltersComponent);
