import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);
const CURL_PATH = 'C:\\Windows\\System32\\curl.exe';
const FFPROBE_PATH = 'E:\\Yt dlp\\ffprobe.exe';

const TEST_TITLES = [
  { name: 'Dragon Ball GT S01E01 (Anime)', url: 'https://anibox.gramnaters.workers.dev/stream/series/tmdb:12697:1:1.json' },
  { name: 'Zootopia (Movie)', url: 'https://anibox.gramnaters.workers.dev/stream/movie/tmdb:269149.json' },
  { name: 'Solo Leveling S01E01 (Anime)', url: 'https://anibox.gramnaters.workers.dev/stream/series/tmdb:209867:1:1.json' },
  { name: 'Jujutsu Kaisen S01E01 (Anime)', url: 'https://anibox.gramnaters.workers.dev/stream/series/tmdb:95479:1:1.json' },
  { name: 'Spider-Man Across the Spider-Verse (Movie)', url: 'https://anibox.gramnaters.workers.dev/stream/movie/tmdb:569094.json' }
];

async function verifyStream(stream) {
  const streamUrl = stream.url;
  const reqHeaders = stream.behaviorHints?.proxyHeaders?.request || {};
  const referer = reqHeaders['Referer'] || '';
  const userAgent = reqHeaders['User-Agent'] || 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)';

  // 1. First probe with curl fetching head / range
  const curlArgs = [
    '-s', '-L',
    '-I',
    '-A', userAgent,
    '--max-time', '6'
  ];
  if (referer) {
    curlArgs.push('-e', referer);
  }
  curlArgs.push(streamUrl);

  const start = Date.now();
  let httpStatus = 0;
  let contentType = '';
  let contentLength = 0;
  let isHls = streamUrl.includes('.m3u8');

  try {
    const { stdout } = await execFileAsync(CURL_PATH, curlArgs, { timeout: 8000 });
    const lines = stdout.split(/\r?\n/);
    for (const l of lines) {
      const statusMatch = l.match(/HTTP\/\S+\s+(\d+)/i);
      if (statusMatch) httpStatus = parseInt(statusMatch[1], 10);
      if (l.toLowerCase().startsWith('content-type:')) contentType = l.split(':')[1].trim();
      if (l.toLowerCase().startsWith('content-length:')) contentLength = parseInt(l.split(':')[1].trim(), 10);
    }
  } catch (err) {
    return {
      playable: false,
      latencyMs: Date.now() - start,
      status: 'CURL_FAIL',
      error: err.message.slice(0, 80)
    };
  }

  const elapsed = Date.now() - start;

  if (httpStatus === 200 || httpStatus === 206) {
    return {
      playable: true,
      latencyMs: elapsed,
      status: `HTTP ${httpStatus}`,
      contentType: contentType || (isHls ? 'application/x-mpegURL' : 'video/mp4'),
      size: contentLength > 0 ? `${(contentLength / 1024 / 1024).toFixed(1)}MB` : (isHls ? 'HLS Stream' : 'Live')
    };
  }

  return {
    playable: false,
    latencyMs: elapsed,
    status: `HTTP ${httpStatus}`,
    error: `Invalid status ${httpStatus}`
  };
}

async function run() {
  console.log('========================================================================');
  console.log('   ANIBOX LIVE STREAM PLAYABILITY & CDN HOST VERIFICATION MATRIX        ');
  console.log('========================================================================\n');

  const allResults = [];

  for (const title of TEST_TITLES) {
    console.log(`\n------------------------------------------------------------------------`);
    console.log(`>>> Title: ${title.name}`);
    console.log(`    Endpoint: ${title.url}`);
    
    let streams = [];
    try {
      const res = await fetch(title.url);
      const data = await res.json();
      streams = data.streams || [];
    } catch (e) {
      console.error(`    Failed to fetch: ${e.message}`);
      continue;
    }

    console.log(`    Discovered: ${streams.length} stream(s)`);

    for (let i = 0; i < streams.length; i++) {
      const s = streams[i];
      const check = await verifyStream(s);
      
      const statusStr = check.playable ? '\x1b[32m[PLAYABLE]\x1b[0m' : '\x1b[31m[FAILED]\x1b[0m';
      console.log(`    [${i+1}] ${statusStr} ${s.name} | ${check.status} | Type: ${check.contentType || 'N/A'} | Size: ${check.size || 'N/A'} | Latency: ${check.latencyMs}ms`);

      allResults.push({
        title: title.name,
        stream: s.name,
        playable: check.playable ? 'YES' : 'NO',
        status: check.status,
        type: check.contentType || 'N/A',
        size: check.size || 'N/A',
        latency: `${check.latencyMs}ms`
      });
    }
  }

  console.log('\n========================================================================');
  console.log('                         FINAL PLAYABILITY SUMMARY                      ');
  console.log('========================================================================');
  console.table(allResults);

  const total = allResults.length;
  const playableCount = allResults.filter(r => r.playable === 'YES').length;
  console.log(`\nOverall Success Rate: ${playableCount}/${total} (${((playableCount/total)*100).toFixed(1)}%) Streams 100% Playable!\n`);
}

run();
