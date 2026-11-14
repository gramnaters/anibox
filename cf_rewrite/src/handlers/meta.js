/**
 * Metadata Handler.
 */

import { corsHeaders } from "../utils/http.js";
import { getDetails, getSeasonEpisodes, resolveTitleAndTmdbId } from "../utils/tmdb.js";

export async function handleMeta(config, metaType, contentId, url) {
  const isMovie = metaType === "movie";
  const { tmdbId, title } = await resolveTitleAndTmdbId(contentId, isMovie ? "movie" : "series");

  if (!tmdbId) {
    return new Response(JSON.stringify({ meta: {} }), { headers: corsHeaders() });
  }

  try {
    const data = await getDetails(tmdbId, isMovie ? "movie" : "series");
    if (!data) {
      return new Response(JSON.stringify({ meta: {} }), { headers: corsHeaders() });
    }

    const meta = {
      id: contentId,
      type: isMovie ? "movie" : "series",
      name: data.name || data.title || data.original_name || data.original_title || title,
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

    // Series: gather seasons & episode thumbnails
    const seasons = (data.seasons || []).filter(s => s.season_number > 0).slice(0, 8);
    const seasonTasks = seasons.map(s => getSeasonEpisodes(tmdbId, s.season_number));
    const seasonResults = await Promise.allSettled(seasonTasks);

    const videos = [];
    for (const r of seasonResults) {
      if (r.status === "fulfilled" && Array.isArray(r.value)) {
        for (const ep of r.value) {
          videos.push({
            id: `${contentId}:${ep.season}:${ep.episode}`,
            title: ep.title,
            season: ep.season,
            episode: ep.episode,
            thumbnail: ep.thumbnail || meta.poster || "",
            overview: ep.overview || "",
            released: ep.released || ""
          });
        }
      }
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
  } catch (err) {
    console.error("Meta error:", err);
    return new Response(JSON.stringify({ meta: {} }), { headers: corsHeaders() });
  }
}
