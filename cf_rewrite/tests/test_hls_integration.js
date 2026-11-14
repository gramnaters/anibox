import { handleRequest } from "../src/index.js";
import { execFile } from "child_process";
import { promisify } from "util";
import fs from "fs";

const execFileAsync = promisify(execFile);

async function run() {
  console.log("=== Step 1: Requesting DB GT Streams ===");
  const streamReq = new Request("http://127.0.0.1/stream/series/tmdb:12697:1:1.json");
  const streamRes = await handleRequest(streamReq);
  const streamData = await streamRes.json();
  console.log("Found streams:", streamData.streams.map(s => s.name));

  const modiStream = streamData.streams.find(s => s.name.includes("ModiPlay"));
  if (!modiStream) throw new Error("No ModiPlay stream found!");
  console.log("ModiPlay Stream URL:", modiStream.url);

  console.log("\n=== Step 2: Fetching Master Playlist via /hls/manifest ===");
  const masterReq = new Request(modiStream.url);
  const masterRes = await handleRequest(masterReq);
  console.log("Master HTTP Status:", masterRes.status);
  const masterText = await masterRes.text();
  console.log("Master Playlist Preview:\n", masterText.slice(0, 400));

  const childUrlLine = masterText.split("\n").map(l => l.trim()).find(l => !l.startsWith("#") && l.includes("/hls/manifest"));
  if (!childUrlLine) throw new Error("No /hls/manifest child line in master playlist!");
  console.log("Child URL line:", childUrlLine);

  console.log("\n=== Step 3: Fetching Child Playlist via /hls/manifest ===");
  const childReq = new Request(childUrlLine);
  const childRes = await handleRequest(childReq);
  console.log("Child HTTP Status:", childRes.status);
  const childText = await childRes.text();
  console.log("Child Playlist Preview:\n", childText.slice(0, 400));

  const segUrlLine = childText.split("\n").map(l => l.trim()).find(l => !l.startsWith("#") && l.includes("/hls/seg/"));
  if (!segUrlLine) throw new Error("No /hls/seg/ line in child playlist!");
  console.log("First Seg URL line:", segUrlLine);

  console.log("\n=== Step 4: Fetching Segment via /hls/seg/<token>.ts ===");
  const segReq = new Request(segUrlLine);
  const segRes = await handleRequest(segReq);
  console.log("Seg HTTP Status:", segRes.status);
  console.log("Seg Content-Type:", segRes.headers.get("content-type"));
  const segBuf = await segRes.arrayBuffer();
  console.log("Seg Received Bytes:", segBuf.byteLength);

  const b = Buffer.from(segBuf);
  console.log("First byte is 0x47 (MPEG-TS sync)?", b[0] === 0x47);
  fs.writeFileSync("cf_rewrite/tests/edge_seg.ts", b);

  console.log("\n=== Step 5: Probing with ffprobe ===");
  const { stdout, stderr } = await execFileAsync("E:\\Yt dlp\\ffprobe.exe", ["cf_rewrite/tests/edge_seg.ts"]);
  console.log("FFPROBE SUCCESS:\n", stdout, stderr);
}

run().catch(console.error);
