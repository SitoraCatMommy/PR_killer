/** Base URL including `/api/v1` (see `.env.example`). */
export function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL as string | undefined;
  if (!raw?.trim()) {
    throw new Error(
      'VITE_API_BASE_URL is missing. Copy web/.env.example to web/.env.development or set the variable.',
    );
  }
  return raw.replace(/\/$/, '');
}
