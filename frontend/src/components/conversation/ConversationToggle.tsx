import { MessageSquare } from "lucide-react";
import { useConversationStore } from "../../stores/conversationStore";
import { cn } from "../../lib/utils";

export function ConversationToggle() {
  const { isOpen, toggleOpen, messages } = useConversationStore();
  const unread = messages.filter((m) => m.role === "assistant").length;

  return (
    <button
      onClick={toggleOpen}
      className={cn(
        "fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full shadow-xl transition-all",
        "bg-gradient-to-br from-[var(--accent-primary)] to-[var(--accent-secondary)]",
        "hover:shadow-[var(--accent-primary)]/40 hover:scale-105",
        isOpen && "rotate-0"
      )}
      aria-label={isOpen ? "Close conversation" : "Open conversation"}
    >
      <MessageSquare size={22} className="text-white" />
      {unread > 0 && !isOpen && (
        <span className="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--status-error)] text-[10px] font-bold text-white">
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </button>
  );
}
