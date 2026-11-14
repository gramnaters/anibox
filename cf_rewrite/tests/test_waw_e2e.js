import { getWatchAnimeWorldStreams } from '../src/providers/watchanimeworld.js';

async function testWawStreams() {
  console.log('Resolving WatchAnimeWorld Solo Leveling S01E01...');
  const streams = await getWatchAnimeWorldStreams('Solo Leveling', false, 1, 1);
  console.log(`Found ${streams.length} streams from WatchAnimeWorld:`);
  streams.forEach(s => console.log(` - ${s.name} [${s.quality}] -> ${s.url.substring(0, 60)}...`));
}
testWawStreams();
