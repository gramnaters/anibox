import http from "http";
import { execFile } from "child_process";
import { promisify } from "util";

const execFileAsync = promisify(execFile);
const tiktokUrl = "https://p19-ad-site-sign-sg.tiktokcdn.com/ad-site-i18n-sg/202608255d0d3f4bab3c0df84ca69bdd~tplv-d5opwmad15-ttam-origin.image?lk3s=6d71dd51&x-expires=1819218998&x-signature=xNwi4EkM9dz2D6k3UYRPoxAF66E%3D";

// Start a lightweight test server that serves .m3u8 and .ts
const server = http.createServer(async (req, res) => {
  if (req.url === "/playlist.m3u8") {
    res.writeHead(200, { "Content-Type": "application/vnd.apple.mpegurl" });
    res.end(`#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:11
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:10.010,
http://127.0.0.1:8999/chunk0.ts
#EXT-X-ENDLIST`);
  } else if (req.url === "/chunk0.ts") {
    const upstream = await fetch(tiktokUrl, { headers: { Range: "bytes=70-" } });
    const buf = await upstream.arrayBuffer();
    res.writeHead(200, {
      "Content-Type": "video/mp2t",
      "Content-Length": buf.byteLength,
      "Access-Control-Allow-Origin": "*",
    });
    res.end(Buffer.from(buf));
  } else {
    res.writeHead(404).end();
  }
});

server.listen(8999, "127.0.0.1", async () => {
  console.log("Mock HLS server running on port 8999");
  try {
    const { stdout, stderr } = await execFileAsync("E:\\Yt dlp\\ffprobe.exe", [
      "-i", "http://127.0.0.1:8999/playlist.m3u8"
    ]);
    console.log("SUCCESS! FFPROBE OUTPUT:\n", stdout, stderr);
  } catch (err) {
    console.error("FFPROBE FAILED:", err.message);
  } finally {
    server.close();
    process.exit(0);
  }
});
