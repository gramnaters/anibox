import { searchWatchAnimeWorld, getWatchAnimeWorldStreams } from '../src/providers/watchanimeworld.js';

async function testWaw() {
  console.log('Testing WatchAnimeWorld...');
  const search = await searchWatchAnimeWorld('Demon Slayer');
  console.log('Search Demon Slayer:', search);
  if (search.length) {
    const streams = await getWatchAnimeWorldStreams(search[0].slug, false, 1, 1);
    console.log('Demon Slayer S01E01 Streams:', streams);
  }
}
testWaw();
