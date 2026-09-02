'use client';

/** REST helpers — all requests go through the gateway with XTransformPort. */

export const BRIDGE_PORT = 8010;

export function apiUrl(path: string): string {
  return `${path}${path.includes('?') ? '&' : '?'}XTransformPort=${BRIDGE_PORT}`;
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(apiUrl(path), init);
  if (!res.ok) {
    throw new Error(`${path}: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  return fetchJson<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}
