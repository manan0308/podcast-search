"use client";

import Link from "next/link";
import { User, Bot, ExternalLink, Clock } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { ChatResponse } from "@/lib/types";
import { cn, formatDuration } from "@/lib/utils";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: ChatResponse["citations"];
  timestamp: Date;
}

interface ChatMessageProps {
  message: Message;
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex gap-3", isUser && "flex-row-reverse")}>
      {/* Avatar */}
      <div
        className={cn(
          "shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      {/* Content */}
      <div className={cn("flex-1 max-w-[80%]", isUser && "text-right")}>
        <Card
          className={cn(
            "inline-block p-3 text-sm",
            isUser ? "bg-primary text-primary-foreground" : "bg-muted"
          )}
        >
          <p className="whitespace-pre-wrap">{message.content}</p>
        </Card>

        {/* Citations */}
        {message.citations && message.citations.length > 0 && (
          <div className="mt-2 space-y-2">
            <p className="text-xs text-muted-foreground">Sources:</p>
            <div className="space-y-1">
              {message.citations.map((citation, index) => (
                <CitationCard key={index} citation={citation} index={index + 1} />
              ))}
            </div>
          </div>
        )}

        {/* Timestamp */}
        <p className="text-xs text-muted-foreground mt-1">
          {message.timestamp.toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>
    </div>
  );
}

interface CitationCardProps {
  citation: ChatResponse["citations"][0];
  index: number;
}

function CitationCard({ citation, index }: CitationCardProps) {
  const youtubeLink = citation.episode_url
    ? `${citation.episode_url}&t=${Math.floor(citation.timestamp_ms / 1000)}`
    : null;

  return (
    <Card className="p-2 text-xs">
      <div className="flex items-start gap-2">
        <Badge variant="secondary" className="shrink-0">
          {index}
        </Badge>
        <div className="flex-1 min-w-0">
          <Link
            href={`/podcasts/${citation.channel_slug}/episodes/${citation.episode_id}`}
            className="font-medium hover:underline line-clamp-1"
          >
            {citation.episode_title}
          </Link>
          <div className="flex items-center gap-2 text-muted-foreground mt-0.5">
            <span>{citation.channel_name}</span>
            <span>•</span>
            <span className="flex items-center gap-0.5">
              <Clock className="h-3 w-3" />
              {citation.timestamp}
            </span>
          </div>
          <p className="text-muted-foreground mt-1 line-clamp-2">{citation.text}</p>
          {youtubeLink && (
            <a
              href={youtubeLink}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-primary hover:underline mt-1"
            >
              Watch <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
      </div>
    </Card>
  );
}
