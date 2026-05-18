import { Tabs } from "../ui/Tabs";

export type TimeRange = "1h" | "24h" | "7d" | "30d";

const TABS: { value: TimeRange; label: string }[] = [
  { value: "1h", label: "1h" },
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
];

interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (next: TimeRange) => void;
  className?: string;
}

export function TimeRangeSelector({ value, onChange, className }: TimeRangeSelectorProps) {
  return <Tabs<TimeRange> tabs={TABS} value={value} onChange={onChange} className={className} />;
}
