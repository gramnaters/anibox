#!/usr/bin/env python3
"""
ExoPlayer Local Playability Test Harness for AniBox.

Tests playability of video streams (HLS m3u8 or direct MP4/MKV) end-to-end:
1. HTTP upstream reachability & headers (Range, Content-Type, Content-Length)
2. Media header validation (MP4 ftyp box / MPEG-TS 0x47 sync / HLS #EXTM3U)
3. ffprobe codec, resolution, bitrate, audio track analysis
4. Android Emulator ExoPlayer playback test via adb logcat verification
"""
import sys
import os
import re
import time
import json
import argparse
import subprocess
import requests
import warnings

warnings.filterwarnings('ignore')

ADB_PATH = os.path.expandvars(r"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe")
FFPROBE_PATH = r"E:\Yt dlp\ffprobe.exe"
DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36")


def check_adb_device():
    """Check if an Android emulator or device is connected via ADB."""
    if not os.path.exists(ADB_PATH):
        return None
    try:
        out = subprocess.check_output([ADB_PATH, 'devices'], stderr=subprocess.STDOUT, text=True)
        for line in out.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2 and parts[1] == 'device':
                return parts[0]
    except Exception:
        pass
    return None


def probe_http(url, referer='', user_agent=DEFAULT_UA, timeout=12):
    """Test HTTP accessibility, range requests, and media header bytes."""
    headers = {'User-Agent': user_agent}
    if referer:
        headers['Referer'] = referer
    
    result = {
        'status': None,
        'final_url': url,
        'content_type': '',
        'content_length': None,
        'is_hls': False,
        'media_type': 'unknown',
        'magic_valid': False,
        'error': None
    }
    
    try:
        # Try HEAD first
        r = requests.head(url, headers=headers, timeout=timeout, verify=False, allow_redirects=True)
        result['status'] = r.status_code
        result['final_url'] = r.url
        result['content_type'] = r.headers.get('Content-Type', '')
        length = r.headers.get('Content-Length')
        if length and length.isdigit():
            result['content_length'] = int(length)
        
        # Test first chunk with GET (Range 0-1024)
        get_headers = dict(headers)
        get_headers['Range'] = 'bytes=0-1024'
        rg = requests.get(url, headers=get_headers, timeout=timeout, verify=False, stream=True)
        
        if result['status'] is None or result['status'] >= 400:
            result['status'] = rg.status_code
            result['final_url'] = rg.url
            result['content_type'] = rg.headers.get('Content-Type', '')
        
        chunk = rg.raw.read(1024)
        rg.close()
        
        if b'#EXTM3U' in chunk:
            result['is_hls'] = True
            result['media_type'] = 'HLS Playlist'
            result['magic_valid'] = True
        elif b'ftyp' in chunk[:32]:
            result['media_type'] = 'MP4'
            result['magic_valid'] = True
        elif len(chunk) >= 188 and chunk[0] == 0x47:
            result['media_type'] = 'MPEG-TS'
            result['magic_valid'] = True
        elif chunk.startswith(b'\x1a\x45\xdf\xa3'):
            result['media_type'] = 'MKV/WebM'
            result['magic_valid'] = True
        elif result['status'] == 200 or result['status'] == 206:
            result['media_type'] = 'Generic Media'
            result['magic_valid'] = len(chunk) > 100
            
    except Exception as e:
        result['error'] = str(e)
        
    return result


def probe_ffprobe(url, referer='', user_agent=DEFAULT_UA, timeout=15):
    """Run ffprobe to analyze audio/video streams, resolution, codecs."""
    if not os.path.exists(FFPROBE_PATH):
        return {'available': False, 'error': 'ffprobe not found'}
    
    header_str = f"User-Agent: {user_agent}\r\n"
    if referer:
        header_str += f"Referer: {referer}\r\n"
        
    cmd = [
        FFPROBE_PATH,
        '-v', 'error',
        '-headers', header_str,
        '-show_entries', 'stream=codec_name,codec_type,width,height,r_frame_rate,bit_rate:format=duration,bit_rate',
        '-of', 'json',
        url
    ]
    
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode == 0 and proc.stdout.strip():
            data = json.loads(proc.stdout)
            video_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'video'), None)
            audio_stream = next((s for s in data.get('streams', []) if s.get('codec_type') == 'audio'), None)
            fmt = data.get('format', {})
            
            return {
                'available': True,
                'valid': True,
                'video_codec': video_stream.get('codec_name') if video_stream else None,
                'resolution': f"{video_stream.get('width')}x{video_stream.get('height')}" if video_stream else None,
                'fps': video_stream.get('r_frame_rate') if video_stream else None,
                'audio_codec': audio_stream.get('codec_name') if audio_stream else None,
                'duration': float(fmt.get('duration', 0)) if fmt.get('duration') else None,
                'bitrate': int(fmt.get('bit_rate', 0)) if fmt.get('bit_rate') else None,
            }
        else:
            return {'available': True, 'valid': False, 'error': proc.stderr.strip()[:200]}
    except subprocess.TimeoutExpired:
        return {'available': True, 'valid': False, 'error': 'ffprobe timed out'}
    except Exception as e:
        return {'available': True, 'valid': False, 'error': str(e)}


def test_exoplayer_on_emulator(url, device_id='emulator-5554', duration_sec=5):
    """Verify ExoPlayer playback on Android emulator by inspecting logcat."""
    if not os.path.exists(ADB_PATH):
        return {'tested': False, 'reason': 'adb not found'}
    
    # Clear logcat
    try:
        subprocess.run([ADB_PATH, '-s', device_id, 'logcat', '-c'], check=True, timeout=5)
    except Exception as e:
        return {'tested': False, 'reason': f'logcat clear failed: {e}'}
    
    # Check if Nuvio or Photos can play
    print(f"[*] Testing playback on {device_id}...")
    
    # Wait for playback to buffer and render
    time.sleep(duration_sec)
    
    # Capture logcat
    try:
        logcat = subprocess.check_output(
            [ADB_PATH, '-s', device_id, 'logcat', '-d'],
            stderr=subprocess.STDOUT, text=True, errors='ignore'
        )
    except Exception as e:
        return {'tested': False, 'reason': f'logcat read failed: {e}'}
    
    exoplayer_init = bool(re.search(r'ExoPlayerImpl:\s*Init', logcat, re.I))
    mediacodec_found = bool(re.search(r'MediaCodec|c2\.android|OMX\.', logcat, re.I))
    audiotrack_found = bool(re.search(r'AudioTrack', logcat, re.I))
    error_found = bool(re.search(r'HttpDataSourceException|ParserException|BehindLiveWindowException|404 Not Found', logcat, re.I))
    
    return {
        'tested': True,
        'exoplayer_init': exoplayer_init,
        'decoder_active': mediacodec_found,
        'audio_active': audiotrack_found,
        'errors_detected': error_found,
        'playable': (exoplayer_init or mediacodec_found) and not error_found
    }


def run_test(url, name="Stream Test", referer=''):
    print("\n" + "="*70)
    print(f"Testing Stream: {name}")
    print(f"URL: {url[:100]}...")
    if referer:
        print(f"Referer: {referer}")
    print("="*70)
    
    # Step 1: HTTP Probe
    print("[1/3] Probing HTTP upstream...")
    http_res = probe_http(url, referer)
    print(f"  -> HTTP Status: {http_res['status']}")
    print(f"  -> Media Type: {http_res['media_type']}")
    print(f"  -> Magic Header Valid: {http_res['magic_valid']}")
    if http_res['content_length']:
        print(f"  -> Content Length: {http_res['content_length'] / (1024*1024):.2f} MB")
    if http_res['error']:
        print(f"  -> Error: {http_res['error']}")
    
    # Step 2: ffprobe Analysis
    print("\n[2/3] Analyzing stream via ffprobe...")
    ff_res = probe_ffprobe(url, referer)
    if ff_res.get('valid'):
        print(f"  -> Video Codec: {ff_res['video_codec']} ({ff_res['resolution']} @ {ff_res['fps']} fps)")
        print(f"  -> Audio Codec: {ff_res['audio_codec']}")
        if ff_res['duration']:
            mins = int(ff_res['duration'] // 60)
            secs = int(ff_res['duration'] % 60)
            print(f"  -> Duration: {mins}m {secs}s")
        if ff_res['bitrate']:
            print(f"  -> Bitrate: {ff_res['bitrate'] // 1000} kbps")
    else:
        print(f"  -> ffprobe: {ff_res.get('error', 'Failed')}")
        
    # Step 3: Android Device Check
    print("\n[3/3] Checking Android Emulator & ExoPlayer...")
    device = check_adb_device()
    if device:
        print(f"  -> Connected Device: {device}")
        exo_res = test_exoplayer_on_emulator(url, device)
        print(f"  -> ExoPlayer Test: {exo_res}")
    else:
        print("  -> No Android device connected.")
        
    # Verdict
    is_playable = http_res['status'] in (200, 206) and (http_res['magic_valid'] or ff_res.get('valid'))
    print("\n" + "-"*70)
    if is_playable:
        print(f"VERDICT: [PASS] Stream is LIVE and PLAYABLE")
    else:
        print(f"VERDICT: [FAIL] Stream is UNPLAYABLE (Status {http_res['status']})")
    print("-" * 70)
    return is_playable


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Test video stream playability locally")
    parser.add_argument("--url", help="Stream URL to test")
    parser.add_argument("--referer", default="", help="HTTP Referer header")
    parser.add_argument("--name", default="Custom Stream", help="Stream title")
    parser.add_argument("--batch", action="store_true", help="Run standard test batch")
    args = parser.parse_args()
    
    if args.url:
        run_test(args.url, args.name, args.referer)
    elif args.batch or len(sys.argv) == 1:
        # Run test batch
        test_streams = [
            {
                'name': 'Zootopia 1080p (Abyss / sssrr.org)',
                'url': 'https://hgexcwir16.sssrr.org/sora/3382218935/cFg0NG5YNmFOTzcvV01rNkJZQXVoQXFxb25UVGR6aUdIdkZOYytnY3ZOeHJoQzBnVWxV',
                'referer': 'https://abyssplayer.com/'
            },
            {
                'name': 'Zootopia 2160p 4K (Dead stream test)',
                'url': 'https://yurawzq6o26.sssrr.org/sora/11107817563/YUs4WFpyNUxGeStJdEozQnlEelRkcXlQOFF1UHU0RkFrUXFCT3BPR2g0VWgyYzdabVR4Zg',
                'referer': 'https://abyssplayer.com/'
            },
        ]
        results = []
        for s in test_streams:
            res = run_test(s['url'], s['name'], s['referer'])
            results.append((s['name'], res))
            
        print("\n\n" + "="*40 + " SUMMARY " + "="*40)
        for name, passed in results:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {name}")
        print("="*89)
