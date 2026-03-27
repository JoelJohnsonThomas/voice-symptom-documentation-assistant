import { useEffect, useRef } from "react";
import { cn } from "../../lib/utils";

interface WaveformVisualizerProps {
  audioLevel: number;
  isActive: boolean;
  barCount?: number;
  className?: string;
}

export function WaveformVisualizer({
  audioLevel,
  isActive,
  barCount = 40,
  className,
}: WaveformVisualizerProps) {
  const barsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!barsRef.current || !isActive) return;
    const bars = barsRef.current.children;
    for (let i = 0; i < bars.length; i++) {
      const bar = bars[i] as HTMLElement;
      const distance = Math.abs(i - barCount / 2) / (barCount / 2);
      const height = Math.max(
        4,
        audioLevel * 100 * (1 - distance * 0.6) * (0.5 + Math.random() * 0.5)
      );
      bar.style.height = `${height}%`;
    }
  }, [audioLevel, isActive, barCount]);

  return (
    <div
      ref={barsRef}
      className={cn(
        "flex h-16 items-end justify-center gap-[2px]",
        className
      )}
    >
      {Array.from({ length: barCount }).map((_, i) => (
        <div
          key={i}
          className={cn(
            "w-[3px] rounded-full transition-[height] duration-75",
            isActive
              ? "bg-gradient-to-t from-[var(--accent-primary)] to-[var(--accent-secondary)]"
              : "bg-[var(--border-primary)]"
          )}
          style={{ height: isActive ? undefined : "4px" }}
        />
      ))}
    </div>
  );
}
