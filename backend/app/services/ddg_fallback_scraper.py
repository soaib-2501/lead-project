"""
Fallback social links + images source: DuckDuckGo Search (via the ddgs library).

WHY DUCKDUCKGO INSTEAD OF GOOGLE:
An earlier version of this fallback used Playwright to drive Google Search,
but Google's bot-detection triggered CAPTCHA/block pages very quickly under
even light request volume, which meant a cooldown period during which
social links/images came back empty. DuckDuckGo's search library (ddgs)
doesn't require a browser at all — it's a direct HTTP-based text/image
search — and in practice tolerates far more requests before any blocking
behavior shows up. It's also faster (no browser tab to open/wait on).

WHY THIS EXISTS AT ALL:
social_scraper.py can only find social links/images/email by visiting a
business's OWN WEBSITE. Many small businesses have no website at all —
their only online presence is their Google Business Profile and/or social
media pages. For those, this module searches DuckDuckGo for the business
directly instead of leaving social/image fields empty.

APPROACH: One `site:instagram.com` and one `site:facebook.com` text search
per business, plus one image search. No browser session needed, so this
does NOT take a Playwright `browser` object — it can be called standalone.
"""

import logging
import re

from ddgs import DDGS

logger = logging.getLogger(__name__)

MAX_IMAGES = 6

SOCIAL_DOMAINS = {
    "instagram": "instagram.com",
    "facebook": "facebook.com",
}

# Handle values that mean "this isn't a business's own profile page" —
# a single post, hashtag/explore page, login wall, etc.
NOISE_HANDLES = {
    "p", "reel", "reels", "explore", "accounts", "stories", "tv",
    "directory", "login", "share", "sharer", "dialog", "about",
    "help", "legal", "privacy", "terms", "policies", "ads",
}


def _location_hint(address: str) -> str:
    """
    Picks a useful city/area fragment from a full address instead of just
    taking the first comma-separated chunk (usually a shop/floor number).
    Prefers the second-to-last segment, which is typically the city
    (e.g. "..., Sector 62, Noida, Uttar Pradesh 201309" -> "Noida").
    """
    parts = [p.strip() for p in address.split(",") if p.strip()]
    if len(parts) >= 2:
        return parts[-2]
    if parts:
        return parts[0]
    return ""


def get_social_links_from_ddg(name: str, address: str = "") -> dict:
    """One site:-filtered text search per platform, no browser required."""
    location_hint = _location_hint(address)
    links = {}

    for platform, domain in SOCIAL_DOMAINS.items():
        query = f"site:{domain} {name} {location_hint}".strip()

        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=5))

            for r in results:
                url = r.get("href") or r.get("url") or ""
                if domain not in url:
                    continue

                match = re.search(rf"{re.escape(domain)}/([a-zA-Z0-9_.\-]{{2,50}})", url, re.I)
                if not match:
                    continue

                handle = match.group(1)
                if handle.lower() in NOISE_HANDLES:
                    continue

                links[platform] = f"https://{domain}/{handle}"
                logger.info(f"[ddg_fallback] {platform}: found {links[platform]} for '{name}'")
                break

            if platform not in links:
                logger.info(f"[ddg_fallback] {platform}: no result for '{name}'")

        except Exception as e:
            logger.warning(f"[ddg_fallback] {platform} search failed for '{name}': {e}")
            continue

    return links


def get_images_from_ddg(name: str, address: str = "") -> list[str]:
    """DuckDuckGo image search — returns thumbnail URLs."""
    location_hint = _location_hint(address)
    query = f"{name} {location_hint}".strip()
    images = []

    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(query, max_results=MAX_IMAGES))

        for r in results:
            src = r.get("image") or r.get("thumbnail")
            if src and src not in images:
                images.append(src)
            if len(images) >= MAX_IMAGES:
                break

        logger.info(f"[ddg_fallback] images: found {len(images)} for '{name}'")

    except Exception as e:
        logger.warning(f"[ddg_fallback] Image search failed for '{name}': {e}")

    return images


def get_ddg_fallback_intel(name: str, address: str = "") -> dict:
    """
    Combined fallback lookup, called only when a business has no website.
    No browser argument needed — this is pure HTTP-based search.
    """
    return {
        "social_links": get_social_links_from_ddg(name, address),
        "images": get_images_from_ddg(name, address),
    }