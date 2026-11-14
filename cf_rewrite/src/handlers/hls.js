import { corsHeaders } from "../utils/http.js";

// Safe Base64URL encoder/decoder for edge workers
function b64urlEncode(str) {
  return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function b64urlDecode(str) {
  let padded = str + "=".repeat((4 - (str.length % 4)) % 4);
  return atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
}

export async function handleHlsManifest(request) {
  const reqUrl = new URL(request.url);
  const targetUrl = reqUrl.searchParams.get("url");
  const ref = reqUrl.searchParams.get("ref") || "";

  if (!targetUrl) {
    return new Response("Missing url param", { status: 400 });
  }

  const upstreamHeaders = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
  };
  if (ref) upstreamHeaders["Referer"] = ref;

  const res = await fetch(targetUrl, { headers: upstreamHeaders });
  if (!res.ok) {
    return new Response(`Upstream manifest failed: ${res.status}`, { status: res.status });
  }

  const text = await res.text();
  const workerOrigin = reqUrl.origin;

  // Transform lines in manifest
  const lines = text.split("\n");
  const newLines = lines.map((line) => {
    const trimmed = line.trim();
    if (!trimmed) return line;

    // Check for URI="..." attribute inside tags (e.g. #EXT-X-MEDIA)
    if (trimmed.startsWith("#")) {
      return line.replace(/URI="([^"]+)"/g, (match, uri) => {
        let absoluteUri = uri;
        if (uri.startsWith("/")) {
          const u = new URL(uri, targetUrl);
          // If this is a stream_proxy pointing to an m3u8 playlist:
          const innerUrl = u.searchParams.get("url");
          if (innerUrl && innerUrl.includes(".m3u8")) {
            absoluteUri = `${workerOrigin}/hls/manifest?url=${encodeURIComponent(u.toString())}&ref=${encodeURIComponent(ref)}`;
          } else {
            absoluteUri = u.toString();
          }
        }
        return `URI="${absoluteUri}"`;
      });
    }

    // This is a media URI line (either child playlist or segment)
    let fullUri = trimmed;
    if (trimmed.startsWith("/")) {
      fullUri = new URL(trimmed, targetUrl).toString();
    }

    // If it's a child playlist (contains .m3u8)
    if (fullUri.includes(".m3u8")) {
      return `${workerOrigin}/hls/manifest?url=${encodeURIComponent(fullUri)}&ref=${encodeURIComponent(ref)}`;
    }

    // If it's a stream_proxy segment pointing to TikTok / CDN image
    try {
      const u = new URL(fullUri);
      const rawChunkUrl = u.searchParams.get("url");
      if (rawChunkUrl) {
        // Route through our high-performance Edge segment proxy with .ts extension
        const encoded = b64urlEncode(rawChunkUrl);
        return `${workerOrigin}/hls/seg/${encoded}.ts`;
      }
    } catch (e) {}

    // Fallback: keep full absolute URI
    return fullUri;
  });

  return new Response(newLines.join("\n"), {
    headers: corsHeaders({
      "Content-Type": "application/vnd.apple.mpegurl",
      "Cache-Control": "public, max-age=300",
    }),
  });
}

export async function handleHlsSegment(request, segToken) {
  if (!segToken) return new Response("Missing segment token", { status: 400 });

  let rawUrl = "";
  try {
    const cleanToken = segToken.replace(/\.ts$/i, "");
    rawUrl = b64urlDecode(cleanToken);
  } catch (e) {
    return new Response("Invalid segment token", { status: 400 });
  }

  // Fetch from TikTok / upstream CDN using Range: bytes=70- to strip image header at zero cost
  const upstreamRes = await fetch(rawUrl, {
    headers: {
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
      "Range": "bytes=70-",
    },
  });

  if (!upstreamRes.ok && upstreamRes.status !== 206) {
    // If Range header wasn't accepted, fetch normally and slice
    const fullRes = await fetch(rawUrl);
    if (!fullRes.ok) return new Response("Segment fetch failed", { status: fullRes.status });
    const buf = await fullRes.arrayBuffer();
    const isPng = new Uint8Array(buf.slice(0, 4))[0] === 0x89;
    const body = isPng ? buf.slice(70) : buf;
    return new Response(body, {
      headers: corsHeaders({
        "Content-Type": "video/mp2t",
        "Cache-Control": "public, max-age=604800, s-maxage=604800, immutable",
      }),
    });
  }

  // Stream directly from Edge
  return new Response(upstreamRes.body, {
    status: 200,
    headers: corsHeaders({
      "Content-Type": "video/mp2t",
      "Cache-Control": "public, max-age=604800, s-maxage=604800, immutable",
    }),
  });
}
