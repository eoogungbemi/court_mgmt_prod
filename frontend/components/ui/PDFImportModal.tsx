"use client";

import { useRef, useState } from "react";
import { FileUp, X, AlertTriangle, CheckCircle2, PlusCircle, Loader2 } from "lucide-react";
import { pdfImport } from "@/lib/api";
import type {
  PDFHearingPreviewRow,
  PDFImportPreviewResponse,
  PDFImportResult,
} from "@/lib/types";
import Button from "@/components/ui/Button";

type Step = "upload" | "preview" | "done";

const STATUS_STYLES: Record<string, string> = {
  matched:  "bg-green-50  text-green-700  border-green-200",
  new_case: "bg-amber-50  text-amber-700  border-amber-200",
  error:    "bg-red-50    text-red-700    border-red-200",
};

const STATUS_LABEL: Record<string, string> = {
  matched:  "Existing case",
  new_case: "New case",
  error:    "Error",
};

function StatusPill({ status }: { status: string }) {
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${STATUS_STYLES[status] ?? ""}`}>
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

// ── Upload step ───────────────────────────────────────────────────────────────

function UploadStep({
  onParsed,
  onClose,
}: {
  onParsed: (data: PDFImportPreviewResponse) => void;
  onClose: () => void;
}) {
  const inputRef              = useRef<HTMLInputElement>(null);
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");
  const [dragging, setDragging] = useState(false);

  async function handleFile(file: File) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setError("Please select a PDF file.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const data = await pdfImport.preview(file) as PDFImportPreviewResponse;
      onParsed(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to process PDF");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="text-sm text-gray-600">
        Upload an Allegheny County court calendar PDF. The system will extract
        hearings and match them against existing cases.
      </p>

      <div
        className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-10 transition-colors cursor-pointer
          ${dragging ? "border-court-navy bg-blue-50" : "border-gray-300 hover:border-court-navy"}`}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const file = e.dataTransfer.files[0];
          if (file) handleFile(file);
        }}
      >
        {loading ? (
          <>
            <Loader2 className="h-10 w-10 animate-spin text-court-navy mb-3" />
            <p className="text-sm text-gray-500">Extracting hearing data with AI…</p>
          </>
        ) : (
          <>
            <FileUp className="h-10 w-10 text-gray-400 mb-3" />
            <p className="text-sm font-medium text-gray-700">Drop PDF here or click to browse</p>
            <p className="text-xs text-gray-400 mt-1">Allegheny County CPCMS 3940 format</p>
          </>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
      />

      {error && (
        <p className="flex items-center gap-2 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          {error}
        </p>
      )}

      <div className="flex justify-end">
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
      </div>
    </div>
  );
}

// ── Preview step ──────────────────────────────────────────────────────────────

function PreviewStep({
  preview,
  onConfirmed,
  onBack,
}: {
  preview: PDFImportPreviewResponse;
  onConfirmed: (result: PDFImportResult) => void;
  onBack: () => void;
}) {
  const [rows, setRows]       = useState<PDFHearingPreviewRow[]>(
    preview.rows.map((r) => ({ ...r, include: r.match_status !== "error" }))
  );
  const [complexity, setComplexity] = useState("medium");
  const [loading, setLoading] = useState(false);
  const [error,   setError]   = useState("");

  function toggle(idx: number) {
    setRows((prev) => prev.map((r, i) => i === idx ? { ...r, include: !r.include } : r));
  }

  function toggleAll(val: boolean) {
    setRows((prev) => prev.map((r) => r.match_status === "error" ? r : { ...r, include: val }));
  }

  const selectable = rows.filter((r) => r.match_status !== "error");
  const allSelected = selectable.every((r) => r.include);

  async function submit() {
    setError("");
    setLoading(true);
    try {
      const result = await pdfImport.confirm({ rows, default_complexity: complexity }) as PDFImportResult;
      onConfirmed(result);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Import failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex flex-wrap gap-3 text-sm">
        <span className="text-gray-500">
          <strong className="text-gray-900">{preview.total_rows}</strong> hearings on{" "}
          <strong className="text-gray-900">{preview.hearing_date}</strong>
          {preview.judge_name && ` · ${preview.judge_name}`}
        </span>
        <span className="text-green-700">{preview.matched} matched</span>
        <span className="text-amber-700">{preview.new_cases} new cases</span>
        {preview.errors > 0 && (
          <span className="text-red-700">{preview.errors} errors</span>
        )}
      </div>

      {/* Complexity selector for new cases */}
      {preview.new_cases > 0 && (
        <div className="flex items-center gap-2 text-sm">
          <label className="text-gray-600 shrink-0">Default complexity for new cases:</label>
          <select
            className="rounded border border-gray-300 px-2 py-1 text-sm"
            value={complexity}
            onChange={(e) => setComplexity(e.target.value)}
          >
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
        </div>
      )}

      {/* Table */}
      <div className="max-h-80 overflow-y-auto rounded-lg border border-gray-200">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-gray-50">
            <tr className="border-b border-gray-200 text-left text-gray-500">
              <th className="px-3 py-2">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={(e) => toggleAll(e.target.checked)}
                />
              </th>
              <th className="px-3 py-2">Time</th>
              <th className="px-3 py-2">Participant</th>
              <th className="px-3 py-2">Docket</th>
              <th className="px-3 py-2">Hearing type</th>
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, idx) => (
              <tr
                key={row.row_index}
                className={`border-b border-gray-100 ${row.match_status === "error" ? "opacity-50" : ""}`}
              >
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={row.include}
                    disabled={row.match_status === "error"}
                    onChange={() => toggle(idx)}
                  />
                </td>
                <td className="px-3 py-2 font-mono">{row.time}</td>
                <td className="px-3 py-2 font-medium">{row.participant}</td>
                <td className="px-3 py-2 font-mono text-gray-500">{row.docket_number}</td>
                <td className="px-3 py-2 capitalize">{row.hearing_type.replace(/_/g, " ")}</td>
                <td className="px-3 py-2">
                  <StatusPill status={row.match_status} />
                  {row.issues.length > 0 && (
                    <p className="mt-0.5 text-red-600">{row.issues.join("; ")}</p>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {error && (
        <p className="flex items-center gap-2 rounded bg-red-50 px-3 py-2 text-sm text-red-700">
          <AlertTriangle className="h-4 w-4 flex-shrink-0" />
          {error}
        </p>
      )}

      <div className="flex justify-between">
        <Button variant="secondary" onClick={onBack}>Back</Button>
        <Button
          onClick={submit}
          loading={loading}
          disabled={rows.every((r) => !r.include)}
        >
          Import {rows.filter((r) => r.include).length} hearing{rows.filter((r) => r.include).length !== 1 ? "s" : ""}
        </Button>
      </div>
    </div>
  );
}

// ── Done step ─────────────────────────────────────────────────────────────────

function DoneStep({
  result,
  onClose,
}: {
  result: PDFImportResult;
  onClose: () => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 rounded-lg bg-green-50 px-4 py-3">
        <CheckCircle2 className="h-6 w-6 text-green-600 shrink-0" />
        <div>
          <p className="font-semibold text-green-800">Import complete</p>
          <p className="text-sm text-green-700">
            {result.hearings_created} hearing{result.hearings_created !== 1 ? "s" : ""} added
            {result.cases_created > 0 && `, ${result.cases_created} new case${result.cases_created !== 1 ? "s" : ""} created`}
            {result.skipped > 0 && `, ${result.skipped} skipped`}
          </p>
        </div>
      </div>

      {result.errors.length > 0 && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3">
          <p className="mb-1 text-sm font-semibold text-red-800">Errors</p>
          <ul className="list-disc pl-4 text-xs text-red-700 space-y-0.5">
            {result.errors.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
        </div>
      )}

      {result.cases_created > 0 && (
        <p className="flex items-start gap-2 text-xs text-amber-700 bg-amber-50 rounded px-3 py-2">
          <PlusCircle className="h-3.5 w-3.5 mt-0.5 shrink-0" />
          New cases were created without a defense attorney assigned. A clerk should update
          the attorney on each new case via the Cases page.
        </p>
      )}

      <div className="flex justify-end">
        <Button onClick={onClose}>Done</Button>
      </div>
    </div>
  );
}

// ── Modal shell ───────────────────────────────────────────────────────────────

export default function PDFImportModal({ onClose, onImported }: {
  onClose: () => void;
  onImported?: () => void;
}) {
  const [step,    setStep]    = useState<Step>("upload");
  const [preview, setPreview] = useState<PDFImportPreviewResponse | null>(null);
  const [result,  setResult]  = useState<PDFImportResult | null>(null);

  const TITLES: Record<Step, string> = {
    upload:  "Import from PDF docket",
    preview: "Review extracted hearings",
    done:    "Import complete",
  };

  function handleConfirmed(res: PDFImportResult) {
    setResult(res);
    setStep("done");
    onImported?.();
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-2xl rounded-lg bg-white shadow-xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-gray-200 px-6 py-4">
          <h2 className="text-lg font-semibold text-court-navy">{TITLES[step]}</h2>
          <button onClick={onClose} className="rounded p-1 hover:bg-gray-100">
            <X className="h-5 w-5 text-gray-500" />
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-5">
          {step === "upload" && (
            <UploadStep
              onParsed={(data) => { setPreview(data); setStep("preview"); }}
              onClose={onClose}
            />
          )}
          {step === "preview" && preview && (
            <PreviewStep
              preview={preview}
              onConfirmed={handleConfirmed}
              onBack={() => setStep("upload")}
            />
          )}
          {step === "done" && result && (
            <DoneStep result={result} onClose={onClose} />
          )}
        </div>
      </div>
    </div>
  );
}
