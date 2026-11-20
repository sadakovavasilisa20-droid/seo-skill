#!/usr/bin/env python3
"""Шаг 7. Спрос: группирует запросы и привязывает их к страницам сайта.

    python3 demand.py --out audit/ --queries wordstat.csv
    python3 demand.py --out audit/ --skip "клиент не дал доступ к Вордстату"

wordstat.csv: две колонки, запрос;частотность (разделитель ; или , или таб).
Частотность берётся только из выгрузки, скрипт её не придумывает.

Что делает:
- группирует запросы в кластеры по общим основам слов;
- для каждого кластера ищет страницу сайта, которая ему соответствует (title, H1, URL);
- кластеры без подходящей страницы = непокрытый спрос, кандидаты на новые страницы;
- несколько страниц на один кластер = риск каннибализации.
Результат: audit/demand.json
"""
import argparse
import csv
import os
import re
from collections import defaultdict
from urllib.parse import unquote, urlparse

from seo_lib import load_json, mark_step, save_json

STOP = set("в во на и или для с со по от до из за к ко о об у а но не ни как что это купить цена цены "
           "недорого москва спб москве".split())
ENDINGS = sorted("ами ями ого его ому ему ыми ими ых их ую юю ая яя ое ее ой ей ий ый ом ем ам ям ах ях "
                 "ов ев ы и а я у ю е о ь й".split(), key=len, reverse=True)


def stem(word):
    w = word.lower().replace("ё", "е")
    if len(w) <= 4:
        return w
    for e in ENDINGS:
        if w.endswith(e) and len(w) - len(e) >= 4:
            return w[: -len(e)]
    return w


def stems(text):
    return {stem(w) for w in re.findall(r"[a-zа-яё0-9]+", text.lower()) if w not in STOP and len(w) > 1}


def read_queries(path):
    with open(path, encoding="utf-8-sig") as f:
        sample = f.read(2048)
        f.seek(0)
        delim = ";" if sample.count(";") >= sample.count(",") else ","
        if "\t" in sample:
            delim = "\t"
        rows = []
        for row in csv.reader(f, delimiter=delim):
            if len(row) < 2:
                continue
            q, n = row[0].strip(), re.sub(r"[^\d]", "", row[1])
            if q and n:
                rows.append((q, int(n)))
        return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    ap.add_argument("--queries", help="CSV из Вордстата: запрос;частотность")
    ap.add_argument("--skip", help="пропустить шаг, обязательно с причиной")
    a = ap.parse_args()

    if a.skip:
        save_json(os.path.join(a.out, "demand.json"), {"status": "skipped", "reason": a.skip})
        mark_step(a.out, "demand", "skipped", a.skip)
        print("Шаг пропущен:", a.skip)
        return
    if not a.queries:
        raise SystemExit("Нужен --queries файл.csv или --skip \"причина\"")

    crawl = load_json(os.path.join(a.out, "crawl.json"))
    if not crawl:
        raise SystemExit("Нет crawl.json: сначала запусти crawl.py")
    rows = read_queries(a.queries)
    if not rows:
        raise SystemExit("В CSV не нашлось строк «запрос;частотность»")

    # кластеры: запросы с одинаковым набором из двух самых частых основ
    stem_freq = defaultdict(int)
    for q, _ in rows:
        for s in stems(q):
            stem_freq[s] += 1
    clusters = defaultdict(list)
    for q, n in rows:
        st = sorted(stems(q), key=lambda s: (-stem_freq[s], s))[:2]
        clusters[" ".join(sorted(st)) or q].append({"query": q, "freq": n})

    pages = [p for p in crawl["pages"] if p.get("status") == 200 and "title" in p]
    page_stems = {p["url"]: stems(" ".join([p["title"], " ".join(p["h1"]),
                                             unquote(urlparse(p["url"]).path).replace("-", " ").replace("/", " ")]))
                  for p in pages}

    out = []
    for key, qs in clusters.items():
        key_stems = set(key.split())
        scored = []
        for u, ps in page_stems.items():
            score = len(key_stems & ps) / max(len(key_stems), 1)
            if score >= 0.5:
                scored.append((score, u))
        scored.sort(reverse=True)
        total = sum(x["freq"] for x in qs)
        status = "нет страницы" if not scored else ("каннибализация" if len(scored) > 1 and scored[0][0] == scored[1][0] else "есть страница")
        out.append({"cluster": key, "total_freq": total,
                    "main_query": max(qs, key=lambda x: x["freq"])["query"],
                    "queries": sorted(qs, key=lambda x: -x["freq"])[:15],
                    "page": scored[0][1] if scored else None,
                    "competing_pages": [u for _, u in scored[1:4]] if status == "каннибализация" else [],
                    "status": status})
    out.sort(key=lambda c: -c["total_freq"])
    total = sum(c["total_freq"] for c in out)
    uncovered = sum(c["total_freq"] for c in out if c["status"] == "нет страницы")
    data = {"status": "done", "source": os.path.basename(a.queries), "queries": len(rows),
            "clusters": out, "total_freq": total, "uncovered_freq": uncovered,
            "uncovered_share": round(uncovered / max(total, 1) * 100),
            "method_note": "Кластеры собраны по общим основам слов. Это быстрая автоматическая группировка: "
                           "спорные кластеры Claude проверяет вручную по выдаче."}
    save_json(os.path.join(a.out, "demand.json"), data)
    mark_step(a.out, "demand", "done", f"{len(out)} кластеров, непокрыто {data['uncovered_share']}% спроса")
    print(f"{len(rows)} запросов → {len(out)} кластеров. Без страницы: {data['uncovered_share']}% спроса")


if __name__ == "__main__":
    main()
