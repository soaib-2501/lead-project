"""
Social media links + brand images extraction from a business's own website.

WHY THIS IS A SEPARATE MODULE FROM maps_scraper.py:
Google Maps almost never lists a business's social media accounts or brand
imagery directly — the reliable source is the business's own website
(footer/header links, meta tags), which is a completely different fetch (a
plain HTTP page, not a Maps listing) with a different failure mode (site
down, blocks bots, no website at all). Keeping it separate means a broken
website never touches the Maps scraping logic.

APPROACH: httpx (fast, no browser) + regex + light HTML parsing over the raw
HTML. Intentionally lightweight — no JavaScript execution, just a scan of
meta tags, JSON-LD, and every link/script tag for known patterns. Sites that
only render their footer/images via client-side JS won't be fully caught
here; if that turns out to be common, swap this for a Playwright-based fetch.
"""

import logging
import re
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

# ---------- Social platform patterns ----------
# Broadened beyond the original 5 — these are the platforms most commonly
# linked from small/medium business website footers.
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

# Paths that show up inside every social domain's own share/login widgets —
# matching these would misidentify a "share on Facebook" button as the
# business's own Facebook page, so they're excluded.
NOISE_PATTERNS = ("sharer", "share.php", "intent/tweet", "login", "dialog", "/plugins/")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".svg", ".gif")


def _clean_url(raw: str) -> str:
    return raw.rstrip("/\"'")


def _make_absolute(base_url: str, maybe_relative: str) -> str:
    """Turns '/img/logo.png' into 'https://example.com/img/logo.png'."""
    try:
        return urljoin(base_url, maybe_relative)
    except Exception:
        return maybe_relative


def _extract_social_links(html: str) -> dict:
    """Two-pass social link extraction: JSON-LD sameAs, then raw HTML scan."""
    links = {}

    # Pass 1: JSON-LD "sameAs" — most reliable when present, often used for SEO.
    for ld_match in re.finditer(r'"sameAs"\s*:\s*\[(.*?)\]', html, re.S):
        block = ld_match.group(1)
        for platform, pattern in SOCIAL_PATTERNS.items():
            if platform in links:
                continue
            match = pattern.search(block)
            if match:
                links[platform] = "https://" + _clean_url(match.group(0))

    # Pass 2: general HTML scan for anything JSON-LD missed.
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
    """
    Pulls brand-relevant images in priority order:
    - og:image / twitter:image (social share preview, usually the logo/hero)
    - <link rel="icon"> favicon
    - JSON-LD "logo" / "image" fields
    - a handful of <img> tags likely to be the logo (alt/src containing 'logo')
    - fallback: first few generic <img> tags on the page (gallery/product shots)
    """
    images = {"og_image": None, "favicon": None, "logo": None, "gallery": []}

    # og:image / twitter:image
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

    # favicon
    fav_match = re.search(
        r'<link[^>]+rel=["\'](?:shortcut )?icon["\'][^>]+href=["\']([^"\']+)["\']',
        html, re.I,
    )
    if fav_match:
        images["favicon"] = _make_absolute(base_url, fav_match.group(1))
    else:
        # sensible default most browsers/servers honor
        images["favicon"] = _make_absolute(base_url, "/favicon.ico")

    # JSON-LD logo/image
    logo_match = re.search(r'"logo"\s*:\s*"([^"]+)"', html)
    if logo_match:
        images["logo"] = _make_absolute(base_url, logo_match.group(1))

    # <img> tags whose src/alt hints at being the logo
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

    # Fallback gallery — first handful of real image files on the page,
    # skipping obvious icons/tracking pixels by size hints in the filename.
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


def extract_social_links(website_url: str, timeout: float = 8.0) -> dict:
    """Backward-compatible wrapper — social links only (used by existing callers)."""
    result = extract_site_intel(website_url, timeout=timeout)
    return result.get("social_links", {})


def extract_site_intel(website_url: str, timeout: float = 8.0) -> dict:
    """
    Fetches a business's homepage and returns social profile URLs + brand
    images in one pass (a single fetch is reused for both, since they both
    need the same HTML).

    Returns:
        {
            "social_links": {"facebook": "https://...", "instagram": "..."},
            "images": {
                "og_image": "https://...",
                "favicon": "https://...",
                "logo": "https://...",
                "gallery": ["https://...", ...]
            }
        }

    Returns empty structures on any failure — a missing/broken website
    should never crash a whole search batch.
    """
    empty = {"social_links": {}, "images": {"og_image": None, "favicon": None, "logo": None, "gallery": []}}

    if not website_url:
        return empty

    parsed = urlparse(website_url)
    if not parsed.scheme:
        website_url = "https://" + website_url

    try:
        with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
            response = client.get(website_url)
            response.raise_for_status()
            html = response.text
            final_url = str(response.url)  # after redirects, for correct relative-URL resolution
    except Exception as e:
        logger.warning(f"[social_scraper] Could not fetch {website_url}: {e}")
        return empty

    social_links = _extract_social_links(html)
    images = _extract_images(html, final_url)

    if not social_links:
        logger.info(f"[social_scraper] No social links found for {website_url}")
    else:
        logger.info(f"[social_scraper] Found {len(social_links)} social links for {website_url}: {list(social_links.keys())}")

    image_count = sum(1 for k in ("og_image", "favicon", "logo") if images[k]) + len(images["gallery"])
    logger.info(f"[social_scraper] Found {image_count} image(s) for {website_url}")

    return {"social_links": social_links, "images": images}