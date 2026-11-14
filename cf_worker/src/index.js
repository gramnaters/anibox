/**
 * AniBox Edge - Cloudflare Workers Addon & Scraper
 * Runs at 300+ edge locations worldwide for instant (<50ms) scraping and streaming.
 */

const TMDB_API_KEY = "45873911f9f257a419eb94c502b28c50";
const DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36";

const MANIFEST = {
  id: "community.anibox.edge",
  version: "1.0.0",
  name: "AniBox Edge",
  description: "Ultra-fast edge-powered anime & cartoon scraper with Hindi & multi-audio dubs.",
  resources: ["stream", "catalog"],
  types: ["movie", "series", "anime"],
  catalogs: [
    {
      type: "anime",
      id: "anibox_edge_catalog",
      name: "AniBox Edge Trending",
      extra: [{ name: "search", isRequired: false }]
    }
  ],
  idPrefixes: ["tt", "tmdb:", "hd:"]
};

// --- Helper Functions ---
function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    "Content-Type": "application/json; charset=utf-8",
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
  return fetch(url, {
    ...options,
    headers,
    cf: {
      cacheTtl: options.ttl || 300,
      cacheEverything: true,
    },
  });
}

// --- TMDB Metadata Resolver ---
async function getTmdbTitle(contentId, type = "movie") {
  let tmdbId = contentId;
  if (contentId.startsWith("tmdb:")) tmdbId = contentId.replace("tmdb:", "");
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

  const endpoint = type === "series" ? `tv/${tmdbId}` : `movie/${tmdbId}`;
  const res = await edgeFetch(
    `https://api.themoviedb.org/3/${endpoint}?api_key=${TMDB_API_KEY}`,
    { ttl: 86400 }
  );
  if (!res.ok) return null;
  const json = await res.json();
  return json.name || json.title || json.original_name || json.original_title || null;
}

// --- MultiMovies Scraper ---
async function scrapeMultiMovies(title, season, episode) {
  const streams = [];
  try {
    const searchUrl = `https://m1.multimovies.courses/?s=${encodeURIComponent(title)}`;
    const res = await edgeFetch(searchUrl, { ttl: 600 });
    if (!res.ok) return [];
    const html = await res.text();

    const postMatches = [...html.matchAll(/<article[^>]*class="[^"]*item-movies[^"]*"[^>]*>[\s\S]*?<a href="([^"]+)"[^>]*>[\s\S]*?alt="([^"]+)"/gi)];
    let targetUrl = null;
    for (const match of postMatches) {
      const pUrl = match[1];
      const pTitle = match[2];
      if (pTitle.toLowerCase().includes(title.toLowerCase())) {
        targetUrl = pUrl;
        break;
      }
    }
    if (!targetUrl && postMatches.length > 0) targetUrl = postMatches[0][1];
    if (!targetUrl) return [];

    let pageUrl = targetUrl;
    if (season && episode) {
      pageUrl = targetUrl.replace(/\/$/, "") + `-season-${season}-episode-${episode}/`;
    }

    const pageRes = await edgeFetch(pageUrl, { ttl: 300 });
    if (!pageRes.ok) return [];
    const pageHtml = await pageRes.text();

    const iframes = [...pageHtml.matchAll(/<iframe[^>]+src="([^"]+)"/gi)].map(m => m[1]);
    for (let u of iframes) {
      if (u.startsWith("//")) u = "https:" + u;
      if (u.includes("bysetayico.com") || u.includes("byse")) {
        const resolved = await resolveByse(u);
        if (resolved) streams.push({ ...resolved, provider: "MultiMovies" });
      } else if (u.includes("vidmmo.com") || u.includes(".m3u8")) {
        streams.push({
          title: "MultiMovies / Direct M3U8",
          name: "MultiMovies",
          url: u,
          quality: "1080p",
          languages: ["Hindi", "English"],
          behaviorHints: { proxyHeaders: { request: { Referer: "https://m1.multimovies.courses/" } } },
          provider: "MultiMovies",
        });
      }
    }
  } catch (e) {
    console.error("MultiMovies edge error:", e);
  }
  return streams;
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
      title: "MultiMovies / Byse [1080p]",
      name: "Byse 1080p",
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
async function scrapeToonStream(title, season, episode) {
  const streams = [];
  try {
    const searchUrl = `https://toonstream.us/?s=${encodeURIComponent(title)}`;
    const res = await edgeFetch(searchUrl, { ttl: 600 });
    if (!res.ok) return [];
    const html = await res.text();

    const links = [...html.matchAll(/<a\s+href="([^"]+)"[^>]*rel="bookmark"[^>]*>([^<]+)<\/a>/gi)];
    let target = null;
    for (const l of links) {
      if (l[2].toLowerCase().includes(title.toLowerCase())) {
        target = l[1];
        break;
      }
    }
    if (!target && links.length) target = links[0][1];
    if (!target) return [];

    let epUrl = target;
    if (season && episode) {
      epUrl = target.replace(/\/$/, "") + `-season-${season}-episode-${episode}/`;
    }

    const epRes = await edgeFetch(epUrl, { ttl: 300 });
    if (!epRes.ok) return [];
    const epHtml = await epRes.text();

    const iframes = [...epHtml.matchAll(/<iframe[^>]+src="([^"]+)"/gi)].map(m => m[1]);
    for (let u of iframes) {
      if (u.startsWith("//")) u = "https:" + u;
      if (u.includes("abyssplayer.com") || u.includes("player.abyssplayer.com")) {
        const abyssStreams = await resolveAbyss(u);
        for (const s of abyssStreams) {
          streams.push({ ...s, provider: "ToonStream" });
        }
      }
    }
  } catch (e) {
    console.error("ToonStream edge error:", e);
  }
  return streams;
}

// --- Abyss Player Resolver ---
async function resolveAbyss(embedUrl) {
  const streams = [];
  try {
    const parts = embedUrl.split("/").filter(Boolean);
    const id = parts[parts.length - 1];
    if (!id) return [];

    const apiUrl = `https://player.abyssplayer.com/api/source/${id}`;
    const res = await edgeFetch(apiUrl, {
      method: "POST",
      headers: {
        "Referer": "https://abyssplayer.com/",
        "X-Requested-With": "XMLHttpRequest",
      },
      ttl: 600,
    });
    if (!res.ok) return [];
    const json = await res.json();
    if (!json.success || !Array.isArray(json.data)) return [];

    for (const item of json.data) {
      if (item.status === false) continue; // Skip unrendered / unplayable formats
      const q = item.label || item.quality || "720p";
      streams.push({
        title: `Abyss / ${q}`,
        name: `Abyss ${q}`,
        url: item.file,
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
  } catch (e) {
    console.error("Abyss resolve error:", e);
  }
  return streams;
}

// --- Main Request Router ---
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders() });
    }

    // 1. Manifest
    if (path === "/manifest.json" || path.endsWith("/manifest.json")) {
      return new Response(JSON.stringify(MANIFEST), { headers: corsHeaders() });
    }

    // 2. Stream Route: /stream/:type/:id.json or /:config/stream/:type/:id.json
    const streamMatch = path.match(/(?:\/([^\/]+))?\/stream\/([^\/]+)\/([^\/]+)\.json$/);
    if (streamMatch) {
      const configStr = streamMatch[1] && streamMatch[1] !== "stream" ? streamMatch[1] : "";
      const contentType = streamMatch[2];
      const contentId = decodeURIComponent(streamMatch[3]);
      const config = parseConfig(configStr);

      const parts = contentId.split(":");
      let season = null, episode = null, baseId = contentId;
      if (parts.length >= 3 && !isNaN(parts[parts.length - 2]) && !isNaN(parts[parts.length - 1])) {
        season = parseInt(parts[parts.length - 2]);
        episode = parseInt(parts[parts.length - 1]);
        baseId = parts.slice(0, parts.length - 2).join(":");
      }

      const title = await getTmdbTitle(baseId, contentType);
      if (!title) {
        return new Response(JSON.stringify({ streams: [] }), { headers: corsHeaders() });
      }

      // Parallel edge scraping
      const [mmStreams, tsStreams] = await Promise.all([
        scrapeMultiMovies(title, season, episode),
        scrapeToonStream(title, season, episode),
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
      const qRank = { "4k": 5, "2160p": 5, "1080p": 4, "720p": 3, "480p": 2, "360p": 1, "": 0 };

      if (sortBy === "quality_asc") {
        allStreams.sort((a, b) => (qRank[(a.quality || "").toLowerCase()] || 0) - (qRank[(b.quality || "").toLowerCase()] || 0));
      } else if (sortBy === "provider") {
        allStreams.sort((a, b) => (a.provider || "").localeCompare(b.provider || ""));
      } else {
        // Default quality_desc
        allStreams.sort((a, b) => (qRank[(b.quality || "").toLowerCase()] || 0) - (qRank[(a.quality || "").toLowerCase()] || 0));
      }

      // Deduplicate streams
      const seen = new Set();
      const finalStreams = [];
      for (const s of allStreams) {
        if (!s.url || seen.has(s.url)) continue;
        seen.add(s.url);
        finalStreams.push({
          title: `AniBox Edge · ${s.title || s.name}\n${(s.languages || []).join(" · ")}`,
          name: s.name || "AniBox Edge",
          url: s.url,
          behaviorHints: s.behaviorHints || {},
        });
      }

      return new Response(JSON.stringify({ streams: finalStreams }), { headers: corsHeaders() });
    }

    return new Response(JSON.stringify({ status: "AniBox Edge Worker Online" }), {
      headers: corsHeaders(),
    });
  },
};
