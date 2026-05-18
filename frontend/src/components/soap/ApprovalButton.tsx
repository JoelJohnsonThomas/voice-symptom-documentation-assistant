import { Check, Loader2 } from "lucide-react";
import { useApproveVersion } from "../../hooks/useSoapReview";

interface ApprovalButtonProps {
  sessionId: string;
  versionId: string | null | undefined;
  onApproved?: (sessionApproved: boolean) => void;
  size?: "sm" | "md";
}

export function ApprovalButton({ sessionId, versionId, onApproved, size = "md" }: ApprovalButtonProps) {
  const approve = useApproveVersion(sessionId);
  const handleClick = () => {
    if (!versionId) return;
    approve.mutate(versionId, {
      onSuccess: (data) => onApproved?.(data.session_approved),
    });
  };
  const isLoading = approve.isPending;
  const isSmall = size === "sm";

  return (
    <button
      type="button"
      onClick={handleClick}
      disabled={!versionId || isLoading}
      className={
        "inline-flex items-center gap-2 rounded-md border border-[var(--status-online)]/30 bg-[var(--status-online)]/10 font-medium text-[var(--status-online)] transition-colors hover:bg-[var(--status-online)]/20 disabled:opacity-50 " +
        (isSmall ? "px-2 py-1 text-xs" : "px-3 py-1.5 text-sm")
      }
    >
      {isLoading ? <Loader2 size={isSmall ? 12 : 14} className="animate-spin" /> : <Check size={isSmall ? 12 : 14} />}
      Approve SOAP
    </button>
  );
}
