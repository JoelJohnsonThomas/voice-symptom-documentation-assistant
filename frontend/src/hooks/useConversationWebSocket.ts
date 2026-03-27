import { useCallback, useRef } from "react";
import { useConversationStore } from "../stores/conversationStore";
import { useWebSocketStore } from "../stores/websocketStore";
import type { ConversationMessage } from "../types/conversation";

interface UseConversationWSOptions {
  onEmergency?: (message: ConversationMessage) => void;
}

export function useConversationWebSocket(options: UseConversationWSOptions = {}) {
  const { onEmergency } = options;
  const wsRef = useRef<WebSocket | null>(null);
  const addMessage = useConversationStore((s) => s.addMessage);
  const setTyping = useConversationStore((s) => s.setTyping);
  const setStatus = useWebSocketStore((s) => s.setConversationStatus);

  const connect = useCallback(
    (sessionId?: string) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;

      setStatus("connecting");
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const query = sessionId ? `?session_id=${sessionId}` : "";
      const ws = new WebSocket(`${protocol}//${window.location.host}/ws/conversation${query}`);

      ws.onopen = () => setStatus("connected");

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "typing") {
            setTyping(true);
            return;
          }

          if (data.type === "message") {
            setTyping(false);
            const msg: ConversationMessage = {
              id: data.id || crypto.randomUUID(),
              role: data.role || "assistant",
              content: data.content,
              timestamp: data.timestamp || new Date().toISOString(),
              isEmergency: data.isEmergency,
              entities: data.entities,
            };
            addMessage(msg);
            if (msg.isEmergency) onEmergency?.(msg);
          }
        } catch {
          // plain text fallback
          setTyping(false);
          addMessage({
            id: crypto.randomUUID(),
            role: "assistant",
            content: event.data,
            timestamp: new Date().toISOString(),
          });
        }
      };

      ws.onerror = () => setStatus("error");
      ws.onclose = () => {
        setStatus("disconnected");
        setTyping(false);
      };

      wsRef.current = ws;
    },
    [setStatus, addMessage, setTyping, onEmergency]
  );

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const sendMessage = useCallback((content: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "message", content }));
    }
  }, []);

  return { connect, disconnect, sendMessage };
}
