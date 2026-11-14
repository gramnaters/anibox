import { resolveModiplay } from "../src/players/direct_m3u8.js";

async function main() {
  const embedUrl = "https://rozgarlelo.modiplay.xyz/embed/tmdb/tv?id=12697&s=1&e=1";
  console.log("Resolving ModiPlay directly:", embedUrl);
  const stream = await resolveModiplay(embedUrl, "MultiMovies ModiPlay");
  console.log("Stream:", stream);
  if (!stream) return;

  const reqH = stream.behaviorHints?.proxyHeaders?.request || {};
  const res = await fetch(stream.url, { headers: reqH });
  console.log("Master status:", res.status);
  const master = await res.text();
  console.log("Master playlist:\n", master);

  const streamLine = master.split("\n").map(l => l.trim()).find(l => !l.startsWith("#") && l.includes(".m3u8"));
  console.log("Stream line:", streamLine);
  const childUrl = new URL(streamLine, stream.url).toString();
  console.log("Child URL:", childUrl);
  const cRes = await fetch(childUrl, { headers: reqH });
  console.log("Child status:", cRes.status);
  const child = await cRes.text();
  
  const segLines = child.split("\n").map(l => l.trim()).filter(l => !l.startsWith("#") && l.length > 0);
  console.log("Total segments:", segLines.length);
  console.log("First seg line:", segLines[0]);
  const seg0Url = new URL(segLines[0], stream.url).toString();
  console.log("First seg URL:", seg0Url);

  const sRes = await fetch(seg0Url, { headers: reqH });
  console.log("First seg response status:", sRes.status);
  console.log("First seg headers:", Object.fromEntries(sRes.headers.entries()));
  const buf = await sRes.arrayBuffer();
  console.log("First seg bytes:", buf.byteLength);
}

main().catch(console.error);
