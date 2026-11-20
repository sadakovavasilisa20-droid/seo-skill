"""Общие функции SEO-скилла: загрузка страниц, разбор HTML, нормализация ссылок.

Только стандартная библиотека Python 3.
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urldefrag, urlencode, urljoin, urlparse

UA = "Mozilla/5.0 (compatible; seo-skill/2.0; +https://github.com/sadakovavasilisa20-droid/seo-skill)"
SKIP_EXT = re.compile(r"\.(jpe?g|png|gif|webp|avif|svg|ico|pdf|zip|rar|docx?|xlsx?|pptx?|mp4|mov|mp3|css|js|xml|json|txt)$", re.I)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_opener = urllib.request.build_opener(NoRedirect)


def fetch(url, timeout=20, max_redirects=5):
    """Возвращает dict: status, final_url, redirects (цепочка), headers, body (str), seconds."""
    chain, cur, t0 = [], url, time.time()
    for _ in range(max_redirects + 1):
        req = urllib.request.Request(cur, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
        try:
            r = _opener.open(req, timeout=timeout)
            code, headers, raw = r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            code, headers, raw = e.code, e.headers, e.read() if e.fp else b""
        except Exception as e:  # сеть, SSL, таймаут
            return {"status": None, "error": str(e)[:200], "final_url": cur, "redirects": chain,
                    "headers": {}, "body": "", "seconds": round(time.time() - t0, 2)}
        if code in (301, 302, 303, 307, 308) and headers.get("Location"):
            chain.append({"from": cur, "to": urljoin(cur, headers["Location"]), "code": code})
            cur = urljoin(cur, headers["Location"])
            continue
        charset = headers.get_content_charset() if hasattr(headers, "get_content_charset") else None
        if not charset:  # старые русские сайты: кодировка только в <meta charset> (часто windows-1251)
            m = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', raw[:4096], re.I)
            charset = m.group(1).decode("ascii", "ignore") if m else "utf-8"
        try:
            body = raw.decode(charset, errors="replace")
        except LookupError:
            body = raw.decode("utf-8", errors="replace")
        return {"status": code, "final_url": cur, "redirects": chain,
                "headers": {k.lower(): v for k, v in headers.items()}, "body": body,
                "seconds": round(time.time() - t0, 2)}
    return {"status": None, "error": "слишком много редиректов", "final_url": cur, "redirects": chain,
            "headers": {}, "body": "", "seconds": round(time.time() - t0, 2)}


TRACKING = re.compile(r"^(utm_\w+|yclid|gclid|fbclid|ysclid|_openstat|from|ref|roistat\w*|etext|_ga)$", re.I)


def norm_url(href, base):
    """Абсолютный URL без якоря, без меток рекламы и аналитики, с отсортированными параметрами."""
    if not href:
        return None
    href = href.strip()
    if href.startswith(("mailto:", "tel:", "javascript:", "data:", "#")):
        return None
    u = urldefrag(urljoin(base, href))[0]
    p = urlparse(u)
    if p.scheme not in ("http", "https"):
        return None
    path = p.path or "/"
    query = urlencode(sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k)))
    return p._replace(path=path, netloc=p.netloc.lower(), query=query).geturl()


def same_site(a, b):
    ha, hb = urlparse(a).netloc.lower(), urlparse(b).netloc.lower()
    return ha.removeprefix("www.") == hb.removeprefix("www.")


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self._in_title = "", False
        self.meta, self.canonical, self.lang = {}, None, None
        self.links, self._a_href, self._a_text = [], None, []
        self.headings, self._h_level, self._h_text = [], None, []
        self.images, self.scripts, self.iframes = [], [], []
        self.jsonld, self._in_jsonld, self._jsonld_buf = [], False, []
        self.forms, self._form = [], None
        self._skip, self.text_parts = 0, []
        self.resources = []

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
            self.images.append({"src": a.get("src") or a.get("data-original") or a.get("data-src") or "",
                                "alt": a.get("alt") if "alt" in a else None})
        elif tag == "a":
            self._a_href, self._a_text = a.get("href"), []
        elif tag == "iframe":
            self.iframes.append(a.get("src", ""))
        if tag in ("img", "script", "iframe", "source", "video", "audio") and a.get("src"):
            self.resources.append(a["src"])
        elif tag == "link" and a.get("href") and a.get("rel", "").lower() in ("stylesheet", "preload", "icon"):
            self.resources.append(a["href"])
        elif tag == "form":
            self._form = {"action": a.get("action", ""), "fields": [], "checkbox": False}
        elif tag in ("input", "textarea", "select") and self._form is not None:
            t = a.get("type", "text").lower()
            if t == "checkbox":
                self._form["checkbox"] = True
            elif t not in ("hidden", "submit", "button"):
                self._form["fields"].append((a.get("name") or t).lower() + ":" + t)
        elif tag == "script":
            if a.get("src"):
                self.scripts.append(a["src"])
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
        elif tag == "form" and self._form is not None:
            self.forms.append(self._form)
            self._form = None
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


def schema_types(blocks):
    types = []
    for b in blocks:
        try:
            data = json.loads(b)
        except ValueError:
            types.append("ошибка JSON-LD")
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for it in items:
            if isinstance(it, dict) and "@type" in it:
                t = it["@type"]
                types.extend(t if isinstance(t, list) else [t])
    return types


def analyze_html(html, url):
    """Разбирает HTML страницы в словарь SEO-данных."""
    p = PageParser()
    try:
        p.feed(html)
    except Exception:
        pass
    text = " ".join(" ".join(p.text_parts).split())
    internal, external = [], []
    for href, anchor in p.links:
        u = norm_url(href, url)
        if not u:
            continue
        (internal if same_site(u, url) else external).append({"url": u, "anchor": anchor[:80]})
    return {
        "title": " ".join(p.title.split()),
        "description": p.meta.get("description", "").strip(),
        "h1": [t for lvl, t in p.headings if lvl == 1],
        "headings": [[lvl, t[:120]] for lvl, t in p.headings][:60],
        "canonical": norm_url(p.canonical, url) if p.canonical else None,
        "meta_robots": p.meta.get("robots", "").lower(),
        "viewport": "viewport" in p.meta,
        "lang": p.lang,
        "og": {k: v for k, v in p.meta.items() if k.startswith("og:")},
        "schema": schema_types(p.jsonld),
        "images": len(p.images),
        "images_no_alt": [i["src"] for i in p.images if i["alt"] is None][:20],
        "words": len(re.findall(r"\w+", text)),
        "text_sample": text[:3000],
        "internal_links": internal,
        "external_links": external,
        "scripts": p.scripts,
        "iframes": p.iframes,
        "forms": p.forms,
        "insecure_resources": sorted({x for x in p.resources if x.startswith("http://")})[:20]
        if url.startswith("https://") else [],
        "image_urls": [urljoin(url, i["src"]) for i in p.images if i["src"] and not i["src"].startswith("data:")][:60],
        "all_anchors": " ".join(t.lower() for _, t in p.links)[:5000],
        # счётчики и пиксели ищем по всему HTML, включая встроенные скрипты
        "trackers": sorted(set(re.findall(
            r"(mc\.yandex\.ru|google-analytics\.com|googletagmanager\.com|connect\.facebook\.net|"
            r"top-fwz1\.mail\.ru|vk\.com/rtrg|static\.hotjar\.com)", html))),
    }


def read_sitemap(url, seen=None, limit=20):
    """Читает sitemap и sitemap index (рекурсивно, до limit файлов). Возвращает список URL."""
    import xml.etree.ElementTree as ET
    seen = set() if seen is None else seen
    if url in seen or len(seen) >= limit:
        return []
    seen.add(url)
    r = fetch(url)
    if r["status"] != 200:
        return []
    try:
        root = ET.fromstring(r["body"].encode("utf-8"))
    except ET.ParseError:
        return []
    m = re.match(r"\{.*\}", root.tag)
    ns = m.group(0) if m else ""
    if root.tag.endswith("sitemapindex"):
        urls = []
        for loc in root.iter(ns + "loc"):
            urls += read_sitemap(loc.text.strip(), seen, limit)
        return urls
    return [loc.text.strip() for loc in root.iter(ns + "loc") if loc.text]


def sitemaps_from_robots(root):
    r = fetch(root + "/robots.txt")
    txt = r["body"] if r["status"] == 200 else ""
    return r, txt, re.findall(r"(?im)^\s*sitemap:\s*(\S+)", txt) or [root + "/sitemap.xml"]


def load_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def current_run(out_dir):
    """run_id текущего обхода: им помечаются все шаги, чтобы гейт видел, что они сделаны по одному обходу."""
    crawl = load_json(os.path.join(out_dir, "crawl.json"), {}) or {}
    return crawl.get("run_id")


def mark_step(out_dir, step, status="done", note="", run_id=None):
    """Записывает состояние шага в state.json: его проверяет гейт."""
    path = os.path.join(out_dir, "state.json")
    state = load_json(path, {})
    state[step] = {"status": status, "note": note, "at": time.strftime("%Y-%m-%d %H:%M"),
                   "run_id": run_id if run_id is not None else current_run(out_dir)}
    save_json(path, state)
