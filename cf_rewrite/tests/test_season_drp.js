import { fetchText } from '../src/utils/http.js';

async function checkSeasonDrp() {
  const html = await fetchText('https://watchanimeworld.top/series/solo-leveling');
  const idx = html.indexOf('choose-season');
  if (idx !== -1) {
    console.log(html.substring(idx - 50, idx + 800));
  }
}
checkSeasonDrp();
