import json
import time
import urllib.request
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from statistics import mean

URL = os.getenv('LOADTEST_URL', 'http://localhost:5000/api/competencias/completas')
CONCURRENCY = int(os.getenv('LOADTEST_CONCURRENCY', '50'))
TIMEOUT = int(os.getenv('LOADTEST_TIMEOUT', '25'))
AUTH_TOKEN = os.getenv('LOADTEST_AUTH_TOKEN', '').strip()


def call_once() -> dict:
    start = time.perf_counter()
    req = urllib.request.Request(URL, method='GET')
    if AUTH_TOKEN:
        req.add_header('Authorization', f'Bearer {AUTH_TOKEN}')
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode('utf-8', errors='replace')
            elapsed_ms = (time.perf_counter() - start) * 1000
            status = resp.getcode()
            size = -1
            try:
                payload = json.loads(body)
                if isinstance(payload, list):
                    size = len(payload)
            except Exception:
                pass
            return {'ok': status == 200 and size > 0, 'status': status, 'ms': elapsed_ms, 'size': size, 'err': ''}
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {'ok': False, 'status': -1, 'ms': elapsed_ms, 'size': -1, 'err': str(exc)}


def percentile(values, p):
    if not values:
        return 0.0
    index = int((p / 100.0) * (len(values) - 1))
    return values[index]


if __name__ == '__main__':
    started = time.perf_counter()
    results = []

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(call_once) for _ in range(CONCURRENCY)]
        for fut in as_completed(futures):
            results.append(fut.result())

    wall_ms = (time.perf_counter() - started) * 1000
    oks = [r for r in results if r['ok']]
    fails = [r for r in results if not r['ok']]
    lat = sorted(r['ms'] for r in results)

    print('=== LOAD TEST (50 usuarios concurrentes) ===')
    print(f'URL: {URL}')
    print(f'Requests: {len(results)}')
    print(f'OK: {len(oks)}')
    print(f'FAIL: {len(fails)}')
    print(f'Wall time: {wall_ms:.1f} ms')

    if lat:
        print(f'Latency avg: {mean(lat):.1f} ms')
        print(f'Latency p50: {percentile(lat, 50):.1f} ms')
        print(f'Latency p95: {percentile(lat, 95):.1f} ms')
        print(f'Latency max: {max(lat):.1f} ms')

    payload_sizes = sorted(set(r['size'] for r in oks if r['size'] >= 0))
    print(f'Payload sizes: {payload_sizes}')

    if fails:
        print('--- Errores (muestra) ---')
        for row in fails[:5]:
            print(f"status={row['status']} ms={row['ms']:.1f} err={row['err'][:180]}")
