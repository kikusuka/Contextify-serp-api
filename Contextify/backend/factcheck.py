"""Search established fact-checking sites for evidence about a claim (Role 3).

search_factchecks(claim) returns up to 5 evidence items:
    {"title", "link", "source", "date", "snippet"}

How it works
- sites come from factcheck_sites.json (the file order is the priority order).
  Broad news sites (Reuters, India Today...) have a "path" so only their fact-check
  section counts, not every news article.
- Google ignores very long queries, so the sites are split into small groups and each
  group is one SerpApi "google" query (SerpApi credits used per check = _MAX_QUERIES).
- Every result is checked against the allowlist before it is returned.

Raises RuntimeError when the search itself is broken (missing key, SerpApi error) so
the backend can tell the user a part is missing. A search with no matches returns [].
Needs the google-search-results package and a SerpApi key (passed in by the backend).
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_SITES_FILE = Path(__file__).with_name("factcheck_sites.json")
_MAX_RESULTS = 5
_QUERY_CHUNK = 7      # sites per Google query (keeps the query short enough)
_MAX_QUERIES = 2      # how many chunks we search = SerpApi credits per check
_MAX_CLAIM_WORDS = 12


def _load_sites() -> list[dict[str, str]]:
    """Read and validate the site list; a broken file gives an empty list."""
    try:
        data = json.loads(_SITES_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    sites = []
    for site in data:
        if not isinstance(site, dict):
            continue
        if not all(isinstance(site.get(k), str) and site[k].strip()
                   for k in ("name", "domain", "country")):
            continue
        path = site.get("path", "")
        if not isinstance(path, str):
            continue
        sites.append({**site, "path": path.strip("/")})
    return sites


def _site_term(site: dict[str, str]) -> str:
    return f"site:{site['domain']}" + (f"/{site['path']}" if site["path"] else "")


def _serpapi_search(params: dict[str, str]) -> dict[str, Any]:
    """Call SerpApi using the google-search-results client."""
    from serpapi import GoogleSearch  # type: ignore[import-not-found]

    response = GoogleSearch(params).get_dict()
    return response if isinstance(response, dict) else {}


def _run_query(claim_words: str, sites: list[dict[str, str]], api_key: str) -> list[Any]:
    terms = " OR ".join(_site_term(s) for s in sites)
    response = _serpapi_search({
        "engine": "google",
        "q": f"{claim_words} ({terms})",
        "gl": "in",
        "hl": "en",
        "num": "10",
        "api_key": api_key,
    })
    error = response.get("error")
    if error:
        if "hasn't returned any results" in str(error):
            return []  # no matches is not a failure
        raise RuntimeError(f"SerpApi error: {error}")
    results = response.get("organic_results", [])
    return results if isinstance(results, list) else []


def _match_site(link: str, sites: list[dict[str, str]]) -> dict[str, str] | None:
    parsed = urlparse(link)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.lstrip("/").lower()
    for site in sites:
        domain = site["domain"].lower()
        if host != domain and not host.endswith("." + domain):
            continue
        prefix = site["path"].lower()
        if prefix and not (path == prefix or path.startswith(prefix + "/")
                           or path.startswith(prefix)):
            continue
        return site
    return None


def search_factchecks(claim: str, api_key: str | None = None) -> list[dict[str, str]]:
    """Find up to five fact-check articles matching *claim*.

    api_key: the user's SerpApi key (sent from the web page). Falls back to the
    SERPAPI_API_KEY environment variable if not given.
    """
    if not isinstance(claim, str) or not claim.strip():
        return []
    api_key = (api_key or os.getenv("SERPAPI_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("SerpApi key is missing (add it in the API keys box on the page)")
    sites = _load_sites()
    if not sites:
        raise RuntimeError("factcheck_sites.json is missing or invalid")

    claim_words = " ".join(claim.split()[:_MAX_CLAIM_WORDS])
    chunks = [sites[i:i + _QUERY_CHUNK] for i in range(0, len(sites), _QUERY_CHUNK)]
    chunks = chunks[:_MAX_QUERIES]

    def run(chunk):
        try:
            return _run_query(claim_words, chunk, api_key), None
        except Exception as exc:  # one failed query should not lose the others
            return [], exc

    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        outcomes = list(pool.map(run, chunks))  # map keeps priority order

    if all(err is not None for _, err in outcomes):
        raise RuntimeError(f"Fact-check search failed: {outcomes[0][1]}")

    evidence: list[dict[str, str]] = []
    seen: set[str] = set()
    for results, _err in outcomes:
        for item in results:
            if not isinstance(item, dict):
                continue
            link, title = item.get("link"), item.get("title")
            if not isinstance(link, str) or not isinstance(title, str):
                continue
            link = link.strip()
            if not link.startswith(("https://", "http://")) or link in seen:
                continue
            site = _match_site(link, sites)
            if site is None:  # never accept results outside the allowlist
                continue
            evidence.append({
                "title": title.strip(),
                "link": link,
                "source": site["name"],
                "date": str(item.get("date") or item.get("published_date") or "").strip(),
                "snippet": str(item.get("snippet") or "").strip(),
            })
            seen.add(link)
            if len(evidence) == _MAX_RESULTS:
                return evidence
    return evidence
