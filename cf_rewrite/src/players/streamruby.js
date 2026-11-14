/**
 * StreamRuby / RubySTM player resolver.
 */

import { edgeFetch, DEFAULT_UA } from "../utils/http.js";

export async function resolveStreamRuby(embedUrl, providerName = "ToonStream") {
  try {
    const res = await edgeFetch(embedUrl, {
      headers: { Referer: "https://tooniboy.xyz/" },
      ttl: 300
    });
    if (!res.ok) return null;
    const html = await res.text();

    const m3u8Match = html.match(/(https?:\/\/[^\s"']+\.m3u8[^\s"']*)/i) ||
                      html.match(/file:\s*["']([^"']+\.m3u8[^"']*)["']/i);
    if (!m3u8Match) return null;

    return {
      name: `${providerName} · StreamRuby [1080p]`,
      title: `RubySTM 1080p\nHindi · Multi Audio`,
      url: m3u8Match[1],
      quality: "1080p",
      provider: providerName,
      languages: ["Hindi", "English"],
      behaviorHints: {
        proxyHeaders: {
          request: {
            "User-Agent": DEFAULT_UA,
            "Referer": embedUrl
          }
        }
      }
    };
  } catch (e) {
    return null;
  }
}
