const PRIVATE_ORIGIN = "http://frontend:3000";

function buildOriginRequest(request: Request): Request {
  const publicUrl = new URL(request.url);
  const originUrl = new URL(`${publicUrl.pathname}${publicUrl.search}`, PRIVATE_ORIGIN);
  const headers = new Headers(request.headers);

  headers.delete("host");
  headers.delete("connection");
  headers.set("x-forwarded-host", publicUrl.host);
  headers.set("x-forwarded-proto", "https");

  const init: RequestInit = {
    method: request.method,
    headers,
    redirect: "manual",
    signal: request.signal,
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
  }

  return new Request(originUrl, init);
}

function rewriteOriginLocation(headers: Headers, publicUrl: URL): void {
  const location = headers.get("location");
  if (!location) return;

  const resolved = new URL(location, PRIVATE_ORIGIN);
  if (resolved.origin !== PRIVATE_ORIGIN) return;

  headers.set(
    "location",
    `${publicUrl.origin}${resolved.pathname}${resolved.search}${resolved.hash}`,
  );
}

export default {
  async fetch(request, env): Promise<Response> {
    const publicUrl = new URL(request.url);

    try {
      const originResponse = await env.AGENTAI_VPC.fetch(buildOriginRequest(request));
      const headers = new Headers(originResponse.headers);

      rewriteOriginLocation(headers, publicUrl);
      headers.set("x-content-type-options", "nosniff");

      return new Response(originResponse.body, {
        status: originResponse.status,
        statusText: originResponse.statusText,
        headers,
      });
    } catch (error) {
      console.error(
        JSON.stringify({
          event: "agentai_origin_fetch_failed",
          path: publicUrl.pathname,
          error: error instanceof Error ? error.message : "Unknown origin error",
        }),
      );
      return new Response("Agent AI is temporarily unavailable.", { status: 502 });
    }
  },
} satisfies ExportedHandler<Env>;
