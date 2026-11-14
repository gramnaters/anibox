async function main() {
  const embedUrl = "https://rozgarlelo.modiplay.xyz/embed/tmdb/tv?id=12697&s=1&e=1";
  const r1 = await fetch(embedUrl);
  const html1 = await r1.text();
  const ifm = html1.match(/<iframe[^>]+src="([^"]+)"/i);
  const rawProxy = ifm[1].replace(/&amp;/g, "&");
  const proxyUrl = new URL(rawProxy, embedUrl).toString();
  console.log("Proxy URL:", proxyUrl);

  const r2 = await fetch(proxyUrl, { headers: { Referer: embedUrl } });
  console.log("Proxy status:", r2.status);
  console.log("Proxy Set-Cookie:", r2.headers.get("set-cookie"));
  console.log("All proxy headers:", Object.fromEntries(r2.headers.entries()));
}

main().catch(console.error);
