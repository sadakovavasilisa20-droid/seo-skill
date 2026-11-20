#!/usr/bin/env python3
"""Шаг 10. Гейт: не даёт собрать отчёт, пока не пройдены все шаги.

    python3 gate.py --out audit/

Проверяет, что у каждого шага есть отметка в state.json и файл с результатом,
а пропущенные шаги (skipped) имеют причину. Код выхода 0 = можно собирать отчёт, 1 = нельзя.
"""
import argparse
import os
import sys

from seo_lib import load_json

STEPS = [
    ("brief", "Бриф", "brief.json", False),
    ("crawl", "Обход сайта", "crawl.json", False),
    ("robots_sitemap", "robots.txt и sitemap", "sitemap.json", False),
    ("link_graph", "Ссылочный граф", "links.json", False),
    ("onpage", "On-page по всему сайту", "onpage.json", False),
    ("rkn", "Риски по законам РФ", "rkn.json", False),
    ("demand", "Спрос", "demand.json", True),       # можно пропустить с причиной
    ("traffic", "Модель трафика", "traffic.json", True),
    ("manual_checks", "Ручные проверки", "checklist.json", False),
]


def check(out):
    state = load_json(os.path.join(out, "state.json"), {})
    problems, rows = [], []
    for key, name, artifact, skippable in STEPS:
        st = state.get(key, {})
        status = st.get("status", "нет")
        exists = os.path.exists(os.path.join(out, artifact))
        ok = exists and (status == "done" or (skippable and status == "skipped" and st.get("note")))
        if not exists:
            problems.append(f"{name}: нет файла {artifact}")
        elif status == "skipped" and not skippable:
            problems.append(f"{name}: этот шаг нельзя пропускать")
        elif status not in ("done", "skipped"):
            problems.append(f"{name}: статус «{status}» {st.get('note', '')}".strip())
        rows.append((ok, name, status, st.get("note", "")))
    crawl = load_json(os.path.join(out, "crawl.json"), {})
    if crawl and not [p for p in crawl.get("pages", []) if p.get("status") == 200]:
        problems.append("Обход сайта: ни одной страницы с кодом 200")
    return rows, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    a = ap.parse_args()
    rows, problems = check(a.out)
    for ok, name, status, note in rows:
        print(f"{'✅' if ok else '⛔'} {name}: {status}" + (f" ({note})" if note else ""))
    if problems:
        print("\nГЕЙТ ЗАКРЫТ. Отчёт собирать нельзя:")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("\nГЕЙТ ОТКРЫТ: все шаги пройдены, можно собирать отчёт.")


if __name__ == "__main__":
    main()
