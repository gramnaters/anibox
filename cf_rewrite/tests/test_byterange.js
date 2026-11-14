import fs from "fs";
import { execFile } from "child_process";
import { promisify } from "util";

const execFileAsync = promisify(execFile);
const tiktokUrl = "https://p19-ad-site-sign-sg.tiktokcdn.com/ad-site-i18n-sg/202608255d0d3f4bab3c0df84ca69bdd~tplv-d5opwmad15-ttam-origin.image?lk3s=6d71dd51&x-expires=1819218998&x-signature=xNwi4EkM9dz2D6k3UYRPoxAF66E%3D";

const testM3u8 = `#EXTM3U
#EXT-X-VERSION:4
#EXT-X-TARGETDURATION:11
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:10.010,
#EXT-X-BYTERANGE:502712@70
${tiktokUrl}
#EXT-X-ENDLIST`;

fs.writeFileSync("cf_rewrite/tests/test_byterange.m3u8", testM3u8);

async function test() {
  const { stdout, stderr } = await execFileAsync("E:\\Yt dlp\\ffprobe.exe", ["cf_rewrite/tests/test_byterange.m3u8"]);
  console.log("ffprobe output:\n", stdout, stderr);
}

test().catch(console.error);
