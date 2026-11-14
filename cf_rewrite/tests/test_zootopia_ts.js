import { searchToonStream, getToonStreamStreams } from '../src/providers/toonstream.js';
import { resolveEmbedUrl } from '../src/players/index.js';
import { fetchText } from '../src/utils/http.js';

async function testZootopia() {
  const res = await searchToonStream('Zootopia');
  console.log('Search res:', res);
  if (res.length) {
    const movieUrl = res[0].url;
    console.log('Movie URL:', movieUrl);
    const html = await fetchText(movieUrl);
    const iframes = [
      ...html.matchAll(/<iframe[^>]+src="([^"]+)"/gi),
      ...html.matchAll(/data-(?:url|embed|src)="([^"]+)"/gi)
    ].map(m => m[1].replace(/&amp;/g, '&').trim()).filter(u => u.startsWith('http'));
    console.log('Iframes:', iframes);
    for (const u of iframes) {
      const s = await resolveEmbedUrl(u, 'ToonStream');
      console.log('Resolved for', u, s);
    }
  }
}
testZootopia();
