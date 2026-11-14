import { fetchText } from '../src/utils/http.js';

async function inspectEp() {
  const html = await fetchText('https://watchanimeworld.one/episode/solo-leveling-1x1/');
  const iframes = [...html.matchAll(/<iframe[^>]+src="([^"]+)"/gi)].map(m => m[1]);
  console.log('Iframes:', iframes);
  const embeds = [...html.matchAll(/data-(?:url|embed|src)="([^"]+)"/gi)].map(m => m[1]);
  console.log('Embeds:', embeds);
  const openPlayer = [...html.matchAll(/open_player[^>]*data-post="([^"]+)"[^>]*data-nume="([^"]+)"/gi)];
  console.log('Open player:', openPlayer.map(m => ({ post: m[1], nume: m[2] })));
}
inspectEp();
