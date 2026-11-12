#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""并发探测 API 端点存活，输出 status.json。只测无需 Key 的条目。"""

import json
import os
import sys
import time
import ssl
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V1 = os.path.join(ROOT, "docs", "api", "v1")
STATUS = os.path.join(V1, "status.json")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
TIMEOUT = 8


def arg(name, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def probe(url):
    """返回 (code, ms)。code=0 表示网络层失败。"""
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "application/json,text/html,*/*",
        })
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as r:
            r.read(256)
            return r.status, int((time.time() - t0) * 1000)
    except urllib.error.HTTPError as e:
        return e.code, int((time.time() - t0) * 1000)
    except Exception:
        return 0, int((time.time() - t0) * 1000)


def alive(code):
    return 200 <= code < 500


def main():
    limit = int(arg("--limit", "0"))
    workers = int(arg("--workers", "32"))

    with open(os.path.join(V1, "apis.json"), encoding="utf-8") as f:
        apis = json.load(f)

    targets = [a for a in apis if a["auth"] == "No" and a.get("https")]
    if limit > 0:
        targets = targets[:limit]

    old = {}
    if os.path.exists(STATUS):
        try:
            with open(STATUS, encoding="utf-8") as f:
                old = json.load(f).get("items", {})
        except Exception:
            old = {}

    print("probing %d endpoints with %d workers" % (len(targets), workers), file=sys.stderr)
    items = dict(old)
    ok = 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(probe, a["url"]): a for a in targets}
        for i, fut in enumerate(as_completed(futs), 1):
            a = futs[fut]
            code, ms = fut.result()
            items[a["id"]] = {"code": code, "ms": ms, "alive": alive(code)}
            if alive(code):
                ok += 1
            if i % 50 == 0:
                print("  %d/%d  alive=%d  %.0fs" % (i, len(targets), ok, time.time() - t0), file=sys.stderr)

    out = {
        "checked": len(targets),
        "alive": ok,
        "dead": len(targets) - ok,
        "alive_rate": round(ok * 100.0 / max(len(targets), 1), 1),
        "elapsed_s": round(time.time() - t0, 1),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "items": items,
    }
    with open(STATUS, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    print(json.dumps({k: v for k, v in out.items() if k != "items"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
