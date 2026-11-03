# MultiMovies rewrite — plan & live findings

## Confirmed live (m1.multimovies.courses, new "Cinema" theme)
- Search: `GET /search?q=` → `article.poster-card` → `a.poster-art[href]` → `/movie/{slug}-{id}` or `/series/{slug}-{id}`
- Movie page: `/movie/{slug}-{id}` → `h1` title + `button.server-chip[data-url]`
- Series page: `/series/{slug}-{id}` → episode links `/series/{slug}-{id}/season/{s}/episode/{e}` + server grid
- No `doo_player_ajax` anymore — server URLs are inline `data-url`.

## Server host → resolver (verified)
- rozgarlelo.modiplay.xyz  → proxy.php → `var src` stream_proxy.php → m3u8 (VERIFIED 200 #EXTM3U)
- streams.iqsmartgames.com → iqsmart_common.resolve_embed (already wired)
- web.nxsha.app            → nxsha.space AES API (already wired in nxsha.py)
- embed.vidrift.net        → direct .m3u8 in HTML (gzip.rousav.tech) VERIFIED 200
- embed.filmu.in           → direct .m3u8 in HTML (gzip.rousav.tech)
- vidout.pages.dev         → direct .m3u8 in HTML (vidmmo.com, short-lived token)
- screenscape.me / peachify.top / nhdapi.com / moviesnexus.fun / vidbolt.xyz → dead or JS-only (skip)

## Todo
- [x] confirm new domain + theme structure
- [x] verify modiplay + direct-m3u8 hosts live
- [ ] rewrite multimovies.py (search/details/episodes/streams)
- [ ] wire host dispatch
- [ ] live test each provider method
- [ ] commit + push + redeploy Render
