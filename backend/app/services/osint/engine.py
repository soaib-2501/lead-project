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

logger = logging.getLogger(__name__)

MAX_BUSINESS_CANDIDATES_TO_FETCH = 6


def _get_business_keywords(business_name: str) -> list[str]:
    stopwords = {"the", "and", "of", "a", "an"}
    words = business_name.strip().lower().split()
    return [w for w in words if w not in stopwords and len(w) > 2]


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

    keyword_matches = [r for r in other_results if any(k in r["domain"] for k in keywords)]
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
    business_email = None
    business_phone = None

    for candidate in candidates[:MAX_BUSINESS_CANDIDATES_TO_FETCH]:
        logger.info("Fetching candidate: %s", candidate["url"])
        page_data = fetch_page(candidate["url"])

        if business_website is None:
            business_website = candidate["url"]

        if business_email is None and page_data["emails"]:
            business_email = page_data["emails"][0]
            logger.info("Found email: %s", business_email)

        if business_phone is None and page_data["phones"]:
            business_phone = page_data["phones"][0]
            logger.info("Found phone: %s", business_phone)

        if business_email and business_phone:
            logger.info("Both email and phone found — stopping candidate fetch early")
            break

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
        "✅ Search complete — website=%s verified=%s email=%s phone=%s social=%d reviews=%d other=%d",
        business_website, verified_website, bool(business_email), bool(business_phone),
        len(social_media), len(reviews), len(search_results),
    )
    logger.info("=" * 60)

    return {
        "business": {
            "name": business_name,
            "website": business_website,
            "phone": business_phone,
            "email": business_email,
        },
        "snapshot": snapshot,
        "ai_summary": ai_summary,
        "social_media": social_media,
        "reviews": reviews,
        "search_results": search_results,
    }