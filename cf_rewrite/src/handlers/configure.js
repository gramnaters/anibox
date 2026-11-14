/**
 * FMHY-Inspired Modern Configuration Dashboard for AniBox Edge.
 */

export function handleConfigure(request) {
  const host = new URL(request.url).host;
  const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AniBox — Edge Anime & Movie Stream Addon</title>
  <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
  <style>
    body { background: #0b0f19; color: #f1f5f9; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    .card { background: #131b2e; border: 1px solid #1f2d4a; border-radius: 1rem; }
    .btn-gradient { background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #d946ef 100%); }
    .btn-gradient:hover { filter: brightness(1.15); transform: translateY(-1px); }
    .toggle-checkbox:checked { right: 0; border-color: #6366f1; }
    .toggle-checkbox:checked + .toggle-label { background-color: #6366f1; }
  </style>
</head>
<body class="min-h-screen flex items-center justify-center p-4">
  <div class="card max-w-xl w-full p-8 shadow-2xl space-y-6">
    <div class="flex items-center space-x-4 border-b border-gray-800 pb-5">
      <div class="w-12 h-12 rounded-xl btn-gradient flex items-center justify-center text-white font-black text-2xl shadow-lg">A</div>
      <div>
        <h1 class="text-2xl font-extrabold text-white tracking-tight">AniBox Edge</h1>
        <p class="text-xs text-indigo-400 font-semibold tracking-wide uppercase">All Providers · 300+ Edge Locations · Instant Streams</p>
      </div>
    </div>

    <div class="space-y-4">
      <h3 class="text-xs font-bold text-gray-400 uppercase tracking-wider">Active Providers</h3>
      <div class="grid grid-cols-2 gap-3 text-sm">
        <label class="flex items-center space-x-2.5 p-3 rounded-lg bg-gray-900 border border-gray-800 cursor-pointer hover:border-gray-700">
          <input type="checkbox" id="src_multimovies" checked class="form-checkbox h-4 w-4 text-indigo-600 rounded bg-gray-800 border-gray-700">
          <span class="font-medium text-gray-200">MultiMovies</span>
        </label>
        <label class="flex items-center space-x-2.5 p-3 rounded-lg bg-gray-900 border border-gray-800 cursor-pointer hover:border-gray-700">
          <input type="checkbox" id="src_toonstream" checked class="form-checkbox h-4 w-4 text-indigo-600 rounded bg-gray-800 border-gray-700">
          <span class="font-medium text-gray-200">ToonStream</span>
        </label>
        <label class="flex items-center space-x-2.5 p-3 rounded-lg bg-gray-900 border border-gray-800 cursor-pointer hover:border-gray-700">
          <input type="checkbox" id="src_watchanimeworld" checked class="form-checkbox h-4 w-4 text-indigo-600 rounded bg-gray-800 border-gray-700">
          <span class="font-medium text-gray-200">AnimeWorld</span>
        </label>
        <label class="flex items-center space-x-2.5 p-3 rounded-lg bg-gray-900 border border-gray-800 cursor-pointer hover:border-gray-700">
          <input type="checkbox" id="src_piratexplay" checked class="form-checkbox h-4 w-4 text-indigo-600 rounded bg-gray-800 border-gray-700">
          <span class="font-medium text-gray-200">PirateXPlay</span>
        </label>
      </div>
    </div>

    <div class="space-y-4 border-t border-gray-800 pt-5 text-sm">
      <h3 class="text-xs font-bold text-gray-400 uppercase tracking-wider">Filters & Ordering</h3>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block font-semibold text-gray-300 mb-1 text-xs">Quality Sorting</label>
          <select id="sort_by" class="w-full bg-gray-900 border border-gray-800 rounded-lg p-2.5 text-white focus:outline-none focus:border-indigo-500">
            <option value="quality_desc">Highest Quality First (4K / 1080p → 720p)</option>
            <option value="quality_asc">Lowest Quality First (Data Saver)</option>
            <option value="provider">Group by Provider</option>
          </select>
        </div>
        <div>
          <label class="block font-semibold text-gray-300 mb-1 text-xs">Audio Filter</label>
          <select id="filter_audio" class="w-full bg-gray-900 border border-gray-800 rounded-lg p-2.5 text-white focus:outline-none focus:border-indigo-500">
            <option value="all">All Audio (Hindi Dubs + Multi Audio)</option>
            <option value="hindi_only">Hindi Dubs Strict Only</option>
          </select>
        </div>
      </div>
    </div>

    <div class="space-y-3 pt-2">
      <a id="install_btn" href="stremio://${host}/manifest.json" class="btn-gradient w-full py-3.5 px-4 rounded-xl font-bold text-center block text-white shadow-xl transition">
        Install Addon to Stremio
      </a>
      <button onclick="copyManifest()" class="w-full py-3 px-4 rounded-xl font-semibold bg-gray-900 hover:bg-gray-800 border border-gray-800 text-gray-300 transition">
        Copy Manifest Link
      </button>
      <a id="web_btn" href="https://web.stremio.com/#/addons?addon=${encodeURIComponent(`https://${host}/manifest.json`)}" target="_blank" class="w-full py-2.5 px-4 rounded-xl font-medium text-center block text-xs text-gray-400 hover:text-white transition">
        Open in Stremio Web
      </a>
    </div>

    <p id="copied_msg" class="text-center text-xs text-green-400 hidden">✓ Manifest link copied to clipboard!</p>
  </div>

  <script>
    function updateLinks() {
      const cfg = {
        source_multimovies: document.getElementById('src_multimovies').checked,
        source_toonstream: document.getElementById('src_toonstream').checked,
        source_watchanimeworld: document.getElementById('src_watchanimeworld').checked,
        source_piratexplay: document.getElementById('src_piratexplay').checked,
        sort_by: document.getElementById('sort_by').value,
        filter_audio: document.getElementById('filter_audio').value
      };
      const b64 = btoa(JSON.stringify(cfg)).replace(/\\+/g, '-').replace(/\\//g, '_').replace(/=+$/, '');
      const base = window.location.host;
      const manifestUrl = 'https://' + base + '/' + b64 + '/manifest.json';
      document.getElementById('install_btn').href = 'stremio://' + base + '/' + b64 + '/manifest.json';
      document.getElementById('web_btn').href = 'https://web.stremio.com/#/addons?addon=' + encodeURIComponent(manifestUrl);
      window.currentManifest = manifestUrl;
    }

    ['src_multimovies', 'src_toonstream', 'src_watchanimeworld', 'src_piratexplay', 'sort_by', 'filter_audio'].forEach(id => {
      document.getElementById(id).addEventListener('change', updateLinks);
    });
    window.currentManifest = 'https://${host}/manifest.json';

    function copyManifest() {
      navigator.clipboard.writeText(window.currentManifest || 'https://${host}/manifest.json');
      const msg = document.getElementById('copied_msg');
      msg.classList.remove('hidden');
      setTimeout(() => msg.classList.add('hidden'), 2500);
    }
  </script>
</body>
</html>`;

  return new Response(html, {
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
    }
  });
}
