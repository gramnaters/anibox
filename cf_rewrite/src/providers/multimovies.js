/**
 * MultiMovies Provider.
 */

import { edgeFetch, fetchText, DEFAULT_UA } from "../utils/http.js";
import { resolveEmbedUrl } from "../players/index.js";

const DOMAINS = [
  "https://m1.multimovies.courses",
  "https://multimovies.courses",
  "https://multimovies.cloud"
];
let activeDomain = DOMAINS[0];

export async function getLiveDomain() {
  return activeDomain;
}

export async function searchMultiMovies(query) {
  const dom = await getLiveDomain();
  const searchUrl = `${dom}/search?q=${encodeURIComponent(query)}`;
  const html = await fetchText(searchUrl, { ttl: 600 });
  if (!html) return [];

  const results = [];
  const matches = [...html.matchAll(/<a[^>]*class="[^"]*poster-art[^"]*"[^>]*href="([^"]+)"[^>]*aria-label="([^"]+)"/gi)];
  for (const m of matches) {
    const href = m[1];
    const title = m[2];
    const isMovie = href.includes("/movie/");
    const slug = href.replace(/^\/+|\/+$/g, "");
    results.push({
      title,
      slug,
      type: isMovie ? "movie" : "series",
      provider: "multimovies",
      url: `${dom}/${slug}`
    });
  }
  return results;
}

export async function getHomeCatalogMultiMovies() {
  const dom = await getLiveDomain();
  const paths = ["", "series", "movies", "genre/anime-series"];
  const results = [];
  const seen = new Set();

  await Promise.all(paths.map(async (p) => {
    const url = p ? `${dom}/${p}` : dom;
    const html = await fetchText(url, { ttl: 3600 });
    if (!html) return;

    const matches = [...html.matchAll(/<a[^>]*class="[^"]*poster-art[^"]*"[^>]*href="([^"]+)"[\s\S]*?alt="([^"]+)"/gi)];
    for (const m of matches) {
      const href = m[1];
      const title = m[2];
      if (seen.has(href)) continue;
      seen.add(href);
      const isMovie = href.includes("/movie/");
      const slug = href.replace(/^\/+|\/+$/g, "");
      results.push({
        title,
        slug,
        type: isMovie ? "movie" : "series",
        provider: "multimovies",
        poster: ""
      });
    }
  }));

  return results;
}

export async function getMultiMoviesStreams(slugOrTitle, isMovie = false, season = 1, episode = 1) {
  const dom = await getLiveDomain();
  let pageUrl = "";

  if (slugOrTitle.includes("series/") || slugOrTitle.includes("movie/")) {
    const clean = slugOrTitle.replace(/^\/+|\/+$/g, "");
    pageUrl = isMovie ? `${dom}/${clean}` : `${dom}/${clean}/season/${season}/episode/${episode}`;
  } else {
    const results = await searchMultiMovies(slugOrTitle);
    if (!results.length) return [];
    const cleanTitle = slugOrTitle.toLowerCase().trim();
    let best = results.find(r => r.title.toLowerCase().trim() === cleanTitle) ||
               results.find(r => r.title.toLowerCase().includes(cleanTitle)) ||
               results[0];
    pageUrl = isMovie ? `${dom}/${best.slug}` : `${dom}/${best.slug}/season/${season}/episode/${episode}`;
  }

  const html = await fetchText(pageUrl, { ttl: 300 });
  if (!html) return [];

  const embeds = [
    ...html.matchAll(/data-(?:embed|src|url)="([^"]+)"/gi),
    ...html.matchAll(/<iframe[^>]+src="([^"]+)"/gi)
  ].map(m => m[1].replace(/&amp;/g, "&").trim()).filter(u => u.startsWith("http") && !u.includes("vidmmo") && !u.includes("vidout"));

  const tasks = embeds.map(u => resolveEmbedUrl(u, "MultiMovies"));
  const settled = await Promise.allSettled(tasks);
  const streams = [];
  for (const s of settled) {
    if (s.status === "fulfilled" && Array.isArray(s.value)) {
      streams.push(...s.value);
    }
  }
  return streams;
}
