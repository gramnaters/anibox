import { resolveAbyss } from '../src/players/abyss.js';

async function testWawAbyss() {
  const streams = await resolveAbyss('https://player.abyssplayer.com/2kpi6P6mW', 'AnimeWorld Hindi');
  console.log('Resolved streams:', streams);
}
testWawAbyss();
