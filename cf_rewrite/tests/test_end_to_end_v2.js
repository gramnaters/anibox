import { handleRequest } from "../src/index.js";
import { resolveDirectTmdbStreams } from "../src/providers/direct_tmdb.js";

async function runEndToEndTests() {
  console.log("=== 1. TESTING DIRECT TMDB & IMDB (ROGL / MODIPLAY MULTI-SERVER) ===");
  const t0 = Date.now();
  const movieStreams = await resolveDirectTmdbStreams("1022789", true);
  console.log(`Movie TMDB 1022789 streams (${Date.now() - t0}ms):`, movieStreams.map(s => s.name));
  if (movieStreams.length === 0) throw new Error("Expected at least 1 movie stream");

  const t1 = Date.now();
  const tvStreams = await resolveDirectTmdbStreams("12697", false, 1, 1);
  console.log(`TV TMDB 12697 S01E01 streams (${Date.now() - t1}ms):`, tvStreams.map(s => s.name));
  if (tvStreams.length === 0) throw new Error("Expected at least 1 TV stream");

  const t2 = Date.now();
  const imdbStreams = await resolveDirectTmdbStreams("tt15239678", true);
  console.log(`IMDb tt15239678 streams (${Date.now() - t2}ms):`, imdbStreams.map(s => s.name));
  if (imdbStreams.length === 0) throw new Error("Expected at least 1 IMDb stream");

  console.log("\n=== 2. TESTING EDGE VIDEO STREAM PROXY (/stream/proxy) ===");
  const sssrrUrl = "https://njuaynwkh47.sssrr.org/sora/205193216/b1dlc0wrQnVZQ1B6K2M5OE92dENKMzc3MWhjYmNzRzN6K2FJTnl4bGlDcHdNUlJrWlE";
  const proxyReq = new Request(`https://anibox.gramnaters.workers.dev/stream/proxy?url=${encodeURIComponent(sssrrUrl)}&ref=${encodeURIComponent("https://abyssplayer.com/")}`, {
    headers: {
      "Range": "bytes=0-2048",
      "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
  });

  const t3 = Date.now();
  const proxyRes = await handleRequest(proxyReq);
  console.log(`Proxy response status (${Date.now() - t3}ms):`, proxyRes.status, proxyRes.statusText);
  console.log("Content-Type:", proxyRes.headers.get("content-type"));
  console.log("Content-Range:", proxyRes.headers.get("content-range"));
  console.log("Accept-Ranges:", proxyRes.headers.get("accept-ranges"));
  const proxyBuf = Buffer.from(await proxyRes.arrayBuffer());
  console.log("Proxy byte count:", proxyBuf.length);
  const hasFtyp = proxyBuf.includes(Buffer.from("ftyp"));
  console.log("MP4 Box 'ftyp' found in stream:", hasFtyp);
  if (!hasFtyp) throw new Error("Stream proxy did not return valid MP4 header");

  console.log("\n=== 3. TESTING STREMIO STREAM ROUTE WITH ABYSS & MODIPLAY ===");
  const streamReq = new Request("https://anibox.gramnaters.workers.dev/stream/movie/hd:tmdb:1022789.json");
  const t4 = Date.now();
  const streamRes = await handleRequest(streamReq);
  const streamJson = await streamRes.json();
  console.log(`Stream route returned ${streamJson.streams.length} streams in ${Date.now() - t4}ms`);
  
  for (const st of streamJson.streams) {
    console.log(`- ${st.name} -> ${st.url.slice(0, 75)}...`);
    if (st.url.includes("vidmmo.com") || st.url.includes("vidout.pages.dev")) {
      throw new Error(`Dead domain leaked into stream output: ${st.url}`);
    }
  }

  console.log("\nALL VERIFICATIONS PASSED SUCCESSFULLY!");
}

runEndToEndTests().catch(e => {
  console.error("Test failed:", e);
  process.exit(1);
});
