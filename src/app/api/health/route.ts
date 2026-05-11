import { NextResponse } from "next/server";
import { hasBackendProxyTarget, proxyToBackend } from "../_lib/backendProxy";

export async function GET() {
  if (hasBackendProxyTarget()) {
    return await proxyToBackend("/api/health", {
      method: "GET",
    });
  }

  const status: Record<string, unknown> = {
    ok: true,
    timestamp: new Date().toISOString(),
    uptime: process.uptime(),
  };

  return NextResponse.json(status);
}


