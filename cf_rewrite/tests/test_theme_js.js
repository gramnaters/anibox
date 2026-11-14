import { fetchText } from '../src/utils/http.js';

async function checkScripts() {
  const html = await fetchText('https://watchanimeworld.top/series/solo-leveling');
  const scripts = [...html.matchAll(/<script[^>]*src="([^"]+)"/gi)].map(m => m[1]);
  console.log('Scripts:', scripts);
  const inline = [...html.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/gi)].map(m => m[1]);
  for (const s of inline) {
    if (s.includes('sel-temp') || s.includes('choose-season') || s.includes('episode_by_temp')) {
      console.log('Found handler:', s.substring(0, 500));
    }
  }
}
checkScripts();
