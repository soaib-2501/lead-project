import logging
import os
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


def _valid_rating(raw: str):
    """Returns a float rating only if it's a plausible 0.0-5.0 Google Maps
    star rating. Rejects anything else (phone number fragments, photo
    counts, etc.) that a loose regex might otherwise pick up."""
    if not raw:
        return None
    try:
        value = float(raw.replace(",", "."))
    except (ValueError, TypeError):
        return None
    if 0.0 <= value <= 5.0:
        return value
    return None


# Word(s) Google Maps uses right after a review count. "ratings" is
# included defensively alongside "reviews" — some listing types have been
# seen phrasing the widget that way, and accepting both costs nothing
# since we still require the number to sit right next to it.
_REVIEW_WORD = r"(?:google\s+)?(?:reviews?|ratings?)"


def parse_review_count_text(text: str) -> str:
    """
    Google Maps shows review counts in several different formats depending
    on place type/locale — colleges and institutions in particular often
    drop the "(1,234)" parenthetical style used by restaurants/shops, and
    often show LOW single/double-digit counts written as plain text
    ("1 review", "5 reviews") with no parentheses at all.

    FIXED BUG (single-digit counts): the old plain-text pattern required
    the number to have at least 2 characters ("{2,}"), which silently
    rejected single-digit counts like "5 reviews" or "1 review" — a real,
    confirmed cause of reviews showing as 0 for lower-traffic listings
    (colleges, small clinics, etc.) even though Google Maps clearly showed
    a nonzero count.

    FIXED BUG (photos/videos bundled into the same widget text): this used
    to reject the ENTIRE match if "photo(s)"/"video(s)" appeared ANYWHERE
    in the text, on the theory that such text was never a review count.
    But some listing types (confirmed on educational institutions — the
    exact case that was showing 0 reviews despite a valid rating) render
    the rating widget's text/aria-label with the review count and a
    nearby photo/video count bundled into the SAME string, e.g. "4.4
    stars 233 Reviews, 5,000 photos". The blanket check discarded the
    perfectly valid "233" whenever that happened — which also explains
    why rating still came through fine (it's read by a separate, simpler
    regex untouched by this check) while reviews silently came back as 0.
    Now we only reject a specific parenthetical match if THAT number is
    itself immediately followed by "photo(s)"/"video(s)" (e.g. a stray
    "(48) photos" chip), instead of nuking the whole string over a
    mention elsewhere in it. The K-format and plain-count patterns are
    also now tightened to require the review/rating word directly next
    to the number, so they can never latch onto a photo count on their
    own either.
    """
    if not text:
        return ""

    # "45 reviews mention library" / "12 people mentioned parking" — these
    # are per-topic "review highlight" chips, not the actual total review
    # count. Must be excluded here, otherwise the fallback scan in
    # get_rating_and_reviews() can pick up a chip's small number instead
    # of the real total.
    if re.search(r"\bmention", text, re.I):
        return ""

    # "(1,234)" — the common restaurant/shop style. Only reject THIS
    # specific match if it's immediately followed by "photo(s)"/"video(s)"
    # — see the FIXED BUG note above for why we no longer reject based on
    # those words appearing anywhere else in the string.
    match = re.search(r"\(([\d,]+)\)(?!\s*photos?\b)(?!\s*videos?\b)", text, re.I)
    if match:
        return match.group(1).replace(",", "")

    # "1.2K reviews" / "1.2K Reviews" — now requires the review/rating
    # word right next to the K-number so this can never latch onto an
    # unrelated "1.2K photos" figure sitting elsewhere in the same text.
    k_match = re.search(rf"([\d.]+)\s*K\s*{_REVIEW_WORD}\b", text, re.I)
    if k_match:
        try:
            return str(int(float(k_match.group(1)) * 1000))
        except ValueError:
            pass

    # "1,234 reviews" / "5 reviews" / "1 review" / "1,234 Google reviews"
    # / "233 ratings" — no parens, ANY digit count (including single
    # digits — this is the confirmed fix, previously required 2+ chars
    # via "{2,}").
    plain_match = re.search(rf"([\d,]+)\s*{_REVIEW_WORD}\b", text, re.I)
    if plain_match:
        return plain_match.group(1).replace(",", "")

    return ""


def _bbox_top(locator_or_handle):
    """
    Returns the y-coordinate of an element's bounding box, or None if it
    can't be measured (detached/hidden elements). Used to filter out
    "similar places" / "people also search for" carousel cards, which
    always render well below the business's own rating widget near the
    top of the page — this is layout-agnostic (works regardless of which
    CSS class Google currently uses) unlike relying purely on DOM order.
    """
    try:
        box = locator_or_handle.bounding_box()
        if box:
            return box["y"]
    except Exception:
        pass
    return None


def _wait_for_rating_widget(detail_page, timeout_ms: int = 6000):
    """
    Polls for the rating/review widget to actually render before we try to
    read it, instead of relying purely on the caller's single fixed sleep.
    Some listing types render the rating a beat before the review count
    text fills in, or vice versa — this gives both a real chance to appear.
    """
    waited = 0
    step = 300
    while waited < timeout_ms:
        try:
            if detail_page.locator("div.F7nice").count() > 0:
                return True
            if detail_page.locator("[aria-label*='star' i]").count() > 0:
                return True
        except Exception:
            pass
        detail_page.wait_for_timeout(step)
        waited += step
    return False


def _debug_dump_html(detail_page, business_name: str):
    """
    Opt-in diagnostic aid — does nothing unless MAPS_SCRAPER_DEBUG=1 is set
    in the environment. When enabled, and every tier in
    get_rating_and_reviews() still failed to find a review count, this
    saves the full rendered page HTML so the failure can be inspected
    offline (exact classes/aria-labels Google served for that listing)
    instead of guessing from logs alone. Never runs by default, so it
    can't affect performance or disk usage in normal operation.
    """
    if not os.environ.get("MAPS_SCRAPER_DEBUG"):
        return
    try:
        os.makedirs("/tmp/maps_scraper_debug", exist_ok=True)
        safe_name = re.sub(r"[^a-zA-Z0-9_-]+", "_", business_name or "unknown")[:80]
        path = f"/tmp/maps_scraper_debug/{safe_name}_{int(time.time())}.html"
        with open(path, "w", encoding="utf-8") as f:
            f.write(detail_page.content())
        logger.info(f"[get_rating_and_reviews] Debug HTML dumped to {path}")
    except Exception as e:
        logger.info(f"[get_rating_and_reviews] Debug HTML dump failed: {e}")


def get_rating_and_reviews(detail_page, business_name: str = ""):
    """
    Extracts rating + review count for the business currently open in
    detail_page.

    Strategy, in order (each tier only fills in whatever the previous
    tier left missing — never overwrites a value already found):

      Tier 0 — primary div.F7nice widget (first one located ABOVE a
               y=700px cutoff, i.e. inside the visible business info
               panel, not a lower "similar places" carousel card).
      Tier 1 — combined aria-label like "4.5 stars 1,234 Reviews",
               same y-position guard.
      Tier 2 — separate rating element + separate review-count element
               (some layouts, esp. institutions, don't combine them into
               one widget at all).
      Tier 3 — last-resort scan of any element whose aria-label mentions
               "review", still guarded by the y-position cutoff.
      Tier 4 — broadest fallback: plain visible text matching an
               "N review(s)"/"N rating(s)" pattern with NO aria-label
               required at all, for listing types that expose the count
               only as plain text.

    Every tier logs exactly what it saw and matched, so failures are
    diagnosable from logs rather than silent. If MAPS_SCRAPER_DEBUG=1 is
    set and every tier still comes up empty, the full rendered page HTML
    is saved to /tmp/maps_scraper_debug/ for offline inspection.
    """
    rating = ""
    review_count = ""
    tiers_tried = []

    _wait_for_rating_widget(detail_page)

    NEAR_TOP_MAX_Y = 700  # px — business's own widget always renders here;
                          # carousel cards render well below this on any
                          # layout we've seen.

    # ---- Tier 0: primary F7nice widget, position-guarded ----
    try:
        containers = detail_page.locator("div.F7nice")
        total = containers.count()
        for i in range(min(total, 4)):
            container = containers.nth(i)
            top_y = _bbox_top(container)
            if top_y is not None and top_y > NEAR_TOP_MAX_Y:
                continue  # this one's a carousel card further down the page

            try:
                block_text = container.inner_text(timeout=2000)
            except Exception:
                continue
            try:
                aria_text = container.get_attribute("aria-label", timeout=1000) or ""
            except Exception:
                aria_text = ""

            combined = f"{block_text} {aria_text}"
            rating_match = re.search(r"(\d+[.,]\d+)", combined)
            candidate_rating = _valid_rating(rating_match.group(1)) if rating_match else None
            candidate_reviews = parse_review_count_text(combined)

            # Only fill in values still missing — a later container (e.g. a
            # "similar places" card that slipped past the y-position guard)
            # must never clobber a value the first matching container
            # already got right.
            if not rating and candidate_rating is not None:
                rating = f"{candidate_rating}"
            if not review_count and candidate_reviews:
                review_count = candidate_reviews

            if rating or review_count:
                tiers_tried.append(f"Tier0(container#{i}, y={top_y})")
                logger.info(
                    f"[get_rating_and_reviews] '{business_name}' Tier 0 matched "
                    f"container {i} (y={top_y}): rating={rating or 'N/A'}, "
                    f"reviews={review_count or 'N/A'}, raw={combined!r}"
                )
            if rating and review_count:
                break
    except Exception as e:
        logger.info(f"[get_rating_and_reviews] '{business_name}' Tier 0 error: {e}")

    # ---- Tier 1: combined "X stars Y reviews" aria-label, position-guarded ----
    if not rating or not review_count:
        try:
            star_candidates = detail_page.locator("[aria-label*='star' i]")
            star_count = star_candidates.count()
            for i in range(min(star_count, 6)):
                el = star_candidates.nth(i)
                top_y = _bbox_top(el)
                if top_y is not None and top_y > NEAR_TOP_MAX_Y:
                    continue

                label = el.get_attribute("aria-label", timeout=800) or ""
                combo_match = re.search(
                    rf"(\d+[.,]\d+)\s*stars?,?\s*([\d,]+)\s*{_REVIEW_WORD}\b",
                    label, re.I,
                )
                if combo_match:
                    candidate_rating = _valid_rating(combo_match.group(1))
                    if candidate_rating is None:
                        continue
                    if not rating:
                        rating = f"{candidate_rating}"
                    if not review_count:
                        review_count = combo_match.group(2).replace(",", "")
                    tiers_tried.append(f"Tier1(el#{i}, y={top_y})")
                    logger.info(
                        f"[get_rating_and_reviews] '{business_name}' Tier 1 matched "
                        f"element {i} (y={top_y}): rating={rating}, "
                        f"reviews={review_count}, label={label!r}"
                    )
                    break
        except Exception as e:
            logger.info(f"[get_rating_and_reviews] '{business_name}' Tier 1 error: {e}")

    # ---- Tier 2: separate rating element + separate review-count element ----
    # Some layouts (notably institutions/colleges) don't combine rating and
    # review count into one widget at all — the review count instead lives
    # in its own clickable element (e.g. a button/link that jumps to the
    # reviews tab) whose visible text or aria-label is JUST the number.
    if not review_count:
        try:
            review_only_candidates = detail_page.locator(
                "button[aria-label*='review' i], a[aria-label*='review' i], "
                "span[aria-label*='review' i]"
            )
            count = review_only_candidates.count()
            for i in range(min(count, 6)):
                el = review_only_candidates.nth(i)
                top_y = _bbox_top(el)
                if top_y is not None and top_y > NEAR_TOP_MAX_Y:
                    continue

                label = el.get_attribute("aria-label", timeout=800) or ""
                # Require the label to be MOSTLY just a number + "review(s)"
                # word, not a longer sentence — avoids matching unrelated
                # long-form aria text that happens to contain "review".
                tight_match = re.match(
                    rf"^\s*([\d,]+)\s*{_REVIEW_WORD}\s*$", label, re.I
                )
                found = tight_match.group(1).replace(",", "") if tight_match else ""
                if not found:
                    found = parse_review_count_text(label)

                if found:
                    review_count = found
                    tiers_tried.append(f"Tier2(el#{i}, y={top_y})")
                    logger.info(
                        f"[get_rating_and_reviews] '{business_name}' Tier 2 matched "
                        f"element {i} (y={top_y}): reviews={review_count}, label={label!r}"
                    )
                    if not rating:
                        rating_match = re.search(r"(\d+[.,]\d+)", label)
                        candidate = _valid_rating(rating_match.group(1)) if rating_match else None
                        if candidate is not None:
                            rating = f"{candidate}"
                    break
        except Exception as e:
            logger.info(f"[get_rating_and_reviews] '{business_name}' Tier 2 error: {e}")

    # ---- Tier 3: last resort, no position guard, first 3 candidates only ----
    if not review_count:
        try:
            candidates = detail_page.locator("[aria-label*='review' i]")
            count = candidates.count()
            for i in range(min(count, 3)):
                label = candidates.nth(i).get_attribute("aria-label", timeout=800) or ""
                found = parse_review_count_text(label)
                if found:
                    review_count = found
                    tiers_tried.append(f"Tier3(candidate#{i})")
                    if not rating:
                        rating_match = re.search(r"(\d+[.,]\d+)", label)
                        candidate = _valid_rating(rating_match.group(1)) if rating_match else None
                        if candidate is not None:
                            rating = f"{candidate}"
                    logger.info(
                        f"[get_rating_and_reviews] '{business_name}' Tier 3 (last resort) "
                        f"matched: rating={rating or 'N/A'}, reviews={review_count}, label={label!r}"
                    )
                    break
        except Exception as e:
            logger.info(f"[get_rating_and_reviews] '{business_name}' Tier 3 error: {e}")

    logger.info(
        f"[get_rating_and_reviews] FINAL for '{business_name}': "
        f"rating={rating or 'N/A'}, reviews={review_count or 'N/A'}, "
        f"tiers_used={tiers_tried or ['none matched']}"
    )
    if not review_count:
        logger.warning(
            f"[get_rating_and_reviews] '{business_name}': no review count found "
            f"after all tiers — Google Maps DOM layout for this listing type "
            f"isn't covered yet by any selector/regex tried."
        )

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
                detail_page.wait_for_timeout(2000)

                name = get_name(detail_page)
                address = get_text(detail_page, "[data-item-id*='address']")
                phone = get_text(detail_page, "[data-item-id*='phone']")
                category = get_category(detail_page)
                raw_rating, raw_reviews = get_rating_and_reviews(detail_page, business_name=name)
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
                        f"— rating={raw_rating or 'N/A'}, reviews={raw_reviews or 'N/A'}, "
                        f"{len(combined_images)} images, {len(social_links)} social links, "
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