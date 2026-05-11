import { NextResponse } from "next/server";
import { hasBackendProxyTarget, proxyToBackend } from "../../../_lib/backendProxy";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await params;

  if (hasBackendProxyTarget()) {
    return await proxyToBackend(
      `/api/v1/callcenter/admin/sessions/${encodeURIComponent(sessionId)}`,
      { method: "GET" },
    );
  }

  return NextResponse.json({ error: "Backend proxy is not configured" }, { status: 404 });
}
