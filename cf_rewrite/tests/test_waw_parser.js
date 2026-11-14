import { resolveAbyss } from '../src/players/abyss.js';
import { fetchText } from '../src/utils/http.js';

async function testWawParser() {
  const seriesUrl = 'https://watchanimeworld.top/series/solo-leveling';
  const html = await fetchText(seriesUrl);
  
  // Find episode link for season 1 ep 1
  const s = 1, e = 1;
  const epRegex = new RegExp(`href="([^"]*(?:episode|series)[^"]*(?:${s}x0?${e}|season-0?${s}-episode-0?${e}|s0?${s}-?e0?${e})[^"]*)"`, 'i');
  let epMatch = html.match(epRegex);
  if (!epMatch) {
    // Try generic episode match
    const allEps = [...html.matchAll(/href="([^"]*(?:\/episode\/|\/episodes\/)[^"]*)"/gi)].map(m => m[1]);
    console.log('All eps sample:', allEps.slice(0, 5));
    epMatch = allEps.find(u => u.includes(`${s}x${e}`) || u.includes(`-${e}/`));
    if (epMatch) epMatch = [null, epMatch];
  }

  console.log('Matched ep URL:', epMatch ? epMatch[1] : 'None');
  if (epMatch) {
    const epHtml = await fetchText(epMatch[1]);
    const dubMatch = epHtml.match(/src="([^"]*dub-player[^"]*)"/i);
    console.log('Dub player match:', dubMatch ? dubMatch[1] : 'None');
    if (dubMatch) {
      const dubUrl = dubMatch[1].startsWith('http') ? dubMatch[1] : `https://watchanimeworld.one${dubMatch[1]}`;
      const dubHtml = await fetchText(dubUrl);
      const cfgMatch = dubHtml.match(/CONFIG\s*=\s*(\{[\s\S]*?\});/);
      if (cfgMatch) {
        const config = JSON.parse(cfgMatch[1]);
        console.log('Found config ready:', config.ready);
        for (const [lang, id] of Object.entries(config.ready)) {
          const lName = config.lang?.[lang]?.name || lang;
          const abyssUrl = `${config.prefix || 'https://player.abyssplayer.com/'}${id}`;
          console.log(`Resolving ${lName}: ${abyssUrl}`);
          const res = await resolveAbyss(abyssUrl, `AnimeWorld ${lName}`);
          console.log(` -> ${res.length} streams for ${lName}`);
        }
      }
    }
  }
}
testWawParser();
