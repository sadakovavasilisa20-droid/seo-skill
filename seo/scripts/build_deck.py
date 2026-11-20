#!/usr/bin/env python3
"""Шаг 13. Дека для заказчика: презентация 16:9 из результатов аудита. Только через гейт.

    python3 build_deck.py --out audit/ [--brand "#FC3F1D"]

Пока гейт закрыт, дека не собирается. Цифры в деке берутся только из файлов шагов,
ничего не дописывается от себя. Результат: audit/deck.html (открыть в браузере,
Печать → Сохранить как PDF: каждый слайд ляжет на отдельную страницу).
"""
import argparse
import html
import os
import sys
import time

from build_report import ICON, SEV_RANK, collect
from gate import check

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
@page{size:1280px 720px;margin:0}
body{font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;background:#222;color:#151515}
.s{width:1280px;height:720px;margin:0 auto 20px;background:#F5F3EF;padding:60px 72px;position:relative;overflow:hidden;page-break-after:always}
@media print{body{background:none}.s{margin:0}}
.n{position:absolute;top:30px;right:72px;font-size:14px;color:#777}
.k{font-size:13px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;color:var(--b)}
h1{font-size:64px;line-height:1.05;letter-spacing:-2px}
h2{font-size:42px;line-height:1.1;letter-spacing:-1px;margin-bottom:26px}
.big{font-size:110px;font-weight:800;letter-spacing:-4px;line-height:1;color:var(--b)}
.g{display:grid;gap:14px}
.c{background:#fff;border-radius:20px;padding:22px 24px}
.c p{font-size:16px;line-height:1.4;margin-top:8px;color:#444}
li{font-size:18px;line-height:1.4;margin:0 0 10px 22px}
.dark{background:#151515;color:#fff}.dark .c{background:#262626;color:#fff}.dark .c p{color:#ccc}
.lim{font-size:13px;color:#777;position:absolute;left:72px;right:72px;bottom:24px}
"""


def e(x):
    return html.escape(str(x))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    ap.add_argument("--brand", default="#FC3F1D", help="акцентный цвет бренда клиента")
    a = ap.parse_args()
    rows, problems = check(a.out)
    if problems:
        print("ГЕЙТ ЗАКРЫТ, дека не собрана:")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    D = collect(a.out)
    brief, crawl, tasks = D["brief"], D["crawl"], D["tasks"]
    crit = [t for t in tasks if SEV_RANK[t[0]] == 0]
    imp = [t for t in tasks if SEV_RANK[t[0]] == 1]
    slides = []
    add = slides.append
    n = lambda: f'<div class="n">{len(slides) + 1}</div>'

    add(f'<section class="s">{n()}<div class="k">SEO-аудит · {e(time.strftime("%d.%m.%Y"))}</div>'
        f'<h1 style="margin-top:120px">{e(crawl["root"])}</h1>'
        f'<p style="font-size:22px;margin-top:24px;color:#444">{e(brief.get("business", ""))} · {e(brief.get("region", ""))}<br>'
        f'Цель сайта: {e(brief.get("goal", ""))}</p></section>')

    add(f'<section class="s dark">{n()}<div class="k">Главное</div>'
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:40px">'
        f'<div class="c"><div class="big">{len(tasks)}</div><p>задач найдено</p></div>'
        f'<div class="c"><div class="big">{len(crit)}</div><p>критичных: мешают попасть в поиск</p></div>'
        f'<div class="c"><div class="big">{len(imp)}</div><p>важных: стоят позиций и кликов</p></div></div>'
        f'<p style="font-size:20px;margin-top:40px;color:#ddd">Проверено страниц: {len(crawl["pages"])}. '
        f'Все шаги аудита пройдены и подтверждены гейтом.</p></section>')

    top = tasks[:5]
    items = "".join(f'<div class="c"><b>{ICON[s]} {e(w)}</b><p>{e(f)}</p></div>' for s, w, f in top)
    add(f'<section class="s">{n()}<h2>Что сделать в первую очередь</h2><div class="g">{items}</div></section>')

    sp, comp, dem, tr = D["speed"], D["comp"], D["dem"], D["tr"]
    if sp.get("status") == "done":
        cards = "".join(f'<div class="c"><div class="k">{e(r["url"][:60])}</div><div class="big" style="font-size:72px">'
                        f'{r["mobile"]["score"]}</div><p>мобильная из 100 · LCP {e(r["mobile"]["lcp"])}</p></div>'
                        for r in sp["results"] if "mobile" in r)
        add(f'<section class="s">{n()}<h2>Скорость на телефоне</h2><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:14px">{cards}</div>'
            f'<div class="lim">Источник: Google PageSpeed Insights</div></section>')
    if comp.get("status") == "done" and comp.get("gaps"):
        li = "".join(f"<li>{e(g)}</li>" for g in comp["gaps"])
        add(f'<section class="s">{n()}<h2>Чем мы уступаем конкурентам</h2><ul>{li}</ul>'
            f'<div class="lim">Сравнение витрин по открытым данным, не позиций</div></section>')
    if dem.get("status") == "done":
        add(f'<section class="s dark">{n()}<div class="k">Спрос</div><div class="big" style="margin-top:40px">{dem["uncovered_share"]}%</div>'
            f'<p style="font-size:24px;margin-top:16px">спроса клиентов приходится на запросы, под которые на сайте нет страницы '
            f'({dem["uncovered_freq"]} запросов в месяц, источник: {e(dem["source"])})</p></section>')
    if tr.get("status") == "done":
        t = tr["totals_per_month"]
        add(f'<section class="s">{n()}<h2>Сколько трафика можно получить</h2>'
            f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:14px">'
            + "".join(f'<div class="c"><div class="k">{k}</div><div class="big" style="font-size:64px">{v}</div><p>визитов в месяц</p></div>' for k, v in t.items())
            + f'</div><div class="lim">Прогноз на допущениях: {e(" ".join(tr["assumptions"]))}</div></section>')

    for title, rank in (("Неделя 1: критичное", 0), ("Недели 2–4: важное", 1), ("Дальше: улучшения", 2)):
        its = [t for t in tasks if SEV_RANK[t[0]] == rank][:7]
        if its:
            li = "".join(f"<li>{e(f)}</li>" for _, _, f in its)
            add(f'<section class="s">{n()}<div class="k">План работ</div><h2 style="margin-top:10px">{title}</h2><ul>{li}</ul></section>')

    lim = [f"Шаг «{nm}» пропущен: {nt}" for ok, nm, st, nt in rows if st == "skipped"]
    if crawl.get("limit_reached"):
        lim.append(f"Обход ограничен {crawl['max_pages']} страницами")
    lim.append("Позиции, поведенческие факторы и внешние ссылки по открытым данным не видны: нужны Вебмастер и Метрика")
    add(f'<section class="s">{n()}<h2>Ограничения аудита</h2><ul>{"".join(f"<li>{e(x)}</li>" for x in lim)}</ul></section>')

    doc = f'<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>SEO-аудит {e(crawl["root"])}</title>' \
          f'<style>:root{{--b:{e(a.brand)}}}{CSS}</style></head><body>{"".join(slides)}</body></html>'
    path = os.path.join(a.out, "deck.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"Дека: {path}, слайдов: {len(slides)}")


if __name__ == "__main__":
    main()
