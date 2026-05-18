import { NextResponse } from "next/server";
import { hasBackendProxyTarget, proxyToBackend } from "../../../_lib/backendProxy";

export async function GET(
  _request: Request,
  { params }: { params: Promise<{ runId: string }> },
) {
  const { runId } = await params;

  if (hasBackendProxyTarget()) {
    return await proxyToBackend(
      `/api/v1/callcenter/stress-lab/runs/${encodeURIComponent(runId)}`,
      { method: "GET" },
    );
  }

  return NextResponse.json(
    { error: "Backend proxy is not configured" },
    { status: 404 },
  );
}
