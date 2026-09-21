"""Fetch recent papers from Europe PMC.

Europe PMC indexes PubMed/MEDLINE, PubMed Central, and preprint
servers (bioRxiv, medRxiv, ChemRxiv, etc.) behind a single free,
ToS-compliant search API, which is why we use it instead of calling
PubMed and bioRxiv separately: https://europepmc.org/RestfulWebService
"""

from datetime import datetime, timezone
import logging

import requests

from agent.utils import cutoff_date

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


def fetch_papers(terms: list[str], lookback_days: int, max_items: int) -> list[dict]:
    """Search Europe PMC for the given terms, restricted to recent items.

    Returns a list of dicts with a common shape used by the rest of
    the pipeline: id, source, title, authors, date, doi, url, abstract.
    """
    since = cutoff_date(lookback_days).strftime("%Y-%m-%d")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    term_query = " OR ".join(f'"{term}"' for term in terms)
    query = f"({term_query}) AND FIRST_PDATE:[{since} TO {today}]"

    params = {
        "query": query,
        "format": "json",
        "resultType": "core",
        "pageSize": min(max_items, 100),
        "sort": "P_PDATE_D desc",
    }

    try:
        resp = requests.get(SEARCH_URL, params=params, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Europe PMC request failed: %s", exc)
        return []

    results = resp.json().get("resultList", {}).get("result", [])
    papers = []
    for item in results[:max_items]:
        doi = item.get("doi", "")
        url = f"https://doi.org/{doi}" if doi else item.get("fullTextUrlList", {}).get(
            "fullTextUrl", [{}]
        )[0].get("url", "")
        papers.append(
            {
                "id": doi or item.get("id", ""),
                "source": item.get("source", "Europe PMC"),
                "title": item.get("title", "").strip(),
                "authors": item.get("authorString", ""),
                "date": item.get("firstPublicationDate", item.get("pubYear", "")),
                "doi": doi,
                "url": url,
                "abstract": item.get("abstractText", ""),
            }
        )
    return papers
