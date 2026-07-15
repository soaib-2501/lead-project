import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
PHONE_REGEX = re.compile(r"(\+\d{1,3}[-.\s]?)?\(?\d{3,4}\)?[-.\s]\d{3,4}[-.\s]?\d{0,4}")
SECTOR_PATTERN = re.compile(r"sector[\s-]*(\d+)", re.IGNORECASE)

PLATFORM_DOMAINS = {
    "linkedin.com": "LinkedIn",
    "facebook.com": "Facebook",
    "instagram.com": "Instagram",
    "twitter.com": "X (Twitter)",
    "x.com": "X (Twitter)",
    "youtube.com": "YouTube",
}

REVIEW_DOMAINS = {
    "glassdoor.com": "Glassdoor",
    "glassdoor.co.in": "Glassdoor",
    "glassdoor.ie": "Glassdoor",
    "indeed.com": "Indeed",
    "trustpilot.com": "Trustpilot",
    "ambitionbox.com": "AmbitionBox",
    "zomato.com": "Zomato",
    "justdial.com": "Justdial",
    "magicpin.in": "MagicPin",
    "eazydiner.com": "EazyDiner",
    "practo.com": "Practo",
    "tripadvisor.com": "TripAdvisor",
    "yelp.com": "Yelp",
}

NON_BUSINESS_DOMAINS = {
    "economictimes.indiatimes.com", "timesofindia.indiatimes.com",
    "financialexpress.com", "hindustantimes.com", "alamy.com",
    "freshersnow.com", "placementdrive.in", "alexahire.in",
    "housing.com", "homebazaar.com", "dnb.com", "globaldata.com",
    "rocketreach.co", "beststartup.in", "lawctopus.com", "signalhire.com",
    "quora.com", "reddit.com", "pinterest.com", "wypages.com",
    "punelist.com", "nativeplanet.com", "nobroker.in", "startupindiamagazine.com",
    # Education boards / govt portals — these show up as high-ranking
    # "keyword matches" for coaching centers (e.g. any business with
    # "NIOS"/"CBSE" in its name) but are never the business's own site.
    "nios.ac.in", "cbse.gov.in", "cbse.nic.in", "cisce.org",
    "ncert.nic.in", "ncert.gov.in", "aicte-india.org", "ugc.ac.in",
    "digilocker.gov.in",
    # Job/recruitment listing sites — these rank highly for hospital/
    # company names because they scrape and republish job postings, but
    # are never the business's own site.
    "allgovernmentjobs.in", "sarkariresult.com", "freejobalert.com",
    "employmentnews.gov.in", "indgovtjobs.in", "governmentjobs.com",
}

# Any domain ending in one of these is almost certainly a government or
# educational-institution portal, not an individual business's own site —
# checked as a suffix so we don't need to enumerate every board/state site.
# NOTE: this is only ever applied to FALLBACK candidates (see engine.py) —
# never to keyword-matched candidates, since a real government hospital's
# or college's own official site legitimately lives on a .gov.in/.ac.in
# domain and must not be excluded just for matching that suffix.
NON_BUSINESS_DOMAIN_SUFFIXES = (
    ".gov.in", ".nic.in", ".ac.in", ".edu.in", ".gov", ".edu",
)

BUSINESS_TYPE_KEYWORDS = {
    "Cafe": ["cafe", "café", "coffee"],
    "Restaurant": ["restaurant", "dining", "cuisine", "eatery", "bistro"],
    "Hotel": ["hotel", "resort", "guest house", "stay"],
    "Salon & Spa": ["salon", "spa", "parlour", "parlor"],
    "Gym & Fitness": ["gym", "fitness", "workout"],
    "Hospital & Clinic": ["hospital", "clinic", "medical", "diagnostic"],
    "Retail Store": ["store", "shop", "mart", "retail", "showroom"],
    "IT / Software Company": ["software", "technologies", "it services", "tech solutions"],
    "Education": ["school", "college", "institute", "academy", "coaching"],
    "Real Estate": ["real estate", "properties", "builders", "realty"],
}


def extract_emails(text: str) -> list[str]:
    return list(set(EMAIL_REGEX.findall(text)))


def extract_phones(text: str) -> list[str]:
    results = []
    for match in PHONE_REGEX.finditer(text):
        value = match.group().strip()
        digits_only = re.sub(r"\D", "", value)

        if re.match(r"^\d{4}\d{2}\d{2}$", digits_only):
            continue

        if 8 <= len(digits_only) <= 13:
            results.append(value)

    return list(set(results))


def get_domain(url: str) -> str:
    try:
        netloc = urlparse(url).netloc.lower()
        return netloc.replace("www.", "")
    except Exception:
        return ""


def get_path_length(url: str) -> int:
    try:
        return len(urlparse(url).path.strip("/"))
    except Exception:
        return 999


def _domain_matches(domain: str, target: str) -> bool:
    return domain == target or domain.endswith("." + target)


def is_social(domain: str):
    for d, platform in PLATFORM_DOMAINS.items():
        if _domain_matches(domain, d):
            return platform
    return None


def is_review_site(domain: str):
    for d, source in REVIEW_DOMAINS.items():
        if _domain_matches(domain, d):
            return source
    return None


def is_probably_not_business_site(domain: str) -> bool:
    if any(_domain_matches(domain, d) for d in NON_BUSINESS_DOMAINS):
        return True
    if any(domain.endswith(suffix) for suffix in NON_BUSINESS_DOMAIN_SUFFIXES):
        return True
    return False


def extract_sector_number(text: str):
    match = SECTOR_PATTERN.search(text)
    if match:
        return int(match.group(1))
    return None


def extract_all_sector_numbers(text: str) -> list[int]:
    return [int(n) for n in SECTOR_PATTERN.findall(text)]


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def detect_business_type(text: str, fuzzy: bool = False):
    text_lower = text.lower()

    for category, keywords in BUSINESS_TYPE_KEYWORDS.items():
        if any(keyword in text_lower for keyword in keywords):
            return category

    if not fuzzy:
        return None

    words = re.findall(r"[a-z]+", text_lower)
    best_category = None
    best_score = 0.0

    for word in words:
        if len(word) < 4:
            continue
        for category, keywords in BUSINESS_TYPE_KEYWORDS.items():
            for keyword in keywords:
                if len(keyword) < 4:
                    continue
                score = _similarity(word, keyword)
                if score > best_score:
                    best_score = score
                    best_category = category

    if best_score >= 0.8:
        return best_category

    return None