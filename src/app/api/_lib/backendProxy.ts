import { NextResponse } from "next/server";

const DEFAULT_TIMEOUT_MS = 90_000;

function getBackendBaseUrl(): string | null {
  const raw = process.env.FRONTEND_BACKEND_BASE_URL?.trim();
  if (!raw) return null;
  return raw.replace(/\/+$/, "");
}

export function hasBackendProxyTarget(): boolean {
  return Boolean(getBackendBaseUrl());
}

export async function proxyToBackend(
  path: string,
  init: RequestInit = {},
): Promise<NextResponse> {
  const baseUrl = getBackendBaseUrl();
  if (!baseUrl) {
    throw new Error("FRONTEND_BACKEND_BASE_URL is not configured");
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);

  try {
    const response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
      },
      cache: "no-store",
      signal: controller.signal,
    });

    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") ?? "application/json",
      },
    });
  } finally {
    clearTimeout(timeout);
  }
}
