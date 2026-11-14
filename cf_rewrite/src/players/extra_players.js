/**
 * Extra Player Resolvers: TurboVid, GDMirrorBot, UpnShare.
 */

import { edgeFetch, DEFAULT_UA } from "../utils/http.js";

export async function resolveTurboVid(embedUrl, providerName = "AniBox") {
  try {
    const res = await edgeFetch(embedUrl, { ttl: 300 });
    if (!res.ok) return null;
    const html = await res.text();
    const m = html.match(/file:\s*["']([^"']+\.m3u8[^"']*)["']/i) || html.match(/(https?:\/\/[^\s"']+\.m3u8[^\s"']*)/i);
    if (!m) return null;

    return {
      name: `${providerName} · TurboVid [1080p]`,
      title: `TurboVid 1080p\nHindi · Multi Audio`,
      url: m[1],
      quality: "1080p",
      provider: providerName,
      languages: ["Hindi", "English"],
      behaviorHints: { proxyHeaders: { request: { "User-Agent": DEFAULT_UA, "Referer": embedUrl } } }
    };
  } catch (e) {
    return null;
  }
}

export async function resolveUpnShare(embedUrl, providerName = "AniBox") {
  try {
    const res = await edgeFetch(embedUrl, { ttl: 300 });
    if (!res.ok) return null;
    const html = await res.text();
    const m = html.match(/(https?:\/\/[^\s"']+\.m3u8[^\s"']*)/i);
    if (!m) return null;

    return {
      name: `${providerName} · UpnShare [720p]`,
      title: `UpnShare 720p\nHindi · Multi Audio`,
      url: m[1],
      quality: "720p",
      provider: providerName,
      languages: ["Hindi", "English"],
      behaviorHints: { proxyHeaders: { request: { "User-Agent": DEFAULT_UA, "Referer": embedUrl } } }
    };
  } catch (e) {
    return null;
  }
}
