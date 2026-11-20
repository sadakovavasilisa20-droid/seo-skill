"""Тесты SEO-скилла. Без сети: аудит собирается из подготовленных данных.

    python3 -m unittest discover -s tests -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(HERE, "..", "seo", "scripts")
sys.path.insert(0, SCRIPTS)

from seo_lib import analyze_html, mark_step, norm_url, save_json  # noqa: E402
from gate import check  # noqa: E402

RUN = "test-run-1"


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def page(url, title, text, depth=0, links=()):
    return {"url": url, "final_url": url, "status": 200, "depth": depth, "found_via": "links", "redirects": [],
            "seconds": 0.2, "x_robots": "", "title": title, "description": "Описание страницы для теста " * 4,
            "h1": [title], "headings": [[1, title]], "canonical": url, "meta_robots": "", "viewport": True, "lang": "ru",
            "og": {"og:title": title, "og:image": "x.jpg"}, "schema": ["Organization"], "images": 1, "images_no_alt": [],
            "words": len(text.split()), "text_sample": text, "internal_links": [{"url": u, "anchor": "ссылка"} for u in links],
            "external_links": [], "scripts": [], "iframes": [], "forms": [], "trackers": [], "insecure_resources": [],
            "image_urls": [], "all_anchors": "политика конфиденциальности"}


def py(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args], capture_output=True, text=True)


class AuditFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = self.tmp.name
        a, b = "https://site.test/", "https://site.test/uslugi/"
        text = " ".join(f"слово{i}" for i in range(400))
        save_json(os.path.join(self.out, "crawl.json"), {
            "run_id": RUN, "start": a, "root": "https://site.test", "max_pages": 50, "limit_reached": False,
            "links_exhausted": True, "pages": [page(a, "Главная страница студии", text, 0, [b]),
                                               page(b, "Услуги студии и цены", text + " другое", 1, [a])]})
        mark_step(self.out, "crawl", "done", "2 страницы", run_id=RUN)

    def tearDown(self):
        self.tmp.cleanup()

    def fill_all(self):
        """Все шаги закрыты корректно по текущему обходу."""
        save_json(os.path.join(self.out, "brief.json"), {"business": "студия", "region": "Москва", "goal": "заявки",
                                                         "queries": ["студия"], "competitors": []})
        mark_step(self.out, "brief", "done", "студия", run_id=None)
        for step, f, data in [("robots_sitemap", "sitemap.json", {"robots_txt_found": True, "robots_blocks_all": False,
                                                                   "sitemap_found": True, "sitemap_urls": 2, "in_sitemap_not_crawled": [],
                                                                   "in_sitemap_only_no_links": [], "indexable_not_in_sitemap": [],
                                                                   "bad_urls_in_sitemap": []}),
                              ("link_graph", "links.json", {"depth_distribution": {"0": 1, "1": 1}, "broken_links": [], "orphans": [],
                                                             "orphans_reliable": True, "orphans_note": "", "dead_ends": [], "deep_pages": [],
                                                             "top_weight": [{"url": "https://site.test/", "weight": 50, "inbound": 1}]}),
                              ("tech", "tech.json", {"main_url": "https://site.test/", "mirrors": [], "trailing_slash": None,
                                                     "soft404": {"status": 404}, "mixed_content_pages": 0,
                                                     "external_links": {"total": 0, "checked": 0, "broken": []},
                                                     "images": {"total": 0, "checked": 0, "heavy": []}, "findings": []}),
                              ("onpage", "onpage.json", {"pages_checked": 2, "issues": []}),
                              ("rkn", "rkn.json", {"findings": [], "check_manually": [], "disclaimer": "не юрзаключение"})]:
            save_json(os.path.join(self.out, f), data)
            mark_step(self.out, step, "done", "ok")
        for step, f in [("speed", "speed.json"), ("demand", "demand.json"), ("traffic", "traffic.json"),
                        ("competitors", "competitors.json")]:
            save_json(os.path.join(self.out, f), {"status": "skipped", "reason": "нет данных в тесте"})
            mark_step(self.out, step, "skipped", "нет данных в тесте")
        self.assertEqual(py("checklist.py", "--out", self.out, "init").returncode, 0)
        chk = read_json(os.path.join(self.out, "checklist.json"))
        for k in chk:
            r = py("checklist.py", "--out", self.out, "set", k, "na", "нельзя проверить в тесте без сети")
            self.assertEqual(r.returncode, 0, r.stderr)


class TestGate(AuditFixture):
    def test_closed_without_brief(self):
        _, problems = check(self.out)
        self.assertTrue(any("Бриф" in p for p in problems))

    def test_open_when_all_steps_done(self):
        self.fill_all()
        _, problems = check(self.out)
        self.assertEqual(problems, [])

    def test_closed_when_step_from_other_crawl(self):
        self.fill_all()
        mark_step(self.out, "onpage", "done", "ok", run_id="old-run")
        _, problems = check(self.out)
        self.assertTrue(any("другому обходу" in p for p in problems))

    def test_closed_when_checklist_from_old_crawl(self):
        self.fill_all()
        crawl = read_json(os.path.join(self.out, "crawl.json"))
        crawl["run_id"] = "new-run"
        save_json(os.path.join(self.out, "crawl.json"), crawl)
        _, problems = check(self.out)
        self.assertTrue(any("старому обходу" in p for p in problems) or any("другому обходу" in p for p in problems))

    def test_non_skippable_step_cannot_be_skipped(self):
        self.fill_all()
        mark_step(self.out, "tech", "skipped", "лень")
        _, problems = check(self.out)
        self.assertTrue(any("нельзя пропускать" in p for p in problems))

    def test_short_checklist_note_rejected(self):
        self.fill_all()
        chk_path = os.path.join(self.out, "checklist.json")
        chk = read_json(chk_path)
        chk["speed"]["note"] = "ок"
        save_json(chk_path, chk)
        _, problems = check(self.out)
        self.assertTrue(any("короткая заметка" in p for p in problems))

    def test_competitors_cannot_be_skipped_if_in_brief(self):
        self.fill_all()
        b = read_json(os.path.join(self.out, "brief.json"))
        b["competitors"] = ["https://rival.test"]
        save_json(os.path.join(self.out, "brief.json"), b)
        _, problems = check(self.out)
        self.assertTrue(any("Конкуренты" in p for p in problems))


class TestReportAndDeck(AuditFixture):
    def test_report_and_deck_blocked_by_closed_gate(self):
        self.assertNotEqual(py("build_report.py", "--out", self.out).returncode, 0)
        self.assertNotEqual(py("build_deck.py", "--out", self.out).returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(self.out, "deck.html")))

    def test_report_and_deck_built_when_gate_open(self):
        self.fill_all()
        r1, r2 = py("build_report.py", "--out", self.out), py("build_deck.py", "--out", self.out)
        self.assertEqual(r1.returncode, 0, r1.stdout + r1.stderr)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        deck = read_text(os.path.join(self.out, "deck.html"))
        self.assertIn("Ограничения аудита", deck)
        self.assertIn("нет данных в тесте", deck)


class TestChecks(AuditFixture):
    def test_near_duplicates_found(self):
        r = py("onpage.py", "--out", self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        data = read_json(os.path.join(self.out, "onpage.json"))
        self.assertTrue(any("Почти одинаковые" in i["issue"] for i in data["issues"]))

    def test_demand_marks_uncovered_cluster(self):
        q = os.path.join(self.out, "q.csv")
        with open(q, "w", encoding="utf-8") as f:
            f.write("студия главная;100\nдоставка пиццы;900\n")
        r = py("demand.py", "--out", self.out, "--queries", q)
        self.assertEqual(r.returncode, 0, r.stderr)
        d = read_json(os.path.join(self.out, "demand.json"))
        pizza = [c for c in d["clusters"] if "пиццы" in c["main_query"]][0]
        self.assertEqual(pizza["status"], "нет страницы")


class TestLib(unittest.TestCase):
    def test_norm_url_strips_tracking_and_sorts(self):
        self.assertEqual(norm_url("/a/?utm_source=x&b=2&a=1&yclid=5#top", "https://Site.ru/"),
                         "https://site.ru/a/?a=1&b=2")

    def test_analyze_html(self):
        h = ('<html lang="ru"><head><title>Тест</title><meta name="description" content="Описание">'
             '<script src="http://cdn.test/x.js"></script><script>ym(1);mc.yandex.ru</script></head>'
             '<body><h1>Заголовок</h1><img src="a.jpg"><a href="/b">Б</a></body></html>')
        d = analyze_html(h, "https://site.test/")
        self.assertEqual(d["title"], "Тест")
        self.assertEqual(d["h1"], ["Заголовок"])
        self.assertIn("mc.yandex.ru", d["trackers"])
        self.assertEqual(d["insecure_resources"], ["http://cdn.test/x.js"])
        self.assertEqual(d["images_no_alt"], ["a.jpg"])


if __name__ == "__main__":
    unittest.main()
