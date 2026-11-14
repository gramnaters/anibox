import { getWatchAnimeWorldStreams } from '../src/providers/watchanimeworld.js';
import { fetchText } from '../src/utils/http.js';

async function testWawMovie() {
  const url = 'https://watchanimeworld.top/movies/demon-slayer-kimetsu-no-yaiba-infinity-castle';
  const html = await fetchText(url);
  console.log('HTML length:', html ? html.length : 0);
  const iframes = [
    ...html.matchAll(/<iframe[^>]+src="([^"]+)"/gi),
    ...html.matchAll(/data-(?:url|embed|src)="([^"]+)"/gi)
  ];
  console.log('Iframes / embeds:', iframes.map(m => m[1]));
  const streams = await getWatchAnimeWorldStreams('demon-slayer-kimetsu-no-yaiba-infinity-castle', true);
  console.log('Streams:', streams);
}
testWawMovie();
