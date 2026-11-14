import { DEFAULT_UA, corsHeaders } from "../utils/http.js";

export async function handleStreamProxy(request) {
  const reqUrl = new URL(request.url);
  const targetUrl = reqUrl.searchParams.get("url");
  const referer = reqUrl.searchParams.get("ref") || "";

  if (!targetUrl) {
    return new Response("Missing target url parameter", { status: 400, headers: corsHeaders() });
  }

  const clientRange = request.headers.get("range");
  const clientUa = request.headers.get("user-agent") || DEFAULT_UA;

  const upstreamHeaders = {
    "User-Agent": clientUa,
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "video",
    "Sec-Fetch-Mode": "no-cors",
    "Sec-Fetch-Site": "cross-site",
  };
  if (referer) {
    upstreamHeaders["Referer"] = referer;
  }
  if (clientRange) {
    upstreamHeaders["Range"] = clientRange;
  }

  try {
    let currentUrl = targetUrl;
    let response;
    let redirects = 0;

    while (redirects < 5) {
      response = await fetch(currentUrl, {
        method: request.method === "HEAD" ? "HEAD" : "GET",
        headers: upstreamHeaders,
        redirect: "manual",
      });

      if ([301, 302, 303, 307, 308].includes(response.status) && response.headers.get("location")) {
        const loc = response.headers.get("location");
        currentUrl = new URL(loc, currentUrl).toString();
        redirects++;
        continue;
      }
      break;
    }

    if (!response.ok && response.status !== 206) {
      const errBody = await response.text().catch(() => "");
      return new Response(`Upstream returned ${response.status} ${response.statusText} from ${currentUrl}\n${errBody}`, {
        status: response.status,
        headers: corsHeaders({ "Content-Type": "text/plain" }),
      });
    }

    const resHeaders = new Headers();
    for (const [k, v] of response.headers.entries()) {
      const lk = k.toLowerCase();
      if ([
        "content-type",
        "content-length",
        "content-range",
        "accept-ranges",
        "etag",
        "last-modified"
      ].includes(lk)) {
        resHeaders.set(k, v);
      }
    }

    resHeaders.set("Access-Control-Allow-Origin", "*");
    resHeaders.set("Access-Control-Allow-Headers", "*");
    resHeaders.set("Access-Control-Allow-Methods", "GET, HEAD, OPTIONS");
    resHeaders.set("Cache-Control", "public, max-age=14400");

    return new Response(request.method === "HEAD" ? null : response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: resHeaders,
    });
  } catch (err) {
    return new Response(`Stream proxy error: ${err.message}`, {
      status: 502,
      headers: corsHeaders(),
    });
  }
}
