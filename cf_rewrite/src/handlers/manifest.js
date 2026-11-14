/**
 * Stremio Manifest Builder.
 */

export const BASE_MANIFEST = {
  id: "community.anibox",
  version: "2.2.0",
  name: "AniBox",
  description: "Stream movies, anime, and cartoons from MultiMovies, ToonStream, AnimeWorld, and PirateXPlay with direct edge CDN speed.",
  logo: "https://raw.githubusercontent.com/stremio/stremio-addon-sdk/master/docs/logo.png",
  background: "https://image.tmdb.org/t/p/original/xLoQu249IIlQtFsFgF6VZhMYWfz.jpg",
  resources: [
    { name: "catalog", types: ["series", "movie", "anime"] },
    { name: "meta", types: ["series", "movie", "anime"], idPrefixes: ["tt", "tmdb:", "hd:tmdb:", "hd:"] },
    { name: "stream", types: ["series", "movie", "anime"], idPrefixes: ["tt", "tmdb:", "hd:tmdb:", "hd:"] }
  ],
  types: ["series", "movie", "anime"],
  idPrefixes: ["tt", "tmdb:", "hd:tmdb:", "hd:"],
  catalogs: [
    {
      type: "series",
      id: "anibox_trending_series",
      name: "AniBox · Popular Anime Series",
      extra: [{ name: "search", isRequired: false }, { name: "skip", isRequired: false }]
    },
    {
      type: "movie",
      id: "anibox_popular_movies",
      name: "AniBox · Anime & Cartoon Movies",
      extra: [{ name: "search", isRequired: false }, { name: "skip", isRequired: false }]
    },
    {
      type: "series",
      id: "anibox_hindi_series",
      name: "AniBox · Hindi Dub Anime",
      extra: [{ name: "search", isRequired: false }, { name: "skip", isRequired: false }]
    },
    {
      type: "series",
      id: "multimovies_series",
      name: "MultiMovies · Series",
      extra: [{ name: "search", isRequired: false }, { name: "skip", isRequired: false }]
    },
    {
      type: "movie",
      id: "multimovies_movies",
      name: "MultiMovies · Movies",
      extra: [{ name: "search", isRequired: false }, { name: "skip", isRequired: false }]
    },
    {
      type: "series",
      id: "toonstream_series",
      name: "ToonStream · Series",
      extra: [{ name: "search", isRequired: false }, { name: "skip", isRequired: false }]
    },
    {
      type: "movie",
      id: "toonstream_movies",
      name: "ToonStream · Movies",
      extra: [{ name: "search", isRequired: false }, { name: "skip", isRequired: false }]
    },
    {
      type: "series",
      id: "watchanimeworld_series",
      name: "AnimeWorld · Hindi Series",
      extra: [{ name: "search", isRequired: false }, { name: "skip", isRequired: false }]
    },
    {
      type: "series",
      id: "piratexplay_series",
      name: "PirateXPlay · Anime Series",
      extra: [{ name: "search", isRequired: false }, { name: "skip", isRequired: false }]
    }
  ],
  behaviorHints: {
    configurable: true,
    configurationRequired: false
  }
};

export function makeManifest(config = {}) {
  const m = { ...BASE_MANIFEST };
  if (config && Object.keys(config).length > 0) {
    const hash = Math.abs(JSON.stringify(config).split("").reduce((a, b) => { a = ((a << 5) - a) + b.charCodeAt(0); return a & a; }, 0));
    m.id = `community.anibox.${hash % 10000}`;
  }
  return m;
}
