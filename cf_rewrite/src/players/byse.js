/**
 * Byse Player resolver (bysetayico.com / bysezejataos.com / bysevepoin.com).
 * Extracts direct HLS playlist with streamruby Referer.
 */

import { edgeFetch, DEFAULT_UA } from "../utils/http.js";

export async function resolveByse(embedUrl, providerName = "MultiMovies") {
  try {
    const res = await edgeFetch(embedUrl, {
      headers: { Referer: "https://m1.multimovies.courses/" },
      ttl: 300,
    });
    if (!res.ok) return null;
    const html = await res.text();

    const fileMatch = html.match(/file:\s*["']([^"']+\.m3u8[^"']*)["']/i) ||
                      html.match(/source:\s*["']([^"']+\.m3u8[^"']*)["']/i) ||
                      html.match(/(https?:\/\/[^\s"']+\.m3u8[^\s"']*)/i);
    if (!fileMatch) return null;

    const m3u8Url = fileMatch[1];
    return {
      name: `${providerName} · Byse [1080p]`,
      title: `Byse HLS 1080p\nHindi · Multi Audio`,
      url: m3u8Url,
      quality: "1080p",
      provider: providerName,
      languages: ["Hindi", "English"],
      behaviorHints: {
        proxyHeaders: {
          request: {
            "User-Agent": DEFAULT_UA,
            "Referer": "https://streamruby.net/",
          },
        },
      },
    };
  } catch (e) {
    return null;
  }
}
