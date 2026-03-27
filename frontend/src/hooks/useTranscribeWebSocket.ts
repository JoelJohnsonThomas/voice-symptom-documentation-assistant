import { useCallback, useRef } from "react";
import { useSessionStore } from "../stores/sessionStore";
import { useWebSocketStore } from "../stores/websocketStore";

interface UseTranscribeWSOptions {
  onPartialTranscript?: (text: string) => void;
  onFinalTranscript?: (text: string) => void;
  language?: string;
}

export function useTranscribeWebSocket(options: UseTranscribeWSOptions = {}) {
  const { onPartialTranscript, onFinalTranscript, language = "en" } = options;
  const wsRef = useRef<WebSocket | null>(null);
  const setTranscript = useSessionStore((s) => s.setTranscript);
  const setStatus = useWebSocketStore((s) => s.setTranscriptionStatus);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus("connecting");
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/transcribe?language=${language}`);

    ws.onopen = () => setStatus("connected");

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "partial") {
          onPartialTranscript?.(data.text);
        } else if (data.type === "final") {
          setTranscript(data.text);
          onFinalTranscript?.(data.text);
        }
      } catch {
        // non-JSON message, treat as plain text transcript
        setTranscript(event.data);
        onFinalTranscript?.(event.data);
      }
    };

    ws.onerror = () => setStatus("error");
    ws.onclose = () => setStatus("disconnected");

    wsRef.current = ws;
  }, [language, setStatus, setTranscript, onPartialTranscript, onFinalTranscript]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  const sendAudio = useCallback((data: Blob | ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  return { connect, disconnect, sendAudio };
}
