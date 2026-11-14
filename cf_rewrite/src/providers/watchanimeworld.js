/**
 * WatchAnimeWorld (ToroFilm theme) Provider.
 */

import { edgeFetch, fetchText, fetchJson, DEFAULT_UA } from "../utils/http.js";
import { resolveEmbedUrl } from "../players/index.js";
import { resolveAbyss } from "../players/abyss.js";

const BASES = ["https://watchanimeworld.top", "https://watchanimeworld.one"];
const BASE = BASES[0];
const ONE_BASE = BASES[1];

export async function searchWatchAnimeWorld(query) {
  const url = `${BASE}/?s=${encodeURIComponent(query)}`;
  const html = await fetchText(url, { ttl: 600 });
  if (!html) return [];

  const results = [];
  const matches = [...html.matchAll(/<article[^>]*>[\s\S]*?<a[^>]*href="([^"]*(?:series|movie|movies)\/([^"/?#]+)[^"]*)"[^>]*>[\s\S]*?(?:alt="([^"]+)"|title="([^"]+)"|<h[23][^>]*>([^<]+)<\/h[23]>)/gi)];

  for (const m of matches) {
    const href = m[1];
    const slug = m[2];
    const title = (m[3] || m[4] || m[5] || slug).trim();
    const isMovie = href.includes("/movies/") || href.includes("/movie/");
    results.push({
      title,
      slug,
      type: isMovie ? "movie" : "series",
      provider: "watchanimeworld",
      url: `${BASE}/${isMovie ? "movies" : "series"}/${slug}`
    });
  }
  return results;
}

export async function getHomeCatalogWatchAnimeWorld() {
  const paths = ["", "series", "movies"];
  const results = [];
  const seen = new Set();

  await Promise.all(paths.map(async (p) => {
    const url = p ? `${BASE}/${p}` : BASE;
    const html = await fetchText(url, { ttl: 3600 });
    if (!html) return;

    const matches = [...html.matchAll(/<a[^>]*href="([^"]*(?:series|movie|movies)\/([^"/?#]+)[^"]*)"[^>]*>[\s\S]*?(?:alt="([^"]+)"|<h[23][^>]*>([^<]+)<\/h[23]>)/gi)];
    for (const m of matches) {
      const href = m[1];
      const slug = m[2];
      const title = (m[3] || m[4] || slug).trim();
      if (!slug || seen.has(slug)) continue;
      seen.add(slug);

      const isMovie = href.includes("/movies/") || href.includes("/movie/");
      results.push({
        title,
        slug,
        type: isMovie ? "movie" : "series",
        provider: "watchanimeworld",
        poster: ""
      });
    }
  }));

  return results;
}

export async function getWatchAnimeWorldStreams(slugOrTitle, isMovie = false, season = 1, episode = 1) {
  let targetSlug = slugOrTitle;
  if (!slugOrTitle.includes("-") || slugOrTitle.includes(" ")) {
    const results = await searchWatchAnimeWorld(slugOrTitle);
    if (!results.length) return [];
    targetSlug = results[0].slug;
  }

  const endpoint = isMovie ? "movies" : "series";
  const pageUrl = `${BASE}/${endpoint}/${targetSlug}`;
  const html = await fetchText(pageUrl, { ttl: 300 });
  if (!html) return [];

  let targetEpUrl = pageUrl;

  if (!isMovie) {
    // 1. Try ToroFilm action_select_season AJAX
    const postMatch = html.match(/data-post="(\d+)"/i);
    let episodeFound = false;

    if (postMatch) {
      const postId = postMatch[1];
      const ajaxUrl = `${ONE_BASE}/wp-admin/admin-ajax.php?action=action_select_season&season=${season}&post=${postId}`;
      const ajaxHtml = await fetchText(ajaxUrl, { ttl: 600 });
      if (ajaxHtml) {
        const epMatches = [...ajaxHtml.matchAll(/<a[^>]+href="([^"]*\/episode\/[^"]*)"/gi)];
        const wanted = epMatches.find(m => m[1].includes(`${season}x${episode}`) || m[1].includes(`-${season}x${episode}/`));
        if (wanted) {
          targetEpUrl = wanted[1];
          episodeFound = true;
        }
      }
    }

    // 2. Fallback to scraping series page HTML for episode link
    if (!episodeFound) {
      const allEps = [...html.matchAll(/<a[^>]+href="([^"]*(?:\/episode\/|\/episodes\/)[^"]*)"/gi)].map(m => m[1]);
      const matched = allEps.find(u => u.includes(`${season}x${episode}`) || u.includes(`-${episode}/`));
      if (matched) {
        targetEpUrl = matched;
      }
    }
  }

  const epHtml = targetEpUrl === pageUrl ? html : await fetchText(targetEpUrl, { ttl: 300 });
  if (!epHtml) return [];

  const streams = [];

  // 3. Check for waw-dub-player / dub-player iframe (Multi-Audio Abyss player)
  const dubMatch = epHtml.match(/src="([^"]*dub-player[^"]*)"/i);
  if (dubMatch) {
    try {
      const dubUrl = dubMatch[1].startsWith("http") ? dubMatch[1] : `${ONE_BASE}${dubMatch[1]}`;
      const dubHtml = await fetchText(dubUrl, { ttl: 600 });
      const cfgMatch = dubHtml.match(/CONFIG\s*=\s*(\{[\s\S]*?\});/);
      if (cfgMatch) {
        const config = JSON.parse(cfgMatch[1]);
        const prefix = config.prefix || "https://player.abyssplayer.com/";
        const ready = config.ready || {};
        const langs = config.lang || {};

        const dubTasks = Object.entries(ready).map(async ([langCode, abyssId]) => {
          const lName = langs[langCode]?.name || langCode.toUpperCase();
          const abyssUrl = `${prefix}${abyssId}`;
          const abyssStreams = await resolveAbyss(abyssUrl, `AnimeWorld ${lName}`);
          return abyssStreams.map(s => ({
            ...s,
            languages: [lName],
          }));
        });

        const settledDub = await Promise.allSettled(dubTasks);
        for (const r of settledDub) {
          if (r.status === "fulfilled" && Array.isArray(r.value)) {
            streams.push(...r.value);
          }
        }
      }
    } catch (e) {
      console.error("WatchAnimeWorld dub-player parse error:", e);
    }
  }

  // 4. Standard iframes and embeds
  const iframes = [
    ...epHtml.matchAll(/<iframe[^>]+src="([^"]+)"/gi),
    ...epHtml.matchAll(/data-(?:url|embed|src)="([^"]+)"/gi)
  ].map(m => m[1].replace(/&amp;/g, "&").trim()).filter(u => u.startsWith("http") && !u.includes("dub-player"));

  const tasks = iframes.map(u => resolveEmbedUrl(u, "AnimeWorld"));
  const settled = await Promise.allSettled(tasks);
  for (const s of settled) {
    if (s.status === "fulfilled" && Array.isArray(s.value)) {
      streams.push(...s.value);
    }
  }

  return streams;
}
