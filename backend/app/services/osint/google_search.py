import logging
import time
from ddgs import DDGS

logger = logging.getLogger(__name__)


def search_google(query: str, num_results: int = 6) -> list[dict]:
    results = []
    try:
        with DDGS() as ddgs:
            raw_results = ddgs.text(query, max_results=num_results)
            for r in raw_results:
                if "href" in r:
                    results.append({
                        "url": r["href"],
                        "title": r.get("title", ""),
                        "snippet": r.get("body", ""),
                    })
        logger.debug("Query '%s' → %d results", query, len(results))
    except Exception as exc:
        logger.warning("Search failed for query '%s': %s", query, exc)

    time.sleep(0.3)
    return results