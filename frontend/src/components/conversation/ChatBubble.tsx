import { AlertTriangle, Bot, User } from "lucide-react";
import { cn } from "../../lib/utils";
import type { ConversationMessage } from "../../types/conversation";

interface ChatBubbleProps {
  message: ConversationMessage;
}

export function ChatBubble({ message }: ChatBubbleProps) {
  const isUser = message.role === "user";
  const isSystem = message.role === "system";

  return (
    <div
      className={cn(
        "flex gap-2.5 animate-[bubble-in_0.3s_ease-out]",
        isUser ? "flex-row-reverse" : "flex-row"
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-white",
          isUser
            ? "bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)]"
            : isSystem
            ? "bg-[var(--status-warning)]"
            : "bg-[var(--bg-tertiary)]"
        )}
      >
        {isUser ? <User size={14} /> : isSystem ? <AlertTriangle size={14} /> : <Bot size={14} />}
      </div>

      {/* Bubble */}
      <div
        className={cn(
          "max-w-[75%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser
            ? "rounded-br-md bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)] text-white"
            : "rounded-bl-md border border-[var(--border-primary)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]",
          message.isEmergency &&
            "border-[var(--status-error)]/50 bg-[var(--status-error)]/10"
        )}
      >
        {message.isEmergency && (
          <p className="mb-1 flex items-center gap-1 text-xs font-bold text-[var(--status-error)]">
            <AlertTriangle size={12} />
            EMERGENCY
          </p>
        )}
        <p>{message.content}</p>
        <p
          className={cn(
            "mt-1 text-[10px]",
            isUser ? "text-white/60" : "text-[var(--text-muted)]"
          )}
        >
          {new Date(message.timestamp).toLocaleTimeString()}
        </p>
      </div>
    </div>
  );
}
