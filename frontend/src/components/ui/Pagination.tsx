import { ChevronLeft, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface PaginationProps {
  page: number;
  pageCount: number;
  onPageChange: (next: number) => void;
  className?: string;
}

export function Pagination({ page, pageCount, onPageChange, className }: PaginationProps) {
  const canPrev = page > 1;
  const canNext = page < pageCount;
  return (
    <nav
      aria-label="Pagination"
      className={cn("flex items-center justify-between text-xs text-[var(--text-secondary)]", className)}
    >
      <button
        type="button"
        onClick={() => canPrev && onPageChange(page - 1)}
        disabled={!canPrev}
        aria-label="Previous page"
        className="inline-flex items-center gap-1 rounded border border-[var(--border-primary)] px-2 py-1 disabled:opacity-40"
      >
        <ChevronLeft size={12} />
        Prev
      </button>
      <span>
        Page <span className="font-medium text-[var(--text-primary)]">{page}</span> of {pageCount}
      </span>
      <button
        type="button"
        onClick={() => canNext && onPageChange(page + 1)}
        disabled={!canNext}
        aria-label="Next page"
        className="inline-flex items-center gap-1 rounded border border-[var(--border-primary)] px-2 py-1 disabled:opacity-40"
      >
        Next
        <ChevronRight size={12} />
      </button>
    </nav>
  );
}
