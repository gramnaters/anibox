#!/usr/bin/env python3
"""
Full Stress Benchmark:
Python Flask Codebase vs Cloudflare Worker Edge Scraper.
"""
import time
import json
import statistics
import concurrent.futures
import requests
import warnings

warnings.filterwarnings('ignore')

RENDER_URL = "https://anibox-4l4u.onrender.com"
LOCAL_PY_URL = "http://127.0.0.1:5001"
LOCAL_WORKER_URL = "http://127.0.0.1:8787"

def req(url, timeout=25):
    t0 = time.perf_counter()
    try:
        r = requests.get(url, timeout=timeout, verify=False)
        dur = time.perf_counter() - t0
        return {'status': r.status_code, 'time': dur, 'bytes': len(r.content), 'ok': r.status_code == 200, 'err': None}
    except Exception as e:
        dur = time.perf_counter() - t0
        return {'status': 0, 'time': dur, 'bytes': 0, 'ok': False, 'err': str(e)}

def stress(url, n=10, c=5, timeout=25):
    results = []
    t0 = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=c) as ex:
        futures = [ex.submit(req, url, timeout) for _ in range(n)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())
    total_dur = time.perf_counter() - t0
    
    ok = [r for r in results if r['ok']]
    times = [r['time'] * 1000 for r in ok]
    
    return {
        'total': n,
        'concurrency': c,
        'ok_count': len(ok),
        'fail_count': n - len(ok),
        'total_time': total_dur,
        'rps': n / total_dur if total_dur > 0 else 0,
        'min_ms': min(times) if times else 0,
        'avg_ms': statistics.mean(times) if times else 0,
        'median_ms': statistics.median(times) if times else 0,
        'max_ms': max(times) if times else 0,
    }

def main():
    print("=" * 80, flush=True)
    print("      BENCHMARK & STRESS COMPARISON: PYTHON FLASK vs CLOUDFLARE WORKER", flush=True)
    print("=" * 80, flush=True)

    # -------------------------------------------------------------
    # 1. Manifest Latency
    # -------------------------------------------------------------
    print("\n--- TEST 1: MANIFEST LATENCY (Single Request) ---", flush=True)
    
    targets = [
        ("Cloudflare Worker (Edge / V8)", f"{LOCAL_WORKER_URL}/manifest.json"),
        ("Python Flask (Local)", f"{LOCAL_PY_URL}/manifest.json"),
        ("Python Flask (Render Live)", f"{RENDER_URL}/manifest.json"),
    ]

    for label, url in targets:
        # Run 3 times to get avg
        samples = [req(url) for _ in range(3)]
        times = [s['time'] * 1000 for s in samples if s['ok']]
        avg = statistics.mean(times) if times else 0
        status = samples[0]['status']
        print(f"  {label:<32}: Status {status} | Avg: {avg:6.1f} ms | Min: {min(times):6.1f} ms", flush=True)

    # -------------------------------------------------------------
    # 2. Concurrency Stress on Manifest (20 requests, 10 concurrent)
    # -------------------------------------------------------------
    print("\n--- TEST 2: CONCURRENCY STRESS ON MANIFEST (20 requests @ 10 concurrent) ---", flush=True)
    for label, url in targets:
        res = stress(url, n=20, c=10)
        print(f"  {label:<32}: {res['ok_count']}/{res['total']} OK | Avg: {res['avg_ms']:6.1f} ms | Max: {res['max_ms']:6.1f} ms | RPS: {res['rps']:5.1f} req/s", flush=True)

    # -------------------------------------------------------------
    # 3. Stream Scrape Latency (Cold search)
    # -------------------------------------------------------------
    print("\n--- TEST 3: LIVE STREAM SCRAPING (Dragon Ball GT Ep 1) ---", flush=True)
    stream_targets = [
        ("Cloudflare Worker (Edge / V8)", f"{LOCAL_WORKER_URL}/stream/series/hd%3Amultimovies%3Aseries~dragon-ball-gt-171982%3A1%3A1.json"),
        ("Python Flask (Local)", f"{LOCAL_PY_URL}/stream/series/hd%3Amultimovies%3Aseries~dragon-ball-gt-171982%3A1%3A1.json"),
        ("Python Flask (Render Live)", f"{RENDER_URL}/stream/series/hd%3Amultimovies%3Aseries~dragon-ball-gt-171982%3A1%3A1.json"),
    ]

    for label, url in stream_targets:
        print(f"  Probing {label}...", flush=True)
        r = req(url, timeout=35)
        if r['ok']:
            try:
                j = json.loads(requests.get(url, timeout=35, verify=False).text)
                streams_count = len(j.get('streams', []))
            except:
                streams_count = 'unknown'
            print(f"    -> OK: {r['time']:.2f}s | Streams found: {streams_count} | Payload: {r['bytes']} bytes", flush=True)
        else:
            print(f"    -> FAILED ({r['status']}): {r['time']:.2f}s | Error: {r['err']}", flush=True)

    # -------------------------------------------------------------
    # 4. Stream Scraper Concurrency Stress (4 requests @ 2 concurrent)
    # -------------------------------------------------------------
    print("\n--- TEST 4: SCRAPER CONCURRENCY UNDER LOAD (4 requests @ 2 concurrent) ---", flush=True)
    for label, url in stream_targets:
        print(f"  Benchmarking {label}...", flush=True)
        res = stress(url, n=4, c=2, timeout=40)
        print(f"    -> {res['ok_count']}/{res['total']} OK | Avg: {res['avg_ms']/1000:5.2f}s | Total: {res['total_time']:5.2f}s | Throughput: {res['rps']:4.2f} req/s", flush=True)

    print("\n" + "=" * 80, flush=True)
    print("BENCHMARK COMPLETED", flush=True)
    print("=" * 80, flush=True)

if __name__ == '__main__':
    main()
