/**
 * Abyss Player (abyssplayer.com / playhydrax.com / sssrr.org) resolver.
 * Decrypts stream sources via enc-dec.app API and attaches proxyHeaders.
 */

import { edgeFetch, DEFAULT_UA } from "../utils/http.js";

export async function resolveAbyss(embedUrl, providerName = "ToonStream") {
  const streams = [];
  try {
    const res = await edgeFetch(embedUrl, {
      headers: {
        "User-Agent": DEFAULT_UA,
        "Referer": "https://playhydrax.com/",
      },
      ttl: 600,
    });
    if (!res.ok) return [];
    const html = await res.text();

    // 1. Direct HLS in page
    const m3u8Match = html.match(/(https?:\/\/[^\s"']+\.m3u8[^\s"']*)/i);
    if (m3u8Match) {
      return [{
        name: `${providerName} · Abyss [1080p]`,
        title: `Abyss Direct HLS 1080p\nHindi · Multi Audio`,
        url: m3u8Match[1],
        quality: "1080p",
        provider: providerName,
        isAbyss: true,
        languages: ["Hindi", "English"],
        behaviorHints: { proxyHeaders: { request: { "User-Agent": DEFAULT_UA, "Referer": "https://abyssplayer.com/" } } },
      }];
    }

    // 2. Decrypt datas
    const datasMatch = html.match(/const\s+datas\s*=\s*["']([^"']+)["']/i);
    if (datasMatch) {
      const decRes = await edgeFetch("https://enc-dec.app/api/dec-abyss", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Referer": "https://playhydrax.com/",
        },
        body: JSON.stringify({ text: datasMatch[1] }),
        ttl: 600,
      });

      if (decRes.ok) {
        const json = await decRes.json();
        const sources = (json.result && json.result.sources) || [];
        const candidates = [];
        for (const item of sources) {
          if (item.status === false) continue; // Skip unrendered / unplayable formats
          const q = item.type || item.quality || "720p";
          const fileUrl = item.url || item.file;
          if (fileUrl && fileUrl.startsWith("http")) {
            candidates.push({ item, q, fileUrl });
          }
        }

        // Parallel HEAD pre-validation to eliminate 404 dead CDN entries
        const verifiedCandidates = await Promise.all(
          candidates.map(async (c) => {
            try {
              const headRes = await fetch(c.fileUrl, {
                method: "HEAD",
                headers: { "Referer": "https://abyssplayer.com/", "User-Agent": DEFAULT_UA },
                signal: AbortSignal.timeout(1800),
              });
              if (headRes.status === 200 || headRes.status === 206) {
                return c;
              }
              return null;
            } catch (e) {
              return null; // Skip unreachable or timed out streams
            }
          })
        );

        for (const c of verifiedCandidates) {
          if (!c) continue;
          streams.push({
            name: `${providerName} · Abyss [${c.q}]`,
            title: `Abyss ${c.q}\nHindi · Multi Audio`,
            url: c.fileUrl,
            quality: c.q,
            size: c.item.size || 0,
            provider: providerName,
            isAbyss: true,
            languages: ["Hindi", "English"],
            behaviorHints: {
              notWebReady: false,
              proxyHeaders: {
                request: {
                  "User-Agent": DEFAULT_UA,
                  "Referer": "https://abyssplayer.com/",
                },
              },
            },
          });
        }
      }
    }
  } catch (e) {
    console.error("Abyss resolve error:", e);
  }
  return streams;
}
