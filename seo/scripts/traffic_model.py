#!/usr/bin/env python3
"""Шаг 8. Модель трафика: сколько посетителей в месяц может дать рост позиций.

    python3 traffic_model.py --out audit/ [--positions positions.csv] [--ctr ctr.json]
    python3 traffic_model.py --out audit/ --skip "нет данных о спросе"

positions.csv: запрос;текущая позиция (из Яндекс Вебмастера или Search Console).
ctr.json: своя кривая CTR по позициям, например из отчёта Вебмастера клиента.

Три сценария для каждого кластера: осторожный (позиция 8), базовый (5), смелый (3).
Это прогноз на допущениях, не обещание. Все допущения пишутся в отчёт.
Результат: audit/traffic.json
"""
import argparse
import csv
import json
import os

from seo_lib import load_json, mark_step, save_json

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CTR = os.path.join(HERE, "..", "references", "ctr_curve.json")
SCENARIOS = {"осторожный": 8, "базовый": 5, "смелый": 3}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    ap.add_argument("--positions")
    ap.add_argument("--ctr", default=DEFAULT_CTR)
    ap.add_argument("--skip")
    a = ap.parse_args()

    demand = load_json(os.path.join(a.out, "demand.json"))
    if a.skip or not demand or demand.get("status") != "done":
        reason = a.skip or "шаг «Спрос» пропущен, считать не из чего"
        save_json(os.path.join(a.out, "traffic.json"), {"status": "skipped", "reason": reason})
        mark_step(a.out, "traffic", "skipped", reason)
        print("Шаг пропущен:", reason)
        return

    with open(a.ctr, encoding="utf-8") as f:
        ctr_cfg = json.load(f)
    ctr = {int(k): v for k, v in ctr_cfg["ctr_by_position"].items()}

    def ctr_at(pos):
        return ctr.get(int(round(pos)), 0.0) if pos and pos <= max(ctr) else 0.0

    positions = {}
    if a.positions:
        with open(a.positions, encoding="utf-8-sig") as f:
            for row in csv.reader(f, delimiter=";"):
                if len(row) >= 2:
                    try:
                        positions[row[0].strip().lower()] = float(row[1].replace(",", "."))
                    except ValueError:
                        pass

    rows, totals = [], {"сейчас": 0, **{k: 0 for k in SCENARIOS}}
    for c in demand["clusters"]:
        cur = 0
        for q in c["queries"]:
            cur += q["freq"] * ctr_at(positions.get(q["query"].lower()))
        row = {"cluster": c["main_query"], "freq": c["total_freq"], "page": c["page"], "сейчас": round(cur)}
        for name, pos in SCENARIOS.items():
            row[name] = max(round(c["total_freq"] * ctr_at(pos)), row["сейчас"])
        rows.append(row)
        for k in totals:
            totals[k] += row[k]

    data = {"status": "done", "scenarios": SCENARIOS, "totals_per_month": totals,
            "clusters": sorted(rows, key=lambda r: -r["базовый"])[:50],
            "assumptions": [
                "Частотность из Вордстата = примерное число показов в месяц во всём Яндексе, а не только органика.",
                "CTR по позициям: " + ctr_cfg.get("source", "источник не указан"),
                "Текущие позиции: " + ("из файла " + os.path.basename(a.positions) if a.positions else
                                       "не заданы, текущий трафик посчитан как 0"),
                "Сценарии не учитывают сезонность, колдунщики и рекламу в выдаче.",
            ]}
    save_json(os.path.join(a.out, "traffic.json"), data)
    mark_step(a.out, "traffic", "done", f"базовый сценарий ≈ {totals['базовый']} визитов/мес")
    print("Визитов в месяц:", totals)


if __name__ == "__main__":
    main()
