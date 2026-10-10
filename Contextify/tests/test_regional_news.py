import os
import sys
import types
import unittest
from unittest import mock

from backend.regional_news import (
    LIVE_LABEL,
    MOCK_LABEL,
    REGIONS,
    MockSerpApi,
    SerpApiProvider,
    get_regional_news,
)


class RecordingProvider:
    is_mock = False

    def __init__(self, count=7, fail_gl=None):
        self.count = count
        self.fail_gl = fail_gl
        self.calls = []

    def search(self, query, *, gl):
        self.calls.append((query, gl))
        if gl == self.fail_gl:
            raise RuntimeError("simulated provider outage")
        return [
            {
                "title": f"Headline {i}",
                "link": f"https://news.example/{gl}/{i}",
                "source": f"Publisher {i}",
                "date": "2026-01-01",
                "snippet": "Sample snippet",
            }
            for i in range(self.count)
        ]


def fake_serpapi(payload):
    """Build a fake `serpapi` module whose GoogleSearch returns `payload`."""
    module = types.ModuleType("serpapi")

    class GoogleSearch:
        def __init__(self, params):
            self.params = params

        def get_dict(self):
            return payload

    module.GoogleSearch = GoogleSearch
    return module


class RegionalNewsTests(unittest.TestCase):
    def test_mock_provider_output_is_labelled_mock(self):
        output = get_regional_news("sample claim", provider=MockSerpApi())
        self.assertEqual(output["data_mode"], MOCK_LABEL)
        self.assertTrue(output["is_mock"])
        self.assertEqual(list(output["regions"]), [r.name for r in REGIONS])
        self.assertEqual(output["errors"], {})
        for items in output["regions"].values():
            self.assertEqual(len(items), 5)
            for item in items:
                self.assertEqual(
                    set(item),
                    {"title", "link", "source_name", "date", "snippet", "is_mock"},
                )
                self.assertTrue(item["is_mock"])
                self.assertIn("[MOCK]", item["title"])

    def test_real_provider_items_are_not_marked_mock(self):
        output = get_regional_news("claim", provider=RecordingProvider())
        self.assertFalse(output["is_mock"])
        self.assertEqual(output["data_mode"], LIVE_LABEL)
        for items in output["regions"].values():
            self.assertTrue(all(item["is_mock"] is False for item in items))

    def test_query_has_no_quotes(self):
        provider = RecordingProvider()
        get_regional_news("lemon water cures cancer", provider=provider)
        for query, _gl in provider.calls:
            self.assertNotIn('"', query)
            self.assertIn("lemon water cures cancer", query)

    def test_limits_each_region_to_five_items(self):
        output = get_regional_news("claim", provider=RecordingProvider(count=12))
        self.assertTrue(all(len(items) == 5 for items in output["regions"].values()))

    def test_empty_or_whitespace_claim_skips_provider(self):
        for claim in ("", "   ", None):
            provider = RecordingProvider()
            output = get_regional_news(claim, provider=provider)
            self.assertEqual(provider.calls, [])
            self.assertEqual(output["errors"], {})
            self.assertTrue(all(not items for items in output["regions"].values()))

    def test_region_failure_does_not_block_other_regions(self):
        provider = RecordingProvider(fail_gl="us")
        output = get_regional_news("claim", provider=provider)
        self.assertEqual(sorted(call[1] for call in provider.calls), ["gb", "in", "us"])
        self.assertEqual(len(output["regions"]["India"]), 5)
        self.assertEqual(output["regions"]["USA"], [])
        self.assertEqual(len(output["regions"]["UK"]), 5)
        self.assertIn("simulated provider outage", output["errors"]["USA"])

    def test_missing_api_key_reports_error_per_region(self):
        with mock.patch.dict(os.environ, {"CONTEXTIFY_MOCK": "0"}):
            os.environ.pop("SERPAPI_API_KEY", None)
            output = get_regional_news("claim", provider=SerpApiProvider(api_key=None))
        self.assertEqual(set(output["errors"]), {r.name for r in REGIONS})
        self.assertIn("SerpApi key", output["errors"]["India"])

    def test_api_key_argument_reaches_serpapi(self):
        seen = {}

        class Spy:
            def __init__(self, params):
                seen["key"] = params["api_key"]

            def get_dict(self):
                return {"news_results": []}

        module = types.ModuleType("serpapi")
        module.GoogleSearch = Spy
        with mock.patch.dict(os.environ, {"CONTEXTIFY_MOCK": "0", "SERPAPI_API_KEY": ""}):
            with mock.patch.dict(sys.modules, {"serpapi": module}):
                output = get_regional_news("claim", api_key="typed-in-key")
        self.assertEqual(seen["key"], "typed-in-key")
        self.assertEqual(output["errors"], {})

    def test_serpapi_provider_parses_sources_and_story_clusters(self):
        payload = {
            "news_results": [
                {"title": "A", "link": "https://a.example/1", "source": {"name": "Pub A"},
                 "date": "1 hour ago", "snippet": "snip"},
                {"stories": [
                    {"title": "B", "link": "https://b.example/1", "source": {"name": "Pub B"},
                     "date": "2 hours ago"},
                ]},
            ]
        }
        with mock.patch.dict(sys.modules, {"serpapi": fake_serpapi(payload)}):
            raw = SerpApiProvider(api_key="test").search("claim news", gl="in")
        self.assertEqual([r["source"] for r in raw], ["Pub A", "Pub B"])
        self.assertEqual(raw[1]["link"], "https://b.example/1")

    def test_serpapi_no_results_is_empty_not_error(self):
        payload = {"error": "Google hasn't returned any results for this query."}
        with mock.patch.dict(sys.modules, {"serpapi": fake_serpapi(payload)}):
            self.assertEqual(SerpApiProvider(api_key="test").search("x", gl="in"), [])

    def test_serpapi_other_errors_are_raised(self):
        with mock.patch.dict(sys.modules, {"serpapi": fake_serpapi({"error": "Invalid API key"})}):
            with self.assertRaises(RuntimeError):
                SerpApiProvider(api_key="bad").search("x", gl="in")


if __name__ == "__main__":
    unittest.main()
