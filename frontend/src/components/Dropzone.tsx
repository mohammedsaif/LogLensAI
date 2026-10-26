import { FileUp, UploadCloud } from "lucide-react";
import { useRef, useState } from "react";
import { cn, formatBytes } from "@/lib/utils";

export interface DropzoneProps {
  accept: string[];
  maxBytes: number;
  disabled?: boolean;
  onFile: (file: File) => void;
}

export function validateFile(file: File, accept: string[], maxBytes: number): string | null {
  const ext = file.name.includes(".") ? `.${file.name.split(".").pop()!.toLowerCase()}` : "";
  if (!accept.includes(ext)) return `Unsupported file type "${ext || "none"}". Allowed: ${accept.join(", ")}.`;
  if (file.size === 0) return "The selected file is empty.";
  if (file.size > maxBytes) return `File is ${formatBytes(file.size)}; the limit is ${formatBytes(maxBytes)}.`;
  return null;
}

/** Drag-and-drop + keyboard-accessible file picker with client-side pre-validation. */
export function Dropzone({ accept, maxBytes, disabled, onFile }: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handle = (file: File | undefined) => {
    if (!file) return;
    const problem = validateFile(file, accept, maxBytes);
    setError(problem);
    if (!problem) onFile(file);
  };

  return (
    <div>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        aria-label={`Upload a log file. Drag and drop or press Enter to browse. Accepted: ${accept.join(", ")}, up to ${formatBytes(maxBytes)}.`}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (!disabled && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!disabled) handle(e.dataTransfer.files?.[0]);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors",
          dragging ? "border-teal-500 bg-teal-50" : "border-slate-300 bg-white hover:border-teal-400 hover:bg-slate-50",
          disabled && "cursor-not-allowed opacity-60",
        )}
        data-testid="dropzone"
      >
        <span className="rounded-full bg-teal-50 p-3 text-teal-700">
          {dragging ? <FileUp className="size-7" aria-hidden /> : <UploadCloud className="size-7" aria-hidden />}
        </span>
        <div>
          <p className="text-base font-medium text-navy-900">Drop a log file here, or click to browse</p>
          <p className="mt-1 text-sm text-slate-500">
            {accept.join(", ")} · up to {formatBytes(maxBytes)} · processed as untrusted text, never executed
          </p>
        </div>
      </div>
      <label className="sr-only" htmlFor="log-file-input">
        Log file
      </label>
      <input
        id="log-file-input"
        ref={inputRef}
        type="file"
        accept={accept.join(",")}
        className="sr-only"
        tabIndex={-1}
        onChange={(e) => {
          handle(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      {error && (
        <p role="alert" className="mt-2 text-sm font-medium text-red-700">
          {error}
        </p>
      )}
    </div>
  );
}
