import { Download, FileJson, FileText, Send } from "lucide-react";
import { IconButton } from "../ui/IconButton";

interface ExportBarProps {
  onExportJSON: () => void;
  onExportPDF: () => void;
  onExportFHIR: () => void;
  onPushEHR: () => void;
  disabled?: boolean;
}

export function ExportBar({
  onExportJSON,
  onExportPDF,
  onExportFHIR,
  onPushEHR,
  disabled,
}: ExportBarProps) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-[var(--border-primary)] bg-[var(--bg-secondary)] px-3 py-2">
      <span className="mr-2 text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
        Export
      </span>
      <IconButton
        variant="outline"
        size="sm"
        onClick={onExportJSON}
        disabled={disabled}
        aria-label="Export JSON"
      >
        <FileJson size={14} />
      </IconButton>
      <IconButton
        variant="outline"
        size="sm"
        onClick={onExportPDF}
        disabled={disabled}
        aria-label="Export PDF"
      >
        <FileText size={14} />
      </IconButton>
      <IconButton
        variant="outline"
        size="sm"
        onClick={onExportFHIR}
        disabled={disabled}
        aria-label="Export FHIR"
      >
        <Download size={14} />
      </IconButton>
      <div className="mx-1 h-4 w-px bg-[var(--border-primary)]" />
      <IconButton
        variant="solid"
        size="sm"
        onClick={onPushEHR}
        disabled={disabled}
        aria-label="Push to EHR"
      >
        <Send size={14} />
      </IconButton>
    </div>
  );
}
