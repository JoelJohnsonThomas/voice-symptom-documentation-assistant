import { useCallback, useRef } from "react";
import { useSessionStore } from "../stores/sessionStore";
import { useWebSocketStore } from "../stores/websocketStore";
import type { DocumentationResult } from "../types/api";

export function useSOAPStream() {
  const wsRef = useRef<WebSocket | null>(null);
  const setDocumentation = useSessionStore((s) => s.setDocumentation);
  const setProcessing = useSessionStore((s) => s.setProcessing);
  const setPipelineStages = useSessionStore((s) => s.setPipelineStages);
  const setCurrentStage = useSessionStore((s) => s.setCurrentStage);
  const setStatus = useWebSocketStore((s) => s.setSOAPStatus);

  const connect = useCallback(
    (sessionId: string) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) return;

      setStatus("connecting");
      setProcessing(true);
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(
        `${protocol}//${window.location.host}/ws/soap?session_id=${sessionId}`
      );

      ws.onopen = () => setStatus("connected");

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);

          if (data.type === "pipeline") {
            setPipelineStages(data.stages);
            setCurrentStage(data.currentStage);
          }

          if (data.type === "result") {
            const doc = data.documentation as DocumentationResult;
            setDocumentation(doc);
            setProcessing(false);
            setCurrentStage(null);
          }

          if (data.type === "error") {
            console.error("SOAP stream error:", data.message);
            setProcessing(false);
            setCurrentStage(null);
          }
        } catch {
          // ignore non-JSON
        }
      };

      ws.onerror = () => {
        setStatus("error");
        setProcessing(false);
      };
      ws.onclose = () => setStatus("disconnected");

      wsRef.current = ws;
    },
    [setStatus, setProcessing, setDocumentation, setPipelineStages, setCurrentStage]
  );

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    wsRef.current = null;
  }, []);

  return { connect, disconnect };
}
