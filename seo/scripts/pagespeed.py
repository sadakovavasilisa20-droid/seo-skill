#!/usr/bin/env python3
"""Шаг 5б. Скорость через Google PageSpeed Insights API: мобильная и десктоп версии.

    python3 pagespeed.py --out audit/ [--urls 3]
    PAGESPEED_API_KEY=ключ python3 pagespeed.py --out audit/      # с ключом лимиты выше
    python3 pagespeed.py --out audit/ --skip "API недоступен, скорость проверена вручную"

Берёт главную и до N важных страниц из обхода. Если API не ответил (лимит, сеть),
шаг не засчитывается: нужно повторить позже или пропустить с причиной.
Результат: audit/speed.json; при успехе ручной пункт «speed» закрывается автоматически.
"""
import argparse
import json
import os
import urllib.parse
import urllib.request

from seo_lib import load_json, mark_step, save_json

API = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


def run(url, strategy, key):
    q = {"url": url, "strategy": strategy, "category": "performance"}
    if key:
        q["key"] = key
    with urllib.request.urlopen(API + "?" + urllib.parse.urlencode(q), timeout=90) as r:
        d = json.load(r)
    lh = d["lighthouseResult"]
    a = lh["audits"]
    return {"score": round(lh["categories"]["performance"]["score"] * 100),
            "lcp": a["largest-contentful-paint"]["displayValue"],
            "cls": a["cumulative-layout-shift"]["displayValue"],
            "tbt": a["total-blocking-time"]["displayValue"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    ap.add_argument("--urls", type=int, default=3)
    ap.add_argument("--skip")
    a = ap.parse_args()
    if a.skip:
        save_json(os.path.join(a.out, "speed.json"), {"status": "skipped", "reason": a.skip})
        mark_step(a.out, "speed", "skipped", a.skip)
        print("Шаг пропущен:", a.skip)
        return
    crawl = load_json(os.path.join(a.out, "crawl.json"))
    if not crawl:
        raise SystemExit("Нет crawl.json: сначала запусти crawl.py")
    ok = [p for p in crawl["pages"] if p.get("status") == 200 and "title" in p]
    ok.sort(key=lambda p: (p.get("depth") is None, p.get("depth") or 0))
    urls = [p["final_url"] for p in ok[: a.urls]]
    key = os.environ.get("PAGESPEED_API_KEY")
    results, errors = [], []
    for u in urls:
        row = {"url": u}
        for strategy in ("mobile", "desktop"):
            try:
                row[strategy] = run(u, strategy, key)
            except Exception as e:  # лимит 429, сеть
                errors.append(f"{u} {strategy}: {str(e)[:120]}")
        results.append(row)
    measured = [r for r in results if "mobile" in r]
    if not measured:
        save_json(os.path.join(a.out, "speed.json"), {"status": "error", "errors": errors})
        mark_step(a.out, "speed", "todo", "API не ответил: повтори позже, добавь PAGESPEED_API_KEY или --skip с причиной")
        raise SystemExit("PageSpeed не ответил: " + "; ".join(errors[:2]))
    worst = min(measured, key=lambda r: r["mobile"]["score"])
    summary = f"мобильная от {worst['mobile']['score']}/100 (LCP {worst['mobile']['lcp']}) на {worst['url']}"
    issues = []
    for r in measured:
        m = r["mobile"]
        if m["score"] < 50:
            issues.append({"severity": "important", "url": r["url"], "what": f"Медленная мобильная версия: {m['score']}/100, LCP {m['lcp']}"})
        elif m["score"] < 90:
            issues.append({"severity": "nice", "url": r["url"], "what": f"Мобильная скорость {m['score']}/100, LCP {m['lcp']}: есть что ускорить"})
    save_json(os.path.join(a.out, "speed.json"), {"status": "done", "results": results, "errors": errors,
                                                  "summary": summary, "issues": issues,
                                                  "source": "Google PageSpeed Insights API v5, Lighthouse"})
    mark_step(a.out, "speed", "done", summary)
    print("Скорость:", summary)


if __name__ == "__main__":
    main()
