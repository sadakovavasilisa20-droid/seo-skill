#!/usr/bin/env python3
"""Шаг 3. robots.txt и карта сайта (sitemap.xml) против того, что нашёл обход.

    python3 robots_sitemap.py --out audit/

Результат: audit/sitemap.json
"""
import argparse
import os
import re

from seo_lib import load_json, mark_step, norm_url, read_sitemap, save_json, sitemaps_from_robots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    a = ap.parse_args()
    crawl = load_json(os.path.join(a.out, "crawl.json"))
    if not crawl:
        raise SystemExit("Нет crawl.json: сначала запусти crawl.py")
    root = crawl["root"]

    r, robots_txt, sitemaps = sitemaps_from_robots(root)
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
        "in_sitemap_not_crawled": sorted(sm_set - set(by_url))[:200],
        "in_sitemap_only_no_links": sorted(u for u, p in by_url.items() if p.get("found_via") == "sitemap")[:200],
        "indexable_not_in_sitemap": sorted(crawled_ok - sm_set)[:200],
        "bad_urls_in_sitemap": issues_in_sitemap[:200],
        "note": "Обход упёрся в лимит страниц: часть адресов из sitemap не проверена."
                if crawl.get("limit_reached") else "",
    }
    save_json(os.path.join(a.out, "sitemap.json"), data)
    mark_step(a.out, "robots_sitemap", "done", f"sitemap: {len(sm_set)} URL")
    print(f"robots.txt: {'есть' if data['robots_txt_found'] else 'нет'}, sitemap: {len(sm_set)} URL")


if __name__ == "__main__":
    main()
