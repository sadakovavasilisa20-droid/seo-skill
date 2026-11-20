#!/usr/bin/env python3
"""Шаг 5а. Техника, которую поисковики проверяют первой.

    python3 tech_checks.py --out audit/ [--max-external 60] [--max-images 60]

- Зеркала: http и https, с www и без, слэш на конце. Все варианты должны вести 301 на один адрес.
- Ложная 404: несуществующий адрес должен отвечать кодом 404, а не 200.
- Смешанный контент: картинки, скрипты и стили по http на https-странице.
- Битые внешние ссылки.
- Тяжёлые картинки (больше 300 КБ).
Результат: audit/tech.json
"""
import argparse
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from seo_lib import UA, fetch, load_json, mark_step, save_json

HEAVY_KB = 300


def head(url, timeout=15):
    """Код ответа и размер без скачивания тела (с откатом на GET, если HEAD запрещён)."""
    for method in ("HEAD", "GET"):
        req = urllib.request.Request(url, method=method, headers={"User-Agent": UA, "Range": "bytes=0-0"} if method == "GET" else {"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                size = r.headers.get("Content-Length")
                if method == "GET" and r.headers.get("Content-Range"):
                    size = r.headers["Content-Range"].split("/")[-1]
                return r.status, int(size) if size and size.isdigit() else None
        except urllib.error.HTTPError as e:
            if method == "HEAD" and e.code in (403, 405, 501):
                continue
            return e.code, None
        except Exception:
            if method == "HEAD":
                continue
            return None, None
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    ap.add_argument("--max-external", type=int, default=60)
    ap.add_argument("--max-images", type=int, default=60)
    a = ap.parse_args()
    crawl = load_json(os.path.join(a.out, "crawl.json"))
    if not crawl:
        raise SystemExit("Нет crawl.json: сначала запусти crawl.py")
    pages = [p for p in crawl["pages"] if p.get("status") == 200 and "title" in p]
    main_url = pages[0]["final_url"] if pages else crawl["start"]
    mp = urlparse(main_url)
    host = mp.netloc.removeprefix("www.")
    findings = []

    def add(sev, what, fix, examples):
        findings.append({"severity": sev, "what": what, "fix": fix, "examples": examples[:10]})

    # 1. Зеркала
    variants = {f"{s}://{w}{host}/" for s in ("http", "https") for w in ("", "www.")}
    main_root = f"{mp.scheme}://{mp.netloc}/"
    mirrors = []
    for v in sorted(variants):
        r = fetch(v)
        first = r["redirects"][0]["code"] if r["redirects"] else None
        final_root = "{0.scheme}://{0.netloc}/".format(urlparse(r["final_url"]))
        mirrors.append({"url": v, "status": r["status"], "first_redirect": first, "ends_at": r["final_url"]})
        if v == main_root:
            continue
        if r["status"] is None:
            continue  # вариант не открывается вовсе (например, нет www в DNS): это не дубль
        if not r["redirects"]:
            add("critical", f"Зеркало {v} открывается само, без редиректа: поисковик видит дубль сайта",
                f"Настроить 301-редирект на {main_root}", [v])
        elif final_root != main_root:
            add("important", f"Зеркало {v} ведёт не на главный адрес", f"Перенаправлять на {main_root}", [v])
        elif first != 301:
            add("important", f"Зеркало {v} перенаправляет кодом {first}, а не 301", "Поменять редирект на 301 (постоянный)", [v])

    # слэш на конце: берём внутреннюю страницу
    inner = next((p["final_url"] for p in pages if urlparse(p["final_url"]).path not in ("", "/")), None)
    slash = None
    if inner:
        alt = inner[:-1] if inner.endswith("/") else inner + "/"
        r = fetch(alt)
        slash = {"page": inner, "variant": alt, "status": r["status"], "redirects": bool(r["redirects"])}
        if r["status"] == 200 and not r["redirects"]:
            add("important", "Страница открывается и со слэшем на конце, и без: два адреса с одним содержимым",
                "Оставить один вариант, второй перенаправлять 301 (или canonical)", [inner, alt])

    # 2. Ложная 404
    probe = f"{mp.scheme}://{mp.netloc}/seo-skill-check-{int(time.time())}-net-takoy-stranicy"
    r = fetch(probe)
    soft404 = {"url": probe, "status": r["status"]}
    if r["status"] == 200:
        add("critical", "Несуществующая страница отвечает кодом 200 (ложная 404): в индекс может попасть мусор",
            "Настроить ответ 404 для несуществующих адресов", [probe])

    # 3. Смешанный контент
    mixed = {p["url"]: p["insecure_resources"] for p in pages if p.get("insecure_resources")}
    if mixed:
        add("important", f"Смешанный контент: файлы по http на https-страницах ({len(mixed)} стр.)",
            "Перевести адреса картинок, скриптов и стилей на https", list(mixed))

    # 4. Битые внешние ссылки
    ext = sorted({l["url"] for p in pages for l in p.get("external_links", [])})
    checked_ext, broken_ext = ext[: a.max_external], []
    for u in checked_ext:
        code, _ = head(u)
        if code is not None and code >= 400 and code not in (401, 403, 429):  # 401/403/429 часто отдают ботам
            broken_ext.append({"url": u, "status": code})
        time.sleep(0.1)
    if broken_ext:
        add("important", f"Битые внешние ссылки: {len(broken_ext)}", "Заменить или убрать",
            [f"{b['url']} ({b['status']})" for b in broken_ext])

    # 5. Тяжёлые картинки
    imgs = sorted({i for p in pages for i in p.get("image_urls", [])})
    checked_img, heavy = imgs[: a.max_images], []
    for u in checked_img:
        code, size = head(u)
        if size and size > HEAVY_KB * 1024:
            heavy.append({"url": u, "kb": round(size / 1024)})
        time.sleep(0.05)
    heavy.sort(key=lambda x: -x["kb"])
    if heavy:
        add("important" if len(heavy) > 3 else "nice", f"Тяжёлые картинки больше {HEAVY_KB} КБ: {len(heavy)}",
            "Сжать и перевести в WebP или AVIF", [f"{h['url']} ({h['kb']} КБ)" for h in heavy])

    data = {"main_url": main_root, "mirrors": mirrors, "trailing_slash": slash, "soft404": soft404,
            "mixed_content_pages": len(mixed),
            "external_links": {"total": len(ext), "checked": len(checked_ext), "broken": broken_ext},
            "images": {"total": len(imgs), "checked": len(checked_img), "heavy": heavy[:30]},
            "findings": findings}
    save_json(os.path.join(a.out, "tech.json"), data)
    mark_step(a.out, "tech", "done", f"{len(findings)} проблем")
    print(f"Техника: {len(findings)} проблем. Зеркала: {[m['status'] for m in mirrors]}, 404-проверка: {soft404['status']}")


if __name__ == "__main__":
    main()
