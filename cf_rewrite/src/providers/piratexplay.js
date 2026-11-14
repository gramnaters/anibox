/**
 * PirateXPlay Provider (piratexplay.cc).
 */

import { edgeFetch, fetchJson, fetchText, DEFAULT_UA } from "../utils/http.js";
import { resolveEmbedUrl } from "../players/index.js";

const BASE = "https://piratexplay.cc";

export async function searchPirateXPlay(query) {
  const url = `${BASE}/api/search.php/?keyword=${encodeURIComponent(query)}`;
  const json = await fetchJson(url, {
    headers: { "X-Requested-With": "XMLHttpRequest", "Referer": `${BASE}/` },
    ttl: 600
  });
  if (!json || !json.data) return [];

  const results = [];
  for (const item of json.data) {
    const tmdb = item.tmdb || {};
    const title = tmdb.title;
    const basename = tmdb.url;
    if (!title || !basename) continue;
    const isMovie = tmdb.type === "movie";
    results.push({
      title,
      slug: `${isMovie ? "movie" : "series"}/${basename}`,
      type: isMovie ? "movie" : "series",
      provider: "piratexplay",
      url: `${BASE}/${isMovie ? "movies" : "series"}/${basename}/`
    });
  }
  return results;
}

export async function getHomeCatalogPirateXPlay() {
  const sections = ["home", "category/series", "category/movie"];
  const results = [];
  const seen = new Set();

  await Promise.all(sections.map(async (sec) => {
    const url = `${BASE}/${sec}`;
    const html = await fetchText(url, { ttl: 3600 });
    if (!html) return;

    const matches = [...html.matchAll(/<a\s+href="([^"]*(?:\/series\/|\/movies\/|\/movie\/)[^"]*)"[\s\S]*?(?:alt="([^"]+)"|<h[23][^>]*>([^<]+)<\/h[23]>)/gi)];
    for (const m of matches) {
      const href = m[1];
      const title = (m[2] || m[3] || "").trim();
      const slug = href.replace(BASE, "").replace(/^\/+|\/+$/g, "");
      if (!slug || seen.has(slug)) continue;
      seen.add(slug);

      const isMovie = slug.startsWith("movie") || slug.startsWith("movies");
      results.push({
        title,
        slug,
        type: isMovie ? "movie" : "series",
        provider: "piratexplay",
        poster: ""
      });
    }
  }));

  return results;
}

export async function getPirateXPlayStreams(slugOrTitle, isMovie = false, season = 1, episode = 1) {
  let targetUrl = "";

  if (slugOrTitle.startsWith("http")) {
    targetUrl = slugOrTitle;
  } else if (slugOrTitle.includes("series/") || slugOrTitle.includes("movies/") || slugOrTitle.includes("movie/")) {
    const parts = slugOrTitle.split("/");
    const kind = parts[0] === "movie" ? "movies" : "series";
    const basename = parts[1];
    targetUrl = `${BASE}/${kind}/${basename}/`;
  } else {
    const results = await searchPirateXPlay(slugOrTitle);
    if (!results.length) return [];
    targetUrl = results[0].url;
  }

  let epUrl = targetUrl;
  if (!isMovie && season && episode) {
    epUrl = `${targetUrl.replace(/\/+$/, "")}-${season}x${episode}/`;
  }

  const html = await fetchText(epUrl, {
    headers: { "Referer": `${BASE}/` },
    ttl: 300
  });
  if (!html) return [];

  const rawLinks = [];
  for (const ifr of html.matchAll(/<iframe[^>]+(?:src|data-src)="([^"]+)"/gi)) {
    const u = ifr[1];
    if (u.includes("index11.php")) {
      // Follow index11.php player page to data-link servers
      const pHtml = await fetchText(u, { headers: { "Referer": epUrl }, ttl: 300 });
      if (pHtml) {
        for (const opt of pHtml.matchAll(/data-link="([^"]+)"/gi)) {
          if (opt[1].startsWith("http")) rawLinks.push(opt[1]);
        }
      }
    } else if (u.startsWith("http")) {
      rawLinks.push(u);
    }
  }

  const tasks = rawLinks.map(u => resolveEmbedUrl(u, "PirateXPlay"));
  const settled = await Promise.allSettled(tasks);
  const streams = [];
  for (const s of settled) {
    if (s.status === "fulfilled" && Array.isArray(s.value)) {
      streams.push(...s.value);
    }
  }
  return streams;
}
