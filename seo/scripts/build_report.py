#!/usr/bin/env python3
"""Шаг 11. Отчёт для заказчика. Собирается только если гейт открыт.

    python3 build_report.py --out audit/

Результат: audit/report.md (дальше Claude дописывает выводы и при желании делает из него презентацию)
"""
import argparse
import os
import sys
import time

from gate import check
from seo_lib import load_json

ICON = {"critical": "🔴", "important": "🟠", "nice": "🟡", "высокий": "🔴", "средний": "🟠", "низкий": "🟡"}
SEV_RANK = {"critical": 0, "высокий": 0, "important": 1, "средний": 1, "nice": 2, "низкий": 2}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    a = ap.parse_args()
    rows, problems = check(a.out)
    if problems:
        print("ГЕЙТ ЗАКРЫТ, отчёт не собран:")
        for p in problems:
            print(" -", p)
        sys.exit(1)

    L = lambda name: load_json(os.path.join(a.out, name), {})
    brief, crawl, sm, links, onp = L("brief.json"), L("crawl.json"), L("sitemap.json"), L("links.json"), L("onpage.json")
    rkn, dem, tr, chk, state = L("rkn.json"), L("demand.json"), L("traffic.json"), L("checklist.json"), L("state.json")
    tech = L("tech.json")
    ok_pages = [p for p in crawl["pages"] if p.get("status") == 200]

    # единый список задач для приоритизации
    tasks = []
    for i in onp["issues"]:
        tasks.append((i["severity"], f"{i['issue']} — {i['pages_affected']} стр. ({i['share']}%)", i["fix"]))
    for f in tech.get("findings", []):
        tasks.append((f["severity"], f"Техника: {f['what']}", f["fix"]))
    for f in rkn["findings"]:
        tasks.append((f["risk"], f"Закон: {f['what']} — {f['pages']} стр.", f["fix"]))
    if links["broken_links"]:
        tasks.append(("critical", f"Битые внутренние ссылки — {len(links['broken_links'])}", "Исправить или убрать ссылки"))
    if links["orphans"] and not links.get("orphans_reliable", True):
        tasks.append(("nice", f"Кандидаты в страницы-сироты (обход не прошёл весь сайт) — {len(links['orphans'])}",
                      "Перепроверить с большим лимитом обхода и добавить на них ссылки"))
    elif links["orphans"]:
        tasks.append(("important", f"Страницы-сироты: есть в sitemap, но на них не ведёт ни одна ссылка — {len(links['orphans'])}", "Добавить ссылки из меню, разделов или статей"))
    if links["deep_pages"]:
        tasks.append(("important", f"Страницы глубже 3 кликов — {len(links['deep_pages'])}", "Поднять важные страницы ближе к главной"))
    if len(ok_pages) == 1:
        tasks.append(("important", "Сайт из одной страницы: в поиске он может показываться в основном по имени и бренду",
                      "Сделать отдельную страницу под каждую услугу и под кейсы: так сайт сможет собирать запросы по услугам"))
    for k, v in chk.items():
        if v.get("issue"):
            tasks.append((v["issue"]["severity"], f"Ручная проверка: {v['note']}", v["issue"]["fix"]))
    if sm.get("robots_blocks_all"):
        tasks.append(("critical", "robots.txt закрывает весь сайт (Disallow: /)", "Открыть сайт для индексации"))
    if not sm.get("sitemap_found"):
        tasks.append(("important", "Не найдена карта сайта sitemap.xml", "Создать sitemap.xml и указать в robots.txt"))
    if sm.get("bad_urls_in_sitemap"):
        tasks.append(("important", f"В sitemap мусорные URL (ошибки, noindex, редиректы) — {len(sm['bad_urls_in_sitemap'])}", "Оставить в sitemap только рабочие индексируемые страницы"))
    if sm.get("indexable_not_in_sitemap"):
        tasks.append(("nice", f"Страницы не в sitemap — {len(sm['indexable_not_in_sitemap'])}", "Добавить в sitemap"))
    if dem.get("status") == "done":
        unc = [c for c in dem["clusters"] if c["status"] == "нет страницы"][:5]
        for c in unc:
            tasks.append(("important", f"Нет страницы под спрос «{c['main_query']}» ({c['total_freq']} в мес.)", "Создать посадочную страницу"))
    tasks.sort(key=lambda t: SEV_RANK[t[0]])

    o = []
    w = o.append
    w(f"# SEO-аудит сайта {crawl['root']}")
    w(f"\n{brief.get('business', '')} · {brief.get('region', '')} · цель сайта: {brief.get('goal', '')}  ")
    w(f"Дата: {time.strftime('%d.%m.%Y')} · обойдено страниц: {len(crawl['pages'])}"
      + (" (упёрлись в лимит, сайт больше)" if crawl.get("limit_reached") else ""))

    crit = sum(1 for t in tasks if SEV_RANK[t[0]] == 0)
    imp = sum(1 for t in tasks if SEV_RANK[t[0]] == 1)
    w("\n## Главное\n")
    w(f"- Найдено задач: **{len(tasks)}**, из них критичных 🔴 **{crit}**, важных 🟠 **{imp}**")
    if tr.get("status") == "done":
        t = tr["totals_per_month"]
        w(f"- Потенциал трафика из поиска, визитов в месяц: сейчас ≈ {t['сейчас']}, "
          f"осторожно ≈ {t['осторожный']}, базово ≈ {t['базовый']}, смело ≈ {t['смелый']} (см. допущения)")
    if dem.get("status") == "done":
        w(f"- Спроса без своей страницы на сайте: **{dem['uncovered_share']}%** ({dem['uncovered_freq']} запросов в месяц)")
    w("\n### Топ-10 задач\n")
    w("| # | Приоритет | Что не так | Что сделать |\n|---|---|---|---|")
    for n, (sev, what, fix) in enumerate(tasks[:10], 1):
        w(f"| {n} | {ICON[sev]} | {what} | {fix} |")

    w("\n## 1. Индексация: robots.txt и sitemap\n")
    w(f"- robots.txt: {'есть' if sm['robots_txt_found'] else '**нет**'}; закрыт ли весь сайт: {'**да**' if sm['robots_blocks_all'] else 'нет'}")
    w(f"- sitemap: {'найден, ' + str(sm['sitemap_urls']) + ' URL' if sm['sitemap_found'] else '**не найден**'}")
    w(f"- Есть в sitemap, но на сайте на них нет ссылок (сироты): {len(sm.get('in_sitemap_only_no_links', []))}")
    w(f"- Есть в sitemap, но не проверены (лимит обхода): {len(sm.get('in_sitemap_not_crawled', []))}")
    w(f"- Рабочие страницы, которых нет в sitemap: {len(sm['indexable_not_in_sitemap'])}")
    if sm.get("note"):
        w(f"- ⚠️ {sm['note']}")

    w("\n## 2. Техника\n")
    if tech:
        w(f"- Главный адрес сайта: {tech['main_url']}")
        for m in tech["mirrors"]:
            how = f"редирект {m['first_redirect']} → {m['ends_at']}" if m["first_redirect"] else ("не открывается" if m["status"] is None else f"открывается сам, код {m['status']}")
            w(f"  - {m['url']}: {how}")
        if tech.get("trailing_slash"):
            t = tech["trailing_slash"]
            w(f"- Слэш на конце: {t['variant']} → код {t['status']}{', с редиректом' if t['redirects'] else ''}")
        w(f"- Несуществующая страница отвечает кодом {tech['soft404']['status']} {'✅' if tech['soft404']['status'] == 404 else '⚠️'}")
        w(f"- Страниц со смешанным контентом: {tech['mixed_content_pages']}")
        e, im = tech["external_links"], tech["images"]
        w(f"- Внешние ссылки: всего {e['total']}, проверено {e['checked']}, битых {len(e['broken'])}")
        w(f"- Картинки: всего {im['total']}, проверено {im['checked']}, тяжелее 300 КБ: {len(im['heavy'])}")
        for h in im["heavy"][:5]:
            w(f"  - {h['url']} — {h['kb']} КБ")

    w("\n## 3. Структура и ссылки\n")
    w(f"- Глубина вложенности (клики от главной: страниц): {links['depth_distribution']}")
    w(f"- Битых внутренних ссылок: {len(links['broken_links'])}; страниц-тупиков: {len(links['dead_ends'])}; "
      f"{'сирот' if links.get('orphans_reliable', True) else 'кандидатов в сироты'}: {len(links['orphans'])}")
    if links["orphans"]:
        w(f"  - {links['orphans_note']}")
    w("- Страницы с наибольшим внутренним весом:")
    for x in links["top_weight"][:5]:
        w(f"  - {x['url']} (вес {x['weight']}, входящих {x['inbound']})")

    w("\n## 4. Страницы: on-page\n")
    w(f"Проверено страниц: {onp['pages_checked']}\n")
    w("| Приоритет | Проблема | Страниц | Пример |\n|---|---|---|---|")
    for i in onp["issues"][:20]:
        ex = i["examples"][0]["url"] if i["examples"] else ""
        w(f"| {i['icon']} | {i['issue']} | {i['pages_affected']} ({i['share']}%) | {ex} |")

    w("\n## 5. Спрос и трафик\n")
    if dem.get("status") == "done":
        w(f"Источник: {dem['source']}, {dem['queries']} запросов, {len(dem['clusters'])} кластеров.\n")
        w("| Кластер | Запросов в мес. | Страница | Статус |\n|---|---|---|---|")
        for c in dem["clusters"][:15]:
            w(f"| {c['main_query']} | {c['total_freq']} | {c['page'] or '—'} | {c['status']} |")
    else:
        w(f"Шаг пропущен: {dem.get('reason')}")
    if tr.get("status") == "done":
        w("\nДопущения прогноза:")
        for x in tr["assumptions"]:
            w(f"- {x}")
    else:
        w(f"\nМодель трафика пропущена: {tr.get('reason')}")

    w("\n## 6. Риски по законам РФ\n")
    w(f"_{rkn['disclaimer']}_\n")
    for f in rkn["findings"]:
        w(f"- {ICON[f['risk']]} **{f['what']}** ({f['law']}). Что сделать: {f['fix']}. Страниц: {f['pages']}")
    if not rkn["findings"]:
        w("- Автоматическая проверка рисков не нашла")
    w("\nПроверить вручную:")
    for m in rkn["check_manually"]:
        w(f"- {m}")

    w("\n## 7. Ручные проверки\n")
    for k, v in chk.items():
        icon = "⚠️" if v.get("issue") else ("✅" if v["status"] == "done" else "➖")
        w(f"- {icon} {v['what']}: {v['note']}")

    w("\n## 8. План работ\n")
    for title, rank in (("Неделя 1: критичное", 0), ("Недели 2–4: важное", 1), ("Дальше: улучшения", 2)):
        items = [t for t in tasks if SEV_RANK[t[0]] == rank]
        if items:
            w(f"\n**{title}**")
            for sev, what, fix in items:
                w(f"- {fix} ({what})")

    w("\n## Ограничения аудита\n")
    for ok, name, status, note in rows:
        if status == "skipped":
            w(f"- Шаг «{name}» пропущен: {note}")
    if crawl.get("limit_reached"):
        w(f"- Обход ограничен {crawl['max_pages']} страницами")
    w("- Позиции, поведенческие факторы и ссылки с других сайтов скрипты не видят: нужны данные Вебмастера и Метрики")

    path = os.path.join(a.out, "report.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(o) + "\n")
    print("Отчёт:", path)


if __name__ == "__main__":
    main()
