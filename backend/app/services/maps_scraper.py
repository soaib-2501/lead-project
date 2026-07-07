from playwright.sync_api import sync_playwright
import re
import time


def get_text(page, selector):
    try:
        return page.locator(selector).first.inner_text(timeout=3000)
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
                return text.strip()
        except Exception:
            continue

    try:
        title = detail_page.title()
        if title and "Google Maps" in title:
            return title.replace(" - Google Maps", "").strip()
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


def get_category(detail_page):
    selectors = ["button.DkEaL", "button[jsaction*='category']"]
    for sel in selectors:
        try:
            text = detail_page.locator(sel).first.inner_text(timeout=2500)
            if text and text.strip():
                return text.strip()
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
                    lines.append(row_text.replace("\n", " ").strip())
                except Exception:
                    continue
            if lines:
                return " | ".join(lines)
    except Exception:
        pass

    try:
        status = detail_page.locator("span.ZDu9vd").first.inner_text(timeout=2000)
        if status:
            return status.strip()
    except Exception:
        pass

    return ""


def build_query(city: str, area: str, category: str, keyword: str = None) -> str:
    """Builds a single Google Maps search query string from form inputs."""
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
        time.sleep(4)

        try:
            page.locator("button:has-text('Accept all')").first.click(timeout=4000)
            time.sleep(1)
        except Exception:
            pass

        try:
            page.wait_for_selector("div[role='feed']", timeout=15000)
        except Exception:
            browser.close()
            return data

        feed = page.locator("div[role='feed']")

        stagnant_rounds = 0
        previous_count = 0

        for _ in range(40):
            feed.evaluate("el => el.scrollTop = el.scrollHeight")
            time.sleep(1.5)

            cards = page.locator("a[href*='/maps/place']")
            current_count = cards.count()

            if current_count >= max_results:
                break
            if current_count == previous_count:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0
            previous_count = current_count

            if stagnant_rounds >= 4:
                break

        cards = page.locator("a[href*='/maps/place']")
        for i in range(cards.count()):
            href = cards.nth(i).get_attribute("href")
            if href:
                collected_hrefs.add(href)

        shared_user_agent = page.evaluate("navigator.userAgent")

        for href in list(collected_hrefs)[:max_results]:
            try:
                detail_page = browser.new_page(user_agent=shared_user_agent)
                detail_page.goto(href, timeout=30000, wait_until="domcontentloaded")
                detail_page.wait_for_timeout(2500)

                name = get_name(detail_page)
                address = get_text(detail_page, "[data-item-id*='address']")
                phone = get_text(detail_page, "[data-item-id*='phone']")
                category = get_category(detail_page)
                rating, review_count = get_rating_and_reviews(detail_page)
                opening_hours = get_opening_hours(detail_page)

                try:
                    website = detail_page.locator(
                        "[data-item-id*='authority']"
                    ).first.get_attribute("href", timeout=3000)
                except Exception:
                    website = ""

                if name:
                    data.append({
                        "place_id": href,
                        "name": name,
                        "category": category,
                        "address": address,
                        "phone": phone,
                        "website": website,
                        "rating": rating,
                        "reviews": review_count,
                        "opening_hours": opening_hours,
                    })

                detail_page.close()

            except Exception:
                continue

        browser.close()

    return data