import { useEffect, useRef, useState, useCallback } from "react";

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export interface JobUpdate {
  type: "job_update";
  job_id: string;
  batch_id: string;
  episode_id: string;
  status: string;
  progress: number;
  current_step: string;
  error_message?: string;
  timestamp: string;
}

export interface BatchUpdate {
  type: "batch_update";
  batch_id: string;
  status: string;
  completed_episodes: number;
  failed_episodes: number;
  total_episodes: number;
  progress_percent: number;
  timestamp: string;
}

export type WebSocketMessage = JobUpdate | BatchUpdate;

interface UseWebSocketOptions {
  channels?: string[];
  onMessage?: (message: WebSocketMessage) => void;
  onConnect?: () => void;
  onDisconnect?: () => void;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  lastMessage: WebSocketMessage | null;
  subscribe: (channel: string) => void;
  unsubscribe: (channel: string) => void;
  sendMessage: (message: object) => void;
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    channels = ["updates"],
    onMessage,
    onConnect,
    onDisconnect,
    reconnectInterval = 3000,
    maxReconnectAttempts = 10,
  } = options;

  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const pingIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      return;
    }

    const channelParam = channels.join(",");
    const wsUrl = `${WS_URL}/api/ws?channels=${encodeURIComponent(channelParam)}`;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setIsConnected(true);
        reconnectAttemptsRef.current = 0;
        onConnect?.();

        // Start ping interval to keep connection alive
        pingIntervalRef.current = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ action: "ping" }));
          }
        }, 30000);
      };

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as WebSocketMessage;

          // Ignore pong messages
          if ((message as any).type === "pong") {
            return;
          }

          setLastMessage(message);
          onMessage?.(message);
        } catch (e) {
          console.error("Failed to parse WebSocket message:", e);
        }
      };

      ws.onclose = () => {
        setIsConnected(false);
        onDisconnect?.();

        // Clear ping interval
        if (pingIntervalRef.current) {
          clearInterval(pingIntervalRef.current);
        }

        // Attempt reconnection
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current += 1;
          reconnectTimeoutRef.current = setTimeout(connect, reconnectInterval);
        }
      };

      ws.onerror = (error) => {
        console.error("WebSocket error:", error);
      };

      wsRef.current = ws;
    } catch (e) {
      console.error("Failed to create WebSocket:", e);
    }
  }, [channels, onMessage, onConnect, onDisconnect, reconnectInterval, maxReconnectAttempts]);

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
    }
    if (pingIntervalRef.current) {
      clearInterval(pingIntervalRef.current);
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  }, []);

  const subscribe = useCallback((channel: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: "subscribe", channel }));
    }
  }, []);

  const unsubscribe = useCallback((channel: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: "unsubscribe", channel }));
    }
  }, []);

  const sendMessage = useCallback((message: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    }
  }, []);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  return {
    isConnected,
    lastMessage,
    subscribe,
    unsubscribe,
    sendMessage,
  };
}

// Hook for subscribing to a specific batch
export function useBatchUpdates(batchId: string, onUpdate?: (update: BatchUpdate | JobUpdate) => void) {
  const [jobs, setJobs] = useState<Record<string, JobUpdate>>({});
  const [batchStatus, setBatchStatus] = useState<BatchUpdate | null>(null);

  const handleMessage = useCallback((message: WebSocketMessage) => {
    if (message.type === "job_update" && message.batch_id === batchId) {
      setJobs((prev) => ({
        ...prev,
        [message.job_id]: message as JobUpdate,
      }));
      onUpdate?.(message);
    } else if (message.type === "batch_update" && message.batch_id === batchId) {
      setBatchStatus(message as BatchUpdate);
      onUpdate?.(message);
    }
  }, [batchId, onUpdate]);

  const { isConnected } = useWebSocket({
    channels: [`batch:${batchId}`, "updates"],
    onMessage: handleMessage,
  });

  return {
    isConnected,
    jobs,
    batchStatus,
  };
}

// Hook for subscribing to a specific job
export function useJobUpdates(jobId: string, onUpdate?: (update: JobUpdate) => void) {
  const [status, setStatus] = useState<JobUpdate | null>(null);

  const handleMessage = useCallback((message: WebSocketMessage) => {
    if (message.type === "job_update" && message.job_id === jobId) {
      setStatus(message as JobUpdate);
      onUpdate?.(message as JobUpdate);
    }
  }, [jobId, onUpdate]);

  const { isConnected } = useWebSocket({
    channels: [`job:${jobId}`],
    onMessage: handleMessage,
  });

  return {
    isConnected,
    status,
  };
}
