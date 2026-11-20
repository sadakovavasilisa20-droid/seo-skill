#!/usr/bin/env python3
"""Шаг 2. Обход сайта: собирает SEO-данные всех страниц.

    python3 crawl.py https://example.com --out audit/ --max-pages 200

Идёт в ширину от стартовой страницы, только по своему домену, соблюдает robots.txt.
Результат: audit/crawl.json
"""
import argparse
import os
import time
import urllib.robotparser
from collections import deque
from urllib.parse import urlparse

from seo_lib import SKIP_EXT, UA, analyze_html, fetch, mark_step, same_site, save_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="audit")
    ap.add_argument("--max-pages", type=int, default=200)
    ap.add_argument("--delay", type=float, default=0.3, help="пауза между запросами, сек")
    a = ap.parse_args()

    start = a.url if a.url.startswith("http") else "https://" + a.url
    root = "{0.scheme}://{0.netloc}".format(urlparse(start))
    rp = urllib.robotparser.RobotFileParser(root + "/robots.txt")
    try:
        rp.read()
    except Exception:
        rp = None

    queue, seen, pages, blocked = deque([(start, 0)]), {start}, [], []
    while queue and len(pages) < a.max_pages:
        url, depth = queue.popleft()
        if rp and not rp.can_fetch(UA, url):
            blocked.append(url)
            continue
        r = fetch(url)
        ctype = r["headers"].get("content-type", "")
        page = {"url": url, "depth": depth, "status": r["status"], "error": r.get("error"),
                "final_url": r["final_url"], "redirects": r["redirects"], "seconds": r["seconds"],
                "html_kb": round(len(r["body"].encode("utf-8")) / 1024, 1),
                "x_robots": r["headers"].get("x-robots-tag", "")}
        if r["status"] == 200 and "html" in ctype:
            page.update(analyze_html(r["body"], r["final_url"]))
            for link in page["internal_links"]:
                u = link["url"]
                if u not in seen and same_site(u, start) and not SKIP_EXT.search(urlparse(u).path):
                    seen.add(u)
                    queue.append((u, depth + 1))
        pages.append(page)
        print(f"[{len(pages)}/{a.max_pages}] {r['status']} {url}")
        time.sleep(a.delay)

    data = {"start": start, "root": root, "crawled_at": time.strftime("%Y-%m-%d %H:%M"),
            "max_pages": a.max_pages, "limit_reached": bool(queue), "not_crawled_in_queue": len(queue),
            "blocked_by_robots": blocked, "pages": pages}
    save_json(os.path.join(a.out, "crawl.json"), data)
    note = f"{len(pages)} страниц" + (", упёрлись в лимит" if queue else "")
    mark_step(a.out, "crawl", "done", note)
    print("Готово:", note)


if __name__ == "__main__":
    main()
