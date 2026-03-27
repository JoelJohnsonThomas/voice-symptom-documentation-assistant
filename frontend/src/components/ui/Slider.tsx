import { cn } from "@/lib/utils";

interface SliderProps {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  label?: string;
  displayValue?: string;
  className?: string;
}

export function Slider({
  value,
  onChange,
  min = 0,
  max = 100,
  step = 1,
  label,
  displayValue,
  className,
}: SliderProps) {
  return (
    <div className={cn("flex items-center gap-4", className)}>
      {label && (
        <label className="text-sm text-[var(--text-secondary)] min-w-[120px]">
          {label}
        </label>
      )}
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className={cn(
          "flex-1 h-1 rounded-full appearance-none cursor-pointer",
          "bg-[var(--bg-secondary,#1a1d2e)] outline-none",
          "[&::-webkit-slider-thumb]:appearance-none",
          "[&::-webkit-slider-thumb]:w-[18px] [&::-webkit-slider-thumb]:h-[18px]",
          "[&::-webkit-slider-thumb]:rounded-full",
          "[&::-webkit-slider-thumb]:bg-[var(--violet-500,#8b5cf6)]",
          "[&::-webkit-slider-thumb]:shadow-[0_0_8px_rgba(139,92,246,0.3)]",
          "[&::-webkit-slider-thumb]:cursor-pointer",
          "[&::-webkit-slider-thumb]:transition-shadow [&::-webkit-slider-thumb]:duration-200",
          "[&::-webkit-slider-thumb]:hover:shadow-[0_0_12px_rgba(139,92,246,0.5)]"
        )}
      />
      {displayValue && (
        <span className="text-sm font-semibold text-[var(--violet-500,#8b5cf6)] min-w-[40px] text-right">
          {displayValue}
        </span>
      )}
    </div>
  );
}
