import { cn } from "@/lib/utils";

interface Tab<T extends string> {
  value: T;
  label: string;
  count?: number;
}

interface TabsProps<T extends string> {
  tabs: Tab<T>[];
  value: T;
  onChange: (next: T) => void;
  className?: string;
}

export function Tabs<T extends string>({ tabs, value, onChange, className }: TabsProps<T>) {
  return (
    <div
      role="tablist"
      className={cn(
        "inline-flex gap-1 rounded-md border border-[var(--border-primary)] bg-white/[0.02] p-1 text-xs",
        className,
      )}
    >
      {tabs.map((tab) => {
        const active = tab.value === value;
        return (
          <button
            key={tab.value}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.value)}
            className={cn(
              "rounded px-3 py-1 transition-colors",
              active
                ? "bg-[var(--accent-primary)]/15 text-[var(--accent-primary)]"
                : "text-[var(--text-muted)] hover:bg-white/[0.04]",
            )}
          >
            {tab.label}
            {typeof tab.count === "number" && (
              <span className="ml-1.5 rounded bg-white/[0.06] px-1 text-[10px]">{tab.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
