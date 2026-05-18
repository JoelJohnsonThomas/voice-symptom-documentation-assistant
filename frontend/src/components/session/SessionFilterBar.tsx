import { Search } from "lucide-react";
import { DateRangePicker, type DateRange } from "../ui/DateRangePicker";
import { Tabs } from "../ui/Tabs";
import { cn } from "@/lib/utils";

export type SessionFilterStatus = "all" | "draft" | "in_review" | "approved";

const STATUS_TABS: { value: SessionFilterStatus; label: string }[] = [
  { value: "all", label: "All" },
  { value: "draft", label: "Draft" },
  { value: "in_review", label: "In review" },
  { value: "approved", label: "Approved" },
];

interface SessionFilterBarProps {
  search: string;
  onSearchChange: (next: string) => void;
  status: SessionFilterStatus;
  onStatusChange: (next: SessionFilterStatus) => void;
  range: DateRange;
  onRangeChange: (next: DateRange) => void;
  className?: string;
}

export function SessionFilterBar({
  search,
  onSearchChange,
  status,
  onStatusChange,
  range,
  onRangeChange,
  className,
}: SessionFilterBarProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <label className="relative flex flex-1 items-center">
        <Search size={14} className="absolute left-2 text-[var(--text-muted)]" />
        <input
          type="search"
          value={search}
          placeholder="Search sessions…"
          onChange={(e) => onSearchChange(e.target.value)}
          aria-label="Search sessions"
          className="w-full rounded-md border border-[var(--border-primary)] bg-[var(--bg-card)] py-1.5 pl-7 pr-2 text-sm text-[var(--text-primary)]"
        />
      </label>
      <Tabs<SessionFilterStatus> tabs={STATUS_TABS} value={status} onChange={onStatusChange} />
      <DateRangePicker value={range} onChange={onRangeChange} />
    </div>
  );
}
