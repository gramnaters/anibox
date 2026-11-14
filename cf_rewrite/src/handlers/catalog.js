/**
 * Multi-Provider Catalog Handler.
 */

import { corsHeaders } from "../utils/http.js";
import { discoverAnimeSeries, discoverAnimeMovies, discoverHindiDubAnime, searchContent, GENRE_MAP } from "../utils/tmdb.js";
import { PROVIDERS } from "../providers/index.js";

export async function handleCatalog(config, catalogType, catalogId, extra, url) {
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

  // 1. Check if catalogId is a Provider-specific catalog (e.g. multimovies_series, toonstream_series, etc.)
  for (const pKey of Object.keys(PROVIDERS)) {
    for (const suffix of ["_series", "_movies", "_movie"]) {
      if (catalogId === `${pKey}${suffix}`) {
        const prov = PROVIDERS[pKey];
        try {
          let items = [];
          if (searchQuery && prov.search) {
            items = await prov.search(searchQuery);
          } else if (prov.getCatalog) {
            items = await prov.getCatalog();
          }

          const wantType = suffix.includes("movie") ? "movie" : "series";
          const filtered = items.filter(it => it.type === wantType || (!it.type && wantType === "series"));

          metas = filtered.map(it => ({
            id: `hd:${pKey}:${(it.slug || it.title).replace(/\//g, "~")}`,
            type: wantType,
            name: it.title,
            poster: it.poster || "",
            posterShape: "poster",
            description: `${prov.name} catalog item`
          }));

          if (skip) {
            metas = metas.slice(skip, skip + 50);
          }
          return new Response(JSON.stringify({ metas }), {
            headers: corsHeaders({ "Cache-Control": "public, max-age=3600, stale-while-revalidate=1800" })
          });
        } catch (e) {
          console.error(`Catalog error for ${catalogId}:`, e);
          return new Response(JSON.stringify({ metas: [] }), { headers: corsHeaders() });
        }
      }
    }
  }

  // 2. Generic TMDB Catalogs (Trending Anime, Movies, Hindi Dubs)
  try {
    if (searchQuery) {
      const results = await searchContent(searchQuery, isMovie ? "movie" : "series", page);
      metas = results.map(item => ({
        id: `hd:tmdb:${item.id}`,
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
    } else {
      let results = [];
      if (catalogId === "anibox_popular_movies") {
        results = await discoverAnimeMovies(page);
      } else if (catalogId === "anibox_hindi_series") {
        results = await discoverHindiDubAnime(page);
      } else {
        results = await discoverAnimeSeries(page);
      }

      metas = results.map(item => ({
        id: `hd:tmdb:${item.id}`,
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
  } catch (err) {
    console.error("TMDB catalog error:", err);
  }

  return new Response(JSON.stringify({ metas }), {
    headers: corsHeaders({ "Cache-Control": "public, max-age=3600, stale-while-revalidate=1800" })
  });
}
