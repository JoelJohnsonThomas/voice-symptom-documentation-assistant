import { create } from "zustand";
import type { ConversationMessage, ConversationMode, ExtractedEntity } from "../types/conversation";

interface ConversationState {
  messages: ConversationMessage[];
  entities: ExtractedEntity[];
  mode: ConversationMode;
  isTyping: boolean;
  isOpen: boolean;
  inputValue: string;

  addMessage: (message: ConversationMessage) => void;
  updateMessage: (id: string, content: string) => void;
  setEntities: (entities: ExtractedEntity[]) => void;
  addEntity: (entity: ExtractedEntity) => void;
  setMode: (mode: ConversationMode) => void;
  setTyping: (typing: boolean) => void;
  setOpen: (open: boolean) => void;
  toggleOpen: () => void;
  setInputValue: (value: string) => void;
  clearMessages: () => void;
}

export const useConversationStore = create<ConversationState>()((set) => ({
  messages: [],
  entities: [],
  mode: "patient",
  isTyping: false,
  isOpen: false,
  inputValue: "",

  addMessage: (message) =>
    set((state) => ({
      messages: [...state.messages, message],
      entities: message.entities
        ? [...state.entities, ...message.entities]
        : state.entities,
    })),

  updateMessage: (id, content) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, content } : m
      ),
    })),

  setEntities: (entities) => set({ entities }),
  addEntity: (entity) =>
    set((state) => ({ entities: [...state.entities, entity] })),

  setMode: (mode) => set({ mode }),
  setTyping: (isTyping) => set({ isTyping }),
  setOpen: (isOpen) => set({ isOpen }),
  toggleOpen: () => set((state) => ({ isOpen: !state.isOpen })),
  setInputValue: (inputValue) => set({ inputValue }),
  clearMessages: () => set({ messages: [], entities: [] }),
}));
