import logging
import re
import time

from playwright.sync_api import sync_playwright

from app.services.social_scraper import extract_site_intel

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


def get_rating_and_reviews(detail_page):
    rating = ""
    review_count = ""
    try:
        block_text = detail_page.locator("div.F7nice").first.inner_text(timeout=3000)
        rating_match = re.search(r"(\d+[.,]\d+)", block_text)
        if rating_match:
            rating = rating_match.group(1).replace(",", ".")

        review_match = re.search(r"\(([\d,]+)\)", block_text)
        if review_match:
            review_count = review_match.group(1).replace(",", "")
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

    Google lazy-loads the photo strip: only the first (hero) photo has a
    real src on initial load, the rest carry a placeholder until scrolled
    into view. We nudge the page with a few small scroll/wait cycles first
    to force those thumbnails to swap in their real src before reading it.

    We also check data-src/data-lazy-src as a fallback, since some lazy-load
    implementations keep the real URL there until the src swap happens, and
    we validate that whatever we capture actually looks like a complete
    Google-hosted image URL rather than a lazy-load placeholder stub.
    """
    images = []

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

            if (
                src.startswith("http")
                and "googleusercontent.com" in src
                and src not in images
            ):
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

                # Social links + brand images + contact email come from the
                # business's own website, not Maps — a separate fetch that
                # can fail independently (site down, no website, blocks
                # bots). It must never take down the rest of the scrape,
                # so it gets its own try/except here.
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

                # Merge image sources: Maps listing photos first (usually
                # higher quality, actual venue photos), then the website's
                # own logo/og-image/gallery as a fallback/supplement —
                # deduplicated while preserving order.
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