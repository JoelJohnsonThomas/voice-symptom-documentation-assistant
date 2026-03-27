export function TypingIndicator() {
  return (
    <div className="flex items-center gap-2.5">
      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--bg-tertiary)] text-white">
        <span className="text-xs">AI</span>
      </div>
      <div className="flex gap-1 rounded-2xl rounded-bl-md border border-[var(--border-primary)] bg-[var(--bg-secondary)] px-4 py-3">
        <span className="h-2 w-2 animate-[bounce-dot_1.4s_ease-in-out_infinite] rounded-full bg-[var(--text-muted)]" />
        <span className="h-2 w-2 animate-[bounce-dot_1.4s_ease-in-out_0.2s_infinite] rounded-full bg-[var(--text-muted)]" />
        <span className="h-2 w-2 animate-[bounce-dot_1.4s_ease-in-out_0.4s_infinite] rounded-full bg-[var(--text-muted)]" />
      </div>
    </div>
  );
}
