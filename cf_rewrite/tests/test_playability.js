import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);
const FFPROBE_PATH = 'E:\\Yt dlp\\ffprobe.exe';

const TEST_TITLES = [
  { name: 'Dragon Ball GT S01E01', url: 'https://anibox.gramnaters.workers.dev/stream/series/tmdb:12697:1:1.json' },
  { name: 'Zootopia (Movie)', url: 'https://anibox.gramnaters.workers.dev/stream/movie/tmdb:269149.json' },
  { name: 'Solo Leveling S01E01', url: 'https://anibox.gramnaters.workers.dev/stream/series/tmdb:209867:1:1.json' },
  { name: 'Jujutsu Kaisen S01E01', url: 'https://anibox.gramnaters.workers.dev/stream/series/tmdb:95479:1:1.json' },
  { name: 'Spider-Man Across the Spider-Verse', url: 'https://anibox.gramnaters.workers.dev/stream/movie/tmdb:569094.json' }
];

async function probeStream(stream) {
  const streamUrl = stream.url;
  const headers = stream.behaviorHints?.proxyHeaders?.request || {};
  
  // Build header string for ffprobe
  let headerArg = '';
  for (const [k, v] of Object.entries(headers)) {
    headerArg += `${k}: ${v}\r\n`;
  }

  const args = [
    '-v', 'error',
    '-select_streams', 'v:0',
    '-show_entries', 'stream=codec_name,width,height,bit_rate',
    '-show_entries', 'format=format_name,duration,bit_rate',
    '-of', 'json',
    '-analyzeduration', '5000000',
    '-probesize', '5000000'
  ];

  if (headerArg) {
    args.push('-headers', headerArg);
  }

  args.push(streamUrl);

  const start = Date.now();
  try {
    const { stdout } = await execFileAsync(FFPROBE_PATH, args, { timeout: 12000 });
    const elapsed = Date.now() - start;
    const info = JSON.parse(stdout);
    const videoStream = info.streams?.[0];
    const format = info.format;
    
    return {
      playable: true,
      latencyMs: elapsed,
      codec: videoStream?.codec_name || 'unknown',
      resolution: videoStream ? `${videoStream.width}x${videoStream.height}` : 'unknown',
      format: format?.format_name || 'unknown'
    };
  } catch (err) {
    const elapsed = Date.now() - start;
    return {
      playable: false,
      latencyMs: elapsed,
      error: err.killed ? 'Timeout (12s)' : (err.stderr || err.message).slice(0, 120)
    };
  }
}

async function run() {
  console.log('===============================================================');
  console.log('   ANIBOX STREAM PLAYABILITY & HOST/SERVER VERIFICATION        ');
  console.log('===============================================================\n');

  const results = [];

  for (const title of TEST_TITLES) {
    console.log(`\n>>> Testing: ${title.name}`);
    console.log(`    Fetching: ${title.url}`);
    
    let streams = [];
    try {
      const res = await fetch(title.url);
      const data = await res.json();
      streams = data.streams || [];
    } catch (e) {
      console.error(`    Failed to fetch streams: ${e.message}`);
      continue;
    }

    console.log(`    Discovered ${streams.length} stream(s):`);

    for (let i = 0; i < streams.length; i++) {
      const s = streams[i];
      console.log(`\n    [${i+1}/${streams.length}] ${s.name}`);
      console.log(`        Desc: ${s.description || 'N/A'}`);
      console.log(`        URL:  ${s.url.substring(0, 90)}...`);
      if (s.behaviorHints?.proxyHeaders?.request) {
        console.log(`        Headers: ${JSON.stringify(s.behaviorHints.proxyHeaders.request)}`);
      }

      console.log(`        Probing with ffprobe...`);
      const probe = await probeStream(s);
      
      if (probe.playable) {
        console.log(`        \x1b[32m[PLAYABLE]\x1b[0m Codec: ${probe.codec} | Res: ${probe.resolution} | Format: ${probe.format} | Probe: ${probe.latencyMs}ms`);
      } else {
        console.log(`        \x1b[31m[FAILED]\x1b[0m Error: ${probe.error} (${probe.latencyMs}ms)`);
      }

      results.push({
        title: title.name,
        streamName: s.name,
        desc: s.description,
        url: s.url,
        probe
      });
    }
  }

  console.log('\n===============================================================');
  console.log('                     SUMMARY RESULTS MATRIX                    ');
  console.log('===============================================================');
  console.table(results.map(r => ({
    Title: r.title,
    Stream: r.streamName,
    Playable: r.probe.playable ? 'YES' : 'NO',
    Codec: r.probe.codec || 'N/A',
    Resolution: r.probe.resolution || 'N/A',
    Latency: `${r.probe.latencyMs}ms`,
    Error: r.probe.error ? r.probe.error.substring(0, 40) : 'None'
  })));
}

run();
