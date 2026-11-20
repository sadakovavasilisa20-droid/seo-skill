#!/usr/bin/env python3
"""Шаг 9а. Конкуренты: сравниваем сайт с сайтами из брифа по тем же признакам.

    python3 competitors.py --out audit/
    python3 competitors.py --out audit/ --skip "клиент не назвал конкурентов"

Конкуренты берутся из brief.json (поле competitors). По каждому: главная страница
(title, description, H1, объём текста, микроразметка, Open Graph, HTTPS) и размер sitemap.
Это сравнение витрин, а не позиций: позиции нужно смотреть в выдаче.
Результат: audit/competitors.json
"""
import argparse
import os

from seo_lib import analyze_html, fetch, load_json, mark_step, read_sitemap, save_json, sitemaps_from_robots
from urllib.parse import urlparse


def snapshot(url):
    url = url if url.startswith("http") else "https://" + url
    r = fetch(url)
    if r["status"] != 200:
        return {"url": url, "error": f"код {r['status'] or r.get('error')}"}
    d = analyze_html(r["body"], r["final_url"])
    root = "{0.scheme}://{0.netloc}".format(urlparse(r["final_url"]))
    sm = []
    for s in sitemaps_from_robots(root)[2][:3]:
        sm += read_sitemap(s, limit=5)
    return {"url": r["final_url"], "title": d["title"], "title_len": len(d["title"]),
            "description_len": len(d["description"]), "h1": d["h1"][:1], "words": d["words"],
            "schema": d["schema"], "og_image": "og:image" in d["og"], "https": r["final_url"].startswith("https://"),
            "sitemap_urls": len(set(sm)), "seconds": r["seconds"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    ap.add_argument("--skip")
    a = ap.parse_args()
    brief = load_json(os.path.join(a.out, "brief.json"), {}) or {}
    comps = brief.get("competitors", [])
    if a.skip or not comps:
        reason = a.skip or "в брифе нет конкурентов"
        save_json(os.path.join(a.out, "competitors.json"), {"status": "skipped", "reason": reason})
        mark_step(a.out, "competitors", "skipped", reason)
        print("Шаг пропущен:", reason)
        return
    crawl = load_json(os.path.join(a.out, "crawl.json"))
    if not crawl:
        raise SystemExit("Нет crawl.json: сначала запусти crawl.py")
    ours = snapshot(crawl["start"])
    ours["sitemap_urls"] = max(ours.get("sitemap_urls", 0), len([p for p in crawl["pages"] if p.get("status") == 200]))
    rows = [snapshot(c) for c in comps]
    ok = [r for r in rows if "error" not in r]
    gaps = []
    if ok:
        med_pages = sorted(r["sitemap_urls"] for r in ok)[len(ok) // 2]
        if med_pages > ours["sitemap_urls"] * 2:
            gaps.append(f"У конкурентов обычно около {med_pages} страниц в sitemap, у нас {ours['sitemap_urls']}: им есть чем собирать запросы")
        if any(r["schema"] for r in ok) and not ours.get("schema"):
            gaps.append("У конкурентов есть микроразметка, у нас на главной нет")
        med_words = sorted(r["words"] for r in ok)[len(ok) // 2]
        if med_words > ours.get("words", 0) * 1.5:
            gaps.append(f"На главных у конкурентов больше текста: около {med_words} слов против {ours.get('words', 0)}")
    save_json(os.path.join(a.out, "competitors.json"), {"status": "done", "ours": ours, "competitors": rows, "gaps": gaps,
                                                        "note": "Сравнение витрин по открытым данным, не позиций"})
    mark_step(a.out, "competitors", "done", f"{len(ok)} из {len(rows)} сайтов, разрывов: {len(gaps)}")
    print(f"Конкурентов проверено: {len(ok)}, разрывов: {len(gaps)}")


if __name__ == "__main__":
    main()
