import logging
import re
import time

from playwright.sync_api import sync_playwright

from app.services.social_scraper import extract_site_intel
from app.services.ddg_fallback_scraper import get_ddg_fallback_intel

logger = logging.getLogger(__name__)


def clean_text(text: str) -> str:
    """Strip emoji/icon characters and extra whitespace that Google Maps embeds in text nodes."""
    if not text:
        return ""
    cleaned = re.sub(r"[^\x00-\x7F]+", "", text)
    return cleaned.strip(" \n\t-")


def get_text(page, selector):
    try:
        raw = page.locator(selector).first.inner_text(timeout=3000)
        return clean_text(raw)
    except Exception:
        return ""


def get_name(detail_page):
    try:
        detail_page.wait_for_selector("h1", timeout=10000)
    except Exception:
        pass

    selectors = ["h1.DUwDvf", "h1.fontHeadlineLarge", "h1"]

    for sel in selectors:
        try:
            text = detail_page.locator(sel).first.inner_text(timeout=3000)
            if text and text.strip():
                return clean_text(text)
        except Exception:
            continue

    try:
        title = detail_page.title()
        if title and "Google Maps" in title:
            return clean_text(title.replace(" - Google Maps", ""))
    except Exception:
        pass

    return ""


def parse_review_count_text(text: str) -> str:
    """
    Google Maps shows review counts in several different formats depending
    on place type/locale — colleges and institutions in particular often
    drop the "(1,234)" parenthetical style used by restaurants/shops.
    Tries several patterns in order of specificity.
    """
    if not text:
        return ""

    # "(1,234)" — the common restaurant/shop style
    match = re.search(r"\(([\d,]+)\)", text)
    if match:
        return match.group(1).replace(",", "")

    # "1.2K reviews" / "1.2K Reviews"
    k_match = re.search(r"([\d.]+)\s*K\b", text, re.I)
    if k_match:
        try:
            return str(int(float(k_match.group(1)) * 1000))
        except ValueError:
            pass

    # "1,234 reviews" / "1234 Reviews" / "1,234 Google reviews" — no parens
    plain_match = re.search(r"([\d,]{2,})\s*(?:google\s+)?reviews?\b", text, re.I)
    if plain_match:
        return plain_match.group(1).replace(",", "")

    return ""


def get_rating_and_reviews(detail_page):
    rating = ""
    review_count = ""
    try:
        block = detail_page.locator("div.F7nice").first
        block_text = block.inner_text(timeout=3000)

        # aria-label often carries the full "4.5 stars 1,234 Reviews" text
        # even when the visible text is split oddly across child spans —
        # a second, usually more complete, source that survives Google's
        # DOM class-name churn better than scraping visible text alone.
        aria_text = ""
        try:
            aria_text = block.get_attribute("aria-label", timeout=1500) or ""
        except Exception:
            pass

        combined_text = f"{block_text} {aria_text}"

        rating_match = re.search(r"(\d+[.,]\d+)", combined_text)
        if rating_match:
            rating = rating_match.group(1).replace(",", ".")

        review_count = parse_review_count_text(combined_text)
    except Exception:
        pass

    return rating, review_count


def parse_rating(raw: str):
    if not raw:
        return None
    try:
        return round(float(raw), 1)
    except (ValueError, TypeError):
        return None


def parse_reviews(raw: str):
    if not raw:
        return 0
    try:
        return int(raw)
    except (ValueError, TypeError):
        return 0


def get_category(detail_page):
    selectors = ["button.DkEaL", "button[jsaction*='category']"]
    for sel in selectors:
        try:
            text = detail_page.locator(sel).first.inner_text(timeout=2500)
            if text and text.strip():
                return clean_text(text)
        except Exception:
            continue
    return ""


def get_opening_hours(detail_page):
    try:
        detail_page.locator("div[jsaction*='hours']").first.click(timeout=2500)
        detail_page.wait_for_timeout(500)
    except Exception:
        pass

    try:
        rows = detail_page.locator("table.eK4R0e tr")
        count = rows.count()
        if count > 0:
            lines = []
            for i in range(count):
                try:
                    row_text = rows.nth(i).inner_text(timeout=1500)
                    cleaned_row = clean_text(row_text.replace("\n", " "))
                    if cleaned_row:
                        lines.append(cleaned_row)
                except Exception:
                    continue
            if lines:
                return " | ".join(lines)
    except Exception:
        pass

    try:
        status = detail_page.locator("span.ZDu9vd").first.inner_text(timeout=2000)
        if status:
            return clean_text(status)
    except Exception:
        pass

    return ""


def get_images(detail_page, max_images: int = 6):
    """
    Collects listing photo URLs from the business's Google Maps page.

    Primary approach: click the hero photo to open the full photo gallery
    overlay, which renders many more images directly into the DOM than the
    lazy horizontal carousel on the main listing view. Falls back to
    scroll-nudging the page if no gallery could be opened.
    """
    images = []

    gallery_opened = False
    for sel in ["button[jsaction*='heroHeaderImage']", "button.aoRNLd", "div.RZ66Rb img"]:
        try:
            detail_page.locator(sel).first.click(timeout=2500)
            detail_page.wait_for_timeout(1200)
            gallery_opened = True
            break
        except Exception:
            continue

    if gallery_opened:
        try:
            for _ in range(4):
                detail_page.mouse.wheel(0, 600)
                detail_page.wait_for_timeout(400)

            imgs = detail_page.locator("img")
            count = imgs.count()
            for i in range(count):
                try:
                    el = imgs.nth(i)
                    src = el.get_attribute("src") or ""
                    if "googleusercontent.com" not in src:
                        src = el.get_attribute("data-src") or el.get_attribute("data-lazy-src") or ""
                except Exception:
                    continue

                if src.startswith("http") and "googleusercontent.com" in src and src not in images:
                    images.append(src)

                if len(images) >= max_images:
                    break
        except Exception:
            pass

        try:
            detail_page.keyboard.press("Escape")
            detail_page.wait_for_timeout(500)
        except Exception:
            pass

    if not images:
        for _ in range(4):
            try:
                detail_page.mouse.wheel(0, 400)
            except Exception:
                break
            detail_page.wait_for_timeout(500)

        try:
            imgs = detail_page.locator("img")
            count = imgs.count()
            for i in range(count):
                try:
                    el = imgs.nth(i)
                    src = el.get_attribute("src") or ""
                    if "googleusercontent.com" not in src:
                        src = el.get_attribute("data-src") or el.get_attribute("data-lazy-src") or ""
                except Exception:
                    continue

                if src.startswith("http") and "googleusercontent.com" in src and src not in images:
                    images.append(src)

                if len(images) >= max_images:
                    break
        except Exception:
            pass

    return images


def build_query(city: str, area: str, category: str, keyword: str = None) -> str:
    parts = []
    if keyword:
        parts.append(keyword)
    parts.append(category)
    parts.append("in")
    if area:
        parts.append(area)
    parts.append(city)
    return " ".join(parts)


def scrape(query: str, max_results: int = 20) -> list[dict]:
    """Runs one Google Maps text-search query and returns a list of business dicts."""
    logger.info(f"[scrape] Launching browser for query: '{query}' (max_results={max_results})")

    data = []
    collected_hrefs = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"],
        )

        page = browser.new_page(
            viewport={"width": 1366, "height": 768},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="en-US",
        )

        page.goto(
            "https://www.google.com/maps/search/" + query.replace(" ", "+"),
            timeout=60000,
        )
        logger.info("[scrape] Page loaded, waiting for content to settle...")
        time.sleep(4)

        try:
            page.locator("button:has-text('Accept all')").first.click(timeout=4000)
            logger.info("[scrape] Dismissed cookie/consent dialog")
            time.sleep(1)
        except Exception:
            logger.info("[scrape] No consent dialog found (or already dismissed)")

        try:
            page.wait_for_selector("div[role='feed']", timeout=15000)
        except Exception:
            logger.warning("[scrape] Results feed never appeared — returning empty list")
            browser.close()
            return data

        feed = page.locator("div[role='feed']")

        stagnant_rounds = 0
        previous_count = 0

        for round_num in range(40):
            feed.evaluate("el => el.scrollTop = el.scrollHeight")
            time.sleep(1.5)

            cards = page.locator("a[href*='/maps/place']")
            current_count = cards.count()
            logger.info(f"[scrape] Scroll round {round_num + 1}: {current_count} cards loaded so far")

            if current_count >= max_results:
                logger.info("[scrape] Reached max_results during scroll, stopping")
                break
            if current_count == previous_count:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0
            previous_count = current_count

            if stagnant_rounds >= 4:
                logger.info("[scrape] Feed stagnant for 4 rounds, stopping scroll")
                break

        cards = page.locator("a[href*='/maps/place']")
        for i in range(cards.count()):
            href = cards.nth(i).get_attribute("href")
            if href:
                collected_hrefs.add(href)

        logger.info(f"[scrape] Collected {len(collected_hrefs)} unique place links, visiting up to {max_results}")

        shared_user_agent = page.evaluate("navigator.userAgent")

        for idx, href in enumerate(list(collected_hrefs)[:max_results], start=1):
            try:
                detail_page = browser.new_page(user_agent=shared_user_agent)
                detail_page.goto(href, timeout=30000, wait_until="domcontentloaded")
                detail_page.wait_for_timeout(2500)

                name = get_name(detail_page)
                address = get_text(detail_page, "[data-item-id*='address']")
                phone = get_text(detail_page, "[data-item-id*='phone']")
                category = get_category(detail_page)
                raw_rating, raw_reviews = get_rating_and_reviews(detail_page)
                opening_hours = get_opening_hours(detail_page)
                maps_images = get_images(detail_page)

                try:
                    raw_website = detail_page.locator(
                        "[data-item-id*='authority']"
                    ).first.get_attribute("href", timeout=3000)
                    website = raw_website.strip() if raw_website else ""
                except Exception:
                    website = ""

                # Social links + brand images + contact email: prefer the
                # business's own website when it exists (most accurate,
                # via social_scraper.py). If there's no website, fall back
                # to DuckDuckGo search instead of leaving these fields
                # empty. Either path can fail independently and must never
                # take down the rest of the scrape, so each gets its own
                # try/except.
                social_links = {}
                website_images = {"og_image": None, "favicon": None, "logo": None, "gallery": []}
                email = None

                if website:
                    try:
                        intel = extract_site_intel(website)
                        social_links = intel["social_links"]
                        website_images = intel["images"]
                        email = intel.get("email")
                    except Exception as e:
                        logger.info(f"[scrape] Site intel extraction failed for {website}: {e}")
                else:
                    try:
                        fallback = get_ddg_fallback_intel(name, address)
                        social_links = fallback["social_links"]
                        website_images["gallery"] = fallback["images"]
                    except Exception as e:
                        logger.info(f"[scrape] DDG fallback lookup failed for '{name}': {e}")

                # Merge image sources: Maps listing photos first (usually
                # higher quality, actual venue photos), then the website's
                # own logo/og-image/gallery (or the DDG fallback gallery)
                # as a supplement — deduplicated while preserving order.
                combined_images = list(maps_images)
                for extra in [website_images["logo"], website_images["og_image"], *website_images["gallery"]]:
                    if extra and extra not in combined_images:
                        combined_images.append(extra)

                if name:
                    data.append({
                        "place_id": href,
                        "name": name,
                        "category": category,
                        "address": address,
                        "phone": phone,
                        "website": website,
                        "email": email,
                        "rating": parse_rating(raw_rating),
                        "reviews": parse_reviews(raw_reviews),
                        "opening_hours": opening_hours,
                        "images": combined_images,
                        "favicon": website_images["favicon"],
                        "social_links": social_links,
                    })
                    logger.info(
                        f"[scrape] ({idx}/{min(len(collected_hrefs), max_results)}) Scraped: {name} "
                        f"— {len(combined_images)} images, {len(social_links)} social links, "
                        f"email={'yes' if email else 'no'}"
                    )
                else:
                    logger.warning(f"[scrape] ({idx}/{min(len(collected_hrefs), max_results)}) No name found, skipping: {href}")

                detail_page.close()

            except Exception as e:
                logger.warning(f"[scrape] ({idx}) Failed to scrape {href}: {e}")
                continue

        browser.close()

    logger.info(f"[scrape] Done — {len(data)} businesses collected out of {len(collected_hrefs)} links visited")
    return data