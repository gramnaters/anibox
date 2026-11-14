async function main() {
  const masterTok = "2386d64aa4d26480d259ad04a6aec8e8";
  const segTok = "2b2a1597fec0743739086c7c03ccafba";
  const tiktokUrl = "https://p16-ad-site-sign-sg.tiktokcdn.com/ad-site-i18n-sg/202608255d0dbd916328c17e4384bee8~tplv-d5opwmad15-ttam-origin.image?lk3s=6d71dd51&x-expires=1819218988&x-signature=AX%2BfPy6olQSXCsRyFwDNMzB2myE%3D";
  const ref = "https://vibuxer.com/e/4swva5jrfciz";

  // Test 1: original seg URL
  const u1 = `https://rozgarlelo.modiplay.xyz/stream_proxy.php?url=${encodeURIComponent(tiktokUrl)}&ref=${encodeURIComponent(ref)}&tok=${segTok}`;
  const r1 = await fetch(u1, { headers: { "Referer": "https://rozgarlelo.modiplay.xyz/" } });
  console.log("u1 status:", r1.status);

  // Test 2: master tok
  const u2 = `https://rozgarlelo.modiplay.xyz/stream_proxy.php?url=${encodeURIComponent(tiktokUrl)}&ref=${encodeURIComponent(ref)}&tok=${masterTok}`;
  const r2 = await fetch(u2, { headers: { "Referer": "https://rozgarlelo.modiplay.xyz/" } });
  console.log("u2 status:", r2.status);

  // Test 3: without tok
  const u3 = `https://rozgarlelo.modiplay.xyz/stream_proxy.php?url=${encodeURIComponent(tiktokUrl)}&ref=${encodeURIComponent(ref)}`;
  const r3 = await fetch(u3, { headers: { "Referer": "https://rozgarlelo.modiplay.xyz/" } });
  console.log("u3 status:", r3.status);

  // Test 4: check raw tiktok fetch with Range header
  const r4 = await fetch(tiktokUrl, { headers: { "Range": "bytes=0-100" } });
  console.log("tiktok raw Range status:", r4.status, r4.headers.get("content-range"));
}

main().catch(console.error);
