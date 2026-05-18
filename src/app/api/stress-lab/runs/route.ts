import { NextResponse } from "next/server";
import { hasBackendProxyTarget, proxyToBackend } from "../../_lib/backendProxy";

export async function POST(request: Request) {
  if (hasBackendProxyTarget()) {
    const body = await request.text();
    return await proxyToBackend("/api/v1/callcenter/stress-lab/runs", {
      method: "POST",
      body,
    });
  }

  return NextResponse.json(
    { error: "Backend proxy is not configured" },
    { status: 503 },
  );
}
