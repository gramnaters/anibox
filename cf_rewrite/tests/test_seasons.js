import { fetchText } from '../src/utils/http.js';

async function checkSeasons() {
  const html = await fetchText('https://watchanimeworld.top/series/solo-leveling');
  const seasons = [...html.matchAll(/season/gi)];
  console.log('Season mentions:', seasons.length);
  const seasonTabs = [...html.matchAll(/class="[^"]*season[^"]*"[^>]*>([\s\S]*?)<\/[a-z]+>/gi)];
  console.log('Season tabs:', seasonTabs.map(m => m[0].substring(0, 100)));
}
checkSeasons();
