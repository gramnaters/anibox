import { searchMultiMovies, getMultiMoviesStreams } from '../src/providers/multimovies.js';

async function testMmTitles() {
  const titles = ['Naruto', 'Avengers Endgame', 'Avatar The Way of Water'];
  for (const t of titles) {
    console.log(`\nSearching MM: ${t}`);
    const search = await searchMultiMovies(t);
    if (search.length) {
      console.log(`Found: ${search[0].title} (${search[0].slug})`);
      const isMovie = search[0].type === 'movie';
      const streams = await getMultiMoviesStreams(search[0].slug, isMovie, 1, 1);
      console.log(`Streams: ${streams.length}`);
      streams.forEach(s => console.log(`  * ${s.name} [${s.quality}] -> ${s.url.substring(0, 70)}`));
    }
  }
}
testMmTitles();
