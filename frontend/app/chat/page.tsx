"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Loader2, Bot, User, ExternalLink, Mic, FileText, Filter } from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import type { ChatMessage, Citation, Channel, Episode } from "@/lib/types";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [selectedChannel, setSelectedChannel] = useState<string>("all");
  const [loadingChannels, setLoadingChannels] = useState(true);
  
  // Episode filtering
  const [episodes, setEpisodes] = useState<Episode[]>([]);
  const [selectedEpisode, setSelectedEpisode] = useState<string>("all");
  const [loadingEpisodes, setLoadingEpisodes] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    loadChannels();
  }, []);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  useEffect(() => {
    if (selectedChannel !== "all") {
      loadEpisodes(selectedChannel);
    } else {
      setEpisodes([]);
      setSelectedEpisode("all");
    }
  }, [selectedChannel]);

  const loadChannels = async () => {
    try {
      const response = await api.getChannels();
      // Only show channels that have transcribed episodes
      const transcribedChannels = response.channels.filter(
        (c: Channel) => c.transcribed_count > 0
      );
      setChannels(transcribedChannels);
    } catch (error) {
      console.error("Failed to load channels:", error);
    } finally {
      setLoadingChannels(false);
    }
  };

  const loadEpisodes = async (channelSlug: string) => {
    setLoadingEpisodes(true);
    try {
      const response = await api.getEpisodes({
        channel_slug: channelSlug,
        status: "done",
        page_size: 100,
      });
      setEpisodes(response.episodes);
    } catch (error) {
      console.error("Failed to load episodes:", error);
      setEpisodes([]);
    } finally {
      setLoadingEpisodes(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput("");

    // Add user message
    setMessages((prev) => [
      ...prev,
      { role: "user", content: userMessage, citations: [] },
    ]);

    setLoading(true);

    try {
      // Build filters
      const filters: any = {};
      if (selectedChannel !== "all") {
        const channel = channels.find((c) => c.slug === selectedChannel);
        if (channel) {
          filters.channel_id = channel.id;
        }
      }
      if (selectedEpisode !== "all") {
        filters.episode_id = selectedEpisode;
      }

      const response = await api.chat({
        message: userMessage,
        channel_slug: selectedChannel !== "all" ? selectedChannel : undefined,
        filters: Object.keys(filters).length > 0 ? filters : undefined,
      });

      // Add assistant message
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: response.answer,
          citations: response.citations,
        },
      ]);
    } catch (error) {
      console.error("Chat failed:", error);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, I encountered an error. Please try again.",
          citations: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const getContextLabel = () => {
    if (selectedEpisode !== "all") {
      const episode = episodes.find((e) => e.id === selectedEpisode);
      return episode?.title || "Selected Episode";
    }
    if (selectedChannel !== "all") {
      const channel = channels.find((c) => c.slug === selectedChannel);
      return channel?.name || "Selected Podcast";
    }
    return "All Podcasts";
  };

  const totalTranscribedEpisodes = channels.reduce(
    (sum, c) => sum + c.transcribed_count,
    0
  );

  return (
    <div className="container py-8 max-w-4xl">
      <div className="text-center mb-8">
        <h1 className="text-3xl font-bold mb-2">Chat with Podcasts</h1>
        <p className="text-muted-foreground">
          Ask questions about any topic discussed in your podcasts
        </p>
      </div>

      {/* Filters */}
      <div className="mb-4 space-y-3">
        {/* Main Filter Row */}
        <div className="flex items-center gap-2 flex-wrap">
          <Mic className="h-4 w-4 text-muted-foreground shrink-0" />
          <span className="text-sm text-muted-foreground shrink-0">Chatting with:</span>
          <Select
            value={selectedChannel}
            onValueChange={(value) => {
              setSelectedChannel(value);
              setSelectedEpisode("all");
              if (messages.length > 0) {
                setMessages([]);
              }
            }}
          >
            <SelectTrigger className="w-[280px]">
              <SelectValue placeholder="Select a podcast" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">
                All Podcasts ({totalTranscribedEpisodes} episodes)
              </SelectItem>
              {channels.map((channel) => (
                <SelectItem key={channel.id} value={channel.slug}>
                  {channel.name} ({channel.transcribed_count} episodes)
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {loadingChannels && (
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          )}
          
          {/* Advanced Filter Toggle */}
          {selectedChannel !== "all" && episodes.length > 1 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="text-muted-foreground"
            >
              <Filter className="h-4 w-4 mr-1" />
              {showAdvanced ? "Hide" : "Filter by Episode"}
            </Button>
          )}
        </div>

        {/* Episode Filter (Advanced) */}
        {showAdvanced && selectedChannel !== "all" && (
          <div className="flex items-center gap-2 pl-6">
            <FileText className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm text-muted-foreground">Episode:</span>
            <Select
              value={selectedEpisode}
              onValueChange={(value) => {
                setSelectedEpisode(value);
                if (messages.length > 0) {
                  setMessages([]);
                }
              }}
            >
              <SelectTrigger className="w-[350px]">
                <SelectValue placeholder="All episodes" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Episodes</SelectItem>
                {episodes.map((episode) => (
                  <SelectItem key={episode.id} value={episode.id}>
                    <span className="truncate max-w-[300px] block">
                      {episode.title}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {loadingEpisodes && (
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
            )}
          </div>
        )}

        {/* Empty State */}
        {channels.length === 0 && !loadingChannels && (
          <div className="p-4 bg-muted/50 rounded-lg">
            <p className="text-sm text-muted-foreground">
              No transcribed podcasts yet.{" "}
              <Link href="/admin/add" className="text-primary hover:underline">
                Add and transcribe a podcast
              </Link>{" "}
              to start chatting.
            </p>
          </div>
        )}
      </div>

      <Card className="h-[600px] flex flex-col">
        {/* Messages */}
        <ScrollArea className="flex-1 p-4" ref={scrollRef}>
          {messages.length === 0 ? (
            <div className="h-full flex items-center justify-center">
              <div className="text-center text-muted-foreground">
                <Bot className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>Start a conversation by asking a question</p>
                <p className="text-sm mt-2">
                  Chatting with: <span className="font-medium">{getContextLabel()}</span>
                </p>
                <div className="mt-6 space-y-2 text-sm">
                  <p className="font-medium text-foreground">Try asking:</p>
                  <div className="flex flex-wrap gap-2 justify-center">
                    <Badge
                      variant="outline"
                      className="cursor-pointer hover:bg-muted"
                      onClick={() => setInput("What are the main topics discussed?")}
                    >
                      Main topics discussed?
                    </Badge>
                    <Badge
                      variant="outline"
                      className="cursor-pointer hover:bg-muted"
                      onClick={() => setInput("Summarize the key insights")}
                    >
                      Key insights
                    </Badge>
                    <Badge
                      variant="outline"
                      className="cursor-pointer hover:bg-muted"
                      onClick={() => setInput("What advice was given about investing?")}
                    >
                      Investing advice
                    </Badge>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className="space-y-6">
              {messages.map((message, i) => (
                <div
                  key={i}
                  className={`flex gap-3 ${
                    message.role === "user" ? "justify-end" : ""
                  }`}
                >
                  {message.role === "assistant" && (
                    <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0">
                      <Bot className="h-4 w-4 text-primary-foreground" />
                    </div>
                  )}

                  <div
                    className={`max-w-[80%] ${
                      message.role === "user"
                        ? "bg-primary text-primary-foreground rounded-lg px-4 py-2"
                        : ""
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{message.content}</p>

                    {/* Citations */}
                    {message.citations && message.citations.length > 0 && (
                      <div className="mt-4 space-y-2">
                        <p className="text-sm font-medium">Sources:</p>
                        {message.citations.slice(0, 5).map((citation, j) => (
                          <CitationCard key={j} citation={citation} />
                        ))}
                      </div>
                    )}
                  </div>

                  {message.role === "user" && (
                    <div className="w-8 h-8 rounded-full bg-secondary flex items-center justify-center shrink-0">
                      <User className="h-4 w-4" />
                    </div>
                  )}
                </div>
              ))}

              {loading && (
                <div className="flex gap-3">
                  <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center shrink-0">
                    <Bot className="h-4 w-4 text-primary-foreground" />
                  </div>
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Searching transcripts...
                  </div>
                </div>
              )}
            </div>
          )}
        </ScrollArea>

        {/* Input */}
        <div className="border-t p-4">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              placeholder={`Ask about ${getContextLabel().toLowerCase()}...`}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading || channels.length === 0}
              className="flex-1"
            />
            <Button
              type="submit"
              disabled={loading || !input.trim() || channels.length === 0}
            >
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </form>
        </div>
      </Card>
    </div>
  );
}

function CitationCard({ citation }: { citation: Citation }) {
  return (
    <Card className="bg-muted/50">
      <CardContent className="p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <p className="font-medium text-sm truncate">
              {citation.episode_title}
            </p>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              {citation.speaker && (
                <Badge variant="outline" className="text-xs">
                  {citation.speaker}
                </Badge>
              )}
              <span>{citation.timestamp}</span>
            </div>
          </div>
          {citation.episode_url && (
            <a
              href={`${citation.episode_url}&t=${Math.floor(citation.timestamp_ms / 1000)}`}
              target="_blank"
              rel="noopener noreferrer"
              className="shrink-0"
            >
              <ExternalLink className="h-4 w-4 text-muted-foreground hover:text-foreground" />
            </a>
          )}
        </div>
        <p className="text-xs text-muted-foreground mt-2 line-clamp-2">
          {citation.text}
        </p>
      </CardContent>
    </Card>
  );
}
