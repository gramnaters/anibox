/**
 * Universal Provider Aggregator.
 */

import { resolveDirectTmdbStreams } from "./direct_tmdb.js";
import { getMultiMoviesStreams, searchMultiMovies, getHomeCatalogMultiMovies } from "./multimovies.js";
import { getToonStreamStreams, searchToonStream, getHomeCatalogToonStream } from "./toonstream.js";
import { getWatchAnimeWorldStreams, searchWatchAnimeWorld, getHomeCatalogWatchAnimeWorld } from "./watchanimeworld.js";
import { getPirateXPlayStreams, searchPirateXPlay, getHomeCatalogPirateXPlay } from "./piratexplay.js";

export const PROVIDERS = {
  multimovies: {
    name: "MultiMovies",
    getStreams: getMultiMoviesStreams,
    search: searchMultiMovies,
    getCatalog: getHomeCatalogMultiMovies
  },
  toonstream: {
    name: "ToonStream",
    getStreams: getToonStreamStreams,
    search: searchToonStream,
    getCatalog: getHomeCatalogToonStream
  },
  watchanimeworld: {
    name: "AnimeWorld",
    getStreams: getWatchAnimeWorldStreams,
    search: searchWatchAnimeWorld,
    getCatalog: getHomeCatalogWatchAnimeWorld
  },
  piratexplay: {
    name: "PirateXPlay",
    getStreams: getPirateXPlayStreams,
    search: searchPirateXPlay,
    getCatalog: getHomeCatalogPirateXPlay
  }
};

export async function aggregateStreams(params) {
  const { tmdbId, imdbId, query, isMovie, season = 1, episode = 1, enabledProviders = [] } = params;
  const streams = [];

  // 1. Direct TMDB & IMDb O(1) Fast-Track
  let directTasks = [];
  if (tmdbId) {
    directTasks.push(resolveDirectTmdbStreams(tmdbId, isMovie, season, episode));
  } else if (imdbId) {
    directTasks.push(resolveDirectTmdbStreams(imdbId, isMovie, season, episode));
  }

  // 2. Active Provider Scrapers
  const providerTasks = [];
  const providersToRun = enabledProviders.length > 0
    ? enabledProviders.filter(p => PROVIDERS[p])
    : Object.keys(PROVIDERS);

  for (const pKey of providersToRun) {
    const prov = PROVIDERS[pKey];
    if (prov && prov.getStreams) {
      providerTasks.push(prov.getStreams(query, isMovie, season, episode));
    }
  }

  const allSettled = await Promise.allSettled([...directTasks, ...providerTasks]);
  for (const s of allSettled) {
    if (s.status === "fulfilled" && Array.isArray(s.value)) {
      streams.push(...s.value);
    }
  }

  return streams;
}
