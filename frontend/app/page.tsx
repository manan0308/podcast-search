"use client";

import { useState } from "react";
import { Search, Loader2, Mic, Sparkles, Clock, User, Zap, SearchX } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { SearchResults, SearchResultSkeleton } from "@/components/search/SearchResults";
import { SearchFilters } from "@/components/search/SearchFilters";
import { api } from "@/lib/api";
import type { SearchResult, SearchFilters as Filters } from "@/lib/types";

export default function HomePage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [filters, setFilters] = useState<Filters>({});
  const [processingTime, setProcessingTime] = useState<number | null>(null);

  const handleSearch = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setSearched(true);

    try {
      const response = await api.search({
        query,
        filters,
        limit: 20,
        include_context: true,
      });
      setResults(response.results);
      setProcessingTime(response.processing_time_ms);
    } catch (error) {
      console.error("Search failed:", error);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="container py-8">
      {/* Hero Section */}
      <div className="text-center mb-8">
        <div className="inline-flex items-center gap-2 mb-4">
          <Mic className="h-10 w-10 text-primary" />
          <h1 className="text-4xl font-bold tracking-tight">
            Podcast Search
          </h1>
        </div>
        <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
          Find exactly what was said across podcast episodes.
          <span className="inline-flex items-center gap-1 ml-1">
            <Sparkles className="h-4 w-4 text-yellow-500" />
            AI-powered semantic search
          </span>
        </p>
      </div>

      {/* Search Form */}
      <form onSubmit={handleSearch} className="max-w-3xl mx-auto mb-8">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search for topics, quotes, or ideas..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-10 h-12 text-lg"
            />
          </div>
          <Button type="submit" size="lg" disabled={loading} className="gap-2">
            {loading ? (
              <Loader2 className="h-5 w-5 animate-spin" />
            ) : (
              <>
                <Search className="h-5 w-5" />
                Search
              </>
            )}
          </Button>
        </div>
        <SearchFilters filters={filters} onChange={setFilters} />
      </form>

      {/* Results */}
      {searched && (
        <div className="max-w-4xl mx-auto">
          {loading ? (
            <div className="space-y-4">
              <div className="flex items-center gap-2 text-sm text-muted-foreground mb-4">
                <Loader2 className="h-4 w-4 animate-spin" />
                Searching transcripts...
              </div>
              {[1, 2, 3].map((i) => (
                <SearchResultSkeleton key={i} />
              ))}
            </div>
          ) : results.length > 0 ? (
            <>
              <div className="flex justify-between items-center mb-4">
                <p className="text-sm text-muted-foreground flex items-center gap-2">
                  <Zap className="h-4 w-4 text-green-500" />
                  Found {results.length} results
                  {processingTime && ` in ${processingTime}ms`}
                </p>
              </div>
              <SearchResults results={results} query={query} />
            </>
          ) : (
            <div className="text-center py-12">
              <SearchX className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <p className="text-muted-foreground">
                No results found for "{query}"
              </p>
              <p className="text-sm text-muted-foreground mt-2">
                Try different keywords or adjust your filters
              </p>
            </div>
          )}
        </div>
      )}

      {/* Initial State - Feature Cards */}
      {!searched && (
        <div className="max-w-2xl mx-auto text-center py-12">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-8">
            <div className="p-6 border rounded-lg hover:border-primary/50 transition-colors">
              <Sparkles className="h-8 w-8 text-yellow-500 mx-auto mb-3" />
              <h3 className="font-semibold mb-2">Semantic Search</h3>
              <p className="text-sm text-muted-foreground">
                Find content by meaning, not just keywords
              </p>
            </div>
            <div className="p-6 border rounded-lg hover:border-primary/50 transition-colors">
              <User className="h-8 w-8 text-blue-500 mx-auto mb-3" />
              <h3 className="font-semibold mb-2">Speaker Filtering</h3>
              <p className="text-sm text-muted-foreground">
                Filter by specific hosts or guests
              </p>
            </div>
            <div className="p-6 border rounded-lg hover:border-primary/50 transition-colors">
              <Clock className="h-8 w-8 text-green-500 mx-auto mb-3" />
              <h3 className="font-semibold mb-2">Timestamps</h3>
              <p className="text-sm text-muted-foreground">
                Jump directly to the moment
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
