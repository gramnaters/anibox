#!/usr/bin/env python3
"""
ExoPlayer Stream Playability, Seekability & Speed Benchmark Harness for AniBox.

Benchmarks video streams for Android ExoPlayer / Stremio compatibility:
1. Playability: HTTP 200/206, CORS headers, Content-Type, Container format & magic bytes.
2. Multi-Audio & Quality: Detect audio tracks (Hindi, English, etc.) and resolution variants.
3. Seekability: HTTP Range request verification (bytes=0-1024 and mid-stream bytes),
   plus HLS #EXT-X-ENDLIST (VOD seekbar) and random-access mid-stream chunk fetch.
4. Speed & Buffer Latency: TTFB (Time to First Byte), throughput (MB/s & Mbps),
   and buffer health rating.
"""

import sys
import time
import re
import urllib.parse
import requests
import warnings

warnings.filterwarnings('ignore')

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36")


def test_stream_harness(name: str, stream_url: str, referer: str = "", sample_size_kb: int = 1500) -> dict:
    """Run full ExoPlayer playability, seekability, and throughput test on a stream."""
    report = {
        'name': name,
        'url': stream_url,
        'playable': False,
        'seekable': False,
        'status_code': None,
        'ttfb_ms': 0.0,
        'content_type': '',
        'format': 'unknown',
        'cors_allowed': False,
        'range_supported': False,
        'mid_seek_status': None,
        'has_endlist': None,
        'audio_tracks': [],
        'qualities': [],
        'download_mbps': 0.0,
        'download_mb_s': 0.0,
        'grade': 'FAIL',
        'notes': []
    }

    headers = {'User-Agent': DEFAULT_UA}
    if referer:
        headers['Referer'] = referer

    # ─── Step 1: Initial Handshake & TTFB ───
    t0 = time.perf_counter()
    try:
        r = requests.get(stream_url, headers=headers, timeout=12, stream=True)
        ttfb = (time.perf_counter() - t0) * 1000.0
        report['ttfb_ms'] = round(ttfb, 1)
        report['status_code'] = r.status_code
        report['content_type'] = r.headers.get('Content-Type', '')
        report['cors_allowed'] = r.headers.get('Access-Control-Allow-Origin') in ('*', 'null') or 'Access-Control-Allow-Origin' in r.headers
        
        initial_chunk = b""
        for chunk in r.iter_content(chunk_size=16384):
            initial_chunk += chunk
            if len(initial_chunk) >= 16384:
                break
        r.close()
    except Exception as e:
        report['notes'].append(f"Connection failed: {e}")
        return report

    if report['status_code'] not in (200, 206):
        report['notes'].append(f"Bad HTTP status: {report['status_code']}")
        return report

    # ─── Step 2: Format & Container Analysis ───
    text_preview = ""
    try:
        text_preview = initial_chunk.decode('utf-8', errors='ignore')
    except Exception:
        pass

    is_hls = '#EXTM3U' in text_preview
    is_mp4 = b'ftyp' in initial_chunk[:64]
    is_ts = len(initial_chunk) >= 188 and initial_chunk[0] == 0x47

    if is_hls:
        report['format'] = 'HLS (.m3u8)'
    elif is_mp4:
        report['format'] = 'Direct MP4'
    elif is_ts:
        report['format'] = 'Direct MPEG-TS'
    else:
        report['format'] = 'Octet-Stream / Direct'

    # ─── Step 3: HLS Playlist Deep Dive ───
    target_media_url = stream_url
    if is_hls:
        try:
            # Fetch complete playlist text
            full_r = requests.get(stream_url, headers=headers, timeout=10)
            playlist_text = full_r.text
            
            # Extract audio tracks
            audios = re.findall(r'#EXT-X-MEDIA:TYPE=AUDIO.*?NAME=[\"\']([^\"\']+)[\"\']', playlist_text)
            if not audios:
                audios = re.findall(r'#EXT-X-MEDIA:TYPE=AUDIO.*?LANGUAGE=[\"\']([^\"\']+)[\"\']', playlist_text)
            report['audio_tracks'] = list(dict.fromkeys(audios))

            # Extract resolution variants
            resolutions = re.findall(r'RESOLUTION=(\d+x\d+)', playlist_text)
            report['qualities'] = list(dict.fromkeys(resolutions))

            # Check if this is master playlist or media playlist
            raw_variants = [line.strip() for line in playlist_text.splitlines() if line.strip() and not line.startswith('#')]
            # Filter out non-video streams (like subtitle tracks, audio tracks, or storyboard tiles)
            video_variants = [
                v for v in raw_variants 
                if not any(x in v.lower() for x in ['subtitles', 'track_', 'tiles', 'thumb', '.vtt', '.srt'])
            ]
            variant_matches = video_variants if video_variants else raw_variants
            
            if resolutions and variant_matches:
                # Master playlist with variants -> Pick the best variant to test segments
                first_variant = variant_matches[0]
                variant_playlist_url = urllib.parse.urljoin(stream_url, first_variant)
                
                # Fetch variant playlist
                v_resp = requests.get(variant_playlist_url, headers=headers, timeout=10)
                v_text = v_resp.text
                report['has_endlist'] = '#EXT-X-ENDLIST' in v_text
                media_segments = [l.strip() for l in v_text.splitlines() if l.strip() and not l.startswith('#')]
                playlist_base_url = variant_playlist_url
            else:
                report['has_endlist'] = '#EXT-X-ENDLIST' in playlist_text
                media_segments = [
                    l for l in variant_matches 
                    if not any(x in l.lower() for x in ['subtitles', 'track_', 'tiles', '.vtt'])
                ]
                playlist_base_url = stream_url

            if media_segments:
                # Test target segment for download & seekability
                first_seg = media_segments[0]
                target_media_url = urllib.parse.urljoin(playlist_base_url, first_seg)
                
                # If multiple segments exist, test mid-stream seekability!
                mid_idx = len(media_segments) // 2
                mid_seg_url = urllib.parse.urljoin(playlist_base_url, media_segments[mid_idx])
                
                # Fetch mid segment
                try:
                    mid_r = requests.get(mid_seg_url, headers=headers, timeout=10, stream=True)
                    report['mid_seek_status'] = mid_r.status_code
                    mid_r.close()
                    report['seekable'] = (report['has_endlist'] is True) and (mid_r.status_code in (200, 206))
                except Exception as ex:
                    report['notes'].append(f"Mid-segment fetch error: {ex}")

        except Exception as e:
            report['notes'].append(f"HLS parsing note: {e}")

    # ─── Step 4: Seekability for MP4 / HTTP Range ───
    range_headers = dict(headers)
    range_headers['Range'] = 'bytes=0-1024'
    try:
        r_range = requests.get(target_media_url, headers=range_headers, timeout=10, stream=True)
        if r_range.status_code == 206:
            report['range_supported'] = True
            if not is_hls:
                # Test arbitrary mid-file seek Range
                mid_range = dict(headers)
                mid_range['Range'] = 'bytes=500000-502048'
                r_mid = requests.get(target_media_url, headers=mid_range, timeout=10, stream=True)
                report['mid_seek_status'] = r_mid.status_code
                report['seekable'] = r_mid.status_code == 206
                r_mid.close()
        r_range.close()
    except Exception as e:
        report['notes'].append(f"Range check note: {e}")

    # ─── Step 5: Speed & Throughput Benchmark ───
    # Download sample_size_kb (e.g. 1.5MB chunk) to measure real transfer rate
    try:
        t_dl_start = time.perf_counter()
        dl_headers = dict(headers)
        bytes_to_fetch = sample_size_kb * 1024
        dl_headers['Range'] = f"bytes=0-{bytes_to_fetch - 1}"
        
        r_dl = requests.get(target_media_url, headers=dl_headers, timeout=15, stream=True)
        total_downloaded = 0
        for chunk in r_dl.iter_content(chunk_size=32768):
            total_downloaded += len(chunk)
            if total_downloaded >= bytes_to_fetch:
                break
        duration = time.perf_counter() - t_dl_start
        r_dl.close()

        if duration > 0 and total_downloaded > 0:
            mb = total_downloaded / (1024.0 * 1024.0)
            report['download_mb_s'] = round(mb / duration, 2)
            report['download_mbps'] = round((mb * 8.0) / duration, 2)
            report['playable'] = True
    except Exception as e:
        report['notes'].append(f"Throughput measurement error: {e}")

    # ─── Step 6: ExoPlayer Grade Assessment ───
    if report['playable'] and report['seekable']:
        if report['download_mb_s'] >= 4.0 and report['ttfb_ms'] < 700:
            report['grade'] = 'EXCELLENT (ExoPlayer Native 4K/1080p)'
        elif report['download_mb_s'] >= 1.5:
            report['grade'] = 'GOOD (Smooth 1080p/720p)'
        else:
            report['grade'] = 'FAIR (Buffer Risk at high bitrates)'
    elif report['playable']:
        report['grade'] = 'PLAYABLE (Seek limitations / Live mode)'
    else:
        report['grade'] = 'FAILED'

    return report


if __name__ == '__main__':
    print("ExoPlayer Test Harness Module Loaded.")
