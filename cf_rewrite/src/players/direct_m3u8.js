/**
 * Direct M3U8, ModiPlay & Cloudflare worker bridge resolvers.
 */

import { edgeFetch, DEFAULT_UA } from "../utils/http.js";

export async function resolveModiplay(embedUrl, providerName = "MultiMovies") {
  try {
    const r1 = await edgeFetch(embedUrl, { ttl: 0 });
    if (!r1.ok) return null;
    const html1 = await r1.text();
    const ifm = html1.match(/<iframe[^>]+src="([^"]+)"/i);
    if (!ifm) return null;

    const rawProxy = ifm[1].replace(/&amp;/g, "&");
    const proxyUrl = new URL(rawProxy, embedUrl).toString();

    const r2 = await edgeFetch(proxyUrl, { headers: { Referer: embedUrl }, ttl: 0 });
    if (!r2.ok) return null;
    const html2 = await r2.text();

    const srcMatch = html2.match(/var\s+src\s*=\s*"([^"]+)"/i);
    if (srcMatch) {
      const finalSrc = new URL(srcMatch[1].replace(/\\\//g, "/"), proxyUrl).toString();

      // Pre-validate ModiPlay stream: check for live 200 OK and ensure no #EXT-X-ERROR in playlist
      try {
        const testRes = await fetch(finalSrc, {
          headers: { "Referer": proxyUrl, "User-Agent": DEFAULT_UA },
          signal: AbortSignal.timeout(2000),
        });
        if (!testRes.ok) return null;
        const testText = await testRes.text();
        if (testText.includes("EXT-X-ERROR") || !testText.includes("#EXTM3U")) return null;
      } catch (e) {
        return null;
      }

      return {
        name: `${providerName} · ModiPlay [720p]`,
        title: `ModiPlay 720p\nHindi · Multi Audio`,
        url: finalSrc,
        proxyUrl: proxyUrl,
        isModiplay: true,
        quality: "720p",
        provider: providerName,
        languages: ["Hindi", "English"],
        behaviorHints: {
          proxyHeaders: {
            request: {
              "User-Agent": DEFAULT_UA,
              "Referer": proxyUrl,
            },
          },
        },
      };
    }
  } catch (e) {
    return null;
  }
  return null;
}

export async function resolveDirectEmbed(embedUrl, providerName = "Direct") {
  if (!embedUrl || embedUrl.includes("vidmmo.com") || embedUrl.includes("vidout.pages.dev")) {
    return null;
  }
  try {
    const r = await edgeFetch(embedUrl, { ttl: 300 });
    if (!r.ok) return null;
    const html = await r.text();
    const m3u8Match = html.match(/https?:\/\/[^\s"'<>\\]+\.m3u8[^\s"'<>\\]*/);
    if (!m3u8Match) return null;

    const origin = new URL(embedUrl).origin + "/";
    const m3u8Url = m3u8Match[0];
    if (m3u8Url.includes("vidmmo.com") || m3u8Url.includes("vidout.pages.dev")) {
      return null;
    }

    // Pre-validate stream URL so dead DNS / 404 links (e.g. vidmmo) are never emitted
    try {
      const testRes = await fetch(m3u8Url, {
        method: "HEAD",
        headers: { "Referer": origin, "User-Agent": DEFAULT_UA },
        signal: AbortSignal.timeout(1800),
      });
      if (testRes.status !== 200 && testRes.status !== 206) return null;
    } catch (e) {
      return null;
    }

    return {
      name: `${providerName} · Direct HLS [1080p]`,
      title: `${providerName} 1080p\nHindi · Multi Audio`,
      url: m3u8Url,
      quality: "1080p",
      provider: providerName,
      languages: ["Hindi", "English"],
      behaviorHints: {
        proxyHeaders: {
          request: {
            "User-Agent": DEFAULT_UA,
            "Referer": origin,
          },
        },
      },
    };
  } catch (e) {
    return null;
  }
}
