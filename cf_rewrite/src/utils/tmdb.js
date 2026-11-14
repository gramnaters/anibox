/**
 * TMDB API integration with Cloudflare edge caching.
 */

import { fetchJson } from "./http.js";

export const TMDB_API_KEY = "1b3113663c9004682ed61086cf967c44";
export const TMDB_BASE = "https://api.themoviedb.org/3";

export const GENRE_MAP = {
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

export async function findByImdb(imdbId) {
  if (!imdbId || !imdbId.startsWith("tt")) return null;
  const url = `${TMDB_BASE}/find/${imdbId}?api_key=${TMDB_API_KEY}&external_source=imdb_id`;
  const data = await fetchJson(url, { ttl: 86400 });
  if (!data) return null;

  const match = (data.tv_results || [])[0] || (data.movie_results || [])[0];
  if (!match) return null;

  return {
    id: String(match.id),
    name: match.name || match.title || match.original_name || match.original_title,
    type: match.media_type === "movie" || match.title ? "movie" : "series",
    poster: match.poster_path ? `https://image.tmdb.org/t/p/w500${match.poster_path}` : "",
    background: match.backdrop_path ? `https://image.tmdb.org/t/p/original${match.backdrop_path}` : "",
    overview: match.overview || "",
    year: (match.first_air_date || match.release_date || "").slice(0, 4)
  };
}

export async function getDetails(tmdbId, type = "series") {
  const endpoint = type === "movie" ? "movie" : "tv";
  const url = `${TMDB_BASE}/${endpoint}/${tmdbId}?api_key=${TMDB_API_KEY}&append_to_response=external_ids,seasons`;
  return await fetchJson(url, { ttl: 86400 });
}

export async function getSeasonEpisodes(tmdbId, seasonNum = 1) {
  const url = `${TMDB_BASE}/tv/${tmdbId}/season/${seasonNum}?api_key=${TMDB_API_KEY}`;
  const data = await fetchJson(url, { ttl: 86400 });
  if (!data || !data.episodes) return [];

  return data.episodes.map(ep => ({
    season: seasonNum,
    episode: ep.episode_number,
    title: ep.name || `Episode ${ep.episode_number}`,
    thumbnail: ep.still_path ? `https://image.tmdb.org/t/p/w500${ep.still_path}` : "",
    overview: (ep.overview || "").slice(0, 300),
    released: ep.air_date ? new Date(ep.air_date).toISOString() : ""
  }));
}

export async function searchContent(query, type = "series", page = 1) {
  const endpoint = type === "movie" ? "search/movie" : "search/tv";
  const url = `${TMDB_BASE}/${endpoint}?api_key=${TMDB_API_KEY}&query=${encodeURIComponent(query)}&page=${page}`;
  const data = await fetchJson(url, { ttl: 3600 });
  return (data && data.results) || [];
}

export async function discoverAnimeSeries(page = 1) {
  const url = `${TMDB_BASE}/discover/tv?api_key=${TMDB_API_KEY}&with_keywords=210024&sort_by=popularity.desc&page=${page}`;
  const data = await fetchJson(url, { ttl: 7200 });
  return (data && data.results) || [];
}

export async function discoverAnimeMovies(page = 1) {
  const url = `${TMDB_BASE}/discover/movie?api_key=${TMDB_API_KEY}&with_genres=16&sort_by=popularity.desc&page=${page}`;
  const data = await fetchJson(url, { ttl: 7200 });
  return (data && data.results) || [];
}

export async function discoverHindiDubAnime(page = 1) {
  const url = `${TMDB_BASE}/discover/tv?api_key=${TMDB_API_KEY}&with_keywords=210024&with_original_language=ja|hi|en&sort_by=vote_count.desc&page=${page}`;
  const data = await fetchJson(url, { ttl: 7200 });
  return (data && data.results) || [];
}

export async function resolveTitleAndTmdbId(contentId, type = "series") {
  let tmdbId = null;
  let title = null;

  if (contentId.startsWith("tmdb:")) {
    tmdbId = contentId.replace("tmdb:", "");
  } else if (contentId.startsWith("hd:tmdb:")) {
    tmdbId = contentId.replace("hd:tmdb:", "");
  } else if (contentId.startsWith("tt")) {
    const match = await findByImdb(contentId);
    if (match) {
      tmdbId = match.id;
      title = match.name;
    }
  } else if (contentId.startsWith("hd:")) {
    const slugName = contentId.split(":").slice(2).join(" ").replace(/[-_~]/g, " ");
    const results = await searchContent(slugName, type, 1);
    if (results.length > 0) {
      tmdbId = String(results[0].id);
      title = results[0].name || results[0].title;
    }
  } else if (!isNaN(contentId)) {
    tmdbId = contentId;
  }

  if (tmdbId && !title) {
    const details = await getDetails(tmdbId, type);
    if (details) {
      title = details.name || details.title || details.original_name || details.original_title;
    }
  }

  return { tmdbId, title: title || contentId };
}
