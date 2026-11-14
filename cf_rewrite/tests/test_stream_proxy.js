import { DEFAULT_UA } from "../src/utils/http.js";

async function testStreamProxy() {
  const targetUrl = 'https://njuaynwkh47.sssrr.org/sora/205193216/b1dlc0wrQnVZQ1B6K2M5OE92dENKMzc3MWhjYmNzRzN6K2FJTnl4bGlDcHdNUlJrWlE';
  const referer = 'https://abyssplayer.com/';

  // Simulating the worker's handleStreamProxy
  const upstreamHeaders = {
    "User-Agent": DEFAULT_UA,
    "Referer": referer,
    "Range": "bytes=0-1000",
  };

  let currentUrl = targetUrl;
  let response;
  let redirects = 0;
  while (redirects < 5) {
    response = await fetch(currentUrl, {
      method: "GET",
      headers: upstreamHeaders,
      redirect: "manual",
    });

    if ([301, 302, 303, 307, 308].includes(response.status) && response.headers.get("location")) {
      const loc = response.headers.get("location");
      currentUrl = new URL(loc, currentUrl).toString();
      redirects++;
      continue;
    }
    break;
  }

  console.log('Redirects followed:', redirects);
  console.log('Final URL:', currentUrl);
  console.log('Response Status:', response.status);
  console.log('Content-Type:', response.headers.get('content-type'));
  console.log('Content-Range:', response.headers.get('content-range'));
  const buf = Buffer.from(await response.arrayBuffer());
  console.log('Downloaded bytes:', buf.length);
  console.log('MP4 Box ftyp present:', buf.includes(Buffer.from('ftyp')));
}

testStreamProxy();
