#!/usr/bin/env python3
"""
ExoPlayer Stream Benchmark Suite:
Tests playability, seekability, multi-audio, and speed across Direct Embeds and AniBox Providers.
"""

import json
import time
from exoplayer_harness import test_stream_harness
from app.api import ALL_PROVIDERS
from app.players.all_players import resolve_stream
import requests
import re

print("=" * 75)
print("     EXOPLAYER STREAM PLAYABILITY, SEEKABILITY & SPEED BENCHMARK")
print("=" * 75)

test_targets = []

# ─── 1. Direct Embed APIs ───
print("\n[+] Collecting Direct Embed API endpoints...")

# 1a. Vidout Direct CDN (TMDB 1007757)
test_targets.append({
    'category': 'Direct Embed API',
    'name': 'Vidout (Watchout2025): TMDB 1007757',
    'url': 'https://esrzaekj9ifiue8.onlinestudygroups.sbs/ebdetyq0wnxyxizu/hls3/01/08077/6478zdvkiql6_,l,n,h,.urlset/master.txt',
    'referer': 'https://vidout.pages.dev/'
})

# 1b. Vidly Direct CDN (TMDB 269149)
test_targets.append({
    'category': 'Direct Embed API',
    'name': 'Vidly Direct CDN: TMDB 269149',
    'url': 'https://img.rousav.tech/media/8ebf6d6ebd8ddcc51588/index.m3u8',
    'referer': 'https://vidly.pro/'
})

# 1c. Minochinos / VidHide Direct HLS2 (TMDB 46260 via Rozgarlelo)
try:
    r_mino = requests.get('https://minochinos.com/embed/pjvi2mg9zj67', headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://rozgarlelo.modiplay.xyz/'}, timeout=8)
    match = re.search(r'eval\(function\(p,a,c,k,e,d\)\{.*?\}\((.*?)\)\s*$', r_mino.text, re.DOTALL | re.MULTILINE)
    if match:
        params = match.group(1)
        p_match = re.search(r"'(.*?)',\s*(\d+),\s*(\d+),\s*'(.*?)'\.split\('\|'\)", params, re.DOTALL)
        if p_match:
            payload, radix, count, symtab = p_match.group(1), int(p_match.group(2)), int(p_match.group(3)), p_match.group(4).split('|')
            def unbase(val, r):
                alphabet = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
                res = 0
                for char in val: res = res * r + alphabet.index(char)
                return res
            unpacked = re.sub(r'\b\w+\b', lambda m: symtab[unbase(m.group(0), radix)] if unbase(m.group(0), radix) < len(symtab) and symtab[unbase(m.group(0), radix)] else m.group(0), payload)
            hls2_match = re.search(r'https?://[^\s"\'<>]+\.acek-cdn\.com/hls2/[^\s"\'<>]+', unpacked)
            if hls2_match:
                test_targets.append({
                    'category': 'Direct Embed API',
                    'name': 'Minochinos / VidHide HLS2: TMDB 46260',
                    'url': hls2_match.group(0),
                    'referer': 'https://minochinos.com/'
                })
                print("  ✓ Minochinos / VidHide Direct HLS2 stream loaded!")
except Exception as e:
    print("  ✗ Minochinos unpack note:", e)


# ─── 2. AniBox Providers ───
print("\n[+] Collecting Live Streams from AniBox Providers...")

# 2a. ToonStream (StreamRuby resolver)
try:
    ts = ALL_PROVIDERS['toonstream']
    ts_res = ts.search_anime("Ben 10")
    if ts_res:
        slug = ts_res[0].get('slug') or ts_res[0].get('id')
        streams_data = ts.get_episode_streams(slug, 1, 1)
        streams = streams_data.get('streams', [])
        ruby_stream = next((s for s in streams if s.get('player') == 'streamruby'), None)
        if ruby_stream:
            resolved = resolve_stream(ruby_stream)
            if resolved and resolved[0].get('url'):
                test_targets.append({
                    'category': 'AniBox Provider',
                    'name': 'ToonStream: Ben 10 (StreamRuby)',
                    'url': resolved[0]['url'],
                    'referer': 'https://rubystm.com/'
                })
                print("  ✓ ToonStream (StreamRuby) stream loaded!")
except Exception as e:
    print("  ✗ ToonStream fetch note:", e)

# 2b. AnimeWorld (Zephyr & Abyss resolvers)
try:
    aw = ALL_PROVIDERS['watchanimeworld']
    aw_res = aw.search_anime("Naruto")
    if aw_res:
        slug = aw_res[0].get('slug') or aw_res[0].get('id')
        streams_data = aw.get_episode_streams(slug, 1, 1)
        streams = streams_data.get('streams', [])
        
        # Zephyr
        zephyr = next((s for s in streams if s.get('player') == 'zephyrflick'), None)
        if zephyr:
            resolved_z = resolve_stream(zephyr)
            if resolved_z and resolved_z[0].get('url'):
                test_targets.append({
                    'category': 'AniBox Provider',
                    'name': 'AnimeWorld: Naruto (Zephyr)',
                    'url': resolved_z[0]['url'],
                    'referer': 'https://play.zephyrix.org/'
                })
                print("  ✓ AnimeWorld (Zephyr) stream loaded!")

        # Abyss (Hindi MP4)
        abyss = next((s for s in streams if s.get('player') == 'abyss' and 'Hindi' in s.get('languages', [])), None)
        if abyss:
            resolved_a = resolve_stream(abyss)
            # Pick 720p or 1080p
            target_a = next((item for item in resolved_a if item.get('quality') == '720p'), resolved_a[0] if resolved_a else None)
            if target_a and target_a.get('url'):
                test_targets.append({
                    'category': 'AniBox Provider',
                    'name': f"AnimeWorld: Naruto Hindi ({target_a.get('quality', 'Direct')})",
                    'url': target_a['url'],
                    'referer': 'https://player.abyssplayer.com/'
                })
                print(f"  ✓ AnimeWorld (Abyss {target_a.get('quality')}) stream loaded!")
except Exception as e:
    print("  ✗ AnimeWorld fetch note:", e)

# 2c. MultiMovies (Vidmmo direct m3u8)
try:
    mm = ALL_PROVIDERS['multimovies']
    mm_res = mm.search_anime("Naruto")
    if mm_res:
        slug = mm_res[0].get('slug') or mm_res[0].get('id')
        streams_data = mm.get_episode_streams(slug, 1, 1)
        streams = streams_data.get('streams', [])
        vidmmo = next((s for s in streams if 'vidmmo.com' in s.get('url', '')), None)
        if vidmmo:
            test_targets.append({
                'category': 'AniBox Provider',
                'name': 'MultiMovies: Boruto (Vidmmo)',
                'url': vidmmo['url'],
                'referer': vidmmo.get('referer', 'https://vidout.pages.dev/')
            })
            print("  ✓ MultiMovies (Vidmmo) stream loaded!")
except Exception as e:
    print("  ✗ MultiMovies fetch note:", e)

print(f"\n[+] Total streams queued for ExoPlayer testing: {len(test_targets)}")
print("-" * 75)

all_reports = []
for idx, target in enumerate(test_targets, 1):
    print(f"\n[{idx}/{len(test_targets)}] Testing: {target['name']}")
    print(f"      Category: {target['category']}")
    print(f"      URL: {target['url'][:75]}...")
    report = test_stream_harness(
        name=target['name'],
        stream_url=target['url'],
        referer=target['referer'],
        sample_size_kb=1500
    )
    report['category'] = target['category']
    all_reports.append(report)

    print(f"      Status: {report['status_code']} | Format: {report['format']}")
    print(f"      TTFB: {report['ttfb_ms']} ms | Speed: {report['download_mb_s']} MB/s ({report['download_mbps']} Mbps)")
    print(f"      Seekable: {report['seekable']} (VOD endlist: {report['has_endlist']}, Mid-seek: {report['mid_seek_status']})")
    if report['audio_tracks']:
        print(f"      Audios: {', '.join(report['audio_tracks'][:5])}")
    if report['qualities']:
        print(f"      Qualities: {', '.join(report['qualities'][:4])}")
    print(f"      Rating: {report['grade']}")

# Save benchmark results
with open('exoplayer_benchmark_results.json', 'w', encoding='utf-8') as f:
    json.dump(all_reports, f, indent=2)

print("\n" + "=" * 80)
print(f"{'Provider / Source':<32} | {'Format':<12} | {'TTFB':<8} | {'Speed':<10} | {'Seek':<5} | {'Grade'}")
print("=" * 80)
for r in all_reports:
    speed_str = f"{r['download_mb_s']} MB/s"
    ttfb_str = f"{r['ttfb_ms']}ms"
    seek_str = "YES" if r['seekable'] else "NO"
    print(f"{r['name'][:32]:<32} | {r['format'][:12]:<12} | {ttfb_str:<8} | {speed_str:<10} | {seek_str:<5} | {r['grade']}")
print("=" * 80)
