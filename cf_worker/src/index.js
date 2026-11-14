/**
 * AniBox Edge - Cloudflare Workers Addon & Edge Scraper
 * Runs at 300+ edge locations worldwide for instant (<50ms) catalog, metadata, and video stream scraping.
 */

const TMDB_API_KEY = "1b3113663c9004682ed61086cf967c44";
const DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36";

const GENRE_MAP = {
  16: "Animation",
  28: "Action",
  12: "Adventure",
  35: "Comedy",
  18: "Drama",
  14: "Fantasy",
  878: "Science Fiction",
  10759: "Action & Adventure",
  10762: "Kids",
  10765: "Sci-Fi & Fantasy",
  9648: "Mystery",
  10751: "Family"
};

const MANIFEST = {
  id: "community.anibox.edge",
  version: "2.1.0",
  name: "AniBox Edge",
  description: "Ultra-fast Cloudflare Edge scraper with Hindi & multi-audio anime, series, and cartoons.",
  logo: "https://raw.githubusercontent.com/stremio/stremio-addon-sdk/master/docs/logo.png",
  background: "https://image.tmdb.org/t/p/original/xLoQu249IIlQtFsFgF6VZhMYWfz.jpg",
  resources: [
    { name: "catalog", types: ["series", "movie", "anime"] },
    { name: "meta", types: ["series", "movie", "anime"], idPrefixes: ["tmdb:", "tt", "hd:"] },
    { name: "stream", types: ["series", "movie", "anime"], idPrefixes: ["tmdb:", "tt", "hd:"] }
  ],
  types: ["series", "movie", "anime"],
  catalogs: [
    {
      type: "series",
      id: "anibox_trending_series",
      name: "AniBox · Popular Anime Series",
      extra: [
        { name: "search", isRequired: false },
        { name: "skip", isRequired: false }
      ]
    },
    {
      type: "movie",
      id: "anibox_popular_movies",
      name: "AniBox · Anime & Cartoon Movies",
      extra: [
        { name: "search", isRequired: false },
        { name: "skip", isRequired: false }
      ]
    },
    {
      type: "series",
      id: "anibox_hindi_series",
      name: "AniBox · Hindi Dub Anime",
      extra: [
        { name: "search", isRequired: false },
        { name: "skip", isRequired: false }
      ]
    },
    {
      type: "series",
      id: "anibox_toonstream",
      name: "AniBox · ToonStream Cartoons",
      extra: [
        { name: "search", isRequired: false },
        { name: "skip", isRequired: false }
      ]
    },
    {
      type: "series",
      id: "anibox_multimovies",
      name: "AniBox · MultiMovies Series",
      extra: [
        { name: "search", isRequired: false },
        { name: "skip", isRequired: false }
      ]
    },
    {
      type: "anime",
      id: "anibox_edge_catalog",
      name: "AniBox · Anime Catalog",
      extra: [
        { name: "search", isRequired: false },
        { name: "skip", isRequired: false }
      ]
    }
  ],
  idPrefixes: ["tmdb:", "tt", "hd:"],
  behaviorHints: {
    configurable: true,
    configurationRequired: false
  }
};

// In-memory cache for edge isolates
const STREAM_CACHE = new Map();
const CACHE_TTL_MS = 600 * 1000; // 10 minutes

function corsHeaders(extraHeaders = {}) {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Content-Type": "application/json; charset=utf-8",
    ...extraHeaders
  };
}

function parseConfig(seg) {
  if (!seg) return {};
  try {
    let padded = seg + "=".repeat((4 - (seg.length % 4)) % 4);
    let bin = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
    return JSON.parse(bin);
  } catch (e) {
    return {};
  }
}

async function edgeFetch(url, options = {}) {
  const headers = { "User-Agent": DEFAULT_UA, ...(options.headers || {}) };
  const fetchOpts = { ...options, headers };
  if (typeof fetch !== "undefined") {
    fetchOpts.cf = {
      cacheTtl: options.ttl || 300,
      cacheEverything: true,
    };
  }
  return fetch(url, fetchOpts);
}

// --- TMDB Metadata Helpers ---
async function getTmdbTitle(contentId, type = "movie") {
  let tmdbId = contentId;
  if (contentId.startsWith("tmdb:")) tmdbId = contentId.replace("tmdb:", "");
  else if (contentId.startsWith("hd:tmdb:")) tmdbId = contentId.replace("hd:tmdb:", "");
  else if (contentId.startsWith("tt")) {
    const res = await edgeFetch(
      `https://api.themoviedb.org/3/find/${contentId}?api_key=${TMDB_API_KEY}&external_source=imdb_id`,
      { ttl: 86400 }
    );
    if (!res.ok) return null;
    const data = await res.json();
    const match = (data.tv_results || [])[0] || (data.movie_results || [])[0];
    if (match) tmdbId = String(match.id);
  }

  if (!tmdbId || isNaN(tmdbId)) return null;

  const endpoint = type === "series" || type === "anime" ? `tv/${tmdbId}` : `movie/${tmdbId}`;
  const res = await edgeFetch(
    `https://api.themoviedb.org/3/${endpoint}?api_key=${TMDB_API_KEY}`,
    { ttl: 86400 }
  );
  if (!res.ok) return null;
  const json = await res.json();
  return json.name || json.title || json.original_name || json.original_title || null;
}

// --- Catalog Handler ---
async function handleCatalog(configStr, catalogType, catalogId, extra, url) {
  let searchQuery = "";
  let skip = 0;

  if (extra) {
    const searchMatch = extra.match(/search=([^/&]+)/i);
    if (searchMatch) searchQuery = decodeURIComponent(searchMatch[1]);
    const skipMatch = extra.match(/skip=([0-9]+)/i);
    if (skipMatch) skip = parseInt(skipMatch[1], 10);
  }

  if (!searchQuery && url.searchParams.has("search")) {
    searchQuery = url.searchParams.get("search");
  }
  if (!skip && url.searchParams.has("skip")) {
    skip = parseInt(url.searchParams.get("skip") || "0", 10);
  }

  const page = Math.floor(skip / 20) + 1;
  const isMovie = catalogType === "movie";
  let metas = [];

  try {
    if (searchQuery) {
      const endpoint = isMovie ? "search/movie" : "search/tv";
      const tmdbUrl = `https://api.themoviedb.org/3/${endpoint}?api_key=${TMDB_API_KEY}&query=${encodeURIComponent(searchQuery)}&page=${page}`;
      const res = await edgeFetch(tmdbUrl, { ttl: 3600 });
      if (res.ok) {
        const data = await res.json();
        metas = (data.results || []).map(item => ({
          id: `tmdb:${item.id}`,
          type: isMovie ? "movie" : "series",
          name: item.name || item.title || item.original_name || item.original_title || "Unknown",
          poster: item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : "",
          background: item.backdrop_path ? `https://image.tmdb.org/t/p/original${item.backdrop_path}` : "",
          posterShape: "poster",
          description: (item.overview || "").slice(0, 300),
          releaseInfo: (item.first_air_date || item.release_date || "").slice(0, 4),
          imdbRating: item.vote_average ? String(item.vote_average.toFixed(1)) : undefined,
          genres: (item.genre_ids || []).map(gid => GENRE_MAP[gid]).filter(Boolean)
        }));
      }
    } else {
      let discoverUrl = "";
      if (catalogId === "anibox_popular_movies") {
        discoverUrl = `https://api.themoviedb.org/3/discover/movie?api_key=${TMDB_API_KEY}&with_genres=16&sort_by=popularity.desc&page=${page}`;
      } else if (catalogId === "anibox_hindi_series") {
        discoverUrl = `https://api.themoviedb.org/3/discover/tv?api_key=${TMDB_API_KEY}&with_keywords=210024&with_original_language=ja|hi|en&sort_by=vote_count.desc&page=${page}`;
      } else if (catalogId === "anibox_toonstream") {
        discoverUrl = `https://api.themoviedb.org/3/discover/tv?api_key=${TMDB_API_KEY}&with_genres=16&sort_by=popularity.desc&page=${page}`;
      } else if (catalogId === "anibox_multimovies") {
        discoverUrl = `https://api.themoviedb.org/3/discover/tv?api_key=${TMDB_API_KEY}&with_keywords=210024&sort_by=first_air_date.desc&page=${page}`;
      } else {
        // anibox_trending_series or anibox_edge_catalog
        discoverUrl = `https://api.themoviedb.org/3/discover/tv?api_key=${TMDB_API_KEY}&with_keywords=210024&sort_by=popularity.desc&page=${page}`;
      }

      const res = await edgeFetch(discoverUrl, { ttl: 7200 });
      if (res.ok) {
        const data = await res.json();
        metas = (data.results || []).map(item => ({
          id: `tmdb:${item.id}`,
          type: isMovie ? "movie" : "series",
          name: item.name || item.title || item.original_name || item.original_title || "Unknown",
          poster: item.poster_path ? `https://image.tmdb.org/t/p/w500${item.poster_path}` : "",
          background: item.backdrop_path ? `https://image.tmdb.org/t/p/original${item.backdrop_path}` : "",
          posterShape: "poster",
          description: (item.overview || "").slice(0, 300),
          releaseInfo: (item.first_air_date || item.release_date || "").slice(0, 4),
          imdbRating: item.vote_average ? String(item.vote_average.toFixed(1)) : undefined,
          genres: (item.genre_ids || []).map(gid => GENRE_MAP[gid]).filter(Boolean)
        }));
      }
    }
  } catch (e) {
    console.error("Catalog error:", e);
  }

  return new Response(JSON.stringify({ metas }), {
    headers: corsHeaders({ "Cache-Control": "public, max-age=3600, stale-while-revalidate=1800" })
  });
}

// --- Meta Handler ---
async function handleMeta(configStr, metaType, contentId, url) {
  let tmdbId = null;
  const isMovie = metaType === "movie";

  if (contentId.startsWith("tmdb:")) {
    tmdbId = contentId.replace("tmdb:", "");
  } else if (contentId.startsWith("hd:tmdb:")) {
    tmdbId = contentId.replace("hd:tmdb:", "");
  } else if (contentId.startsWith("tt")) {
    const findRes = await edgeFetch(
      `https://api.themoviedb.org/3/find/${contentId}?api_key=${TMDB_API_KEY}&external_source=imdb_id`,
      { ttl: 86400 }
    );
    if (findRes.ok) {
      const findData = await findRes.json();
      const match = isMovie ? (findData.movie_results || [])[0] : ((findData.tv_results || [])[0] || (findData.movie_results || [])[0]);
      if (match) tmdbId = String(match.id);
    }
  } else if (contentId.startsWith("hd:")) {
    // Provider slug meta: search TMDB with clean title
    const rawName = contentId.split(":").slice(2).join(" ").replace(/[-_~]/g, " ");
    const searchRes = await edgeFetch(
      `https://api.themoviedb.org/3/search/${isMovie ? "movie" : "tv"}?api_key=${TMDB_API_KEY}&query=${encodeURIComponent(rawName)}`,
      { ttl: 86400 }
    );
    if (searchRes.ok) {
      const sData = await searchRes.json();
      if (sData.results && sData.results.length > 0) {
        tmdbId = String(sData.results[0].id);
      }
    }
  }

  if (!tmdbId) {
    return new Response(JSON.stringify({ meta: {} }), { headers: corsHeaders() });
  }

  try {
    const endpoint = isMovie ? `movie/${tmdbId}` : `tv/${tmdbId}`;
    const detailRes = await edgeFetch(
      `https://api.themoviedb.org/3/${endpoint}?api_key=${TMDB_API_KEY}&append_to_response=external_ids,seasons`,
      { ttl: 86400 }
    );
    if (!detailRes.ok) {
      return new Response(JSON.stringify({ meta: {} }), { headers: corsHeaders() });
    }

    const data = await detailRes.json();
    const meta = {
      id: contentId,
      type: isMovie ? "movie" : "series",
      name: data.name || data.title || data.original_name || data.original_title,
      poster: data.poster_path ? `https://image.tmdb.org/t/p/w500${data.poster_path}` : "",
      background: data.backdrop_path ? `https://image.tmdb.org/t/p/original${data.backdrop_path}` : "",
      description: data.overview || "",
      genres: (data.genres || []).map(g => g.name),
      releaseInfo: (data.release_date || data.first_air_date || "").slice(0, 4),
      imdbRating: data.vote_average ? String(data.vote_average.toFixed(1)) : undefined,
    };

    if (isMovie) {
      meta.behaviorHints = { defaultVideoId: contentId, hasScheduledVideos: false };
      meta.videos = [];
      return new Response(JSON.stringify({ meta }), {
        headers: corsHeaders({ "Cache-Control": "public, max-age=86400, stale-while-revalidate=43200" })
      });
    }

    // Series: gather seasons and episode thumbnails & titles
    const seasons = (data.seasons || []).filter(s => s.season_number > 0).slice(0, 6);
    const videos = [];

    const seasonFetches = seasons.map(async (s) => {
      try {
        const sRes = await edgeFetch(
          `https://api.themoviedb.org/3/tv/${tmdbId}/season/${s.season_number}?api_key=${TMDB_API_KEY}`,
          { ttl: 86400 }
        );
        if (!sRes.ok) return [];
        const sData = await sRes.json();
        return (sData.episodes || []).map(ep => ({
          id: `${contentId}:${s.season_number}:${ep.episode_number}`,
          title: ep.name || `Episode ${ep.episode_number}`,
          season: s.season_number,
          episode: ep.episode_number,
          thumbnail: ep.still_path ? `https://image.tmdb.org/t/p/w500${ep.still_path}` : (meta.poster || ""),
          overview: ep.overview || "",
          released: ep.air_date ? new Date(ep.air_date).toISOString() : ""
        }));
      } catch (err) {
        return [];
      }
    });

    const seasonResults = await Promise.all(seasonFetches);
    for (const eps of seasonResults) {
      videos.push(...eps);
    }

    if (videos.length === 0) {
      for (let i = 1; i <= 12; i++) {
        videos.push({
          id: `${contentId}:1:${i}`,
          title: `Episode ${i}`,
          season: 1,
          episode: i,
          thumbnail: meta.poster || ""
        });
      }
    }

    videos.sort((a, b) => a.season !== b.season ? a.season - b.season : a.episode - b.episode);
    meta.videos = videos;

    return new Response(JSON.stringify({ meta }), {
      headers: corsHeaders({ "Cache-Control": "public, max-age=86400, stale-while-revalidate=43200" })
    });
  } catch (e) {
    console.error("Meta error:", e);
    return new Response(JSON.stringify({ meta: {} }), { headers: corsHeaders() });
  }
}

// --- MultiMovies Scraper ---
async function scrapeMultiMovies(titleOrSlug, isMovie = false, season = 1, episode = 1) {
  const streams = [];
  try {
    let pageUrl = "";
    if (titleOrSlug.includes("/series/") || titleOrSlug.includes("/movie/")) {
      const cleanSlug = titleOrSlug.replace(/^\/+|\/+$/g, "");
      pageUrl = isMovie
        ? `https://m1.multimovies.courses/${cleanSlug}`
        : `https://m1.multimovies.courses/${cleanSlug}/season/${season}/episode/${episode}`;
    } else {
      const searchUrl = `https://m1.multimovies.courses/search?q=${encodeURIComponent(titleOrSlug)}`;
      const res = await edgeFetch(searchUrl, { ttl: 600 });
      if (!res.ok) return [];
      const html = await res.text();

      const cardMatches = [...html.matchAll(/<a[^>]*class="[^"]*poster-art[^"]*"[^>]*href="([^"]+)"[^>]*aria-label="([^"]+)"/gi)];
      let targetUrl = null;
      const cleanTitle = titleOrSlug.toLowerCase().trim();

      // 1. Exact match
      for (const match of cardMatches) {
        if (match[2].toLowerCase().trim() === cleanTitle) {
          targetUrl = match[1];
          break;
        }
      }
      // 2. Contains match
      if (!targetUrl) {
        for (const match of cardMatches) {
          if (match[2].toLowerCase().includes(cleanTitle)) {
            targetUrl = match[1];
            break;
          }
        }
      }
      if (!targetUrl && cardMatches.length > 0) targetUrl = cardMatches[0][1];
      if (!targetUrl) return [];

      const cleanSlug = targetUrl.replace(/^\/+|\/+$/g, "");
      pageUrl = isMovie
        ? `https://m1.multimovies.courses/${cleanSlug}`
        : `https://m1.multimovies.courses/${cleanSlug}/season/${season}/episode/${episode}`;
    }

    const pageRes = await edgeFetch(pageUrl, { ttl: 300 });
    if (!pageRes.ok) return [];
    const pageHtml = await pageRes.text();

    const embeds = [
      ...pageHtml.matchAll(/data-(?:embed|src|url)="([^"]+)"/gi),
      ...pageHtml.matchAll(/<iframe[^>]+src="([^"]+)"/gi)
    ].map(m => m[1].replace(/&amp;/g, "&").trim()).filter(u => u.startsWith("http"));

    const resolveTasks = embeds.map(async (u) => {
      try {
        if (u.includes("modiplay") || u.includes("rozgarlelo")) {
          const s = await resolveModiplay(u);
          if (s) streams.push({ ...s, provider: "MultiMovies" });
        } else if (u.includes("bysetayico.com") || u.includes("byse")) {
          const s = await resolveByse(u);
          if (s) streams.push({ ...s, provider: "MultiMovies" });
        } else if (u.includes("vidout.pages.dev") || u.includes("embed.filmu.in") || u.includes("vidrift.net")) {
          const r = await edgeFetch(u, { headers: { "Referer": pageUrl }, ttl: 300 });
          if (r.ok) {
            const h = await r.text();
            const m3 = h.match(/https?:\/\/[^\s"'<>\\]+\.m3u8[^\s"'<>\\]*/);
            if (m3) {
              const host = new URL(u).origin + "/";
              streams.push({
                name: "MultiMovies Direct [1080p]",
                title: "MultiMovies HLS 1080p\nHindi · Multi Audio",
                url: m3[0],
                quality: "1080p",
                provider: "MultiMovies",
                behaviorHints: { proxyHeaders: { request: { "User-Agent": DEFAULT_UA, "Referer": host } } }
              });
            }
          }
        } else if (u.includes("vidmmo.com") || u.includes(".m3u8")) {
          streams.push({
            name: "MultiMovies HLS [1080p]",
            title: "MultiMovies Direct HLS 1080p\nHindi · Multi Audio",
            url: u,
            quality: "1080p",
            provider: "MultiMovies",
            behaviorHints: { proxyHeaders: { request: { "User-Agent": DEFAULT_UA, "Referer": "https://m1.multimovies.courses/" } } }
          });
        }
      } catch (err) {}
    });

    await Promise.all(resolveTasks);
  } catch (e) {
    console.error("MultiMovies edge error:", e);
  }
  return streams;
}

// --- ModiPlay Resolver ---
async function resolveModiplay(embedUrl) {
  try {
    const r1 = await edgeFetch(embedUrl, { ttl: 300 });
    if (!r1.ok) return null;
    const html1 = await r1.text();
    const ifm = html1.match(/<iframe[^>]+src="([^"]+)"/i);
    if (!ifm) return null;

    const rawProxy = ifm[1].replace(/&amp;/g, "&");
    const proxyUrl = new URL(rawProxy, embedUrl).toString();

    const r2 = await edgeFetch(proxyUrl, { headers: { Referer: embedUrl }, ttl: 300 });
    if (!r2.ok) return null;
    const html2 = await r2.text();

    const srcMatch = html2.match(/var\s+src\s*=\s*"([^"]+)"/i);
    if (srcMatch) {
      const finalSrc = new URL(srcMatch[1].replace(/\\\//g, "/"), proxyUrl).toString();
      return {
        name: "MultiMovies ModiPlay [720p]",
        title: "ModiPlay 720p\nHindi · Multi Audio",
        url: finalSrc,
        quality: "720p",
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
    }
  } catch (e) {
    return null;
  }
  return null;
}

// --- Byse Player Resolver ---
async function resolveByse(embedUrl) {
  try {
    const res = await edgeFetch(embedUrl, {
      headers: { Referer: "https://m1.multimovies.courses/" },
      ttl: 300,
    });
    if (!res.ok) return null;
    const html = await res.text();

    const fileMatch = html.match(/file:\s*["']([^"']+\.m3u8[^"']*)["']/i) ||
                      html.match(/source:\s*["']([^"']+\.m3u8[^"']*)["']/i);
    if (!fileMatch) return null;

    const m3u8Url = fileMatch[1];
    return {
      name: "MultiMovies Byse [1080p]",
      title: "Byse 1080p\nHindi · Multi Audio",
      url: m3u8Url,
      quality: "1080p",
      languages: ["Hindi", "English"],
      behaviorHints: {
        proxyHeaders: {
          request: {
            "User-Agent": DEFAULT_UA,
            "Referer": "https://streamruby.net/",
          },
        },
      },
    };
  } catch (e) {
    return null;
  }
}

// --- ToonStream Scraper ---
async function scrapeToonStream(title, isMovie = false, season = 1, episode = 1) {
  const streams = [];
  try {
    const searchUrl = `https://tooniboy.xyz/search/all?q=${encodeURIComponent(title)}`;
    const res = await edgeFetch(searchUrl, {
      headers: {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://tooniboy.xyz/"
      },
      ttl: 600
    });
    if (!res.ok) return [];
    const json = await res.json();
    const items = json.data || [];
    if (!items.length) return [];

    let target = null;
    const cleanTitle = title.toLowerCase().trim();
    for (const item of items) {
      if (item.title && item.title.toLowerCase().trim() === cleanTitle) {
        target = item.url;
        break;
      }
    }
    if (!target) {
      for (const item of items) {
        if (item.title && item.title.toLowerCase().includes(cleanTitle)) {
          target = item.url;
          break;
        }
      }
    }
    if (!target && items.length) target = items[0].url;
    if (!target) return [];

    let epUrl = target.startsWith("http") ? target : `https://tooniboy.xyz${target}`;
    if (!isMovie && season && episode) {
      const slug = epUrl.replace(/\/+$/, "").split("/").pop();
      epUrl = `https://tooniboy.xyz/episode/${slug}-${season}x${episode}/`;
    }

    const epRes = await edgeFetch(epUrl, {
      headers: { "Referer": "https://tooniboy.xyz/" },
      ttl: 300
    });
    if (!epRes.ok) return [];
    const epHtml = await epRes.text();

    const iframes = [
      ...epHtml.matchAll(/<iframe[^>]+src="([^"]+)"/gi),
      ...epHtml.matchAll(/data-(?:url|embed|src)="([^"]+)"/gi)
    ].map(m => m[1].replace(/&amp;/g, "&").trim()).filter(u => u.startsWith("http"));

    const resolveTasks = iframes.map(async (u) => {
      try {
        if (u.includes("abyssplayer.com") || u.includes("player.abyssplayer.com")) {
          const abyssStreams = await resolveAbyss(u);
          for (const s of abyssStreams) {
            streams.push({ ...s, provider: "ToonStream" });
          }
        }
      } catch (err) {}
    });

    await Promise.all(resolveTasks);
  } catch (e) {
    console.error("ToonStream edge error:", e);
  }
  return streams;
}

// --- Abyss Player Resolver ---
async function resolveAbyss(embedUrl) {
  const streams = [];
  try {
    const res = await edgeFetch(embedUrl, {
      headers: {
        "User-Agent": DEFAULT_UA,
        "Referer": "https://playhydrax.com/",
      },
      ttl: 600,
    });
    if (!res.ok) return [];
    const html = await res.text();

    const m3u8Match = html.match(/(https?:\/\/[^\s"']+\.m3u8[^\s"']*)/i);
    if (m3u8Match) {
      return [{
        name: "ToonStream Abyss [1080p]",
        title: "Abyss Direct HLS 1080p\nHindi · Multi Audio",
        url: m3u8Match[1],
        quality: "1080p",
        languages: ["Hindi", "English"],
        behaviorHints: { proxyHeaders: { request: { Referer: "https://abyssplayer.com/" } } },
      }];
    }

    const datasMatch = html.match(/const\s+datas\s*=\s*["']([^"']+)["']/i);
    if (datasMatch) {
      const decRes = await edgeFetch("https://enc-dec.app/api/dec-abyss", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Referer": "https://playhydrax.com/",
        },
        body: JSON.stringify({ text: datasMatch[1] }),
        ttl: 600,
      });

      if (decRes.ok) {
        const json = await decRes.json();
        const sources = (json.result && json.result.sources) || [];
        for (const item of sources) {
          if (item.status === false) continue;
          const q = item.type || item.quality || "720p";
          const u = item.url || item.file;
          if (u && u.startsWith("http")) {
            streams.push({
              name: `ToonStream Abyss [${q}]`,
              title: `Abyss ${q}\nHindi · Multi Audio`,
              url: u,
              quality: q,
              size: item.size || 0,
              languages: ["Hindi", "English"],
              behaviorHints: {
                notWebReady: false,
                proxyHeaders: {
                  request: {
                    "User-Agent": DEFAULT_UA,
                    "Referer": "https://abyssplayer.com/",
                  },
                },
              },
            });
          }
        }
      }
    }
  } catch (e) {
    console.error("Abyss resolve error:", e);
  }
  return streams;
}

// --- Stream Handler ---
async function handleStream(configStr, contentType, contentId, url) {
  const config = parseConfig(configStr);
  const cacheKey = `${contentType}:${contentId}:${configStr}`;
  const cached = STREAM_CACHE.get(cacheKey);
  if (cached && Date.now() - cached.ts < CACHE_TTL_MS) {
    return new Response(JSON.stringify({ streams: cached.streams }), {
      headers: corsHeaders({ "Cache-Control": "public, max-age=600, stale-while-revalidate=300" })
    });
  }

  let season = 1, episode = 1, queryOrSlug = contentId;
  const isMovie = contentType === "movie";

  if (contentId.startsWith("hd:") && !contentId.startsWith("hd:tmdb:")) {
    const parts = contentId.split(":");
    if (parts.length >= 3 && !isNaN(parts[parts.length - 2]) && !isNaN(parts[parts.length - 1])) {
      season = parseInt(parts[parts.length - 2]);
      episode = parseInt(parts[parts.length - 1]);
      queryOrSlug = parts.slice(2, parts.length - 2).join(":").replace(/~/g, "/");
    } else {
      queryOrSlug = parts.slice(2).join(":").replace(/~/g, "/");
    }
  } else {
    const parts = contentId.split(":");
    if (parts.length >= 3 && !isNaN(parts[parts.length - 2]) && !isNaN(parts[parts.length - 1])) {
      season = parseInt(parts[parts.length - 2]);
      episode = parseInt(parts[parts.length - 1]);
      const baseId = parts.slice(0, parts.length - 2).join(":");
      queryOrSlug = await getTmdbTitle(baseId, contentType) || baseId;
    } else if (contentId.startsWith("tmdb:") || contentId.startsWith("tt") || !isNaN(contentId)) {
      queryOrSlug = await getTmdbTitle(contentId, contentType) || contentId;
    }
  }

  // Parallel edge scraping
  const [mmStreams, tsStreams] = await Promise.all([
    scrapeMultiMovies(queryOrSlug, isMovie, season, episode),
    scrapeToonStream(queryOrSlug, isMovie, season, episode),
  ]);

  let allStreams = [...mmStreams, ...tsStreams];

  // Filtering by Quality
  const filterQ = config.filter_qualities;
  if (filterQ && filterQ !== "all") {
    const allowed = filterQ.toLowerCase().split(",").map(s => s.trim());
    allStreams = allStreams.filter(s => {
      const q = (s.quality || "").toLowerCase();
      return !q || allowed.includes(q);
    });
  }

  // Sorting
  const sortBy = config.sort_by || "quality_desc";
  const qRank = { "4k": 6, "2160p": 6, "1440p": 5, "1080p": 4, "720p": 3, "480p": 2, "360p": 1, "": 0 };

  if (sortBy === "quality_asc") {
    allStreams.sort((a, b) => (qRank[(a.quality || "").toLowerCase()] || 0) - (qRank[(b.quality || "").toLowerCase()] || 0));
  } else if (sortBy === "provider") {
    allStreams.sort((a, b) => (a.provider || "").localeCompare(b.provider || ""));
  } else {
    allStreams.sort((a, b) => (qRank[(b.quality || "").toLowerCase()] || 0) - (qRank[(a.quality || "").toLowerCase()] || 0));
  }

  // Deduplicate streams
  const seen = new Set();
  const finalStreams = [];
  for (const s of allStreams) {
    if (!s.url || seen.has(s.url)) continue;
    seen.add(s.url);
    finalStreams.push({
      name: `AniBox Edge · ${s.provider || "Fast"} [${s.quality || "HD"}]`,
      title: s.title || `${s.name || "Stream"}\nHindi · Multi Audio`,
      url: s.url,
      behaviorHints: s.behaviorHints || {},
    });
  }

  STREAM_CACHE.set(cacheKey, { ts: Date.now(), streams: finalStreams });

  return new Response(JSON.stringify({ streams: finalStreams }), {
    headers: corsHeaders({ "Cache-Control": "public, max-age=600, stale-while-revalidate=300" })
  });
}

// --- Configure / Web UI Handler ---
function handleConfigure(request) {
  const host = new URL(request.url).host;
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AniBox Edge — Fast Anime & Cartoon Addon</title>
  <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
  <style>
    body { background: #0c0f17; color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    .card { background: #161b26; border: 1px solid #232c3d; border-radius: 1rem; }
    .btn-gradient { background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%); }
    .btn-gradient:hover { filter: brightness(1.1); }
  </style>
</head>
<body class="min-h-screen flex items-center justify-center p-4">
  <div class="card max-w-xl w-full p-8 shadow-2xl">
    <div class="flex items-center space-x-4 mb-6">
      <div class="w-12 h-12 rounded-xl btn-gradient flex items-center justify-center text-white font-extrabold text-2xl shadow-lg">A</div>
      <div>
        <h1 class="text-2xl font-bold text-white tracking-tight">AniBox Edge</h1>
        <p class="text-xs text-indigo-400 font-medium">Cloudflare Global Edge Network · 300+ Locations</p>
      </div>
    </div>

    <div class="space-y-4 mb-6 text-sm">
      <div class="p-4 bg-gray-900 bg-opacity-50 rounded-lg border border-gray-800">
        <label class="block font-semibold text-gray-300 mb-1">Quality Sorting</label>
        <select id="sort_by" class="w-full bg-gray-800 border border-gray-700 rounded-md p-2 text-white">
          <option value="quality_desc">Highest Quality First (4K / 1080p → 720p)</option>
          <option value="quality_asc">Lowest Quality First (Data Saver)</option>
          <option value="provider">Group by Provider</option>
        </select>
      </div>

      <div class="p-4 bg-gray-900 bg-opacity-50 rounded-lg border border-gray-800">
        <label class="block font-semibold text-gray-300 mb-1">Quality Filter</label>
        <select id="filter_q" class="w-full bg-gray-800 border border-gray-700 rounded-md p-2 text-white">
          <option value="all">All Qualities (4K, 1080p, 720p, 480p)</option>
          <option value="1080p,720p">1080p & 720p Only</option>
          <option value="1080p">1080p Only</option>
          <option value="720p">720p Only</option>
        </select>
      </div>
    </div>

    <div class="space-y-3">
      <a id="install_btn" href="stremio://${host}/manifest.json" class="btn-gradient w-full py-3.5 px-4 rounded-xl font-bold text-center block text-white shadow-lg transition">
        Install Addon to Stremio
      </a>
      <button onclick="copyManifest()" class="w-full py-3 px-4 rounded-xl font-semibold bg-gray-800 hover:bg-gray-700 border border-gray-700 text-gray-200 transition">
        Copy Manifest Link
      </button>
      <a id="web_btn" href="https://web.stremio.com/#/addons?addon=${encodeURIComponent(`https://${host}/manifest.json`)}" target="_blank" class="w-full py-2.5 px-4 rounded-xl font-medium text-center block text-xs text-gray-400 hover:text-white transition">
        Open in Stremio Web
      </a>
    </div>

    <p id="copied_msg" class="text-center text-xs text-green-400 mt-3 hidden">Manifest link copied to clipboard!</p>
  </div>

  <script>
    function updateLinks() {
      const sort = document.getElementById('sort_by').value;
      const q = document.getElementById('filter_q').value;
      const cfg = { sort_by: sort, filter_qualities: q };
      const b64 = btoa(JSON.stringify(cfg)).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');
      const base = window.location.host;
      const manifestUrl = 'https://' + base + '/' + b64 + '/manifest.json';
      document.getElementById('install_btn').href = 'stremio://' + base + '/' + b64 + '/manifest.json';
      document.getElementById('web_btn').href = 'https://web.stremio.com/#/addons?addon=' + encodeURIComponent(manifestUrl);
      window.currentManifest = manifestUrl;
    }

    document.getElementById('sort_by').addEventListener('change', updateLinks);
    document.getElementById('filter_q').addEventListener('change', updateLinks);
    window.currentManifest = 'https://${host}/manifest.json';

    function copyManifest() {
      navigator.clipboard.writeText(window.currentManifest || 'https://${host}/manifest.json');
      const msg = document.getElementById('copied_msg');
      msg.classList.remove('hidden');
      setTimeout(() => msg.classList.add('hidden'), 2500);
    }
  </script>
</body>
</html>`;

  return new Response(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    }
  });
}

// --- Main Request Handler ---
async function handleRequest(request) {
  const url = new URL(request.url);
  const path = url.pathname;

  if (request.method === "OPTIONS") {
    return new Response(null, { headers: corsHeaders() });
  }

  const rawSegments = path.split("/").filter(Boolean);
  if (rawSegments.length === 0 || path === "/" || path === "/configure") {
    return handleConfigure(request);
  }

  const last = rawSegments[rawSegments.length - 1];
  if (last === "manifest.json") {
    const configStr = rawSegments.length > 1 ? rawSegments[0] : "";
    return new Response(JSON.stringify(MANIFEST), {
      headers: corsHeaders({ "Cache-Control": "public, max-age=3600, stale-while-revalidate=1800" })
    });
  }

  // Find index of known resources: "catalog", "meta", "stream"
  const resIdx = rawSegments.findIndex(s => ["catalog", "meta", "stream"].includes(s));
  if (resIdx !== -1) {
    const configStr = resIdx > 0 ? rawSegments[0] : "";
    const resource = rawSegments[resIdx];
    const type = rawSegments[resIdx + 1] || "";
    let id = rawSegments[resIdx + 2] || "";
    let extra = rawSegments.slice(resIdx + 3).join("/");

    if (extra.endsWith(".json")) {
      extra = extra.slice(0, -5);
    } else if (id.endsWith(".json")) {
      id = id.slice(0, -5);
    }

    id = decodeURIComponent(id);
    extra = decodeURIComponent(extra);

    if (resource === "catalog") {
      return handleCatalog(configStr, type, id, extra, url);
    } else if (resource === "meta") {
      return handleMeta(configStr, type, id, url);
    } else if (resource === "stream") {
      return handleStream(configStr, type, id, url);
    }
  }

  return new Response(JSON.stringify({ status: "AniBox Edge Worker Online" }), {
    headers: corsHeaders(),
  });
}

// Cloudflare Workers entrypoint
export default {
  async fetch(request, env, ctx) {
    return handleRequest(request);
  },
};

// Node.js local runner for local benchmarking and testing
export { handleRequest };
