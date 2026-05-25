/** Mirrors backend defaults (`UPLOAD_MAX_BYTES`, bulk file cap). */
export const UPLOAD_MAX_BYTES = 100 * 1024 * 1024;
export const BULK_UPLOAD_MAX_FILES = 100;

export const DOCUMENT_UPLOAD_ACCEPT =
  '.txt,.md,.markdown,.docx,text/plain,text/markdown,application/vnd.openxmlformats-officedocument.wordprocessingml.document';

export const MIXED_UPLOAD_ACCEPT = `${DOCUMENT_UPLOAD_ACCEPT},audio/*`;

export type UploadFileFilterResult = {
  files: File[];
  skippedTooLarge: number;
  skippedOverCap: number;
};

export function filterBulkUploadFiles(
  incoming: File[],
  opts?: { maxFiles?: number; maxBytes?: number },
): UploadFileFilterResult {
  const maxFiles = opts?.maxFiles ?? BULK_UPLOAD_MAX_FILES;
  const maxBytes = opts?.maxBytes ?? UPLOAD_MAX_BYTES;
  const withinSize = incoming.filter((f) => f.size <= maxBytes);
  const skippedTooLarge = incoming.length - withinSize.length;
  const capped = withinSize.slice(0, maxFiles);
  const skippedOverCap = Math.max(0, withinSize.length - capped.length);
  return { files: capped, skippedTooLarge, skippedOverCap };
}
