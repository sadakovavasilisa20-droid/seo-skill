#!/usr/bin/env python3
"""Шаг 2. Обход сайта: собирает SEO-данные всех страниц.

    python3 crawl.py https://example.com --out audit/ --max-pages 200

Идёт в ширину от стартовой страницы, только по своему домену, соблюдает robots.txt.
Потом догружает адреса из sitemap, которые не нашлись по ссылкам: так находятся страницы-сироты.
На них оставлено 20% лимита. Результат: audit/crawl.json
"""
import argparse
import os
import time
import urllib.robotparser
from collections import deque
from urllib.parse import urlparse

from seo_lib import (SKIP_EXT, UA, analyze_html, fetch, mark_step, norm_url, read_sitemap, same_site,
                     save_json, sitemaps_from_robots)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="audit")
    ap.add_argument("--max-pages", type=int, default=200)
    ap.add_argument("--delay", type=float, default=0.3, help="пауза между запросами, сек")
    a = ap.parse_args()

    start = norm_url(a.url if a.url.startswith("http") else "https://" + a.url, a.url)
    root = "{0.scheme}://{0.netloc}".format(urlparse(start))
    rp = urllib.robotparser.RobotFileParser(root + "/robots.txt")
    try:
        rp.read()
    except Exception:
        rp = None

    queue, seen, pages, blocked = deque([(start, 0, "links")]), {start}, [], []
    link_budget = max(1, int(a.max_pages * 0.8))
    sitemap_added = False
    links_left = 0
    while len(pages) < a.max_pages:
        if not queue or (len(pages) >= link_budget and not sitemap_added):
            if sitemap_added:
                break
            sitemap_added = True
            links_left = len(queue)  # сколько ссылок не успели обойти к моменту догрузки sitemap
            sm = []
            for s_url in sitemaps_from_robots(root)[2]:
                sm += read_sitemap(s_url)
            extra = [u for u in (norm_url(x, root) for x in sm) if u and u not in seen and same_site(u, start)]
            for u in extra:
                seen.add(u)
            queue = deque([(u, None, "sitemap") for u in extra] + list(queue))
            if not queue:
                break
            continue
        url, depth, via = queue.popleft()
        if rp and not rp.can_fetch(UA, url):
            blocked.append(url)
            continue
        r = fetch(url)
        ctype = r["headers"].get("content-type", "")
        page = {"url": url, "depth": depth, "found_via": via, "status": r["status"], "error": r.get("error"),
                "final_url": r["final_url"], "redirects": r["redirects"], "seconds": r["seconds"],
                "html_kb": round(len(r["body"].encode("utf-8")) / 1024, 1),
                "x_robots": r["headers"].get("x-robots-tag", "")}
        if r["status"] == 200 and "html" in ctype:
            page.update(analyze_html(r["body"], r["final_url"]))
            if via == "links":
                for link in page["internal_links"]:
                    u = link["url"]
                    if u not in seen and same_site(u, start) and not SKIP_EXT.search(urlparse(u).path):
                        seen.add(u)
                        queue.append((u, depth + 1, "links"))
        pages.append(page)
        print(f"[{len(pages)}/{a.max_pages}] {r['status']} {url}")
        time.sleep(a.delay)

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + os.urandom(3).hex()
    data = {"run_id": run_id, "start": start, "root": root, "crawled_at": time.strftime("%Y-%m-%d %H:%M"),
            "max_pages": a.max_pages, "limit_reached": bool(queue), "not_crawled_in_queue": len(queue),
            "from_sitemap_only": sum(1 for p in pages if p["found_via"] == "sitemap"),
            "links_exhausted": links_left == 0,
            "blocked_by_robots": blocked, "pages": pages}
    save_json(os.path.join(a.out, "crawl.json"), data)
    note = f"{len(pages)} страниц" + (", упёрлись в лимит" if queue else "")
    mark_step(a.out, "crawl", "done", note, run_id=run_id)
    print("Готово:", note)


if __name__ == "__main__":
    main()
