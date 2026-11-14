import { searchMultiMovies, getMultiMoviesStreams } from '../src/providers/multimovies.js';

async function testMm() {
  console.log('Testing MultiMovies search...');
  const search = await searchMultiMovies('Dragon Ball GT');
  console.log('Search res:', search);
  if (search.length) {
    const streams = await getMultiMoviesStreams(search[0].slug, false, 1, 1);
    console.log(`Found ${streams.length} MultiMovies streams:`);
    streams.forEach(s => console.log(` - ${s.name} [${s.quality}] -> ${s.url.substring(0, 70)}...`));
  }
}
testMm();
