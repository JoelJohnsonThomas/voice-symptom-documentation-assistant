import { useState } from "react";
import { Send, Type } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";

interface TextInputCardProps {
  onSubmit: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function TextInputCard({
  onSubmit,
  disabled,
  placeholder = "Type symptoms or clinical notes...",
}: TextInputCardProps) {
  const [text, setText] = useState("");

  const handleSubmit = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    onSubmit(trimmed);
    setText("");
  };

  return (
    <GlassCard className="p-5">
      <div className="mb-3 flex items-center gap-2 text-[var(--text-muted)]">
        <Type size={14} />
        <span className="text-xs font-semibold uppercase tracking-wider">
          Text Input
        </span>
      </div>
      <div className="flex gap-2">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit();
            }
          }}
          placeholder={placeholder}
          disabled={disabled}
          rows={3}
          className="flex-1 resize-none rounded-lg border border-[var(--border-primary)] bg-[var(--bg-primary)]/50 px-3 py-2 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none transition-colors focus:border-[var(--accent-primary)] disabled:opacity-50"
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || !text.trim()}
          className="flex h-10 w-10 shrink-0 items-center justify-center self-end rounded-lg bg-[var(--accent-primary)] text-white transition-colors hover:bg-[var(--accent-primary)]/80 disabled:opacity-50"
          aria-label="Send text"
        >
          <Send size={16} />
        </button>
      </div>
    </GlassCard>
  );
}
