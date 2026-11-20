#!/usr/bin/env python3
"""Шаг 9. Ручные проверки: то, что скрипты не видят. Каждый пункт закрывается с заметкой.

    python3 checklist.py --out audit/ init                     # создать список
    python3 checklist.py --out audit/ show                     # что осталось
    python3 checklist.py --out audit/ set speed done "PageSpeed: мобильные 48, десктоп 81"
    python3 checklist.py --out audit/ set webmaster na "нет доступа к Вебмастеру клиента"
    python3 checklist.py --out audit/ set metrika done "счётчика нет" --issue important "Подключить Метрику и цели"

Статусы: done (проверено), na (нельзя проверить, причина обязательна).
Гейт не соберёт отчёт, пока хоть один пункт в статусе todo.
"""
import argparse
import os

from seo_lib import current_run, load_json, mark_step, save_json

ITEMS = {
    "speed": "Скорость: PageSpeed Insights, мобильная и десктоп версии (https://pagespeed.web.dev/)",
    "mobile": "Мобильная версия: открыть 3–5 ключевых страниц с телефона, всё читается и нажимается",
    "index_yandex": "Индексация в Яндексе: запрос site:домен, число страниц сравнить с обходом",
    "index_google": "Индексация в Google: запрос site:домен",
    "webmaster": "Яндекс Вебмастер: ошибки, регион сайта, санкции (если есть доступ)",
    "metrika": "Яндекс Метрика подключена и цели настроены",
    "serp": "Выдача по 3 главным запросам из брифа: кто в топе, чем их страницы лучше",
    "snippet": "Как выглядит сниппет сайта в выдаче Яндекса и Google",
    "business_card": "Яндекс Бизнес / карточка организации (для локального бизнеса)",
    "legal": "Пункты из rkn.json «проверить вручную»: реклама, реестр, оператор ПД",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    ap.add_argument("cmd", choices=["init", "show", "set"])
    ap.add_argument("key", nargs="?")
    ap.add_argument("status", nargs="?", choices=["done", "na", "todo"])
    ap.add_argument("note", nargs="?", default="")
    ap.add_argument("--issue", nargs=2, metavar=("SEVERITY", "FIX"),
                    help="если проверка нашла проблему: critical|important|nice и что сделать")
    a = ap.parse_args()
    path = os.path.join(a.out, "checklist.json")
    data = load_json(path, {})

    if a.cmd == "init":
        for k, v in ITEMS.items():
            data.setdefault(k, {"what": v, "status": "todo", "note": ""})
        speed = load_json(os.path.join(a.out, "speed.json"), {}) or {}
        if speed.get("status") == "done" and data["speed"]["status"] == "todo":
            data["speed"].update(status="done", note="Автоматически из PageSpeed: " + speed.get("summary", ""),
                                 run_id=current_run(a.out))
    elif a.cmd == "set":
        if a.key not in data:
            raise SystemExit(f"Нет пункта {a.key}. Есть: {', '.join(data)}")
        if a.status in ("done", "na") and not a.note.strip():
            raise SystemExit("Нужна заметка: что увидел(а) или почему нельзя проверить")
        data[a.key].update(status=a.status, note=a.note, run_id=current_run(a.out))
        if a.issue:
            if a.issue[0] not in ("critical", "important", "nice"):
                raise SystemExit("SEVERITY: critical, important или nice")
            data[a.key]["issue"] = {"severity": a.issue[0], "fix": a.issue[1]}
    save_json(path, data)

    left = [k for k, v in data.items() if v["status"] == "todo"]
    for k, v in data.items():
        print(f"[{v['status']:>4}] {k}: {v['what']}" + (f" → {v['note']}" if v["note"] else ""))
    if data and not left:
        mark_step(a.out, "manual_checks", "done", f"{len(data)} пунктов закрыто")
    else:
        mark_step(a.out, "manual_checks", "todo", f"осталось: {', '.join(left)}")


if __name__ == "__main__":
    main()
