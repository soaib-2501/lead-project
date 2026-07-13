import logging
import requests
from bs4 import BeautifulSoup

from app.services.osint.utils import extract_emails, extract_phones

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}


def fetch_page(url: str) -> dict:
    result = {"url": url, "title": "", "description": "", "emails": [], "phones": []}

    try:
        response = requests.get(url, headers=HEADERS, timeout=6)

        if response.status_code != 200:
            logger.info("Fetch %s → HTTP %d, skipping", url, response.status_code)
            return result

        soup = BeautifulSoup(response.text, "lxml")

        if soup.title and soup.title.string:
            result["title"] = soup.title.string.strip()

        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc and meta_desc.get("content"):
            result["description"] = meta_desc["content"].strip()

        page_text = soup.get_text(" ", strip=True)[:5000]
        result["emails"] = extract_emails(page_text)
        result["phones"] = extract_phones(page_text)

        logger.info(
            "Fetch %s → title=%r emails=%d phones=%d",
            url, result["title"][:40], len(result["emails"]), len(result["phones"]),
        )

    except Exception as exc:
        logger.warning("Could not fetch %s: %s", url, exc)

    return result