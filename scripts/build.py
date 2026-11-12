#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抓 public-apis README，解析成结构化 JSON API 索引。"""

import json
import os
import re
import sys
import urllib.request
import hashlib
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "api", "v1")
DATA = os.path.join(ROOT, "data")

SOURCES = [
    ("public-apis", "https://raw.githubusercontent.com/public-apis/public-apis/master/README.md",
     "public-apis.md"),
    ("public-api-lists", "https://raw.githubusercontent.com/public-api-lists/public-api-lists/master/README.md",
     "public-api-lists.md"),
]

UA = "Mozilla/5.0 (compatible; free-api-hub/1.0)"
CACHE = os.path.join(ROOT, "data", "cache")
OFFLINE = "--offline" in sys.argv


def fetch(url, cache_name, timeout=20):
    """优先读本地缓存，缓存缺失或强制在线时才走网络。网络失败回退缓存。"""
    cp = os.path.join(CACHE, cache_name)
    if OFFLINE:
        if os.path.exists(cp):
            with open(cp, encoding="utf-8", errors="ignore") as f:
                return f.read()
        raise RuntimeError("offline mode, no cache: %s" % cp)
    if os.path.exists(cp):
        with open(cp, encoding="utf-8", errors="ignore") as f:
            return f.read()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    data = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read().decode("utf-8", "ignore")
    except Exception as e:
        print("[net-fail] %s: %s" % (url, e), file=sys.stderr)
        raise
    os.makedirs(CACHE, exist_ok=True)
    with open(cp, "w", encoding="utf-8") as f:
        f.write(data)
    return data


def slug(s):
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "item"


def parse_public_apis(md, source):
    """解析 public-apis 风格 markdown 表格。"""
    rows = []
    cat = ""
    skip = False
    for line in md.split("\n"):
        line = line.rstrip()
        m = re.match(r"^#{2,3}\s+(.+?)\s*$", line)
        if m:
            title = m.group(1).strip()
            cat = title
            skip = bool(re.search(r"apilayer|sponsor|contribut", title, re.I))
            continue
        if skip:
            continue
        if not line.startswith("| ["):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        link = re.match(r"\[(.+?)\]\((.+?)\)", cells[0])
        if not link:
            continue
        name, url = link.group(1).strip(), link.group(2).strip()
        desc, auth, https, cors = cells[1], cells[2], cells[3], cells[4]
        auth = auth.strip("`").strip()
        if auth.lower() in ("", "no", "none"):
            auth = "No"
        cors = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", cors)
        if "postman" in url.lower() or "apilayer.com" in url.lower():
            continue
        rows.append({
            "name": name,
            "url": url,
            "description": desc.replace("|", "/"),
            "category": cat or "Uncategorized",
            "auth": auth,
            "https": https.lower() in ("yes", "true"),
            "cors": cors or "-",
            "source": source,
        })
    return rows


def dedupe(rows):
    seen = {}
    for r in rows:
        key = (r["name"].lower(), r["url"].rstrip("/"))
        if key in seen:
            continue
        seen[key] = r
    out = []
    used = {}
    for r in seen.values():
        base = slug(r["name"])
        n = used.get(base, 0)
        used[base] = n + 1
        r["id"] = base if n == 0 else "%s-%d" % (base, n + 1)
        out.append(r)
    return out


def load_llm():
    p = os.path.join(DATA, "llm.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return []


def main():
    all_rows = []
    report = []
    for name, url, cache_name in SOURCES:
        try:
            md = fetch(url, cache_name)
            rows = parse_public_apis(md, name)
            all_rows.extend(rows)
            report.append({"source": name, "url": url, "parsed": len(rows), "ok": True})
            print("[ok] %s -> %d rows" % (name, len(rows)), file=sys.stderr)
        except Exception as e:
            report.append({"source": name, "url": url, "parsed": 0, "ok": False, "error": str(e)})
            print("[fail] %s: %s" % (name, e), file=sys.stderr)

    rows = dedupe(all_rows)
    if not rows:
        print("no data parsed, abort", file=sys.stderr)
        sys.exit(1)

    rows.sort(key=lambda r: (r["category"].lower(), r["name"].lower()))

    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(OUT, "category"), exist_ok=True)

    cats = defaultdict(list)
    for r in rows:
        cats[r["category"]].append(r)

    meta = {
        "version": "v1",
        "generated_at": hashlib.md5(json.dumps(rows, sort_keys=True).encode()).hexdigest()[:12],
        "total": len(rows),
        "nokey": sum(1 for r in rows if r["auth"] == "No"),
        "categories": len(cats),
        "sources": report,
    }

    def dump(path, obj, pretty=False):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2 if pretty else None,
                      separators=None if pretty else (",", ":"))

    dump(os.path.join(OUT, "index.json"), meta, True)
    dump(os.path.join(OUT, "apis.json"), rows)
    dump(os.path.join(OUT, "nokey.json"), [r for r in rows if r["auth"] == "No"])
    dump(os.path.join(OUT, "llm.json"), load_llm(), True)

    cat_meta = []
    for c, items in sorted(cats.items()):
        cs = slug(c)
        dump(os.path.join(OUT, "category", cs + ".json"), items)
        cat_meta.append({
            "name": c,
            "slug": cs,
            "count": len(items),
            "nokey": sum(1 for r in items if r["auth"] == "No"),
            "path": "/api/v1/category/%s.json" % cs,
        })
    dump(os.path.join(OUT, "categories.json"), cat_meta, True)

    auth_counter = Counter(r["auth"] for r in rows)
    stats = {
        "total": len(rows),
        "by_auth": dict(auth_counter.most_common()),
        "by_category": {m["name"]: m["count"] for m in cat_meta},
        "cors_yes": sum(1 for r in rows if "yes" in r["cors"].lower()),
        "https": sum(1 for r in rows if r["https"]),
        "generated_at_utc": meta["generated_at"],
    }
    dump(os.path.join(OUT, "stats.json"), stats, True)

    print(json.dumps(meta, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
