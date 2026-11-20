#!/usr/bin/env python3
"""Шаг 3. robots.txt и карта сайта (sitemap.xml) против того, что нашёл обход.

    python3 robots_sitemap.py --out audit/

Результат: audit/sitemap.json
"""
import argparse
import os
import re
import xml.etree.ElementTree as ET

from seo_lib import fetch, load_json, mark_step, norm_url, save_json


def read_sitemap(url, seen, limit=20):
    """Читает sitemap и sitemap index (рекурсивно, до limit файлов)."""
    if url in seen or len(seen) >= limit:
        return []
    seen.add(url)
    r = fetch(url)
    if r["status"] != 200:
        return []
    try:
        root = ET.fromstring(r["body"].encode("utf-8"))
    except ET.ParseError:
        return []
    ns = re.match(r"\{.*\}", root.tag)
    ns = ns.group(0) if ns else ""
    if root.tag.endswith("sitemapindex"):
        urls = []
        for loc in root.iter(ns + "loc"):
            urls += read_sitemap(loc.text.strip(), seen, limit)
        return urls
    return [loc.text.strip() for loc in root.iter(ns + "loc") if loc.text]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    a = ap.parse_args()
    crawl = load_json(os.path.join(a.out, "crawl.json"))
    if not crawl:
        raise SystemExit("Нет crawl.json: сначала запусти crawl.py")
    root = crawl["root"]

    r = fetch(root + "/robots.txt")
    robots_txt = r["body"] if r["status"] == 200 else ""
    sitemaps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots_txt) or [root + "/sitemap.xml"]
    disallow = re.findall(r"(?im)^\s*disallow:\s*(\S*)", robots_txt)
    host_directive = re.findall(r"(?im)^\s*host:\s*(\S+)", robots_txt)

    seen, sm_urls = set(), []
    for s in sitemaps:
        sm_urls += read_sitemap(s, seen)
    sm_set = {norm_url(u, root) for u in sm_urls}
    by_url = {p["url"]: p for p in crawl["pages"]}

    def indexable(p):
        return p.get("status") == 200 and "noindex" not in p.get("meta_robots", "") \
            and "noindex" not in p.get("x_robots", "").lower()

    crawled_ok = {u for u, p in by_url.items() if indexable(p)}
    issues_in_sitemap = []
    for u in sorted(sm_set):
        p = by_url.get(u)
        if p and not indexable(p):
            why = "noindex" if p.get("status") == 200 else f"код {p.get('status')}"
            issues_in_sitemap.append({"url": u, "problem": why})
        elif p and p.get("redirects"):
            issues_in_sitemap.append({"url": u, "problem": "редирект"})

    data = {
        "robots_txt_found": r["status"] == 200,
        "robots_disallow": disallow,
        "robots_blocks_all": "/" in disallow,
        "host_directive": host_directive,
        "sitemaps": sorted(seen),
        "sitemap_found": bool(sm_urls),
        "sitemap_urls": len(sm_set),
        "in_sitemap_not_found_by_links": sorted(sm_set - set(by_url))[:200],
        "indexable_not_in_sitemap": sorted(crawled_ok - sm_set)[:200],
        "bad_urls_in_sitemap": issues_in_sitemap[:200],
        "note": "Если обход упёрся в лимит страниц, часть URL из sitemap попадёт в «не найдены по ссылкам» ложно."
                if crawl.get("limit_reached") else "",
    }
    save_json(os.path.join(a.out, "sitemap.json"), data)
    mark_step(a.out, "robots_sitemap", "done", f"sitemap: {len(sm_set)} URL")
    print(f"robots.txt: {'есть' if data['robots_txt_found'] else 'нет'}, sitemap: {len(sm_set)} URL")


if __name__ == "__main__":
    main()
