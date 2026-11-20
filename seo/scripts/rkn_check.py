#!/usr/bin/env python3
"""Шаг 6. Проверка на риски по законам РФ (РКН): персональные данные, иностранные сервисы,
запрещённые организации, cookie, реклама.

    python3 rkn_check.py --out audit/

Это автоматический поиск признаков риска, а не юридическое заключение.
Каждый найденный пункт нужно проверить вручную или с юристом.
Результат: audit/rkn.json
"""
import argparse
import os
import re

from seo_lib import load_json, mark_step, save_json

FOREIGN_SERVICES = {
    "google-analytics.com": "Google Analytics",
    "googletagmanager.com": "Google Tag Manager",
    "connect.facebook.net": "Meta Pixel",
    "facebook.com/tr": "Meta Pixel",
    "static.hotjar.com": "Hotjar",
    "cdn.segment.com": "Segment",
    "js.hs-scripts.com": "HubSpot",
    "widget.intercom.io": "Intercom",
    "recaptcha": "Google reCAPTCHA",
    "fonts.googleapis.com": "Google Fonts",
}
META_DOMAINS = ("instagram.com", "facebook.com", "fb.com", "threads.net")
PD_FIELDS = re.compile(r"(name|имя|фио|phone|tel|телефон|email|e-mail|почта|mail)", re.I)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="audit")
    a = ap.parse_args()
    crawl = load_json(os.path.join(a.out, "crawl.json"))
    if not crawl:
        raise SystemExit("Нет crawl.json: сначала запусти crawl.py")
    pages = [p for p in crawl["pages"] if p.get("status") == 200 and "title" in p]

    policy_re = r"(политик|конфиденциальн|персональн|privacy|policy)"
    # политика может быть отдельной страницей, PDF-файлом или ссылкой в подвале: ищем везде
    has_policy_page = any(re.search(policy_re, (p["title"] + " " + p["url"]).lower())
                          or re.search(policy_re, p.get("all_anchors", ""))
                          or any(re.search(policy_re, l["url"].lower()) for l in p.get("internal_links", []) + p.get("external_links", []))
                          for p in pages)
    findings = []

    def add(risk, law, what, fix, urls):
        if urls:
            findings.append({"risk": risk, "law": law, "what": what, "fix": fix,
                             "pages": len(urls), "examples": sorted(set(urls))[:10]})

    pd_forms_no_consent, pd_forms_no_policy_link, foreign, meta_links, meta_no_mark = [], [], {}, [], []
    cookie_text = False
    for p in pages:
        text = p.get("text_sample", "").lower()
        anchors = " ".join(l["anchor"].lower() + " " + l["url"].lower() for l in p.get("internal_links", []))
        if "cookie" in text or "куки" in text:
            cookie_text = True
        for f in p.get("forms", []):
            if any(PD_FIELDS.search(x) for x in f["fields"]):
                if not f["checkbox"] and "соглас" not in text:
                    pd_forms_no_consent.append(p["url"])
                if not re.search(r"(политик|конфиденциальн|персональн|privacy)", anchors + text):
                    pd_forms_no_policy_link.append(p["url"])
        for src in p.get("scripts", []) + p.get("iframes", []):
            for dom, name in FOREIGN_SERVICES.items():
                if dom in src:
                    foreign.setdefault(name, []).append(p["url"])
        if any(any(d in l["url"] for d in META_DOMAINS) for l in p.get("external_links", [])):
            meta_links.append(p["url"])
            if "экстремист" not in text and "meta platforms" not in text:
                meta_no_mark.append(p["url"])

    add("высокий", "152-ФЗ «О персональных данных»",
        "Форма собирает имя, телефон или почту, но рядом не найдено согласие на обработку данных",
        "Добавить отдельное согласие на обработку персональных данных (чекбокс + ссылка на текст согласия)",
        pd_forms_no_consent)
    add("высокий", "152-ФЗ, ст. 18.1",
        "Форма собирает персональные данные, но на странице не найдена ссылка на политику обработки данных",
        "Опубликовать политику обработки персональных данных и поставить ссылку у каждой формы",
        pd_forms_no_policy_link)
    trackers = sorted({t for p in pages for t in p.get("trackers", [])})
    collects_pd = bool(pd_forms_no_consent or pd_forms_no_policy_link or trackers
                       or any(any(PD_FIELDS.search(x) for x in f["fields"]) for p in pages for f in p.get("forms", [])))
    if pages and not has_policy_page:
        if collects_pd:
            add("высокий", "152-ФЗ, ст. 18.1",
                "Сайт собирает данные (формы или счётчики), но не найдена страница с политикой обработки персональных данных",
                "Создать страницу политики и дать ссылку в подвале и у форм", [crawl["start"]])
        else:
            add("низкий", "152-ФЗ, ст. 18.1",
                "Нет страницы политики. Сейчас сайт не собирает данные (нет форм и счётчиков), но понадобится, как только появится форма или Метрика",
                "Подготовить политику заранее, вместе с подключением Метрики или формы", [crawl["start"]])
    for name, urls in foreign.items():
        add("средний", "152-ФЗ, ст. 12 (трансграничная передача) и ст. 18 ч. 5 (локализация)",
            f"Подключён иностранный сервис {name}: он может передавать данные посетителей за рубеж",
            "Проверить, уведомлён ли РКН о трансграничной передаче, или заменить на российский аналог (например, Яндекс Метрика)",
            urls)
    add("средний", "Решение суда о признании Meta экстремистской организацией (2022)",
        "Есть ссылки на Instagram / Facebook / Threads без пометки о Meta",
        "Добавить пометку: «Instagram, Facebook и Threads принадлежат Meta, признанной экстремистской и запрещённой в РФ»",
        meta_no_mark)
    if pages and trackers and not cookie_text:
        add("низкий", "152-ФЗ (cookie могут считаться персональными данными)",
            "Не найдено уведомление о cookie", "Добавить баннер о cookie со ссылкой на политику", [crawl["start"]])

    manual = [
        "Реклама на сайте и баннеры партнёров: есть ли маркировка «Реклама», рекламодатель и erid (38-ФЗ, ст. 18.1)",
        "Внешние ссылки: не ведут ли на ресурсы из реестра запрещённых (проверка на blocklist.rkn.gov.ru)",
        "Уведомление РКН об обработке персональных данных: есть ли оператор в реестре (pd.rkn.gov.ru)",
        "Если продаются товары или услуги: реквизиты продавца и оферта (Закон «О защите прав потребителей»)",
    ]
    data = {"pages_checked": len(pages), "trackers": trackers, "collects_personal_data": collects_pd,
            "findings": findings, "check_manually": manual,
            "disclaimer": "Автоматический поиск признаков риска, не юридическое заключение. Перед отчётом клиенту проверить с юристом."}
    save_json(os.path.join(a.out, "rkn.json"), data)
    mark_step(a.out, "rkn", "done", f"{len(findings)} рисков")
    print(f"Найдено рисков: {len(findings)}")


if __name__ == "__main__":
    main()
