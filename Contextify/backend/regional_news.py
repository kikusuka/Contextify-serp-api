"""Regional news lookup for Contextify (Role 4).

get_regional_news(claim) searches SerpApi's google_news engine for India, the US and
the UK (gl=in / us / gb) in parallel and returns:

    {"data_mode": "...", "is_mock": False,
     "regions": {"India": [item, ...], "USA": [...], "UK": [...]},
     "errors":  {"UK": "RuntimeError: ..."}}          # only regions that failed

item = {"title", "link", "source_name", "date", "snippet", "is_mock"}

Needs a SerpApi key: pass api_key=... (the backend passes the key the user typed on the
page), or set SERPAPI_API_KEY in the environment. Set CONTEXTIFY_MOCK=1 to use fake
offline data for UI testing; mock items are always marked is_mock=True.
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol

MAX_RESULTS_PER_REGION = 5
MAX_QUERY_CHARS = 200
MOCK_LABEL = "MOCK DATA — NOT REAL EVIDENCE"
LIVE_LABEL = "LIVE: SerpApi google_news"


@dataclass(frozen=True)
class Region:
    name: str
    gl: str


REGIONS = (
    Region("India", "in"),
    Region("USA", "us"),
    Region("UK", "gb"),
)


class SearchProvider(Protocol):
    """Provider boundary. Implementations return a list of simple result dicts."""

    is_mock: bool

    def search(self, query: str, *, gl: str) -> list[dict[str, Any]]: ...


class MockSerpApi:
    """Offline stand-in with obviously synthetic, non-citable results."""

    is_mock = True

    def search(self, query: str, *, gl: str) -> list[dict[str, Any]]:
        region = next((r.name for r in REGIONS if r.gl == gl), "Unknown region")
        return [
            {
                "title": f"[MOCK] Sample result {i} for {region}",
                "link": f"https://{gl}.mock-search.example/result-{i}",
                "source": f"Mock source {i}",
                "date": "MOCK DATE",
                "snippet": (
                    f"Synthetic fixture for query {query!r}; this is not a news "
                    "article and must not be treated as evidence."
                ),
            }
            for i in range(1, MAX_RESULTS_PER_REGION + 1)
        ]


class SerpApiProvider:
    """Real provider: SerpApi google_news (pip install google-search-results)."""

    is_mock = False

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("SERPAPI_API_KEY")

    def search(self, query: str, *, gl: str) -> list[dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("SerpApi key is missing (add it in the API keys box on the page)")
        from serpapi import GoogleSearch  # imported here so tests need no network package

        data = GoogleSearch(
            {"engine": "google_news", "q": query, "gl": gl, "hl": "en", "api_key": self.api_key}
        ).get_dict()

        error = data.get("error")
        if error:
            if "hasn't returned any results" in str(error):
                return []  # no results is not a failure
            raise RuntimeError(str(error))

        out: list[dict[str, Any]] = []
        for result in data.get("news_results") or []:
            # some results are story clusters that hold the real articles in "stories"
            for item in result.get("stories") or [result]:
                source = item.get("source")
                if isinstance(source, dict):
                    source = source.get("name", "")
                out.append(
                    {
                        "title": item.get("title"),
                        "link": item.get("link"),
                        "source": source,
                        "date": item.get("date"),
                        "snippet": item.get("snippet", ""),
                    }
                )
        return out


def _normalize_result(result: dict[str, Any], *, is_mock: bool) -> dict[str, Any]:
    """Map provider keys onto the public item schema."""
    source = result.get("source") or result.get("source_name") or ""
    if isinstance(source, dict):
        source = source.get("name", "")
    return {
        "title": result.get("title") or "",
        "link": result.get("link") or result.get("url") or "",
        "source_name": source,
        "date": result.get("date") or result.get("published_date") or "",
        "snippet": result.get("snippet") or "",
        "is_mock": is_mock,
    }


def _default_provider(api_key: str | None = None) -> SearchProvider | None:
    """Mock only if CONTEXTIFY_MOCK=1, otherwise the real SerpApi provider."""
    if os.getenv("CONTEXTIFY_MOCK") == "1":
        return MockSerpApi()
    return SerpApiProvider(api_key)


def get_regional_news(
    claim: str,
    *,
    provider: SearchProvider | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Return news results grouped by India, USA and UK.

    Each region is searched independently (in parallel), so a failure in one region
    does not stop the others. Empty or whitespace claims skip all searches.
    """
    results: dict[str, list[dict[str, Any]]] = {r.name: [] for r in REGIONS}
    errors: dict[str, str] = {}
    cleaned_claim = claim.strip() if isinstance(claim, str) else ""
    search_provider = provider if provider is not None else _default_provider(api_key)
    is_mock = bool(getattr(search_provider, "is_mock", False))

    if cleaned_claim:
        # No quotes around the claim: quotes force an exact-phrase match that rarely finds news.
        query = f"{cleaned_claim[:MAX_QUERY_CHARS]} news"

        def run(region: Region):
            try:
                raw = search_provider.search(query, gl=region.gl)
                items = [
                    _normalize_result(item, is_mock=is_mock)
                    for item in (raw or [])[:MAX_RESULTS_PER_REGION]
                ]
                return region.name, items, None
            except Exception as exc:  # isolate a regional failure
                return region.name, [], f"{type(exc).__name__}: {exc}"

        with ThreadPoolExecutor(max_workers=len(REGIONS)) as pool:
            for name, items, err in pool.map(run, REGIONS):  # map keeps region order
                results[name] = items
                if err:
                    errors[name] = err

    return {
        "data_mode": MOCK_LABEL if is_mock else LIVE_LABEL,
        "is_mock": is_mock,
        "regions": results,
        "errors": errors,
    }
