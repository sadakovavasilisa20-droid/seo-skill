#!/usr/bin/env python3
"""Шаг 5. On-page по всему сайту: title, description, H1, текст, картинки, техника.

    python3 onpage.py --out audit/

Ищет не только ошибки на странице, но и проблемы между страницами: дубли title,
description и H1, каннибализацию. Результат: audit/onpage.json
"""
import argparse
import os
from collections import defaultdict

from seo_lib import load_json, mark_step, save_json

SEV = {"critical": "🔴", "important": "🟠", "nice": "🟡"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    a = ap.parse_args()
    crawl = load_json(os.path.join(a.out, "crawl.json"))
    if not crawl:
        raise SystemExit("Нет crawl.json: сначала запусти crawl.py")
    pages = [p for p in crawl["pages"] if p.get("status") == 200 and "title" in p]
    issues = defaultdict(list)

    def add(sev, key, fix, url, value=""):
        issues[(sev, key, fix)].append({"url": url, "value": value[:150] if isinstance(value, str) else value})

    dup = {"title": defaultdict(list), "description": defaultdict(list), "h1": defaultdict(list)}
    for p in pages:
        u, t, d = p["url"], p["title"], p["description"]
        noindex = "noindex" in p.get("meta_robots", "") or "noindex" in p.get("x_robots", "").lower()
        if noindex:
            add("critical", "Страница закрыта noindex", "Проверить, должна ли она быть в поиске", u)
        if not t:
            add("critical", "Нет title", "Написать title с главным запросом", u)
        elif len(t) > 70:
            add("important", "Title длиннее 70 символов", "Сократить, запрос ближе к началу", u, t)
        elif len(t) < 20:
            add("important", "Title короче 20 символов", "Дописать запрос и уточнение", u, t)
        if not d:
            add("important", "Нет meta description", "Написать 120–160 символов с пользой и призывом", u)
        elif not 70 <= len(d) <= 170:
            add("nice", "Description вне ориентира 120–160", "Переписать под ориентир", u, d)
        if not p["h1"]:
            add("critical", "Нет H1", "Добавить один H1 с главным запросом", u)
        elif len(p["h1"]) > 1:
            add("important", "Несколько H1", "Оставить один H1", u, " | ".join(p["h1"]))
        if p["words"] < 300:
            add("important", "Мало текста (меньше 300 слов)", "Расширить текст под запрос, если это не служебная страница", u, p["words"])
        if not p.get("viewport"):
            add("important", "Нет meta viewport", "Добавить мобильную адаптацию", u)
        if not p.get("lang"):
            add("nice", "Не указан lang", "Добавить <html lang=\"ru\">", u)
        if p.get("canonical") and p["canonical"] != p["final_url"]:
            add("important", "Canonical указывает на другую страницу", "Проверить, что это намеренно", u, p["canonical"])
        if not p.get("canonical"):
            add("nice", "Нет canonical", "Добавить canonical на саму страницу", u)
        if p.get("images_no_alt"):
            add("nice", "Картинки без alt", "Дописать alt значимым картинкам", u, len(p["images_no_alt"]))
        if not p.get("schema"):
            add("nice", "Нет микроразметки", "Добавить JSON-LD под тип страницы", u)
        if "og:title" not in p.get("og", {}) or "og:image" not in p.get("og", {}):
            add("nice", "Неполный Open Graph", "Добавить og:title, og:description, og:image", u)
        if p.get("seconds", 0) > 3:
            add("important", "Сервер отвечает дольше 3 секунд", "Проверить хостинг и PageSpeed", u, p["seconds"])
        if p.get("redirects"):
            add("nice", "Страница открывается через редирект", "Ставить ссылки сразу на конечный адрес", u, len(p["redirects"]))
        if not p["final_url"].startswith("https://"):
            add("important", "Страница не на HTTPS", "Перевести сайт на HTTPS", u)
        for field in ("title", "description"):
            if p[field]:
                dup[field][p[field].lower()].append(u)
        if p["h1"]:
            dup["h1"][p["h1"][0].lower()].append(u)

    names = {"title": "Дубли title", "description": "Дубли description", "h1": "Дубли H1 (риск каннибализации)"}
    for field, groups in dup.items():
        for value, urls in groups.items():
            if len(urls) > 1:
                sev = "important" if field != "description" else "nice"
                for u in urls:
                    add(sev, names[field], "Сделать уникальным для каждой страницы", u, value)

    errors = [p for p in crawl["pages"] if p.get("status") != 200]
    for p in errors:
        add("critical", "Страница отдаёт ошибку", "Починить или убрать ссылки на неё", p["url"], str(p.get("status") or p.get("error")))

    order = {"critical": 0, "important": 1, "nice": 2}
    out = []
    for (sev, key, fix), items in sorted(issues.items(), key=lambda x: (order[x[0][0]], -len(x[1]))):
        out.append({"severity": sev, "icon": SEV[sev], "issue": key, "fix": fix,
                    "pages_affected": len(items), "share": round(len(items) / max(len(pages), 1) * 100),
                    "examples": items[:10]})
    save_json(os.path.join(a.out, "onpage.json"), {"pages_checked": len(pages), "issues": out})
    mark_step(a.out, "onpage", "done", f"{len(out)} типов проблем")
    print(f"Проверено {len(pages)} страниц, найдено {len(out)} типов проблем")


if __name__ == "__main__":
    main()
