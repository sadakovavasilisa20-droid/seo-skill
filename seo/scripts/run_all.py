#!/usr/bin/env python3
"""Запускает все автоматические шаги подряд (обход, sitemap, ссылки, техника, on-page, законы) и показывает состояние гейта.

    python3 run_all.py https://example.com --out audit/ [--max-pages 200] [--queries wordstat.csv]

Бриф (brief.py) и ручные проверки (checklist.py) заполняются отдельно: их делает человек или Claude
после изучения сайта. Без них гейт не откроется.
"""
import argparse
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def run(script, *args):
    cmd = [sys.executable, os.path.join(HERE, script), *args]
    print(f"\n=== {script} ===")
    return subprocess.run(cmd).returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--out", default="audit")
    ap.add_argument("--max-pages", default="200")
    ap.add_argument("--queries")
    a = ap.parse_args()
    o = ["--out", a.out]
    if run("crawl.py", a.url, *o, "--max-pages", a.max_pages):
        sys.exit("Обход не удался")
    for s in ("robots_sitemap.py", "link_graph.py", "tech_checks.py", "onpage.py", "rkn_check.py", "pagespeed.py", "competitors.py"):
        run(s, *o)
    if a.queries:
        run("demand.py", *o, "--queries", a.queries)
        run("traffic_model.py", *o)
    if not os.path.exists(os.path.join(a.out, "checklist.json")):
        run("checklist.py", *o, "init")
    run("gate.py", *o)


if __name__ == "__main__":
    main()
