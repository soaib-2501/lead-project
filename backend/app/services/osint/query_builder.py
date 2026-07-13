def build_queries(business_name: str, location: str, address: str | None = None) -> list[str]:
    base = f"{business_name} {location}".strip()

    queries = [
        base,
        f"{base} official website",
        f"{base} LinkedIn",
        f"{base} Crunchbase",
        f"{base} company profile",
        f"{base} news",
        f"{base} reviews",
        f"{base} contact",
        f"{base} owner",
        f"{base} careers",
        f"{base} employees",
        f"{base} Facebook",
        f"{base} Instagram",
        f"{base} X (Twitter)",
        f"{base} YouTube",
        f"{base} filetype:pdf",
        f"{base} GitHub",
        f"{base} business registration",
    ]

    if address:
        queries.append(f"{business_name} {address}")

    seen = set()
    unique_queries = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique_queries.append(q)

    return unique_queries