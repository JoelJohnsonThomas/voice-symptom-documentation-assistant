import { CalendarRange } from "lucide-react";
import { cn } from "@/lib/utils";

export interface DateRange {
  from: string | null;
  to: string | null;
}

interface DateRangePickerProps {
  value: DateRange;
  onChange: (next: DateRange) => void;
  className?: string;
}

export function DateRangePicker({ value, onChange, className }: DateRangePickerProps) {
  return (
    <div className={cn("flex items-center gap-2 text-xs", className)}>
      <CalendarRange size={14} className="text-[var(--text-muted)]" />
      <label className="flex items-center gap-1 text-[var(--text-muted)]">
        From
        <input
          type="date"
          value={value.from ?? ""}
          onChange={(e) => onChange({ ...value, from: e.target.value || null })}
          className="rounded border border-[var(--border-primary)] bg-[var(--bg-card)] px-2 py-1 text-[var(--text-primary)]"
        />
      </label>
      <label className="flex items-center gap-1 text-[var(--text-muted)]">
        To
        <input
          type="date"
          value={value.to ?? ""}
          onChange={(e) => onChange({ ...value, to: e.target.value || null })}
          className="rounded border border-[var(--border-primary)] bg-[var(--bg-card)] px-2 py-1 text-[var(--text-primary)]"
        />
      </label>
    </div>
  );
}
