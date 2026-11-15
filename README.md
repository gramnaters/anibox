<div align="center">
  <img src="static/anibox-icon.png" width="120" height="120" alt="AniBox Logo" />
  <h1>AniBox</h1>
  <p><strong>High-Performance Asynchronous Stremio & Nuvio Streaming Addon</strong></p>

  <p>
    <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+" />
    <img src="https://img.shields.io/badge/Framework-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white" alt="FastAPI" />
    <img src="https://img.shields.io/badge/Server-Uvicorn%20ASGI-499848?style=flat-square&logo=gunicorn&logoColor=white" alt="Uvicorn" />
    <img src="https://img.shields.io/badge/Platform-Stremio%20%7C%20Nuvio-7B5BF2?style=flat-square" alt="Stremio" />
    <img src="https://img.shields.io/badge/Deploy-Render%20%7C%20Docker-46E3B7?style=flat-square&logo=render&logoColor=white" alt="Deploy" />
    <img src="https://img.shields.io/badge/License-MIT-blue?style=flat-square" alt="MIT License" />
  </p>
</div>

---

## Overview

AniBox is an asynchronous streaming addon for [Stremio](https://stremio.com) and [Nuvio](https://github.com/nuvio-app). It scrapes and resolves streams across multiple cinema and anime providers with multi-audio selection (Hindi Dub, Dual Audio, Japanese with Subtitles, and English).

Built on **FastAPI** and **Uvicorn (ASGI)**, AniBox leverages non-blocking concurrency, asynchronous extractors from `docchi-players`, in-memory SQLite title caching, and an anti-slop TypeUI web configuration dashboard.

---

## Core Features

- **Asynchronous ASGI Architecture**: Powered by FastAPI and `aiohttp.ClientSession` for concurrent multi-worker scraping without thread-pool exhaustion.
- **Multi-Source Streaming**: Aggregates releases across cinema, series, cartoons, and anime providers.
- **Embedded Player Extractors**: Integrates `docchi-players` async resolvers to handle complex token handshakes, obfuscated video embeds, and direct CDN playlists.
- **Stream Deduplication & Sorting**: Intelligently groups and orders streams by resolution (4K, 1080p, 720p), CDN response latency, or preferred audio track.
- **Telemetry & Live Health Dashboard**: Built-in `/api/status` endpoint and interactive telemetry panel displaying real-time uptime and ping latency.
- **ExoPlayer Compatibility**: Formats HLS master playlists and headers for smooth playback and seeking on Android TV, mobile, and web players.

---

## Content Providers

| Provider | Content Focus | Audio Tracks | Resolution | Extraction Method |
| :--- | :--- | :--- | :--- | :--- |
| **MultiMovies** | Cinema Releases, Hollywood, Bollywood | Multi-Audio, Hindi, English | 4K / 1080p / 720p | Master M3U8, StreamRuby, Abyss |
| **AnimeWorld** | Shonen, Seinen, Airing Anime | Hindi Dub, Dual-Audio | 1080p / 720p | Direct CDN HLS, Abyss |
| **ToonStream** | Cartoons, Classic Animation, Anime | Hindi, English | 1080p / 720p | Embedded Video Extractor |
| **PirateXPlay** | High-Speed Multi-Lingual Anime | Dual-Audio, Sub / Dub | 1080p / 720p | StreamWish, Vidguard, HLS |

---

## Supported Video Players

AniBox embeds native async resolvers from `docchi-players` alongside internal extractors:

| Resolver | Domains | Stream Type |
| :--- | :--- | :--- |
| **Abyss / HydraX** | `abysscdn.com`, `playhydrax.com` | Direct HLS / MP4 |
| **StreamRuby** | `streamruby.com`, `rubystream.net` | Master M3U8 Playlist |
| **Filemoon / Byse** | `filemoon.sx`, `byse*.com` | HLS adaptive stream |
| **DoodStream** | `dood.watch`, `doodstream.com` | Direct video stream |
| **Turbovid** | `turboviplay.com` | Direct HLS |
| **MP4Upload** | `mp4upload.com` | Direct MP4 stream |
| **Vidguard** | `vidguard.to`, `vgembed.com` | Direct adaptive stream |
| **StreamWish** | `streamwish.to`, `hgcloud.to` | HLS adaptive stream |
| **Vidoza / Vidmoly**| `vidoza.net`, `vidmoly.to` | Direct video stream |

---

## Quick Start & Installation

### Option 1: Use Hosted Instance

1. Open the configuration interface:
   ```text
   https://anibox-4l4u.onrender.com/configure
   ```
2. Select your enabled content providers, resolution preferences, and preferred audio language.
3. Click **Install to Stremio** or copy the generated manifest URL into Stremio's addon search bar.

### Option 2: Self-Host with Docker

```bash
# Clone the repository
git clone https://github.com/gramnaters/anibox.git
cd anibox

# Run with Docker Compose
docker compose up -d --build
```

Access the addon at `http://localhost:5000/configure`.

### Option 3: Local Development (Uvicorn)

```bash
# Clone and enter directory
git clone https://github.com/gramnaters/anibox.git
cd anibox

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: .\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run ASGI server
python run.py
```

The server binds to `http://127.0.0.1:5000` (or the port specified by the `PORT` environment variable).

---

## Configuration & Environment Variables

Copy `.env.example` to `.env` to customize runtime settings:

```bash
cp .env.example .env
```

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `PORT` | `5000` | Port for the HTTP/ASGI server |
| `TMDB_API_KEY` | `""` | TMDB API v3 key for movie/series metadata and search |
| `STREAM_MODE` | `direct` | `direct` for raw stream links, or `proxy` to route via server |
| `DB_TYPE` | `sqlite` | Database engine (`sqlite`) |
| `DB_PATH` | `mappings.db` | Path to persistent title mapping database |
| `CACHE_TTL` | `21600` | Manifest and stream cache lifetime in seconds (default: 6 hours) |

---

## Project Structure

```text
anibox/
├── app/
│   ├── api/                 # Provider search & scraper modules
│   │   ├── multimovies.py
│   │   ├── watchanimeworld.py
│   │   ├── toonstream.py
│   │   └── piratexplay.py
│   ├── players/             # Video player resolvers & docchi-players
│   │   ├── docchi_players/  # High-performance async extractors
│   │   ├── abyss.py
│   │   └── streamruby.py
│   ├── routes/              # FastAPI route endpoints
│   │   ├── manifest.py      # Stremio manifest generator
│   │   ├── catalog.py       # Catalog handlers
│   │   ├── meta.py          # Metadata resolution
│   │   ├── stream.py        # Stream extraction & sorting
│   │   ├── proxy.py         # HLS stream proxying & header rewriting
│   │   └── status.py        # Pipeline telemetry & metrics
│   ├── cdn.py               # Multi-tier CDN caching logic
│   ├── database.py          # SQLite title mapper
│   └── status_monitor.py    # Background provider health checker
├── static/                  # Production brand logos, icons, and assets
├── templates/
│   ├── configure.html       # TypeUI web configuration dashboard
│   └── status.html          # Standalone telemetry page
├── main.py                  # Core FastAPI application entrypoint
├── run.py                   # Universal ASGI/WSGI server bootstrapper
├── gunicorn_config.py       # Production worker configuration
├── render.yaml              # Render Cloud deployment specification
├── Procfile                 # Cloud runtime process configuration
├── requirements.txt         # Python package dependencies
└── Dockerfile               # Container build instructions
```

---

## API Endpoints

- `GET /manifest.json` — Stremio addon manifest.
- `GET /configure` — TypeUI interactive configuration and installation page.
- `GET /catalog/{type}/{id}.json` — Catalog items for Stremio discover views.
- `GET /meta/{type}/{id}.json` — Detailed metadata for selected titles.
- `GET /stream/{type}/{id}.json` — Resolved stream links with resolution, audio, and player badges.
- `GET /api/status` — Live JSON health telemetry across all configured scrapers.
- `GET /health` — Simple healthcheck endpoint for uptime monitors.
- `GET /ping` — Keep-alive ping endpoint.

---

## License

This project is licensed under the [MIT License](LICENSE).
