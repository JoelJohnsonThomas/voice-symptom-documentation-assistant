import { create } from "zustand";

type WSStatus = "disconnected" | "connecting" | "connected" | "error";

interface WebSocketState {
  transcription: WSStatus;
  conversation: WSStatus;
  soap: WSStatus;

  setTranscriptionStatus: (status: WSStatus) => void;
  setConversationStatus: (status: WSStatus) => void;
  setSOAPStatus: (status: WSStatus) => void;
  resetAll: () => void;
}

export const useWebSocketStore = create<WebSocketState>()((set) => ({
  transcription: "disconnected",
  conversation: "disconnected",
  soap: "disconnected",

  setTranscriptionStatus: (transcription) => set({ transcription }),
  setConversationStatus: (conversation) => set({ conversation }),
  setSOAPStatus: (soap) => set({ soap }),
  resetAll: () =>
    set({
      transcription: "disconnected",
      conversation: "disconnected",
      soap: "disconnected",
    }),
}));
