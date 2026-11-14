/**
 * Direct TMDB & IMDb Resolvers - O(1) Stream Fast-Track.
 * Directly queries ModiPlay / ROGL and its multiple servers without web scraping.
 */

import { edgeFetch, DEFAULT_UA } from "../utils/http.js";

export async function resolveDirectTmdbStreams(idOrImdb, isMovie = false, season = 1, episode = 1) {
  if (!idOrImdb) return [];

  const strId = String(idOrImdb).trim();
  let embedUrl = "";

  if (strId.startsWith("tt")) {
    embedUrl = isMovie
      ? `https://rozgarlelo.modiplay.xyz/embed/imdb/movie?id=${strId}`
      : `https://rozgarlelo.modiplay.xyz/embed/imdb/tv?id=${strId}&s=${season}&e=${episode}`;
  } else if (!isNaN(strId)) {
    embedUrl = isMovie
      ? `https://rozgarlelo.modiplay.xyz/embed/tmdb/movie?id=${strId}`
      : `https://rozgarlelo.modiplay.xyz/embed/tmdb/tv?id=${strId}&s=${season}&e=${episode}`;
  } else {
    return [];
  }

  try {
    const res = await edgeFetch(embedUrl, { ttl: 300 });
    if (!res.ok) return [];
    const html = await res.text();

    const srvMatches = [
      ...html.matchAll(/class="srv-item[^"]*"[\s\S]*?data-platform="([^"]+)"[\s\S]*?data-pname="([^"]+)"[\s\S]*?data-code="([^"]+)"/gi)
    ];

    // If no server chips found in dropdown, check for default iframe
    if (srvMatches.length === 0) {
      const ifm = html.match(/<iframe[^>]+src="([^"]+)"/i);
      if (!ifm) return [];
      srvMatches.push([null, "streamhg", "StreamHG", ifm[1]]);
    }

    const tasks = srvMatches.map(async (m) => {
      const platform = m[1];
      const pname = m[2] || "Server";
      const code = m[3];
      const proxyUrl = `https://rozgarlelo.modiplay.xyz/proxy.php?p=${encodeURIComponent(platform)}&c=${encodeURIComponent(code)}&noredirect=1`;

      try {
        const pRes = await edgeFetch(proxyUrl, {
          headers: { "Referer": embedUrl, "User-Agent": DEFAULT_UA },
          ttl: 0,
        });
        if (!pRes.ok) return null;
        const pHtml = await pRes.text();
        const srcMatch = pHtml.match(/var\s+src\s*=\s*"([^"]+)"/i);
        if (!srcMatch) return null;

        const finalSrc = new URL(srcMatch[1].replace(/\\\//g, "/"), proxyUrl).toString();

        // Pre-validate ModiPlay stream with timeout
        const testRes = await fetch(finalSrc, {
          headers: { "Referer": proxyUrl, "User-Agent": DEFAULT_UA },
          signal: AbortSignal.timeout(1800),
        });
        if (!testRes.ok) return null;
        const testText = await testRes.text();
        if (testText.includes("EXT-X-ERROR") || !testText.includes("#EXTM3U")) return null;

        return {
          name: `MultiMovies · ROGL ${pname} [720p]`,
          title: `ROGL ${pname} 720p\nHindi · Multi Audio`,
          url: finalSrc,
          proxyUrl: proxyUrl,
          isModiplay: true,
          quality: "720p",
          provider: "MultiMovies",
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
      } catch (e) {
        return null;
      }
    });

    const results = await Promise.all(tasks);
    return results.filter(Boolean);
  } catch (e) {
    return [];
  }
}
