import { fetchText } from '../src/utils/http.js';

async function listEps() {
  const html = await fetchText('https://watchanimeworld.top/series/solo-leveling');
  const allEps = [...html.matchAll(/href="([^"]*(?:\/episode\/|\/episodes\/)[^"]*)"/gi)].map(m => m[1]);
  console.log('All 14 eps:', allEps);
}
listEps();
