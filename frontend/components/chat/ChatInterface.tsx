"use client";

import { useState, useRef, useEffect, FormEvent } from "react";
import { Send, Loader2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatMessage } from "./ChatMessage";
import { api } from "@/lib/api";
import type { ChatResponse, ChatMessage as ChatMessageType } from "@/lib/types";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: ChatResponse["citations"];
  timestamp: Date;
}

interface ChatInterfaceProps {
  channelSlug?: string;
}

export function ChatInterface({ channelSlug }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      // Build conversation history
      const history: ChatMessageType[] = messages.map((m) => ({
        role: m.role,
        content: m.content,
      }));

      const response = await api.chat({
        message: userMessage.content,
        conversation_history: history,
        channel_slug: channelSlug,
      });

      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: response.response,
        citations: response.citations,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Chat error:", error);
      const errorMessage: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: "Sorry, I encountered an error processing your request. Please try again.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  };

  const clearChat = () => {
    setMessages([]);
  };

  return (
    <div className="flex flex-col h-[600px] border rounded-lg">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <div>
          <h3 className="font-semibold">Chat with Podcasts</h3>
          <p className="text-xs text-muted-foreground">
            {channelSlug
              ? "Ask questions about this podcast"
              : "Ask questions about any transcribed podcast"}
          </p>
        </div>
        {messages.length > 0 && (
          <Button variant="ghost" size="sm" onClick={clearChat}>
            <Trash2 className="h-4 w-4 mr-1" />
            Clear
          </Button>
        )}
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 p-4" ref={scrollRef}>
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center text-muted-foreground">
            <p className="text-lg font-medium mb-2">Start a conversation</p>
            <p className="text-sm max-w-md">
              Ask questions about podcast content and get answers with citations
              from the transcripts.
            </p>
            <div className="mt-4 space-y-2 text-sm">
              <p className="text-muted-foreground">Try asking:</p>
              <div className="space-y-1">
                <button
                  onClick={() => setInput("What topics are discussed most frequently?")}
                  className="block w-full text-left px-3 py-2 rounded-lg bg-muted hover:bg-muted/80 transition-colors"
                >
                  "What topics are discussed most frequently?"
                </button>
                <button
                  onClick={() => setInput("Summarize the key insights about AI")}
                  className="block w-full text-left px-3 py-2 rounded-lg bg-muted hover:bg-muted/80 transition-colors"
                >
                  "Summarize the key insights about AI"
                </button>
                <button
                  onClick={() => setInput("What did the guests say about productivity?")}
                  className="block w-full text-left px-3 py-2 rounded-lg bg-muted hover:bg-muted/80 transition-colors"
                >
                  "What did the guests say about productivity?"
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
            {isLoading && (
              <div className="flex items-center gap-2 text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                <span className="text-sm">Thinking...</span>
              </div>
            )}
          </div>
        )}
      </ScrollArea>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t">
        <div className="flex gap-2">
          <Input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about the podcasts..."
            disabled={isLoading}
            className="flex-1"
          />
          <Button type="submit" disabled={isLoading || !input.trim()}>
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
      </form>
    </div>
  );
}
