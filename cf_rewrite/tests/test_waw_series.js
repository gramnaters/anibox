import { searchWatchAnimeWorld } from '../src/providers/watchanimeworld.js';
import { fetchText } from '../src/utils/http.js';

async function testWawSeries() {
  const search = await searchWatchAnimeWorld('Solo Leveling');
  console.log('Search Solo Leveling:', search);
  if (search.length) {
    const url = search[0].url;
    console.log('Series page:', url);
    const html = await fetchText(url);
    // Find episodes list
    const eps = [...html.matchAll(/<a[^>]+href="([^"]*(?:series|episode)\/[^"]*)"[^>]*>([\s\S]*?)<\/a>/gi)];
    console.log('Episodes found:', eps.slice(0, 5).map(m => m[1]));
    
    // Check first episode page
    if (eps.length) {
      const epUrl = eps[0][1];
      console.log('Fetching episode 1:', epUrl);
      const epHtml = await fetchText(epUrl);
      const iframes = [
        ...epHtml.matchAll(/<iframe[^>]+src="([^"]+)"/gi),
        ...epHtml.matchAll(/data-(?:url|embed|src)="([^"]+)"/gi)
      ].map(m => m[1]);
      console.log('Episode iframes:', iframes);
    }
  }
}
testWawSeries();
