#!/usr/bin/env python3
"""Шаг 1. Бриф: что за сайт, для кого и зачем. Без брифа гейт не пропустит отчёт.

    python3 brief.py --out audit/ --site https://example.com --business "студия маникюра" \
        --region "Москва" --goal "заявки на запись" --queries "маникюр москва; наращивание ногтей"
"""
import argparse
import os

from seo_lib import mark_step, save_json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    ap.add_argument("--site", required=True)
    ap.add_argument("--business", required=True, help="чем занимается бизнес")
    ap.add_argument("--region", required=True)
    ap.add_argument("--goal", required=True, help="что должен давать сайт: заявки, продажи, записи")
    ap.add_argument("--queries", required=True, help="главные запросы через ;")
    ap.add_argument("--audience", default="")
    ap.add_argument("--competitors", default="", help="сайты конкурентов через ;")
    a = ap.parse_args()
    data = {k: v for k, v in vars(a).items() if k != "out"}
    data["queries"] = [q.strip() for q in a.queries.split(";") if q.strip()]
    data["competitors"] = [c.strip() for c in a.competitors.split(";") if c.strip()]
    save_json(os.path.join(a.out, "brief.json"), data)
    mark_step(a.out, "brief", "done", a.business)
    print("Бриф сохранён")


if __name__ == "__main__":
    main()
