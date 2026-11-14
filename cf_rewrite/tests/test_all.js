/**
 * Comprehensive End-to-End Test Suite for AniBox Edge V2.
 */

import { pathToFileURL } from "node:url";
import path from "node:path";

const indexPath = path.resolve("./src/index.js");
const { handleRequest } = await import(pathToFileURL(indexPath).href);

let passCount = 0;
let failCount = 0;

function assert(condition, message) {
  if (condition) {
    console.log(`  ✓ PASS: ${message}`);
    passCount++;
  } else {
    console.error(`  ✗ FAIL: ${message}`);
    failCount++;
  }
}

async function runTests() {
  console.log("==================================================");
  console.log("   AniBox Edge V2: End-to-End Verification Suite  ");
  console.log("==================================================");

  // 1. Manifest
  console.log("\n[1/12] Testing Manifest...");
  const r1 = await handleRequest(new Request("http://localhost/manifest.json"));
  assert(r1.status === 200, "Manifest responds with HTTP 200");
  const m1 = await r1.json();
  assert(m1.id === "community.anibox", "Manifest ID is community.anibox");
  assert(m1.catalogs.length >= 8, `Manifest has ${m1.catalogs.length} catalogs`);
  assert(m1.resources.length === 3, "Manifest has catalog, meta, and stream resources");

  // 2. Configure UI
  console.log("\n[2/12] Testing Configure Dashboard...");
  const r2 = await handleRequest(new Request("http://localhost/configure"));
  assert(r2.status === 200, "Configure page responds with HTTP 200");
  const html2 = await r2.text();
  assert(html2.includes("AniBox Edge"), "Configure page contains brand header");
  assert(html2.includes("MultiMovies") && html2.includes("ToonStream"), "Configure page lists active providers");

  // 3. Trending Anime Catalog
  console.log("\n[3/12] Testing Trending Anime Catalog...");
  const r3 = await handleRequest(new Request("http://localhost/catalog/series/anibox_trending_series.json"));
  assert(r3.status === 200, "Trending series catalog responds with HTTP 200");
  const c3 = await r3.json();
  assert(c3.metas && c3.metas.length > 0, `Trending anime catalog returned ${c3.metas ? c3.metas.length : 0} items`);
  if (c3.metas && c3.metas[0]) {
    assert(c3.metas[0].poster.startsWith("http"), `First item (${c3.metas[0].name}) has valid poster`);
  }

  // 4. MultiMovies Provider Catalog
  console.log("\n[4/12] Testing MultiMovies Provider Catalog...");
  const r4 = await handleRequest(new Request("http://localhost/catalog/series/multimovies_series.json"));
  assert(r4.status === 200, "MultiMovies catalog responds with HTTP 200");
  const c4 = await r4.json();
  assert(c4.metas && c4.metas.length > 0, `MultiMovies catalog returned ${c4.metas ? c4.metas.length : 0} items`);

  // 5. ToonStream Provider Catalog
  console.log("\n[5/12] Testing ToonStream Provider Catalog...");
  const r5 = await handleRequest(new Request("http://localhost/catalog/series/toonstream_series.json"));
  assert(r5.status === 200, "ToonStream catalog responds with HTTP 200");
  const c5 = await r5.json();
  assert(c5.metas && c5.metas.length > 0, `ToonStream catalog returned ${c5.metas ? c5.metas.length : 0} items`);

  // 6. PirateXPlay Provider Catalog
  console.log("\n[6/12] Testing PirateXPlay Provider Catalog...");
  const r6 = await handleRequest(new Request("http://localhost/catalog/series/piratexplay_series.json"));
  assert(r6.status === 200, "PirateXPlay catalog responds with HTTP 200");
  const c6 = await r6.json();
  assert(c6.metas && c6.metas.length > 0, `PirateXPlay catalog returned ${c6.metas ? c6.metas.length : 0} items`);

  // 7. Catalog Search
  console.log("\n[7/12] Testing Catalog Search for 'Dragon Ball'...");
  const r7 = await handleRequest(new Request("http://localhost/catalog/series/anibox_trending_series/search=Dragon%20Ball.json"));
  assert(r7.status === 200, "Search responds with HTTP 200");
  const s7 = await r7.json();
  assert(s7.metas && s7.metas.length > 0, `Search found ${s7.metas ? s7.metas.length : 0} items`);

  // 8. Meta for Dragon Ball GT (Series)
  console.log("\n[8/12] Testing Meta for Dragon Ball GT (tmdb:12697)...");
  const r8 = await handleRequest(new Request("http://localhost/meta/series/tmdb:12697.json"));
  assert(r8.status === 200, "Meta responds with HTTP 200");
  const m8 = await r8.json();
  assert(m8.meta && m8.meta.name === "Dragon Ball GT", `Meta resolved name: ${m8.meta ? m8.meta.name : "null"}`);
  assert(m8.meta.videos && m8.meta.videos.length > 0, `Meta contains ${m8.meta.videos ? m8.meta.videos.length : 0} episodes`);
  if (m8.meta.videos && m8.meta.videos[0]) {
    assert(m8.meta.videos[0].thumbnail.startsWith("http"), "Episode 1 has valid thumbnail card photo");
    console.log(`    Ep 1: "${m8.meta.videos[0].title}" | Thumb: ${m8.meta.videos[0].thumbnail.slice(0, 50)}...`);
  }

  // 9. Meta for Zootopia (Movie)
  console.log("\n[9/12] Testing Meta for Zootopia (tmdb:269149)...");
  const r9 = await handleRequest(new Request("http://localhost/meta/movie/tmdb:269149.json"));
  assert(r9.status === 200, "Movie meta responds with HTTP 200");
  const m9 = await r9.json();
  assert(m9.meta && m9.meta.name === "Zootopia", `Movie resolved name: ${m9.meta ? m9.meta.name : "null"}`);
  assert(m9.meta.behaviorHints && m9.meta.behaviorHints.defaultVideoId === "tmdb:269149", "Movie has defaultVideoId configured");

  // 10. Dragon Ball GT Episode 1 Streams
  console.log("\n[10/12] Testing Streams for Dragon Ball GT Ep 1 (tmdb:12697:1:1)...");
  const r10 = await handleRequest(new Request("http://localhost/stream/series/tmdb:12697:1:1.json"));
  assert(r10.status === 200, "Stream responds with HTTP 200");
  const s10 = await r10.json();
  assert(s10.streams && s10.streams.length > 0, `Resolved ${s10.streams ? s10.streams.length : 0} streams for DB GT Ep 1`);
  for (const st of (s10.streams || []).slice(0, 3)) {
    console.log(`    - ${st.name} --> ${st.url.slice(0, 65)}...`);
  }

  // 11. Zootopia Movie Streams (4K & 1080p)
  console.log("\n[11/12] Testing Streams for Zootopia (tmdb:269149)...");
  const r11 = await handleRequest(new Request("http://localhost/stream/movie/tmdb:269149.json"));
  assert(r11.status === 200, "Movie stream responds with HTTP 200");
  const s11 = await r11.json();
  assert(s11.streams && s11.streams.length > 0, `Resolved ${s11.streams ? s11.streams.length : 0} streams for Zootopia`);
  for (const st of (s11.streams || []).slice(0, 4)) {
    console.log(`    - ${st.name} --> ${st.url.slice(0, 65)}...`);
  }

  // 12. Cinemeta IMDb ID resolution (tt0139774:1:1)
  console.log("\n[12/12] Testing Cinemeta IMDb ID stream resolution (tt0139774:1:1)...");
  const r12 = await handleRequest(new Request("http://localhost/stream/series/tt0139774:1:1.json"));
  assert(r12.status === 200, "IMDb ID stream responds with HTTP 200");
  const s12 = await r12.json();
  assert(s12.streams && s12.streams.length > 0, `Resolved ${s12.streams ? s12.streams.length : 0} streams for IMDb ID tt0139774:1:1`);

  console.log("\n==================================================");
  console.log(`  Test Results: ${passCount} Passed, ${failCount} Failed`);
  console.log("==================================================");

  if (failCount > 0) {
    process.exit(1);
  }
}

runTests().catch((err) => {
  console.error("FATAL TEST ERROR:", err);
  process.exit(1);
});
