#!/usr/bin/env python3
"""Шаг 4. Ссылочный граф: как страницы сайта связаны между собой.

    python3 link_graph.py --out audit/

Считает входящие ссылки, глубину, страницы-сироты, тупики, битые ссылки
и внутренний вес страниц (упрощённый PageRank).
Результат: audit/links.json
"""
import argparse
import os
from collections import defaultdict

from seo_lib import load_json, mark_step, save_json


def pagerank(nodes, edges, d=0.85, iters=30):
    n = len(nodes)
    pr = {u: 1 / n for u in nodes}
    out = {u: [v for v in edges.get(u, ()) if v in pr] for u in nodes}
    for _ in range(iters):
        new = {u: (1 - d) / n for u in nodes}
        for u in nodes:
            targets = out[u] or nodes  # тупик раздаёт вес всем
            share = d * pr[u] / len(targets)
            for v in targets:
                new[v] += share
        pr = new
    return pr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    a = ap.parse_args()
    crawl = load_json(os.path.join(a.out, "crawl.json"))
    if not crawl:
        raise SystemExit("Нет crawl.json: сначала запусти crawl.py")
    pages = {p["url"]: p for p in crawl["pages"]}
    ok = [u for u, p in pages.items() if p.get("status") == 200]

    edges, inbound, anchors = defaultdict(set), defaultdict(int), defaultdict(list)
    broken = []
    for u in ok:
        for link in pages[u].get("internal_links", []):
            v = link["url"]
            if v == u:
                continue
            edges[u].add(v)
            target = pages.get(v)
            if target and target.get("status") and target["status"] >= 400:
                broken.append({"from": u, "to": v, "status": target["status"], "anchor": link["anchor"]})
            if target and target.get("redirects"):
                anchors["__redirect__"].append({"from": u, "to": v})
    for u, targets in edges.items():
        for v in targets:
            inbound[v] += 1

    start = crawl["start"]
    orphans = [u for u in ok if inbound[u] == 0 and u != start]
    dead_ends = [u for u in ok if not edges.get(u)]
    deep = [{"url": u, "depth": pages[u]["depth"]} for u in ok if pages[u]["depth"] > 3]
    pr = pagerank(ok, edges) if ok else {}
    ranked = sorted(pr.items(), key=lambda x: -x[1])
    depth_hist = defaultdict(int)
    for u in ok:
        depth_hist[pages[u]["depth"]] += 1

    data = {
        "pages": len(ok),
        "depth_distribution": dict(sorted(depth_hist.items())),
        "deep_pages": deep[:100],
        "orphans": orphans[:100],
        "orphans_note": "Сирота = страница, на которую не ведёт ни одна ссылка из обойдённых. "
                        "Такие страницы обход находит только через sitemap.json.",
        "dead_ends": dead_ends[:100],
        "broken_links": broken[:200],
        "links_to_redirects": anchors["__redirect__"][:100],
        "top_weight": [{"url": u, "weight": round(w * 100, 2), "inbound": inbound[u]} for u, w in ranked[:15]],
        "low_weight": [{"url": u, "weight": round(w * 100, 2), "inbound": inbound[u]} for u, w in ranked[-15:]],
    }
    save_json(os.path.join(a.out, "links.json"), data)
    mark_step(a.out, "link_graph", "done",
              f"битых: {len(broken)}, тупиков: {len(dead_ends)}, глубже 3: {len(deep)}")
    print(f"Битых ссылок: {len(broken)}, тупиков: {len(dead_ends)}, страниц глубже 3 кликов: {len(deep)}")


if __name__ == "__main__":
    main()
