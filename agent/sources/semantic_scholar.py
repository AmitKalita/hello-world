"""Fetch recent papers from the Semantic Scholar Graph API.

Free to use; an optional API key (SEMANTIC_SCHOLAR_API_KEY) raises
the rate limit but is not required to get started.
https://api.semanticscholar.org/api-docs/graph
"""

import logging
import os

import requests

from agent.utils import cutoff_date, parse_date_loose

logger = logging.getLogger(__name__)

SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
FIELDS = "title,abstract,authors,publicationDate,year,externalIds,url"


def fetch_papers(terms: list[str], lookback_days: int, max_items: int) -> list[dict]:
    since = cutoff_date(lookback_days)
    headers = {}
    api_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    if api_key:
        headers["x-api-key"] = api_key

    query = " | ".join(terms)  # Semantic Scholar treats '|' as OR between terms
    params = {"query": query, "fields": FIELDS, "limit": min(max_items, 100)}

    try:
        resp = requests.get(SEARCH_URL, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Semantic Scholar request failed: %s", exc)
        return []

    papers = []
    for item in resp.json().get("data", []):
        pub_date = item.get("publicationDate") or str(item.get("year") or "")
        parsed = parse_date_loose(pub_date)
        if parsed and parsed < since:
            continue  # older than our lookback window

        doi = (item.get("externalIds") or {}).get("DOI", "")
        authors = ", ".join(a.get("name", "") for a in item.get("authors", []) or [])
        papers.append(
            {
                "id": doi or item.get("url", ""),
                "source": "Semantic Scholar",
                "title": item.get("title", "") or "",
                "authors": authors,
                "date": pub_date,
                "doi": doi,
                "url": item.get("url", ""),
                "abstract": item.get("abstract", "") or "",
            }
        )
        if len(papers) >= max_items:
            break
    return papers
