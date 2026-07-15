import logging

from app.services.osint.query_builder import build_queries
from app.services.osint.google_search import search_google
from app.services.osint.extractor import fetch_page
from app.services.osint.utils import (
    get_domain, is_social, is_review_site,
    get_path_length, is_probably_not_business_site,
    extract_sector_number, extract_all_sector_numbers,
    detect_business_type,
)
from app.services.social_scraper import extract_site_intel

logger = logging.getLogger(__name__)

MAX_BUSINESS_CANDIDATES_TO_FETCH = 6
# How many top website candidates we'll run the (slower, more thorough)
# social_scraper email search on, if the fast extractor pass finds nothing.
MAX_CANDIDATES_FOR_DEEP_EMAIL_SEARCH = 3

# Words that describe an exam board / regulatory body rather than the
# business itself. Coaching centers very commonly put these in their
# names ("XYZ Academy (NIOS & CBSE)"), but matching on them lets an
# unrelated official board site (nios.ac.in, cbse.gov.in...) rank as a
# "keyword match" for thousands of different businesses. They're excluded
# from business-identifying keywords entirely.
GENERIC_BOARD_KEYWORDS = {
    "nios", "cbse", "icse", "cisce", "ncert", "board", "aicte", "ugc",
}


def _get_business_keywords(business_name: str) -> list[str]:
    stopwords = {"the", "and", "of", "a", "an"}
    words = business_name.strip().lower().split()
    return [
        w for w in words
        if w not in stopwords and w not in GENERIC_BOARD_KEYWORDS and len(w) > 2
    ]


def _is_relevant(url: str, title: str, description: str, keywords: list[str], target_sector) -> bool:
    domain = get_domain(url)
    text = f"{domain} {title} {description}".lower()

    if target_sector is not None:
        mentioned_sectors = extract_all_sector_numbers(text)
        if mentioned_sectors and target_sector not in mentioned_sectors:
            return False

    if not keywords:
        return True

    return any(keyword in text for keyword in keywords)


def _build_ai_summary(business_name, business_type, location, social_media, business_website) -> str:
    parts = []

    type_label = business_type.lower() if business_type else "business"
    parts.append(f"{business_name} appears to be a {type_label} located in {location}.")

    if social_media:
        platforms = sorted(set(s["platform"] for s in social_media))
        parts.append(f"Active public presence was found on {', '.join(platforms)}.")

    if business_website:
        parts.append("An official website was identified among public search results.")

    if len(parts) == 1:
        parts.append("Limited additional public information was found for this business.")

    return " ".join(parts)


def run_osint_search(business_name: str, location: str, address: str = None) -> dict:
    logger.info("=" * 60)
    logger.info("Starting OSINT search: name=%r location=%r address=%r", business_name, location, address)

    queries = build_queries(business_name, location, address)
    logger.info("Built %d queries", len(queries))
    logger.debug("Queries: %s", queries)

    all_results = []
    for query in queries:
        query_results = search_google(query)
        logger.debug("Query %r → %d results", query, len(query_results))
        all_results.extend(query_results)

    logger.info("Collected %d raw results across all queries", len(all_results))

    seen_urls = set()
    unique_results = []
    for item in all_results:
        if item["url"] not in seen_urls:
            seen_urls.add(item["url"])
            unique_results.append(item)

    logger.info("Deduplicated: %d → %d unique results", len(all_results), len(unique_results))

    keywords = _get_business_keywords(business_name)
    target_sector = extract_sector_number(location) or (
        extract_sector_number(address) if address else None
    )
    logger.debug("Keywords: %s | target_sector: %s", keywords, target_sector)

    filtered_results = [
        item for item in unique_results
        if _is_relevant(item["url"], item["title"], item["snippet"], keywords, target_sector)
    ]

    logger.info("Relevance filter: %d → %d results", len(unique_results), len(filtered_results))

    if not filtered_results:
        logger.warning("Relevance filter removed everything — falling back to unfiltered results")
        filtered_results = unique_results

    social_seen = set()
    social_media = []
    reviews = []
    other_results = []

    for item in filtered_results:
        url = item["url"]
        domain = get_domain(url)
        platform = is_social(domain)
        review_source = is_review_site(domain)

        if platform:
            base_url = url.split("?")[0]
            if base_url in social_seen:
                continue
            social_seen.add(base_url)
            social_media.append({
                "platform": platform,
                "url": url,
                "title": item["title"] or url,
            })
        elif review_source:
            reviews.append({
                "source": review_source,
                "url": url,
                "snippet": item["snippet"],
            })
        else:
            other_results.append({
                "url": url,
                "domain": domain,
                "title": item["title"] or url,
                "description": item["snippet"],
                "path_length": get_path_length(url),
            })

    logger.info(
        "Categorized: %d social, %d reviews, %d other",
        len(social_media), len(reviews), len(other_results),
    )

    search_results = [
        {"title": r["title"], "url": r["url"], "description": r["description"]}
        for r in other_results
    ]

    # is_probably_not_business_site is applied ONLY to fallback_matches.
    # keyword_matches is intentionally left unfiltered by that blacklist:
    # GENERIC_BOARD_KEYWORDS already strips ambiguous board/regulator terms
    # (nios, cbse, ncert...) out of `keywords`, so a real keyword match here
    # is trustworthy — including legitimate .gov.in/.ac.in sites, which is
    # exactly the business's own site for government hospitals, colleges,
    # etc. Applying the blanket domain-suffix filter to keyword_matches too
    # would incorrectly exclude those legitimate cases (it did, for a
    # government hospital whose own site is on .gov.in — the filter kicked
    # out the real site and a job-listing site got picked up instead).
    keyword_matches = [
        r for r in other_results
        if any(k in r["domain"] for k in keywords)
    ]
    fallback_matches = [
        r for r in other_results
        if r not in keyword_matches and not is_probably_not_business_site(r["domain"])
    ]

    logger.info(
        "Website candidates: %d keyword matches, %d fallback matches",
        len(keyword_matches), len(fallback_matches),
    )

    candidates = (
        sorted(keyword_matches, key=lambda x: x["path_length"])
        + sorted(fallback_matches, key=lambda x: x["path_length"])
    )

    business_website = None
    business_website_domain = None
    business_email = None
    business_phone = None
    # All emails found that genuinely belong to the business's own site
    # (may include more than one, e.g. info@ and admissions@ on different
    # pages) — exposed to the frontend so OSINT can show every related
    # email instead of just one.
    business_emails: list[str] = []

    # Pass 1 — fast: use the lightweight extractor (title/description/
    # emails/phones via a single plain-HTTP fetch) to pick the website and
    # grab a phone number, and an email if it's easy to find this way.
    top_candidates = candidates[:MAX_BUSINESS_CANDIDATES_TO_FETCH]

    for candidate in top_candidates:
        if business_website is None:
            business_website = candidate["url"]
            business_website_domain = candidate["domain"]

        # Only trust contact details scraped from a page that actually
        # belongs to the chosen business website's domain. Other top
        # candidates can be unrelated sites (directories, other listings,
        # near-miss keyword matches) that happen to rank high — their
        # emails/phones must never get attributed to this business.
        if candidate["domain"] != business_website_domain:
            logger.info("Skipping unrelated-domain candidate: %s", candidate["url"])
            continue

        logger.info("Fetching candidate: %s", candidate["url"])
        page_data = fetch_page(candidate["url"])

        for found_email in page_data["emails"]:
            if found_email not in business_emails:
                business_emails.append(found_email)

        if business_email is None and page_data["emails"]:
            business_email = page_data["emails"][0]
            logger.info("Found email (fast pass): %s", business_email)

        if business_phone is None and page_data["phones"]:
            business_phone = page_data["phones"][0]
            logger.info("Found phone: %s", business_phone)

        if business_email and business_phone:
            logger.info("Both email and phone found — stopping fast pass early")
            break

    # Pass 2 — thorough: if the fast pass didn't find an email, reuse the
    # same deep email-extraction logic that powers the Lead Search's
    # business-detail email lookup (obfuscation decoding, contact-page
    # discovery, JS-rendered fetch, click-reveal fallback). Restricted to
    # the business's own domain for the same reason as Pass 1.
    if business_email is None and business_website_domain is not None:
        deep_search_candidates = [
            c for c in top_candidates[:MAX_CANDIDATES_FOR_DEEP_EMAIL_SEARCH]
            if c["domain"] == business_website_domain
        ]
        for candidate in deep_search_candidates:
            logger.info("Fast pass found no email — trying deep email search on: %s", candidate["url"])
            try:
                intel = extract_site_intel(candidate["url"])
                if intel.get("email"):
                    business_email = intel["email"]
                    if business_email not in business_emails:
                        business_emails.append(business_email)
                    logger.info("Found email (deep pass): %s", business_email)
                    break
            except Exception as exc:
                logger.info("Deep email search failed for %s: %s", candidate["url"], exc)
                continue

    verified_website = business_website is not None and any(
        km["url"] == business_website for km in keyword_matches
    )

    combined_text_parts = [business_name]
    combined_text_parts += [r["snippet"] for r in reviews]
    combined_text_parts += [r["description"] for r in other_results]
    combined_text_parts += [s["title"] for s in social_media]
    combined_text = " ".join(combined_text_parts)

    business_type = detect_business_type(business_name, fuzzy=True)
    if business_type is None:
        business_type = detect_business_type(combined_text)

    logger.info("Detected business_type: %s", business_type or "Not classified")

    snapshot = {
        "business_type": business_type or "Not classified",
        "location": address or location,
        "verified_website": verified_website,
    }

    ai_summary = _build_ai_summary(
        business_name, business_type, address or location,
        social_media, business_website,
    )

    logger.info(
        "✅ Search complete — website=%s verified=%s email=%s (%d total) phone=%s social=%d reviews=%d other=%d",
        business_website, verified_website, bool(business_email), len(business_emails),
        bool(business_phone), len(social_media), len(reviews), len(search_results),
    )
    logger.info("=" * 60)

    return {
        "business": {
            "name": business_name,
            "website": business_website,
            "phone": business_phone,
            "email": business_email,
            "emails": business_emails,
        },
        "snapshot": snapshot,
        "ai_summary": ai_summary,
        "social_media": social_media,
        "reviews": reviews,
        "search_results": search_results,
    }