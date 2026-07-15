"""
Social media links + brand images + contact email extraction from a
business's own website.

WHY THIS IS A SEPARATE MODULE FROM maps_scraper.py:
Google Maps almost never lists a business's social media accounts, email,
or brand imagery directly — the reliable source is the business's own
website (footer/header links, meta tags, mailto: links), which is a
completely different fetch (a plain HTTP page, not a Maps listing) with a
different failure mode (site down, blocks bots, no website at all). Keeping
it separate means a broken website never touches the Maps scraping logic.

APPROACH (cheapest → most expensive, stopping at the first success):
1. Plain HTTP fetch (httpx) of the homepage — regex + HTML-entity decoding
   + Cloudflare email-protection decoding + "[at]/[dot]" text obfuscation
   decoding, so most static-HTML emails are caught even when hidden from
   naive scrapers.
2. The same checks on a handful of contact/about/support/team/policy pages
   — first via links actually discovered in the homepage's own nav/footer,
   then via a fixed list of common paths.
3. A Playwright-rendered fetch of the homepage — catches emails injected
   by client-side JavaScript after page load, and gets past some light
   bot-protection that blocks plain HTTP requests.
4. A Playwright click-simulation — some sites only reveal their email when
   a mail-icon/button is actually clicked (href="javascript:void(0)", with
   the real mailto: assembled by a JS click-handler). This finds anything
   that looks like a mail icon/link, clicks it, and captures the resulting
   mailto: navigation.

Steps 3 and 4 are meaningfully slower (real browser launches), so they're
genuinely last resorts — most sites are resolved by step 1 or 2.
"""

import html as html_module
import logging
import re
from urllib.parse import urljoin, urlparse

import httpx

logger = logging.getLogger(__name__)

# ---------- Social platform patterns ----------
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

# ---------- Email patterns ----------
MAILTO_PATTERN = re.compile(r'mailto:([a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})', re.I)
PLAIN_EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
CF_EMAIL_PATTERN = re.compile(r'data-cfemail=["\']([a-f0-9]+)["\']', re.I)

# "[at]" / "(at)" / "[dot]" / "(dot)" style obfuscation — unambiguous
# enough (bracket/paren wrapped) that we won't create false positives.
OBFUSCATION_REPLACEMENTS = [
    (re.compile(r'\s*\[\s*at\s*\]\s*', re.I), '@'),
    (re.compile(r'\s*\(\s*at\s*\)\s*', re.I), '@'),
    (re.compile(r'\s*\{\s*at\s*\}\s*', re.I), '@'),
    (re.compile(r'\s*\[\s*dot\s*\]\s*', re.I), '.'),
    (re.compile(r'\s*\(\s*dot\s*\)\s*', re.I), '.'),
    (re.compile(r'\s*\{\s*dot\s*\}\s*', re.I), '.'),
]

EMAIL_NOISE_DOMAINS = (
    "example.com", "sentry.io", "wixpress.com", "godaddy.com",
    "schema.org", "w3.org", "gstatic.com", "googleapis.com",
    "cloudflare.com", "your-email.com", "yourdomain.com", "domain.com",
    "sentry-next.wixpress.com", "wix.com", "cloudfront.net",
)
EMAIL_NOISE_LOCAL_PARTS = (
    "noreply", "no-reply", "donotreply", "do-not-reply", "test",
    "example", "placeholder", "newsletter", "unsubscribe", "notifications",
)
EMAIL_INVALID_TLD_SUFFIXES = (".png", ".jpg", ".jpeg", ".svg", ".gif", ".webp", ".css", ".js")

# Prefixes that indicate a genuine business contact address — checked in
# this priority order when a page has multiple valid emails.
OFFICIAL_EMAIL_PREFIXES = (
    "info", "contact", "hello", "support", "sales",
    "office", "admin", "enquiries", "enquiry", "care", "mailus",
)

# Common free-mail providers that small/local businesses frequently use as
# their only public contact address — accepted even though the domain
# won't match the website's own domain.
COMMON_PERSONAL_MAIL_DOMAINS = (
    "gmail.com", "yahoo.com", "yahoo.in", "outlook.com", "hotmail.com", "rediffmail.com",
)

# Extra pages to check (in this order) if the homepage itself has no usable
# email. Tried one at a time, cheaply, and we stop as soon as one works.
CANDIDATE_PATHS = (
    "/contact", "/contact-us", "/contactus", "/contact-us.html",
    "/about", "/about-us", "/aboutus",
    "/support", "/help",
    "/team", "/our-team",
    "/get-in-touch",
    "/privacy-policy", "/privacy",
    "/terms", "/terms-and-conditions",
)

# Words that, when found inside an <a href> on the homepage, suggest that
# link leads to a contact/about-style page — used to discover the *real*
# contact page path instead of only guessing common ones.
LINK_TEXT_HINTS = ("contact", "about", "support", "team", "get-in-touch", "reach-us", "reach us")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document",
}

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".svg", ".gif")


def _clean_url(raw: str) -> str:
    return raw.rstrip("/\"'")


def _make_absolute(base_url: str, maybe_relative: str) -> str:
    try:
        return urljoin(base_url, maybe_relative)
    except Exception:
        return maybe_relative


def _is_valid_email(email: str) -> bool:
    email_lower = email.lower()

    if email_lower.endswith(EMAIL_INVALID_TLD_SUFFIXES):
        return False

    domain = email_lower.split("@")[-1]
    if any(noise in domain for noise in EMAIL_NOISE_DOMAINS):
        return False

    local_part = email_lower.split("@")[0]
    if any(noise in local_part for noise in EMAIL_NOISE_LOCAL_PARTS):
        return False

    return True


def _email_domain_matches_site(email: str, site_domain: str) -> bool:
    """True if the email's domain belongs to the business's own website,
    or is a common free-mail provider (frequently the only contact address
    small/local businesses list publicly)."""
    email_domain = email.lower().split("@")[-1]

    if email_domain in COMMON_PERSONAL_MAIL_DOMAINS:
        return True

    site_root = site_domain.replace("www.", "")
    return site_root in email_domain or email_domain in site_root


def _pick_best_email(candidates: list[str], site_domain: str) -> str | None:
    """Given all valid emails found, pick the single best one:
    1. Prefer emails whose domain matches the business's own site (or a
       common free-mail provider).
    2. Among those, prefer official-sounding prefixes (info@, contact@...).
    3. Fall back to the first valid match if nothing scores higher."""
    if not candidates:
        return None

    domain_matched = [e for e in candidates if _email_domain_matches_site(e, site_domain)]
    pool = domain_matched if domain_matched else candidates

    for prefix in OFFICIAL_EMAIL_PREFIXES:
        for email in pool:
            local_part = email.lower().split("@")[0]
            if local_part == prefix or local_part.startswith(prefix + "."):
                return email

    return pool[0]


def _decode_cf_email(hex_string: str) -> str | None:
    """Decodes Cloudflare's 'email protection' obfuscation — a simple XOR
    cipher where the first byte is the key. Very common on WordPress and
    many agency-built sites to hide emails from scrapers."""
    try:
        key = int(hex_string[:2], 16)
        decoded = "".join(
            chr(int(hex_string[i:i + 2], 16) ^ key)
            for i in range(2, len(hex_string), 2)
        )
        return decoded
    except Exception:
        return None


def _deobfuscate_text(text: str) -> str:
    """Applies HTML-entity decoding and common bracket-style obfuscation
    ('[at]', '(dot)', etc.) so emails hidden this way become matchable by
    the normal email regex."""
    decoded = html_module.unescape(text)
    for pattern, replacement in OBFUSCATION_REPLACEMENTS:
        decoded = pattern.sub(replacement, decoded)
    return decoded


def _extract_all_emails(raw_html: str) -> list[str]:
    """Collects every valid, de-duplicated email found via four methods,
    in confidence order: mailto: links, Cloudflare-obfuscated emails,
    bracket-obfuscated plain text, and plain-text regex matches."""
    found = []
    seen = set()

    def _add(candidate):
        if candidate and _is_valid_email(candidate) and candidate.lower() not in seen:
            seen.add(candidate.lower())
            found.append(candidate)

    deobfuscated_html = _deobfuscate_text(raw_html)

    for match in MAILTO_PATTERN.finditer(deobfuscated_html):
        _add(match.group(1))

    for match in CF_EMAIL_PATTERN.finditer(raw_html):
        _add(_decode_cf_email(match.group(1)))

    for match in PLAIN_EMAIL_PATTERN.finditer(deobfuscated_html):
        _add(match.group(0))

    return found


def _discover_contact_links(html_text: str, base_url: str, limit: int = 5) -> list[str]:
    """Scans the homepage's own <a href> links for anything that looks like
    a contact/about/support page, instead of only guessing fixed paths."""
    found = []
    seen = set()

    for match in re.finditer(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html_text, re.I | re.S):
        href, link_text = match.group(1), re.sub(r"<[^>]+>", "", match.group(2)).lower()
        haystack = f"{href.lower()} {link_text}"

        if not any(hint in haystack for hint in LINK_TEXT_HINTS):
            continue
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue

        absolute = _make_absolute(base_url, href)
        if urlparse(absolute).netloc != urlparse(base_url).netloc:
            continue

        if absolute not in seen:
            seen.add(absolute)
            found.append(absolute)

        if len(found) >= limit:
            break

    return found


def _extract_social_links(html_text: str) -> dict:
    links = {}

    for ld_match in re.finditer(r'"sameAs"\s*:\s*\[(.*?)\]', html_text, re.S):
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
        for match in pattern.finditer(html_text):
            candidate = _clean_url(match.group(0))
            if any(noise in candidate.lower() for noise in NOISE_PATTERNS):
                continue
            links[platform] = "https://" + candidate
            break

    return links


def _extract_images(html_text: str, base_url: str) -> dict:
    images = {"og_image": None, "favicon": None, "logo": None, "gallery": []}

    og_match = re.search(
        r'<meta[^>]+(?:property|name)=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        html_text, re.I,
    )
    if not og_match:
        og_match = re.search(
            r'<meta[^>]+(?:property|name)=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
            html_text, re.I,
        )
    if og_match:
        images["og_image"] = _make_absolute(base_url, og_match.group(1))

    fav_match = re.search(
        r'<link[^>]+rel=["\'](?:shortcut )?icon["\'][^>]+href=["\']([^"\']+)["\']',
        html_text, re.I,
    )
    if fav_match:
        images["favicon"] = _make_absolute(base_url, fav_match.group(1))
    else:
        images["favicon"] = _make_absolute(base_url, "/favicon.ico")

    logo_match = re.search(r'"logo"\s*:\s*"([^"]+)"', html_text)
    if logo_match:
        images["logo"] = _make_absolute(base_url, logo_match.group(1))

    for img_match in re.finditer(r'<img[^>]+>', html_text, re.I):
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
    for img_match in re.finditer(r'<img[^>]+src=["\']([^"\']+)["\']', html_text, re.I):
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


def _fetch(client: httpx.Client, url: str) -> str | None:
    try:
        response = client.get(url)
        if response.status_code == 200:
            return response.text
    except Exception:
        pass
    return None


def _fetch_rendered_html(url: str, timeout_ms: int = 15000) -> str | None:
    """Last-resort fetch using a real (headless) browser via Playwright.
    Catches emails injected by client-side JavaScript, and often gets past
    light bot-protection that blocks plain HTTP requests but allows real
    browser traffic."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = browser.new_page(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1366, "height": 768},
            )
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        logger.info(f"[social_scraper] Rendered fetch failed for {url}: {e}")
        return None


def _click_reveal_email(url: str, timeout_ms: int = 15000) -> str | None:
    """Final fallback: some sites only reveal their email when a mail-icon
    /button is actually clicked (href="javascript:void(0)", with the real
    mailto: assembled by a JS click-handler) — a common anti-scraping
    trick. This opens the page for real, finds anything that looks like a
    mail icon/link, clicks it, and captures the resulting mailto:
    navigation (browsers open mailto: links as a new tab/page whose URL
    starts with 'mailto:')."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    candidate_selectors = [
        "a[href^='javascript'][aria-label*='mail' i]",
        "a[aria-label*='mail' i]",
        "a[title*='mail' i]",
        "a:has(svg[class*='mail' i])",
        "a[class*='mail' i]",
        "a[href^='javascript']",
    ]

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1366, "height": 768},
            )
            page = context.new_page()
            page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)

            found_email = None

            for selector in candidate_selectors:
                if found_email:
                    break
                try:
                    elements = page.locator(selector)
                    count = min(elements.count(), 3)
                except Exception:
                    continue

                for i in range(count):
                    try:
                        el = elements.nth(i)
                        with context.expect_page(timeout=4000) as new_page_info:
                            el.click(timeout=3000)
                        new_page = new_page_info.value
                        if new_page.url.lower().startswith("mailto:"):
                            candidate = new_page.url[len("mailto:"):].split("?")[0].strip()
                            if _is_valid_email(candidate):
                                found_email = candidate
                        new_page.close()
                        if found_email:
                            break
                    except Exception:
                        continue

            browser.close()
            return found_email

    except Exception as e:
        logger.info(f"[social_scraper] Click-reveal attempt failed for {url}: {e}")
        return None


def _find_email_on_site(client: httpx.Client, homepage_html: str, base_url: str, site_domain: str) -> str | None:
    """Tries, in order, until one yields a usable email:
    1. Homepage itself.
    2. Contact-style links actually found in the homepage's own navigation/footer.
    3. A fixed list of common contact/about/support/team/footer/policy paths.
    4. A JS-rendered fetch of the homepage.
    5. A click-simulation for JS-triggered mailto: reveals.
    Each source is checked fully before moving to the next, and we stop at
    the first success."""

    candidates = _extract_all_emails(homepage_html)
    best = _pick_best_email(candidates, site_domain)
    if best:
        return best

    discovered_links = _discover_contact_links(homepage_html, base_url)
    for link in discovered_links:
        page_html = _fetch(client, link)
        if not page_html:
            continue
        candidates = _extract_all_emails(page_html)
        best = _pick_best_email(candidates, site_domain)
        if best:
            return best

    for path in CANDIDATE_PATHS:
        page_url = urljoin(base_url, path)
        if page_url in discovered_links:
            continue
        page_html = _fetch(client, page_url)
        if not page_html:
            continue
        candidates = _extract_all_emails(page_html)
        best = _pick_best_email(candidates, site_domain)
        if best:
            return best

    rendered_html = _fetch_rendered_html(base_url)
    if rendered_html:
        candidates = _extract_all_emails(rendered_html)
        best = _pick_best_email(candidates, site_domain)
        if best:
            return best

    clicked_email = _click_reveal_email(base_url)
    if clicked_email:
        return clicked_email

    return None


def extract_site_intel(website_url: str, timeout: float = 8.0) -> dict:
    """
    Fetches a business's homepage (plus, if needed, a handful of likely
    contact pages, a JS-rendered fetch, and a click-simulation) and returns
    social profile URLs, brand images, and a contact email in one pass.

    Returns:
        {
            "social_links": {"facebook": "https://...", "instagram": "..."},
            "images": {
                "og_image": "https://...",
                "favicon": "https://...",
                "logo": "https://...",
                "gallery": ["https://...", ...]
            },
            "email": "contact@business.com" | None
        }

    Returns empty structures on any failure — a missing/broken website
    should never crash a whole search batch.
    """
    empty = {
        "social_links": {},
        "images": {"og_image": None, "favicon": None, "logo": None, "gallery": []},
        "email": None,
    }

    if not website_url:
        return empty

    parsed = urlparse(website_url)
    if not parsed.scheme:
        website_url = "https://" + website_url

    try:
        with httpx.Client(headers=HEADERS, timeout=timeout, follow_redirects=True) as client:
            response = client.get(website_url)
            response.raise_for_status()
            html_text = response.text
            final_url = str(response.url)
            site_domain = urlparse(final_url).netloc.lower().replace("www.", "")

            social_links = _extract_social_links(html_text)
            images = _extract_images(html_text, final_url)
            email = _find_email_on_site(client, html_text, final_url, site_domain)

    except Exception as e:
        logger.warning(f"[social_scraper] Could not fetch {website_url} via httpx: {e}")
        # Even the initial fetch failed (likely bot-blocked) — try a
        # rendered fetch as a last resort before giving up entirely.
        rendered_html = _fetch_rendered_html(website_url)
        if not rendered_html:
            return empty

        final_url = website_url
        site_domain = urlparse(final_url).netloc.lower().replace("www.", "")
        social_links = _extract_social_links(rendered_html)
        images = _extract_images(rendered_html, final_url)
        candidates = _extract_all_emails(rendered_html)
        email = _pick_best_email(candidates, site_domain)

        if not email:
            email = _click_reveal_email(website_url)

    if not social_links:
        logger.info(f"[social_scraper] No social links found for {website_url}")
    else:
        logger.info(f"[social_scraper] Found {len(social_links)} social links for {website_url}: {list(social_links.keys())}")

    image_count = sum(1 for k in ("og_image", "favicon", "logo") if images[k]) + len(images["gallery"])
    logger.info(f"[social_scraper] Found {image_count} image(s) for {website_url}")

    if email:
        logger.info(f"[social_scraper] Found email for {website_url}: {email}")
    else:
        logger.info(f"[social_scraper] No email found for {website_url}")

    return {"social_links": social_links, "images": images, "email": email}