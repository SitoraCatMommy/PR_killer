/**
 * API base including `/api/v1`.
 * In dev, prefer a relative URL (`/api/v1`) so Vite proxies to the backend and CORS is not required.
 */
export function getApiBaseUrl(): string {
  const raw = import.meta.env.VITE_API_BASE_URL as string | undefined;
  const trimmed = raw?.trim();
  if (trimmed) return trimmed.replace(/\/$/, '');
  if (import.meta.env.DEV) return '/api/v1';
  throw new Error(
    'VITE_API_BASE_URL is missing. Copy web/.env.example to web/.env.development or set the variable for production builds.',
  );
}
