# AniBox Edge (Cloudflare Worker Scraper & Stremio Addon)

This directory contains the edge-native rewrite of the AniBox scrapers running on Cloudflare Workers.

## Key Benefits
- **Sub-50ms Response Time**: Executes at 300+ Cloudflare edge locations worldwide instead of a single remote server.
- **Zero Bandwidth Quota Issues**: All edge requests run through Cloudflare's global network with high concurrency.
- **Direct Edge Streaming**: Direct streams (Abyss, Byse, SprintCDN) pass directly with edge-configured `proxyHeaders`.
- **Parallel Edge Fetching**: Scrapes multiple providers in parallel with sub-request caching (`cf.cacheTtl`).

## Project Layout
- `src/index.js`: Edge worker entry point with routing, scrapers, and Stremio protocol implementation.
- `wrangler.toml`: Cloudflare Workers configuration.
- `package.json`: Dependencies and deployment scripts.

## Running Locally
1. Make sure Node.js is installed.
2. In this directory (`cf_worker/`), run:
   ```bash
   npx wrangler dev
   ```
3. Open `http://localhost:8787/manifest.json` in your browser or add it to Stremio.

## Deploying to Cloudflare
1. Log in to your Cloudflare account via CLI:
   ```bash
   npx wrangler login
   ```
2. Deploy globally in seconds:
   ```bash
   npx wrangler deploy
   ```
3. You will receive a live URL:
   `https://anibox-edge.<your-subdomain>.workers.dev/manifest.json`
