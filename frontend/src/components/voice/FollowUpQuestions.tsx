import { useState } from "react";
import { HelpCircle, ChevronRight } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";
import type { FollowUpQuestion } from "../../types/api";

interface FollowUpQuestionsProps {
  questions: FollowUpQuestion[];
  onAnswer: (id: string, answer: string) => void;
}

export function FollowUpQuestions({ questions, onAnswer }: FollowUpQuestionsProps) {
  const [answers, setAnswers] = useState<Record<string, string>>({});

  if (questions.length === 0) return null;

  return (
    <GlassCard glow="cyan" className="p-5">
      <div className="mb-3 flex items-center gap-2 text-[var(--accent-primary)]">
        <HelpCircle size={14} />
        <span className="text-xs font-semibold uppercase tracking-wider">
          Follow-up Questions
        </span>
      </div>
      <div className="space-y-3">
        {questions.map((q) => (
          <div key={q.id} className="space-y-1.5">
            <p className="text-sm text-[var(--text-primary)]">
              {q.required && (
                <span className="mr-1 text-[var(--status-error)]">*</span>
              )}
              {q.question}
            </p>
            {q.answer ? (
              <p className="text-sm text-[var(--text-secondary)]">
                → {q.answer}
              </p>
            ) : (
              <div className="flex gap-2">
                <input
                  type="text"
                  value={answers[q.id] || ""}
                  onChange={(e) =>
                    setAnswers((prev) => ({ ...prev, [q.id]: e.target.value }))
                  }
                  placeholder="Type answer..."
                  className="flex-1 rounded-md border border-[var(--border-primary)] bg-[var(--bg-primary)]/50 px-2 py-1.5 text-sm text-[var(--text-primary)] placeholder-[var(--text-muted)] outline-none focus:border-[var(--accent-primary)]"
                  onKeyDown={(e) => {
                    const val = answers[q.id];
                    if (e.key === "Enter" && val?.trim()) {
                      onAnswer(q.id, val.trim());
                    }
                  }}
                />
                <button
                  onClick={() => {
                    const val = answers[q.id];
                    if (val?.trim()) {
                      onAnswer(q.id, val.trim());
                    }
                  }}
                  className="rounded-md bg-[var(--accent-primary)]/20 px-2 text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/30"
                  aria-label="Submit answer"
                >
                  <ChevronRight size={16} />
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </GlassCard>
  );
}
