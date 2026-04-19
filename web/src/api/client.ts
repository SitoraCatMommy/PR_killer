import { getApiBaseUrl } from '../config';

function joinUrl(path: string): string {
  const base = getApiBaseUrl();
  const p = path.startsWith('/') ? path : `/${path}`;
  return `${base}${p}`;
}

export function formatApiDetail(detail: unknown): string {
  if (typeof detail === 'string') return detail;
  if (
    detail &&
    typeof detail === 'object' &&
    'message' in detail &&
    typeof (detail as { message: unknown }).message === 'string'
  ) {
    return (detail as { message: string }).message;
  }
  try {
    return JSON.stringify(detail);
  } catch {
    return 'Request failed';
  }
}

export class ApiError extends Error {
  readonly name = 'ApiError';
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(formatApiDetail(detail));
    this.status = status;
    this.detail = detail;
  }
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    ...(init?.headers as Record<string, string> | undefined),
  };
  const body = init?.body;
  if (body != null && !(body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }
  const res = await fetch(joinUrl(path), { ...init, headers });
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const j: unknown = await res.json();
      if (j && typeof j === 'object' && 'detail' in j) {
        detail = (j as { detail: unknown }).detail;
      } else {
        detail = j;
      }
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get('content-type');
  if (!ct?.includes('application/json')) return undefined as T;
  return res.json() as Promise<T>;
}

export function buildQuery(
  params: Record<string, string | number | boolean | undefined | null>,
): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue;
    if (typeof v === 'boolean') {
      if (!v) continue;
      sp.set(k, 'true');
      continue;
    }
    sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}
