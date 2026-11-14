import { edgeFetch, DEFAULT_UA } from "../src/utils/http.js";

async function testExtractAllServers(id, isMovie = true) {
  const embedUrl = isMovie
    ? `https://rozgarlelo.modiplay.xyz/embed/tmdb/movie?id=${id}`
    : `https://rozgarlelo.modiplay.xyz/embed/tmdb/tv?id=${id}&s=1&e=1`;

  const start = Date.now();
  const res = await edgeFetch(embedUrl, { ttl: 300 });
  if (!res.ok) return [];
  const html = await res.text();

  const srvMatches = [...html.matchAll(/class="srv-item[^"]*"[\s\S]*?data-platform="([^"]+)"[\s\S]*?data-pname="([^"]+)"[\s\S]*?data-code="([^"]+)"/gi)];
  console.log(`Found ${srvMatches.length} server matches for TV in ${Date.now() - start}ms`);

  const results = await Promise.all(srvMatches.map(async (m) => {
    const platform = m[1];
    const pname = m[2];
    const code = m[3];
    const proxyUrl = `https://rozgarlelo.modiplay.xyz/proxy.php?p=${encodeURIComponent(platform)}&c=${encodeURIComponent(code)}&noredirect=1`;

    try {
      const pRes = await fetch(proxyUrl, {
        headers: { "Referer": embedUrl, "User-Agent": DEFAULT_UA },
        signal: AbortSignal.timeout(2000),
      });
      if (!pRes.ok) return null;
      const pHtml = await pRes.text();
      const srcMatch = pHtml.match(/var\s+src\s*=\s*"([^"]+)"/i);
      if (!srcMatch) return null;

      const finalSrc = new URL(srcMatch[1].replace(/\\\//g, "/"), proxyUrl).toString();

      // Pre-validate
      const testRes = await fetch(finalSrc, {
        headers: { "Referer": proxyUrl, "User-Agent": DEFAULT_UA },
        signal: AbortSignal.timeout(1800),
      });
      if (!testRes.ok) return null;
      const text = await testRes.text();
      if (text.includes("EXT-X-ERROR") || !text.includes("#EXTM3U")) return null;

      return {
        name: `MultiMovies · ROGL ${pname} [720p]`,
        title: `ROGL ${pname} 720p\nHindi · Multi Audio`,
        url: finalSrc,
        proxyUrl: proxyUrl,
        isModiplay: true,
        quality: "720p",
        provider: "MultiMovies",
        languages: ["Hindi", "English"],
      };
    } catch (e) {
      return null;
    }
  }));

  const valid = results.filter(Boolean);
  console.log(`Resolved ${valid.length} live streams for TV in ${Date.now() - start}ms:`, valid.map(v => v.name));
  return valid;
}

testExtractAllServers(12697, false);
