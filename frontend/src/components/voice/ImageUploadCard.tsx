import { useRef, useState } from "react";
import { Camera, X, Upload } from "lucide-react";
import { GlassCard } from "../ui/GlassCard";

interface ImageUploadCardProps {
  onUpload: (file: File) => void;
  disabled?: boolean;
}

export function ImageUploadCard({ onUpload, disabled }: ImageUploadCardProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string>("");

  const handleFile = (file: File) => {
    setFileName(file.name);
    const reader = new FileReader();
    reader.onload = (e) => setPreview(e.target?.result as string);
    reader.readAsDataURL(file);
    onUpload(file);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file?.type.startsWith("image/")) handleFile(file);
  };

  const clear = () => {
    setPreview(null);
    setFileName("");
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <GlassCard className="p-5">
      <div className="mb-3 flex items-center gap-2 text-[var(--text-muted)]">
        <Camera size={14} />
        <span className="text-xs font-semibold uppercase tracking-wider">
          Image Upload
        </span>
      </div>

      {preview ? (
        <div className="relative">
          <img
            src={preview}
            alt={fileName}
            className="h-32 w-full rounded-lg object-cover"
          />
          <button
            onClick={clear}
            className="absolute right-2 top-2 rounded-full bg-black/60 p-1 text-white hover:bg-black/80"
            aria-label="Remove image"
          >
            <X size={14} />
          </button>
          <p className="mt-2 truncate text-xs text-[var(--text-muted)]">
            {fileName}
          </p>
        </div>
      ) : (
        <button
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={handleDrop}
          disabled={disabled}
          className="flex w-full flex-col items-center gap-2 rounded-lg border-2 border-dashed border-[var(--border-primary)] p-6 text-[var(--text-muted)] transition-colors hover:border-[var(--accent-primary)]/50 hover:text-[var(--text-secondary)] disabled:opacity-50"
        >
          <Upload size={24} />
          <span className="text-sm">Drop image or click to upload</span>
        </button>
      )}

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFile(file);
        }}
      />
    </GlassCard>
  );
}
