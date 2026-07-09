"""
Social media links + brand images extraction from a business's own website.

WHY THIS IS A SEPARATE MODULE FROM maps_scraper.py:
Google Maps almost never lists a business's social media accounts or brand
imagery directly — the reliable source is the business's own website
(footer/header links, meta tags), which is a completely different fetch (a
plain HTTP page, not a Maps listing) with a different failure mode (site
down, blocks bots, no website at all). Keeping it separate means a broken
website never touches the Maps scraping logic.

APPROACH: httpx + regex + light HTML parsing over the raw HTML. No
JavaScript execution — just a scan of meta tags, JSON-LD, and every
link/script tag for known patterns.

CONCURRENCY: extract_site_intel_batch() fetches many websites at once using
asyncio + httpx.AsyncClient, bounded by a semaphore. This is the fix for the
biggest performance problem in the pipeline — doing these fetches one at a
time inside the Maps scraping loop meant total time = sum of every site's
fetch time (including slow 403s and timeouts). Fetching concurrently means
total time ~= the single slowest fetch, since they all wait in parallel.
"""

import asyncio
import logging
import re
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

SOCIAL_PATTERNS = {
    "facebook": re.compile(r"facebook\.com/[a-zA-Z0-9_.\-/]+", re.I),
    "instagram": re.compile(r"instagram\.com/[a-zA-Z0-9_.\-/]+", re.I),
    "twitter": re.compile(r"(?:twitter\.com|x\.com)/[a-zA-Z0-9_.\-/]+", re.I),
    "linkedin": re.compile(r"linkedin\.com/[a-zA-Z0-9_.\-/]+", re.I),
    "youtube": re.compile(r"youtube\.com/[a-zA-Z0-9_.\-/@]+", re.I),
    "pinterest": re.compile(r"pinterest\.[a-z.]+/[a-zA-Z0-9_.\-/]+", re.I),
    "tiktok": re.compile(r"tiktok\.com/@[a-zA-Z0-9_.\-]+", re.I),
    "threads": re.compile(r"threads\.net/@[a-zA-Z0-9_.\-]+", re.I),
    "whatsapp": re.compile(r"wa\.me/[0-9]+", re.I),
    "telegram": re.compile(r"t\.me/[a-zA-Z0-9_]+", re.I),
    "github": re.compile(r"github\.com/[a-zA-Z0-9_.\-]+", re.I),
}

NOISE_PATTERNS = ("sharer", "share.php", "intent/tweet", "login", "dialog", "/plugins/")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".svg", ".gif")

EMPTY_INTEL = {"social_links": {}, "images": {"og_image": None, "favicon": None, "logo": None, "gallery": []}}


def _clean_url(raw: str) -> str:
    return raw.rstrip("/\"'")


def _make_absolute(base_url: str, maybe_relative: str) -> str:
    try:
        return urljoin(base_url, maybe_relative)
    except Exception:
        return maybe_relative


def _extract_social_links(html: str) -> dict:
    links = {}

    for ld_match in re.finditer(r'"sameAs"\s*:\s*\[(.*?)\]', html, re.S):
        block = ld_match.group(1)
        for platform, pattern in SOCIAL_PATTERNS.items():
            if platform in links:
                continue
            match = pattern.search(block)
            if match:
                links[platform] = "https://" + _clean_url(match.group(0))

    for platform, pattern in SOCIAL_PATTERNS.items():
        if platform in links:
            continue
        for match in pattern.finditer(html):
            candidate = _clean_url(match.group(0))
            if any(noise in candidate.lower() for noise in NOISE_PATTERNS):
                continue
            links[platform] = "https://" + candidate
            break

    return links


def _extract_images(html: str, base_url: str) -> dict:
    images = {"og_image": None, "favicon": None, "logo": None, "gallery": []}

    og_match = re.search(
        r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html, re.I,
    )
    if not og_match:
        og_match = re.search(
            r'<meta[^>]+(?:property|name)=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            html, re.I,
        )
    if og_match:
        images["og_image"] = _make_absolute(base_url, og_match.group(1))

    fav_match = re.search(
        r'<link[^>]+rel=["\'](?:shortcut )?icon["\'][^>]+href=["\']([^"\']+)["\']',
        html, re.I,
    )
    if fav_match:
        images["favicon"] = _make_absolute(base_url, fav_match.group(1))
    else:
        images["favicon"] = _make_absolute(base_url, "/favicon.ico")

    logo_match = re.search(r'"logo"\s*:\s*"([^"]+)"', html)
    if logo_match:
        images["logo"] = _make_absolute(base_url, logo_match.group(1))

    for img_match in re.finditer(r'<img[^>]+>', html, re.I):
        tag = img_match.group(0)
        src_match = re.search(r'src=["\']([^"\']+)["\']', tag, re.I)
        alt_match = re.search(r'alt=["\']([^"\']*)["\']', tag, re.I)
        if not src_match:
            continue
        src = src_match.group(1)
        alt = (alt_match.group(1) if alt_match else "").lower()
        if not images["logo"] and ("logo" in src.lower() or "logo" in alt):
            images["logo"] = _make_absolute(base_url, src)
            break

    seen = set()
    for img_match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I):
        src = img_match.group(1)
        if not src.lower().endswith(IMAGE_EXTENSIONS):
            continue
        if any(skip in src.lower() for skip in ("pixel", "tracking", "spacer", "1x1")):
            continue
        absolute = _make_absolute(base_url, src)
        if absolute in seen:
            continue
        seen.add(absolute)
        images["gallery"].append(absolute)
        if len(images["gallery"]) >= 8:
            break

    return images


async def _fetch_one_async(client: httpx.AsyncClient, semaphore: asyncio.Semaphore,
                            website_url: str, timeout: float) -> dict:
    """Fetches and parses a single website, bounded by the shared semaphore."""
    parsed = urlparse(website_url)
    normalized = website_url if parsed.scheme else "https://" + website_url

    async with semaphore:
        try:
            response = await client.get(normalized, timeout=timeout, follow_redirects=True)
            response.raise_for_status()
            html = response.text
            final_url = str(response.url)
        except Exception as e:
            logger.warning(f"[social_scraper] Could not fetch {website_url}: {e}")
            return dict(EMPTY_INTEL)

    social_links = _extract_social_links(html)
    images = _extract_images(html, final_url)

    if social_links:
        logger.info(f"[social_scraper] Found {len(social_links)} social links for {website_url}: {list(social_links.keys())}")
    else:
        logger.info(f"[social_scraper] No social links found for {website_url}")

    return {"social_links": social_links, "images": images}


async def extract_site_intel_batch(website_urls: list[str], max_concurrent: int = 8,
                                    timeout: float = 8.0) -> dict:
    """
    Fetches site intel (social links + images) for many websites concurrently.

    Bounded by max_concurrent so we don't open dozens of simultaneous
    connections at once (polite to target servers, and avoids the local
    machine running out of sockets on a big search). Returns a dict keyed
    by the ORIGINAL url string passed in, so callers can match results back
    to businesses without worrying about redirect changes.
    """
    if not website_urls:
        return {}

    semaphore = asyncio.Semaphore(max_concurrent)
    results = {}

    async with httpx.AsyncClient(headers=HEADERS) as client:
        tasks = {url: asyncio.create_task(_fetch_one_async(client, semaphore, url, timeout))
                 for url in website_urls}
        for url, task in tasks.items():
            try:
                results[url] = await task
            except Exception as e:
                logger.warning(f"[social_scraper] Task failed for {url}: {e}")
                results[url] = dict(EMPTY_INTEL)

    return results


def extract_social_links(website_url: str, timeout: float = 8.0) -> dict:
    """Sync single-site helper, kept for any other callers that need one-off lookups."""
    result = asyncio.run(extract_site_intel_batch([website_url], max_concurrent=1, timeout=timeout))
    return result.get(website_url, dict(EMPTY_INTEL))["social_links"]


def extract_site_intel(website_url: str, timeout: float = 8.0) -> dict:
    """Sync single-site helper, kept for any other callers that need one-off lookups."""
    result = asyncio.run(extract_site_intel_batch([website_url], max_concurrent=1, timeout=timeout))
    return result.get(website_url, dict(EMPTY_INTEL))