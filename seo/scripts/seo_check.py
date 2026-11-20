#!/usr/bin/env python3
"""Собирает SEO-данные страницы для аудита.

Использование:
    python3 seo_check.py https://example.com/page
    python3 seo_check.py page.html

Выводит JSON. Только стандартная библиотека Python, ничего ставить не нужно.
"""
import json
import re
import sys
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

UA = "Mozilla/5.0 (compatible; seo-skill/1.0)"


class SEOParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self._in_title = False
        self.meta = {}
        self.links = []          # (href, text)
        self._a_href = None
        self._a_text = []
        self.headings = []       # (level, text)
        self._h_level = None
        self._h_text = []
        self.images = []         # (src, alt or None)
        self.canonical = None
        self.lang = None
        self.jsonld = []
        self._in_jsonld = False
        self._jsonld_buf = []
        self._skip = 0           # внутри script/style/noscript
        self.text_parts = []

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = a.get("lang") or None
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            key = (a.get("name") or a.get("property") or "").lower()
            if key:
                self.meta[key] = a.get("content", "")
        elif tag == "link" and "canonical" in a.get("rel", "").lower():
            self.canonical = a.get("href")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._h_level, self._h_text = int(tag[1]), []
        elif tag == "img":
            self.images.append((a.get("src") or a.get("data-original") or a.get("data-src") or "", a.get("alt")))
        elif tag == "a":
            self._a_href, self._a_text = a.get("href"), []
        elif tag == "script":
            if "ld+json" in a.get("type", ""):
                self._in_jsonld, self._jsonld_buf = True, []
            else:
                self._skip += 1
        elif tag in ("style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6") and self._h_level:
            self.headings.append((self._h_level, " ".join("".join(self._h_text).split())))
            self._h_level = None
        elif tag == "a" and self._a_href is not None:
            self.links.append((self._a_href, " ".join("".join(self._a_text).split())))
            self._a_href = None
        elif tag == "script":
            if self._in_jsonld:
                self.jsonld.append("".join(self._jsonld_buf))
                self._in_jsonld = False
            elif self._skip:
                self._skip -= 1
        elif tag in ("style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._in_jsonld:
            self._jsonld_buf.append(data)
            return
        if self._skip:
            return
        if self._in_title:
            self.title += data
        if self._h_level:
            self._h_text.append(data)
        if self._a_href is not None:
            self._a_text.append(data)
        self.text_parts.append(data)


def load(src):
    if re.match(r"https?://", src):
        req = urllib.request.Request(src, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            charset = r.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace"), r.geturl(), r.status
    with open(src, encoding="utf-8", errors="replace") as f:
        return f.read(), None, None


def schema_types(blocks):
    types = []
    for b in blocks:
        try:
            data = json.loads(b)
        except ValueError:
            types.append("ошибка в JSON-LD")
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for it in items:
            if isinstance(it, dict) and "@type" in it:
                t = it["@type"]
                types.extend(t if isinstance(t, list) else [t])
    return types


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)
    src = sys.argv[1]
    html, final_url, status = load(src)
    p = SEOParser()
    p.feed(html)

    title = " ".join(p.title.split())
    desc = p.meta.get("description", "").strip()
    h1 = [t for lvl, t in p.headings if lvl == 1]
    text = " ".join(" ".join(p.text_parts).split())
    words = len(re.findall(r"\w+", text))

    host = urlparse(final_url or "").netloc
    internal = external = 0
    for href, _ in p.links:
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        h = urlparse(urljoin(final_url or "", href)).netloc
        if host and h and h != host:
            external += 1
        else:
            internal += 1

    no_alt = [s for s, alt in p.images if alt is None]
    empty_alt = [s for s, alt in p.images if alt is not None and not alt.strip()]
    weak_links = [t for _, t in p.links if t.lower() in ("тут", "здесь", "подробнее", "читать", "click here", "here", "more")]

    issues = []
    if not title:
        issues.append("🔴 нет title")
    elif len(title) > 70:
        issues.append(f"🟠 title длинный: {len(title)} символов")
    elif len(title) < 20:
        issues.append(f"🟠 title короткий: {len(title)} символов")
    if not desc:
        issues.append("🟠 нет meta description")
    elif not 70 <= len(desc) <= 170:
        issues.append(f"🟠 description {len(desc)} символов (ориентир 120–160)")
    if len(h1) == 0:
        issues.append("🔴 нет H1")
    elif len(h1) > 1:
        issues.append(f"🟠 H1 несколько: {len(h1)}")
    if "noindex" in p.meta.get("robots", "").lower():
        issues.append("🔴 meta robots noindex: страница закрыта от индексации")
    if not p.canonical:
        issues.append("🟡 нет canonical")
    if "viewport" not in p.meta:
        issues.append("🟠 нет meta viewport (мобильная версия)")
    if not p.lang:
        issues.append("🟠 не указан lang у <html>")
    if no_alt:
        issues.append(f"🟡 картинок без alt: {len(no_alt)} из {len(p.images)}")
    if not p.jsonld:
        issues.append("🟡 нет микроразметки JSON-LD")
    if "og:title" not in p.meta or "og:image" not in p.meta:
        issues.append("🟡 неполный Open Graph (og:title / og:image)")
    if words < 300:
        issues.append(f"🟠 мало текста: {words} слов")
    if final_url and not final_url.startswith("https://"):
        issues.append("🟡 страница не на HTTPS")

    report = {
        "url": final_url or src,
        "status": status,
        "title": {"text": title, "length": len(title)},
        "description": {"text": desc, "length": len(desc)},
        "h1": h1,
        "headings": [f"H{lvl}: {t}" for lvl, t in p.headings][:40],
        "canonical": p.canonical,
        "robots": p.meta.get("robots"),
        "viewport": p.meta.get("viewport"),
        "lang": p.lang,
        "open_graph": {k: v for k, v in p.meta.items() if k.startswith("og:")},
        "schema_types": schema_types(p.jsonld),
        "images": {"total": len(p.images), "no_alt": len(no_alt), "empty_alt": len(empty_alt), "no_alt_examples": no_alt[:5]},
        "links": {"internal": internal, "external": external, "weak_anchor_texts": weak_links[:5]},
        "words": words,
        "quick_issues": issues,
        "check_manually": [
            "скорость: https://pagespeed.web.dev/",
            "индексация: Яндекс Вебмастер и Google Search Console",
            "robots.txt и sitemap.xml сайта",
            "частотность запросов: https://wordstat.yandex.ru/",
        ],
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
