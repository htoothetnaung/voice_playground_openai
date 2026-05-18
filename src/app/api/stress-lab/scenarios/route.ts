import { NextResponse } from "next/server";
import { hasBackendProxyTarget, proxyToBackend } from "../../_lib/backendProxy";

export async function GET() {
  if (hasBackendProxyTarget()) {
    return await proxyToBackend("/api/v1/callcenter/stress-lab/scenarios", {
      method: "GET",
    });
  }

  return NextResponse.json({
    enabled: false,
    real_openai_tools_enabled: false,
    scenarios: [],
  });
}
