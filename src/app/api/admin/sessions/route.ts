import { NextResponse } from "next/server";
import { hasBackendProxyTarget, proxyToBackend } from "../../_lib/backendProxy";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const limit = url.searchParams.get("limit") ?? "25";

  if (hasBackendProxyTarget()) {
    return await proxyToBackend(`/api/v1/callcenter/admin/sessions?limit=${limit}`, {
      method: "GET",
    });
  }

  return NextResponse.json({ sessions: [] });
}
