import { resolveAbyss } from '../src/players/abyss.js';

async function testSoloS01E01() {
  const streams = await resolveAbyss('https://player.abyssplayer.com/S8ZofkQ9_', 'AnimeWorld Hindi');
  console.log(`Found ${streams.length} streams for Solo Leveling S01E01 Hindi:`);
  streams.forEach(s => console.log(s.name, s.quality, s.url));
}
testSoloS01E01();
