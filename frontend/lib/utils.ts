/** Small formatting helpers. */

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function confidenceBadgeClass(confidence: number | null): string {
  if (confidence === null) return "bg-stone-200 text-stone-700";
  if (confidence >= 0.85) return "bg-green-100 text-green-800";
  if (confidence >= 0.6) return "bg-amber-100 text-amber-900";
  return "bg-red-100 text-red-800";
}

export function formatConfidence(confidence: number | null): string {
  if (confidence === null) return "—";
  return `${Math.round(confidence * 100)}%`;
}

/** Rough client-side row estimate for the upload info card (CSV only). */
export async function estimateCsvRowCount(file: File): Promise<number | null> {
  const name = file.name.toLowerCase();
  if (!name.endsWith(".csv")) return null;
  const text = await file.text();
  const lines = text.split(/\r?\n/).filter((line) => line.trim().length > 0);
  // Subtract header row when present.
  return Math.max(0, lines.length - 1);
}
