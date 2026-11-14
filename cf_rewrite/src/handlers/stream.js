/**
 * Stream Aggregation, Filtering, and Sorting Handler.
 */

import { corsHeaders } from "../utils/http.js";
import { resolveTitleAndTmdbId } from "../utils/tmdb.js";
import { aggregateStreams } from "../providers/index.js";

const STREAM_CACHE = new Map();
const CACHE_TTL_MS = 600 * 1000; // 10 minutes

export async function handleStream(config, contentType, contentId, url) {
  const cacheKey = `${contentType}:${contentId}:${JSON.stringify(config)}`;
  const cached = STREAM_CACHE.get(cacheKey);
  if (cached && Date.now() - cached.ts < CACHE_TTL_MS) {
    return new Response(JSON.stringify({ streams: cached.streams }), {
      headers: corsHeaders({ "Cache-Control": "public, max-age=600, stale-while-revalidate=300" })
    });
  }

  const isMovie = contentType === "movie";
  let season = 1, episode = 1, baseId = contentId, queryOrSlug = contentId;

  if (contentId.startsWith("hd:") && !contentId.startsWith("hd:tmdb:")) {
    const parts = contentId.split(":");
    if (parts.length >= 4 && !isNaN(parts[parts.length - 2]) && !isNaN(parts[parts.length - 1])) {
      season = parseInt(parts[parts.length - 2], 10);
      episode = parseInt(parts[parts.length - 1], 10);
      queryOrSlug = parts.slice(2, parts.length - 2).join(":").replace(/~/g, "/");
    } else {
      queryOrSlug = parts.slice(2).join(":").replace(/~/g, "/");
    }
    baseId = queryOrSlug;
  } else {
    const parts = contentId.split(":");
    if (parts.length >= 3 && !isNaN(parts[parts.length - 2]) && !isNaN(parts[parts.length - 1])) {
      season = parseInt(parts[parts.length - 2], 10);
      episode = parseInt(parts[parts.length - 1], 10);
      baseId = parts.slice(0, parts.length - 2).join(":");
    }
  }

  const { tmdbId, title } = await resolveTitleAndTmdbId(baseId, isMovie ? "movie" : "series");
  queryOrSlug = title || queryOrSlug;
  const imdbId = baseId.startsWith("tt") ? baseId : null;

  // Active providers from config
  const enabledProviders = [];
  for (const k of ["multimovies", "toonstream", "watchanimeworld", "piratexplay"]) {
    if (config[`source_${k}`] !== false && config[`source_${k}`] !== "unchecked") {
      enabledProviders.push(k);
    }
  }

  // Aggregate streams from Direct TMDB + Providers
  let rawStreams = await aggregateStreams({
    tmdbId,
    imdbId,
    query: queryOrSlug,
    isMovie,
    season,
    episode,
    enabledProviders
  });

  // Filter by Quality
  const filterQ = config.filter_qualities;
  if (filterQ && filterQ !== "all") {
    const allowed = filterQ.toLowerCase().split(",").map(s => s.trim());
    rawStreams = rawStreams.filter(s => {
      const q = (s.quality || "").toLowerCase();
      return !q || allowed.includes(q);
    });
  }

  // Filter by Audio / Language
  const filterLang = config.filter_audio;
  if (filterLang === "hindi_only") {
    rawStreams = rawStreams.filter(s => {
      const langs = (s.languages || []).map(l => l.toLowerCase());
      return langs.some(l => l.includes("hindi"));
    });
  }

  // Sort streams
  const sortBy = config.sort_by || "quality_desc";
  const qRank = { "4k": 6, "2160p": 6, "1440p": 5, "1080p": 4, "720p": 3, "480p": 2, "360p": 1, "": 0 };

  if (sortBy === "quality_asc") {
    rawStreams.sort((a, b) => (qRank[(a.quality || "").toLowerCase()] || 0) - (qRank[(b.quality || "").toLowerCase()] || 0));
  } else if (sortBy === "provider") {
    rawStreams.sort((a, b) => (a.provider || "").localeCompare(b.provider || ""));
  } else {
    rawStreams.sort((a, b) => (qRank[(b.quality || "").toLowerCase()] || 0) - (qRank[(a.quality || "").toLowerCase()] || 0));
  }

  // Deduplicate and format Stremio stream items
  const seen = new Set();
  const finalStreams = [];
  for (const s of rawStreams) {
    if (!s.url || seen.has(s.url)) continue;

    // Purge completely dead / unresolvable hosts
    if (s.url.includes("vidmmo.com") || s.url.includes("vidout.pages.dev")) {
      continue;
    }

    seen.add(s.url);

    const langStr = (s.languages && s.languages.length) ? s.languages.join(" · ") : "Multi Audio";
    const nameStr = s.name || `AniBox · ${s.provider || "Direct"} [${s.quality || "HD"}]`;
    const titleStr = s.title || `${s.name || "Stream"}\n${langStr}`;

    let finalUrl = s.url;
    let finalHints = s.behaviorHints || {};

    if (s.isModiplay || s.url.includes("modiplay.xyz")) {
      const ref = s.proxyUrl || s.behaviorHints?.proxyHeaders?.request?.Referer || "";
      finalUrl = `${url.origin}/hls/manifest?url=${encodeURIComponent(s.url)}&ref=${encodeURIComponent(ref)}`;
      finalHints = { notWebReady: false };
    } else if (
      s.isAbyss ||
      s.url.includes("sssrr.org") ||
      s.url.includes("trycloudflare.com") ||
      s.behaviorHints?.proxyHeaders?.request?.Referer?.includes("abyss")
    ) {
      // Route Abyss / SSSRR streams through Edge Range Proxy to preserve Referer and eliminate 403 / buffering
      const ref = s.behaviorHints?.proxyHeaders?.request?.Referer || "https://abyssplayer.com/";
      finalUrl = `${url.origin}/stream/proxy?url=${encodeURIComponent(s.url)}&ref=${encodeURIComponent(ref)}`;
      finalHints = { notWebReady: false };
    }

    finalStreams.push({
      name: nameStr,
      title: titleStr,
      url: finalUrl,
      behaviorHints: finalHints
    });
  }

  STREAM_CACHE.set(cacheKey, { ts: Date.now(), streams: finalStreams });

  return new Response(JSON.stringify({ streams: finalStreams }), {
    headers: corsHeaders({ "Cache-Control": "public, max-age=600, stale-while-revalidate=300" })
  });
}
