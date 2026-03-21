"""
API smoke tests — verify all V2 dashboard endpoints return valid data.

Usage:
    /tmp/druck_venv/bin/python tools/test_api.py
    /tmp/druck_venv/bin/python tools/test_api.py --base http://localhost:8000

Exits 0 if all checks pass, 1 if any fail.
"""
import sys
import json
import time
import argparse
import urllib.request
import urllib.error

def check(name: str, url: str, method: str = "GET", *, key: str | None = None, min_list: int = 0) -> bool:
    """Hit `url`, assert status 200, optionally assert a key exists or list is non-empty."""
    try:
        req = urllib.request.Request(url, method=method,
                                     headers={"Content-Length": "0"} if method == "POST" else {})
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"  ✗ {name} — HTTP {e.code}")
        return False
    except Exception as e:
        print(f"  ✗ {name} — {e}")
        return False

    if status != 200:
        print(f"  ✗ {name} — status {status}")
        return False

    if key and key not in body:
        print(f"  ✗ {name} — missing key '{key}' in response")
        return False

    if min_list > 0:
        lst = body if isinstance(body, list) else body.get(key, [])
        if len(lst) < min_list:
            print(f"  ✗ {name} — expected ≥{min_list} items, got {len(lst)}")
            return False

    print(f"  ✓ {name}")
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    print(f"\nAPI Smoke Tests — {base}\n{'─' * 40}")
    t0 = time.time()
    results = []

    # Core V2 endpoints
    results.append(check("terminal feed",     f"{base}/api/v2/terminal",          key="sectors"))
    results.append(check("headlines",         f"{base}/api/v2/headlines",         key="headlines"))
    results.append(check("stock panel AAPL",  f"{base}/api/v2/stock/AAPL",        key="prices"))
    results.append(check("cache clear",       f"{base}/api/v2/cache/clear",       method="POST"))

    # Gate / Alpha endpoints
    results.append(check("gates",             f"{base}/api/v2/gates"))
    results.append(check("alpha stack G8+",   f"{base}/api/alpha/stack?min_gate=8"))

    # Portfolio
    results.append(check("portfolio",         f"{base}/api/portfolio"))

    # Macro / breadth (V1 endpoints still used)
    results.append(check("macro scores",      f"{base}/api/macro/scores"))

    elapsed = time.time() - t0
    passed = sum(results)
    failed = len(results) - passed

    print(f"\n{'─' * 40}")
    print(f"  {passed}/{len(results)} passed  ({elapsed:.1f}s)")

    if failed:
        print(f"  {failed} FAILED — fix before deploying\n")
        sys.exit(1)
    else:
        print("  All checks passed ✓\n")
        sys.exit(0)


if __name__ == "__main__":
    main()
