import { useEffect, useRef } from "react";
import { Send, X, MessageSquare } from "lucide-react";
import { ChatBubble } from "./ChatBubble";
import { TypingIndicator } from "./TypingIndicator";
import { EntitySidebar } from "./EntitySidebar";
import { useConversationStore } from "../../stores/conversationStore";
import { useConversationWebSocket } from "../../hooks/useConversationWebSocket";
import { cn } from "../../lib/utils";

interface ConversationPanelProps {
  sessionId?: string;
}

export function ConversationPanel({ sessionId }: ConversationPanelProps) {
  const {
    messages,
    entities,
    isTyping,
    isOpen,
    inputValue,
    setOpen,
    setInputValue,
    addMessage,
  } = useConversationStore();

  const { connect, disconnect, sendMessage } = useConversationWebSocket();
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isOpen) {
      connect(sessionId);
    }
    return () => disconnect();
  }, [isOpen, sessionId, connect, disconnect]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  const handleSend = () => {
    const text = inputValue.trim();
    if (!text) return;

    addMessage({
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    });
    sendMessage(text);
    setInputValue("");
  };

  if (!isOpen) return null;

  return (
    <div className="flex h-full flex-col border-l border-[var(--border-primary)] bg-[var(--bg-secondary)]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-[var(--border-primary)] px-4 py-3">
        <div className="flex items-center gap-2">
          <MessageSquare size={16} className="text-[var(--accent-primary)]" />
          <span className="text-sm font-semibold text-[var(--text-primary)]">
            Conversation
          </span>
        </div>
        <button
          onClick={() => setOpen(false)}
          className="rounded-md p-1 text-[var(--text-muted)] hover:bg-white/[0.06]"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Messages */}
        <div className="flex flex-1 flex-col">
          <div className="flex-1 space-y-3 overflow-y-auto p-4">
            {messages.map((msg) => (
              <ChatBubble key={msg.id} message={msg} />
            ))}
            {isTyping && <TypingIndicator />}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="border-t border-[var(--border-primary)] p-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={inputValue}
                onChange={(e) => setInputValue(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleSend()}
                placeholder="Ask a question..."
                className="flex-1 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)]/50 px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none focus:border-[var(--accent-primary)]"
              />
              <button
                onClick={handleSend}
                disabled={!inputValue.trim()}
                className="rounded-lg bg-[var(--accent-primary)] px-3 py-2 text-white hover:bg-[var(--accent-primary)]/80 disabled:opacity-50"
              >
                <Send size={16} />
              </button>
            </div>
          </div>
        </div>

        {/* Entity sidebar */}
        {entities.length > 0 && (
          <div className="hidden w-48 overflow-y-auto border-l border-[var(--border-primary)] p-3 lg:block">
            <EntitySidebar entities={entities} />
          </div>
        )}
      </div>
    </div>
  );
}
