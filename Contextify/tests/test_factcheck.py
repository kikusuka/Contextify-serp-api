import os
import unittest
from unittest import mock

from backend import factcheck


def result(link, title="T", snippet="S", date="2026-01-01"):
    return {"link": link, "title": title, "snippet": snippet, "date": date}


class FactcheckTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"SERPAPI_API_KEY": "test-key"})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_returns_evidence_items_with_expected_fields(self):
        payload = {"organic_results": [result("https://www.altnews.in/a-claim")]}
        with mock.patch.object(factcheck, "_serpapi_search", return_value=payload):
            out = factcheck.search_factchecks("lemon water cures cancer")
        self.assertEqual(set(out[0]), {"title", "link", "source", "date", "snippet"})
        self.assertEqual(out[0]["source"], "Alt News")

    def test_blank_claim_returns_empty_without_searching(self):
        with mock.patch.object(factcheck, "_serpapi_search") as search:
            self.assertEqual(factcheck.search_factchecks("   "), [])
            search.assert_not_called()

    def test_results_outside_allowlist_are_dropped(self):
        payload = {"organic_results": [result("https://random-blog.example/post")]}
        with mock.patch.object(factcheck, "_serpapi_search", return_value=payload):
            self.assertEqual(factcheck.search_factchecks("claim"), [])

    def test_broad_news_site_only_counts_inside_its_fact_check_path(self):
        payload = {"organic_results": [
            result("https://www.reuters.com/world/some-news-story/"),
            result("https://www.reuters.com/fact-check/some-claim-2026/"),
        ]}
        with mock.patch.object(factcheck, "_serpapi_search", return_value=payload):
            out = factcheck.search_factchecks("claim")
        self.assertEqual([r["link"] for r in out],
                         ["https://www.reuters.com/fact-check/some-claim-2026/"])

    def test_caps_at_five_and_removes_duplicates(self):
        links = [f"https://www.boomlive.in/fact-check/{i}" for i in range(8)]
        payload = {"organic_results": [result(links[0])] + [result(l) for l in links]}
        with mock.patch.object(factcheck, "_serpapi_search", return_value=payload):
            out = factcheck.search_factchecks("claim")
        self.assertEqual(len(out), 5)
        self.assertEqual(len({r["link"] for r in out}), 5)

    def test_query_is_short_and_uses_site_operators(self):
        seen = []

        def fake(params):
            seen.append(params["q"])
            return {"organic_results": []}

        long_claim = " ".join(f"word{i}" for i in range(40))
        with mock.patch.object(factcheck, "_serpapi_search", side_effect=fake):
            factcheck.search_factchecks(long_claim)
        self.assertEqual(len(seen), factcheck._MAX_QUERIES)
        for q in seen:
            self.assertIn("site:", q)
            self.assertNotIn("word12", q)  # claim trimmed to 12 words

    def test_no_results_error_is_empty_list(self):
        payload = {"error": "Google hasn't returned any results for this query."}
        with mock.patch.object(factcheck, "_serpapi_search", return_value=payload):
            self.assertEqual(factcheck.search_factchecks("claim"), [])

    def test_missing_key_raises_clear_error(self):
        with mock.patch.dict(os.environ, {"SERPAPI_API_KEY": ""}):
            with self.assertRaises(RuntimeError) as ctx:
                factcheck.search_factchecks("claim")
        self.assertIn("SerpApi key", str(ctx.exception))

    def test_all_queries_failing_raises_but_one_failure_does_not(self):
        with mock.patch.object(factcheck, "_serpapi_search", side_effect=OSError("down")):
            with self.assertRaises(RuntimeError):
                factcheck.search_factchecks("claim")

        calls = {"n": 0}

        def flaky(params):
            calls["n"] += 1
            if calls["n"] == 1 and "altnews.in" in params["q"]:
                raise OSError("first query down")
            return {"organic_results": [result("https://www.snopes.com/fact-check/x")]}

        with mock.patch.object(factcheck, "_serpapi_search", side_effect=flaky):
            out = factcheck.search_factchecks("claim")
        self.assertEqual(out[0]["source"], "Snopes")

    def test_key_passed_in_is_used_without_env(self):
        seen = {}

        def fake(params):
            seen["key"] = params["api_key"]
            return {"organic_results": []}

        with mock.patch.dict(os.environ, {"SERPAPI_API_KEY": ""}):
            with mock.patch.object(factcheck, "_serpapi_search", side_effect=fake):
                factcheck.search_factchecks("claim", api_key="typed-in-key")
        self.assertEqual(seen["key"], "typed-in-key")

    def test_site_list_is_valid(self):
        sites = factcheck._load_sites()
        self.assertGreaterEqual(len(sites), 20)
        self.assertTrue(all(s["domain"] and s["name"] for s in sites))


if __name__ == "__main__":
    unittest.main()
