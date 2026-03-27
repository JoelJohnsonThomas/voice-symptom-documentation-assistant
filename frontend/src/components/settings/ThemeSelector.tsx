import { Check } from "lucide-react";
import { cn } from "../../lib/utils";
import { useThemeStore } from "../../stores/themeStore";
import { THEMES } from "../../types/theme";

export function ThemeSelector() {
  const { theme, setTheme } = useThemeStore();

  return (
    <div>
      <h4 className="mb-3 text-sm font-medium text-[var(--text-primary)]">
        Theme
      </h4>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {THEMES.map((t) => (
          <button
            key={t.name}
            onClick={() => setTheme(t.name)}
            className={cn(
              "relative flex flex-col rounded-lg border p-3 text-left transition-all",
              theme === t.name
                ? "border-[var(--accent-primary)] bg-[var(--accent-primary)]/5"
                : "border-[var(--border-primary)] hover:border-[var(--border-hover)]"
            )}
          >
            {/* Preview dots */}
            <div className="mb-2 flex gap-1.5">
              {t.previewColors.map((color, i) => (
                <span
                  key={i}
                  className="h-4 w-4 rounded-full border border-white/10"
                  style={{ backgroundColor: color }}
                />
              ))}
            </div>
            <span className="text-sm font-medium text-[var(--text-primary)]">
              {t.label}
            </span>
            <span className="text-xs text-[var(--text-muted)]">
              {t.description}
            </span>
            {theme === t.name && (
              <Check
                size={14}
                className="absolute right-2 top-2 text-[var(--accent-primary)]"
              />
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
