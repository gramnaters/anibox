/**
 * ToonStream & Tooniboy Provider.
 */

import { edgeFetch, fetchJson, fetchText, DEFAULT_UA } from "../utils/http.js";
import { resolveEmbedUrl } from "../players/index.js";

const BASES = ["https://tooniboy.xyz", "https://toonstream.us"];
const BASE = BASES[0];

export async function searchToonStream(query) {
  const url = `${BASE}/search/all?q=${encodeURIComponent(query)}`;
  const json = await fetchJson(url, {
    headers: { "X-Requested-With": "XMLHttpRequest", "Referer": `${BASE}/` },
    ttl: 600
  });
  if (!json || !json.data) return [];

  return json.data.map(item => {
    const isMovie = item.type === "movie" || (item.url && item.url.includes("/movies/"));
    const slug = (item.url || "").replace(/^\/+|\/+$/g, "");
    return {
      title: item.title,
      slug,
      type: isMovie ? "movie" : "series",
      provider: "toonstream",
      url: `${BASE}/${slug}`
    };
  });
}

export async function getHomeCatalogToonStream() {
  const sections = ["home", "category/anime-series", "category/movies"];
  const results = [];
  const seen = new Set();

  await Promise.all(sections.map(async (sec) => {
    const url = `${BASE}/${sec}`;
    const html = await fetchText(url, { ttl: 3600 });
    if (!html) return;

    const matches = [...html.matchAll(/<a[^>]+href="([^"]*(?:\/series\/|\/movies\/|\/movie\/)[^"]*)"/gi)];
    for (const m of matches) {
      const href = m[1];
      const slug = href.replace(BASE, "").replace(/^\/+|\/+$/g, "");
      if (!slug || seen.has(slug) || slug.includes("category")) continue;
      seen.add(slug);

      const isMovie = slug.startsWith("movie") || slug.startsWith("movies");
      const basename = slug.split("/").pop();
      const title = basename.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());

      results.push({
        title,
        slug,
        type: isMovie ? "movie" : "series",
        provider: "toonstream",
        poster: ""
      });
    }
  }));

  return results;
}

export async function getToonStreamStreams(slugOrTitle, isMovie = false, season = 1, episode = 1) {
  let targetUrl = "";

  if (slugOrTitle.startsWith("http")) {
    targetUrl = slugOrTitle;
  } else if (slugOrTitle.includes("series/") || slugOrTitle.includes("movies/") || slugOrTitle.includes("movie/")) {
    const clean = slugOrTitle.replace(/^\/+|\/+$/g, "");
    targetUrl = `${BASE}/${clean}`;
  } else {
    const results = await searchToonStream(slugOrTitle);
    if (!results.length) return [];
    const cleanTitle = slugOrTitle.toLowerCase().trim();
    let best = results.find(r => r.title.toLowerCase().trim() === cleanTitle) ||
               results.find(r => r.title.toLowerCase().includes(cleanTitle)) ||
               results[0];
    targetUrl = best.url || `${BASE}/${best.slug}`;
  }

  let epUrl = targetUrl;
  if (!isMovie && season && episode) {
    const basename = targetUrl.replace(/\/+$/, "").split("/").pop();
    epUrl = `${BASE}/episode/${basename}-${season}x${episode}/`;
  }

  const html = await fetchText(epUrl, {
    headers: { "Referer": `${BASE}/` },
    ttl: 300
  });
  if (!html) return [];

  const iframes = [
    ...html.matchAll(/<iframe[^>]+src="([^"]+)"/gi),
    ...html.matchAll(/data-(?:url|embed|src)="([^"]+)"/gi)
  ].map(m => m[1].replace(/&amp;/g, "&").trim()).filter(u => u.startsWith("http"));

  const tasks = iframes.map(u => resolveEmbedUrl(u, "ToonStream"));
  const settled = await Promise.allSettled(tasks);
  const streams = [];
  for (const s of settled) {
    if (s.status === "fulfilled" && Array.isArray(s.value)) {
      streams.push(...s.value);
    }
  }
  return streams;
}
